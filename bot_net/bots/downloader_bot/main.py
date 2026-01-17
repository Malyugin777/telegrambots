"""
Точка входа Downloader Bot
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from .config import config
from .handlers import start, download, callbacks
from .middlewares.force_sub import ForceSubscribeMiddleware, ForceSubscribeCallbackMiddleware
from .middlewares.throttling import ThrottlingMiddleware
from .middlewares.user_tracking import UserTrackingMiddleware, register_bot
from .services.queue import DownloadQueue

# Database
from bot_net.core.database.connection import db

logger = logging.getLogger(__name__)


async def create_downloader_bot() -> tuple[Bot, Dispatcher]:
    """Создание и настройка бота"""

    if not config.token:
        raise ValueError("DOWNLOADER_BOT_TOKEN не установлен")

    # Создаём бота
    bot = Bot(
        token=config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Подключаем базу данных
    await db.connect()

    # Регистрируем бота в БД
    bot_info = await bot.get_me()
    await register_bot(
        bot_username=bot_info.username,
        bot_name="SaveNinja"
    )

    # Redis storage для FSM
    storage = RedisStorage.from_url(config.redis_url)

    # Диспетчер
    dp = Dispatcher(storage=storage)

    # Инициализируем очередь
    queue = DownloadQueue(config.redis_url)
    await queue.connect()

    # Добавляем в контекст
    dp["download_queue"] = queue
    dp["config"] = config

    # Middlewares
    # User Tracking — сохранение пользователей в БД (первым!)
    dp.message.middleware(UserTrackingMiddleware())
    dp.callback_query.middleware(UserTrackingMiddleware())

    # Force Subscribe — проверка подписки на каналы
    if config.required_channels:
        dp.message.middleware(ForceSubscribeMiddleware(config.required_channels))
        dp.callback_query.middleware(ForceSubscribeCallbackMiddleware(config.required_channels))

    # Throttling — антиспам
    dp.message.middleware(ThrottlingMiddleware(
        rate_limit=config.rate_limit_messages,
        period=config.rate_limit_seconds
    ))

    # Роутеры
    dp.include_router(start.router)
    dp.include_router(download.router)
    dp.include_router(callbacks.router)

    logger.info("Downloader Bot создан")

    return bot, dp


async def run_downloader_bot():
    """Запуск бота (standalone)"""
    bot, dp = await create_downloader_bot()

    try:
        logger.info("Запуск Downloader Bot...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await db.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_downloader_bot())
