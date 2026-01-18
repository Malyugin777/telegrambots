"""
Users management API endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User, ActionLog, UserRole
from ..schemas import UserResponse, UserListResponse, UserBanRequest, UserRoleUpdate
from ..auth import get_current_user, get_superuser

router = APIRouter()


async def get_user_downloads_count(db: AsyncSession, user_id: int) -> int:
    """Get downloads count for a user."""
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.user_id == user_id,
            ActionLog.action == "download_success"
        )
    )
    return result.scalar() or 0


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    role: Optional[UserRole] = None,
    is_banned: Optional[bool] = None,
    search: Optional[str] = None,
    bot_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """List all telegram users with pagination and filtering."""
    from ..models import BotUser

    query = select(User)

    # Filter by bot
    if bot_id:
        query = query.join(BotUser, User.id == BotUser.user_id).where(BotUser.bot_id == bot_id)

    # Apply filters
    if role:
        query = query.where(User.role == role)
    if is_banned is not None:
        query = query.where(User.is_banned == is_banned)
    if search:
        query = query.where(
            User.username.ilike(f"%{search}%") |
            User.first_name.ilike(f"%{search}%") |
            User.telegram_id.cast(str).ilike(f"%{search}%")
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(User.created_at.desc())

    result = await db.execute(query)
    users = result.scalars().all()

    # Enrich with downloads count
    users_data = []
    for user in users:
        downloads_count = await get_user_downloads_count(db, user.id)
        user_dict = {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "language_code": user.language_code,
            "role": user.role,
            "is_banned": user.is_banned,
            "ban_reason": user.ban_reason,
            "created_at": user.created_at,
            "last_active_at": user.last_active_at,
            "downloads_count": downloads_count,
        }
        users_data.append(UserResponse(**user_dict))

    return UserListResponse(
        data=users_data,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    downloads_count = await get_user_downloads_count(db, user.id)
    return UserResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        role=user.role,
        is_banned=user.is_banned,
        ban_reason=user.ban_reason,
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        downloads_count=downloads_count,
    )


@router.patch("/{user_id}/ban", response_model=UserResponse)
async def ban_user(
    user_id: int,
    data: UserBanRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Ban or unban a user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent banning owner
    if user.role == UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot ban owner",
        )

    user.is_banned = data.is_banned
    user.ban_reason = data.ban_reason if data.is_banned else None

    await db.flush()
    await db.refresh(user)

    return user


@router.patch("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_superuser),  # Only superuser can change roles
):
    """Update user role (superuser only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.role = data.role

    await db.flush()
    await db.refresh(user)

    return user


@router.get("/{user_id}/stats")
async def get_user_stats(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get detailed user statistics including downloads by platform."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Total downloads
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.user_id == user_id,
            ActionLog.action == "download_success"
        )
    )
    total_downloads = result.scalar() or 0

    # Downloads by platform
    result = await db.execute(
        select(ActionLog.details, func.count(ActionLog.id).label('count'))
        .where(
            ActionLog.user_id == user_id,
            ActionLog.action == "download_success"
        )
        .group_by(ActionLog.details)
    )

    platform_counts: dict[str, int] = {}
    for row in result:
        details = row[0]
        count = row[1]
        if details and isinstance(details, dict) and 'info' in details:
            info = details['info']
            if ':' in info:
                platform = info.split(':')[-1]
            else:
                platform = info
            platform_counts[platform] = platform_counts.get(platform, 0) + count

    # Recent activity (last 10 actions)
    result = await db.execute(
        select(ActionLog)
        .where(ActionLog.user_id == user_id)
        .order_by(ActionLog.created_at.desc())
        .limit(10)
    )
    recent_logs = result.scalars().all()

    return {
        "total_downloads": total_downloads,
        "platforms": [
            {"name": name, "count": count}
            for name, count in sorted(platform_counts.items(), key=lambda x: -x[1])
        ],
        "recent_activity": [
            {
                "id": log.id,
                "action": log.action,
                "details": log.details,
                "created_at": log.created_at.isoformat(),
            }
            for log in recent_logs
        ],
    }
