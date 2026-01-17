"""
Redis очередь для загрузок
"""
import json
import logging
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class DownloadQueue:
    """Очередь загрузок на Redis"""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None

        # Ключи Redis
        self.queue_key = "downloader:queue"
        self.active_key = "downloader:active"
        self.stats_key = "downloader:stats"

    async def connect(self):
        """Подключение к Redis"""
        self.redis = redis.from_url(self.redis_url, decode_responses=True)
        logger.info("DownloadQueue подключена к Redis")

    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis:
            await self.redis.close()

    async def add_to_queue(self, user_id: int, url: str, format_type: str) -> int:
        """
        Добавляет задачу в очередь

        Args:
            user_id: ID пользователя
            url: URL для скачивания
            format_type: video или audio

        Returns:
            Позиция в очереди
        """
        task = json.dumps({
            "user_id": user_id,
            "url": url,
            "format": format_type
        })

        await self.redis.rpush(self.queue_key, task)
        position = await self.redis.llen(self.queue_key)

        logger.info(f"Task added to queue: user={user_id}, position={position}")
        return position

    async def get_from_queue(self) -> Optional[dict]:
        """
        Получает задачу из очереди

        Returns:
            Задача или None
        """
        task = await self.redis.lpop(self.queue_key)
        if task:
            return json.loads(task)
        return None

    async def get_position(self, user_id: int) -> Optional[int]:
        """
        Получает позицию пользователя в очереди

        Args:
            user_id: ID пользователя

        Returns:
            Позиция или None если не в очереди
        """
        queue = await self.redis.lrange(self.queue_key, 0, -1)

        for i, task in enumerate(queue):
            data = json.loads(task)
            if data["user_id"] == user_id:
                return i + 1

        return None

    async def set_active(self, user_id: int):
        """Отмечает пользователя как активно загружающего"""
        await self.redis.sadd(self.active_key, str(user_id))

    async def remove_active(self, user_id: int):
        """Убирает пользователя из активных"""
        await self.redis.srem(self.active_key, str(user_id))

    async def is_active(self, user_id: int) -> bool:
        """Проверяет, загружает ли пользователь сейчас"""
        return await self.redis.sismember(self.active_key, str(user_id))

    async def get_active_count(self) -> int:
        """Количество активных загрузок"""
        return await self.redis.scard(self.active_key)

    async def get_queue_length(self) -> int:
        """Длина очереди"""
        return await self.redis.llen(self.queue_key)

    # Статистика
    async def increment_downloads(self, user_id: int, platform: str):
        """Увеличивает счётчик скачиваний"""
        # Общая статистика
        await self.redis.hincrby(self.stats_key, "total", 1)
        await self.redis.hincrby(self.stats_key, f"platform:{platform}", 1)

        # Статистика пользователя
        user_key = f"downloader:user:{user_id}"
        await self.redis.hincrby(user_key, "downloads", 1)

    async def get_stats(self) -> dict:
        """Получает общую статистику"""
        stats = await self.redis.hgetall(self.stats_key)
        return {
            "total": int(stats.get("total", 0)),
            "tiktok": int(stats.get("platform:TikTok", 0)),
            "instagram": int(stats.get("platform:Instagram", 0)),
            "youtube": int(stats.get("platform:YouTube", 0)),
            "pinterest": int(stats.get("platform:Pinterest", 0)),
        }

    async def get_user_stats(self, user_id: int) -> dict:
        """Получает статистику пользователя"""
        user_key = f"downloader:user:{user_id}"
        stats = await self.redis.hgetall(user_key)
        return {
            "downloads": int(stats.get("downloads", 0)),
        }
