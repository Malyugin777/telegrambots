"""
Bot Messages API endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import BotMessage, Bot
from ..schemas import (
    BotMessageCreate,
    BotMessageUpdate,
    BotMessageResponse,
    BotMessageListResponse,
)
from ..auth import get_current_user

router = APIRouter()


@router.get("", response_model=BotMessageListResponse)
async def list_bot_messages(
    bot_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """List all bot messages, optionally filtered by bot_id."""
    query = select(BotMessage, Bot.name.label("bot_name")).join(
        Bot, BotMessage.bot_id == Bot.id
    )

    if bot_id:
        query = query.where(BotMessage.bot_id == bot_id)

    query = query.order_by(BotMessage.bot_id, BotMessage.message_key)

    result = await db.execute(query)
    rows = result.all()

    data = []
    for row in rows:
        msg = row[0]
        bot_name = row[1]
        data.append(BotMessageResponse(
            id=msg.id,
            bot_id=msg.bot_id,
            message_key=msg.message_key,
            text_ru=msg.text_ru,
            text_en=msg.text_en,
            is_active=msg.is_active,
            updated_at=msg.updated_at,
            bot_name=bot_name,
        ))

    return BotMessageListResponse(data=data, total=len(data))


@router.get("/{message_id}", response_model=BotMessageResponse)
async def get_bot_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get a single bot message by ID."""
    result = await db.execute(
        select(BotMessage, Bot.name.label("bot_name"))
        .join(Bot, BotMessage.bot_id == Bot.id)
        .where(BotMessage.id == message_id)
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    msg = row[0]
    bot_name = row[1]

    return BotMessageResponse(
        id=msg.id,
        bot_id=msg.bot_id,
        message_key=msg.message_key,
        text_ru=msg.text_ru,
        text_en=msg.text_en,
        is_active=msg.is_active,
        updated_at=msg.updated_at,
        bot_name=bot_name,
    )


@router.post("", response_model=BotMessageResponse, status_code=status.HTTP_201_CREATED)
async def create_bot_message(
    data: BotMessageCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Create a new bot message."""
    # Check if bot exists
    bot_result = await db.execute(select(Bot).where(Bot.id == data.bot_id))
    bot = bot_result.scalar_one_or_none()
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    # Check if message_key already exists for this bot
    existing = await db.execute(
        select(BotMessage).where(
            BotMessage.bot_id == data.bot_id,
            BotMessage.message_key == data.message_key,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message key '{data.message_key}' already exists for this bot",
        )

    message = BotMessage(
        bot_id=data.bot_id,
        message_key=data.message_key,
        text_ru=data.text_ru,
        text_en=data.text_en,
        is_active=data.is_active,
    )

    db.add(message)
    await db.flush()
    await db.refresh(message)

    return BotMessageResponse(
        id=message.id,
        bot_id=message.bot_id,
        message_key=message.message_key,
        text_ru=message.text_ru,
        text_en=message.text_en,
        is_active=message.is_active,
        updated_at=message.updated_at,
        bot_name=bot.name,
    )


@router.patch("/{message_id}", response_model=BotMessageResponse)
async def update_bot_message(
    message_id: int,
    data: BotMessageUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Update a bot message."""
    result = await db.execute(
        select(BotMessage, Bot.name.label("bot_name"))
        .join(Bot, BotMessage.bot_id == Bot.id)
        .where(BotMessage.id == message_id)
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    message = row[0]
    bot_name = row[1]

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(message, field, value)

    await db.flush()
    await db.refresh(message)

    return BotMessageResponse(
        id=message.id,
        bot_id=message.bot_id,
        message_key=message.message_key,
        text_ru=message.text_ru,
        text_en=message.text_en,
        is_active=message.is_active,
        updated_at=message.updated_at,
        bot_name=bot_name,
    )


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Delete a bot message."""
    result = await db.execute(
        select(BotMessage).where(BotMessage.id == message_id)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    await db.delete(message)
    await db.flush()
