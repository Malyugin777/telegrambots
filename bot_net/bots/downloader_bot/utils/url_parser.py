"""
Парсинг и валидация URL
"""
import re
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlencode

from ..services.platforms import Platform, detect_platform


# Regex паттерны для извлечения URL из текста
URL_PATTERN = re.compile(
    r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*',
    re.IGNORECASE
)

# Параметры для удаления из всех URL
TRACKING_PARAMS = {
    # UTM
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    # Facebook/Meta
    'fbclid', 'fb_action_ids', 'fb_action_types', 'fb_source', 'fb_ref',
    # Google
    'gclid', 'gclsrc', 'dclid',
    # Instagram
    'igsh', 'igshid', 'ig_rid', 'ig_mid',
    # TikTok
    '_r', 'share_item_id', 'is_from_webapp', 'sender_device', 'is_copy_url',
    # YouTube
    'si', 'feature', 'pp',
    # Twitter/X
    't', 's', 'ref_src', 'ref_url',
    # General
    'ref', 'source', 'share_source', 'share_medium',
}


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


def clean_url(url: str, remove_all_params: bool = False) -> str:
    """
    Очищает URL от tracking параметров и нормализует его.

    Это основная функция для очистки URL перед скачиванием.

    Args:
        url: Исходный URL
        remove_all_params: Если True, удаляет ВСЕ query параметры

    Returns:
        Очищенный URL
    """
    try:
        parsed = urlparse(url)

        # Для Instagram, TikTok, Pinterest — удаляем ВСЕ параметры
        # Они не нужны для скачивания, ID контента в пути
        host = parsed.netloc.lower()
        platforms_no_params = [
            'instagram.com', 'www.instagram.com',
            'tiktok.com', 'www.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com',
            'pinterest.com', 'www.pinterest.com', 'pin.it',
        ]

        if remove_all_params or any(p in host for p in platforms_no_params):
            # Убираем все query параметры
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # Для остальных — убираем только tracking параметры
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            # Убираем tracking параметры (case-insensitive)
            cleaned_params = {
                k: v for k, v in params.items()
                if k.lower() not in TRACKING_PARAMS
            }

            if cleaned_params:
                query = urlencode(cleaned_params, doseq=True)
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query}"

        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    except Exception:
        # При любой ошибке возвращаем оригинал
        return url


def clean_tracking_params(url: str) -> str:
    """
    Удаляет tracking параметры из URL (legacy функция)

    Args:
        url: Исходный URL

    Returns:
        Очищенный URL
    """
    return clean_url(url)


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
