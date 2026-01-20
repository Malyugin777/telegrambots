"""
Ops API endpoints - Phase A/B Telemetry MVP

Эндпоинты для мониторинга проходимости, скорости и стоимости по платформам и провайдерам.
Данные берутся из action_logs.details JSON.
"""
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..redis_client import get_redis
from ..models import ActionLog, ErrorLog, APISource
from ..auth import get_current_user

router = APIRouter()


# ============ Schemas ============

class PlatformStats(BaseModel):
    """Статистика по платформе"""
    platform: str
    total: int
    success: int
    errors: int
    success_rate: float  # 0-100%
    p95_total_ms: Optional[float] = None
    avg_speed_kbps: Optional[float] = None
    provider_share: dict  # {"ytdlp": 60, "rapidapi": 40}
    top_error_class: Optional[str] = None


class ProviderStats(BaseModel):
    """Статистика по провайдеру"""
    provider: str
    total: int
    success: int
    errors: int
    success_rate: float
    p95_total_ms: Optional[float] = None
    avg_speed_kbps: Optional[float] = None
    errors_by_class: dict  # {"HARD_KILL": 5, "STALL": 2}
    cooldown_status: Optional[str] = None  # "active" / "cooldown" / null


class QuotaInfo(BaseModel):
    """Информация о квоте API"""
    provider: str
    plan: str
    units_remaining: Optional[int] = None
    units_limit: Optional[int] = None
    requests_remaining: Optional[int] = None
    requests_limit: Optional[int] = None
    reset_hours: Optional[float] = None
    burn_rate_per_day: Optional[float] = None
    days_remaining: Optional[float] = None


class SystemMetrics(BaseModel):
    """Системные метрики"""
    cpu_percent: Optional[float] = None
    ram_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    tmp_size_mb: Optional[float] = None
    active_downloads: int = 0
    active_uploads: int = 0


class PlatformsResponse(BaseModel):
    """Ответ /ops/platforms"""
    range_hours: int
    platforms: List[PlatformStats]


class ProvidersResponse(BaseModel):
    """Ответ /ops/providers"""
    range_hours: int
    providers: List[ProviderStats]


class QuotaResponse(BaseModel):
    """Ответ /ops/quota"""
    updated_at: datetime
    apis: List[QuotaInfo]


class SystemResponse(BaseModel):
    """Ответ /ops/system"""
    timestamp: datetime
    metrics: SystemMetrics


# ============ Helper Functions ============

def parse_range(range_str: str) -> int:
    """Парсит range строку в часы: '24h' -> 24, '7d' -> 168"""
    if range_str.endswith('h'):
        return int(range_str[:-1])
    elif range_str.endswith('d'):
        return int(range_str[:-1]) * 24
    return 24  # default


def calculate_p95(values: List[float]) -> Optional[float]:
    """Вычисляет 95-й перцентиль"""
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * 0.95)
    return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 2)


# ============ Endpoints ============

