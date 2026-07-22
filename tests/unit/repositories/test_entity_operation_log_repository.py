"""
Tests for EntityOperationLogRepository (Feature 057, T006).

Mock strategy: every test uses ``MagicMock(spec=AsyncSession)`` whose
``execute`` is an ``AsyncMock`` — no real database I/O. Mirrors
``test_tag_operation_log_repository.py``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.models.entity_operation_log import (
    EntityEditRollback,
    EntityEditSnapshot,
    EntityOperationLogCreate,
)
from chronovista.repositories.entity_operation_log_repository import (
    EntityOperationLogRepository,
)
from tests.factories.entity_operation_log_factory import create_entity_operation_log

pytestmark = pytest.mark.asyncio


def _uuid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


def _mock_session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


class TestGet:
    async def test_get_returns_entry(self) -> None:
        repo = EntityOperationLogRepository()
        session = _mock_session()
        log = create_entity_operation_log()
        result = MagicMock()
        result.scalar_one_or_none.return_value = log
        session.execute.return_value = result

        got = await repo.get(session, log.id)
        assert got is log
        session.execute.assert_awaited_once()

    async def test_get_missing_returns_none(self) -> None:
        repo = EntityOperationLogRepository()
        session = _mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        assert await repo.get(session, _uuid()) is None


class TestExists:
    async def test_exists_true(self) -> None:
        repo = EntityOperationLogRepository()
        session = _mock_session()
        result = MagicMock()
        result.first.return_value = (uuid7(),)
        session.execute.return_value = result
        assert await repo.exists(session, _uuid()) is True

    async def test_exists_false(self) -> None:
        repo = EntityOperationLogRepository()
        session = _mock_session()
        result = MagicMock()
        result.first.return_value = None
        session.execute.return_value = result
        assert await repo.exists(session, _uuid()) is False


class TestGetByEntity:
    async def test_returns_list(self) -> None:
        repo = EntityOperationLogRepository()
        session = _mock_session()
        entity_id = _uuid()
        logs = [
            create_entity_operation_log(entity_id=entity_id),
            create_entity_operation_log(entity_id=entity_id),
        ]
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = logs
        result.scalars.return_value = scalars
        session.execute.return_value = result

        got = await repo.get_by_entity(session, entity_id)
        assert got == logs
        session.execute.assert_awaited_once()


class TestCreate:
    async def test_create_adds_and_returns(self) -> None:
        repo = EntityOperationLogRepository()
        session = _mock_session()
        entity_id = _uuid()
        obj_in = EntityOperationLogCreate(
            entity_id=entity_id,
            rollback_data=EntityEditRollback(
                before=EntityEditSnapshot(canonical_name="Openai"),
                after=EntityEditSnapshot(canonical_name="OpenAI"),
                changed_fields=["canonical_name"],
            ),
            performed_by="user:local",
        )
        created = await repo.create(session, obj_in=obj_in)
        session.add.assert_called_once()
        assert created.entity_id == entity_id
        assert created.performed_by == "user:local"
        assert created.rollback_data["changed_fields"] == ["canonical_name"]


class TestMarkRolledBack:
    async def test_marks_and_stamps(self) -> None:
        repo = EntityOperationLogRepository()
        session = _mock_session()
        log = create_entity_operation_log(rolled_back=False, rolled_back_at=None)
        result = MagicMock()
        result.scalar_one_or_none.return_value = log
        session.execute.return_value = result

        got = await repo.mark_rolled_back(session, log.id)
        assert got is log
        assert log.rolled_back is True
        assert log.rolled_back_at is not None
        session.add.assert_called_once_with(log)
        session.flush.assert_awaited_once()

    async def test_missing_returns_none(self) -> None:
        repo = EntityOperationLogRepository()
        session = _mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        assert await repo.mark_rolled_back(session, _uuid()) is None
