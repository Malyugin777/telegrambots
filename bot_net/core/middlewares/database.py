"""
Database middleware for Aiogram 3.
Injects database session into handler data.
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot_net.core.database import db


class DatabaseMiddleware(BaseMiddleware):
    """
    Middleware that provides database session to handlers.

    Usage in handler:
        async def my_handler(message: Message, session: AsyncSession):
            # Use session here
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with db.session() as session:
            data["session"] = session
            return await handler(event, data)
