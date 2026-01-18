import asyncio
import logging
import os
from aiohttp import ClientSession, ClientTimeout, TCPConnector
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from shared.database import init_db, AsyncSessionLocal
from shared.config import settings

# Import bot routers
from bot_manager.bots.downloader import router as downloader_router

# Import middlewares
from bot_manager.middlewares import UserTrackingMiddleware, init_bot_record

# Import messages loader
from bot_manager.bots.downloader.messages import load_messages_from_db, start_cache_refresh_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def start_bot(token: str, name: str, router):
    """Start a single bot with its router."""

    # Создаём кастомную aiohttp.ClientSession с максимальными таймаутами для 2GB файлов
    # total=None снимает общий лимит, sock_read=3600 (1 час) дает время на обработку
    custom_timeout = ClientTimeout(
        total=None,        # Без общего лимита (файлы до 2GB)
        sock_read=3600,    # 1 час между чанками данных (для processing gap)
        sock_connect=120   # 2 минуты на подключение
    )

    # TCPConnector с агрессивным keepalive и без force_close
    connector = TCPConnector(
        limit=100,
        limit_per_host=30,
        force_close=False,  # НЕ закрывать соединение после запроса
        enable_cleanup_closed=True,
        ttl_dns_cache=300,
    )

    # Создаём aiohttp.ClientSession вручную с нашими настройками
    aiohttp_session = ClientSession(
        timeout=custom_timeout,
        connector=connector
    )

    # Оборачиваем в AiohttpSession для aiogram
    session = AiohttpSession()
    session._session = aiohttp_session

    # HACK: Устанавливаем timeout как число для Dispatcher
    # Dispatcher проверяет bot.session.timeout и складывает с polling_timeout
    # Если это ClientTimeout - будет TypeError
    session.timeout = 60.0  # Число для Dispatcher polling

    logger.info("Custom aiohttp session: sock_read=3600s, total=None, force_close=False")

    bot = Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Регистрируем middleware для трекинга пользователей
    dp.message.middleware(UserTrackingMiddleware())
    dp.callback_query.middleware(UserTrackingMiddleware())

    dp.include_router(router)

    # Получаем информацию о боте и регистрируем в БД
    bot_info = await bot.get_me()
    await init_bot_record(
        bot_username=bot_info.username,
        bot_id=bot_info.id,
        bot_name=name
    )

    logger.info(f"Starting bot: {name} (@{bot_info.username})")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"Bot {name} error: {e}")
        raise


async def main():
    logger.info("Initializing database...")
    await init_db()

    # Загружаем сообщения бота из БД
    logger.info("Loading bot messages from database...")
    async with AsyncSessionLocal() as session:
        await load_messages_from_db(session)

    # Запускаем фоновое обновление кэша сообщений
    start_cache_refresh_task()

    # Collect all bots to start
    bots_to_start = []

    # Downloader bot
    downloader_token = os.getenv("DOWNLOADER_BOT_TOKEN")
    if downloader_token and downloader_token != "YOUR_BOT_TOKEN_HERE":
        bots_to_start.append(
            start_bot(downloader_token, "SaveNinja", downloader_router)
        )
        logger.info("Downloader bot configured")
    else:
        logger.warning("DOWNLOADER_BOT_TOKEN not set, skipping downloader bot")

    if not bots_to_start:
        logger.error("No bots configured! Set bot tokens in .env")
        return

    logger.info(f"Starting {len(bots_to_start)} bot(s)...")
    await asyncio.gather(*bots_to_start)


if __name__ == "__main__":
    asyncio.run(main())
# Test bot deploy
# Sync 2026-01-18
