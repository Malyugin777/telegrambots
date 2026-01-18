"""
Statistics API endpoints.
"""
from datetime import datetime, timedelta
import random

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..redis_client import get_redis
from ..config import settings
from ..models import Bot, User, Broadcast, ActionLog, BotStatus, BroadcastStatus
from ..schemas import StatsResponse, LoadChartResponse, ChartDataPoint, PerformanceResponse, PlatformPerformance
from ..auth import get_current_user

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
    """
    downloads_data = []
    users_data = []

    # Include today (i=0) through (days-1) days ago
    for i in range(days - 1, -1, -1):
        day_start = (datetime.utcnow() - timedelta(days=i)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_end = day_start + timedelta(days=1)
        date_str = day_start.strftime("%Y-%m-%d")

        # Downloads per day
        result = await db.execute(
            select(func.count(ActionLog.id)).where(
                ActionLog.created_at >= day_start,
                ActionLog.created_at < day_end,
                ActionLog.action == "download_success"
            )
        )
        downloads_count = result.scalar() or 0
        downloads_data.append(ChartDataPoint(date=date_str, value=downloads_count))

        # New users per day
        result = await db.execute(
            select(func.count(User.id)).where(
                User.created_at >= day_start,
                User.created_at < day_end
            )
        )
        users_count = result.scalar() or 0
        users_data.append(ChartDataPoint(date=date_str, value=users_count))

    return LoadChartResponse(
        messages=downloads_data,  # Renamed to downloads in frontend
        users=users_data,
    )


@router.get("/platforms")
async def get_platform_stats(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get download statistics by platform."""
    # Parse platform from details->info field
    # Format: {"info": "video:instagram"} or {"info": "instagram:https://..."}

    # Count downloads by parsing the info field
    result = await db.execute(
        select(ActionLog.details, func.count(ActionLog.id).label('count'))
        .where(ActionLog.action == "download_success")
        .group_by(ActionLog.details)
    )

    platform_counts: dict[str, int] = {}
    for row in result:
        details = row[0]
        count = row[1]
        if details and isinstance(details, dict) and 'info' in details:
            info = details['info']
            # Parse "video:instagram" -> "instagram"
            if ':' in info:
                platform = info.split(':')[-1]  # Get last part after ':'
            else:
                platform = info
            platform_counts[platform] = platform_counts.get(platform, 0) + count

    return {
        "platforms": [
            {"name": name, "count": count}
            for name, count in sorted(platform_counts.items(), key=lambda x: -x[1])
        ]
    }


@router.get("/performance", response_model=PerformanceResponse)
async def get_performance_stats(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get performance metrics (download time, file size, speed) by platform."""

    # Overall metrics
    result = await db.execute(
        select(
            func.avg(ActionLog.download_time_ms).label('avg_time'),
            func.avg(ActionLog.file_size_bytes).label('avg_size'),
            func.avg(ActionLog.download_speed_kbps).label('avg_speed'),
            func.count(ActionLog.id).label('total')
        ).where(
            ActionLog.action == "download_success",
            ActionLog.download_time_ms.isnot(None)
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

    # Per-platform metrics
    # Parse platform from details->info field
    result = await db.execute(
        select(
            ActionLog.details,
            func.avg(ActionLog.download_time_ms).label('avg_time'),
            func.avg(ActionLog.file_size_bytes).label('avg_size'),
            func.avg(ActionLog.download_speed_kbps).label('avg_speed'),
            func.count(ActionLog.id).label('total')
        ).where(
            ActionLog.action == "download_success",
            ActionLog.download_time_ms.isnot(None)
        ).group_by(ActionLog.details)
    )

    platform_metrics: dict[str, dict] = {}
    for row in result:
        details = row.details
        if details and isinstance(details, dict) and 'info' in details:
            info = details['info']
            # Parse "video:instagram" -> "instagram"
            if ':' in info:
                parts = info.split(':')
                # Handle both "video:instagram" and "instagram:url"
                platform = parts[1] if parts[1] not in ['http', 'https'] else parts[0]
            else:
                platform = info

            if platform not in platform_metrics:
                platform_metrics[platform] = {
                    'time': [],
                    'size': [],
                    'speed': [],
                    'total': 0
                }

            platform_metrics[platform]['time'].append(row.avg_time or 0)
            platform_metrics[platform]['size'].append(row.avg_size or 0)
            platform_metrics[platform]['speed'].append(row.avg_speed or 0)
            platform_metrics[platform]['total'] += row.total or 0

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
