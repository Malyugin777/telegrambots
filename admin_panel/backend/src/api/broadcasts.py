"""
Broadcasts management API endpoints.
"""
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..redis_client import get_redis
from ..models import Broadcast, BroadcastStatus, AdminUser, User, Segment
from ..schemas import (
    BroadcastCreate, BroadcastUpdate, BroadcastResponse, BroadcastListResponse, BroadcastProgress
)
from ..auth import get_current_user

router = APIRouter()


async def count_recipients(
    db: AsyncSession,
    target_type: str,
    target_segment_id: Optional[int] = None,
    target_user_ids: Optional[List[int]] = None,
) -> int:
    """Count recipients based on targeting."""
    if target_type == "all":
        result = await db.execute(
            select(func.count(User.id)).where(User.is_blocked == False)
        )
        return result.scalar() or 0

    elif target_type == "list" and target_user_ids:
        return len(target_user_ids)

    elif target_type == "segment" and target_segment_id:
        segment = await db.get(Segment, target_segment_id)
        if segment and segment.cached_count:
            return segment.cached_count
        # TODO: Calculate from conditions
        return 0

    return 0


@router.get("", response_model=BroadcastListResponse)
async def list_broadcasts(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status_filter: Optional[BroadcastStatus] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """List all broadcasts with pagination."""
    query = select(Broadcast)

    if status_filter:
        query = query.where(Broadcast.status == status_filter)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Broadcast.created_at.desc())

    result = await db.execute(query)
    broadcasts = result.scalars().all()

    return BroadcastListResponse(
        data=[BroadcastResponse.model_validate(b) for b in broadcasts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{broadcast_id}", response_model=BroadcastResponse)
async def get_broadcast(
    broadcast_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get broadcast by ID."""
    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()

    if not broadcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broadcast not found",
        )

    return broadcast


@router.post("", response_model=BroadcastResponse, status_code=status.HTTP_201_CREATED)
async def create_broadcast(
    data: BroadcastCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Create a new broadcast."""
    # Count recipients
    recipients = await count_recipients(
        db, data.target_type, data.target_segment_id, data.target_user_ids
    )

    broadcast = Broadcast(
        name=data.name,
        text=data.text,
        image_url=data.image_url,
        message_video=data.message_video,
        buttons=[btn.model_dump() for btn in data.buttons] if data.buttons else None,
        target_type=data.target_type,
        target_bots=data.target_bots,
        target_languages=data.target_languages,
        target_segment_id=data.target_segment_id,
        target_user_ids=data.target_user_ids,
        scheduled_at=data.scheduled_at,
        status=BroadcastStatus.SCHEDULED if data.scheduled_at else BroadcastStatus.DRAFT,
        total_recipients=recipients,
        created_by=current_user.id,
    )
    db.add(broadcast)
    await db.flush()
    await db.refresh(broadcast)

    return broadcast


@router.patch("/{broadcast_id}", response_model=BroadcastResponse)
async def update_broadcast(
    broadcast_id: int,
    data: BroadcastUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Update broadcast (only drafts and scheduled)."""
    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()

    if not broadcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broadcast not found",
        )

    if broadcast.status not in [BroadcastStatus.DRAFT, BroadcastStatus.SCHEDULED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit running or completed broadcast",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Handle buttons serialization
    if "buttons" in update_data and update_data["buttons"]:
        update_data["buttons"] = [btn.model_dump() for btn in data.buttons]

    for key, value in update_data.items():
        setattr(broadcast, key, value)

    # Recalculate recipients if targeting changed
    if any(k in update_data for k in ["target_type", "target_segment_id", "target_user_ids"]):
        broadcast.total_recipients = await count_recipients(
            db,
            broadcast.target_type,
            broadcast.target_segment_id,
            broadcast.target_user_ids,
        )

    # Update status based on scheduled_at
    if data.scheduled_at:
        broadcast.status = BroadcastStatus.SCHEDULED
    elif broadcast.status == BroadcastStatus.SCHEDULED and not broadcast.scheduled_at:
        broadcast.status = BroadcastStatus.DRAFT

    await db.flush()
    await db.refresh(broadcast)

    return broadcast


@router.delete("/{broadcast_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_broadcast(
    broadcast_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Delete a broadcast (only drafts)."""
    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()

    if not broadcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broadcast not found",
        )

    if broadcast.status != BroadcastStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only delete draft broadcasts",
        )

    await db.delete(broadcast)


@router.post("/{broadcast_id}/start", response_model=BroadcastResponse)
async def start_broadcast(
    broadcast_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Start a broadcast immediately."""
    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()

    if not broadcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broadcast not found",
        )

    if broadcast.status not in [BroadcastStatus.DRAFT, BroadcastStatus.SCHEDULED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Broadcast already started or completed",
        )

    # Mark as running
    broadcast.status = BroadcastStatus.RUNNING
    broadcast.started_at = datetime.utcnow()

    # TODO: Add to Redis queue for actual processing
    try:
        redis = await get_redis()
        await redis.lpush("broadcast_queue", str(broadcast.id))
    except Exception:
        pass  # Redis optional for now

    await db.flush()
    await db.refresh(broadcast)

    return broadcast


@router.post("/{broadcast_id}/cancel", response_model=BroadcastResponse)
async def cancel_broadcast(
    broadcast_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Cancel a running or scheduled broadcast."""
    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()

    if not broadcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broadcast not found",
        )

    if broadcast.status not in [BroadcastStatus.SCHEDULED, BroadcastStatus.RUNNING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only cancel scheduled or running broadcasts",
        )

    broadcast.status = BroadcastStatus.CANCELLED
    broadcast.completed_at = datetime.utcnow()

    await db.flush()
    await db.refresh(broadcast)

    return broadcast


@router.get("/{broadcast_id}/progress", response_model=BroadcastProgress)
async def get_broadcast_progress(
    broadcast_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get real-time progress of a broadcast."""
    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()

    if not broadcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broadcast not found",
        )

    progress = 0.0
    if broadcast.total_recipients > 0:
        progress = round((broadcast.sent_count / broadcast.total_recipients) * 100, 1)

    return BroadcastProgress(
        status=broadcast.status.value,
        total=broadcast.total_recipients,
        sent=broadcast.sent_count,
        delivered=broadcast.delivered_count,
        failed=broadcast.failed_count,
        progress_percent=progress,
    )
