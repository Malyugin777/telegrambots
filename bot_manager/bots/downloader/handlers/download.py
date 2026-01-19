"""
Обработчик ссылок - скачивание видео и аудио

Используем:
- Instagram: instaloader (primary) → RapidAPI (fallback)
- YouTube Shorts (<5 мин): pytubefix (primary) → RapidAPI (fallback)
- YouTube полные (≥5 мин): pytubefix (только)
- TikTok, Pinterest: yt-dlp (работает хорошо)
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
from ..services.cache import (
    get_cached_file_ids,
    cache_file_ids,
    acquire_user_slot,
    release_user_slot,
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
from shared.utils.video_fixer import get_video_dimensions, get_video_duration

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
rapidapi = RapidAPIDownloader()  # Fallback для Instagram, YouTube Shorts
pytubefix = PytubeDownloader()  # YouTube (primary)
instaloader_dl = InstaloaderDownloader()  # Instagram (primary)

# NOTE: Таймауты теперь настроены глобально в main.py через ClientTimeout
# ClientTimeout(total=None, sock_read=1200) в aiohttp session
# Здесь используем request_timeout только для переопределения если нужно

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

    # Статус сообщение
    status_msg = await message.answer(get_downloading_message())

    # Данные о прогрессе скачивания (для обновления сообщения)
    progress_data = {
        'downloaded_bytes': 0,
        'total_bytes': 0,
        'speed': 0,
    }

    # Callback для прогресса yt-dlp
    last_log_time = [0]  # Используем список чтобы изменять в замыкании
    def progress_callback(d):
        if d['status'] == 'downloading':
            progress_data['downloaded_bytes'] = d.get('downloaded_bytes', 0)
            progress_data['total_bytes'] = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            progress_data['speed'] = d.get('speed', 0)

            # Логируем прогресс раз в 60 секунд (для отладки)
            import time
            now = time.time()
            if now - last_log_time[0] >= 60:
                downloaded_mb = progress_data['downloaded_bytes'] / (1024 * 1024)
                total_mb = progress_data['total_bytes'] / (1024 * 1024) if progress_data['total_bytes'] else 0
                speed_kbps = (progress_data['speed'] or 0) / 1024
                logger.info(f"[PROGRESS] {downloaded_mb:.1f}MB / {total_mb:.1f}MB, speed={speed_kbps:.1f}KB/s")
                last_log_time[0] = now

    # === ЗАМЕРЯЕМ ВРЕМЯ СКАЧИВАНИЯ ===
    download_start = time.time()

    # Прогресс для долгих загрузок
    done_event = asyncio.Event()
    progress_task = asyncio.create_task(update_progress_message(status_msg, done_event, progress_data, download_start))

    try:
        logger.info(f"[HANDLER_START] user={user_id}, platform={platform}, url={url[:100]}")

        # Переменная для отслеживания используемого API
        api_source = None

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
                logger.warning(f"Download failed: user={user_id}, error={carousel.error}")
                await error_logger.log_error_by_telegram_id(
                    telegram_id=user_id,
                    bot_username="SaveNinja_bot",
                    platform=platform,
                    url=url,
                    error_type="download_failed",
                    error_message=carousel.error,
                    error_details={"source": "rapidapi"}
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
                    {"type": "carousel", "platform": platform, "files_count": len(carousel.files)},
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
                    platform="instagram"
                )
            )

        # YOUTUBE - pytubefix (primary), RapidAPI fallback для Shorts
        elif is_youtube:
            logger.info(f"[YOUTUBE] Getting video info: {url}")

            # Получаем инфо чтобы узнать длительность
            info = await pytubefix.get_video_info(url)

            if not info.success:
                # Не получилось получить инфо - пробуем скачать сразу
                logger.warning(f"[YOUTUBE] pytubefix info failed: {info.error}, trying direct download")
                pytube_result = await pytubefix.download(url, quality="720p")
                api_source = "pytubefix"

                # Преобразуем PytubeResult → DownloadResult
                from ..services.downloader import DownloadResult, MediaInfo
                if pytube_result.success:
                    result = DownloadResult(
                        success=True,
                        file_path=pytube_result.file_path,
                        filename=pytube_result.filename,
                        file_size=pytube_result.file_size,
                        is_photo=False,
                        send_as_document=False,
                        info=MediaInfo(
                            title=pytube_result.title or "video",
                            author=pytube_result.author or "unknown",
                            platform=platform
                        )
                    )
                else:
                    result = DownloadResult(success=False, error=pytube_result.error)

            elif info.duration > 0 and info.duration < 300:
                # Короткое видео (<5 мин = Shorts) - pytubefix primary, RapidAPI fallback
                logger.info(f"[YOUTUBE] Shorts detected ({info.duration}s), using pytubefix (primary)")
                pytube_result = await pytubefix.download(url, quality="720p")

                if pytube_result.success:
                    api_source = "pytubefix"

                    # Преобразуем PytubeResult → DownloadResult
                    from ..services.downloader import DownloadResult, MediaInfo
                    result = DownloadResult(
                        success=True,
                        file_path=pytube_result.file_path,
                        filename=pytube_result.filename,
                        file_size=pytube_result.file_size,
                        is_photo=False,
                        send_as_document=False,
                        info=MediaInfo(
                            title=pytube_result.title or "video",
                            author=pytube_result.author or "unknown",
                            platform=platform
                        )
                    )
                else:
                    # FALLBACK: RapidAPI для Shorts
                    logger.warning(f"[YOUTUBE] pytubefix failed for Shorts: {pytube_result.error}, trying RapidAPI fallback")
                    await status_msg.edit_text("⏳ Пробую альтернативный способ...")

                    from ..services.downloader import DownloadResult, MediaInfo
                    file_result = await rapidapi.download(url, adaptive_quality=False)

                    if not file_result.success:
                        # Оба упали
                        logger.error(f"[YOUTUBE] Both pytubefix and RapidAPI failed for Shorts")
                        await error_logger.log_error_by_telegram_id(
                            telegram_id=user_id,
                            bot_username="SaveNinja_bot",
                            platform=platform,
                            url=url,
                            error_type="download_failed",
                            error_message=f"pytubefix: {pytube_result.error}, RapidAPI: {file_result.error}",
                            error_details={"source": "both"}
                        )
                        await status_msg.edit_text(f"❌ {make_user_friendly_error(pytube_result.error)}")
                        return

                    api_source = "rapidapi"

                    # Проверяем размер
                    file_size = file_result.file_size or 0
                    if file_size > 2_000_000_000:  # > 2GB
                        await status_msg.edit_text(get_error_message("too_large"))
                        await rapidapi.cleanup(file_result.file_path)
                        return

                    # Создаём DownloadResult
                    result = DownloadResult(
                        success=True,
                        file_path=file_result.file_path,
                        filename=file_result.filename,
                        file_size=file_result.file_size,
                        is_photo=False,
                        send_as_document=False,
                        info=MediaInfo(
                            title=file_result.title or "video",
                            author=file_result.author or "unknown",
                            platform=platform
                        )
                    )

            else:
                # Длинное видео (≥5 мин) - только pytubefix (720p)
                logger.info(f"[YOUTUBE] Full video detected ({info.duration}s), using pytubefix only (720p)")
                pytube_result = await pytubefix.download(url, quality="720p")
                api_source = "pytubefix"

                # Преобразуем PytubeResult → DownloadResult
                from ..services.downloader import DownloadResult, MediaInfo
                if pytube_result.success:
                    result = DownloadResult(
                        success=True,
                        file_path=pytube_result.file_path,
                        filename=pytube_result.filename,
                        file_size=pytube_result.file_size,
                        is_photo=False,
                        send_as_document=False,
                        info=MediaInfo(
                            title=pytube_result.title or "video",
                            author=pytube_result.author or "unknown",
                            platform=platform
                        )
                    )
                else:
                    result = DownloadResult(success=False, error=pytube_result.error)

        # TikTok, Pinterest -> yt-dlp
        else:
            result = await downloader.download(url, progress_callback=progress_callback)
            api_source = "ytdlp"

        if not result.success:
            logger.warning(f"yt-dlp failed: user={user_id}, error={result.error}")

            # === FALLBACK: Пробуем RapidAPI если yt-dlp упал ===
            if supports_rapidapi_fallback(url):
                logger.info(f"Trying RapidAPI fallback for: {url}")
                await status_msg.edit_text("⏳ Пробую альтернативный способ...")

                # Для YouTube используем adaptive_quality, для TikTok/Pinterest - обычный режим
                from ..services.downloader import DownloadResult, MediaInfo
                use_adaptive = is_youtube
                file_result = await rapidapi.download(url, adaptive_quality=use_adaptive)

                if file_result.success:
                    logger.info(f"RapidAPI fallback succeeded: {file_result.filename}")
                    api_source = "rapidapi"

                    # Проверяем размер
                    file_size = file_result.file_size or 0
                    if file_size > 2_000_000_000:  # > 2GB
                        await status_msg.edit_text("❌ Видео слишком большое (>2GB), не могу отправить в Telegram")
                        await rapidapi.cleanup(file_result.file_path)
                        return

                    result = DownloadResult(
                        success=True,
                        file_path=file_result.file_path,
                        filename=file_result.filename,
                        file_size=file_result.file_size,
                        is_photo=file_result.is_photo,
                        send_as_document=False,  # Всегда отправляем как видео
                        info=MediaInfo(
                            title=file_result.title or "video",
                            author=file_result.author or "unknown",
                            platform=platform
                        )
                    )
                else:
                    # Оба способа упали
                    logger.error(f"Both yt-dlp and RapidAPI failed for: {url}")
                    await error_logger.log_error_by_telegram_id(
                        telegram_id=user_id,
                        bot_username="SaveNinja_bot",
                        platform=platform,
                        url=url,
                        error_type="download_failed",
                        error_message=f"yt-dlp: {result.error}, RapidAPI: {file_result.error}",
                        error_details={"source": "both"}
                    )
                    await status_msg.edit_text(f"❌ {make_user_friendly_error(result.error)}")
                    return
            else:
                # Нет fallback - показываем ошибку yt-dlp
                await error_logger.log_error_by_telegram_id(
                    telegram_id=user_id,
                    bot_username="SaveNinja_bot",
                    platform=platform,
                    url=url,
                    error_type="download_failed",
                    error_message=result.error,
                    error_details={"source": "yt-dlp"}
                )
                await status_msg.edit_text(f"❌ {make_user_friendly_error(result.error)}")
                return

        # Отправляем медиа
        await status_msg.edit_text(get_uploading_message())

        media_file = FSInputFile(result.file_path, filename=result.filename)
        file_id = None

        if result.is_photo:
            # === ОТПРАВЛЯЕМ ФОТО ===
            photo_msg = await message.answer_photo(
                photo=media_file,
                caption=CAPTION,
                request_timeout=TIMEOUT_PHOTO,  # 5 минут для фото
            )
            file_id = photo_msg.photo[-1].file_id if photo_msg.photo else None

            # Рассчитываем метрики производительности
            download_time_ms = int((time.time() - download_start) * 1000)
            file_size = result.file_size or (os.path.getsize(result.file_path) if result.file_path else 0)
            download_speed = int(file_size / download_time_ms * 1000 / 1024) if download_time_ms > 0 else 0

            logger.info(f"Sent photo: user={user_id}, size={file_size}, time={download_time_ms}ms")
            await log_action(
                user_id, "download_success",
                {"type": "photo", "platform": platform},
                download_time_ms=download_time_ms,
                file_size_bytes=file_size,
                download_speed_kbps=download_speed,
                api_source=api_source
            )

            # Кэшируем и удаляем
            await cache_file_ids(url, file_id, None)
            if api_source == "rapidapi":
                await rapidapi.cleanup(result.file_path)
            elif api_source == "pytubefix":
                await pytubefix.cleanup(result.file_path)
            elif api_source == "instaloader":
                await instaloader_dl.cleanup(result.file_path)
            else:
                await downloader.cleanup(result.file_path)
            await status_msg.delete()

        else:
            # Проверяем размер файла (лимит Local Bot API Server - 2GB)
            file_size = result.file_size or (os.path.getsize(result.file_path) if result.file_path else 0)
            MAX_FILE_SIZE = 2_000_000_000  # 2GB (Local Bot API Server)

            if file_size > MAX_FILE_SIZE:
                size_mb = file_size / 1024 / 1024
                await status_msg.edit_text(get_error_message("too_large"))
                logger.warning(f"File too large: {size_mb:.1f}MB > 2GB limit")
                if api_source == "rapidapi":
                    await rapidapi.cleanup(result.file_path)
                else:
                    await downloader.cleanup(result.file_path)
                return

            # === ОТПРАВЛЯЕМ ВИДЕО (до 2GB с Local Bot API Server) ===
            # Статус уже "📤 Отправляю..." после скачивания

            # Извлекаем размеры и длительность для правильного отображения
            # duration в sendVideo - "железный" способ показать длительность (не зависит от moov atom)
            width, height = get_video_dimensions(result.file_path)
            duration = get_video_duration(result.file_path)

            video_msg = await message.answer_video(
                video=media_file,
                caption=CAPTION,
                duration=duration if duration > 0 else None,  # КРИТИЧНО для отображения времени!
                width=width if width > 0 else None,
                height=height if height > 0 else None,
                supports_streaming=True,  # КРИТИЧНО для автопроигрывания!
                request_timeout=TIMEOUT_VIDEO,  # 15 минут для видео
            )
            file_id = video_msg.video.file_id if video_msg.video else None

            # Рассчитываем метрики производительности
            download_time_ms = int((time.time() - download_start) * 1000)
            file_size = result.file_size or (os.path.getsize(result.file_path) if result.file_path else 0)
            download_speed = int(file_size / download_time_ms * 1000 / 1024) if download_time_ms > 0 else 0

            logger.info(f"Sent video: user={user_id}, size={file_size}, time={download_time_ms}ms, speed={download_speed}KB/s")
            await log_action(
                user_id, "download_success",
                {"type": "video", "platform": platform},
                download_time_ms=download_time_ms,
                file_size_bytes=file_size,
                download_speed_kbps=download_speed,
                api_source=api_source
            )

            # Кэшируем и удаляем (без аудио для длинных видео)
            await cache_file_ids(url, file_id, None)
            if api_source == "rapidapi":
                await rapidapi.cleanup(result.file_path)
            elif api_source == "pytubefix":
                await pytubefix.cleanup(result.file_path)
            elif api_source == "instaloader":
                await instaloader_dl.cleanup(result.file_path)
            else:
                await downloader.cleanup(result.file_path)
            await status_msg.delete()

            # Логируем успешное завершение
            total_time = time.time() - download_start
            logger.info(f"[HANDLER_SUCCESS] user={user_id}, total_time={total_time:.1f}s")

    except Exception as e:
        logger.exception(f"Handler error: {e}")
        await error_logger.log_error_by_telegram_id(
            telegram_id=user_id,
            bot_username="SaveNinja_bot",
            platform=platform,
            url=url,
            error_type="exception",
            error_message=str(e)[:200],
            error_details={"exception_type": type(e).__name__}
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
        # Освобождаем слот юзера
        await release_user_slot(user_id)


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
