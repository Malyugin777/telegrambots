"""
User registration middleware.
Auto-registers new users and updates existing ones.
"""
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot_net.core.database import User


class UserRegisterMiddleware(BaseMiddleware):
    """
    Middleware that registers new users and updates user info.

    Requires DatabaseMiddleware to be registered BEFORE this one.

    Usage in handler:
        async def my_handler(message: Message, user: User):
            # user is the database User object
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session: AsyncSession = data.get("session")
        if session is None:
            # No session - just pass through
            return await handler(event, data)

        # Get telegram user from event
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        # Find or create user
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            # Create new user
            user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language_code=tg_user.language_code,
                last_active_at=datetime.utcnow(),
            )
            session.add(user)
            await session.flush()
        else:
            # Update existing user info
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name
            user.language_code = tg_user.language_code
            user.last_active_at = datetime.utcnow()

        data["user"] = user
        return await handler(event, data)
