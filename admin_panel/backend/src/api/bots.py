"""
Bots management API endpoints.
"""
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Bot, BotUser, ActionLog, BotStatus
from ..schemas import BotCreate, BotUpdate, BotResponse, BotListResponse
from ..auth import get_current_user

router = APIRouter()


def hash_token(token: str) -> str:
    """Create SHA-256 hash of bot token."""
    return hashlib.sha256(token.encode()).hexdigest()


async def get_bot_stats(db: AsyncSession, bot_id: int) -> tuple[int, int]:
    """Get users count and downloads count for a bot."""
    # Users count
    result = await db.execute(
        select(func.count(BotUser.id)).where(BotUser.bot_id == bot_id)
    )
    users_count = result.scalar() or 0

    # Downloads count (count successful downloads)
    result = await db.execute(
        select(func.count(ActionLog.id)).where(
            ActionLog.bot_id == bot_id,
            ActionLog.action == "download_success"
        )
    )
    downloads_count = result.scalar() or 0

    return users_count, downloads_count


@router.get("", response_model=BotListResponse)
async def list_bots(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status_filter: Optional[BotStatus] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """List all bots with pagination and filtering."""
    # Base filter conditions
    conditions = []
    if status_filter:
        conditions.append(Bot.status == status_filter)
    if search:
        conditions.append(
            Bot.name.ilike(f"%{search}%") | Bot.username.ilike(f"%{search}%")
        )

    # Get total count
    count_query = select(func.count(Bot.id))
    for cond in conditions:
        count_query = count_query.where(cond)
    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Subqueries for stats (optimized - single query with GROUP BY)
    users_subq = (
        select(BotUser.bot_id, func.count(BotUser.id).label("users_count"))
        .group_by(BotUser.bot_id)
        .subquery()
    )

    downloads_subq = (
        select(ActionLog.bot_id, func.count(ActionLog.id).label("downloads_count"))
        .where(ActionLog.action == "download_success")
        .group_by(ActionLog.bot_id)
        .subquery()
    )

    # Main query with LEFT JOINs - one query instead of N+1
    query = (
        select(
            Bot,
            func.coalesce(users_subq.c.users_count, 0).label("users_count"),
            func.coalesce(downloads_subq.c.downloads_count, 0).label("downloads_count"),
        )
        .outerjoin(users_subq, Bot.id == users_subq.c.bot_id)
        .outerjoin(downloads_subq, Bot.id == downloads_subq.c.bot_id)
    )

    # Apply filters
    for cond in conditions:
        query = query.where(cond)

    # Apply pagination and order
    query = query.order_by(Bot.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    # Build response - no additional queries needed
    bots_data = []
    for row in rows:
        bot = row[0]
        users_count = row[1]
        downloads_count = row[2]
        bots_data.append(BotResponse(
            id=bot.id,
            name=bot.name,
            username=bot.username,
            description=bot.description,
            webhook_url=bot.webhook_url,
            status=bot.status,
            settings=bot.settings,
            token_hash=bot.token_hash,
            created_at=bot.created_at,
            updated_at=bot.updated_at,
            users_count=users_count,
            downloads_count=downloads_count,
        ))

    return BotListResponse(
        data=bots_data,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get bot by ID."""
    result = await db.execute(select(Bot).where(Bot.id == bot_id))
    bot = result.scalar_one_or_none()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    users_count, downloads_count = await get_bot_stats(db, bot.id)
    return BotResponse(
        id=bot.id,
        name=bot.name,
        username=bot.username,
        description=bot.description,
        webhook_url=bot.webhook_url,
        status=bot.status,
        settings=bot.settings,
        token_hash=bot.token_hash,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
        users_count=users_count,
        downloads_count=downloads_count,
    )


@router.post("", response_model=BotResponse, status_code=status.HTTP_201_CREATED)
async def create_bot(
    data: BotCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Create a new bot."""
    # Check if name exists
    result = await db.execute(select(Bot).where(Bot.name == data.name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot with this name already exists",
        )

    # Check if token already used (by hash)
    token_hash = hash_token(data.token)
    result = await db.execute(select(Bot).where(Bot.token_hash == token_hash))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This token is already registered",
        )

    bot = Bot(
        name=data.name,
        token_hash=token_hash,
        username=data.username,
        description=data.description,
        webhook_url=data.webhook_url,
        status=data.status,
        settings=data.settings,
    )
    db.add(bot)
    await db.flush()
    await db.refresh(bot)

    return bot


@router.patch("/{bot_id}", response_model=BotResponse)
async def update_bot(
    bot_id: int,
    data: BotUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Update bot settings."""
    result = await db.execute(select(Bot).where(Bot.id == bot_id))
    bot = result.scalar_one_or_none()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Handle token update separately
    if "token" in update_data:
        token = update_data.pop("token")
        if token:
            update_data["token_hash"] = hash_token(token)

    # Check name uniqueness if changing
    if "name" in update_data and update_data["name"] != bot.name:
        result = await db.execute(select(Bot).where(Bot.name == update_data["name"]))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bot with this name already exists",
            )

    for key, value in update_data.items():
        setattr(bot, key, value)

    await db.flush()
    await db.refresh(bot)

    return bot


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Delete a bot."""
    result = await db.execute(select(Bot).where(Bot.id == bot_id))
    bot = result.scalar_one_or_none()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    await db.delete(bot)


@router.post("/{bot_id}/restart", response_model=BotResponse)
async def restart_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Restart a bot.
    This is a placeholder - actual restart logic depends on your bot deployment.
    """
    result = await db.execute(select(Bot).where(Bot.id == bot_id))
    bot = result.scalar_one_or_none()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    # TODO: Implement actual restart logic
    # For now, just toggle status
    bot.status = BotStatus.ACTIVE

    await db.flush()
    await db.refresh(bot)

    return bot