@router.get("/platforms", response_model=PlatformsResponse)
async def get_platforms_stats(
    range: str = Query("24h", description="Time range: 24h, 7d, etc."),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    GET /api/v1/ops/platforms?range=24h

    Статистика по платформам: success_rate, p95_total_ms, provider_share, top_error_class
    """
    hours = parse_range(range)
    since = datetime.utcnow() - timedelta(hours=hours)

    # Получаем все download_success и download_error записи за период
    success_result = await db.execute(
        select(
            ActionLog.details,
            ActionLog.api_source,
            ActionLog.download_time_ms,
            ActionLog.download_speed_kbps
        ).where(
            ActionLog.created_at >= since,
            ActionLog.action == "download_success"
        )
    )

    error_result = await db.execute(
        select(ActionLog.details).where(
            ActionLog.created_at >= since,
            ActionLog.action == "download_error"
        )
    )

    # Группируем по платформам
    platform_data: dict = {}

    for row in success_result:
        details = row.details or {}
        platform = details.get("platform", "unknown")
        api_source = row.api_source.value if row.api_source else "unknown"

        if platform not in platform_data:
            platform_data[platform] = {
                "success": 0, "errors": 0,
                "times": [], "speeds": [],
                "providers": {}
            }

        platform_data[platform]["success"] += 1
        if row.download_time_ms:
            platform_data[platform]["times"].append(row.download_time_ms)
        if row.download_speed_kbps:
            platform_data[platform]["speeds"].append(row.download_speed_kbps)

        # Provider share
        platform_data[platform]["providers"][api_source] = \
            platform_data[platform]["providers"].get(api_source, 0) + 1

    for row in error_result:
        details = row[0] or {}
        platform = details.get("platform", "unknown")
        error_class = details.get("error_class", "UNKNOWN")

        if platform not in platform_data:
            platform_data[platform] = {
                "success": 0, "errors": 0,
                "times": [], "speeds": [],
                "providers": {}, "error_classes": {}
            }

        platform_data[platform]["errors"] += 1
        if "error_classes" not in platform_data[platform]:
            platform_data[platform]["error_classes"] = {}
        platform_data[platform]["error_classes"][error_class] = \
            platform_data[platform]["error_classes"].get(error_class, 0) + 1

    # Формируем ответ
    platforms = []
    for name, data in sorted(platform_data.items(), key=lambda x: -(x[1]["success"] + x[1]["errors"])):
        total = data["success"] + data["errors"]
        success_rate = round(data["success"] / total * 100, 1) if total > 0 else 0

        # Provider share в процентах
        provider_share = {}
        if data["providers"]:
            for prov, count in data["providers"].items():
                provider_share[prov] = round(count / data["success"] * 100, 1) if data["success"] > 0 else 0

        # Top error class
        error_classes = data.get("error_classes", {})
        top_error = max(error_classes.items(), key=lambda x: x[1])[0] if error_classes else None

        platforms.append(PlatformStats(
            platform=name,
            total=total,
            success=data["success"],
            errors=data["errors"],
            success_rate=success_rate,
            p95_total_ms=calculate_p95(data["times"]),
            avg_speed_kbps=round(sum(data["speeds"]) / len(data["speeds"]), 2) if data["speeds"] else None,
            provider_share=provider_share,
            top_error_class=top_error
        ))

    return PlatformsResponse(range_hours=hours, platforms=platforms)


@router.get("/providers", response_model=ProvidersResponse)
async def get_providers_stats(
    range: str = Query("24h", description="Time range: 24h, 7d, etc."),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    GET /api/v1/ops/providers?range=24h

    Статистика по провайдерам: success_rate, p95_total_ms, avg_speed, errors_by_class
    """
    hours = parse_range(range)
    since = datetime.utcnow() - timedelta(hours=hours)

    # Успешные загрузки по провайдерам
    success_result = await db.execute(
        select(
            ActionLog.api_source,
            ActionLog.download_time_ms,
            ActionLog.download_speed_kbps
        ).where(
            ActionLog.created_at >= since,
            ActionLog.action == "download_success",
            ActionLog.api_source.isnot(None)
        )
    )

    # Ошибки
    error_result = await db.execute(
        select(ActionLog.api_source, ActionLog.details).where(
            ActionLog.created_at >= since,
            ActionLog.action == "download_error"
        )
    )

    provider_data: dict = {}

    for row in success_result:
        provider = row.api_source.value if row.api_source else "unknown"

        if provider not in provider_data:
            provider_data[provider] = {
                "success": 0, "errors": 0,
                "times": [], "speeds": [],
                "error_classes": {}
            }

        provider_data[provider]["success"] += 1
        if row.download_time_ms:
            provider_data[provider]["times"].append(row.download_time_ms)
        if row.download_speed_kbps:
            provider_data[provider]["speeds"].append(row.download_speed_kbps)

    for row in error_result:
        provider = row.api_source.value if row.api_source else "unknown"
        details = row.details or {}
        error_class = details.get("error_class", "UNKNOWN")

        if provider not in provider_data:
            provider_data[provider] = {
                "success": 0, "errors": 0,
                "times": [], "speeds": [],
                "error_classes": {}
            }

        provider_data[provider]["errors"] += 1
        provider_data[provider]["error_classes"][error_class] = \
            provider_data[provider]["error_classes"].get(error_class, 0) + 1

    # Формируем ответ
    providers = []
    for name, data in sorted(provider_data.items(), key=lambda x: -(x[1]["success"] + x[1]["errors"])):
        total = data["success"] + data["errors"]
        success_rate = round(data["success"] / total * 100, 1) if total > 0 else 0

        providers.append(ProviderStats(
            provider=name,
            total=total,
            success=data["success"],
            errors=data["errors"],
            success_rate=success_rate,
            p95_total_ms=calculate_p95(data["times"]),
            avg_speed_kbps=round(sum(data["speeds"]) / len(data["speeds"]), 2) if data["speeds"] else None,
            errors_by_class=data["error_classes"],
            cooldown_status=None  # TODO: implement cooldown tracking
        ))

    return ProvidersResponse(range_hours=hours, providers=providers)


@router.get("/quota", response_model=QuotaResponse)
async def get_quota_status(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    GET /api/v1/ops/quota

    Текущий остаток квоты по API + прогноз дней.
    Данные берутся из последнего quota_snapshot в action_logs.details
    """
    # Ищем последнюю запись с quota_snapshot в details
    result = await db.execute(
        select(ActionLog.details, ActionLog.created_at)
        .where(
            ActionLog.action == "download_success",
            ActionLog.api_source == APISource.RAPIDAPI
        )
        .order_by(ActionLog.created_at.desc())
        .limit(1)
    )
    row = result.first()

    apis = []

    # Social Download All In One (для Instagram)
    apis.append(QuotaInfo(
        provider="social_download",
        plan="Basic (Free)",
        requests_remaining=None,  # TODO: track from headers
        requests_limit=100,
        reset_hours=None,
        burn_rate_per_day=None,
        days_remaining=None
    ))

    # SaveNow (для YouTube)
    # Пытаемся извлечь из последней записи
    if row and row.details:
        quota = row.details.get("quota_snapshot", {})
        units_remaining = quota.get("units_remaining")
        requests_remaining = quota.get("requests_remaining")

        # Считаем burn rate за вчера
        yesterday_start = datetime.utcnow().replace(hour=0, minute=0, second=0) - timedelta(days=1)
        yesterday_end = yesterday_start + timedelta(days=1)

        burn_result = await db.execute(
            select(func.count(ActionLog.id)).where(
                ActionLog.created_at >= yesterday_start,
                ActionLog.created_at < yesterday_end,
                ActionLog.action == "download_success",
                ActionLog.api_source == APISource.RAPIDAPI
            )
        )
        yesterday_count = burn_result.scalar() or 0

        days_remaining = None
        if units_remaining and yesterday_count > 0:
            days_remaining = round(units_remaining / yesterday_count, 1)

        apis.append(QuotaInfo(
            provider="savenow",
            plan="Basic (Free)" if (requests_remaining or 0) < 1000 else "Pro",
            units_remaining=units_remaining,
            units_limit=500,  # Daily limit for Basic
            requests_remaining=requests_remaining,
            reset_hours=24.0,
            burn_rate_per_day=float(yesterday_count) if yesterday_count else None,
            days_remaining=days_remaining
        ))
    else:
        apis.append(QuotaInfo(
            provider="savenow",
            plan="Unknown",
            units_remaining=None,
            units_limit=500,
            days_remaining=None
        ))

    return QuotaResponse(
        updated_at=datetime.utcnow(),
        apis=apis
    )


@router.get("/system", response_model=SystemResponse)
async def get_system_metrics(
    _=Depends(get_current_user),
):
    """
    GET /api/v1/ops/system

    Системные метрики: CPU, RAM, disk, /tmp size, active downloads/uploads.
    """
    metrics = SystemMetrics()

    # Пытаемся получить метрики из Redis (если бот их пишет)
    try:
        redis = await get_redis()

        # Active downloads/uploads counters
        downloads = await redis.get("counter:active_downloads")
        uploads = await redis.get("counter:active_uploads")

        metrics.active_downloads = int(downloads) if downloads else 0
        metrics.active_uploads = int(uploads) if uploads else 0

        # System metrics (если бот их пишет)
        cpu = await redis.get("system:cpu_percent")
        ram = await redis.get("system:ram_percent")
        disk = await redis.get("system:disk_percent")
        tmp_size = await redis.get("system:tmp_size_mb")

        if cpu:
            metrics.cpu_percent = float(cpu)
        if ram:
            metrics.ram_percent = float(ram)
        if disk:
            metrics.disk_percent = float(disk)
        if tmp_size:
            metrics.tmp_size_mb = float(tmp_size)

    except Exception:
        pass  # Redis unavailable

    return SystemResponse(
        timestamp=datetime.utcnow(),
        metrics=metrics
    )
