"""The remaining-matches counts must stay index-eligible (#203).

`get_correction_patterns` issues one COUNT per correction pair, and applies
`limit` only *after* that loop, so every pair is scanned however few are
returned. Each count originally filtered on

    CASE WHEN has_correction THEN corrected_text ELSE text END LIKE '%phrase%'

A GIN trigram index cannot be used when LIKE targets a CASE expression, so each
iteration became a parallel sequential scan of the whole segment corpus:
measured at 100 pairs x ~105 ms = ~10.5 s, 83% of the endpoint's runtime.

The fix adds an index-eligible super-set over the RAW `text` / `corrected_text`
columns, keeping the CASE predicate as an exact re-check.

Both halves are load-bearing and neither is protected by a functional test:

* drop the **super-set** and every result stays correct while the query silently
  returns to a full scan — no assertion anywhere would fail;
* drop the **re-check** and it gets faster and quietly wrong, counting segments
  whose correction already removed the phrase.

So this asserts the shape of the emitted SQL, in the spirit of the
constitution's rule that unit tests for queries verify the columns rather than
just the return value.
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


def _pair_row(original: str = "acme corp", corrected: str = "Acme Corp") -> MagicMock:
    row = MagicMock()
    row.original_text = original
    row.corrected_text = corrected
    row.occurrences = 3
    return row


def _session_returning_one_pair() -> tuple[MagicMock, list[Any]]:
    """Session whose first execute yields one pair, and every later one a count.

    The captured statement list is what the assertions inspect.
    """
    captured: list[Any] = []
    session = MagicMock(spec=AsyncSession)

    pairs_result = MagicMock()
    pairs_result.all.return_value = [_pair_row()]

    count_result = MagicMock()
    count_result.scalar_one.return_value = 7

    async def _execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        captured.append(stmt)
        return pairs_result if len(captured) == 1 else count_result

    session.execute = AsyncMock(side_effect=_execute)
    return session, captured


def _remaining_sql(captured: list[Any]) -> str:
    """Compile the per-pair COUNT statement (the second execute)."""
    assert len(captured) >= 2, "expected a per-pair count query"
    return str(captured[1].compile(compile_kwargs={"literal_binds": False}))


class TestRemainingMatchesStaysIndexEligible:
    async def test_filters_the_raw_columns_so_the_trigram_index_can_be_used(
        self,
    ) -> None:
        """The super-set must name `text` AND `corrected_text` directly.

        Naming them only inside the CASE would satisfy a substring check while
        leaving the predicate opaque to the index, so the assertion below looks
        for the raw comparisons rather than for the column names alone.
        """
        session, captured = _session_returning_one_pair()
        await TranscriptCorrectionRepository().get_correction_patterns(
            session, min_occurrences=2, limit=25, show_completed=True
        )

        sql = _remaining_sql(captured)
        normalised = " ".join(sql.split()).lower()

        assert "transcript_segments.text like" in normalised, (
            "the raw `text` column is no longer filtered directly, so the "
            "pg_trgm index cannot be used and this count is a full seq scan"
        )
        assert (
            "transcript_segments.corrected_text like" in normalised
        ), "the raw `corrected_text` column is no longer filtered directly"

    async def test_keeps_the_case_expression_as_an_exact_recheck(self) -> None:
        """The super-set alone over-counts; the CASE re-check is what fixes that."""
        session, captured = _session_returning_one_pair()
        await TranscriptCorrectionRepository().get_correction_patterns(
            session, min_occurrences=2, limit=25, show_completed=True
        )

        normalised = " ".join(_remaining_sql(captured).split()).lower()

        assert "case when" in normalised, (
            "the CASE re-check is gone — the count now includes segments whose "
            "correction already removed the phrase"
        )
        assert "has_correction" in normalised

    async def test_the_raw_filter_is_a_union_not_an_intersection(self) -> None:
        """`text OR corrected_text`, never AND.

        AND would drop every uncorrected segment, because `corrected_text` is
        NULL for 99.77% of the corpus — a silent under-count rather than a
        slow query.
        """
        session, captured = _session_returning_one_pair()
        await TranscriptCorrectionRepository().get_correction_patterns(
            session, min_occurrences=2, limit=25, show_completed=True
        )

        normalised = " ".join(_remaining_sql(captured).split()).lower()
        start = normalised.index("transcript_segments.text like")
        end = normalised.index("transcript_segments.corrected_text like")
        between = normalised[start:end]

        assert " or " in between, "the raw-column candidate filter must be an OR"
