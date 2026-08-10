"""`with_remaining=False` must actually skip the counting (#213).

Counting remaining matches is the whole cost of `get_correction_patterns`:
measured over 106 pairs on a ~2M-segment corpus at 4.68s, against 0.13s for the
grouping query that precedes it. Two of the three callers never read the
result — the diff-analysis endpoint recomputes it per token, and cross-segment
discovery reads only `original_text`.

The saving is entirely in *queries not issued*, so a test that only checked the
returned values would pass against an implementation that still ran all 106
counts and then discarded them. These assert the query count instead.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)

pytestmark = pytest.mark.asyncio


def _pair(original: str, corrected: str, occurrences: int) -> MagicMock:
    row = MagicMock()
    row.original_text = original
    row.corrected_text = corrected
    row.occurrences = occurrences
    return row


def _session(pairs: list[MagicMock], remaining: int = 4) -> tuple[MagicMock, list[Any]]:
    """First execute returns the grouped pairs; any later one returns a count."""
    captured: list[Any] = []
    session = MagicMock(spec=AsyncSession)

    pairs_result = MagicMock()
    pairs_result.all.return_value = pairs

    count_result = MagicMock()
    count_result.scalar_one.return_value = remaining

    async def _execute(stmt: Any, *a: Any, **kw: Any) -> Any:
        captured.append(stmt)
        return pairs_result if len(captured) == 1 else count_result

    session.execute = AsyncMock(side_effect=_execute)
    return session, captured


THREE_PAIRS = [
    _pair("aaa", "AAA", 5),
    _pair("bbb", "BBB", 50),
    _pair("ccc", "CCC", 12),
]


class TestSkipsTheCountQueries:
    async def test_issues_only_the_grouping_query(self) -> None:
        """One query total, not one per pair — this is the entire point."""
        session, captured = _session(list(THREE_PAIRS))
        await TranscriptCorrectionRepository().get_correction_patterns(
            session, show_completed=True, with_remaining=False
        )

        assert len(captured) == 1, (
            f"expected 1 query (the grouping query) but {len(captured)} were "
            "issued — the per-pair counts are still running"
        )

    async def test_counting_is_still_the_default(self) -> None:
        """Callers that do not opt out keep the previous behaviour exactly."""
        session, captured = _session(list(THREE_PAIRS))
        await TranscriptCorrectionRepository().get_correction_patterns(
            session, show_completed=True
        )

        assert len(captured) == 1 + len(THREE_PAIRS)

    async def test_remaining_is_none_not_zero(self) -> None:
        """Unknown and none-remaining are different facts.

        Reporting 0 for a count that was never taken would read as "this
        correction has been fully applied", which is the opposite conclusion.
        """
        session, _ = _session(list(THREE_PAIRS))
        patterns = await TranscriptCorrectionRepository().get_correction_patterns(
            session, show_completed=True, with_remaining=False
        )

        assert patterns, "expected patterns back"
        assert all(p.remaining_matches is None for p in patterns)


class TestOrdering:
    async def test_orders_by_occurrences_when_counts_are_skipped(self) -> None:
        """The old sort key is unavailable, so fall back to a meaningful one."""
        session, _ = _session(list(THREE_PAIRS))
        patterns = await TranscriptCorrectionRepository().get_correction_patterns(
            session, show_completed=True, with_remaining=False
        )

        assert [p.occurrences for p in patterns] == [50, 12, 5]

    async def test_limit_applies_after_ordering(self) -> None:
        """Otherwise the limit would drop the highest-occurrence patterns."""
        session, _ = _session(list(THREE_PAIRS))
        patterns = await TranscriptCorrectionRepository().get_correction_patterns(
            session, limit=2, show_completed=True, with_remaining=False
        )

        assert [p.occurrences for p in patterns] == [50, 12]


class TestIncoherentCombinationIsRefused:
    async def test_show_completed_false_requires_the_counts(self) -> None:
        """`show_completed=False` filters on a count that would not exist.

        Silently returning everything would look like a working filter, which
        is worse than refusing.
        """
        session, captured = _session(list(THREE_PAIRS))

        with pytest.raises(ValueError, match="show_completed=False requires"):
            await TranscriptCorrectionRepository().get_correction_patterns(
                session, show_completed=False, with_remaining=False
            )

        assert captured == [], "refused before touching the database"

    async def test_the_default_combination_is_allowed(self) -> None:
        """show_completed=False with counting is the pre-existing default."""
        session, _ = _session(list(THREE_PAIRS))
        await TranscriptCorrectionRepository().get_correction_patterns(
            session, show_completed=False
        )
