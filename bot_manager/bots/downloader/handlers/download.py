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
import aiohttp
from aiogram import Router, types, F
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo

from ..services.downloader import VideoDownloader
from ..services.rapidapi_downloader import RapidAPIDownloader
from ..services.cache import get_cached_file_ids, cache_file_ids
from ..messages import (
    CAPTION,
    get_downloading_message,
    get_sending_message,
    get_extracting_audio_message,
    get_unsupported_url_message,
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
    r"youtube\.com/shorts|youtu\.be|"        # YouTube Shorts
    r"pinterest\.[a-z.]+|pin\.it"            # Pinterest
    r")"
    r"[^\s]*",
    re.IGNORECASE
)


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


def use_rapidapi(url: str) -> bool:
    """Проверяет, нужно ли использовать RapidAPI для этого URL"""
    url_lower = url.lower()
    # RapidAPI только для Instagram (yt-dlp требует авторизации)
    return any(domain in url_lower for domain in [
        'instagram.com', 'instagr.am'
    ])


@router.message(F.text.regexp(URL_PATTERN))
async def handle_url(message: types.Message):
    """Обработка ссылок - скачивание видео/фото + аудио"""
    match = URL_PATTERN.search(message.text)
    if not match:
        return

    url = match.group()
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

    # Статус сообщение
    status_msg = await message.answer(get_downloading_message())

    try:
        # === ЗАМЕРЯЕМ ВРЕМЯ СКАЧИВАНИЯ ===
        download_start = time.time()

        # === ВЫБИРАЕМ ЗАГРУЗЧИК ===
        # Instagram -> RapidAPI (yt-dlp требует авторизации)
        # Остальные -> yt-dlp (работает хорошо)

        if use_rapidapi(url):
            logger.info(f"Using RapidAPI for: {url}")

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
                await status_msg.edit_text(f"❌ {carousel.error}")
                return

            # === КАРУСЕЛЬ (несколько файлов) ===
            if len(carousel.files) > 1:
                await status_msg.edit_text(get_sending_message())

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
                    download_speed_kbps=download_speed
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
            # TikTok, YouTube, Pinterest -> yt-dlp
            result = await downloader.download(url)

        if not result.success:
            logger.warning(f"Download failed: user={user_id}, error={result.error}")
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
        await status_msg.edit_text(get_sending_message())

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
                download_speed_kbps=download_speed
            )

            # Кэшируем и удаляем
            await cache_file_ids(url, file_id, None)
            await downloader.cleanup(result.file_path)
            await status_msg.delete()

        else:
            # === ОТПРАВЛЯЕМ ВИДЕО ===
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

            logger.info(f"Sent video: user={user_id}, size={file_size}, time={download_time_ms}ms, speed={download_speed}KB/s")
            await log_action(
                user_id, "download_success", f"video:{platform}",
                download_time_ms=download_time_ms,
                file_size_bytes=file_size,
                download_speed_kbps=download_speed
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
            await downloader.cleanup(result.file_path)
            await status_msg.delete()

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
