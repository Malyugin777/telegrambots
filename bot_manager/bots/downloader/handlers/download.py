"""
Обработчик ссылок - скачивание видео и аудио
"""
import re
import logging
from aiogram import Router, types, F
from aiogram.types import FSInputFile

from ..services.downloader import VideoDownloader
from ..messages import (
    CAPTION,
    STATUS_DOWNLOADING,
    STATUS_SENDING,
    STATUS_EXTRACTING_AUDIO,
    UNSUPPORTED_URL_MESSAGE,
)

router = Router()
logger = logging.getLogger(__name__)

# Глобальный экземпляр загрузчика
downloader = VideoDownloader()

# Паттерн для поддерживаемых URL
URL_PATTERN = re.compile(
    r"https?://(?:www\.|m\.|[a-z]{2}\.)?"
    r"(?:"
    r"tiktok\.com|vm\.tiktok\.com|"
    r"instagram\.com|"
    r"youtube\.com/shorts|youtu\.be|"
    r"pinterest\.[a-z.]+|pin\.it"
    r")"
    r"[^\s]*",
    re.IGNORECASE
)


@router.message(F.text.regexp(URL_PATTERN))
async def handle_url(message: types.Message):
    """Обработка ссылок - скачивание видео + аудио"""
    match = URL_PATTERN.search(message.text)
    if not match:
        return

    url = match.group()
    user_id = message.from_user.id

    logger.info(f"Download request: user={user_id}, url={url}")

    # Статус сообщение
    status_msg = await message.answer(STATUS_DOWNLOADING)

    try:
        # === СКАЧИВАЕМ ВИДЕО ===
        video_result = await downloader.download(url)

        if not video_result.success:
            logger.warning(f"Video download failed: user={user_id}, error={video_result.error}")
            await status_msg.edit_text(f"❌ {video_result.error}")
            return

        # Отправляем видео
        await status_msg.edit_text(STATUS_SENDING)

        video_file = FSInputFile(video_result.file_path, filename=video_result.filename)
        await message.answer_video(
            video=video_file,
            caption=CAPTION,
            supports_streaming=True,  # КРИТИЧНО для автопроигрывания!
        )

        logger.info(f"Sent video: user={user_id}, size={video_result.file_size}")

        # Удаляем видео файл
        await downloader.cleanup(video_result.file_path)

        # === СКАЧИВАЕМ АУДИО ===
        await status_msg.edit_text(STATUS_EXTRACTING_AUDIO)

        audio_result = await downloader.download_audio(url)

        if audio_result.success:
            audio_file = FSInputFile(audio_result.file_path, filename=audio_result.filename)

            # Получаем title и author для аудио
            title = video_result.info.title[:60] if video_result.info.title else "audio"
            performer = video_result.info.author if video_result.info.author != "unknown" else None

            await message.answer_audio(
                audio=audio_file,
                caption=CAPTION,
                title=title,
                performer=performer,
            )

            logger.info(f"Sent audio: user={user_id}, size={audio_result.file_size}")

            # Удаляем аудио файл
            await downloader.cleanup(audio_result.file_path)
        else:
            logger.warning(f"Audio extraction failed: {audio_result.error}")
            # Не показываем ошибку пользователю - видео уже отправлено

        # Удаляем статус сообщение
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
