"""API routes package."""
from fastapi import APIRouter

from .stats import router as stats_router
from .bots import router as bots_router
from .users import router as users_router
from .broadcasts import router as broadcasts_router
from .auth import router as auth_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(stats_router, prefix="/stats", tags=["stats"])
api_router.include_router(bots_router, prefix="/bots", tags=["bots"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(broadcasts_router, prefix="/broadcasts", tags=["broadcasts"])
