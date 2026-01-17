"""
Ban check middleware.
Blocks banned users from interacting with the bot.
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message

from bot_net.core.database import User


class BanCheckMiddleware(BaseMiddleware):
    """
    Middleware that blocks banned users.

    Requires UserRegisterMiddleware to be registered BEFORE this one.
    """

    def __init__(self, silent: bool = True):
        """
        Args:
            silent: If True, silently ignore banned users.
                   If False, send a message about the ban.
        """
        self.silent = silent

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user: User | None = data.get("user")

        if user is not None and user.is_banned:
            if not self.silent and isinstance(event, Message):
                reason = user.ban_reason or "No reason specified"
                await event.answer(f"You are banned.\nReason: {reason}")
            return None

        return await handler(event, data)
