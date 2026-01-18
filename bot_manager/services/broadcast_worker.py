"""
Broadcast worker - отправка рассылок пользователям.

Telegram API лимиты:
- 30 сообщений в секунду (используем 25 для безопасности)
- 20 сообщений в минуту в одну группу
"""
import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.connection import async_session
from shared.database.models import User

logger = logging.getLogger(__name__)

# Telegram API limits
MESSAGES_PER_SECOND = 25
BATCH_SIZE = 100
UPDATE_STATS_EVERY = 50


class BroadcastWorker:
    """Worker для отправки рассылок."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._cancelled = False

    async def send_broadcast(
        self,
        broadcast_id: int,
        text: str,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        buttons: Optional[List[dict]] = None,
        target_type: str = "all",
        target_user_ids: Optional[List[int]] = None,
        on_progress: Optional[callable] = None,
    ) -> dict:
        """
        Отправить рассылку.

        Args:
            broadcast_id: ID рассылки в БД
            text: Текст сообщения (HTML)
            image_url: URL или file_id фото
            video_url: URL или file_id видео
            buttons: Список кнопок [{text, url}, ...]
            target_type: 'all' | 'list'
            target_user_ids: Список telegram_id (если target_type='list')
            on_progress: Callback для обновления прогресса

        Returns:
            dict с результатами: sent, delivered, failed
        """
        self._cancelled = False

        # Получаем список получателей
        recipients = await self._get_recipients(target_type, target_user_ids)
        total = len(recipients)

        logger.info(f"Starting broadcast {broadcast_id}: {total} recipients")

        # Строим клавиатуру
        keyboard = self._build_keyboard(buttons)

        sent = 0
        delivered = 0
        failed = 0
        blocked_users = []

        for batch in self._chunks(recipients, BATCH_SIZE):
            if self._cancelled:
                logger.info(f"Broadcast {broadcast_id} cancelled")
                break

            for telegram_id in batch:
                try:
                    await self._send_message(
                        telegram_id, text, image_url, video_url, keyboard
                    )
                    delivered += 1

                except TelegramForbiddenError:
                    # Пользователь заблокировал бота
                    failed += 1
                    blocked_users.append(telegram_id)

                except TelegramBadRequest as e:
                    failed += 1
                    logger.warning(f"Bad request for {telegram_id}: {e}")

                except Exception as e:
                    failed += 1
                    logger.error(f"Error sending to {telegram_id}: {e}")

                sent += 1

                # Обновляем прогресс
                if sent % UPDATE_STATS_EVERY == 0 and on_progress:
                    await on_progress(sent, delivered, failed)

                # Throttling
                await asyncio.sleep(1 / MESSAGES_PER_SECOND)

        # Помечаем заблокировавших пользователей
        if blocked_users:
            await self._mark_blocked_users(blocked_users)

        # Финальный колбэк
        if on_progress:
            await on_progress(sent, delivered, failed)

        logger.info(
            f"Broadcast {broadcast_id} completed: "
            f"{delivered}/{total} delivered, {failed} failed"
        )

        return {
            "sent": sent,
            "delivered": delivered,
            "failed": failed,
            "blocked": len(blocked_users),
        }

    def cancel(self):
        """Отменить текущую рассылку."""
        self._cancelled = True

    async def _get_recipients(
        self,
        target_type: str,
        target_user_ids: Optional[List[int]] = None,
    ) -> List[int]:
        """Получить список telegram_id получателей."""
        async with async_session() as session:
            query = select(User.telegram_id).where(User.is_blocked == False)

            if target_type == "list" and target_user_ids:
                query = query.where(User.telegram_id.in_(target_user_ids))

            result = await session.execute(query)
            return [row[0] for row in result.all()]

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        image_url: Optional[str],
        video_url: Optional[str],
        keyboard: Optional[InlineKeyboardMarkup],
    ):
        """Отправить сообщение одному пользователю."""
        if video_url:
            await self.bot.send_video(
                chat_id=chat_id,
                video=video_url,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        elif image_url:
            await self.bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        else:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

    def _build_keyboard(
        self, buttons: Optional[List[dict]]
    ) -> Optional[InlineKeyboardMarkup]:
        """Построить inline клавиатуру."""
        if not buttons:
            return None

        keyboard_buttons = []
        for btn in buttons:
            if btn.get("url"):
                keyboard_buttons.append([
                    InlineKeyboardButton(text=btn["text"], url=btn["url"])
                ])
            elif btn.get("callback_data"):
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=btn["text"],
                        callback_data=btn["callback_data"]
                    )
                ])

        return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None

    async def _mark_blocked_users(self, telegram_ids: List[int]):
        """Пометить пользователей как заблокировавших бота."""
        async with async_session() as session:
            await session.execute(
                update(User)
                .where(User.telegram_id.in_(telegram_ids))
                .values(is_blocked=True)
            )
            await session.commit()

        logger.info(f"Marked {len(telegram_ids)} users as blocked")

    @staticmethod
    def _chunks(lst: List, n: int):
        """Разбить список на чанки."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]
