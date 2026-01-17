"""
Обработка ссылок на скачивание
"""
import logging
from aiogram import Router, F
from aiogram.types import Message

from ..config import config
from ..services.platforms import detect_platform, Platform, is_youtube_shorts
from ..keyboards.inline import get_format_keyboard

router = Router(name="download")
logger = logging.getLogger(__name__)


@router.message(F.text.regexp(r'https?://'))
async def handle_url(message: Message):
    """Обработка ссылок"""
    url = message.text.strip()

    # Определяем платформу
    platform = detect_platform(url)

    if platform == Platform.UNKNOWN:
        await message.answer(config.messages["invalid_url"])
        return

    # Проверяем YouTube - только Shorts поддерживается
    if platform == Platform.YOUTUBE and not is_youtube_shorts(url):
        await message.answer(
            "⚠️ <b>Поддерживаются только YouTube Shorts</b>\n\n"
            "Обычные видео YouTube слишком большие для отправки в Telegram (лимит 50MB).\n\n"
            "Отправь ссылку на Shorts: youtube.com/shorts/..."
        )
        return

    # Показываем выбор формата
    await message.answer(
        f"🔗 <b>{platform.value}</b>\n\n{config.messages['choose_format']}",
        reply_markup=get_format_keyboard(url)
    )


@router.message(F.text)
async def handle_text(message: Message):
    """Обработка текста без ссылки"""
    # Игнорируем команды и кнопки меню
    if message.text.startswith("/") or message.text in ["❓ Помощь", "📊 Статистика"]:
        return

    await message.answer(
        "📎 Отправь мне ссылку на видео.\n\n"
        "Поддерживаются: TikTok, Instagram, YouTube Shorts, Pinterest"
    )
