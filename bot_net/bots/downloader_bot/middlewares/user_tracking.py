"""
User Tracking Middleware
Сохраняет пользователей в БД и отслеживает статистику
"""
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject, User as TgUser
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from bot_net.core.database.connection import db
from bot_net.core.database.models import User, Bot, BotUser, ActionLog

logger = logging.getLogger(__name__)

# ID бота в базе (устанавливается при старте)
BOT_DB_ID: int | None = None


async def register_bot(bot_username: str, bot_name: str = "SaveNinja") -> int:
    """
    Регистрирует бота в БД при запуске.

    Args:
        bot_username: Username бота (без @)
        bot_name: Название бота

    Returns:
        ID бота в базе
    """
    global BOT_DB_ID

    async with db.session() as session:
        # Ищем бота по username
        result = await session.execute(
            select(Bot).where(Bot.bot_username == bot_username)
        )
        bot = result.scalar_one_or_none()

        if bot:
            BOT_DB_ID = bot.id
            logger.info(f"Bot found in DB: id={bot.id}, name={bot.name}")
        else:
            # Создаём нового бота
            new_bot = Bot(
                name=bot_name,
                bot_username=bot_username,
                token_hash="downloader",  # Заглушка
                description="All-in-One Video Downloader",
                settings={"type": "downloader"}
            )
            session.add(new_bot)
            await session.flush()
            BOT_DB_ID = new_bot.id
            logger.info(f"Bot registered in DB: id={new_bot.id}, username={bot_username}")

        return BOT_DB_ID


async def track_user(tg_user: TgUser) -> int | None:
    """
    Создаёт или обновляет пользователя в БД.

    Args:
        tg_user: Telegram User объект

    Returns:
        ID пользователя в базе
    """
    if not tg_user:
        return None

    async with db.session() as session:
        # Upsert пользователя
        stmt = insert(User).values(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code,
            last_active_at=datetime.utcnow()
        ).on_conflict_do_update(
            index_elements=['telegram_id'],
            set_={
                'username': tg_user.username,
                'first_name': tg_user.first_name,
                'last_name': tg_user.last_name,
                'language_code': tg_user.language_code,
                'last_active_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
        ).returning(User.id)

        result = await session.execute(stmt)
        user_id = result.scalar_one()

        # Upsert bot_user связь
        if BOT_DB_ID:
            bot_user_stmt = insert(BotUser).values(
                user_id=user_id,
                bot_id=BOT_DB_ID,
                last_interaction=datetime.utcnow()
            ).on_conflict_do_update(
                index_elements=['user_id', 'bot_id'],
                set_={
                    'last_interaction': datetime.utcnow(),
                    'is_subscribed': True
                }
            )
            # Добавляем constraint если его нет
            try:
                await session.execute(bot_user_stmt)
            except Exception:
                # Если нет уникального индекса, делаем обычный upsert
                existing = await session.execute(
                    select(BotUser).where(
                        BotUser.user_id == user_id,
                        BotUser.bot_id == BOT_DB_ID
                    )
                )
                bot_user = existing.scalar_one_or_none()
                if bot_user:
                    bot_user.last_interaction = datetime.utcnow()
                else:
                    session.add(BotUser(
                        user_id=user_id,
                        bot_id=BOT_DB_ID,
                        last_interaction=datetime.utcnow()
                    ))

        return user_id


async def log_action(user_id: int | None, action: str, details: dict = None):
    """
    Логирует действие пользователя.

    Args:
        user_id: ID пользователя в БД
        action: Тип действия (start, download_video, download_audio)
        details: Дополнительные данные
    """
    if not BOT_DB_ID:
        return

    async with db.session() as session:
        log = ActionLog(
            user_id=user_id,
            bot_id=BOT_DB_ID,
            action=action,
            details=details or {}
        )
        session.add(log)


class UserTrackingMiddleware(BaseMiddleware):
    """
    Middleware для автоматического трекинга пользователей.
    Сохраняет каждого пользователя в БД при любом взаимодействии.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем пользователя
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user:
            try:
                # Трекаем пользователя
                user_db_id = await track_user(user)
                data['user_db_id'] = user_db_id
            except Exception as e:
                logger.warning(f"Failed to track user {user.id}: {e}")
                data['user_db_id'] = None

        return await handler(event, data)
