"""
Throttling Middleware
Антиспам защита
"""
import time
import logging
from typing import Any, Awaitable, Callable, Dict
from collections import defaultdict

from aiogram import BaseMiddleware
from aiogram.types import Message

from ..config import config

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """Middleware для ограничения частоты запросов"""

    def __init__(self, rate_limit: int = 3, period: int = 10):
        """
        Args:
            rate_limit: Максимальное количество сообщений
            period: За период в секундах
        """
        self.rate_limit = rate_limit
        self.period = period
        self.user_timestamps: Dict[int, list] = defaultdict(list)
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        current_time = time.time()

        # Очищаем старые timestamps
        self.user_timestamps[user_id] = [
            ts for ts in self.user_timestamps[user_id]
            if current_time - ts < self.period
        ]

        # Проверяем лимит
        if len(self.user_timestamps[user_id]) >= self.rate_limit:
            await event.answer(config.messages["rate_limit"])
            return

        # Добавляем текущий timestamp
        self.user_timestamps[user_id].append(current_time)

        # Продолжаем обработку
        return await handler(event, data)
