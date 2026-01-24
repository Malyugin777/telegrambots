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
    """Статистика FlyerService (Mom's Strategy)."""
    # Сегодня
    ads_shown_today: int  # Показано рекламы (10-е скачивание, юзер НЕ подписан)
    silent_passes_today: int  # Тихие проходы (10-е скачивание, юзер подписан)
    free_downloads_today: int  # Бесплатные скачивания (не 10-е или honey period)
    total_downloads_today: int  # Всего скачиваний

    # За всё время
    ads_shown_total: int
    silent_passes_total: int
    free_downloads_total: int
    total_downloads: int

    # Процент монетизации
    monetization_rate_today: float  # % скачиваний с проверкой (ads + silent)
    ad_conversion_today: float  # % показов рекламы от проверок

    # Топ качальщиков без рекламы (user_id, count)
    top_free_downloaders: List[dict]

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
    # Не используем GROUP BY на JSON - получаем все записи и группируем в Python
    result = await db.execute(
        select(ActionLog.details)
        .where(ActionLog.action == "download_success")
    )

    platform_counts: dict[str, int] = {}
    for row in result:
        details = row[0]
        if details and isinstance(details, dict) and 'info' in details:
            info = details['info']
            # Parse "video:instagram" -> "instagram"
            if ':' in info:
                platform = info.split(':')[-1]  # Get last part after ':'
            else:
                platform = info
            platform_counts[platform] = platform_counts.get(platform, 0) + 1

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
    # Не используем GROUP BY на JSON - получаем все записи и группируем в Python
    result = await db.execute(
        select(
            ActionLog.details,
            ActionLog.download_time_ms,
            ActionLog.file_size_bytes,
            ActionLog.download_speed_kbps
        ).where(
            ActionLog.action == "download_success",
            ActionLog.download_time_ms.isnot(None)
        )
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
    """Get API usage statistics (RapidAPI, yt-dlp, Cobalt)."""

    # Get today's start and month's start
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # RapidAPI usage
    # Today
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.created_at >= today_start,
            ActionLog.api_source == APISource.RAPIDAPI,
            ActionLog.action == "download_success"
        )
    )
    rapidapi_today = result.scalar() or 0

    # This month
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.created_at >= month_start,
            ActionLog.api_source == APISource.RAPIDAPI,
            ActionLog.action == "download_success"
        )
    )
    rapidapi_month = result.scalar() or 0

    # yt-dlp usage
    # Today
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.created_at >= today_start,
            ActionLog.api_source == APISource.YTDLP,
            ActionLog.action == "download_success"
        )
    )
    ytdlp_today = result.scalar() or 0

    # This month
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.created_at >= month_start,
            ActionLog.api_source == APISource.YTDLP,
            ActionLog.action == "download_success"
        )
    )
    ytdlp_month = result.scalar() or 0

    # Cobalt usage (optional)
    # Today
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.created_at >= today_start,
            ActionLog.api_source == APISource.COBALT,
            ActionLog.action == "download_success"
        )
    )
    cobalt_today = result.scalar() or 0

    # This month
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.created_at >= month_start,
            ActionLog.api_source == APISource.COBALT,
            ActionLog.action == "download_success"
        )
    )
    cobalt_month = result.scalar() or 0

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
    Статистика FlyerService (Mom's Strategy).

    Логика:
    - flyer_ad_shown action = 10-е скачивание, юзер НЕ подписан, показали рекламу
    - download_success + flyer_required=True = 10-е скачивание, юзер подписан (silent pass)
    - download_success + flyer_required=False = бесплатное скачивание (не 10-е или honey period)
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # === 1. Считаем показы рекламы (flyer_ad_shown) ===
    result = await db.execute(
        select(func.count(ActionLog.id))
        .where(ActionLog.action == "flyer_ad_shown", ActionLog.created_at >= today_start)
    )
    ads_shown_today = result.scalar() or 0

    result = await db.execute(
        select(func.count(ActionLog.id))
        .where(ActionLog.action == "flyer_ad_shown")
    )
    ads_shown_total = result.scalar() or 0

    # === 2. Считаем успешные скачивания ===
    result = await db.execute(
        select(ActionLog.details, ActionLog.user_id, ActionLog.created_at)
        .where(ActionLog.action == "download_success")
    )

    # Счётчики
    silent_passes_today = 0
    silent_passes_total = 0
    free_downloads_today = 0
    free_downloads_total = 0
    total_downloads_today = 0
    total_downloads = 0

    # Счётчик бесплатных скачиваний по юзерам
    user_free_counts: dict[int, int] = {}

    for row in result:
        details = row.details
        user_id = row.user_id
        created_at = row.created_at

        total_downloads += 1
        is_today = created_at and created_at >= today_start

        if is_today:
            total_downloads_today += 1

        if not details or not isinstance(details, dict):
            # Нет details = старая запись, считаем как free
            free_downloads_total += 1
            if is_today:
                free_downloads_today += 1
            continue

        # Проверяем flyer_required
        flyer_required = details.get('flyer_required', False)

        if flyer_required:
            # 10-е скачивание, юзер был подписан (silent pass)
            silent_passes_total += 1
            if is_today:
                silent_passes_today += 1
        else:
            # Бесплатное скачивание (не 10-е или honey period)
            free_downloads_total += 1
            if is_today:
                free_downloads_today += 1

            # Считаем для топа бесплатных качальщиков
            if user_id:
                user_free_counts[user_id] = user_free_counts.get(user_id, 0) + 1

    # === 3. Рассчитываем проценты ===
    # Процент монетизации = (ads + silent) / total * 100
    checks_today = ads_shown_today + silent_passes_today
    monetization_rate_today = (checks_today / total_downloads_today * 100) if total_downloads_today > 0 else 0

    # Конверсия рекламы = ads / (ads + silent) * 100
    # (сколько % от проверок закончились показом рекламы)
    ad_conversion_today = (ads_shown_today / checks_today * 100) if checks_today > 0 else 0

    # === 4. Топ 10 бесплатных качальщиков ===
    top_users = sorted(user_free_counts.items(), key=lambda x: -x[1])[:10]

    top_free_downloaders = []
    if top_users:
        user_ids = [u[0] for u in top_users]
        users_result = await db.execute(
            select(User.id, User.telegram_id, User.username, User.first_name)
            .where(User.id.in_(user_ids))
        )
        users_map = {row.id: row for row in users_result}

        for user_id, count in top_users:
            user = users_map.get(user_id)
            top_free_downloaders.append({
                "user_id": user_id,
                "telegram_id": user.telegram_id if user else None,
                "username": user.username if user else None,
                "name": user.first_name if user else None,
                "free_count": count,
            })

    return FlyerStatsResponse(
        ads_shown_today=ads_shown_today,
        silent_passes_today=silent_passes_today,
        free_downloads_today=free_downloads_today,
        total_downloads_today=total_downloads_today,
        ads_shown_total=ads_shown_total,
        silent_passes_total=silent_passes_total,
        free_downloads_total=free_downloads_total,
        total_downloads=total_downloads,
        monetization_rate_today=round(monetization_rate_today, 1),
        ad_conversion_today=round(ad_conversion_today, 1),
        top_free_downloaders=top_free_downloaders,
    )
