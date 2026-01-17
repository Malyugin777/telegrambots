"""
Force Subscribe Middleware
Проверяет подписку на обязательные каналы
"""
import logging
from typing import Any, Awaitable, Callable, Dict, List

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message

from ..config import config
from ..keyboards.inline import get_check_sub_keyboard

logger = logging.getLogger(__name__)


class ForceSubscribeMiddleware(BaseMiddleware):
    """Middleware для проверки подписки на каналы"""

    def __init__(self, channels: List[str]):
        self.channels = channels
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Пропускаем если нет каналов для проверки
        if not self.channels:
            return await handler(event, data)

        # Пропускаем команду /start для первого сообщения
        if event.text and event.text.startswith("/start"):
            # Но всё равно проверяем подписку
            pass

        bot: Bot = data["bot"]
        user_id = event.from_user.id

        # Проверяем подписку на все каналы
        not_subscribed = []

        for channel in self.channels:
            try:
                member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
                if member.status in ["left", "kicked"]:
                    not_subscribed.append(channel)
            except Exception as e:
                logger.warning(f"Не удалось проверить подписку на {channel}: {e}")
                not_subscribed.append(channel)

        # Если не подписан на все каналы
        if not_subscribed:
            channels_text = "\n".join([f"• {ch}" for ch in self.channels])

            await event.answer(
                config.messages["force_sub"].format(channels=channels_text),
                reply_markup=get_check_sub_keyboard(self.channels)
            )
            return  # Не пропускаем дальше

        # Всё ок, продолжаем
        return await handler(event, data)
