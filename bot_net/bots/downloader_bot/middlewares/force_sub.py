"""
Force Subscribe Middleware
Проверяет подписку на обязательные каналы перед обработкой сообщений

Логика:
1. Перед обработкой любого сообщения проверяем подписку
2. Список каналов берём из config.required_channels
3. Если не подписан — показываем кнопки каналов + "Я подписался"
4. Если подписан — пропускаем дальше

Исключения (не проверять):
- Команда /start (первый раз показываем приветствие)
- Callback "check_subscription" (чтобы можно было проверить)
"""
import logging
from typing import Any, Awaitable, Callable, Dict, List, Union

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)


class ForceSubscribeMiddleware(BaseMiddleware):
    """
    Middleware для принудительной подписки на каналы

    Использование:
        dp.message.middleware(ForceSubscribeMiddleware(["@channel1", "@channel2"]))
        dp.callback_query.middleware(ForceSubscribeMiddleware(["@channel1"]))
    """

    def __init__(self, channels: List[str]):
        """
        Args:
            channels: Список каналов для обязательной подписки
                     Формат: ["@channel1", "@channel2"] или ["-1001234567890"]
        """
        self.channels = [ch.strip() for ch in channels if ch.strip()]
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""

        # Если нет каналов для проверки — пропускаем
        if not self.channels:
            return await handler(event, data)

        # Определяем тип события
        if isinstance(event, CallbackQuery):
            return await self._handle_callback(handler, event, data)
        elif isinstance(event, Message):
            return await self._handle_message(handler, event, data)
        else:
            return await handler(event, data)

    async def _handle_message(
        self,
        handler: Callable,
        message: Message,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка сообщений"""

        # Исключение: команда /start — пропускаем проверку
        if message.text and message.text.startswith("/start"):
            return await handler(message, data)

        # Проверяем подписку
        bot: Bot = data["bot"]
        user_id = message.from_user.id

        is_subscribed, missing_channels = await self._check_subscription(bot, user_id)

        if is_subscribed:
            # Подписан на все — пропускаем дальше
            return await handler(message, data)

        # Не подписан — показываем сообщение
        await message.answer(
            self._get_subscribe_message(),
            reply_markup=self._get_subscribe_keyboard()
        )
        # Не пропускаем дальше
        return None

    async def _handle_callback(
        self,
        handler: Callable,
        callback: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка callback-кнопок"""

        # Исключение: кнопка "Я подписался" — пропускаем проверку
        # (её обработчик сам проверит подписку)
        if callback.data == "check_subscription":
            return await handler(callback, data)

        # Проверяем подписку
        bot: Bot = data["bot"]
        user_id = callback.from_user.id

        is_subscribed, missing_channels = await self._check_subscription(bot, user_id)

        if is_subscribed:
            return await handler(callback, data)

        # Не подписан — показываем alert
        await callback.answer(
            "❌ Сначала подпишись на каналы!",
            show_alert=True
        )
        return None

    async def _check_subscription(
        self,
        bot: Bot,
        user_id: int
    ) -> tuple[bool, List[str]]:
        """
        Проверяет подписку пользователя на все каналы

        Args:
            bot: Инстанс бота
            user_id: ID пользователя

        Returns:
            (is_subscribed, missing_channels)
        """
        missing = []

        for channel in self.channels:
            try:
                member = await bot.get_chat_member(chat_id=channel, user_id=user_id)

                # Статусы подписанного пользователя
                subscribed_statuses = ["creator", "administrator", "member", "restricted"]

                if member.status not in subscribed_statuses:
                    missing.append(channel)

            except Exception as e:
                # Ошибка проверки — считаем не подписанным
                logger.warning(f"Ошибка проверки подписки на {channel}: {e}")
                missing.append(channel)

        is_subscribed = len(missing) == 0
        return is_subscribed, missing

    def _get_subscribe_message(self) -> str:
        """Сообщение с просьбой подписаться"""
        channels_text = "\n".join([f"   • {self._format_channel(ch)}" for ch in self.channels])

        return (
            "🔒 <b>Доступ ограничен</b>\n\n"
            "Для использования бота подпишись на каналы:\n"
            f"{channels_text}\n\n"
            "После подписки нажми кнопку ниже 👇"
        )

    def _get_subscribe_keyboard(self) -> InlineKeyboardMarkup:
        """
        Клавиатура с кнопками каналов

        Структура:
        [📢 Канал 1] [📢 Канал 2]
        [✅ Я подписался]
        """
        buttons = []

        # Кнопки каналов (по 2 в ряд)
        channel_buttons = []
        for i, channel in enumerate(self.channels):
            channel_name = self._format_channel(channel)
            channel_url = self._get_channel_url(channel)

            channel_buttons.append(
                InlineKeyboardButton(
                    text=f"📢 {channel_name}",
                    url=channel_url
                )
            )

            # По 2 кнопки в ряд
            if len(channel_buttons) == 2:
                buttons.append(channel_buttons)
                channel_buttons = []

        # Добавляем оставшиеся кнопки
        if channel_buttons:
            buttons.append(channel_buttons)

        # Кнопка проверки подписки
        buttons.append([
            InlineKeyboardButton(
                text="✅ Я подписался",
                callback_data="check_subscription"
            )
        ])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def _format_channel(self, channel: str) -> str:
        """Форматирует название канала для отображения"""
        # Убираем @ если есть
        if channel.startswith("@"):
            return channel[1:]
        # Если это ID — показываем как есть
        if channel.startswith("-100"):
            return f"Канал"
        return channel

    def _get_channel_url(self, channel: str) -> str:
        """Получает URL канала для кнопки"""
        if channel.startswith("@"):
            return f"https://t.me/{channel[1:]}"
        elif channel.startswith("-100"):
            # Для private каналов по ID — не можем дать прямую ссылку
            # Но можно попробовать через t.me/c/
            channel_id = channel[4:]  # Убираем -100
            return f"https://t.me/c/{channel_id}"
        else:
            return f"https://t.me/{channel}"


class ForceSubscribeCallbackMiddleware(ForceSubscribeMiddleware):
    """
    Отдельный middleware для callback_query
    (если нужно разное поведение для сообщений и callback)
    """

    async def __call__(
        self,
        handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка callback"""

        if not self.channels:
            return await handler(event, data)

        # Пропускаем check_subscription
        if event.data == "check_subscription":
            return await handler(event, data)

        # Пропускаем cancel
        if event.data == "cancel":
            return await handler(event, data)

        # Проверяем подписку
        bot: Bot = data["bot"]
        user_id = event.from_user.id

        is_subscribed, _ = await self._check_subscription(bot, user_id)

        if is_subscribed:
            return await handler(event, data)

        # Не подписан
        await event.answer(
            "❌ Для использования бота подпишись на каналы!",
            show_alert=True
        )

        # Показываем/обновляем сообщение с кнопками
        try:
            await event.message.edit_text(
                self._get_subscribe_message(),
                reply_markup=self._get_subscribe_keyboard()
            )
        except Exception:
            pass  # Сообщение не изменилось

        return None
