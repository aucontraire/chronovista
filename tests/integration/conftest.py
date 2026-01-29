"""
Shared fixtures for integration tests.

Provides database session fixtures for migration and integration testing.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from chronovista.db.models import Base


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide database session for tests.

    Each test gets a fresh session with automatic cleanup for isolation.
    Creates and drops tables for each test to ensure clean state.
    """
    test_db_url = os.getenv(
        "DATABASE_INTEGRATION_URL",
        os.getenv(
            "CHRONOVISTA_INTEGRATION_DB_URL",
            "postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test",
        ),
    )

    engine = create_async_engine(
        test_db_url,
        echo=False,
        pool_pre_ping=True,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
