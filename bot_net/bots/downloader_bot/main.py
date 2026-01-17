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
from .middlewares.force_sub import ForceSubscribeMiddleware
from .middlewares.throttling import ThrottlingMiddleware
from .services.queue import DownloadQueue

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
    if config.required_channels:
        dp.message.middleware(ForceSubscribeMiddleware(config.required_channels))

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_downloader_bot())
