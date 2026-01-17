"""
Обработчик ссылок - скачивание видео и аудио

Используем:
- RapidAPI для Instagram (требует авторизации в yt-dlp)
- yt-dlp для TikTok, YouTube Shorts, Pinterest (работает хорошо)
"""
import re
import logging
from aiogram import Router, types, F
from aiogram.types import FSInputFile

from ..services.downloader import VideoDownloader
from ..services.rapidapi_downloader import RapidAPIDownloader
from ..services.cache import get_cached_file_ids, cache_file_ids
from ..messages import (
    CAPTION,
    STATUS_DOWNLOADING,
    STATUS_SENDING,
    STATUS_EXTRACTING_AUDIO,
    UNSUPPORTED_URL_MESSAGE,
)

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

    logger.info(f"Download request: user={user_id}, url={url}")

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
    status_msg = await message.answer(STATUS_DOWNLOADING)

    try:
        # === ВЫБИРАЕМ ЗАГРУЗЧИК ===
        # Instagram -> RapidAPI (yt-dlp требует авторизации)
        # Остальные -> yt-dlp (работает хорошо)

        if use_rapidapi(url):
            logger.info(f"Using RapidAPI for: {url}")
            result = await rapidapi.download(url)

            # Конвертируем результат RapidAPI в формат yt-dlp downloader
            if result.success:
                from ..services.downloader import DownloadResult, MediaInfo
                result = DownloadResult(
                    success=True,
                    file_path=result.file_path,
                    filename=result.filename,
                    file_size=result.file_size,
                    is_photo=result.is_photo,
                    info=MediaInfo(
                        title=result.title or "video",
                        author=result.author or "unknown",
                        platform="instagram"
                    )
                )
            else:
                from ..services.downloader import DownloadResult
                result = DownloadResult(success=False, error=result.error)
        else:
            # TikTok, YouTube, Pinterest -> yt-dlp
            result = await downloader.download(url)

        if not result.success:
            logger.warning(f"Download failed: user={user_id}, error={result.error}")
            await status_msg.edit_text(f"❌ {result.error}")
            return

        # Отправляем медиа
        await status_msg.edit_text(STATUS_SENDING)

        media_file = FSInputFile(result.file_path, filename=result.filename)
        file_id = None

        if result.is_photo:
            # === ОТПРАВЛЯЕМ ФОТО ===
            photo_msg = await message.answer_photo(
                photo=media_file,
                caption=CAPTION,
            )
            file_id = photo_msg.photo[-1].file_id if photo_msg.photo else None
            logger.info(f"Sent photo: user={user_id}, size={result.file_size}")

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
            logger.info(f"Sent video: user={user_id}, size={result.file_size}")

            # === ИЗВЛЕКАЕМ АУДИО ИЗ СКАЧАННОГО ВИДЕО ===
            await status_msg.edit_text(STATUS_EXTRACTING_AUDIO)

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

                await downloader.cleanup(audio_result.file_path)
            else:
                logger.warning(f"Audio extraction failed: {audio_result.error}")

            # Кэшируем и удаляем
            await cache_file_ids(url, file_id, audio_file_id)
            await downloader.cleanup(result.file_path)
            await status_msg.delete()

    except Exception as e:
        logger.exception(f"Handler error: {e}")
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
        await message.answer(UNSUPPORTED_URL_MESSAGE)
    else:
        # Просто текст без ссылки
        await message.answer(
            "📎 Отправь мне ссылку на видео.\n\n"
            "Поддерживаю: TikTok, Instagram, YouTube Shorts, Pinterest"
        )
