"""Candidate selection for archive recovery (Feature 065, FR-003).

These capture the statement the repository builds and compile it, rather than
asserting on a mocked return value. A mocked repository returning a list proves
only that the mock was configured; compiling the SQL proves the predicate says
what it is supposed to say.

**Assertions are scoped to the WHERE clause.** The query loads whole rows, so
every column name appears in the SELECT list — `"title" in sql` is true of a
bare ``select(Video)`` and stays true after the title disjunct is deleted. Two
assertions here were written against the whole statement and could not fail;
they are the reason this note exists.

Behavioural coverage — that a filled video is genuinely absent from the result
— lives in ``tests/integration/services/test_filmot_recovery_provenance.py``
(``TestSelectionExcludesFilledVideos``), against a real database.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.db.models import Video as VideoDB
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.recovery.merge_policy import placeholder_title_condition

pytestmark = pytest.mark.asyncio


async def _captured_sql(limit: int | None = None) -> str:
    """Run the selection and return the compiled SQL it issued."""
    session = AsyncMock()
    session.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    )

    await VideoRepository().get_filmot_candidates(
        session, placeholder_title_condition(VideoDB.title), limit=limit
    )

    statement: Any = session.execute.await_args.args[0]
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


async def _captured_where(limit: int | None = None) -> str:
    """The WHERE clause alone — the only part that selects anything."""
    sql = await _captured_sql(limit=limit)
    return sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]


class TestGapPredicate:
    async def test_every_gap_column_is_named(self) -> None:
        """A missing disjunct silently narrows the backlog."""
        where = await _captured_where()

        assert "title" in where
        assert "channel_id IS NULL" in where
        assert "duration IS NULL" in where

    async def test_both_placeholder_forms_reach_the_query(self) -> None:
        """FR-004c: the policy's condition, not a restatement."""
        where = await _captured_where()

        assert "https://www.youtube.com/watch%" in where
        assert "[Placeholder] Video %" in where

    async def test_null_and_blank_titles_are_covered(self) -> None:
        """`LIKE` cannot express these, so they are separate disjuncts.

        They now arrive as part of the policy's single condition rather than
        being reassembled here, which is what stopped the query, the policy and
        the write gate from spelling "blank" three different ways.
        """
        where = await _captured_where()

        assert "title IS NULL" in where
        assert "btrim" in where.lower()

    async def test_only_unavailable_videos_are_candidates(self) -> None:
        """FR-001. An available video has no business being sent anywhere."""
        where = await _captured_where()

        assert "availability_status" in where
        assert "!=" in where or "<>" in where


class TestOrderingAndLimit:
    async def test_ordering_matches_the_sibling_recovery_command(self) -> None:
        """Consistent operator experience across both recovery commands."""
        sql = await _captured_sql()

        assert "ORDER BY" in sql
        assert "unavailability_first_detected" in sql
        assert "created_at" in sql

    async def test_limit_is_applied_when_given(self) -> None:
        assert "LIMIT 25" in await _captured_sql(limit=25)

    async def test_no_limit_clause_when_unbounded(self) -> None:
        assert "LIMIT" not in await _captured_sql()


class TestSelectionIsByGapNotHistory:
    async def test_prior_recovery_is_not_filtered_on(self) -> None:
        """FR-003/FR-003a, asserted structurally.

        Selection must not *filter* on the attribution columns: doing so would
        make prior recovery a proxy for completeness, which it is not — an
        earlier run may have filled only the duration.
        """
        where = await _captured_where()

        assert "recovery_source" not in where
        assert "recovered_at" not in where
