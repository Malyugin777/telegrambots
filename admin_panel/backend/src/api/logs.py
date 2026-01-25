"""
Action logs API endpoints.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import ActionLog, User, Bot
from ..schemas import LogResponse, LogListResponse
from ..auth import get_current_user

router = APIRouter()


@router.get("", response_model=LogListResponse)
async def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    bot_id: Optional[int] = None,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """List action logs with pagination and filtering."""
    # Base query with joins
    query = (
        select(
            ActionLog.id,
            ActionLog.user_id,
            ActionLog.bot_id,
            ActionLog.action,
            ActionLog.details,
            ActionLog.created_at,
            User.username.label("username"),
            User.first_name.label("first_name"),
            Bot.name.label("bot_name"),
        )
        .outerjoin(User, ActionLog.user_id == User.id)
        .outerjoin(Bot, ActionLog.bot_id == Bot.id)
    )

    # Filter by date range
    start_date = datetime.utcnow() - timedelta(days=days)
    query = query.where(ActionLog.created_at >= start_date)

    # Apply filters
    if bot_id:
        query = query.where(ActionLog.bot_id == bot_id)
    if user_id:
        query = query.where(ActionLog.user_id == user_id)
    if action:
        query = query.where(ActionLog.action.ilike(f"%{action}%"))

    # Get total count
    count_query = (
        select(func.count(ActionLog.id))
        .where(ActionLog.created_at >= start_date)
    )
    if bot_id:
        count_query = count_query.where(ActionLog.bot_id == bot_id)
    if user_id:
        count_query = count_query.where(ActionLog.user_id == user_id)
    if action:
        count_query = count_query.where(ActionLog.action.ilike(f"%{action}%"))

    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(ActionLog.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    logs = [
        LogResponse(
            id=row.id,
            user_id=row.user_id,
            bot_id=row.bot_id,
            action=row.action,
            details=row.details,
            created_at=row.created_at,
            username=row.username,
            first_name=row.first_name,
            bot_name=row.bot_name,
        )
        for row in rows
    ]

    return LogListResponse(
        data=logs,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/actions")
async def get_action_types(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get list of unique action types."""
    result = await db.execute(
        select(ActionLog.action).distinct().order_by(ActionLog.action)
    )
    actions = [row[0] for row in result.all()]
    return {"actions": actions}
