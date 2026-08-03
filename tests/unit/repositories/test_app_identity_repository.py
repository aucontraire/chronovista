"""Tests for AppIdentityRepository (Feature 060, T011).

Mock strategy: ``MagicMock(spec=AsyncSession)`` with ``AsyncMock`` execute —
no real database I/O (mirrors test_entity_operation_log_repository.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.models.app_identity import (
    AppIdentitySource,
    AppIdentityUpdate,
)
from chronovista.repositories.app_identity_repository import AppIdentityRepository
from tests.factories.app_identity_factory import create_app_identity_create

pytestmark = pytest.mark.asyncio


def _mock_session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


class TestGetIdentity:
    async def test_returns_row_when_present(self) -> None:
        repo = AppIdentityRepository()
        session = _mock_session()
        row = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = row
        session.execute.return_value = result

        got = await repo.get_identity(session)
        assert got is row
        session.execute.assert_awaited_once()

    async def test_returns_none_when_absent(self) -> None:
        repo = AppIdentityRepository()
        session = _mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        assert await repo.get_identity(session) is None


class TestSetIdentity:
    async def test_persists_singleton_with_id_1(self) -> None:
        repo = AppIdentityRepository()
        session = _mock_session()

        created = await repo.set_identity(
            session,
            obj_in=create_app_identity_create(
                user_id="UCzYTmeK-6v3DcJ6hzRh1q9w",
                source=AppIdentitySource.CHANNEL,
            ),
        )

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert created.id == 1
        assert created.user_id == "UCzYTmeK-6v3DcJ6hzRh1q9w"
        # source stored as the enum's string value
        assert created.source == "channel"

    async def test_local_constant_source(self) -> None:
        repo = AppIdentityRepository()
        session = _mock_session()
        created = await repo.set_identity(
            session,
            obj_in=create_app_identity_create(
                user_id="local_user", source=AppIdentitySource.LOCAL_CONSTANT
            ),
        )
        assert created.source == "local_constant"


class TestUpdateIdentity:
    async def test_returns_none_when_unestablished(self) -> None:
        repo = AppIdentityRepository()
        session = _mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        got = await repo.update_identity(
            session, obj_in=AppIdentityUpdate(user_id="UCnew")
        )
        assert got is None

    async def test_updates_existing_and_maps_enum(self) -> None:
        repo = AppIdentityRepository()
        session = _mock_session()

        existing = MagicMock()
        existing.user_id = "local_user"
        existing.source = "local_constant"
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        session.execute.return_value = result

        await repo.update_identity(
            session,
            obj_in=AppIdentityUpdate(
                user_id="UCzYTmeK-6v3DcJ6hzRh1q9w", source=AppIdentitySource.CHANNEL
            ),
        )
        assert existing.user_id == "UCzYTmeK-6v3DcJ6hzRh1q9w"
        # enum mapped to its string value on the ORM object
        assert existing.source == "channel"
        session.flush.assert_awaited_once()
