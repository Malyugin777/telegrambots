"""
Auth API endpoints.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import AdminUser
from ..schemas import LoginRequest, TokenResponse, AdminUserCreate, AdminUserResponse
from ..auth import hash_password, verify_password, create_access_token, get_current_user, get_superuser
from ..config import settings

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login and get access token."""
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == data.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Update last login
    user.last_login = datetime.utcnow()

    access_token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.post("/register", response_model=AdminUserResponse)
async def register(
    data: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_superuser),  # Only superusers can create users
):
    """Register new admin user (superuser only)."""
    # Check if username exists
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    # Check if email exists
    result = await db.execute(
        select(AdminUser).where(AdminUser.email == data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists",
        )

    user = AdminUser(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return user


@router.get("/me", response_model=AdminUserResponse)
async def get_me(
    current_user: AdminUser = Depends(get_current_user),
):
    """Get current user info."""
    return current_user


@router.post("/setup", response_model=AdminUserResponse)
async def initial_setup(
    data: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Initial setup - create first superuser.
    Only works if no admin users exist.
    """
    result = await db.execute(select(AdminUser).limit(1))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setup already completed. Admin users exist.",
        )

    user = AdminUser(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        is_superuser=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return user
