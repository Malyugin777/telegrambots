"""
Обработчик ссылок - скачивание видео и аудио

Используем:
- RapidAPI для Instagram (требует авторизации в yt-dlp)
- yt-dlp для TikTok, YouTube Shorts, Pinterest (работает хорошо)
"""
import re
import os
import time
import logging
import asyncio
import aiohttp
from aiogram import Router, types, F
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo

from ..services.downloader import VideoDownloader
from ..services.rapidapi_downloader import RapidAPIDownloader
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
)
from bot_manager.middlewares import log_action
from bot_manager.services.error_logger import error_logger

router = Router()
logger = logging.getLogger(__name__)

# Глобальные экземпляры загрузчиков
downloader = VideoDownloader()
rapidapi = RapidAPIDownloader()

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


async def update_progress_message(status_msg, done_event: asyncio.Event, progress_data: dict):
    """
    Обновляет статус-сообщение ТОЛЬКО 3 раза:
    - 0 мин: "⏳ Скачиваю видео..."
    - 5 мин: "⏳ Скачиваю... 45 MB / 200 MB (720p)"
    - 15 мин: "⏳ Почти готово... 180 MB / 200 MB"
    """
    UPDATE_INTERVALS = [0, 300, 900]  # 0, 5 мин, 15 мин (в секундах)

    try:
        start_time = asyncio.get_event_loop().time()
        update_index = 0

        while not done_event.is_set() and update_index < len(UPDATE_INTERVALS):
            # Вычисляем время до следующего обновления
            next_update_at = UPDATE_INTERVALS[update_index]
            current_elapsed = asyncio.get_event_loop().time() - start_time
            sleep_time = next_update_at - current_elapsed

            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

            if done_event.is_set():
                break

            # Формируем сообщение в зависимости от момента времени
            downloaded = progress_data.get('downloaded_bytes', 0)
            total = progress_data.get('total_bytes', 0)

            if update_index == 0:
                # 0 мин - стартовое сообщение уже показано, пропускаем
                pass
            elif update_index == 1:
                # 5 мин
                if total and downloaded:
                    downloaded_mb = int(downloaded / (1024 * 1024))
                    total_mb = int(total / (1024 * 1024))
                    text = f"⏳ Скачиваю... {downloaded_mb} MB / {total_mb} MB (720p)"
                else:
                    text = "⏳ Скачиваю большое видео..."
                await status_msg.edit_text(text)
                logger.info(f"[PROGRESS] 5min update: {downloaded}/{total} bytes")
            elif update_index == 2:
                # 15 мин
                if total and downloaded:
                    downloaded_mb = int(downloaded / (1024 * 1024))
                    total_mb = int(total / (1024 * 1024))
                    text = f"⏳ Почти готово... {downloaded_mb} MB / {total_mb} MB"
                else:
                    text = "⏳ Почти готово..."
                await status_msg.edit_text(text)
                logger.info(f"[PROGRESS] 15min update: {downloaded}/{total} bytes")

            update_index += 1

    except Exception as e:
        logger.warning(f"[PROGRESS] Update error: {e}")


def use_rapidapi_primary(url: str) -> bool:
    """Проверяет, нужно ли использовать RapidAPI как ОСНОВНОЙ способ"""
    url_lower = url.lower()
    # RapidAPI для Instagram (авторизация) и YouTube (адаптивное качество)
    return any(domain in url_lower for domain in [
        'instagram.com', 'instagr.am',
        'youtube.com', 'youtu.be'
    ])

