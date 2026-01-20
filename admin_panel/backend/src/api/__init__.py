"""API routes package."""
from fastapi import APIRouter

from .stats import router as stats_router
from .bots import router as bots_router
from .users import router as users_router
from .broadcasts import router as broadcasts_router
from .auth import router as auth_router
from .logs import router as logs_router
from .errors import router as errors_router
from .uploads import router as uploads_router
from .subscriptions import router as subscriptions_router
from .bot_messages import router as bot_messages_router
from .ops import router as ops_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(stats_router, prefix="/stats", tags=["stats"])
api_router.include_router(bots_router, prefix="/bots", tags=["bots"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(broadcasts_router, prefix="/broadcasts", tags=["broadcasts"])
api_router.include_router(logs_router, prefix="/logs", tags=["logs"])
api_router.include_router(errors_router, prefix="/errors", tags=["errors"])
api_router.include_router(uploads_router, prefix="/uploads", tags=["uploads"])
api_router.include_router(subscriptions_router, prefix="/subscriptions", tags=["subscriptions"])
api_router.include_router(bot_messages_router, prefix="/bot-messages", tags=["bot-messages"])
api_router.include_router(ops_router, prefix="/ops", tags=["ops"])
