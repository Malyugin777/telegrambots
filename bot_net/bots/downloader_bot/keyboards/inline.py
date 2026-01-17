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

from ..utils.url_parser import clean_url


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )


def encode_url_for_callback(url: str) -> str:
    """
    Кодирует URL для callback_data с учётом лимита 64 байта.

    Args:
        url: URL для кодирования

    Returns:
        Base64 закодированный URL
    """
    # Сначала очищаем URL от всех параметров
    clean = clean_url(url, remove_all_params=True)

    # Кодируем
    encoded = base64.urlsafe_b64encode(clean.encode()).decode()

    # Telegram callback_data limit: 64 bytes
    # Формат: "dl:video:" = 9 символов, остаётся 55
    max_len = 54

    if len(encoded) <= max_len:
        return encoded

    # URL всё ещё слишком длинный — пробуем сократить
    # Убираем www. если есть
    if 'www.' in clean:
        clean = clean.replace('www.', '')
        encoded = base64.urlsafe_b64encode(clean.encode()).decode()

    if len(encoded) <= max_len:
        return encoded

    # Если и это не помогло — возвращаем что есть, надеясь на лучшее
    # В будущем можно использовать Redis для хранения длинных URL
    return encoded


def get_format_keyboard(url: str) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора формата (видео/аудио)

    Args:
        url: URL для скачивания
    """
    url_encoded = encode_url_for_callback(url)

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
    url_encoded = encode_url_for_callback(url)

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 Попробовать снова",
                callback_data=f"dl:video:{url_encoded}"
            )
        ]
    ])
