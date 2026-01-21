"""
Обработчик ссылок - скачивание видео и аудио

Провайдеры:
- Instagram: RapidAPI (primary)
- YouTube: yt-dlp → pytubefix → SaveNow API (CDN, IP не банится!)
- TikTok, Pinterest: yt-dlp → RapidAPI (fallback)
"""
import re
import os
import time
import logging
import asyncio
import aiohttp
from aiogram import Router, types, F
from aiogram.types import FSInputFile, BufferedInputFile, InputMediaPhoto, InputMediaVideo

from ..services.downloader import VideoDownloader
from ..services.rapidapi_downloader import RapidAPIDownloader
from ..services.pytubefix_downloader import PytubeDownloader
from ..services.instaloader_downloader import InstaloaderDownloader
from ..services.savenow_downloader import SaveNowDownloader
from ..services.cache import (
    get_cached_file_ids,
    cache_file_ids,
    acquire_user_slot,
    release_user_slot,
    increment_active_downloads,
    decrement_active_downloads,
    increment_active_uploads,
    decrement_active_uploads,
)
from ..messages import (
    CAPTION,
    get_downloading_message,
    get_processing_message,
    get_compressing_message,
    get_uploading_message,
    get_extracting_audio_message,
    get_unsupported_url_message,
    get_rate_limit_message,
    get_message,
    get_error_message,
)
from bot_manager.middlewares import log_action
from bot_manager.services.error_logger import error_logger
from shared.utils.video_fixer import get_video_dimensions, get_video_duration, download_thumbnail, ensure_faststart

router = Router()
logger = logging.getLogger(__name__)

# === Per-Request Timeouts для больших файлов ===
# aiogram 3.24.0 НЕ поддерживает ClientTimeout в request_timeout (баг/ограничение)
# Используем числовые таймауты (в секундах) вместо ClientTimeout
TIMEOUT_DOCUMENT = 1800  # 30 минут для 2GB файлов
TIMEOUT_VIDEO = 900      # 15 минут для видео
TIMEOUT_PHOTO = 300      # 5 минут для фото
TIMEOUT_CAROUSEL = 1200  # 20 минут для каруселей
TIMEOUT_AUDIO = 600      # 10 минут для аудио

# Глобальные экземпляры загрузчиков
downloader = VideoDownloader()  # yt-dlp (TikTok, Pinterest)
rapidapi = RapidAPIDownloader()  # Instagram primary, TikTok/Pinterest fallback
pytubefix = PytubeDownloader()  # YouTube (primary)
savenow = SaveNowDownloader()  # YouTube fallback (CDN, не googlevideo!)
instaloader_dl = InstaloaderDownloader()  # Instagram (primary)

# NOTE: Таймауты теперь настроены глобально в main.py через ClientTimeout
# ClientTimeout(total=None, sock_read=1200) в aiohttp session
# Здесь используем request_timeout только для переопределения если нужно

# === RETRY CONFIGURATION ===
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF = [5, 10, 20]  # секунды между попытками

# Ошибки которые стоит ретраить (network/transport)
RETRYABLE_ERRORS = (
    ConnectionResetError,
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)
RETRYABLE_ERROR_STRINGS = (
    "closing transport",
    "connection reset",
    "server disconnected",
    "broken pipe",
    "timed out",
    "network error",
)

# === PHASE 7.0 TELEMETRY: Error Classification ===
# HARD_KILL = мгновенный fallback + cooldown (IP ban, auth required)
# STALL = retry once, then fallback (network issues)
# PROVIDER_BUG = логируем, не cooldown (parser error, format unavailable)
HARD_KILL_PATTERNS = (
    "ssl: unexpected_eof",
    "ssl_error_eof",
    "403 forbidden",
    "429 too many",
    "sign in to confirm",
    "login required",
    "private video",
    "age-restricted",
)
STALL_PATTERNS = (
    "download stalled",
    "connection timeout",
    "incomplete read",
    "no progress",
    "connection reset",
    "server disconnected",
)


def classify_error(error: str) -> str:
    """
    Phase 7.0 Telemetry: Классифицирует ошибку для аналитики и cooldown.

    Returns:
        'HARD_KILL' - IP ban, auth required → instant fallback + cooldown
        'STALL' - network issue → retry once, then fallback
        'PROVIDER_BUG' - parser error → log only, no cooldown
    """
    if not error:
        return "PROVIDER_BUG"

    error_lower = error.lower()

    for pattern in HARD_KILL_PATTERNS:
        if pattern in error_lower:
            return "HARD_KILL"

    for pattern in STALL_PATTERNS:
        if pattern in error_lower:
            return "STALL"

    return "PROVIDER_BUG"


def get_content_bucket(platform: str, content_type: str = None, duration_sec: int = 0) -> str:
    """
    Phase 7.1 Telemetry: Определяет bucket по типу контента.

    Args:
        platform: youtube/instagram/tiktok/pinterest
        content_type: тип контента (reel/post/story/carousel/photo/video)
        duration_sec: длительность в секундах (для YouTube)

    Returns:
        - youtube: 'shorts' (<5 min) / 'full' (>=5 min)
        - instagram: 'reel' / 'post' / 'story' / 'carousel'
        - tiktok: 'video'
        - pinterest: 'photo' / 'video'
    """
    if platform == "youtube":
        return "shorts" if duration_sec < 300 else "full"
    elif platform == "instagram":
        return content_type or "post"
    elif platform == "tiktok":
        return "video"
    elif platform == "pinterest":
        return content_type or "video"
    return "unknown"


