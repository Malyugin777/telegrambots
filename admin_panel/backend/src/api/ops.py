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
from ..models import ActionLog, APISource
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
    # P95 breakdown по стадиям
    p95_total_ms: Optional[float] = None
    p95_prep_ms: Optional[float] = None      # job creation + polling
    p95_download_ms: Optional[float] = None  # file download time
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
    # CDN vs direct host analysis
    download_host_share: dict = {}  # {"googlevideo.com": 30, "cdn.savenow.io": 70}
    top_hosts: List[str] = []  # топ-3 хоста


class QuotaInfo(BaseModel):
    """Информация о квоте API"""
    provider: str
    plan: str
    units_remaining: Optional[int] = None
    units_limit: Optional[int] = None
    requests_remaining: Optional[int] = None
    requests_limit: Optional[int] = None
    reset_hours: Optional[float] = None
    # Burn rates по периодам
    burn_rate_24h: Optional[float] = None  # req/day за последние 24h
    burn_rate_7d: Optional[float] = None   # avg req/day за 7 дней
    # Прогнозы
    forecast_pessimistic: Optional[float] = None  # дней по worst hour * 24
    forecast_average: Optional[float] = None      # дней по среднему 24h


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
                "prep_times": [], "download_times": [],  # P95 breakdown
                "providers": {}
            }

        platform_data[platform]["success"] += 1
        if row.download_time_ms:
            platform_data[platform]["times"].append(row.download_time_ms)
        if row.download_speed_kbps:
            platform_data[platform]["speeds"].append(row.download_speed_kbps)

        # P95 breakdown: prep_ms и download_ms из details
        if details.get("prep_ms"):
            platform_data[platform]["prep_times"].append(details["prep_ms"])
        if details.get("download_ms"):
            platform_data[platform]["download_times"].append(details["download_ms"])

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
            p95_prep_ms=calculate_p95(data.get("prep_times", [])),
            p95_download_ms=calculate_p95(data.get("download_times", [])),
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

    # Успешные загрузки по провайдерам (включая details для download_host)
    success_result = await db.execute(
        select(
            ActionLog.api_source,
            ActionLog.download_time_ms,
            ActionLog.download_speed_kbps,
            ActionLog.details
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
        details = row.details or {}

        if provider not in provider_data:
            provider_data[provider] = {
                "success": 0, "errors": 0,
                "times": [], "speeds": [],
                "error_classes": {},
                "hosts": {}  # download_host tracking
            }

        provider_data[provider]["success"] += 1
        if row.download_time_ms:
            provider_data[provider]["times"].append(row.download_time_ms)
        if row.download_speed_kbps:
            provider_data[provider]["speeds"].append(row.download_speed_kbps)

        # Track download_host (CDN vs googlevideo detection)
        download_host = details.get("download_host")
        if download_host:
            provider_data[provider]["hosts"][download_host] = \
                provider_data[provider]["hosts"].get(download_host, 0) + 1

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

        # Download host share (% по каждому хосту)
        hosts = data.get("hosts", {})
        host_total = sum(hosts.values()) if hosts else 0
        download_host_share = {}
        for host, count in hosts.items():
            download_host_share[host] = round(count / host_total * 100, 1) if host_total > 0 else 0

        # Top-3 hosts
        top_hosts = sorted(hosts.items(), key=lambda x: -x[1])[:3]
        top_hosts = [h[0] for h in top_hosts]

        providers.append(ProviderStats(
            provider=name,
            total=total,
            success=data["success"],
            errors=data["errors"],
            success_rate=success_rate,
            p95_total_ms=calculate_p95(data["times"]),
            avg_speed_kbps=round(sum(data["speeds"]) / len(data["speeds"]), 2) if data["speeds"] else None,
            errors_by_class=data["error_classes"],
            cooldown_status=None,  # TODO: implement cooldown tracking
            download_host_share=download_host_share,
            top_hosts=top_hosts
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

        now = datetime.utcnow()

        # burn_rate_24h: запросы за последние 24 часа
        since_24h = now - timedelta(hours=24)
        burn_24h_result = await db.execute(
            select(func.count(ActionLog.id)).where(
                ActionLog.created_at >= since_24h,
                ActionLog.action == "download_success",
                ActionLog.api_source == APISource.RAPIDAPI
            )
        )
        burn_rate_24h = burn_24h_result.scalar() or 0

        # burn_rate_7d: среднее в день за 7 дней
        since_7d = now - timedelta(days=7)
        burn_7d_result = await db.execute(
            select(func.count(ActionLog.id)).where(
                ActionLog.created_at >= since_7d,
                ActionLog.action == "download_success",
                ActionLog.api_source == APISource.RAPIDAPI
            )
        )
        burn_7d_total = burn_7d_result.scalar() or 0
        burn_rate_7d = round(burn_7d_total / 7, 1) if burn_7d_total else None

        # worst_hour: максимум запросов за любой час в последние 24h (для pessimistic forecast)
        # Упрощенно: берем burn_rate_24h и умножаем на пик-фактор 2x
        worst_hour_rate = burn_rate_24h / 24 * 2 if burn_rate_24h else None

        # Forecasts
        forecast_average = None
        forecast_pessimistic = None
        if units_remaining:
            if burn_rate_24h > 0:
                forecast_average = round(units_remaining / burn_rate_24h, 1)
            if worst_hour_rate and worst_hour_rate > 0:
                # Pessimistic: если весь день будет как worst hour
                forecast_pessimistic = round(units_remaining / (worst_hour_rate * 24), 1)

        apis.append(QuotaInfo(
            provider="savenow",
            plan="Basic (Free)" if (requests_remaining or 0) < 1000 else "Pro",
            units_remaining=units_remaining,
            units_limit=500,  # Daily limit for Basic
            requests_remaining=requests_remaining,
            reset_hours=24.0,
            burn_rate_24h=float(burn_rate_24h) if burn_rate_24h else None,
            burn_rate_7d=burn_rate_7d,
            forecast_pessimistic=forecast_pessimistic,
            forecast_average=forecast_average
        ))
    else:
        apis.append(QuotaInfo(
            provider="savenow",
            plan="Unknown",
            units_remaining=None,
            units_limit=500
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
