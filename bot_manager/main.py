import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

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
    from aiohttp import ClientTimeout
    from aiogram.client.session.aiohttp import AiohttpSession

    # Создаём сессию с увеличенными таймаутами для больших файлов
    session = AiohttpSession()

    bot = Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # HACK: Патчим внутреннюю aiohttp сессию напрямую после создания
    # Устанавливаем длинные таймауты для загрузки больших файлов (до 2GB)
    if hasattr(bot.session, '_session') and bot.session._session:
        bot.session._session._timeout = ClientTimeout(
            total=None,        # Без общего лимита (используем request_timeout)
            connect=60,        # 1 минута на подключение
            sock_read=600,     # 10 минут между чанками (КЛЮЧЕВОЕ!)
            sock_connect=60    # 1 минута на socket connect
        )
        logger.info("Patched aiohttp session timeout: sock_read=600s (for large file uploads)")

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
