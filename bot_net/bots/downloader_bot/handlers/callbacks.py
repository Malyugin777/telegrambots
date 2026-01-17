"""
Обработка callback-кнопок
"""
import os
import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, FSInputFile

from ..config import config
from ..services.downloader import VideoDownloader
from ..services.queue import DownloadQueue
from ..keyboards.inline import get_check_sub_keyboard

router = Router(name="callbacks")
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("dl:"))
async def handle_download(callback: CallbackQuery, bot: Bot, download_queue: DownloadQueue):
    """Обработка нажатия на кнопку скачивания"""
    await callback.answer()

    # Парсим данные: dl:video:base64url или dl:audio:base64url
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.message.edit_text("❌ Ошибка данных")
        return

    _, format_type, url_encoded = parts

    # Декодируем URL
    import base64
    try:
        url = base64.urlsafe_b64decode(url_encoded.encode()).decode()
    except Exception:
        await callback.message.edit_text("❌ Ошибка декодирования URL")
        return

    user_id = callback.from_user.id

    # Проверяем очередь
    position = await download_queue.get_position(user_id)
    if position is not None:
        await callback.message.edit_text(
            config.messages["queue_position"].format(position=position)
        )
        return

    # Проверяем лимит активных загрузок
    active_count = await download_queue.get_active_count()
    if active_count >= config.max_concurrent_downloads:
        # Добавляем в очередь
        await download_queue.add_to_queue(user_id, url, format_type)
        position = await download_queue.get_position(user_id)
        await callback.message.edit_text(
            config.messages["queue_position"].format(position=position)
        )
        return

    # Начинаем загрузку
    await callback.message.edit_text(config.messages["downloading"])

    try:
        await download_queue.set_active(user_id)

        downloader = VideoDownloader(config)
        extract_audio = format_type == "audio"

        result = await downloader.download(url, extract_audio=extract_audio)

        if result.error:
            await callback.message.edit_text(
                config.messages["download_error"].format(error=result.error)
            )
            return

        # Проверяем размер файла
        file_size_mb = os.path.getsize(result.file_path) / (1024 * 1024)
        if file_size_mb > config.max_file_size_mb:
            os.remove(result.file_path)
            await callback.message.edit_text(
                config.messages["file_too_large"].format(max_size=config.max_file_size_mb)
            )
            return

        # Отправляем файл
        file = FSInputFile(result.file_path, filename=result.filename)

        if extract_audio:
            await bot.send_audio(
                chat_id=callback.message.chat.id,
                audio=file,
                title=result.title,
                performer=result.author,
                caption=f"🎵 {result.title}"
            )
        else:
            await bot.send_video(
                chat_id=callback.message.chat.id,
                video=file,
                caption=f"🎬 {result.title}\n👤 {result.author}",
                supports_streaming=True
            )

        await callback.message.edit_text(config.messages["download_success"])

        # Удаляем файл
        if os.path.exists(result.file_path):
            os.remove(result.file_path)

        # TODO: Сохранить статистику в БД

    except asyncio.TimeoutError:
        await callback.message.edit_text("❌ Таймаут загрузки")
    except Exception as e:
        logger.exception(f"Download error: {e}")
        await callback.message.edit_text(
            config.messages["download_error"].format(error=str(e)[:100])
        )
    finally:
        await download_queue.remove_active(user_id)


@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: CallbackQuery, bot: Bot):
    """Проверка подписки на каналы"""
    user_id = callback.from_user.id

    all_subscribed = True
    for channel in config.required_channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                all_subscribed = False
                break
        except Exception:
            all_subscribed = False
            break

    if all_subscribed:
        await callback.message.edit_text(config.messages["force_sub_success"])
    else:
        await callback.answer(config.messages["force_sub_failed"], show_alert=True)


@router.callback_query(F.data == "cancel")
async def cancel_download(callback: CallbackQuery):
    """Отмена"""
    await callback.message.edit_text("❌ Отменено")
