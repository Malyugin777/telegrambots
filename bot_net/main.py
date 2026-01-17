"""
Main entry point for the bot network.
Runs all bots concurrently.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "shared"))

from config import settings
from bot_net.core import db, logger
from bot_net.bots.main_bot import create_main_bot


async def on_startup() -> None:
    """Run on bot startup."""
    logger.info("Starting bot network...")

    # Connect to database and create tables
    await db.connect()
    await db.create_tables()
    logger.info("Database connected and tables created")


async def on_shutdown() -> None:
    """Run on bot shutdown."""
    logger.info("Shutting down bot network...")
    await db.disconnect()
    logger.info("Database disconnected")


async def main() -> None:
    """Main function to run all bots."""
    await on_startup()

    try:
        # Create bots
        bots_to_run = []

        if settings.main_bot_token:
            main_bot, main_dp = create_main_bot(
                token=settings.main_bot_token,
                redis_url=settings.redis_url if settings.redis_host else None,
            )
            bots_to_run.append((main_bot, main_dp, "Main Bot"))
            logger.info("Main bot initialized")

        if not bots_to_run:
            logger.error("No bot tokens configured! Check your .env file")
            return

        # Run all bots concurrently
        logger.info(f"Starting {len(bots_to_run)} bot(s)...")

        async def run_bot(bot, dp, name):
            logger.info(f"{name} starting polling...")
            try:
                await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
            except Exception as e:
                logger.error(f"{name} error: {e}")

        await asyncio.gather(
            *[run_bot(bot, dp, name) for bot, dp, name in bots_to_run]
        )

    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
