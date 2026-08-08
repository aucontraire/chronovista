"""
Database configuration and connection management.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import Engine, create_engine
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
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @staticmethod
    def _pool_kwargs() -> dict[str, int]:
        """Return connection pool settings based on environment.

        Development uses a small pool with no overflow for fast failure.
        Production uses a larger pool to handle concurrent status polling
        alongside long-running background tasks that hold sessions open.
        """
        if settings.is_development_database:
            return {"pool_size": 5, "max_overflow": 0, "pool_timeout": 10}
        return {"pool_size": 10, "max_overflow": 20, "pool_timeout": 30}

    def get_engine(self) -> AsyncEngine:
        """Get or create async database engine."""
        if self._engine is None:
            database_url = settings.effective_database_url

            engine_kwargs = {
                "echo": settings.db_log_queries,
                "future": True,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
                # Prevent runaway queries from holding connections indefinitely
                "connect_args": {"server_settings": {"statement_timeout": "60000"}},
                **self._pool_kwargs(),
            }

            self._engine = create_async_engine(database_url, **engine_kwargs)
        return self._engine

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get or create session factory."""
        if self._session_factory is None:
            engine = self.get_engine()
            self._session_factory = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return self._session_factory

    @asynccontextmanager
    async def session(self, echo: bool | None = None) -> AsyncIterator[AsyncSession]:
        """Session scope that commits on success and rolls back on failure.

        Prefer this over :meth:`get_session`. Because it is a context manager,
        leaving the block early — ``return``, ``break``, an exception — is
        ordinary control flow, and the commit still runs::

            async with db_manager.session() as session:
                await repo.create(session, obj_in=thing)
                return thing          # committed

        The generator form cannot offer that. Exiting an ``async for`` loop
        early throws ``GeneratorExit`` at the suspended ``yield``, so the
        ``await session.commit()`` after it never runs and the write is lost
        with no error at the call site.

        ``except BaseException`` rather than ``except Exception``: both
        ``GeneratorExit`` and ``asyncio.CancelledError`` derive from
        ``BaseException``, so the narrower form left a cancelled request — a
        client disconnecting mid-write — with no rollback at all.
        """
        temp_engine: AsyncEngine | None = None

        if echo is not None:
            # A distinct engine, because `echo` is fixed at engine construction.
            self.get_engine()
            engine_kwargs = {
                "echo": echo,
                "future": True,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
                **self._pool_kwargs(),
            }
            temp_engine = create_async_engine(
                settings.effective_database_url, **engine_kwargs
            )
            session_factory = async_sessionmaker(
                bind=temp_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        else:
            session_factory = self.get_session_factory()

        # One commit/rollback path for both branches. They were duplicated, so
        # the `except Exception` defect existed — and had to be fixed — twice.
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise
            finally:
                await session.close()
                if temp_engine is not None:
                    await temp_engine.dispose()

    async def get_session(
        self, echo: bool | None = None
    ) -> AsyncGenerator[AsyncSession, None]:
        """Generator form of :meth:`session`, for FastAPI's ``Depends``.

        FastAPI dependencies must be generators, so this form has to exist. It
        carries the early-exit hazard described in :meth:`session`: consumers
        writing ``async for s in db_manager.get_session(): ... break`` skip the
        commit. New code should use ``async with db_manager.session()``.
        """
        async with self.session(echo=echo) as session:
            yield session

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
        return create_engine(sync_url, echo=settings.db_log_queries)


# Global database manager instance
db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session."""
    async for session in db_manager.get_session():
        yield session


# Export for migrations
__all__ = ["Base", "db_manager", "get_db_session", "metadata"]
