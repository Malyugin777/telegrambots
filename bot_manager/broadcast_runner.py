"""
Broadcast runner - обрабатывает рассылки из БД.

Запускается отдельно от основного бота.
Каждые N секунд проверяет БД на наличие рассылок со статусом RUNNING.
"""
import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import select, update

from shared.database import init_db
from shared.database.connection import async_session
from shared.config import settings

# Импортируем модели из admin_panel для работы с broadcasts
# Но они одинаковые с shared, так что просто создадим локальную копию
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum as SQLEnum, JSON
from sqlalchemy.orm import declarative_base
import enum

from bot_manager.services.broadcast_worker import BroadcastWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Интервал проверки новых рассылок (секунды)
CHECK_INTERVAL = 10


class BroadcastStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


async def process_broadcast(bot: Bot, broadcast_id: int):
    """Обработать одну рассылку."""
    async with async_session() as session:
        # Получаем данные рассылки напрямую из БД
        result = await session.execute(
            select("*").select_from(
                session.get_bind().dialect.identifier_preparer.format_table(
                    session.get_bind().dialect.identifier_preparer.quote("broadcasts")
                )
            )
        )
        # Упрощённый запрос
        from sqlalchemy import text
        result = await session.execute(
            text("SELECT * FROM broadcasts WHERE id = :id"),
            {"id": broadcast_id}
        )
        row = result.fetchone()

        if not row:
            logger.error(f"Broadcast {broadcast_id} not found")
            return

        # Распаковываем данные
        broadcast = dict(row._mapping)

        if broadcast["status"] != "running":
            logger.info(f"Broadcast {broadcast_id} is not running, skipping")
            return

        logger.info(f"Processing broadcast {broadcast_id}: {broadcast['name']}")

        worker = BroadcastWorker(bot)

        async def update_progress(sent: int, delivered: int, failed: int):
            """Обновить прогресс в БД."""
            await session.execute(
                text("""
                    UPDATE broadcasts
                    SET sent_count = :sent, delivered_count = :delivered, failed_count = :failed
                    WHERE id = :id
                """),
                {"sent": sent, "delivered": delivered, "failed": failed, "id": broadcast_id}
            )
            await session.commit()

        try:
            result = await worker.send_broadcast(
                broadcast_id=broadcast_id,
                text=broadcast["text"],
                image_url=broadcast.get("image_url"),
                video_url=broadcast.get("message_video"),
                buttons=broadcast.get("buttons"),
                target_type=broadcast.get("target_type", "all"),
                target_user_ids=broadcast.get("target_user_ids"),
                on_progress=update_progress,
            )

            # Завершаем рассылку
            await session.execute(
                text("""
                    UPDATE broadcasts
                    SET status = 'completed',
                        completed_at = :completed_at,
                        sent_count = :sent,
                        delivered_count = :delivered,
                        failed_count = :failed
                    WHERE id = :id
                """),
                {
                    "id": broadcast_id,
                    "completed_at": datetime.utcnow(),
                    "sent": result["sent"],
                    "delivered": result["delivered"],
                    "failed": result["failed"],
                }
            )
            await session.commit()

            logger.info(f"Broadcast {broadcast_id} completed successfully")

        except Exception as e:
            logger.exception(f"Broadcast {broadcast_id} failed: {e}")
            # Помечаем как отменённую
            await session.execute(
                text("""
                    UPDATE broadcasts
                    SET status = 'cancelled', completed_at = :completed_at
                    WHERE id = :id
                """),
                {"id": broadcast_id, "completed_at": datetime.utcnow()}
            )
            await session.commit()


async def main():
    """Основной цикл обработки рассылок."""
    logger.info("Initializing broadcast runner...")
    await init_db()

    # Инициализируем бота
    token = os.getenv("DOWNLOADER_BOT_TOKEN")
    if not token:
        logger.error("DOWNLOADER_BOT_TOKEN not set!")
        return

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    logger.info("Broadcast runner started, checking for broadcasts...")

    try:
        while True:
            try:
                async with async_session() as session:
                    from sqlalchemy import text

                    # Находим рассылки со статусом RUNNING
                    result = await session.execute(
                        text("SELECT id FROM broadcasts WHERE status = 'running' LIMIT 1")
                    )
                    row = result.fetchone()

                    if row:
                        broadcast_id = row[0]
                        logger.info(f"Found running broadcast: {broadcast_id}")
                        await process_broadcast(bot, broadcast_id)
                    else:
                        # Проверяем scheduled рассылки
                        result = await session.execute(
                            text("""
                                SELECT id FROM broadcasts
                                WHERE status = 'scheduled'
                                AND scheduled_at <= NOW()
                                LIMIT 1
                            """)
                        )
                        row = result.fetchone()

                        if row:
                            broadcast_id = row[0]
                            logger.info(f"Starting scheduled broadcast: {broadcast_id}")
                            # Переводим в running
                            await session.execute(
                                text("""
                                    UPDATE broadcasts
                                    SET status = 'running', started_at = NOW()
                                    WHERE id = :id
                                """),
                                {"id": broadcast_id}
                            )
                            await session.commit()
                            await process_broadcast(bot, broadcast_id)

            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")

            await asyncio.sleep(CHECK_INTERVAL)

    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
