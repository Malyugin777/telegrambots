"""
Nexus Control - Admin API
FastAPI application entry point.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import engine
from .redis_client import close_redis
from .api import api_router
from . import models


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    print("Database tables created")

    yield

    # Shutdown
    await engine.dispose()
    await close_redis()
    print("Connections closed")


app = FastAPI(
    title="Nexus Control API",
    description="Admin API for Telegram Bot Network",
    version="1.0.0",
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    openapi_url="/api/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "nexus-control-api"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Nexus Control API",
        "version": "1.0.0",
        "docs": "/api/docs" if settings.debug else "disabled",
    }