def supports_rapidapi_fallback(url: str) -> bool:
    """Проверяет, поддерживает ли RapidAPI этот URL как FALLBACK"""
    url_lower = url.lower()
    # RapidAPI поддерживает Instagram, YouTube, TikTok, Pinterest
    return any(domain in url_lower for domain in [
        'instagram.com', 'instagr.am',
        'youtube.com', 'youtu.be',
        'tiktok.com',
        'pinterest.', 'pin.it'
    ])


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
    await log_action(user_id, "download_request", f"{platform}:{url[:100]}")

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

    # Прогресс для долгих загрузок
    done_event = asyncio.Event()
    progress_task = asyncio.create_task(update_progress_message(status_msg, done_event, progress_data))

    try:
        # === ЗАМЕРЯЕМ ВРЕМЯ СКАЧИВАНИЯ ===
        download_start = time.time()
        logger.info(f"[HANDLER_START] user={user_id}, platform={platform}, url={url[:100]}")

        # Переменная для отслеживания используемого API
        api_source = None

        # === ВЫБИРАЕМ ЗАГРУЗЧИК ===
        # Instagram -> RapidAPI download_all() (карусели)
        # YouTube -> RapidAPI download() (адаптивное качество)
        # TikTok/Pinterest -> yt-dlp первым, RapidAPI fallback если упал

        is_instagram = any(d in url.lower() for d in ['instagram.com', 'instagr.am'])
        is_youtube = any(d in url.lower() for d in ['youtube.com', 'youtu.be'])

        if use_rapidapi_primary(url):
            logger.info(f"Using RapidAPI (primary) for: {url}")
            api_source = "rapidapi"

            # YouTube - адаптивное качество
            if is_youtube:
                from ..services.downloader import DownloadResult, MediaInfo
                file_result = await rapidapi.download(url, adaptive_quality=True)

                if not file_result.success:
                    logger.warning(f"Download failed: user={user_id}, error={file_result.error}")
                    await error_logger.log_error_by_telegram_id(
                        telegram_id=user_id,
                        bot_username="SaveNinja_bot",
                        platform=platform,
                        url=url,
                        error_type="download_failed",
                        error_message=file_result.error,
                        error_details={"source": "rapidapi"}
                    )
                    await status_msg.edit_text(f"❌ {file_result.error}")
                    return

                # Проверяем размер файла для выбора способа отправки
                file_size = file_result.file_size or 0
                send_as_document = False

                if file_size > 2_000_000_000:  # > 2GB
                    await status_msg.edit_text("❌ Видео слишком большое (>2GB), не могу отправить в Telegram")
                    await rapidapi.cleanup(file_result.file_path)
                    return
                elif file_size >= 50_000_000:  # >= 50MB
                    send_as_document = True

                # Создаём DownloadResult
                result = DownloadResult(
                    success=True,
                    file_path=file_result.file_path,
                    filename=file_result.filename,
                    file_size=file_result.file_size,
                    is_photo=file_result.is_photo,
                    send_as_document=send_as_document,
                    info=MediaInfo(
                        title=file_result.title or "video",
                        author=file_result.author or "unknown",
                        platform=platform
                    )
                )
            else:
                # Instagram - скачиваем ВСЕ медиа (для каруселей)
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
                    await status_msg.edit_text(f"❌ {carousel.error}")
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
                            media_group.append(InputMediaVideo(
                                media=input_file,
                                caption=caption,
                                supports_streaming=True
                            ))

                    # Отправляем альбом
                    await message.answer_media_group(media=media_group)

                    # Рассчитываем метрики производительности
                    download_time_ms = int((time.time() - download_start) * 1000)
                    total_size = sum(f.file_size or 0 for f in carousel.files)
                    download_speed = int(total_size / download_time_ms * 1000 / 1024) if download_time_ms > 0 else 0

                    logger.info(f"Sent carousel: user={user_id}, files={len(carousel.files)}, time={download_time_ms}ms, size={total_size}")
                    await log_action(
                        user_id, "download_success", f"carousel:{platform}:{len(carousel.files)}",
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
                                )
                                await log_action(user_id, "audio_extracted", f"{platform}")
                                await downloader.cleanup(audio_result.file_path)

                    # Очистка
                    for file in carousel.files:
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
        else:
            # TikTok, YouTube, Pinterest -> yt-dlp (первая попытка)
            result = await downloader.download(url, progress_callback=progress_callback)
            api_source = "ytdlp"

        if not result.success:
            logger.warning(f"yt-dlp failed: user={user_id}, error={result.error}")

            # === FALLBACK: Пробуем RapidAPI если yt-dlp упал ===
            if supports_rapidapi_fallback(url):
                logger.info(f"Trying RapidAPI fallback for: {url}")
                await status_msg.edit_text("⏳ Пробую альтернативный способ...")

                # Для YouTube/TikTok/Pinterest используем download() - скачивает ОДНО лучшее качество
                # (download_all() скачивает ВСЕ качества - 19 файлов для YouTube!)
                from ..services.downloader import DownloadResult, MediaInfo
                file_result = await rapidapi.download(url)

                if file_result.success:
                    logger.info(f"RapidAPI fallback succeeded: {file_result.filename}")
                    api_source = "rapidapi"
                    result = DownloadResult(
                        success=True,
                        file_path=file_result.file_path,
                        filename=file_result.filename,
                        file_size=file_result.file_size,
                        is_photo=file_result.is_photo,
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
                    await status_msg.edit_text(f"❌ {result.error}")
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
                await status_msg.edit_text(f"❌ {result.error}")
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
            )
            file_id = photo_msg.photo[-1].file_id if photo_msg.photo else None

            # Рассчитываем метрики производительности
            download_time_ms = int((time.time() - download_start) * 1000)
            file_size = result.file_size or (os.path.getsize(result.file_path) if result.file_path else 0)
            download_speed = int(file_size / download_time_ms * 1000 / 1024) if download_time_ms > 0 else 0

            logger.info(f"Sent photo: user={user_id}, size={file_size}, time={download_time_ms}ms")
            await log_action(
                user_id, "download_success", f"photo:{platform}",
                download_time_ms=download_time_ms,
                file_size_bytes=file_size,
                download_speed_kbps=download_speed,
                api_source=api_source
            )

            # Кэшируем и удаляем
            await cache_file_ids(url, file_id, None)
            if api_source == "rapidapi":
                await rapidapi.cleanup(result.file_path)
            else:
                await downloader.cleanup(result.file_path)
            await status_msg.delete()

        else:
            # === ОТПРАВЛЯЕМ ВИДЕО или ДОКУМЕНТ (для больших YouTube) ===
            if result.send_as_document:
                # Большой YouTube файл (50MB-2GB) - отправляем как документ
                await status_msg.edit_text(get_message("downloading_large"))
                doc_msg = await message.answer_document(
                    document=media_file,
                    caption=CAPTION + "\n\n📁 " + get_message("sent_as_document"),
                )
                file_id = doc_msg.document.file_id if doc_msg.document else None
            else:
                # Обычное видео - отправляем с превью
                video_msg = await message.answer_video(
                    video=media_file,
                    caption=CAPTION,
                    supports_streaming=True,  # КРИТИЧНО для автопроигрывания!
                )
                file_id = video_msg.video.file_id if video_msg.video else None

            # Рассчитываем метрики производительности
            download_time_ms = int((time.time() - download_start) * 1000)
            file_size = result.file_size or (os.path.getsize(result.file_path) if result.file_path else 0)
            download_speed = int(file_size / download_time_ms * 1000 / 1024) if download_time_ms > 0 else 0

            logger.info(f"Sent {'document' if result.send_as_document else 'video'}: user={user_id}, size={file_size}, time={download_time_ms}ms, speed={download_speed}KB/s")
            await log_action(
                user_id, "download_success", f"video:{platform}",
                download_time_ms=download_time_ms,
                file_size_bytes=file_size,
                download_speed_kbps=download_speed,
                api_source=api_source
            )

            # === ИЗВЛЕКАЕМ АУДИО ИЗ СКАЧАННОГО ВИДЕО ===
            await status_msg.edit_text(get_extracting_audio_message())

            audio_result = await downloader.extract_audio(result.file_path)
            audio_file_id = None

            if audio_result.success:
                audio_file = FSInputFile(audio_result.file_path, filename=audio_result.filename)

                # Получаем title и author для аудио
                title = result.info.title[:60] if result.info.title else "audio"
                performer = result.info.author if result.info.author != "unknown" else None

                audio_msg = await message.answer_audio(
                    audio=audio_file,
                    caption=CAPTION,
                    title=title,
                    performer=performer,
                )

                audio_file_id = audio_msg.audio.file_id if audio_msg.audio else None
                logger.info(f"Sent audio: user={user_id}, size={audio_result.file_size}")
                await log_action(user_id, "audio_extracted", f"{platform}")

                await downloader.cleanup(audio_result.file_path)
            else:
                logger.warning(f"Audio extraction failed: {audio_result.error}")

            # Кэшируем и удаляем
            await cache_file_ids(url, file_id, audio_file_id)
            if api_source == "rapidapi":
                await rapidapi.cleanup(result.file_path)
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
        try:
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:50]}")
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
