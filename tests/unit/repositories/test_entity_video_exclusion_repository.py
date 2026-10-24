"""SQL-artifact + behavior tests for EntityVideoExclusionRepository (Feature 091).

A mock session captures the emitted statement; assertions inspect the compiled SQL and
the return-value semantics (idempotent add, remove-hit). The ``execute`` result is a
plain ``MagicMock`` so the Result's sync methods (``.first()`` / ``.scalars()``) are not
mis-modeled as coroutines. Name-free (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.entity_video_exclusion_repository import (
    EntityVideoExclusionRepository,
)

pytestmark = pytest.mark.asyncio

_EID = uuid.UUID(int=1)
_VID = "placeholder01"


def _session(result: MagicMock) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result
    return session


def _captured(session: AsyncMock) -> Any:
    return session.execute.await_args.args[0]


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


class TestAdd:
    async def test_insert_is_idempotent_on_pair(self) -> None:
        session = _session(MagicMock(rowcount=1))
        created = await EntityVideoExclusionRepository().add(
            session, _EID, _VID, "user", reason="unrelated"
        )
        assert created is True
        sql = _sql(_captured(session))
        assert sql.startswith("INSERT INTO entity_video_exclusions")
        cols = sql.split("VALUES")[0]
        for col in ("entity_id", "video_id", "excluded_by", "reason"):
            assert col in cols, f"{col} missing from INSERT columns"
        assert "ON CONFLICT (entity_id, video_id) DO NOTHING" in sql

    async def test_already_excluded_returns_false(self) -> None:
        session = _session(MagicMock(rowcount=0))  # conflict → nothing inserted
        created = await EntityVideoExclusionRepository().add(
            session, _EID, _VID, "user"
        )
        assert created is False


class TestRemove:
    async def test_delete_scoped_to_pair(self) -> None:
        session = _session(MagicMock(rowcount=1))
        removed = await EntityVideoExclusionRepository().remove(session, _EID, _VID)
        assert removed is True
        sql = _sql(_captured(session))
        assert sql.startswith("DELETE FROM entity_video_exclusions")
        assert "entity_id" in sql and "video_id" in sql

    async def test_remove_miss_returns_false(self) -> None:
        session = _session(MagicMock(rowcount=0))
        removed = await EntityVideoExclusionRepository().remove(session, _EID, _VID)
        assert removed is False


class TestExists:
    async def test_true_when_row_present(self) -> None:
        result = MagicMock()
        result.first.return_value = (_EID,)
        session = _session(result)
        assert (
            await EntityVideoExclusionRepository().exists(session, _EID, _VID) is True
        )
        sql = _sql(_captured(session))
        assert "FROM entity_video_exclusions" in sql
        assert "entity_id" in sql and "video_id" in sql

    async def test_false_when_absent(self) -> None:
        result = MagicMock()
        result.first.return_value = None
        session = _session(result)
        assert (
            await EntityVideoExclusionRepository().exists(session, _EID, _VID) is False
        )


class TestListForEntity:
    async def test_orders_recent_first_and_paginates(self) -> None:
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session = _session(result)
        session.scalar.return_value = 0
        items, total = await EntityVideoExclusionRepository().list_for_entity(
            session, _EID, limit=50, offset=10
        )
        assert items == []
        assert total == 0
        sql = _sql(_captured(session))
        assert "FROM entity_video_exclusions" in sql
        assert "ORDER BY" in sql and "excluded_at" in sql and "DESC" in sql.upper()
        assert "LIMIT" in sql.upper() and "OFFSET" in sql.upper()
