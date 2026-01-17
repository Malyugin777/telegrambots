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
from ..models import Bot, User, Broadcast, BotStatus, BroadcastStatus
from ..schemas import StatsResponse, LoadChartResponse, ChartDataPoint
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
        total_bots=total_bots,
        active_bots=active_bots,
        total_users=total_users,
        active_users_today=active_users_today,
        messages_in_queue=queue_length,
        broadcasts_running=broadcasts_running,
    )


@router.get("/chart", response_model=LoadChartResponse)
async def get_load_chart(
    days: int = 7,
    _=Depends(get_current_user),
):
    """
    Get load chart data for the last N days.
    Returns fake data for now - replace with real metrics later.
    """
    messages_data = []
    users_data = []

    for i in range(days, 0, -1):
        date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        # Fake data - replace with real queries
        messages_data.append(ChartDataPoint(
            date=date,
            value=random.randint(1000, 5000),
        ))
        users_data.append(ChartDataPoint(
            date=date,
            value=random.randint(100, 500),
        ))

    return LoadChartResponse(
        messages=messages_data,
        users=users_data,
    )
