"""
Users management API endpoints.
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User, ActionLog, UserRole
from ..schemas import UserResponse, UserListResponse, UserBanRequest, UserRoleUpdate
from ..auth import get_current_user, get_superuser


class FreeDownloaderResponse(BaseModel):
    """Юзер с количеством бесплатных скачиваний."""
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    free_youtube_full_count: int
    total_youtube_full_count: int

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

    # Base filter conditions
    conditions = []
    join_bot_user = False

    # Filter by bot
    if bot_id:
        join_bot_user = True
        conditions.append(BotUser.bot_id == bot_id)

    # Apply filters
    if role:
        conditions.append(User.role == role)
    if is_banned is not None:
        conditions.append(User.is_banned == is_banned)
    if search:
        conditions.append(
            User.username.ilike(f"%{search}%") |
            User.first_name.ilike(f"%{search}%") |
            User.telegram_id.cast(str).ilike(f"%{search}%")
        )

    # Get total count
    count_query = select(func.count(User.id))
    if join_bot_user:
        count_query = count_query.join(BotUser, User.id == BotUser.user_id)
    for cond in conditions:
        count_query = count_query.where(cond)
    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Subquery for downloads count (optimized - single query with GROUP BY)
    downloads_subq = (
        select(ActionLog.user_id, func.count(ActionLog.id).label("downloads_count"))
        .where(ActionLog.action == "download_success")
        .group_by(ActionLog.user_id)
        .subquery()
    )

    # Main query with LEFT JOIN - one query instead of N+1
    query = (
        select(
            User,
            func.coalesce(downloads_subq.c.downloads_count, 0).label("downloads_count"),
        )
        .outerjoin(downloads_subq, User.id == downloads_subq.c.user_id)
    )

    # Join BotUser if filtering by bot
    if join_bot_user:
        query = query.join(BotUser, User.id == BotUser.user_id)

    # Apply filters
    for cond in conditions:
        query = query.where(cond)

    # Apply pagination and order
    query = query.order_by(User.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    # Build response - no additional queries needed
    users_data = []
    for row in rows:
        user = row[0]
        downloads_count = row[1]
        users_data.append(UserResponse(
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
        ))

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
    # Не используем GROUP BY на JSON - получаем все записи и группируем в Python
    result = await db.execute(
        select(ActionLog.details)
        .where(
            ActionLog.user_id == user_id,
            ActionLog.action == "download_success"
        )
    )

    platform_counts: dict[str, int] = {}
    for row in result:
        details = row[0]
        if details and isinstance(details, dict) and 'info' in details:
            info = details['info']
            if ':' in info:
                platform = info.split(':')[-1]
            else:
                platform = info
            platform_counts[platform] = platform_counts.get(platform, 0) + 1

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


@router.get("/top-free-downloaders", response_model=List[FreeDownloaderResponse])
async def get_top_free_downloaders(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Получить топ юзеров по количеству бесплатных YouTube Full скачиваний.

    Бесплатные = flyer_required=False в details (без показа рекламы).
    """
    # Получаем все YouTube Full скачивания
    result = await db.execute(
        select(ActionLog.details, ActionLog.user_id)
        .where(ActionLog.action == "download_success")
    )

    # Счётчики по юзерам
    user_free_counts: dict[int, int] = {}
    user_total_counts: dict[int, int] = {}

    for row in result:
        details = row.details
        user_id = row.user_id

        if not details or not isinstance(details, dict) or not user_id:
            continue

        # Проверяем что это YouTube Full
        platform = details.get('platform', '')
        if platform != 'youtube_full':
            continue

        # Считаем общее
        user_total_counts[user_id] = user_total_counts.get(user_id, 0) + 1

        # Считаем бесплатные
        flyer_required = details.get('flyer_required', False)
        if not flyer_required:
            user_free_counts[user_id] = user_free_counts.get(user_id, 0) + 1

    # Сортируем по количеству бесплатных
    top_users = sorted(user_free_counts.items(), key=lambda x: -x[1])[:limit]

    if not top_users:
        return []

    # Получаем информацию о юзерах
    user_ids = [u[0] for u in top_users]
    users_result = await db.execute(
        select(User).where(User.id.in_(user_ids))
    )
    users_map = {u.id: u for u in users_result.scalars().all()}

    # Формируем ответ
    response = []
    for user_id, free_count in top_users:
        user = users_map.get(user_id)
        if not user:
            continue

        response.append(FreeDownloaderResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            free_youtube_full_count=free_count,
            total_youtube_full_count=user_total_counts.get(user_id, 0),
        ))

    return response
