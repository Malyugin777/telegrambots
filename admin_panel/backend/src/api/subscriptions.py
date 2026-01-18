"""
Subscriptions (Billing Tracker) API endpoints.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Subscription, SubscriptionStatus
from ..schemas import (
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionResponse,
    SubscriptionListResponse,
    UpcomingPayment,
)
from ..auth import get_current_user

router = APIRouter()


def calculate_days_until(next_payment_date: Optional[datetime]) -> Optional[int]:
    """Calculate days until next payment."""
    if not next_payment_date:
        return None
    delta = next_payment_date - datetime.utcnow()
    return max(0, delta.days)


@router.get("", response_model=SubscriptionListResponse)
async def list_subscriptions(
    status_filter: Optional[SubscriptionStatus] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """List all subscriptions."""
    query = select(Subscription)

    if status_filter:
        query = query.where(Subscription.status == status_filter)

    query = query.order_by(Subscription.next_payment_date.asc().nullslast())

    result = await db.execute(query)
    subscriptions = result.scalars().all()

    # Enrich with computed fields
    data = []
    for sub in subscriptions:
        sub_dict = {
            "id": sub.id,
            "name": sub.name,
            "description": sub.description,
            "provider": sub.provider,
            "provider_url": sub.provider_url,
            "amount": sub.amount,
            "currency": sub.currency,
            "billing_cycle": sub.billing_cycle,
            "next_payment_date": sub.next_payment_date,
            "auto_renew": sub.auto_renew,
            "notify_days": sub.notify_days,
            "status": sub.status,
            "created_at": sub.created_at,
            "updated_at": sub.updated_at,
            "days_until_payment": calculate_days_until(sub.next_payment_date),
        }
        data.append(SubscriptionResponse(**sub_dict))

    return SubscriptionListResponse(data=data, total=len(data))


@router.get("/upcoming", response_model=list[UpcomingPayment])
async def get_upcoming_payments(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get upcoming payments within specified days."""
    cutoff_date = datetime.utcnow() + timedelta(days=days)

    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.next_payment_date.isnot(None),
            Subscription.next_payment_date <= cutoff_date,
        )
        .order_by(Subscription.next_payment_date.asc())
    )
    subscriptions = result.scalars().all()

    return [
        UpcomingPayment(
            id=sub.id,
            name=sub.name,
            provider=sub.provider,
            amount=sub.amount,
            currency=sub.currency,
            next_payment_date=sub.next_payment_date,
            days_until=calculate_days_until(sub.next_payment_date) or 0,
        )
        for sub in subscriptions
    ]


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get subscription by ID."""
    result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    return SubscriptionResponse(
        id=subscription.id,
        name=subscription.name,
        description=subscription.description,
        provider=subscription.provider,
        provider_url=subscription.provider_url,
        amount=subscription.amount,
        currency=subscription.currency,
        billing_cycle=subscription.billing_cycle,
        next_payment_date=subscription.next_payment_date,
        auto_renew=subscription.auto_renew,
        notify_days=subscription.notify_days,
        status=subscription.status,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
        days_until_payment=calculate_days_until(subscription.next_payment_date),
    )


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    data: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Create a new subscription."""
    subscription = Subscription(
        name=data.name,
        description=data.description,
        provider=data.provider,
        provider_url=data.provider_url,
        amount=data.amount,
        currency=data.currency,
        billing_cycle=data.billing_cycle,
        next_payment_date=data.next_payment_date,
        auto_renew=data.auto_renew,
        notify_days=data.notify_days,
        status=data.status,
    )

    db.add(subscription)
    await db.flush()
    await db.refresh(subscription)

    return SubscriptionResponse(
        id=subscription.id,
        name=subscription.name,
        description=subscription.description,
        provider=subscription.provider,
        provider_url=subscription.provider_url,
        amount=subscription.amount,
        currency=subscription.currency,
        billing_cycle=subscription.billing_cycle,
        next_payment_date=subscription.next_payment_date,
        auto_renew=subscription.auto_renew,
        notify_days=subscription.notify_days,
        status=subscription.status,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
        days_until_payment=calculate_days_until(subscription.next_payment_date),
    )


@router.patch("/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: int,
    data: SubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Update a subscription."""
    result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subscription, field, value)

    await db.flush()
    await db.refresh(subscription)

    return SubscriptionResponse(
        id=subscription.id,
        name=subscription.name,
        description=subscription.description,
        provider=subscription.provider,
        provider_url=subscription.provider_url,
        amount=subscription.amount,
        currency=subscription.currency,
        billing_cycle=subscription.billing_cycle,
        next_payment_date=subscription.next_payment_date,
        auto_renew=subscription.auto_renew,
        notify_days=subscription.notify_days,
        status=subscription.status,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
        days_until_payment=calculate_days_until(subscription.next_payment_date),
    )


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Delete a subscription."""
    result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    await db.delete(subscription)
    await db.flush()
