"""
Redis кэширование для видео file_id

Telegram хранит file_id навсегда, поэтому один раз скачанное видео
можно отправлять мгновенно по его file_id.
"""
import hashlib
import logging
from typing import Optional, Tuple

import redis.asyncio as redis

from shared.config import settings

logger = logging.getLogger(__name__)

# Глобальный Redis клиент
_redis: Optional[redis.Redis] = None

# TTL кэша (7 дней - file_id не протухают, но на всякий случай)
CACHE_TTL = 7 * 24 * 60 * 60


async def get_redis() -> redis.Redis:
    """Получить Redis клиент (ленивая инициализация)"""
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
    return _redis


def _url_hash(url: str) -> str:
    """Генерирует хэш URL для использования как ключ"""
    return hashlib.md5(url.encode()).hexdigest()


async def get_cached_file_ids(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Получить закэшированные file_id для URL

    Returns:
        (video_file_id, audio_file_id) - оба или None
    """
    try:
        r = await get_redis()
        url_hash = _url_hash(url)

        video_id = await r.get(f"video:{url_hash}")
        audio_id = await r.get(f"audio:{url_hash}")

        if video_id or audio_id:
            logger.info(f"Cache hit: video={bool(video_id)}, audio={bool(audio_id)}")

        return video_id, audio_id
    except Exception as e:
        logger.warning(f"Redis get error: {e}")
        return None, None


async def cache_file_ids(
    url: str,
    video_file_id: Optional[str] = None,
    audio_file_id: Optional[str] = None
):
    """
    Закэшировать file_id видео и/или аудио

    Args:
        url: Оригинальный URL
        video_file_id: Telegram file_id видео
        audio_file_id: Telegram file_id аудио
    """
    try:
        r = await get_redis()
        url_hash = _url_hash(url)

        if video_file_id:
            await r.set(f"video:{url_hash}", video_file_id, ex=CACHE_TTL)
            logger.debug(f"Cached video: {url_hash[:8]}...")

        if audio_file_id:
            await r.set(f"audio:{url_hash}", audio_file_id, ex=CACHE_TTL)
            logger.debug(f"Cached audio: {url_hash[:8]}...")

    except Exception as e:
        logger.warning(f"Redis set error: {e}")


async def close_redis():
    """Закрыть Redis соединение"""
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
