from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from shared.config import settings

if TYPE_CHECKING:
    from shared.database.models import Base

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Alias for backward compatibility
AsyncSessionLocal = async_session


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    from shared.database.models import Base  # Local import to avoid circular dependency
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
