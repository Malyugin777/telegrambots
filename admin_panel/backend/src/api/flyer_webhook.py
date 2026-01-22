"""
FlyerService webhook handler.

Receives callbacks from FlyerService when users complete subscription tasks.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("")
async def flyer_webhook(request: Request):
    """
    Receive webhook from FlyerService.

    FlyerService sends POST requests when users complete tasks (subscribe to channels).
    Must return {"status": true} for FlyerService to accept the webhook.
    """
    try:
        # Get raw body for logging
        body = await request.json()
        logger.info(f"[FLYER WEBHOOK] Received: {body}")

        # FlyerService requires exactly {"status": true}
        return {"status": True}
    except Exception as e:
        logger.error(f"[FLYER WEBHOOK] Error: {e}")
        # Still return status: true to not break FlyerService
        return {"status": True}


@router.get("")
async def flyer_webhook_check():
    """Health check for webhook endpoint."""
    return {"status": "ok", "message": "FlyerService webhook is active"}
