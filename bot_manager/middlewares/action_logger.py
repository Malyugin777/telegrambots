"""
Утилита для логирования действий пользователей в БД
"""
import logging
from typing import Optional
from datetime import datetime

from shared.database.connection import async_session
from shared.database.models import ActionLog, User, Bot
from sqlalchemy import select

logger = logging.getLogger(__name__)

# ID бота SaveNinja (будет заполнен при старте)
_bot_id: Optional[int] = None


async def init_bot_record(bot_username: str, bot_id: int, bot_name: str) -> int:
    """
    Создаёт или обновляет запись бота в БД.
    Вызывается при старте бота.
    """
    global _bot_id

    async with async_session() as session:
        result = await session.execute(
            select(Bot).where(Bot.bot_id == bot_id)
        )
        db_bot = result.scalar_one_or_none()

        if db_bot:
            db_bot.username = bot_username
            db_bot.name = bot_name
            await session.commit()
            _bot_id = db_bot.id
        else:
            db_bot = Bot(
                bot_id=bot_id,
                username=bot_username,
                name=bot_name,
            )
            session.add(db_bot)
            await session.commit()
            await session.refresh(db_bot)
            _bot_id = db_bot.id

        logger.info(f"Bot registered: {bot_username} (db_id={_bot_id})")
        return _bot_id


async def log_action(
    telegram_id: int,
    action: str,
    details: Optional[str] = None
) -> None:
    """
    Записывает действие пользователя в action_logs.

    Args:
        telegram_id: Telegram ID пользователя
        action: Тип действия (start, download, audio, etc.)
        details: Дополнительные данные (URL, платформа, etc.)
    """
    try:
        async with async_session() as session:
            # Находим user_id по telegram_id
            result = await session.execute(
                select(User.id).where(User.telegram_id == telegram_id)
            )
            user_id = result.scalar_one_or_none()

            if not user_id:
                logger.warning(f"User not found for action log: {telegram_id}")
                return

            # details должен быть dict (JSON), а не строкой
            details_dict = {"info": details} if details else None

            log_entry = ActionLog(
                user_id=user_id,
                bot_id=_bot_id,
                action=action,
                details=details_dict,
            )
            session.add(log_entry)
            await session.commit()

            logger.debug(f"Action logged: user={telegram_id}, action={action}")

    except Exception as e:
        logger.error(f"Action log error: {e}")
