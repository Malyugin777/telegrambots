"""
Users management API endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User, UserRole
from ..schemas import UserResponse, UserListResponse, UserBanRequest, UserRoleUpdate
from ..auth import get_current_user, get_superuser

router = APIRouter()


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    role: Optional[UserRole] = None,
    is_banned: Optional[bool] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """List all telegram users with pagination and filtering."""
    query = select(User)

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

    return UserListResponse(
        data=[UserResponse.model_validate(user) for user in users],
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

    return user


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
