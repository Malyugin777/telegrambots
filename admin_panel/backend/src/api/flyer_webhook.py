"""
FlyerService webhook handler.

Receives callbacks from FlyerService when users complete subscription tasks.

Event types:
- test: webhook verification
- sub_completed: user completed mandatory subscription
- new_status (status=abort): user unsubscribed from channel
"""
import logging
from typing import Any, Dict
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Store recent events for debugging
_recent_events: list = []
MAX_EVENTS = 50


@router.post("")
async def flyer_webhook(request: Request):
    """
    Receive webhook from FlyerService.

    Must return {"status": true} for FlyerService to accept.
    """
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
            user_id = data.get("user_id")
            logger.info(f"[FLYER WEBHOOK] User {user_id} completed subscription!")
        elif event_type == "new_status":
            status = data.get("status")
            user_id = data.get("user_id")
            logger.info(f"[FLYER WEBHOOK] User {user_id} status changed to: {status}")

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
