"""
FlyerService webhook handler.

Receives callbacks from FlyerService when users complete subscription tasks.

Event types:
- test: webhook verification
- sub_completed: user completed mandatory subscription
- new_status (status=abort): user unsubscribed from channel
"""
import os
import logging
from typing import Any, Dict
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User, ActionLog

logger = logging.getLogger(__name__)

router = APIRouter()

# Store recent events for debugging
_recent_events: list = []
MAX_EVENTS = 50

# Webhook secret token (set in FlyerService dashboard)
FLYER_WEBHOOK_SECRET = os.getenv("FLYER_WEBHOOK_SECRET", "")


def verify_webhook_auth(authorization: str = Header(None)) -> bool:
    """Verify webhook authorization header."""
    if not FLYER_WEBHOOK_SECRET:
        # If no secret configured, allow all (for backward compatibility)
        logger.warning("[FLYER WEBHOOK] No FLYER_WEBHOOK_SECRET configured - accepting all requests")
        return True

    if not authorization:
        return False

    # Check Bearer token
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        return token == FLYER_WEBHOOK_SECRET

    return False


@router.post("")
async def flyer_webhook(
    request: Request,
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Receive webhook from FlyerService.

    Must return {"status": true} for FlyerService to accept.
    """
    # Verify authorization
    if not verify_webhook_auth(authorization):
        logger.warning(f"[FLYER WEBHOOK] Unauthorized request from {request.client.host}")
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        body = await request.json()

        # Detailed logging
        event_type = body.get("type", "unknown")
        key_number = body.get("key_number")
        data = body.get("data", {})

        logger.info(f"[FLYER WEBHOOK] Event: type={event_type}, key={key_number}, data={data}")

        # Store for debugging
        _recent_events.append({
            "timestamp": datetime.utcnow().isoformat(),
            "type": event_type,
            "key_number": key_number,
            "data": data,
            "raw": body
        })
        if len(_recent_events) > MAX_EVENTS:
            _recent_events.pop(0)

        # Handle specific events
        if event_type == "test":
            logger.info("[FLYER WEBHOOK] Test event received - webhook is working")

        elif event_type == "sub_completed":
            telegram_id = data.get("user_id")
            logger.info(f"[FLYER WEBHOOK] User {telegram_id} completed subscription!")

            # Update user in database
            if telegram_id:
                try:
                    result = await db.execute(
                        select(User).where(User.telegram_id == int(telegram_id))
                    )
                    user = result.scalar_one_or_none()

                    if user:
                        # Update extra_data with flyer subscription info
                        extra_data = user.extra_data or {}
                        extra_data["flyer_subscribed_at"] = datetime.utcnow().isoformat()
                        extra_data["flyer_completed"] = True
                        user.extra_data = extra_data

                        # Create action log
                        action_log = ActionLog(
                            user_id=user.id,
                            action="flyer_sub_completed",
                            details={"event": "sub_completed", "data": data}
                        )
                        db.add(action_log)
                        await db.commit()

                        logger.info(f"[FLYER WEBHOOK] Updated user {telegram_id} in database")
                    else:
                        logger.warning(f"[FLYER WEBHOOK] User {telegram_id} not found in database")
                except Exception as db_error:
                    logger.error(f"[FLYER WEBHOOK] Database error: {db_error}")

        elif event_type == "new_status":
            status = data.get("status")
            telegram_id = data.get("user_id")
            logger.info(f"[FLYER WEBHOOK] User {telegram_id} status changed to: {status}")

            # If user unsubscribed, update database
            if status == "abort" and telegram_id:
                try:
                    result = await db.execute(
                        select(User).where(User.telegram_id == int(telegram_id))
                    )
                    user = result.scalar_one_or_none()

                    if user:
                        extra_data = user.extra_data or {}
                        extra_data["flyer_completed"] = False
                        extra_data["flyer_unsubscribed_at"] = datetime.utcnow().isoformat()
                        user.extra_data = extra_data

                        action_log = ActionLog(
                            user_id=user.id,
                            action="flyer_unsubscribed",
                            details={"event": "new_status", "status": status, "data": data}
                        )
                        db.add(action_log)
                        await db.commit()

                        logger.info(f"[FLYER WEBHOOK] User {telegram_id} unsubscribed, updated database")
                except Exception as db_error:
                    logger.error(f"[FLYER WEBHOOK] Database error: {db_error}")

        return {"status": True}
    except Exception as e:
        logger.error(f"[FLYER WEBHOOK] Error: {e}", exc_info=True)
        return {"status": True}


@router.get("")
async def flyer_webhook_check():
    """Health check for webhook endpoint."""
    return {
        "status": "ok",
        "message": "FlyerService webhook is active",
        "recent_events_count": len(_recent_events)
    }


@router.get("/events")
async def flyer_webhook_events():
    """Get recent webhook events for debugging."""
    return {
        "events": _recent_events[-20:],  # Last 20 events
        "total": len(_recent_events)
    }
