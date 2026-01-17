"""
Обработка callback-кнопок
"""
import base64
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, FSInputFile

from ..config import config
from ..services.downloader import VideoDownloader
from ..services.queue import DownloadQueue
from ..keyboards.inline import get_check_sub_keyboard
from ..middlewares.user_tracking import log_action

router = Router(name="callbacks")
logger = logging.getLogger(__name__)

# Глобальный экземпляр загрузчика
downloader = VideoDownloader()


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
    try:
        url = base64.urlsafe_b64decode(url_encoded.encode()).decode()
    except Exception:
        await callback.message.edit_text("❌ Ошибка декодирования URL")
        return

    user_id = callback.from_user.id

    # Проверяем, не загружает ли уже этот пользователь
    if await download_queue.is_active(user_id):
        await callback.answer("⏳ Дождитесь завершения предыдущей загрузки", show_alert=True)
        return

    # Проверяем лимит активных загрузок
    active_count = await download_queue.get_active_count()
    if active_count >= config.max_concurrent_downloads:
        # Добавляем в очередь
        await download_queue.add_to_queue(user_id, url, format_type)
        position = await download_queue.get_position(user_id)
        await callback.message.edit_text(
            f"⏳ <b>В очереди</b>\n\n"
            f"Позиция: {position}\n"
            f"Активных загрузок: {active_count}/{config.max_concurrent_downloads}"
        )
        return

    # Начинаем загрузку
    await callback.message.edit_text(
        "⏳ <b>Скачиваю...</b>\n\n"
        "Это может занять до минуты."
    )

    try:
        # Отмечаем как активную загрузку
        await download_queue.set_active(user_id)

        # Скачиваем
        if format_type == "audio":
            result = await downloader.download_audio(url)
        else:
            result = await downloader.download(url)

        # Проверяем результат
        if not result.success:
            await callback.message.edit_text(
                f"❌ <b>Ошибка</b>\n\n{result.error}"
            )
            return

        # Отправляем файл
        file = FSInputFile(result.file_path, filename=result.filename)

        # Подпись бота (простая и кликабельная)
        bot_signature = "❤️ @SaveNinja_bot"

        if format_type == "audio":
            # Для аудио — минимальная подпись
            await bot.send_audio(
                chat_id=callback.message.chat.id,
                audio=file,
                title=result.info.title[:60] if result.info.title else "audio",
                performer=result.info.author[:30] if result.info.author and result.info.author != "unknown" else None,
                caption=bot_signature
            )
        else:
            # Для видео — только подпись бота
            await bot.send_video(
                chat_id=callback.message.chat.id,
                video=file,
                caption=bot_signature,
                supports_streaming=True
            )

        # Удаляем сообщение "Скачиваю..."
        await callback.message.delete()

        # Обновляем статистику
        await download_queue.increment_downloads(user_id, result.info.platform)

        # Логируем в БД
        user_db_id = data.get('user_db_id')
        await log_action(
            user_id=user_db_id,
            action=f"download_{format_type}",
            details={
                "platform": result.info.platform,
                "title": result.info.title[:100] if result.info.title else None,
                "file_size": result.file_size
            }
        )

        # Удаляем файл
        await downloader.cleanup(result.file_path)

        logger.info(f"Download success: user={user_id}, platform={result.info.platform}, format={format_type}")

    except Exception as e:
        logger.exception(f"Download error: {e}")
        await callback.message.edit_text(
            f"❌ <b>Ошибка</b>\n\n{str(e)[:100]}"
        )
    finally:
        # Убираем из активных
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
        await callback.message.edit_text(
            "✅ <b>Спасибо за подписку!</b>\n\n"
            "Теперь отправь мне ссылку на видео."
        )
    else:
        await callback.answer(
            "❌ Ты не подписан на все каналы. Проверь и попробуй снова.",
            show_alert=True
        )


@router.callback_query(F.data == "cancel")
async def cancel_download(callback: CallbackQuery):
    """Отмена"""
    await callback.message.edit_text("❌ Отменено")
