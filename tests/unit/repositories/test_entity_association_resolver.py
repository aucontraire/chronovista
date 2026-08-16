"""SQL-shape guards for the canonical association resolver (Feature 066).

These inspect the *statements the resolver emits*, not just its return value
(Cross-Feature Data Contract §4). Correctness on real data is covered by the
integration suite (count consistency, video-panel parity); this file guards the
query shape that research.md calls out as this repo's scar tissue — a bounded
number of queries (never per-row) and no correlated `EXISTS` (which regressed
#56).

The session is mocked to return empty results and to record every statement it
is asked to execute; each is compiled and asserted against.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.repositories.entity_mention_repository import EntityMentionRepository

pytestmark = pytest.mark.asyncio


def _empty_result() -> MagicMock:
    r = MagicMock()
    r.all.return_value = []
    r.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    return r


async def _capture_sql(entity_ids: list[uuid.UUID]) -> list[str]:
    """Run the resolver with a recording mock session; return compiled SQL."""
    session = AsyncMock()
    captured: list[Any] = []

    async def _execute(stmt: Any, *a: Any, **k: Any) -> MagicMock:
        captured.append(stmt)
        return _empty_result()

    session.execute = _execute
    await EntityMentionRepository().association_triples(session, entity_ids)
    return [str(s.compile(compile_kwargs={"literal_binds": False})) for s in captured]


async def _capture_count_sql(entity_ids: list[uuid.UUID]) -> list[str]:
    """Run get_association_counts with a recording mock; return compiled SQL."""
    session = AsyncMock()
    captured: list[Any] = []

    async def _execute(stmt: Any, *a: Any, **k: Any) -> MagicMock:
        captured.append(stmt)
        return _empty_result()

    session.execute = _execute
    await EntityMentionRepository().get_association_counts(session, entity_ids)
    return [str(s.compile(compile_kwargs={"literal_binds": False})) for s in captured]


class TestQueryShape:
    async def test_empty_input_issues_no_queries(self) -> None:
        """A resolver that hits the database for an empty page is a latency bug."""
        assert await _capture_sql([]) == []

    async def test_bounded_query_count_not_per_row(self) -> None:
        """The count is fixed regardless of page size — never per-entity.

        Empty alias rows short-circuit the fourth (alias-matched-tag) query, so
        an all-empty mock issues three: mentions, canonical tags, aliases.
        """
        one = await _capture_sql([uuid.uuid4()])
        many = await _capture_sql([uuid.uuid4() for _ in range(25)])
        assert len(one) == len(many), "query count grows with page size"
        assert len(one) == 3

    async def test_no_correlated_exists(self) -> None:
        """Correlated EXISTS re-evaluated per row is the #56 regression."""
        for sql in await _capture_sql([uuid.uuid4(), uuid.uuid4()]):
            assert "EXISTS" not in sql.upper(), f"correlated-EXISTS shape: {sql[:120]}"

    async def test_mention_query_has_visible_name_join_and_source_label(self) -> None:
        """The mention path must filter by visible name and label the source."""
        sqls = await _capture_sql([uuid.uuid4()])
        mention_sql = next(s for s in sqls if "mention_source" in s)
        assert "lower(" in mention_sql.lower(), "visible-name match is case-folded"
        assert "CASE" in mention_sql.upper(), "manual vs stored source label"
        assert "DISTINCT" in mention_sql.upper()

    async def test_tag_query_joins_through_canonical_tag(self) -> None:
        """The canonical-tag path joins tag_aliases and video_tags, deduped."""
        sqls = await _capture_sql([uuid.uuid4()])
        tag_sql = next(s for s in sqls if "video_tags" in s and "canonical_tags" in s)
        assert "tag_aliases" in tag_sql
        assert "DISTINCT" in tag_sql.upper()


class TestCountAggregationShape:
    """The count path aggregates in SQL, not by materialising triples in Python."""

    async def test_counts_aggregate_in_sql_not_per_row(self) -> None:
        """One bounded aggregating query with COUNT(DISTINCT)/GROUP BY over a union.

        With an all-empty mock the alias arm short-circuits, so the counter
        issues two statements: the alias-fetch and the aggregating count query.
        Its shape is what keeps a heavy entity's thousands of rows inside
        Postgres rather than crossing into Python (the 2.4s→0.7s fix).
        """
        one = await _capture_count_sql([uuid.uuid4()])
        many = await _capture_count_sql([uuid.uuid4() for _ in range(25)])
        assert len(one) == len(many), "count query grows with page size"

        agg = next(s for s in one if "GROUP BY" in s.upper())
        assert "COUNT(DISTINCT" in agg.upper(), "distinct-video counting in SQL"
        assert "UNION ALL" in agg.upper(), "the association paths are unioned"
        assert "FILTER" in agg.upper(), "per-source breakdown via FILTER (WHERE ...)"

    async def test_count_query_has_no_correlated_exists(self) -> None:
        for sql in await _capture_count_sql([uuid.uuid4(), uuid.uuid4()]):
            assert "EXISTS" not in sql.upper(), f"correlated-EXISTS shape: {sql[:120]}"

    async def test_empty_input_issues_no_count_queries(self) -> None:
        assert await _capture_count_sql([]) == []
