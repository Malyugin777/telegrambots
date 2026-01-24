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
    """Статистика по платформе (или платформа+bucket)"""
    platform: str
    bucket: Optional[str] = None  # shorts/full, reel/post/story/carousel, video, photo
    total: int
    success: int
    errors: int
    success_rate: float  # 0-100%
    # P95 breakdown по стадиям
    p95_total_ms: Optional[float] = None
    p95_prep_ms: Optional[float] = None      # job creation + polling
    p95_download_ms: Optional[float] = None  # file download time
    p95_upload_ms: Optional[float] = None    # Telegram upload time
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
    # Provider state management
    enabled: bool = True
    cooldown_until: Optional[datetime] = None
    health: str = "healthy"  # healthy / degraded / down
    # CDN vs direct host analysis
    download_host_share: dict = {}  # {"googlevideo.com": 30, "cdn.savenow.io": 70}
    top_hosts: List[str] = []  # топ-3 хоста
    # Last activity (for debugging)
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_class: Optional[str] = None


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
    # RAM
    ram_percent: Optional[float] = None
    ram_used_bytes: Optional[int] = None
    ram_total_bytes: Optional[int] = None
    # Disk
    disk_percent: Optional[float] = None
    disk_used_bytes: Optional[int] = None
    disk_total_bytes: Optional[int] = None
    # /tmp
    tmp_used_bytes: Optional[int] = None
    # Active operations
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
    group_by: str = Query("platform", description="Группировка: platform или bucket"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    GET /api/v1/ops/platforms?range=24h&group_by=platform

    Статистика по платформам или подтипам (bucket):
    - group_by=platform: youtube, instagram, tiktok, pinterest
    - group_by=bucket: youtube:shorts, youtube:full, instagram:reel, etc.

    Limited to 10000 records to prevent OOM.
    """
    hours = parse_range(range)
    since = datetime.utcnow() - timedelta(hours=hours)
    use_bucket = group_by == "bucket"

    # Limit records to prevent OOM (10k should be enough for statistics)
    MAX_RECORDS = 10000

    # Получаем download_success записи за период (с лимитом)
    success_result = await db.execute(
        select(
            ActionLog.details,
            ActionLog.api_source,
            ActionLog.download_time_ms,
            ActionLog.download_speed_kbps
        ).where(
            ActionLog.created_at >= since,
            ActionLog.action == "download_success"
        ).order_by(ActionLog.created_at.desc()).limit(MAX_RECORDS)
    )

    error_result = await db.execute(
        select(ActionLog.details).where(
            ActionLog.created_at >= since,
            ActionLog.action == "download_error"
        ).order_by(ActionLog.created_at.desc()).limit(MAX_RECORDS)
    )

    # Группируем по платформам (или platform:bucket)
    platform_data: dict = {}

    def get_key(details: dict) -> tuple:
        """Возвращает ключ группировки: (platform, bucket) или (platform, None)"""
        platform = details.get("platform", "unknown")
        bucket = details.get("bucket") if use_bucket else None
        return (platform, bucket)

    for row in success_result:
        details = row.details or {}
        key = get_key(details)
        api_source = row.api_source.value if row.api_source else "unknown"

        if key not in platform_data:
            platform_data[key] = {
                "success": 0, "errors": 0,
                "times": [], "speeds": [],
                "prep_times": [], "download_times": [], "upload_times": [],
                "providers": {}, "error_classes": {}
            }

        platform_data[key]["success"] += 1
        if row.download_time_ms:
            platform_data[key]["times"].append(row.download_time_ms)
        if row.download_speed_kbps:
            platform_data[key]["speeds"].append(row.download_speed_kbps)

        # P95 breakdown: prep_ms, download_ms, upload_ms из details
        if details.get("prep_ms"):
            platform_data[key]["prep_times"].append(details["prep_ms"])
        if details.get("download_ms"):
            platform_data[key]["download_times"].append(details["download_ms"])
        if details.get("upload_ms"):
            platform_data[key]["upload_times"].append(details["upload_ms"])

        # Provider share
        platform_data[key]["providers"][api_source] = \
            platform_data[key]["providers"].get(api_source, 0) + 1

    for row in error_result:
        details = row[0] or {}
        key = get_key(details)
        error_class = details.get("error_class", "UNKNOWN")

        if key not in platform_data:
            platform_data[key] = {
                "success": 0, "errors": 0,
                "times": [], "speeds": [],
                "prep_times": [], "download_times": [], "upload_times": [],
                "providers": {}, "error_classes": {}
            }

        platform_data[key]["errors"] += 1
        platform_data[key]["error_classes"][error_class] = \
            platform_data[key]["error_classes"].get(error_class, 0) + 1

    # Формируем ответ
    platforms = []
    for (platform, bucket), data in sorted(
        platform_data.items(),
        key=lambda x: -(x[1]["success"] + x[1]["errors"])
    ):
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
            platform=platform,
            bucket=bucket,
            total=total,
            success=data["success"],
            errors=data["errors"],
            success_rate=success_rate,
            p95_total_ms=calculate_p95(data["times"]),
            p95_prep_ms=calculate_p95(data.get("prep_times", [])),
            p95_download_ms=calculate_p95(data.get("download_times", [])),
            p95_upload_ms=calculate_p95(data.get("upload_times", [])),
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
    Limited to 10000 records to prevent OOM.
    """
    hours = parse_range(range)
    since = datetime.utcnow() - timedelta(hours=hours)

    # Limit records to prevent OOM
    MAX_RECORDS = 10000

    # Успешные загрузки по провайдерам
    success_result = await db.execute(
        select(
            ActionLog.api_source,
            ActionLog.download_time_ms,
            ActionLog.download_speed_kbps,
            ActionLog.details,
            ActionLog.created_at
        ).where(
            ActionLog.created_at >= since,
            ActionLog.action == "download_success",
            ActionLog.api_source.isnot(None)
        ).order_by(ActionLog.created_at.desc()).limit(MAX_RECORDS)
    )

    # Ошибки
    error_result = await db.execute(
        select(
            ActionLog.api_source,
            ActionLog.details,
            ActionLog.created_at
        ).where(
            ActionLog.created_at >= since,
            ActionLog.action == "download_error"
        ).order_by(ActionLog.created_at.desc()).limit(MAX_RECORDS)
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
                "hosts": {},  # download_host tracking
                "last_success_at": None,
                "last_error_at": None,
                "last_error_class": None
            }

        provider_data[provider]["success"] += 1
        if row.download_time_ms:
            provider_data[provider]["times"].append(row.download_time_ms)
        if row.download_speed_kbps:
            provider_data[provider]["speeds"].append(row.download_speed_kbps)

        # Track last success (первая запись = последняя по времени, т.к. ORDER BY desc)
        if provider_data[provider]["last_success_at"] is None:
            provider_data[provider]["last_success_at"] = row.created_at

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
                "error_classes": {},
                "hosts": {},
                "last_success_at": None,
                "last_error_at": None,
                "last_error_class": None
            }

        provider_data[provider]["errors"] += 1
        provider_data[provider]["error_classes"][error_class] = \
            provider_data[provider]["error_classes"].get(error_class, 0) + 1

        # Track last error (первая запись = последняя по времени)
        if provider_data[provider]["last_error_at"] is None:
            provider_data[provider]["last_error_at"] = row.created_at
            provider_data[provider]["last_error_class"] = error_class

    # Получаем состояние провайдеров из Redis
    redis = await get_redis()
    provider_states = {}
    for provider_name in ["ytdlp", "rapidapi", "pytubefix", "savenow", "instaloader", "cobalt"]:
        enabled = await redis.get(f"provider:{provider_name}:enabled")
        cooldown = await redis.get(f"provider:{provider_name}:cooldown_until")
        provider_states[provider_name] = {
            "enabled": enabled != "false" if enabled else True,
            "cooldown_until": datetime.fromisoformat(cooldown) if cooldown else None
        }

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

        # Provider state from Redis
        state = provider_states.get(name, {"enabled": True, "cooldown_until": None})

        # Health based on success rate
        if success_rate >= 90:
            health = "healthy"
        elif success_rate >= 70:
            health = "degraded"
        else:
            health = "down"

        # If in cooldown, mark as degraded
        if state["cooldown_until"] and state["cooldown_until"] > datetime.utcnow():
            health = "degraded"

        providers.append(ProviderStats(
            provider=name,
            total=total,
            success=data["success"],
            errors=data["errors"],
            success_rate=success_rate,
            p95_total_ms=calculate_p95(data["times"]),
            avg_speed_kbps=round(sum(data["speeds"]) / len(data["speeds"]), 2) if data["speeds"] else None,
            errors_by_class=data.get("error_classes", {}),
            enabled=state["enabled"],
            cooldown_until=state["cooldown_until"],
            health=health,
            download_host_share=download_host_share,
            top_hosts=top_hosts,
            last_success_at=data.get("last_success_at"),
            last_error_at=data.get("last_error_at"),
            last_error_class=data.get("last_error_class")
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
    Optimized: Combined COUNT queries.
    """
    import os

    # Лимиты из env (или defaults для Pro плана)
    SOCIAL_REQUESTS_LIMIT = int(os.getenv("RAPIDAPI_SOCIAL_REQUESTS_LIMIT", "6000"))
    SOCIAL_PLAN_NAME = os.getenv("RAPIDAPI_SOCIAL_PLAN_NAME", "Pro")
    SAVENOW_UNITS_LIMIT = int(os.getenv("SAVENOW_UNITS_LIMIT", "100000"))
    SAVENOW_PLAN_NAME = os.getenv("SAVENOW_PLAN_NAME", "Pro")

    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    apis = []

    # === Combined query for RAPIDAPI burn rates ===
    # Single query with conditional counts instead of 3 separate queries
    result = await db.execute(
        select(
            func.count(ActionLog.id).filter(ActionLog.created_at >= since_24h).label("burn_24h"),
            func.count(ActionLog.id).filter(ActionLog.created_at >= since_7d).label("burn_7d"),
            func.count(ActionLog.id).filter(ActionLog.created_at >= month_start).label("month_usage")
        )
        .where(
            ActionLog.action == "download_success",
            ActionLog.api_source == APISource.RAPIDAPI
        )
    )
    row = result.first()
    social_burn_24h = row.burn_24h or 0
    social_burn_7d = row.burn_7d or 0
    social_month_usage = row.month_usage or 0
    social_burn_rate_7d = round(social_burn_7d / 7, 1) if social_burn_7d else None

    # === Get latest quota info from RAPIDAPI ===
    social_result = await db.execute(
        select(ActionLog.details)
        .where(
            ActionLog.action == "download_success",
            ActionLog.api_source == APISource.RAPIDAPI
        )
        .order_by(ActionLog.created_at.desc())
        .limit(1)
    )
    social_row = social_result.first()

    social_remaining = None
    social_limit = None
    social_reset = None

    if social_row and social_row.details:
        quota = social_row.details.get("quota") or {}
        social_remaining = quota.get("requests_remaining") if quota else None
        social_limit = quota.get("requests_limit") if quota else None
        social_reset = quota.get("requests_reset_sec") if quota else None

    # Если API не отдаёт remaining - вычисляем из базы
    if social_remaining is None and social_month_usage > 0:
        limit = social_limit or SOCIAL_REQUESTS_LIMIT
        social_remaining = max(0, limit - social_month_usage)

    # Forecasts для Social Download
    social_forecast_avg = None
    social_forecast_pess = None
    effective_remaining = social_remaining if social_remaining is not None else (
        (social_limit or SOCIAL_REQUESTS_LIMIT) - social_burn_24h if social_burn_24h else None
    )
    if effective_remaining and social_burn_24h > 0:
        social_forecast_avg = round(effective_remaining / social_burn_24h, 1)
        worst_hour = social_burn_24h / 24 * 2
        if worst_hour > 0:
            social_forecast_pess = round(effective_remaining / (worst_hour * 24), 1)

    apis.append(QuotaInfo(
        provider="social_download",
        plan=SOCIAL_PLAN_NAME,
        requests_remaining=social_remaining,
        requests_limit=social_limit or SOCIAL_REQUESTS_LIMIT,
        reset_hours=round(social_reset / 3600, 1) if social_reset else None,
        burn_rate_24h=float(social_burn_24h) if social_burn_24h else None,
        burn_rate_7d=social_burn_rate_7d,
        forecast_average=social_forecast_avg,
        forecast_pessimistic=social_forecast_pess
    ))

    # === 2. SaveNow / YouTube Info & Download API ===
    savenow_result = await db.execute(
        select(ActionLog.details)
        .where(
            ActionLog.action == "download_success",
            ActionLog.api_source == APISource.SAVENOW
        )
        .order_by(ActionLog.created_at.desc())
        .limit(1)
    )
    savenow_row = savenow_result.first()

    units_remaining = None
    units_reset = None

    if savenow_row and savenow_row.details:
        quota = savenow_row.details.get("quota") or {}
        units_remaining = quota.get("units_remaining") if quota else None
        units_reset = quota.get("units_reset_sec") if quota else None

    # Для SaveNow: used = limit - remaining
    units_used_month = None
    if units_remaining is not None:
        units_used_month = SAVENOW_UNITS_LIMIT - units_remaining

    savenow_current_percent = None
    if units_used_month is not None:
        savenow_current_percent = round((units_used_month / SAVENOW_UNITS_LIMIT) * 100, 2)

    apis.append(QuotaInfo(
        provider="savenow",
        plan=SAVENOW_PLAN_NAME,
        units_remaining=units_remaining,
        units_limit=SAVENOW_UNITS_LIMIT,
        requests_remaining=None,
        reset_hours=round(units_reset / 3600, 1) if units_reset else None,
        burn_rate_24h=float(units_used_month) if units_used_month else None,
        burn_rate_7d=None,
        forecast_average=savenow_current_percent,
        forecast_pessimistic=None
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

        # System metrics (бот пишет их каждые 30 секунд)
        cpu = await redis.get("system:cpu_percent")
        ram_percent = await redis.get("system:ram_percent")
        ram_used = await redis.get("system:ram_used_bytes")
        ram_total = await redis.get("system:ram_total_bytes")
        disk_percent = await redis.get("system:disk_percent")
        disk_used = await redis.get("system:disk_used_bytes")
        disk_total = await redis.get("system:disk_total_bytes")
        tmp_used = await redis.get("system:tmp_used_bytes")

        if cpu:
            metrics.cpu_percent = float(cpu)
        if ram_percent:
            metrics.ram_percent = float(ram_percent)
        if ram_used:
            metrics.ram_used_bytes = int(ram_used)
        if ram_total:
            metrics.ram_total_bytes = int(ram_total)
        if disk_percent:
            metrics.disk_percent = float(disk_percent)
        if disk_used:
            metrics.disk_used_bytes = int(disk_used)
        if disk_total:
            metrics.disk_total_bytes = int(disk_total)
        if tmp_used:
            metrics.tmp_used_bytes = int(tmp_used)

    except Exception:
        pass  # Redis unavailable

    return SystemResponse(
        timestamp=datetime.utcnow(),
        metrics=metrics
    )


# ============ Provider State Management ============

class ProviderStateResponse(BaseModel):
    """Ответ на изменение состояния провайдера"""
    provider: str
    enabled: bool
    cooldown_until: Optional[datetime] = None
    message: str


@router.post("/providers/{provider}/enable", response_model=ProviderStateResponse)
async def enable_provider(
    provider: str,
    _=Depends(get_current_user),
):
    """
    POST /api/v1/ops/providers/{provider}/enable

    Включить провайдер (убрать cooldown и пометить enabled=true)
    """
    redis = await get_redis()

    await redis.set(f"provider:{provider}:enabled", "true")
    await redis.delete(f"provider:{provider}:cooldown_until")

    return ProviderStateResponse(
        provider=provider,
        enabled=True,
        cooldown_until=None,
        message=f"Provider {provider} enabled"
    )


@router.post("/providers/{provider}/disable", response_model=ProviderStateResponse)
async def disable_provider(
    provider: str,
    _=Depends(get_current_user),
):
    """
    POST /api/v1/ops/providers/{provider}/disable

    Отключить провайдер (enabled=false)
    """
    redis = await get_redis()

    await redis.set(f"provider:{provider}:enabled", "false")

    return ProviderStateResponse(
        provider=provider,
        enabled=False,
        cooldown_until=None,
        message=f"Provider {provider} disabled"
    )


@router.post("/providers/{provider}/cooldown", response_model=ProviderStateResponse)
async def set_provider_cooldown(
    provider: str,
    minutes: int = Query(30, description="Cooldown в минутах"),
    _=Depends(get_current_user),
):
    """
    POST /api/v1/ops/providers/{provider}/cooldown?minutes=30

    Установить cooldown для провайдера (временное отключение)
    """
    redis = await get_redis()

    until = datetime.utcnow() + timedelta(minutes=minutes)
    await redis.set(f"provider:{provider}:cooldown_until", until.isoformat())
    await redis.expire(f"provider:{provider}:cooldown_until", minutes * 60)

    return ProviderStateResponse(
        provider=provider,
        enabled=True,
        cooldown_until=until,
        message=f"Provider {provider} in cooldown until {until.isoformat()}"
    )


# ============ Routing Management ============

# Дефолтные chains для каждого источника (fallback если нет в Redis)
DEFAULT_ROUTING = {
    "youtube_full": ["ytdlp", "pytubefix", "savenow"],
    "youtube_shorts": ["ytdlp", "pytubefix", "savenow"],
    "instagram_reel": ["rapidapi"],
    "instagram_post": ["rapidapi"],
    "instagram_story": ["rapidapi"],
    "instagram_carousel": ["rapidapi"],
    "tiktok": ["ytdlp", "rapidapi"],
    "pinterest": ["ytdlp", "rapidapi"],
}

# Доступные провайдеры для каждого источника
AVAILABLE_PROVIDERS = {
    "youtube_full": ["ytdlp", "pytubefix", "savenow"],
    "youtube_shorts": ["ytdlp", "pytubefix", "savenow"],
    "instagram_reel": ["rapidapi", "ytdlp"],
    "instagram_post": ["rapidapi", "ytdlp"],
    "instagram_story": ["rapidapi"],
    "instagram_carousel": ["rapidapi"],
    "tiktok": ["ytdlp", "rapidapi"],
    "pinterest": ["ytdlp", "rapidapi"],
}


class ProviderConfig(BaseModel):
    """Конфиг провайдера в chain"""
    name: str
    enabled: bool = True
    timeout_sec: int = 60


class RoutingConfig(BaseModel):
    """Конфиг роутинга для источника"""
    source: str
    chain: List[ProviderConfig]
    available_providers: List[str]
    has_override: bool = False
    override_expires_at: Optional[datetime] = None


class RoutingListResponse(BaseModel):
    """Ответ со списком всех routing configs"""
    sources: List[RoutingConfig]


class RoutingSaveRequest(BaseModel):
    """Запрос на сохранение routing"""
    chain: List[ProviderConfig]


class RoutingOverrideRequest(BaseModel):
    """Запрос на override routing"""
    chain: List[str]  # просто список имён провайдеров
    minutes: int = 30


@router.get("/routing", response_model=RoutingListResponse)
async def get_all_routing(
    _=Depends(get_current_user),
):
    """
    GET /api/v1/ops/routing

    Получить routing configs для всех источников
    """
    import json
    redis = await get_redis()
    sources = []

    for source, default_chain in DEFAULT_ROUTING.items():
        # Читаем chain из Redis
        chain_json = await redis.get(f"routing:{source}")
        if chain_json:
            chain_data = json.loads(chain_json)
        else:
            # Дефолтный chain
            chain_data = [{"name": p, "enabled": True, "timeout_sec": 60} for p in default_chain]

        # Проверяем override
        override_json = await redis.get(f"routing_override:{source}")
        has_override = False
        override_expires = None
        if override_json:
            override_data = json.loads(override_json)
            expires_at = datetime.fromisoformat(override_data["expires_at"])
            if expires_at > datetime.utcnow():
                has_override = True
                override_expires = expires_at
                # При активном override показываем его chain
                chain_data = [{"name": p, "enabled": True, "timeout_sec": 60} for p in override_data["chain"]]

        sources.append(RoutingConfig(
            source=source,
            chain=[ProviderConfig(**p) if isinstance(p, dict) else ProviderConfig(name=p) for p in chain_data],
            available_providers=AVAILABLE_PROVIDERS.get(source, []),
            has_override=has_override,
            override_expires_at=override_expires
        ))

    return RoutingListResponse(sources=sources)


@router.get("/routing/{source}", response_model=RoutingConfig)
async def get_routing(
    source: str,
    _=Depends(get_current_user),
):
    """
    GET /api/v1/ops/routing/{source}

    Получить routing config для конкретного источника
    """
    import json

    if source not in DEFAULT_ROUTING:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown source: {source}")

    redis = await get_redis()

    # Читаем chain из Redis
    chain_json = await redis.get(f"routing:{source}")
    if chain_json:
        chain_data = json.loads(chain_json)
    else:
        chain_data = [{"name": p, "enabled": True, "timeout_sec": 60} for p in DEFAULT_ROUTING[source]]

    # Проверяем override
    override_json = await redis.get(f"routing_override:{source}")
    has_override = False
    override_expires = None
    if override_json:
        override_data = json.loads(override_json)
        expires_at = datetime.fromisoformat(override_data["expires_at"])
        if expires_at > datetime.utcnow():
            has_override = True
            override_expires = expires_at
            chain_data = [{"name": p, "enabled": True, "timeout_sec": 60} for p in override_data["chain"]]

    return RoutingConfig(
        source=source,
        chain=[ProviderConfig(**p) if isinstance(p, dict) else ProviderConfig(name=p) for p in chain_data],
        available_providers=AVAILABLE_PROVIDERS.get(source, []),
        has_override=has_override,
        override_expires_at=override_expires
    )


@router.post("/routing/{source}")
async def save_routing(
    source: str,
    request: RoutingSaveRequest,
    _=Depends(get_current_user),
):
    """
    POST /api/v1/ops/routing/{source}

    Сохранить routing config для источника
    """
    import json

    if source not in DEFAULT_ROUTING:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown source: {source}")

    redis = await get_redis()

    # Сохраняем chain
    chain_data = [{"name": p.name, "enabled": p.enabled, "timeout_sec": p.timeout_sec} for p in request.chain]
    await redis.set(f"routing:{source}", json.dumps(chain_data))

    return {"status": "ok", "source": source, "chain": chain_data}


@router.delete("/routing/{source}")
async def reset_routing(
    source: str,
    _=Depends(get_current_user),
):
    """
    DELETE /api/v1/ops/routing/{source}

    Сбросить routing на дефолтный
    """
    if source not in DEFAULT_ROUTING:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown source: {source}")

    redis = await get_redis()
    await redis.delete(f"routing:{source}")
    await redis.delete(f"routing_override:{source}")

    return {"status": "ok", "source": source, "message": "Reset to default"}


@router.post("/routing/{source}/override")
async def set_routing_override(
    source: str,
    request: RoutingOverrideRequest,
    _=Depends(get_current_user),
):
    """
    POST /api/v1/ops/routing/{source}/override

    Установить временный override routing (например, "только SaveNow на 30 минут")
    """
    import json

    if source not in DEFAULT_ROUTING:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown source: {source}")

    redis = await get_redis()

    expires_at = datetime.utcnow() + timedelta(minutes=request.minutes)
    override_data = {
        "chain": request.chain,
        "expires_at": expires_at.isoformat()
    }

    await redis.set(f"routing_override:{source}", json.dumps(override_data))
    await redis.expire(f"routing_override:{source}", request.minutes * 60)

    return {
        "status": "ok",
        "source": source,
        "chain": request.chain,
        "expires_at": expires_at.isoformat(),
        "message": f"Override set for {request.minutes} minutes"
    }


@router.delete("/routing/{source}/override")
async def clear_routing_override(
    source: str,
    _=Depends(get_current_user),
):
    """
    DELETE /api/v1/ops/routing/{source}/override

    Снять override routing
    """
    if source not in DEFAULT_ROUTING:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown source: {source}")

    redis = await get_redis()
    await redis.delete(f"routing_override:{source}")

    return {"status": "ok", "source": source, "message": "Override cleared"}
