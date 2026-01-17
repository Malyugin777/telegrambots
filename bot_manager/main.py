import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from shared.database import init_db
from shared.config import settings

# Import bot routers
from bot_manager.bots.downloader import router as downloader_router

# Import middlewares
from bot_manager.middlewares import UserTrackingMiddleware, init_bot_record

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def start_bot(token: str, name: str, router):
    """Start a single bot with its router."""
    bot = Bot(
        token=token,
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
