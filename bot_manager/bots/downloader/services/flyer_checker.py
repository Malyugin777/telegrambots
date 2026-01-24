"""
FlyerService интеграция для монетизации через подписки на каналы.

Логика проверки ("Mom's Strategy"):
- Первые 3 дня — без проверок (медовый месяц)
- Начиная с 4-го дня — проверка на каждое 10-е скачивание (10, 20, 30...)
- Если юзер уже подписан — молча пропускаем (тихая проверка)
- Единое правило для ВСЕХ платформ
"""

import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
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

# FlyerService API ключ (из переменной окружения)
FLYER_API_KEY = os.getenv("FLYER_API_KEY", "")
FLYER_DISABLED = False  # Глобальный выключатель

# === Настройки монетизации (Mom's Strategy) ===
FREE_DAYS = 3          # Первые N дней без проверок (медовый месяц)
CHECK_INTERVAL = 10    # Проверять каждое N-е скачивание

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
            "days_since_registration": int,
            "total_downloads": int,
        }
    """
    # Получаем юзера
    user_result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        return {
            "days_since_registration": 0,
            "total_downloads": 0,
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

    return {
        "days_since_registration": days_since,
        "total_downloads": total_downloads,
    }


async def should_check_subscription(
    session: AsyncSession,
    telegram_id: int,
    platform: str,  # Оставляем для совместимости, но не используем
) -> bool:
    """
    Определить, нужно ли проверять подписку для этого скачивания.

    Логика (Mom's Strategy):
    1. Первые FREE_DAYS дней — бесплатно
    2. После — каждое CHECK_INTERVAL-е скачивание

    Args:
        session: SQLAlchemy async session
        telegram_id: Telegram user ID
        platform: Платформа (не используется, единое правило для всех)

    Returns:
        True если нужно проверить подписку, False если скачивание бесплатное
    """
    stats = await get_user_stats(session, telegram_id)

    days = stats["days_since_registration"]
    total = stats["total_downloads"]

    # Step A: Медовый месяц — первые N дней бесплатно
    if days < FREE_DAYS:
        logger.debug(f"[FLYER] User {telegram_id}: FREE (honey period, day {days + 1}/{FREE_DAYS})")
        return False

    # Step B: Номер текущего скачивания (это будет следующее после total)
    current_download = total + 1

    # Step C: Проверяем каждое N-е скачивание
    if current_download % CHECK_INTERVAL == 0:
        logger.info(f"[FLYER] User {telegram_id}: CHECK (download #{current_download}, every {CHECK_INTERVAL})")
        return True

    # Step D: Остальные скачивания бесплатны
    logger.debug(f"[FLYER] User {telegram_id}: FREE (download #{current_download})")
    return False


async def check_subscription(
    telegram_id: int,
    language_code: str = "ru",
) -> bool:
    """
    Проверить подписку через FlyerService (тихая проверка).

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
            logger.warning(f"[FLYER] User {telegram_id}: flyerapi not available, SKIP")
            return True

        # Очищаем локальный кэш чтобы всегда делать реальный запрос
        if telegram_id in flyer._cache:
            del flyer._cache[telegram_id]
            logger.debug(f"[FLYER] User {telegram_id}: cleared local cache")

        # Кастомное сообщение для SaveNinja
        custom_message = {
            'text': '📥 <b>Чтобы скачать видео</b>, подпишись на нашего партнёра\n\n<i>После подписки отправь ссылку ещё раз</i>',
            'button_bot': '🤖 Запустить',
            'button_channel': '📢 Подписаться',
            'button_fp': '✅ Проверить',
        }

        logger.info(f"[FLYER] User {telegram_id}: calling API check()...")
        result = await flyer.check(telegram_id, language_code=language_code, message=custom_message)

        if result:
            # Юзер подписан — тихий проход
            # Пробуем получить info для детализации (почему skip=True)
            try:
                info = await flyer.info(telegram_id)
                attached_at = info.get('attached_at', 'unknown')
                logger.info(f"[FLYER] User {telegram_id}: SILENT PASS (subscribed since {attached_at})")
            except Exception:
                logger.info(f"[FLYER] User {telegram_id}: SILENT PASS (subscribed)")
        else:
            logger.info(f"[FLYER] User {telegram_id}: AD SHOWN (not subscribed)")

        return result
    except Exception as e:
        # При ошибке FlyerService — пропускаем проверку (не блокируем юзера)
        logger.error(f"[FLYER] Error checking subscription for {telegram_id}: {e}")
        return True


class FlyerCheckResult:
    """Результат проверки FlyerService."""
    def __init__(self, allowed: bool, flyer_required: bool, flyer_shown: bool = False):
        self.allowed = allowed  # Можно ли скачивать
        self.flyer_required = flyer_required  # Требовалась ли проверка Flyer (для телеметрии)
        self.flyer_shown = flyer_shown  # Была ли показана реклама (юзер не подписан)


async def check_and_allow(
    session: AsyncSession,
    telegram_id: int,
    platform: str,
    language_code: str = "ru",
) -> FlyerCheckResult:
    """
    Главная функция: проверить нужна ли подписка и если да — проверить её.

    Args:
        session: SQLAlchemy async session
        telegram_id: Telegram user ID
        platform: Платформа скачивания (для совместимости, не влияет на логику)
        language_code: Язык пользователя

    Returns:
        FlyerCheckResult с информацией о проверке
    """
    # Глобальный выключатель
    if FLYER_DISABLED:
        logger.debug(f"[FLYER] Disabled, allowing download for {telegram_id}")
        return FlyerCheckResult(allowed=True, flyer_required=False)

    try:
        # Проверяем нужна ли проверка для этого случая
        should_check = await should_check_subscription(session, telegram_id, platform)

        if not should_check:
            # Бесплатное скачивание (медовый месяц или не 10-е)
            return FlyerCheckResult(allowed=True, flyer_required=False)

        # Проверяем подписку через FlyerService
        is_subscribed = await check_subscription(telegram_id, language_code)

        if is_subscribed:
            # Юзер подписан — разрешаем без показа рекламы (тихая проверка)
            return FlyerCheckResult(allowed=True, flyer_required=True, flyer_shown=False)
        else:
            # Юзер НЕ подписан — FlyerAPI показал рекламу
            return FlyerCheckResult(allowed=False, flyer_required=True, flyer_shown=True)

    except Exception as e:
        # При ЛЮБОЙ ошибке — не блокируем юзера, логируем и пропускаем
        logger.error(f"[FLYER] Error in check_and_allow for {telegram_id}: {e}", exc_info=True)
        return FlyerCheckResult(allowed=True, flyer_required=False)
