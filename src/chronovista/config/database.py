"""
Database configuration and connection management.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from chronovista.config.settings import settings

logger = logging.getLogger(__name__)
from chronovista.db.models import Base

# Metadata for migrations
metadata = Base.metadata


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._read_only_engine: AsyncEngine | None = None

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

    def _get_read_only_engine(self) -> AsyncEngine:
        """A separate engine whose transactions the server starts read-only.

        ``default_transaction_read_only`` is a connection setting, so it covers
        every transaction on these connections, including one a caller opens after an
        unexpected ``commit()``. It lives on its own pool so it never reaches the
        read-write connections. It is a default, not a permission: deliberate SQL
        (``SET TRANSACTION READ WRITE``) can override it, which is why the session
        resets every setting before the connection returns to the pool.
        """
        if self._read_only_engine is None:
            self._read_only_engine = create_async_engine(
                settings.effective_database_url,
                # Read-only callers handle library keys; never log their SQL or
                # put bound parameters in an exception message.
                echo=False,
                hide_parameters=True,
                future=True,
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={
                    "server_settings": {
                        "statement_timeout": "60000",
                        "default_transaction_read_only": "on",
                    }
                },
                **self._pool_kwargs(),
            )
        return self._read_only_engine

    @asynccontextmanager
    async def session(
        self, echo: bool | None = None, *, read_only: bool = False
    ) -> AsyncIterator[AsyncSession]:
        """Session scope that commits on success and rolls back on failure.

        ``read_only=True`` opens the session on connections whose transactions the
        database starts read-only, and always rolls back, so an accidental write or a
        stray ``commit()`` cannot change data. Only deliberate SQL could override it,
        and every setting is reset before the connection is reused. Read-only
        commands use it instead of relying on their own dry-run conventions (``echo``
        is ignored with it).

        The single supported way to open a session. Because it is a context
        manager, leaving the block early — ``return``, ``break``, an exception
        — is ordinary control flow, and the commit still runs::

            async with db_manager.session() as session:
                await repo.create(session, obj_in=thing)
                return thing          # committed

        An ``async for`` over a session *generator* could not offer that:
        exiting the loop early throws ``GeneratorExit`` at the suspended
        ``yield``, so the trailing ``await session.commit()`` never runs and
        the write is lost with no error at the call site (issue #189, #233).

        ``except BaseException`` rather than ``except Exception``: both
        ``GeneratorExit`` and ``asyncio.CancelledError`` derive from
        ``BaseException``, so the narrower form left a cancelled request — a
        client disconnecting mid-write — with no rollback at all.
        """
        temp_engine: AsyncEngine | None = None

        if read_only:
            read_only_factory = async_sessionmaker(
                bind=self._get_read_only_engine(),
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with read_only_factory() as session:
                try:
                    yield session
                finally:
                    await session.rollback()
                    # Undo any SET the caller ran, so it never reaches the next user.
                    # Committed, because rolling back would undo the RESET too; the
                    # transaction holds nothing else. If the connection is broken,
                    # drop it instead, without hiding the caller's own error.
                    try:
                        await session.execute(text("RESET ALL"))
                        await session.commit()
                    except Exception:  # noqa: BLE001 — cleanup must not mask an error
                        logger.warning(
                            "read-only session reset failed; connection dropped"
                        )
                        await session.invalidate()
                    await session.close()
            return

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

    async def close(self) -> None:
        """Close database connections."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        self._session_factory = None
        if self._read_only_engine is not None:
            await self._read_only_engine.dispose()
            self._read_only_engine = None

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
    async with db_manager.session() as session:
        yield session


# Export for migrations
__all__ = ["Base", "db_manager", "get_db_session", "metadata"]
