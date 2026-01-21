"""
FlyerService интеграция для монетизации через подписки на каналы.

Логика проверки:
- Первые 3 дня — без проверок (даём попробовать)
- Первые 5 скачиваний — без проверок
- YouTube Full: после 3 видео → каждый раз
- Instagram: каждый 3-й раз
- YouTube Shorts, TikTok, Pinterest — бесплатно
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.models import User, ActionLog

# Попытка импортировать flyerapi (может быть не установлен)
try:
    from flyerapi import Flyer
    FLYER_AVAILABLE = True
except ImportError:
    Flyer = None
    FLYER_AVAILABLE = False

logger = logging.getLogger(__name__)

# FlyerService API ключ
FLYER_API_KEY = "FL-RELiwN-PULZsV-OqkKlf-ygoADQ"

# Настройки монетизации
FREE_DAYS = 3  # Первые N дней без проверок
FREE_DOWNLOADS = 5  # Первые N скачиваний без проверок
YOUTUBE_FULL_FREE_COUNT = 3  # YouTube Full бесплатно первые N раз
INSTAGRAM_CHECK_EVERY = 3  # Instagram проверять каждый N-й раз

# Инициализация клиента
_flyer: Optional[Flyer] = None


def get_flyer() -> Optional["Flyer"]:
    """Получить инстанс Flyer клиента (singleton)."""
    global _flyer
    if not FLYER_AVAILABLE:
        logger.warning("[FLYER] flyerapi not installed, skipping subscription check")
        return None
    if _flyer is None:
        _flyer = Flyer(FLYER_API_KEY)
        logger.info("[FLYER] Initialized FlyerService client")
    return _flyer


async def get_user_stats(session: AsyncSession, telegram_id: int) -> dict:
    """
    Получить статистику пользователя для проверки монетизации.

    Returns:
        {
            "created_at": datetime,
            "days_since_registration": int,
            "total_downloads": int,
            "youtube_full_count": int,
            "instagram_count": int,
        }
    """
    # Получаем юзера
    user_result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        return {
            "created_at": datetime.utcnow(),
            "days_since_registration": 0,
            "total_downloads": 0,
            "youtube_full_count": 0,
            "instagram_count": 0,
        }

    # Считаем дни с регистрации
    days_since = (datetime.utcnow() - user.created_at).days if user.created_at else 0

    # Считаем общее количество успешных скачиваний
    total_result = await session.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.user_id == user.id,
            ActionLog.action == "download_success"
        )
    )
    total_downloads = total_result.scalar() or 0

    # Считаем YouTube Full скачивания
    # Включаем "youtube" для совместимости со старыми записями (до разделения на shorts/full)
    # Используем json_extract_path_text для PostgreSQL JSON колонок
    platform_text = func.json_extract_path_text(ActionLog.details, 'platform')
    yt_full_result = await session.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.user_id == user.id,
            ActionLog.action == "download_success",
            or_(
                platform_text == "youtube_full",
                platform_text == "youtube"
            )
        )
    )
    youtube_full_count = yt_full_result.scalar() or 0

    # Считаем Instagram скачивания
    ig_result = await session.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.user_id == user.id,
            ActionLog.action == "download_success",
            platform_text == "instagram"
        )
    )
    instagram_count = ig_result.scalar() or 0

    return {
        "created_at": user.created_at,
        "days_since_registration": days_since,
        "total_downloads": total_downloads,
        "youtube_full_count": youtube_full_count,
        "instagram_count": instagram_count,
    }


async def should_check_subscription(
    session: AsyncSession,
    telegram_id: int,
    platform: str,
) -> bool:
    """
    Определить, нужно ли проверять подписку для этого скачивания.

    Args:
        session: SQLAlchemy async session
        telegram_id: Telegram user ID
        platform: Платформа (youtube_full, instagram, tiktok, pinterest, youtube_shorts)

    Returns:
        True если нужно проверить подписку, False если скачивание бесплатное
    """
    stats = await get_user_stats(session, telegram_id)

    # Первые N дней — бесплатно
    if stats["days_since_registration"] < FREE_DAYS:
        logger.debug(f"[FLYER] User {telegram_id}: free (day {stats['days_since_registration']+1}/{FREE_DAYS})")
        return False

    # Первые N скачиваний — бесплатно
    if stats["total_downloads"] < FREE_DOWNLOADS:
        logger.debug(f"[FLYER] User {telegram_id}: free (download {stats['total_downloads']+1}/{FREE_DOWNLOADS})")
        return False

    # Бесплатные платформы
    if platform in ("tiktok", "pinterest", "youtube_shorts", "youtube"):
        logger.debug(f"[FLYER] User {telegram_id}: free platform ({platform})")
        return False

    # YouTube Full: после 3 видео → каждый раз
    if platform == "youtube_full":
        if stats["youtube_full_count"] < YOUTUBE_FULL_FREE_COUNT:
            logger.debug(f"[FLYER] User {telegram_id}: free YT Full ({stats['youtube_full_count']+1}/{YOUTUBE_FULL_FREE_COUNT})")
            return False
        logger.info(f"[FLYER] User {telegram_id}: CHECK for youtube_full (count={stats['youtube_full_count']})")
        return True

    # Instagram: каждый 3-й раз
    if platform in ("instagram", "instagram_reel", "instagram_post", "instagram_story", "instagram_carousel"):
        # +1 потому что это будет следующее скачивание
        next_count = stats["instagram_count"] + 1
        if next_count % INSTAGRAM_CHECK_EVERY == 0:
            logger.info(f"[FLYER] User {telegram_id}: CHECK for instagram (count={next_count}, every {INSTAGRAM_CHECK_EVERY})")
            return True
        logger.debug(f"[FLYER] User {telegram_id}: free instagram ({next_count} % {INSTAGRAM_CHECK_EVERY} != 0)")
        return False

    # По умолчанию — бесплатно
    logger.debug(f"[FLYER] User {telegram_id}: free (unknown platform: {platform})")
    return False


async def check_subscription(
    telegram_id: int,
    language_code: str = "ru",
) -> bool:
    """
    Проверить подписку через FlyerService.

    Если пользователь не подписан — FlyerAPI автоматически покажет ему
    сообщение с кнопками для подписки.

    Args:
        telegram_id: Telegram user ID
        language_code: Язык пользователя

    Returns:
        True если подписан (можно скачивать), False если нет (сообщение уже показано)
    """
    try:
        flyer = get_flyer()
        if flyer is None:
            # flyerapi не установлен — пропускаем проверку
            return True

        result = await flyer.check(telegram_id, language_code=language_code)

        if result:
            logger.info(f"[FLYER] User {telegram_id}: subscribed ✓")
        else:
            logger.info(f"[FLYER] User {telegram_id}: not subscribed, showing tasks")

        return result
    except Exception as e:
        # При ошибке FlyerService — пропускаем проверку (не блокируем юзера)
        logger.error(f"[FLYER] Error checking subscription for {telegram_id}: {e}")
        return True


async def check_and_allow(
    session: AsyncSession,
    telegram_id: int,
    platform: str,
    language_code: str = "ru",
) -> bool:
    """
    Главная функция: проверить нужна ли подписка и если да — проверить её.

    Args:
        session: SQLAlchemy async session
        telegram_id: Telegram user ID
        platform: Платформа скачивания
        language_code: Язык пользователя

    Returns:
        True если можно скачивать, False если нужно сначала подписаться
    """
    # Проверяем нужна ли проверка для этого случая
    if not await should_check_subscription(session, telegram_id, platform):
        return True  # Бесплатное скачивание

    # Проверяем подписку через FlyerService
    return await check_subscription(telegram_id, language_code)
