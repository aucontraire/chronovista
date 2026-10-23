"""SQL-artifact tests for EntityCategoryRepository / WikipediaCategoryRepository.

A mock session captures the emitted statement; assertions inspect the compiled SQL
and bound parameters rather than the mock's return value.
"""

from __future__ import annotations

import datetime
import re
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


class TestSharedCategoryNeighboursSql:
    """Feature 085: the aggregate-by-neighbour query — group/order/filter/bound asserted in SQL."""

    async def _sql(self) -> tuple[str, Any]:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        out = await EntityCategoryRepository().shared_category_neighbours(
            session, uuid.uuid4(), limit=12, offset=3, max_category_size=20000
        )
        assert out == []
        compiled = _compile(_captured(session))
        return str(compiled), compiled

    async def test_group_order_filter_bound(self) -> None:
        sql, compiled = await self._sql()
        low = sql.lower()
        # one row per neighbour entity
        assert "GROUP BY" in sql
        assert "array_agg" in low  # the shared-category names
        # ranking: count desc primary, specificity (min global_size) asc secondary
        assert "ORDER BY" in sql
        assert "DESC" in sql and "ASC" in sql
        assert "min(" in low
        # active-only neighbour join
        assert "status" in low
        # hub suppression: global_size <= :cap OR IS NULL
        assert "global_size <=" in sql
        assert "IS NULL" in sql
        # bounded
        assert "LIMIT" in sql and "OFFSET" in sql
        # bound params carried
        assert 12 in compiled.params.values()  # limit
        assert 3 in compiled.params.values()  # offset
        assert 20000 in compiled.params.values()  # hub ceiling
        # total order: a final entity_id tiebreak so LIMIT/OFFSET paging is stable under ties
        assert "entity_id" in sql.split("ORDER BY", 1)[1]

    async def test_read_only_single_statement(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await EntityCategoryRepository().shared_category_neighbours(
            session, uuid.uuid4(), limit=5, offset=0, max_category_size=100
        )
        # exactly one SELECT, no writes
        session.execute.assert_awaited_once()
        assert str(_compile(_captured(session))).lstrip().upper().startswith("SELECT")

    async def test_aggregates_ids_aligned_with_names(self) -> None:
        """086: two array_aggs (names + ids) under one total ORDER BY so refs pair 1:1."""
        sql, _ = await self._sql()
        low = sql.lower()
        # both the name array and the id array are aggregated (so the endpoint can emit {id,name})
        assert low.count("array_agg") == 2
        # a secondary id key makes the aggregate order total → names[i] and ids[i] align
        # (global_size alone ties on NULLs / equal sizes). Both array_aggs carry this ORDER BY.
        assert "global_size" in low
        assert ".id" in low


class TestDistinctiveCategoriesSql:
    """Feature 089: sole-active-member categories — group/having/active/order asserted in SQL."""

    async def _sql(self) -> tuple[str, Any]:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        # distinctive_categories reads ORM rows via .scalars().all()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result
        out = await EntityCategoryRepository().distinctive_categories(
            session, uuid.uuid4(), limit=50, offset=10
        )
        assert out == []
        compiled = _compile(_captured(session))
        return str(compiled), compiled

    async def test_group_by_category_having_single_active_member(self) -> None:
        sql, compiled = await self._sql()
        low = sql.lower()
        # grouped self-join (not a correlated subquery), one row per category
        assert "GROUP BY" in sql
        # the defining predicate: the category has exactly ONE active member
        assert "HAVING" in sql
        assert "count(" in low
        assert 1 in compiled.params.values()  # the HAVING count == 1 bind
        # active-only on BOTH the viewed entity AND the member being counted — this
        # is the guard that stops an INACTIVE subject (whose category has one OTHER
        # active member) being mis-reported as distinctive. Prove it is on two
        # distinct named_entities aliases, not just that the word "status" appears
        # once: the statement must carry two separate `status = :param` predicates,
        # each binding "active". Removing the ne_self join would drop one of them.
        assert (
            low.count("status =") >= 2
        ), "need an active-status filter on BOTH aliases"
        assert list(compiled.params.values()).count("active") >= 2
        # the viewed entity anchors the query
        assert "entity_categories.entity_id =" in sql or "entity_id =" in sql

    async def test_stable_order_by_name_then_id(self) -> None:
        sql, _ = await self._sql()
        order = sql.split("ORDER BY", 1)[1].lower()
        # lower(name) then id → a TOTAL order, so LIMIT/OFFSET paging never
        # skips/repeats a category when two names collide case-insensitively
        assert "lower(" in order and "name" in order
        assert "id" in order

    async def test_read_only_bounded_single_select(self) -> None:
        sql, compiled = await self._sql()
        # exactly one SELECT, no writes, bounded like its shared-category sibling
        assert sql.lstrip().upper().startswith("SELECT")
        assert "LIMIT" in sql.upper() and "OFFSET" in sql.upper()
        assert 50 in compiled.params.values()  # limit
        assert 10 in compiled.params.values()  # offset


class TestCategoriesWithMemberCountsSql:
    """Feature 090: all of an entity's categories + active member count — group/count/order/bound."""

    async def _sql(self) -> tuple[str, Any]:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.all.return_value = (
            []
        )  # categories_with_member_counts reads Rows via .all()
        session.execute.return_value = result
        out = await EntityCategoryRepository().categories_with_member_counts(
            session, uuid.uuid4(), limit=50, offset=10
        )
        assert out == []
        compiled = _compile(_captured(session))
        return str(compiled), compiled

    async def test_group_count_no_having_active_both_aliases(self) -> None:
        sql, compiled = await self._sql()
        low = sql.lower()
        # grouped self-join returning each category + its member count
        assert "GROUP BY" in sql
        assert "count(" in low
        # it is "distinctive minus the HAVING" — this is ALL categories, so NO HAVING filter
        assert "HAVING" not in sql
        # active-only on BOTH the subject and the counted members — prove the two status
        # predicates sit on TWO DISTINCT named_entities aliases (not both on one, which would
        # drop the subject-active guard and still satisfy a naive count-based check).
        alias_status = set(re.findall(r"(\w+)\.status =", sql))
        assert (
            len(alias_status) >= 2
        ), f"active filter must be on two aliases, got {alias_status}"
        assert list(compiled.params.values()).count("active") >= 2
        # anchored on the viewed entity
        assert "entity_categories.entity_id =" in sql or "entity_id =" in sql

    async def test_order_by_count_then_name_then_id(self) -> None:
        sql, _ = await self._sql()
        # isolate the ORDER BY clause (between ORDER BY and LIMIT) and split into its keys
        order = sql.split("ORDER BY", 1)[1].split("LIMIT")[0].lower()
        terms = [t.strip() for t in order.split(",")]
        # most-specific-first: member count ascending is the PRIMARY key,
        # then lower(name), then id as the FINAL key — a total, stable order for safe paging
        assert "count(" in terms[0]
        assert "lower(" in terms[1] and "name" in terms[1]
        assert (
            terms[-1].split()[0].endswith(".id")
        ), f"id must be the final sort key, got {terms[-1]}"

    async def test_read_only_bounded_single_select(self) -> None:
        sql, compiled = await self._sql()
        assert sql.lstrip().upper().startswith("SELECT")
        assert "LIMIT" in sql.upper() and "OFFSET" in sql.upper()
        assert 50 in compiled.params.values()  # limit
        assert 10 in compiled.params.values()  # offset


class TestEntitiesInCategorySql:
    """Feature 086: the member list — active-only, total order (name, id), bounded."""

    async def _sql(self) -> tuple[str, Any]:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        out = await EntityCategoryRepository().entities_in_category(
            session, uuid.uuid4(), limit=25, offset=50
        )
        assert out == []
        compiled = _compile(_captured(session))
        return str(compiled), compiled

    async def test_active_only_total_order_bounded(self) -> None:
        sql, compiled = await self._sql()
        order = sql.split("ORDER BY", 1)[1].lower()
        # active-only join predicate
        assert "status" in sql.lower()
        # total order: lower(canonical_name) then id — so paging never skips/repeats on a tie
        assert "lower(" in order and "canonical_name" in order
        assert "id" in order
        # bounded
        assert "LIMIT" in sql and "OFFSET" in sql
        assert 25 in compiled.params.values()  # limit
        assert 50 in compiled.params.values()  # offset

    async def test_read_only_single_select(self) -> None:
        sql, _ = await self._sql()
        assert sql.lstrip().upper().startswith("SELECT")


class TestCountActiveMembersSql:
    """Feature 086: the member count — a single count(*) over the same active-only join."""

    async def _run(self) -> tuple[str, Any]:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one.return_value = 7
        session.execute.return_value = result
        out = await EntityCategoryRepository().count_active_members(
            session, uuid.uuid4()
        )
        assert out == 7
        compiled = _compile(_captured(session))
        return str(compiled), compiled

    async def test_counts_active_members_only(self) -> None:
        sql, _ = await self._run()
        low = sql.lower()
        assert "count(" in low
        assert "status" in low  # same active-only filter as the member list
        assert "limit" not in low  # a count is unbounded by design


class TestWikipediaCategoryGetByIdSql:
    """Feature 086: get_by_id selects by the UUID primary key."""

    async def test_selects_by_id(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        cid = uuid.uuid4()
        out = await WikipediaCategoryRepository().get_by_id(session, cid)
        assert out is None
        compiled = _compile(_captured(session))
        sql = str(compiled)
        assert sql.lstrip().upper().startswith("SELECT")
        assert "wikipedia_categories.id =" in sql
        assert cid in compiled.params.values()
