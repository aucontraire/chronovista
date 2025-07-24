"""
Database configuration and connection management.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from chronovista.config.settings import settings
from chronovista.db.models import Base

# Metadata for migrations
metadata = Base.metadata


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker | None = None

    def get_engine(self) -> AsyncEngine:
        """Get or create async database engine."""
        if self._engine is None:
            # Use development database URL when in development mode
            database_url = settings.effective_database_url

            # Development-specific engine configuration
            engine_kwargs = {
                "echo": settings.debug or settings.db_log_queries,
                "future": True,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
            }

            # Optimize for development if using dev database
            if settings.is_development_database:
                engine_kwargs.update(
                    {
                        "pool_size": 5,  # Smaller pool for development
                        "max_overflow": 0,  # No overflow for development
                        "pool_timeout": 10,  # Shorter timeout for development
                    }
                )

            self._engine = create_async_engine(database_url, **engine_kwargs)
        return self._engine

    def get_session_factory(self) -> async_sessionmaker:
        """Get or create session factory."""
        if self._session_factory is None:
            engine = self.get_engine()
            self._session_factory = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return self._session_factory

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session."""
        session_factory = self.get_session_factory()
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self) -> None:
        """Close database connections."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        self._session_factory = None

    async def create_tables(self) -> None:
        """Create database tables."""
        engine = self.get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        """Drop database tables."""
        engine = self.get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    def get_sync_engine(self) -> Engine:
        """Get synchronous engine for Alembic migrations."""
        sync_url = settings.get_sync_database_url()
        return create_engine(sync_url, echo=settings.debug or settings.db_log_queries)


# Global database manager instance
db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session."""
    async for session in db_manager.get_session():
        yield session
