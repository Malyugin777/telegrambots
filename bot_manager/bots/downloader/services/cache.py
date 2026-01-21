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


# === RATE LIMITING ===

MAX_USER_DOWNLOADS = 2  # Макс одновременных скачиваний на юзера
MAX_GLOBAL_FFMPEG = 5   # Макс одновременных ffmpeg процессов


async def check_user_limit(user_id: int) -> bool:
    """
    Проверяет, может ли юзер начать скачивание

    Returns:
        True если можно начать, False если лимит превышен
    """
    try:
        r = await get_redis()
        user_downloads = await r.get(f"downloads:user:{user_id}")
        count = int(user_downloads) if user_downloads else 0
        return count < MAX_USER_DOWNLOADS
    except Exception as e:
        logger.warning(f"Rate limit check error: {e}")
        return True  # При ошибке разрешаем


async def acquire_user_slot(user_id: int) -> bool:
    """
    Занять слот скачивания для юзера

    Returns:
        True если слот получен, False если лимит превышен
    """
    try:
        r = await get_redis()
        key = f"downloads:user:{user_id}"

        # Increment и проверяем
        count = await r.incr(key)
        await r.expire(key, 300)  # TTL 5 минут на случай сбоя

        if count > MAX_USER_DOWNLOADS:
            await r.decr(key)
            return False

        return True
    except Exception as e:
        logger.warning(f"Acquire user slot error: {e}")
        return True


async def release_user_slot(user_id: int):
    """Освободить слот скачивания юзера"""
    try:
        r = await get_redis()
        await r.decr(f"downloads:user:{user_id}")
    except Exception as e:
        logger.warning(f"Release user slot error: {e}")


async def check_ffmpeg_limit() -> bool:
    """
    Проверяет глобальный лимит ffmpeg процессов

    Returns:
        True если можно запустить ffmpeg, False если лимит превышен
    """
    try:
        r = await get_redis()
        ffmpeg_count = await r.get("ffmpeg:active")
        count = int(ffmpeg_count) if ffmpeg_count else 0
        return count < MAX_GLOBAL_FFMPEG
    except Exception as e:
        logger.warning(f"FFmpeg limit check error: {e}")
        return True


async def acquire_ffmpeg_slot() -> bool:
    """
    Занять слот ffmpeg процесса

    Returns:
        True если слот получен, False если лимит превышен
    """
    try:
        r = await get_redis()
        key = "ffmpeg:active"

        count = await r.incr(key)
        await r.expire(key, 600)  # TTL 10 минут

        if count > MAX_GLOBAL_FFMPEG:
            await r.decr(key)
            return False

        return True
    except Exception as e:
        logger.warning(f"Acquire ffmpeg slot error: {e}")
        return True


async def release_ffmpeg_slot():
    """Освободить слот ffmpeg процесса"""
    try:
        r = await get_redis()
        await r.decr("ffmpeg:active")
    except Exception as e:
        logger.warning(f"Release ffmpeg slot error: {e}")


# === ACTIVE OPERATIONS COUNTERS (for Ops Dashboard) ===

async def increment_active_downloads():
    """Увеличить счётчик активных скачиваний"""
    try:
        r = await get_redis()
        await r.incr("counter:active_downloads")
        await r.expire("counter:active_downloads", 300)  # TTL 5 минут
    except Exception as e:
        logger.warning(f"Increment active downloads error: {e}")


async def decrement_active_downloads():
    """Уменьшить счётчик активных скачиваний"""
    try:
        r = await get_redis()
        count = await r.decr("counter:active_downloads")
        # Не даём уйти в минус
        if count < 0:
            await r.set("counter:active_downloads", "0", ex=300)
    except Exception as e:
        logger.warning(f"Decrement active downloads error: {e}")


async def increment_active_uploads():
    """Увеличить счётчик активных загрузок в Telegram"""
    try:
        r = await get_redis()
        await r.incr("counter:active_uploads")
        await r.expire("counter:active_uploads", 300)
    except Exception as e:
        logger.warning(f"Increment active uploads error: {e}")


async def decrement_active_uploads():
    """Уменьшить счётчик активных загрузок"""
    try:
        r = await get_redis()
        count = await r.decr("counter:active_uploads")
        if count < 0:
            await r.set("counter:active_uploads", "0", ex=300)
    except Exception as e:
        logger.warning(f"Decrement active uploads error: {e}")
