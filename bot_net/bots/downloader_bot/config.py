"""
Конфигурация Downloader Bot
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DownloaderConfig:
    """Настройки бота-загрузчика"""

    # Токен бота
    token: str = field(default_factory=lambda: os.getenv("DOWNLOADER_BOT_TOKEN", ""))

    # Каналы для обязательной подписки (Force Subscribe)
    required_channels: List[str] = field(default_factory=lambda: [
        ch.strip() for ch in os.getenv("FORCE_SUB_CHANNELS", "").split(",") if ch.strip()
    ])

    # Лимиты
    max_concurrent_downloads: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "5"))
    max_file_size_mb: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    max_video_duration: int = int(os.getenv("MAX_VIDEO_DURATION", "600"))  # 10 минут

    # Пути
    download_path: str = os.getenv("DOWNLOAD_PATH", "/tmp/downloads")

    # Instagram cookies (для обхода блокировок)
    instagram_cookies_file: Optional[str] = field(default_factory=lambda: os.getenv("INSTAGRAM_COOKIES_FILE"))

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    queue_key: str = "downloader:queue"
    active_downloads_key: str = "downloader:active"

    # Throttling
    rate_limit_messages: int = 3  # сообщений
    rate_limit_seconds: int = 10  # за N секунд

    # Сообщения
    messages: dict = field(default_factory=lambda: {
        "start": (
            "👋 <b>Привет!</b>\n\n"
            "Я умею скачивать видео из:\n"
            "• TikTok\n"
            "• Instagram Reels\n"
            "• YouTube Shorts\n"
            "• Pinterest\n\n"
            "📎 Просто отправь мне ссылку!"
        ),
        "force_sub": (
            "⚠️ <b>Для использования бота подпишись на каналы:</b>\n\n"
            "{channels}\n\n"
            "После подписки нажми кнопку ниже 👇"
        ),
        "force_sub_success": "✅ Спасибо за подписку! Теперь отправь ссылку.",
        "force_sub_failed": "❌ Ты не подписан на все каналы. Проверь и попробуй снова.",
        "invalid_url": "❌ Не могу распознать ссылку. Поддерживаются: TikTok, Instagram, YouTube, Pinterest",
        "downloading": "⏳ Скачиваю... Это может занять до минуты.",
        "queue_position": "⏳ В очереди: позиция {position}",
        "download_success": "✅ Готово!",
        "download_error": "❌ Ошибка при скачивании: {error}",
        "file_too_large": "❌ Файл слишком большой (>{max_size}MB)",
        "video_too_long": "❌ Видео слишком длинное (>{max_duration} сек)",
        "rate_limit": "⏳ Подожди немного перед следующим запросом.",
        "choose_format": "🎬 Выбери формат:",
        "instagram_unavailable": (
            "⚠️ <b>Instagram временно недоступен</b>\n\n"
            "Попробуй TikTok или YouTube Shorts."
        ),
    })

    def __post_init__(self):
        """Создать папку для загрузок"""
        os.makedirs(self.download_path, exist_ok=True)


# Глобальный конфиг
config = DownloaderConfig()
