"""
Парсинг и валидация URL
"""
import re
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

from ..services.platforms import Platform, detect_platform


# Regex паттерны для извлечения URL из текста
URL_PATTERN = re.compile(
    r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*',
    re.IGNORECASE
)


def extract_urls(text: str) -> list[str]:
    """
    Извлекает все URL из текста

    Args:
        text: Текст сообщения

    Returns:
        Список найденных URL
    """
    return URL_PATTERN.findall(text)


def is_valid_url(url: str) -> bool:
    """
    Проверяет, является ли строка валидным URL

    Args:
        url: URL для проверки

    Returns:
        True если валидный URL
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def parse_url(url: str) -> Tuple[Optional[str], Platform]:
    """
    Парсит URL и определяет платформу

    Args:
        url: URL для парсинга

    Returns:
        Tuple[очищенный URL, платформа]
    """
    if not is_valid_url(url):
        return None, Platform.UNKNOWN

    # Очищаем URL
    url = clean_tracking_params(url)

    # Определяем платформу
    platform = detect_platform(url)

    return url, platform


def clean_tracking_params(url: str) -> str:
    """
    Удаляет tracking параметры из URL

    Args:
        url: Исходный URL

    Returns:
        Очищенный URL
    """
    parsed = urlparse(url)

    # Параметры для удаления
    tracking_params = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'fbclid', 'gclid', 'ref', 'ref_src', 'ref_url',
        'igshid', 'ig_rid',  # Instagram
        '_r', 'share_item_id',  # TikTok
        'si', 'feature',  # YouTube
    }

    if parsed.query:
        params = parse_qs(parsed.query)
        # Убираем tracking параметры
        cleaned_params = {
            k: v for k, v in params.items()
            if k.lower() not in tracking_params
        }

        if cleaned_params:
            from urllib.parse import urlencode
            query = urlencode(cleaned_params, doseq=True)
            url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query}"
        else:
            url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    return url


def normalize_tiktok_url(url: str) -> str:
    """
    Нормализует TikTok URL (короткие ссылки)

    Args:
        url: TikTok URL

    Returns:
        Нормализованный URL
    """
    # vm.tiktok.com и vt.tiktok.com - короткие ссылки
    # Они редиректят на полный URL, yt-dlp сам разберётся
    return url


def normalize_instagram_url(url: str) -> str:
    """
    Нормализует Instagram URL

    Args:
        url: Instagram URL

    Returns:
        Нормализованный URL
    """
    # Убираем параметры
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def get_thumbnail_url(url: str, platform: Platform) -> Optional[str]:
    """
    Пытается получить URL превью

    Args:
        url: URL видео
        platform: Платформа

    Returns:
        URL превью или None
    """
    # Для большинства платформ yt-dlp сам получит thumbnail
    return None
