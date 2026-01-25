"""
Middleware для отслеживания пользователей

Сохраняет пользователей в БД при первом контакте,
обновляет last_active_at при каждом сообщении.
"""
import logging
from typing import Callable, Dict, Any, Awaitable
from datetime import datetime

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from sqlalchemy import select

from shared.database.connection import async_session
from shared.database.models import User, BotUser
from bot_manager.middlewares.action_logger import _bot_id

logger = logging.getLogger(__name__)


class UserTrackingMiddleware(BaseMiddleware):
    """
    Middleware для трекинга пользователей.

    - При первом контакте создаёт запись в users
    - При каждом сообщении обновляет last_active_at
    - Сохраняет db_user в event data для использования в хендлерах
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Извлекаем пользователя из события
        user = None

        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user and not user.is_bot:
            try:
                db_user = await self._track_user(user)
                data["db_user"] = db_user
            except Exception as e:
                logger.error(f"User tracking error: {e}")

        return await handler(event, data)

    async def _track_user(self, tg_user) -> User:
        """Создаёт или обновляет пользователя в БД"""
        async with async_session() as session:
            # Ищем пользователя
            result = await session.execute(
                select(User).where(User.telegram_id == tg_user.id)
            )
            db_user = result.scalar_one_or_none()

            if db_user:
                # Обновляем last_active_at и данные профиля
                db_user.last_active_at = datetime.utcnow()
                db_user.username = tg_user.username
                db_user.first_name = tg_user.first_name
                db_user.last_name = tg_user.last_name
                if tg_user.language_code:
                    db_user.language_code = tg_user.language_code

                await session.commit()
                await session.refresh(db_user)

                logger.debug(f"User updated: {tg_user.id} (@{tg_user.username})")
            else:
                # Создаём нового пользователя
                db_user = User(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                    language_code=tg_user.language_code or "ru",
                    last_active_at=datetime.utcnow(),
                )
                session.add(db_user)
                await session.commit()
                await session.refresh(db_user)

                logger.info(f"New user: {tg_user.id} (@{tg_user.username})")

            # Создаём связь user-bot если ещё нет
            if _bot_id:
                result = await session.execute(
                    select(BotUser).where(
                        BotUser.user_id == db_user.id,
                        BotUser.bot_id == _bot_id
                    )
                )
                bot_user = result.scalar_one_or_none()

                if not bot_user:
                    bot_user = BotUser(
                        user_id=db_user.id,
                        bot_id=_bot_id,
                    )
                    session.add(bot_user)
                    await session.commit()
                    logger.info(f"User {tg_user.id} linked to bot {_bot_id}")

            return db_user