def detect_instagram_bucket(url: str, is_carousel: bool = False) -> str:
    """
    Определяет тип Instagram контента по URL.

    Returns:
        'reel' / 'story' / 'carousel' / 'post'
    """
    url_lower = url.lower()
    if "/reel/" in url_lower or "/reels/" in url_lower:
        return "reel"
    elif "/stories/" in url_lower:
        return "story"
    elif is_carousel:
        return "carousel"
    return "post"


def _is_retryable_error(error: Exception) -> bool:
    """Проверяет, стоит ли ретраить эту ошибку"""
    # Проверяем тип исключения
    if isinstance(error, RETRYABLE_ERRORS):
        return True

    # Проверяем текст ошибки
    error_str = str(error).lower()
    return any(s in error_str for s in RETRYABLE_ERROR_STRINGS)


async def send_with_retry(
    send_func,
    file_path: str,
    filename: str,
    thumb_path: str | None = None,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
    backoff: list = None,
    **send_kwargs
):
    """
    Отправка файла с retry логикой.

    Args:
        send_func: async функция отправки (message.answer_video, message.answer_photo)
        file_path: путь к файлу
        filename: имя файла для Telegram
        thumb_path: путь к thumbnail (опционально)
        max_attempts: максимум попыток
        backoff: список задержек между попытками [5, 10, 20]
        **send_kwargs: дополнительные аргументы для send_func
            - Если thumbnail=True и thumb_path задан, создаст FSInputFile для thumbnail

    Returns:
        Результат send_func (Message)

    Raises:
        Exception: если все попытки исчерпаны
    """
    if backoff is None:
        backoff = RETRY_BACKOFF

    last_error = None

    for attempt in range(max_attempts):
        try:
            # Пересоздаём FSInputFile на каждую попытку (handle может быть "одноразовый")
            media_file = FSInputFile(file_path, filename=filename)

            # Копируем kwargs для модификации
            kwargs = dict(send_kwargs)

            # Пересоздаём thumbnail если есть путь и флаг thumbnail=True
            if thumb_path and os.path.exists(thumb_path) and kwargs.get('thumbnail') is True:
                kwargs['thumbnail'] = FSInputFile(thumb_path)
            elif kwargs.get('thumbnail') is True:
                # thumbnail=True но нет файла — убираем из kwargs
                kwargs.pop('thumbnail', None)

            # Отправляем
            result = await send_func(media_file, **kwargs)
            return result

        except Exception as e:
            last_error = e

            if not _is_retryable_error(e):
                # Не ретраим: "file too big", "bad request", etc
                logger.warning(f"[RETRY] Non-retryable error (attempt {attempt + 1}): {e}")
                raise

            if attempt < max_attempts - 1:
                wait_time = backoff[attempt] if attempt < len(backoff) else backoff[-1]
                logger.warning(
                    f"[RETRY] Retryable error (attempt {attempt + 1}/{max_attempts}): {e}. "
                    f"Waiting {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"[RETRY] All {max_attempts} attempts failed: {e}")
                raise

    # Не должны сюда попасть, но на всякий случай
    raise last_error or Exception("All retry attempts failed")


# Паттерн для поддерживаемых URL
URL_PATTERN = re.compile(
    r"https?://(?:www\.|m\.|vm\.|vt\.|[a-z]{2}\.)?"
    r"(?:"
    r"tiktok\.com|"                          # TikTok
    r"instagram\.com|instagr\.am|"           # Instagram (все форматы)
    r"youtube\.com|youtu\.be|"               # YouTube (полные + Shorts)
    r"pinterest\.[a-z.]+|pin\.it"            # Pinterest + короткие ссылки
    r")"
    r"[^\s]*",
    re.IGNORECASE
)


def extract_url_from_text(text: str) -> str | None:
    """Извлечь URL из текста (для сообщений типа 'Take a look at https://...')"""
    if not text:
        return None
    match = URL_PATTERN.search(text)
    return match.group() if match else None


async def resolve_short_url(url: str) -> str:
    """Разрезолвить короткую ссылку Pinterest (pin.it) в полную"""
    if 'pin.it' in url.lower():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    resolved_url = str(resp.url)
                    logger.info(f"Resolved short URL: {url} -> {resolved_url}")
                    return resolved_url
        except Exception as e:
            logger.warning(f"Failed to resolve short URL {url}: {e}")
            return url
    return url


async def update_progress_message(status_msg, done_event: asyncio.Event, progress_data: dict, start_time: float):
    """
    Обновляет статус-сообщение каждые 60 секунд показывая время и прогресс:
    - "⏳ Скачиваю... 1 мин"
    - "⏳ Скачиваю... 3 мин, 45 MB / 200 MB"
    - "⏳ Скачиваю... 7 мин, 150 MB / 200 MB"
    """
    UPDATE_INTERVAL = 60  # Обновление каждые 60 секунд

    try:
        last_update_time = start_time

        while not done_event.is_set():
            await asyncio.sleep(UPDATE_INTERVAL)

            if done_event.is_set():
                break

            # Считаем прошедшее время
            elapsed = int(time.time() - start_time)
            minutes = elapsed // 60

            # Формируем сообщение
            downloaded = progress_data.get('downloaded_bytes', 0)
            total = progress_data.get('total_bytes', 0)

            if total and downloaded:
                downloaded_mb = int(downloaded / (1024 * 1024))
                total_mb = int(total / (1024 * 1024))
                text = f"⏳ Скачиваю... {minutes} мин, {downloaded_mb} MB / {total_mb} MB"
            else:
                text = f"⏳ Скачиваю... {minutes} мин, подождите"

            try:
                await status_msg.edit_text(text)
                logger.info(f"[PROGRESS] {minutes}min update: {downloaded}/{total} bytes")
            except Exception as e:
                logger.warning(f"[PROGRESS] Failed to update message: {e}")

    except asyncio.CancelledError:
        logger.debug("[PROGRESS] Task cancelled")
    except Exception as e:
        logger.warning(f"[PROGRESS] Update error: {e}")


def use_rapidapi_primary(url: str) -> bool:
    """Проверяет, нужно ли использовать RapidAPI как ОСНОВНОЙ способ"""
    url_lower = url.lower()
    # RapidAPI только для Instagram (yt-dlp требует авторизации)
    # YouTube обрабатывается отдельно по длительности
    return any(domain in url_lower for domain in [
        'instagram.com', 'instagr.am'
    ])

def supports_rapidapi_fallback(url: str) -> bool:
    """Проверяет, поддерживает ли RapidAPI этот URL как FALLBACK"""
    url_lower = url.lower()
    # RapidAPI поддерживает YouTube (Shorts fallback), TikTok, Pinterest
    # Instagram уже использует RapidAPI primary
    return any(domain in url_lower for domain in [
        'youtube.com', 'youtu.be',
        'tiktok.com',
        'pinterest.', 'pin.it'
    ])


def make_user_friendly_error(error: str) -> str:
    """Преобразует техническую ошибку в человекочитаемую"""
    if not error:
        return get_error_message("unknown")

    error_lower = error.lower()

    # Уже человеческие ошибки (начинаются с эмодзи) - возвращаем как есть
    if error.startswith(("❌", "⏱", "📦", "🔒", "🌍", "⚠️", "📡", "⚙️", "📤", "🔗")):
        return error

    # Технические ошибки -> человеческие (используем messages.py)
    if "too large" in error_lower or "слишком большое" in error_lower:
        return get_error_message("too_large")
    elif "no media" in error_lower or "no suitable" in error_lower or "not found" in error_lower:
        return get_error_message("not_found")
    elif "timeout" in error_lower or "timed out" in error_lower:
        return get_error_message("timeout")
    elif "unavailable" in error_lower or "not available" in error_lower:
        return get_error_message("unavailable")
    elif "private" in error_lower or "login" in error_lower:
        return get_error_message("private")
    elif "region" in error_lower or "country" in error_lower:
        return get_error_message("region")
    elif "api error" in error_lower or "api" in error_lower:
        return get_error_message("api")
    elif "connection" in error_lower or "network" in error_lower:
        return get_error_message("connection")
    else:
        return get_error_message("unknown")


@router.message(F.text)
async def handle_url(message: types.Message):
    """Обработка ссылок - скачивание видео/фото + аудио"""
    # Извлекаем URL из текста (работает с "Take a look at URL" и пересланными сообщениями)
    url = extract_url_from_text(message.text)
    if not url:
        return

    user_id = message.from_user.id

    # Резолвим короткие ссылки Pinterest (pin.it -> pinterest.com)
    url = await resolve_short_url(url)

    logger.info(f"Download request: user={user_id}, url={url}")

    # Определяем платформу для логирования
    platform = "unknown"
    if "instagram" in url.lower() or "instagr.am" in url.lower():
        platform = "instagram"
    elif "tiktok" in url.lower():
        platform = "tiktok"
    elif "youtube" in url.lower() or "youtu.be" in url.lower():
        platform = "youtube"
    elif "pinterest" in url.lower() or "pin.it" in url.lower():
        platform = "pinterest"

    # Логируем запрос на скачивание
    await log_action(user_id, "download_request", {"platform": platform, "url": url[:200]})

    # === ПРОВЕРЯЕМ КЭШ (мгновенная отправка) ===
    cached_video, cached_audio = await get_cached_file_ids(url)

    if cached_video:
        logger.info(f"Cache hit! Sending cached files: user={user_id}")
        try:
            # Пробуем как видео, если не получится - как фото
            try:
                await message.answer_video(video=cached_video, caption=CAPTION)
            except Exception:
                await message.answer_photo(photo=cached_video, caption=CAPTION)
            if cached_audio:
                await message.answer_audio(audio=cached_audio, caption=CAPTION)
            return
        except Exception as e:
            logger.warning(f"Cache send failed, re-downloading: {e}")
            # Кэш протух, скачиваем заново

    # === ПРОВЕРЯЕМ RATE LIMIT ===
    if not await acquire_user_slot(user_id):
        await message.answer(get_rate_limit_message())
        return

    # Ops Dashboard: увеличиваем счётчик активных скачиваний
    await increment_active_downloads()

    # Статус сообщение
    status_msg = await message.answer(get_downloading_message())

    # Данные о прогрессе скачивания (для обновления сообщения)
    progress_data = {
        'downloaded_bytes': 0,
        'total_bytes': 0,
        'speed': 0,
        # Phase 7.0 Telemetry: stage breakdown
        'first_byte_time': None,  # Время когда начали получать данные
        'download_end_time': None,  # Время завершения скачивания
    }

    # Callback для прогресса yt-dlp
    last_log_time = [0]  # Используем список чтобы изменять в замыкании
    def progress_callback(d):
        if d['status'] == 'downloading':
            progress_data['downloaded_bytes'] = d.get('downloaded_bytes', 0)
            progress_data['total_bytes'] = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            progress_data['speed'] = d.get('speed', 0)

            # Phase 7.0 Telemetry: фиксируем момент первого байта
            if progress_data['first_byte_time'] is None and progress_data['downloaded_bytes'] > 0:
                progress_data['first_byte_time'] = time.time()

            # Логируем прогресс раз в 60 секунд (для отладки)
            now = time.time()
            if now - last_log_time[0] >= 60:
                downloaded_mb = progress_data['downloaded_bytes'] / (1024 * 1024)
                total_mb = progress_data['total_bytes'] / (1024 * 1024) if progress_data['total_bytes'] else 0
                speed_kbps = (progress_data['speed'] or 0) / 1024
                logger.info(f"[PROGRESS] {downloaded_mb:.1f}MB / {total_mb:.1f}MB, speed={speed_kbps:.1f}KB/s")
                last_log_time[0] = now

        elif d['status'] == 'finished':
            # Phase 7.0 Telemetry: фиксируем момент завершения скачивания
            progress_data['download_end_time'] = time.time()

    # === ЗАМЕРЯЕМ ВРЕМЯ СКАЧИВАНИЯ ===
    download_start = time.time()

    # Прогресс для долгих загрузок
    done_event = asyncio.Event()
    progress_task = asyncio.create_task(update_progress_message(status_msg, done_event, progress_data, download_start))

    # === ПЕРЕМЕННЫЕ ДЛЯ CLEANUP (инициализируем до try для доступа в finally) ===
    result = None  # Результат скачивания (содержит file_path)
    thumb_path = None  # Путь к thumbnail
    api_source = None  # Источник API для cleanup

    try:
        logger.info(f"[HANDLER_START] user={user_id}, platform={platform}, url={url[:100]}")

        # === ВЫБИРАЕМ ЗАГРУЗЧИК ===
        # Instagram -> instaloader (primary) → RapidAPI (fallback)
        # YouTube Shorts (<5 мин) -> pytubefix (primary) → RapidAPI (fallback)
        # YouTube полные (≥5 мин) -> только pytubefix
        # TikTok/Pinterest -> yt-dlp

        is_instagram = any(d in url.lower() for d in ['instagram.com', 'instagr.am'])
        is_youtube = any(d in url.lower() for d in ['youtube.com', 'youtu.be'])

        # INSTAGRAM - RapidAPI (instaloader блокируется Instagram без логина)
        if is_instagram:
            logger.info(f"[INSTAGRAM] Using RapidAPI: {url}")
            api_source = "rapidapi"

            # Скачиваем ВСЕ медиа (для каруселей)
            carousel = await rapidapi.download_all(url)

            if not carousel.success:
                error_class = classify_error(carousel.error)
                logger.warning(f"Download failed: user={user_id}, error={carousel.error}, class={error_class}")
                await error_logger.log_error_by_telegram_id(
                    telegram_id=user_id,
                    bot_username="SaveNinja_bot",
                    platform=platform,
                    url=url,
                    error_type="download_failed",
                    error_message=carousel.error,
                    error_details={"source": "rapidapi", "error_class": error_class}
                )
                await status_msg.edit_text(f"❌ {make_user_friendly_error(carousel.error)}")
                return

            # === КАРУСЕЛЬ (несколько файлов) ===
            if len(carousel.files) > 1:
                await status_msg.edit_text(get_uploading_message())

                # Формируем MediaGroup
                media_group = []
                for i, file in enumerate(carousel.files):
                    input_file = FSInputFile(file.file_path, filename=file.filename)
                    caption = CAPTION if i == 0 else None  # Подпись только к первому

                    if file.is_photo:
                        media_group.append(InputMediaPhoto(media=input_file, caption=caption))
                    else:
                        # Извлекаем размеры и длительность для правильного отображения
                        width, height = get_video_dimensions(file.file_path)
                        duration = get_video_duration(file.file_path)
                        media_group.append(InputMediaVideo(
                            media=input_file,
                            caption=caption,
                            duration=duration if duration > 0 else None,
                            width=width if width > 0 else None,
                            height=height if height > 0 else None,
                            supports_streaming=True
                        ))

                # Отправляем альбом с ClientTimeout для sock_read
                # Retry logic для каруселей (fallback на случай реальных network issues)
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await message.answer_media_group(
                            media=media_group,
                            request_timeout=TIMEOUT_CAROUSEL,  # 20 минут для каруселей
                        )
                        break  # Success
                    except (ConnectionResetError, ConnectionError, TimeoutError, Exception) as e:
                        error_str = str(e).lower()
                        if "closing transport" in error_str or "connection reset" in error_str or "timeout" in error_str:
                            if attempt < max_retries - 1:
                                wait_time = 5 * (2 ** attempt)  # 5s, 10s, 20s
                                logger.warning(f"Carousel upload failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                                await asyncio.sleep(wait_time)
                                # Recreate media group (streams might be consumed)
                                media_group = []
                                for i, file in enumerate(carousel.files):
                                    input_file = FSInputFile(file.file_path, filename=file.filename)
                                    caption = CAPTION if i == 0 else None
                                    if file.is_photo:
                                        media_group.append(InputMediaPhoto(media=input_file, caption=caption))
                                    else:
                                        # Извлекаем размеры и длительность для правильного отображения
                                        width, height = get_video_dimensions(file.file_path)
                                        duration = get_video_duration(file.file_path)
                                        media_group.append(InputMediaVideo(
                                            media=input_file,
                                            caption=caption,
                                            duration=duration if duration > 0 else None,
                                            width=width if width > 0 else None,
                                            height=height if height > 0 else None,
                                            supports_streaming=True
                                        ))
                            else:
                                logger.error(f"Carousel upload failed after {max_retries} attempts: {e}")
                                raise
                        else:
                            raise  # Other errors - don't retry

                # Рассчитываем метрики производительности
                download_time_ms = int((time.time() - download_start) * 1000)
                total_size = sum(f.file_size or 0 for f in carousel.files)
                download_speed = int(total_size / download_time_ms * 1000 / 1024) if download_time_ms > 0 else 0

                logger.info(f"Sent carousel: user={user_id}, files={len(carousel.files)}, time={download_time_ms}ms, size={total_size}")
                await log_action(
                    user_id, "download_success",
                    {
                        "type": "carousel",
                        "platform": platform,
                        "bucket": "carousel",
                        "files_count": len(carousel.files),
                        "has_video": carousel.has_video,
                    },
                    download_time_ms=download_time_ms,
                    file_size_bytes=total_size,
                    download_speed_kbps=download_speed,
                    api_source=api_source
                )

                # Извлекаем аудио из первого видео (если есть)
                if carousel.has_video:
                    await status_msg.edit_text(get_extracting_audio_message())
                    video_file = next((f for f in carousel.files if not f.is_photo), None)
                    if video_file:
                        audio_result = await downloader.extract_audio(video_file.file_path)
                        if audio_result.success:
                            audio_file = FSInputFile(audio_result.file_path, filename=audio_result.filename)
                            await message.answer_audio(
                                audio=audio_file,
                                caption=CAPTION,
                                title=carousel.title[:60] if carousel.title else "audio",
                                performer=carousel.author if carousel.author else None,
                                request_timeout=TIMEOUT_AUDIO,  # 10 минут для аудио
                            )
                            await log_action(user_id, "audio_extracted", {"platform": platform})
                            await downloader.cleanup(audio_result.file_path)

                # Очистка
                for file in carousel.files:
                    if api_source == "instaloader":
                        await instaloader_dl.cleanup(file.file_path)
                    else:
                        await rapidapi.cleanup(file.file_path)
                await status_msg.delete()
                return

            # === ОДИН ФАЙЛ (не карусель) ===
            from ..services.downloader import DownloadResult, MediaInfo
            single_file = carousel.files[0]
            result = DownloadResult(
                success=True,
                file_path=single_file.file_path,
                filename=single_file.filename,
                file_size=single_file.file_size,
                is_photo=single_file.is_photo,
                info=MediaInfo(
                    title=carousel.title or "video",
                    author=carousel.author or "unknown",
                    thumbnail=single_file.thumbnail,  # RapidAPI/ffmpeg thumbnail
                    platform="instagram"
                )
            )

        # YOUTUBE: yt-dlp (primary) -> pytubefix (fallback #1) -> SaveNow (fallback #2, CDN)
        elif is_youtube:
            from ..services.downloader import DownloadResult, MediaInfo

            # Step 1: yt-dlp (быстрый, напрямую с YouTube CDN)
            logger.info(f"[YOUTUBE] Trying yt-dlp: {url}")
            result = await downloader.download(url, progress_callback=progress_callback)
            api_source = "ytdlp"

            if not result.success:
                # Step 2: pytubefix (иногда работает когда yt-dlp нет)
                logger.warning(f"[YOUTUBE] yt-dlp failed: {result.error}, trying pytubefix")
                pytube_result = await pytubefix.download(url, quality="720p")

                if pytube_result.success:
                    api_source = "pytubefix"
                    result = DownloadResult(
                        success=True,
                        file_path=pytube_result.file_path,
                        filename=pytube_result.filename,
                        file_size=pytube_result.file_size,
                        is_photo=False,
                        send_as_document=pytube_result.file_size > 50_000_000,  # >50MB как документ
                        info=MediaInfo(
                            title=pytube_result.title or "video",
                            author=pytube_result.author or "unknown",
                            thumbnail=pytube_result.thumbnail_url,
                            platform=platform
                        ),
                        # Phase 7.0 Telemetry
                        download_host=pytube_result.download_host
                    )
                else:
                    # Step 3: SaveNow API (CDN проксирует, IP не банится)
                    logger.warning(f"[YOUTUBE] pytubefix failed: {pytube_result.error}, trying SaveNow API")
                    await status_msg.edit_text("⏳ Пробую альтернативный способ...")

                    # Получаем примерную длительность для адаптивного качества
                    duration_hint = 0
                    try:
                        info = await pytubefix.get_video_info(url)
                        if info.success:
                            duration_hint = info.duration
                    except:
                        pass

                    file_result = await savenow.download_adaptive(url, duration_hint=duration_hint)

                    if file_result.success:
                        api_source = "savenow"
                        logger.info(f"[YOUTUBE] SaveNow succeeded: {file_result.filename}, host={file_result.download_host}")

                        # Проверяем размер
                        if file_result.file_size > 2_000_000_000:
                            await status_msg.edit_text("❌ Видео слишком большое (>2GB)")
                            await savenow.cleanup(file_result.file_path)
                            return

                        result = DownloadResult(
                            success=True,
                            file_path=file_result.file_path,
                            filename=file_result.filename,
                            file_size=file_result.file_size,
                            is_photo=False,
                            send_as_document=file_result.file_size > 50_000_000,
                            info=MediaInfo(
                                title=file_result.title or "video",
                                author=file_result.author or "unknown",
                                thumbnail=file_result.thumbnail_path,  # SaveNow возвращает локальный путь
                                platform=platform
                            ),
                            # Phase 7.0 Telemetry: передаем данные из SaveNowResult
                            prep_ms=file_result.prep_ms,
                            download_ms=file_result.download_ms,
                            download_host=file_result.download_host,
                            quota_snapshot=file_result.quota_snapshot.to_dict() if file_result.quota_snapshot else None
                        )
                    else:
                        # Все 3 способа упали
                        error_class = classify_error(result.error)  # Классифицируем по первой ошибке
                        logger.error(f"[YOUTUBE] All 3 methods failed: yt-dlp, pytubefix, SaveNow, class={error_class}")
                        await error_logger.log_error_by_telegram_id(
                            telegram_id=user_id,
                            bot_username="SaveNinja_bot",
                            platform=platform,
                            url=url,
                            error_type="download_failed",
                            error_message=f"yt-dlp: {result.error}, pytubefix: {pytube_result.error}, SaveNow: {file_result.error}",
                            error_details={
                                "source": "all_three",
                                "error_class": error_class,
                                "ytdlp_class": classify_error(result.error),
                                "pytubefix_class": classify_error(pytube_result.error),
                                "savenow_class": classify_error(file_result.error),
                            }
                        )
                        await status_msg.edit_text(f"❌ {make_user_friendly_error(result.error)}")
                        return

        # TikTok, Pinterest -> yt-dlp (primary) -> RapidAPI (fallback)
        else:
            result = await downloader.download(url, progress_callback=progress_callback)
            api_source = "ytdlp"

            if not result.success:
                logger.warning(f"yt-dlp failed: user={user_id}, error={result.error}")

                # FALLBACK: RapidAPI
                if supports_rapidapi_fallback(url):
                    logger.info(f"Trying RapidAPI fallback for: {url}")
                    await status_msg.edit_text("⏳ Пробую альтернативный способ...")

                    from ..services.downloader import DownloadResult, MediaInfo
                    file_result = await rapidapi.download(url, adaptive_quality=False)

                    if file_result.success:
                        logger.info(f"RapidAPI fallback succeeded: {file_result.filename}")
                        api_source = "rapidapi"

                        if file_result.file_size > 2_000_000_000:
                            await status_msg.edit_text("❌ Видео слишком большое (>2GB)")
                            await rapidapi.cleanup(file_result.file_path)
                            return

                        result = DownloadResult(
                            success=True,
                            file_path=file_result.file_path,
                            filename=file_result.filename,
                            file_size=file_result.file_size,
                            is_photo=file_result.is_photo,
                            send_as_document=False,
                            info=MediaInfo(
                                title=file_result.title or "video",
                                author=file_result.author or "unknown",
                                thumbnail=file_result.thumbnail,
                                platform=platform
                            )
                        )
                    else:
                        error_class = classify_error(result.error)
                        logger.error(f"Both yt-dlp and RapidAPI failed for: {url}, class={error_class}")
                        await error_logger.log_error_by_telegram_id(
                            telegram_id=user_id,
                            bot_username="SaveNinja_bot",
                            platform=platform,
                            url=url,
                            error_type="download_failed",
                            error_message=f"yt-dlp: {result.error}, RapidAPI: {file_result.error}",
                            error_details={
                                "source": "both",
                                "error_class": error_class,
                                "ytdlp_class": classify_error(result.error),
                                "rapidapi_class": classify_error(file_result.error),
                            }
                        )
                        await status_msg.edit_text(f"❌ {make_user_friendly_error(result.error)}")
                        return
                else:
                    error_class = classify_error(result.error)
                    await error_logger.log_error_by_telegram_id(
                        telegram_id=user_id,
                        bot_username="SaveNinja_bot",
                        platform=platform,
                        url=url,
                        error_type="download_failed",
                        error_message=result.error,
                        error_details={"source": "yt-dlp", "error_class": error_class}
                    )
                    await status_msg.edit_text(f"❌ {make_user_friendly_error(result.error)}")
                    return

        # Отправляем медиа
        await status_msg.edit_text(get_uploading_message())

        file_id = None

        if result.is_photo:
            # === ОТПРАВЛЯЕМ ФОТО (с retry) ===
            async def _send_photo(media_file, **kwargs):
                return await message.answer_photo(photo=media_file, **kwargs)

            photo_msg = await send_with_retry(
                send_func=_send_photo,
                file_path=result.file_path,
                filename=result.filename,
                caption=CAPTION,
                request_timeout=TIMEOUT_PHOTO,  # 5 минут для фото
            )
            file_id = photo_msg.photo[-1].file_id if photo_msg.photo else None

            # Рассчитываем метрики производительности
            download_time_ms = int((time.time() - download_start) * 1000)
            file_size = result.file_size or (os.path.getsize(result.file_path) if result.file_path else 0)
            download_speed = int(file_size / download_time_ms * 1000 / 1024) if download_time_ms > 0 else 0

            # Phase 7.1: content bucket для фото
            photo_bucket = "photo" if platform == "pinterest" else detect_instagram_bucket(url)

            logger.info(f"Sent photo: user={user_id}, size={file_size}, time={download_time_ms}ms, bucket={photo_bucket}")
            await log_action(
                user_id, "download_success",
                {"type": "photo", "platform": platform, "bucket": photo_bucket},
                download_time_ms=download_time_ms,
                file_size_bytes=file_size,
                download_speed_kbps=download_speed,
                api_source=api_source
            )

            # Кэшируем file_id
            await cache_file_ids(url, file_id, None)
            await status_msg.delete()

        else:
            # Проверяем размер файла (лимит Local Bot API Server - 2GB)
            file_size = result.file_size or (os.path.getsize(result.file_path) if result.file_path else 0)
            MAX_FILE_SIZE = 2_000_000_000  # 2GB (Local Bot API Server)

            if file_size > MAX_FILE_SIZE:
                size_mb = file_size / 1024 / 1024
                await status_msg.edit_text(get_error_message("too_large"))
                logger.warning(f"File too large: {size_mb:.1f}MB > 2GB limit")
                return  # Cleanup будет в finally

            # === ОТПРАВЛЯЕМ ВИДЕО (до 2GB с Local Bot API Server) ===
            # Статус уже "📤 Отправляю..." после скачивания

            # Гарантируем faststart (moov atom в начале) для корректного preview/duration
            # yt-dlp и pytubefix обычно уже делают это, но для RapidAPI нужно явно
            ensure_faststart(result.file_path)

            # Извлекаем размеры и длительность для правильного отображения
            # duration в sendVideo - "железный" способ показать длительность (не зависит от moov atom)
            width, height = get_video_dimensions(result.file_path)
            duration = get_video_duration(result.file_path)

            # Скачиваем/используем thumbnail (превью)
            # Это даёт preview "как у конкурентов" вместо чёрного прямоугольника
            if result.info and result.info.thumbnail:
                thumbnail_value = result.info.thumbnail
                if thumbnail_value.startswith('http'):
                    # URL — скачиваем и ужимаем
                    thumb_path = download_thumbnail(thumbnail_value)
                elif os.path.exists(thumbnail_value):
                    # Локальный файл (ffmpeg extracted) — используем напрямую
                    thumb_path = thumbnail_value
                    logger.info(f"[THUMBNAIL] Using local file: {thumb_path}")

            # === ОТПРАВКА С RETRY (3 попытки, backoff 5/10/20s) ===
            # Phase 7.0 Telemetry: измеряем upload_ms
            upload_start = time.time()

            async def _send_video(media_file, **kwargs):
                return await message.answer_video(video=media_file, **kwargs)

            video_msg = await send_with_retry(
                send_func=_send_video,
                file_path=result.file_path,
                filename=result.filename,
                thumb_path=thumb_path,
                caption=CAPTION,
                thumbnail=True,  # Флаг что нужен thumbnail (send_with_retry создаст FSInputFile)
                duration=duration if duration > 0 else None,
                width=width if width > 0 else None,
                height=height if height > 0 else None,
                supports_streaming=True,
                request_timeout=TIMEOUT_VIDEO,  # 15 минут для видео
            )
            upload_ms = int((time.time() - upload_start) * 1000)
            file_id = video_msg.video.file_id if video_msg.video else None

            # Рассчитываем метрики производительности
            total_ms = int((time.time() - download_start) * 1000)
            file_size = result.file_size or (os.path.getsize(result.file_path) if result.file_path else 0)
            download_speed = int(file_size / total_ms * 1000 / 1024) if total_ms > 0 else 0

            # Phase 7.1 Telemetry: content bucket для аналитики по подтипам
            if platform == "instagram":
                # Для Instagram определяем тип из URL (reel/post/story)
                content_bucket = detect_instagram_bucket(url)
            else:
                # YouTube: shorts/full по duration, TikTok/Pinterest: video
                content_bucket = get_content_bucket(platform, duration_sec=duration)

            # Phase 7.0 Telemetry: собираем данные из result (SaveNowResult и др.)
            prep_ms = getattr(result, 'prep_ms', None) or 0
            download_ms = getattr(result, 'download_ms', None) or 0
            download_host = getattr(result, 'download_host', None)
            quota_snapshot = getattr(result, 'quota_snapshot', None)

            # Phase 7.0 Telemetry: stage breakdown из progress_callback (для yt-dlp)
            # Если result не имеет prep_ms/download_ms, вычисляем из progress_data
            if prep_ms == 0 and progress_data.get('first_byte_time'):
                # prep = время от старта до первого байта
                prep_ms = int((progress_data['first_byte_time'] - download_start) * 1000)
            if download_ms == 0 and progress_data.get('first_byte_time') and progress_data.get('download_end_time'):
                # download = время от первого байта до завершения
                download_ms = int((progress_data['download_end_time'] - progress_data['first_byte_time']) * 1000)
            elif download_ms == 0 and progress_data.get('first_byte_time'):
                # fallback: download = total - prep - upload (приблизительно)
                download_ms = max(0, total_ms - prep_ms - upload_ms)

            # Fallback download_host по платформе (для yt-dlp который не трекает host)
            if not download_host:
                platform_hosts = {
                    "youtube": "googlevideo.com",
                    "tiktok": "tiktokcdn.com",
                    "pinterest": "pinimg.com",
                    "instagram": "cdninstagram.com",
                }
                download_host = platform_hosts.get(platform, "unknown")

            # Telemetry details для Ops API
            telemetry = {
                "type": "video",
                "platform": platform,
                "bucket": content_bucket,
                "duration_sec": duration,
                "prep_ms": prep_ms,
                "download_ms": download_ms,
                "upload_ms": upload_ms,
                "total_ms": total_ms,
                "download_host": download_host,
            }
            # Добавляем quota если есть
            if quota_snapshot:
                telemetry["quota"] = quota_snapshot.to_dict() if hasattr(quota_snapshot, 'to_dict') else None

            logger.info(f"Sent video: user={user_id}, size={file_size}, total={total_ms}ms, prep={prep_ms}ms, download={download_ms}ms, upload={upload_ms}ms, bucket={content_bucket}")
            await log_action(
                user_id, "download_success",
                telemetry,
                download_time_ms=total_ms,
                file_size_bytes=file_size,
                download_speed_kbps=download_speed,
                api_source=api_source
            )

            # Кэшируем file_id
            await cache_file_ids(url, file_id, None)
            await status_msg.delete()

            # Логируем успешное завершение
            total_time = time.time() - download_start
            logger.info(f"[HANDLER_SUCCESS] user={user_id}, total_time={total_time:.1f}s")

    except Exception as e:
        error_class = classify_error(str(e))
        logger.exception(f"Handler error: {e}, class={error_class}")
        await error_logger.log_error_by_telegram_id(
            telegram_id=user_id,
            bot_username="SaveNinja_bot",
            platform=platform,
            url=url,
            error_type="exception",
            error_message=str(e)[:200],
            error_details={
                "exception_type": type(e).__name__,
                "error_class": error_class,
                "api_source": api_source,
            }
        )

        # Человеческие сообщения об ошибках (используем messages.py)
        error_str = str(e).lower()

        if "closing transport" in error_str or "connection reset" in error_str:
            error_text = get_error_message("transport")
        elif "timeout" in error_str or "timed out" in error_str:
            error_text = get_error_message("timeout")
        elif "too large" in error_str:
            error_text = get_error_message("too_large")
        elif "no space" in error_str or "disk" in error_str:
            error_text = get_error_message("processing")
        else:
            error_text = get_error_message("unknown")

        try:
            await status_msg.edit_text(error_text)
        except:
            pass
    finally:
        # Останавливаем фоновую задачу обновления прогресса
        done_event.set()
        progress_task.cancel()

        # === CLEANUP: Всегда чистим файлы (даже при ошибках) ===
        try:
            # Чистим основной файл
            if result and result.file_path and os.path.exists(result.file_path):
                if api_source == "rapidapi":
                    await rapidapi.cleanup(result.file_path)
                elif api_source == "pytubefix":
                    await pytubefix.cleanup(result.file_path)
                elif api_source == "savenow":
                    await savenow.cleanup(result.file_path)
                elif api_source == "instaloader":
                    await instaloader_dl.cleanup(result.file_path)
                else:
                    await downloader.cleanup(result.file_path)
                logger.debug(f"[CLEANUP] Cleaned main file: {result.file_path}")

            # Чистим thumbnail
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
                logger.debug(f"[CLEANUP] Cleaned thumbnail: {thumb_path}")

        except Exception as cleanup_error:
            logger.warning(f"[CLEANUP] Error during cleanup: {cleanup_error}")

        # Освобождаем слот юзера
        await release_user_slot(user_id)

        # Ops Dashboard: уменьшаем счётчик активных скачиваний
        await decrement_active_downloads()


@router.message(F.text)
async def handle_text(message: types.Message):
    """Обработка текста без поддерживаемой ссылки"""
    # Пропускаем команды
    if message.text.startswith("/"):
        return

    # Проверяем, есть ли вообще ссылка в сообщении
    if "http" in message.text.lower():
        # Есть ссылка, но не поддерживаемая
        await message.answer(get_unsupported_url_message())
    else:
        # Просто текст без ссылки
        await message.answer(
            "📎 Отправь мне ссылку на видео.\n\n"
            "Поддерживаю: TikTok, Instagram, YouTube Shorts, Pinterest"
        )
