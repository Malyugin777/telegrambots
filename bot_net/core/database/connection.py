"""
Database connection and session management.
"""
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
from config import settings

from .models import Base


class Database:
    """Database connection manager."""

    def __init__(self, url: str | None = None):
        self.url = url or settings.database_url
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None

    async def connect(self) -> None:
        """Create engine and session factory."""
        self.engine = create_async_engine(
            self.url,
            echo=settings.debug,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def disconnect(self) -> None:
        """Close engine."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    async def create_tables(self) -> None:
        """Create all tables (for development)."""
        if self.engine is None:
            await self.connect()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        """Drop all tables (dangerous!)."""
        if self.engine is None:
            await self.connect()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if self.session_factory is None:
            await self.connect()

        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Dependency for FastAPI/Aiogram."""
        async with self.session() as session:
            yield session


# Global database instance
db = Database()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Shortcut for dependency injection."""
    async with db.session() as session:
        yield session
