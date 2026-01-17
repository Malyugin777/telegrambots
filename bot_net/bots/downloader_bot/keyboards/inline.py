"""
Inline клавиатуры
"""
import base64
from typing import List

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )


def get_format_keyboard(url: str) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора формата (видео/аудио)

    Args:
        url: URL для скачивания
    """
    # Кодируем URL в base64 для callback_data (ограничение 64 байта)
    url_encoded = base64.urlsafe_b64encode(url.encode()).decode()

    # Если слишком длинный, обрезаем (будет ошибка, но это edge case)
    if len(url_encoded) > 50:
        url_encoded = url_encoded[:50]

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎬 Видео",
                callback_data=f"dl:video:{url_encoded}"
            ),
            InlineKeyboardButton(
                text="🎵 Аудио (MP3)",
                callback_data=f"dl:audio:{url_encoded}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel"
            )
        ]
    ])


def get_check_sub_keyboard(channels: List[str]) -> InlineKeyboardMarkup:
    """
    Клавиатура для проверки подписки

    Args:
        channels: Список каналов для подписки
    """
    buttons = []

    # Кнопки для каждого канала
    for i, channel in enumerate(channels):
        # Убираем @ если есть
        channel_name = channel.lstrip("@")
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 Канал {i + 1}",
                url=f"https://t.me/{channel_name}"
            )
        ])

    # Кнопка проверки
    buttons.append([
        InlineKeyboardButton(
            text="✅ Я подписался",
            callback_data="check_subscription"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_downloading_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура во время загрузки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_download"
            )
        ]
    ])


def get_error_keyboard(url: str) -> InlineKeyboardMarkup:
    """Клавиатура при ошибке (попробовать снова)"""
    url_encoded = base64.urlsafe_b64encode(url.encode()).decode()[:50]

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 Попробовать снова",
                callback_data=f"dl:video:{url_encoded}"
            )
        ]
    ])
