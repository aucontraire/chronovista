"""SQL-artifact tests for EntityCategoryRepository / WikipediaCategoryRepository.

A mock session captures the emitted statement; assertions inspect the compiled SQL
and bound parameters rather than the mock's return value.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.entity_category_repository import (
    EntityCategoryRepository,
)
from chronovista.repositories.wikipedia_category_repository import (
    WikipediaCategoryRepository,
)

pytestmark = pytest.mark.asyncio


def _captured(session: AsyncMock) -> Any:
    session.execute.assert_awaited_once()
    return session.execute.await_args.args[0]


def _compile(stmt: Any) -> Any:
    return stmt.compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]


class TestEntityCategoryAddSql:
    async def test_insert_targets_all_columns_with_on_conflict_do_nothing(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        entity_id, category_id = uuid.uuid4(), uuid.uuid4()
        when = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

        await EntityCategoryRepository().add(
            session, entity_id, category_id, "dbpedia", when
        )

        compiled = _compile(_captured(session))
        sql = str(compiled)
        assert sql.startswith("INSERT INTO entity_categories")
        for col in ("entity_id", "category_id", "source", "set_at"):
            assert col in sql.split("VALUES")[0], f"{col} missing from INSERT columns"
        assert "ON CONFLICT (entity_id, category_id) DO NOTHING" in sql
        assert compiled.params == {
            "entity_id": entity_id,
            "category_id": category_id,
            "source": "dbpedia",
            "set_at": when,
        }

    async def test_set_at_defaults_to_none(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        await EntityCategoryRepository().add(
            session, uuid.uuid4(), uuid.uuid4(), "dbpedia"
        )
        assert _compile(_captured(session)).params["set_at"] is None


class TestDeleteForEntitySql:
    """Feature 084 replace path: the DELETE must be scoped to the one entity (Cross-Feature)."""

    async def test_delete_is_scoped_to_entity_id(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.rowcount = 3
        session.execute.return_value = result
        entity_id = uuid.uuid4()

        removed = await EntityCategoryRepository().delete_for_entity(session, entity_id)

        compiled = _compile(_captured(session))
        sql = str(compiled)
        assert sql.startswith("DELETE FROM entity_categories")
        # Scoped by entity_id — it must never remove another entity's rows.
        assert "WHERE entity_categories.entity_id =" in sql
        assert entity_id in compiled.params.values()
        assert removed == 3  # returns the row count removed

    async def test_null_rowcount_returns_zero(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.rowcount = None
        session.execute.return_value = result
        removed = await EntityCategoryRepository().delete_for_entity(
            session, uuid.uuid4()
        )
        assert removed == 0


class TestBridgeSql:
    async def _bridge_sql(self, cap: int | None) -> tuple[str, Any]:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        entity_id = uuid.uuid4()
        out = await EntityCategoryRepository().shared_category_bridge(
            session, entity_id, cap
        )
        assert out == []
        compiled = _compile(_captured(session))
        return str(compiled), compiled

    async def test_uncapped_has_no_size_predicate_but_excludes_self(self) -> None:
        sql, _ = await self._bridge_sql(None)
        assert "global_size <=" not in sql
        assert "IS NOT NULL" not in sql
        assert "!=" in sql  # self-exclusion

    async def test_capped_binds_cap_and_requires_known_size(self) -> None:
        sql, compiled = await self._bridge_sql(250)
        assert "global_size IS NOT NULL" in sql
        assert "global_size <=" in sql
        assert 250 in compiled.params.values()


class TestWikipediaCategorySql:
    async def test_upsert_conflicts_on_name_do_nothing(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = WikipediaCategoryRepository()
        repo.get_by_name = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
        await repo.upsert(session, "cat-x")
        compiled = _compile(_captured(session))
        assert "ON CONFLICT (name) DO NOTHING" in str(compiled)
        assert compiled.params["name"] == "cat-x"

    async def test_set_global_size_sets_size_and_fetched_at_only(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        cid = uuid.uuid4()
        when = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
        await WikipediaCategoryRepository().set_global_size(session, cid, 42, when)
        compiled = _compile(_captured(session))
        set_clause = str(compiled).split("SET")[1].split("WHERE")[0]
        assert "global_size" in set_clause
        assert "global_size_fetched_at" in set_clause
        assert "name" not in set_clause
        assert 42 in compiled.params.values()
        assert cid in compiled.params.values()
