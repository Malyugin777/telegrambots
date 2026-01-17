"""
Main bot factory.
"""
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from bot_net.core import (
    DatabaseMiddleware,
    UserRegisterMiddleware,
    BanCheckMiddleware,
    logger,
)
from .handlers import router


def create_main_bot(token: str, redis_url: str | None = None) -> tuple[Bot, Dispatcher]:
    """
    Create and configure the main bot.

    Args:
        token: Bot token from BotFather
        redis_url: Redis URL for FSM storage (optional)

    Returns:
        Tuple of (Bot, Dispatcher)
    """
    # Create bot instance
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Create dispatcher with storage
    if redis_url:
        storage = RedisStorage.from_url(redis_url)
        dp = Dispatcher(storage=storage)
    else:
        dp = Dispatcher()

    # Register middlewares (order matters!)
    dp.message.middleware(DatabaseMiddleware())
    dp.message.middleware(UserRegisterMiddleware())
    dp.message.middleware(BanCheckMiddleware(silent=False))

    dp.callback_query.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(UserRegisterMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware(silent=True))

    # Register routers
    dp.include_router(router)

    logger.info("Main bot created successfully")
    return bot, dp
