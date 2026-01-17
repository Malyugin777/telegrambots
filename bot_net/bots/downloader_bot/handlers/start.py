"""
Команда /start
"""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart

from ..config import config
from ..keyboards.inline import get_main_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработка команды /start"""
    await message.answer(
        config.messages["start"],
        reply_markup=get_main_keyboard()
    )


@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    """Помощь"""
    help_text = (
        "📖 <b>Как пользоваться:</b>\n\n"
        "1️⃣ Скопируй ссылку на видео\n"
        "2️⃣ Отправь её мне\n"
        "3️⃣ Выбери формат (видео или аудио)\n"
        "4️⃣ Получи файл!\n\n"
        "<b>Поддерживаемые платформы:</b>\n"
        "• TikTok (tiktok.com, vm.tiktok.com)\n"
        "• Instagram Reels (instagram.com/reel/)\n"
        "• YouTube Shorts (youtube.com/shorts/)\n"
        "• Pinterest (pinterest.com/pin/)\n\n"
        f"📦 Максимальный размер: {config.max_file_size_mb}MB\n"
        f"⏱ Максимальная длительность: {config.max_video_duration // 60} мин"
    )
    await message.answer(help_text)


@router.message(F.text == "📊 Статистика")
async def cmd_stats(message: Message):
    """Статистика пользователя"""
    # TODO: Получить из БД
    stats_text = (
        "📊 <b>Твоя статистика:</b>\n\n"
        "📥 Скачано видео: 0\n"
        "🎵 Извлечено аудио: 0\n"
        "📅 С нами с: сегодня"
    )
    await message.answer(stats_text)
