"""
Error logging service for download errors.
"""
import logging
from typing import Optional
from sqlalchemy import select

from shared.database.connection import async_session
from shared.database.models import DownloadError, User, Bot

logger = logging.getLogger(__name__)


class ErrorLogger:
    """Service to log download errors to database."""

    @staticmethod
    async def log_error(
        user_id: Optional[int],
        bot_id: Optional[int],
        platform: str,
        url: str,
        error_type: str,
        error_message: Optional[str] = None,
        error_details: Optional[dict] = None,
    ) -> None:
        """
        Log a download error to the database.

        Args:
            user_id: Internal user ID (not telegram_id)
            bot_id: Internal bot ID
            platform: Platform name (instagram, tiktok, pinterest, youtube)
            url: URL that failed to download
            error_type: Type of error (network, parse, api, timeout, etc)
            error_message: Human-readable error message
            error_details: Additional error details as dict
        """
        try:
            async with async_session() as session:
                error = DownloadError(
                    user_id=user_id,
                    bot_id=bot_id,
                    platform=platform,
                    url=url,
                    error_type=error_type,
                    error_message=error_message,
                    error_details=error_details,
                )
                session.add(error)
                await session.commit()
                logger.info(f"Logged download error: {platform} - {error_type}")
        except Exception as e:
            logger.error(f"Failed to log download error: {e}")

    @staticmethod
    async def log_error_by_telegram_id(
        telegram_id: int,
        bot_username: str,
        platform: str,
        url: str,
        error_type: str,
        error_message: Optional[str] = None,
        error_details: Optional[dict] = None,
    ) -> None:
        """
        Log error using telegram_id and bot_username (easier for handlers).
        """
        try:
            async with async_session() as session:
                # Get user_id by telegram_id
                user_id = None
                result = await session.execute(
                    select(User.id).where(User.telegram_id == telegram_id)
                )
                user_row = result.scalar_one_or_none()
                if user_row:
                    user_id = user_row

                # Get bot_id by username
                bot_id = None
                result = await session.execute(
                    select(Bot.id).where(Bot.username == bot_username)
                )
                bot_row = result.scalar_one_or_none()
                if bot_row:
                    bot_id = bot_row

                error = DownloadError(
                    user_id=user_id,
                    bot_id=bot_id,
                    platform=platform,
                    url=url,
                    error_type=error_type,
                    error_message=error_message,
                    error_details=error_details,
                )
                session.add(error)
                await session.commit()
                logger.info(f"Logged download error: {platform} - {error_type}")
        except Exception as e:
            logger.error(f"Failed to log download error: {e}")


# Singleton instance
error_logger = ErrorLogger()
