"""
Pytest fixtures for unit model tests.

Provides database fixtures for testing SQLAlchemy models.
Falls back to PostgreSQL if SQLite async is not available.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from chronovista.db.models import Base


def get_test_db_url() -> str:
    """Get test database URL for PostgreSQL (required for JSONB columns).

    Note: SQLite cannot be used because the schema uses PostgreSQL-specific
    types like JSONB that are not supported by SQLite.
    """
    return os.getenv(
        "DATABASE_INTEGRATION_URL",
        os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test",
        ),
    )


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """
    Create an async database engine for testing.

    Uses SQLite in-memory if available, otherwise PostgreSQL.
    Each test gets a fresh database to ensure test isolation.
    """
    db_url = get_test_db_url()
    is_sqlite = "sqlite" in db_url

    engine = create_async_engine(
        db_url,
        echo=False,
        future=True,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Clean up
    if not is_sqlite:
        # For PostgreSQL, drop all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine):
    """
    Provide an async database session for testing.

    Creates a new session for each test and handles rollback on failure.
    """
    session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            # Rollback any pending transaction on teardown
            if session.in_transaction():
                await session.rollback()
