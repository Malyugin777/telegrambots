"""
Определение платформы по URL
"""
import re
from enum import Enum
from typing import Optional


class Platform(Enum):
    """Поддерживаемые платформы"""
    TIKTOK = "TikTok"
    INSTAGRAM = "Instagram"
    YOUTUBE = "YouTube"
    PINTEREST = "Pinterest"
    UNKNOWN = "Unknown"


# Паттерны для определения платформы
PLATFORM_PATTERNS = {
    Platform.TIKTOK: [
        r'(?:https?://)?(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+',
        r'(?:https?://)?(?:vm|vt)\.tiktok\.com/[\w]+',
        r'(?:https?://)?(?:www\.)?tiktok\.com/t/[\w]+',
    ],
    Platform.INSTAGRAM: [
        r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|reels)/[\w-]+',
        r'(?:https?://)?(?:www\.)?instagram\.com/[\w.-]+/reel/[\w-]+',
    ],
    Platform.YOUTUBE: [
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
        r'(?:https?://)?youtu\.be/[\w-]+',
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
    ],
    Platform.PINTEREST: [
        r'(?:https?://)?(?:www\.)?pinterest\.[a-z]+/pin/[\d]+',
        r'(?:https?://)?pin\.it/[\w]+',
    ],
}


def detect_platform(url: str) -> Platform:
    """
    Определяет платформу по URL

    Args:
        url: Ссылка на видео

    Returns:
        Platform enum
    """
    url = url.strip()

    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.match(pattern, url, re.IGNORECASE):
                return platform

    return Platform.UNKNOWN


def clean_url(url: str) -> str:
    """
    Очищает URL от лишних параметров

    Args:
        url: Исходный URL

    Returns:
        Очищенный URL
    """
    # Убираем tracking параметры
    url = re.sub(r'\?.*$', '', url)
    return url.strip()


def extract_video_id(url: str, platform: Platform) -> Optional[str]:
    """
    Извлекает ID видео из URL

    Args:
        url: URL видео
        platform: Платформа

    Returns:
        ID видео или None
    """
    patterns = {
        Platform.TIKTOK: r'/video/(\d+)',
        Platform.INSTAGRAM: r'/(?:p|reel|reels)/([\w-]+)',
        Platform.YOUTUBE: r'(?:shorts/|v=|youtu\.be/)([\w-]+)',
        Platform.PINTEREST: r'/pin/(\d+)',
    }

    pattern = patterns.get(platform)
    if not pattern:
        return None

    match = re.search(pattern, url)
    return match.group(1) if match else None


def is_youtube_shorts(url: str) -> bool:
    """
    Проверяет, является ли YouTube URL ссылкой на Shorts

    Args:
        url: YouTube URL

    Returns:
        True если это Shorts, False если обычное видео
    """
    return bool(re.search(r'youtube\.com/shorts/', url, re.IGNORECASE))
