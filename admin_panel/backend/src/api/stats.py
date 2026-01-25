"""
Statistics API endpoints.
"""
from datetime import datetime, timedelta
import random
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..redis_client import get_redis
from ..config import settings
from ..models import Bot, User, Broadcast, ActionLog, BotStatus, BroadcastStatus, APISource
from ..schemas import StatsResponse, LoadChartResponse, ChartDataPoint, PerformanceResponse, PlatformPerformance, APIUsageResponse, APIUsageStats
from ..auth import get_current_user


class FlyerStatsResponse(BaseModel):
    """Статистика FlyerService."""
    # Сегодня
    downloads_today: int           # Все скачивания
    ad_offers_today: int           # Уникальные юзеры которым показали рекламу
    subscribed_today: int          # Подписались (flyer_sub_completed)

    # За всё время
    downloads_total: int
    ad_offers_total: int
    subscribed_total: int

router = APIRouter()


@router.get("", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get dashboard statistics."""
    # Total bots
    result = await db.execute(select(func.count(Bot.id)))
    total_bots = result.scalar() or 0

    # Active bots
    result = await db.execute(
        select(func.count(Bot.id)).where(Bot.status == BotStatus.ACTIVE)
    )
    active_bots = result.scalar() or 0

    # Total users
    result = await db.execute(select(func.count(User.id)))
    total_users = result.scalar() or 0

    # Active users today (DAU)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(User.id)).where(User.last_active_at >= today_start)
    )
    active_users_today = result.scalar() or 0

    # Downloads today
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.created_at >= today_start,
            ActionLog.action == "download_success"
        )
    )
    downloads_today = result.scalar() or 0

    # Total downloads
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.action == "download_success"
        )
    )
    total_downloads = result.scalar() or 0

    # Messages in queue (from Redis)
    try:
        redis = await get_redis()
        queue_length = await redis.llen("message_queue") or 0
    except Exception:
        queue_length = 0

    # Running broadcasts
    result = await db.execute(
        select(func.count(Broadcast.id)).where(Broadcast.status == BroadcastStatus.RUNNING)
    )
    broadcasts_running = result.scalar() or 0

    return StatsResponse(
        version=settings.version,
        total_bots=total_bots,
        active_bots=active_bots,
        total_users=total_users,
        active_users_today=active_users_today,
        downloads_today=downloads_today,
        total_downloads=total_downloads,
        messages_in_queue=queue_length,
        broadcasts_running=broadcasts_running,
    )


@router.get("/chart", response_model=LoadChartResponse)
async def get_load_chart(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Get load chart data for the last N days.
    Shows downloads and new users per day.
    Optimized: 2 queries instead of 14 (7 days × 2 metrics).
    """
    start_date = (datetime.utcnow() - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Downloads per day - single query with GROUP BY
    result = await db.execute(
        select(
            func.date(ActionLog.created_at).label("date"),
            func.count(ActionLog.id).label("count")
        )
        .where(
            ActionLog.created_at >= start_date,
            ActionLog.action == "download_success"
        )
        .group_by(func.date(ActionLog.created_at))
        .order_by(func.date(ActionLog.created_at))
    )
    downloads_map = {str(row.date): row.count for row in result}

    # New users per day - single query with GROUP BY
    result = await db.execute(
        select(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count")
        )
        .where(User.created_at >= start_date)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
    )
    users_map = {str(row.date): row.count for row in result}

    # Build response with all days (fill missing days with 0)
    downloads_data = []
    users_data = []

    for i in range(days - 1, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        date_str = day.strftime("%Y-%m-%d")

        downloads_data.append(ChartDataPoint(
            date=date_str,
            value=downloads_map.get(date_str, 0)
        ))
        users_data.append(ChartDataPoint(
            date=date_str,
            value=users_map.get(date_str, 0)
        ))

    return LoadChartResponse(
        messages=downloads_data,  # Renamed to downloads in frontend
        users=users_data,
    )


@router.get("/platforms")
async def get_platform_stats(
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Get download statistics by platform.
    Limited to last N days to prevent OOM (default 90 days).
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    # Try to use PostgreSQL JSON extraction for 'platform' field first
    # Then fall back to parsing 'info' field for older records
    result = await db.execute(
        select(ActionLog.details)
        .where(
            ActionLog.action == "download_success",
            ActionLog.created_at >= start_date
        )
    )

    platform_counts: dict[str, int] = {}
    for row in result:
        details = row[0]
        if not details or not isinstance(details, dict):
            continue

        # Try direct 'platform' field first (newer format)
        platform = details.get('platform')

        # Fall back to parsing 'info' field (older format)
        if not platform and 'info' in details:
            info = details['info']
            # Parse "video:instagram" -> "instagram"
            if ':' in info:
                platform = info.split(':')[-1]  # Get last part after ':'
            else:
                platform = info

        if platform:
            platform_counts[platform] = platform_counts.get(platform, 0) + 1

    return {
        "platforms": [
            {"name": name, "count": count}
            for name, count in sorted(platform_counts.items(), key=lambda x: -x[1])
        ]
    }


@router.get("/performance", response_model=PerformanceResponse)
async def get_performance_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Get performance metrics (download time, file size, speed) by platform.
    Limited to last N days to prevent OOM (default 30 days).
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    # Overall metrics (last N days)
    result = await db.execute(
        select(
            func.avg(ActionLog.download_time_ms).label('avg_time'),
            func.avg(ActionLog.file_size_bytes).label('avg_size'),
            func.avg(ActionLog.download_speed_kbps).label('avg_speed'),
            func.count(ActionLog.id).label('total')
        ).where(
            ActionLog.action == "download_success",
            ActionLog.download_time_ms.isnot(None),
            ActionLog.created_at >= start_date
        )
    )
    row = result.first()

    overall = PlatformPerformance(
        platform="overall",
        avg_download_time_ms=round(row.avg_time, 2) if row.avg_time else None,
        avg_file_size_mb=round(row.avg_size / 1024 / 1024, 2) if row.avg_size else None,
        avg_speed_kbps=round(row.avg_speed, 2) if row.avg_speed else None,
        total_downloads=row.total or 0
    )

    # Per-platform metrics (last N days)
    result = await db.execute(
        select(
            ActionLog.details,
            ActionLog.download_time_ms,
            ActionLog.file_size_bytes,
            ActionLog.download_speed_kbps
        ).where(
            ActionLog.action == "download_success",
            ActionLog.download_time_ms.isnot(None),
            ActionLog.created_at >= start_date
        )
    )

    platform_metrics: dict[str, dict] = {}
    for row in result:
        details = row.details
        if not details or not isinstance(details, dict):
            continue

        # Try direct 'platform' field first (newer format)
        platform = details.get('platform')

        # Fall back to parsing 'info' field (older format)
        if not platform and 'info' in details:
            info = details['info']
            if ':' in info:
                parts = info.split(':')
                platform = parts[1] if parts[1] not in ['http', 'https'] else parts[0]
            else:
                platform = info

        if not platform:
            continue

        if platform not in platform_metrics:
            platform_metrics[platform] = {
                'time': [],
                'size': [],
                'speed': [],
                'total': 0
            }

        platform_metrics[platform]['time'].append(row.download_time_ms or 0)
        platform_metrics[platform]['size'].append(row.file_size_bytes or 0)
        platform_metrics[platform]['speed'].append(row.download_speed_kbps or 0)
        platform_metrics[platform]['total'] += 1

    platforms = []
    for name, metrics in sorted(platform_metrics.items(), key=lambda x: -x[1]['total']):
        avg_time = sum(metrics['time']) / len(metrics['time']) if metrics['time'] else None
        avg_size = sum(metrics['size']) / len(metrics['size']) if metrics['size'] else None
        avg_speed = sum(metrics['speed']) / len(metrics['speed']) if metrics['speed'] else None

        platforms.append(PlatformPerformance(
            platform=name,
            avg_download_time_ms=round(avg_time, 2) if avg_time else None,
            avg_file_size_mb=round(avg_size / 1024 / 1024, 2) if avg_size else None,
            avg_speed_kbps=round(avg_speed, 2) if avg_speed else None,
            total_downloads=metrics['total']
        ))

    return PerformanceResponse(
        overall=overall,
        platforms=platforms
    )


@router.get("/api-usage", response_model=APIUsageResponse)
async def get_api_usage(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Get API usage statistics (RapidAPI, yt-dlp, Cobalt).
    Optimized: 2 queries instead of 6.
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Today's usage - single query with GROUP BY
    result = await db.execute(
        select(
            ActionLog.api_source,
            func.count(ActionLog.id).label("count")
        )
        .where(
            ActionLog.created_at >= today_start,
            ActionLog.action == "download_success",
            ActionLog.api_source.isnot(None)
        )
        .group_by(ActionLog.api_source)
    )
    today_counts = {row.api_source: row.count for row in result}

    # Month's usage - single query with GROUP BY
    result = await db.execute(
        select(
            ActionLog.api_source,
            func.count(ActionLog.id).label("count")
        )
        .where(
            ActionLog.created_at >= month_start,
            ActionLog.action == "download_success",
            ActionLog.api_source.isnot(None)
        )
        .group_by(ActionLog.api_source)
    )
    month_counts = {row.api_source: row.count for row in result}

    # Extract counts for each API
    rapidapi_today = today_counts.get(APISource.RAPIDAPI, 0)
    rapidapi_month = month_counts.get(APISource.RAPIDAPI, 0)
    ytdlp_today = today_counts.get(APISource.YTDLP, 0)
    ytdlp_month = month_counts.get(APISource.YTDLP, 0)
    cobalt_today = today_counts.get(APISource.COBALT, 0)
    cobalt_month = month_counts.get(APISource.COBALT, 0)

    # RapidAPI limit: 6000 per month (hardcoded for now)
    rapidapi_limit = 6000

    return APIUsageResponse(
        rapidapi=APIUsageStats(
            today=rapidapi_today,
            month=rapidapi_month,
            limit=rapidapi_limit
        ),
        ytdlp=APIUsageStats(
            today=ytdlp_today,
            month=ytdlp_month,
            limit=None  # No limit for yt-dlp
        ),
        cobalt=APIUsageStats(
            today=cobalt_today,
            month=cobalt_month,
            limit=None  # No limit for Cobalt
        ) if (cobalt_today > 0 or cobalt_month > 0) else None
    )


@router.get("/flyer", response_model=FlyerStatsResponse)
async def get_flyer_stats(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Статистика FlyerService.
    - downloads: все скачивания
    - ad_offers: уникальные юзеры которым показали рекламу
    - subscribed: кто подписался через FlyerService
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # === 1. Скачивания (всего) ===
    result = await db.execute(
        select(
            func.count(ActionLog.id).filter(ActionLog.created_at >= today_start).label("today"),
            func.count(ActionLog.id).label("total")
        )
        .where(ActionLog.action == "download_success")
    )
    row = result.first()
    downloads_today = row.today or 0
    downloads_total = row.total or 0

    # === 2. Предложения рекламы (УНИКАЛЬНЫЕ юзеры) ===
    result = await db.execute(
        select(
            func.count(func.distinct(ActionLog.user_id)).filter(ActionLog.created_at >= today_start).label("today"),
            func.count(func.distinct(ActionLog.user_id)).label("total")
        )
        .where(ActionLog.action == "flyer_ad_shown")
    )
    row = result.first()
    ad_offers_today = row.today or 0
    ad_offers_total = row.total or 0

    # === 3. Подписки (flyer_sub_completed) ===
    result = await db.execute(
        select(
            func.count(ActionLog.id).filter(ActionLog.created_at >= today_start).label("today"),
            func.count(ActionLog.id).label("total")
        )
        .where(ActionLog.action == "flyer_sub_completed")
    )
    row = result.first()
    subscribed_today = row.today or 0
    subscribed_total = row.total or 0

    return FlyerStatsResponse(
        downloads_today=downloads_today,
        ad_offers_today=ad_offers_today,
        subscribed_today=subscribed_today,
        downloads_total=downloads_total,
        ad_offers_total=ad_offers_total,
        subscribed_total=subscribed_total,
    )
