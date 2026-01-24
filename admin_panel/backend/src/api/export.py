"""
CSV Export API endpoints.
"""
import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User, Bot, Broadcast, ActionLog, Subscription, BotUser, UserRole
from ..auth import get_current_user

router = APIRouter()


def format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime for CSV."""
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@router.get("/users")
async def export_users(
    role: Optional[UserRole] = None,
    is_banned: Optional[bool] = None,
    bot_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Export users to CSV."""
    # Build query
    conditions = []
    join_bot_user = False

    if bot_id:
        join_bot_user = True
        conditions.append(BotUser.bot_id == bot_id)
    if role:
        conditions.append(User.role == role)
    if is_banned is not None:
        conditions.append(User.is_banned == is_banned)

    # Downloads count subquery
    downloads_subq = (
        select(ActionLog.user_id, func.count(ActionLog.id).label("downloads_count"))
        .where(ActionLog.action == "download_success")
        .group_by(ActionLog.user_id)
        .subquery()
    )

    query = (
        select(
            User,
            func.coalesce(downloads_subq.c.downloads_count, 0).label("downloads_count"),
        )
        .outerjoin(downloads_subq, User.id == downloads_subq.c.user_id)
    )

    if join_bot_user:
        query = query.join(BotUser, User.id == BotUser.user_id)

    for cond in conditions:
        query = query.where(cond)

    query = query.order_by(User.created_at.desc())

    result = await db.execute(query)
    rows = result.all()

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "ID", "Telegram ID", "Username", "First Name", "Last Name",
        "Language", "Role", "Banned", "Ban Reason", "Downloads",
        "Created At", "Last Active"
    ])

    # Data
    for row in rows:
        user = row[0]
        downloads = row[1]
        writer.writerow([
            user.id,
            user.telegram_id,
            user.username or "",
            user.first_name or "",
            user.last_name or "",
            user.language_code or "",
            user.role.value if user.role else "user",
            "Yes" if user.is_banned else "No",
            user.ban_reason or "",
            downloads,
            format_datetime(user.created_at),
            format_datetime(user.last_active_at),
        ])

    output.seek(0)

    filename = f"users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/bots")
async def export_bots(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Export bots to CSV."""
    # Users count subquery
    users_subq = (
        select(BotUser.bot_id, func.count(BotUser.id).label("users_count"))
        .group_by(BotUser.bot_id)
        .subquery()
    )

    # Downloads count subquery
    downloads_subq = (
        select(ActionLog.bot_id, func.count(ActionLog.id).label("downloads_count"))
        .where(ActionLog.action == "download_success")
        .group_by(ActionLog.bot_id)
        .subquery()
    )

    query = (
        select(
            Bot,
            func.coalesce(users_subq.c.users_count, 0).label("users_count"),
            func.coalesce(downloads_subq.c.downloads_count, 0).label("downloads_count"),
        )
        .outerjoin(users_subq, Bot.id == users_subq.c.bot_id)
        .outerjoin(downloads_subq, Bot.id == downloads_subq.c.bot_id)
        .order_by(Bot.created_at.desc())
    )

    result = await db.execute(query)
    rows = result.all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Name", "Username", "Status", "Users", "Downloads",
        "Created At", "Updated At"
    ])

    for row in rows:
        bot = row[0]
        users_count = row[1]
        downloads_count = row[2]
        writer.writerow([
            bot.id,
            bot.name,
            bot.username or "",
            bot.status.value if bot.status else "inactive",
            users_count,
            downloads_count,
            format_datetime(bot.created_at),
            format_datetime(bot.updated_at),
        ])

    output.seek(0)
    filename = f"bots_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/broadcasts")
async def export_broadcasts(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Export broadcasts to CSV."""
    query = select(Broadcast).order_by(Broadcast.created_at.desc())

    if status:
        query = query.where(Broadcast.status == status)

    result = await db.execute(query)
    broadcasts = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Name", "Status", "Total Recipients", "Sent Count",
        "Failed Count", "Scheduled At", "Started At", "Completed At", "Created At"
    ])

    for b in broadcasts:
        writer.writerow([
            b.id,
            b.name,
            b.status,
            b.total_recipients or 0,
            b.sent_count or 0,
            b.failed_count or 0,
            format_datetime(b.scheduled_at),
            format_datetime(b.started_at),
            format_datetime(b.completed_at),
            format_datetime(b.created_at),
        ])

    output.seek(0)
    filename = f"broadcasts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/logs")
async def export_logs(
    action: Optional[str] = None,
    bot_id: Optional[int] = None,
    user_id: Optional[int] = None,
    limit: int = Query(10000, le=50000),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Export activity logs to CSV (max 50k records)."""
    query = select(ActionLog).order_by(ActionLog.created_at.desc())

    if action:
        query = query.where(ActionLog.action == action)
    if bot_id:
        query = query.where(ActionLog.bot_id == bot_id)
    if user_id:
        query = query.where(ActionLog.user_id == user_id)

    query = query.limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Action", "Bot ID", "User ID", "Created At"
    ])

    for log in logs:
        writer.writerow([
            log.id,
            log.action,
            log.bot_id or "",
            log.user_id or "",
            format_datetime(log.created_at),
        ])

    output.seek(0)
    filename = f"activity_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/subscriptions")
async def export_subscriptions(
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Export subscriptions to CSV."""
    query = select(Subscription).order_by(Subscription.created_at.desc())

    if is_active is not None:
        query = query.where(Subscription.is_active == is_active)

    result = await db.execute(query)
    subscriptions = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "User ID", "Telegram ID", "Plan", "Active", "Stars Paid",
        "Flyer Payment ID", "Started At", "Expires At", "Created At"
    ])

    for sub in subscriptions:
        writer.writerow([
            sub.id,
            sub.user_id,
            sub.telegram_id or "",
            sub.plan or "",
            "Yes" if sub.is_active else "No",
            sub.stars_paid or 0,
            sub.flyer_payment_id or "",
            format_datetime(sub.started_at),
            format_datetime(sub.expires_at),
            format_datetime(sub.created_at),
        ])

    output.seek(0)
    filename = f"subscriptions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
