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
    This endpoint just acknowledges the request - FlyerService handles the subscription tracking.
    """
    try:
        # Get raw body for logging
        body = await request.json()
        logger.info(f"[FLYER WEBHOOK] Received: {body}")

        # Just acknowledge - FlyerService handles the logic
        return JSONResponse(
            content={"success": True},
            status_code=200
        )
    except Exception as e:
        logger.error(f"[FLYER WEBHOOK] Error: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=200  # Return 200 anyway to not break FlyerService
        )


@router.get("")
async def flyer_webhook_check():
    """Health check for webhook endpoint."""
    return {"status": "ok", "message": "FlyerService webhook is active"}
