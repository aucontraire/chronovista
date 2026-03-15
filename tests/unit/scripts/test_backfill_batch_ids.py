"""
Unit tests for scripts/utilities/backfill_batch_ids.py.

Verifies the pure business-logic functions (``identify_batches``,
``_group_key``, ``fetch_unassigned_corrections``, ``assign_batch_id``,
``run_backfill``) and the CLI parser without touching a real database.

All database I/O is mocked — these are unit tests only.

References
----------
- T019 [US2]: Unit tests for backfill script logic (Feature 045)
- scripts/utilities/backfill_batch_ids.py
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
#
# This file contains a mix of synchronous (pure unit logic) and async (I/O
# mock) tests.  Synchronous classes have all synchronous methods; async
# classes use async def.  The module-level marker is set to asyncio so that
# all async tests run correctly with pytest-cov.  Sync tests receive the
# marker too, which produces benign warnings but does NOT affect correctness.
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Lazy imports from the script (avoids sys.path manipulation at import time
# since the script bootstraps its own path).  The script adds ``src/`` on
# first import, so we do a direct import after ensuring the path is set.
# ---------------------------------------------------------------------------

from scripts.utilities.backfill_batch_ids import (  # noqa: E402
    DEFAULT_WINDOW_SECONDS,
    BatchGroup,
    CorrectionRow,
    assign_batch_id,
    build_parser,
    fetch_unassigned_corrections,
    identify_batches,
    run_backfill,
    _group_key,
    _display_summary,
)

from tests.factories.transcript_correction_factory import (
    TranscriptCorrectionFactory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(
    id: str = "row-1",
    corrected_by_user_id: str | None = "cli",
    original_text: str = "teh quick brown fox",
    corrected_text: str = "the quick brown fox",
    corrected_at: datetime | None = None,
) -> CorrectionRow:
    """Build a CorrectionRow with sensible defaults.

    Parameters
    ----------
    id : str
        The correction's UUID string.
    corrected_by_user_id : str | None
        User ID who made the correction (None treated as distinct NULL group).
    original_text : str
        Original (uncorrected) text.
    corrected_text : str
        Corrected text after applying the change.
    corrected_at : datetime | None
        Timestamp; defaults to ``2024-01-01T10:00:00Z`` if not provided.

    Returns
    -------
    CorrectionRow
        Lightweight data container for one correction row.
    """
    if corrected_at is None:
        corrected_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    return CorrectionRow(
        id=id,
        corrected_by_user_id=corrected_by_user_id,
        original_text=original_text,
        corrected_text=corrected_text,
        corrected_at=corrected_at,
    )


def _at(seconds_offset: float) -> datetime:
    """Return a UTC datetime offset from the base time by ``seconds_offset``.

    Parameters
    ----------
    seconds_offset : float
        Number of seconds after the anchor ``2024-01-01T10:00:00Z``.

    Returns
    -------
    datetime
        Base time plus the given offset.
    """
    base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(seconds=seconds_offset)


# ---------------------------------------------------------------------------
# TestGroupKey
# ---------------------------------------------------------------------------


class TestGroupKey:
    """Unit tests for the ``_group_key`` helper."""

    def test_returns_tuple_of_user_original_corrected(self) -> None:
        """Key must be (corrected_by_user_id, original_text, corrected_text)."""
        row = _make_row(
            corrected_by_user_id="cli",
            original_text="abc",
            corrected_text="ABC",
        )
        assert _group_key(row) == ("cli", "abc", "ABC")

    def test_none_user_id_in_key(self) -> None:
        """NULL corrected_by_user_id must appear as None in the group key."""
        row = _make_row(corrected_by_user_id=None)
        key = _group_key(row)
        assert key[0] is None

    def test_different_texts_produce_different_keys(self) -> None:
        """Two rows differing only in ``original_text`` must have distinct keys."""
        row_a = _make_row(original_text="foo", corrected_text="bar")
        row_b = _make_row(original_text="baz", corrected_text="bar")
        assert _group_key(row_a) != _group_key(row_b)

    def test_same_fields_produce_equal_keys(self) -> None:
        """Two rows with identical grouping fields must produce the same key."""
        row_a = _make_row(id="id-1", corrected_by_user_id="u", original_text="x", corrected_text="y")
        row_b = _make_row(id="id-2", corrected_by_user_id="u", original_text="x", corrected_text="y")
        assert _group_key(row_a) == _group_key(row_b)


# ---------------------------------------------------------------------------
# TestIdentifyBatchesGrouping
# ---------------------------------------------------------------------------


class TestIdentifyBatchesGrouping:
    """Tests for grouping heuristic in ``identify_batches``."""

    def test_empty_corrections_returns_empty(self) -> None:
        """Empty input must return an empty list."""
        result = identify_batches([], window_seconds=5.0)
        assert result == []

    def test_two_identical_group_within_window_forms_batch(self) -> None:
        """Two corrections with same key within window_seconds form a single batch."""
        rows = [
            _make_row(id="a", corrected_at=_at(0)),
            _make_row(id="b", corrected_at=_at(3)),  # 3s gap < 5s window
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert len(batches) == 1
        assert set(batches[0].correction_ids) == {"a", "b"}

    def test_single_correction_produces_no_batch(self) -> None:
        """A group with only one correction must NOT produce a batch."""
        rows = [_make_row(id="solo", corrected_at=_at(0))]
        batches = identify_batches(rows, window_seconds=5.0)
        assert batches == []

    def test_different_original_text_are_separate_groups(self) -> None:
        """Rows with differing ``original_text`` must be in separate groups."""
        rows = [
            _make_row(id="a", original_text="foo", corrected_text="bar", corrected_at=_at(0)),
            _make_row(id="b", original_text="baz", corrected_text="bar", corrected_at=_at(1)),
        ]
        # Each group has only 1 member → no batches
        batches = identify_batches(rows, window_seconds=5.0)
        assert batches == []

    def test_different_corrected_text_are_separate_groups(self) -> None:
        """Rows with differing ``corrected_text`` must not be grouped together."""
        rows = [
            _make_row(id="a", original_text="foo", corrected_text="bar", corrected_at=_at(0)),
            _make_row(id="b", original_text="foo", corrected_text="BAR", corrected_at=_at(1)),
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert batches == []

    def test_different_user_ids_are_separate_groups(self) -> None:
        """Rows with different ``corrected_by_user_id`` are separate groups."""
        rows = [
            _make_row(id="a", corrected_by_user_id="alice", corrected_at=_at(0)),
            _make_row(id="b", corrected_by_user_id="bob", corrected_at=_at(1)),
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert batches == []

    def test_multiple_groups_each_with_pairs(self) -> None:
        """Two separate groups each with 2+ corrections produce two batch groups."""
        rows = [
            # Group 1: user=alice, original=foo → bar
            _make_row(id="a1", corrected_by_user_id="alice", original_text="foo", corrected_text="bar", corrected_at=_at(0)),
            _make_row(id="a2", corrected_by_user_id="alice", original_text="foo", corrected_text="bar", corrected_at=_at(2)),
            # Group 2: user=alice, original=baz → qux
            _make_row(id="b1", corrected_by_user_id="alice", original_text="baz", corrected_text="qux", corrected_at=_at(0)),
            _make_row(id="b2", corrected_by_user_id="alice", original_text="baz", corrected_text="qux", corrected_at=_at(3)),
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert len(batches) == 2
        all_ids = {cid for bg in batches for cid in bg.correction_ids}
        assert all_ids == {"a1", "a2", "b1", "b2"}


# ---------------------------------------------------------------------------
# TestIdentifyBatchesSlidingWindow
# ---------------------------------------------------------------------------


class TestIdentifyBatchesSlidingWindow:
    """Tests for the sliding-window time-gap logic in ``identify_batches``."""

    def test_gap_strictly_less_than_threshold_stays_in_batch(self) -> None:
        """Gap of 4.999s with 5s window: corrections remain in the same batch."""
        rows = [
            _make_row(id="a", corrected_at=_at(0)),
            _make_row(id="b", corrected_at=_at(4.999)),
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert len(batches) == 1
        assert set(batches[0].correction_ids) == {"a", "b"}

    def test_gap_exactly_at_threshold_starts_new_batch(self) -> None:
        """Gap of exactly 5s with 5s window: must start a new batch (gap >= threshold)."""
        rows = [
            _make_row(id="a", corrected_at=_at(0)),
            _make_row(id="b", corrected_at=_at(5.0)),  # gap == window → new batch
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        # Each sub-window has only 1 correction → no batches qualify
        assert batches == []

    def test_gap_above_threshold_splits_into_separate_batches(self) -> None:
        """Gap of 10s with 5s window: the second pair forms a new batch."""
        rows = [
            _make_row(id="a", corrected_at=_at(0)),
            _make_row(id="b", corrected_at=_at(2)),   # gap 2s < 5s → same batch
            _make_row(id="c", corrected_at=_at(12)),  # gap 10s >= 5s → new window
            _make_row(id="d", corrected_at=_at(14)),  # gap 2s < 5s → same batch as c
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert len(batches) == 2
        batch_id_sets = [set(bg.correction_ids) for bg in batches]
        assert {"a", "b"} in batch_id_sets
        assert {"c", "d"} in batch_id_sets

    def test_custom_window_smaller_than_default(self) -> None:
        """A tighter window (2.5s) must split corrections that fit in the default 5s."""
        rows = [
            _make_row(id="a", corrected_at=_at(0)),
            _make_row(id="b", corrected_at=_at(3)),   # gap 3s >= 2.5s → new window
        ]
        batches = identify_batches(rows, window_seconds=2.5)
        # Each window has only 1 → no batches
        assert batches == []

    def test_custom_window_larger_groups_more_corrections(self) -> None:
        """A wider window (10s) groups corrections that would split at 5s."""
        rows = [
            _make_row(id="a", corrected_at=_at(0)),
            _make_row(id="b", corrected_at=_at(7)),   # gap 7s < 10s → same batch
            _make_row(id="c", corrected_at=_at(9)),   # gap 2s < 10s → same batch
        ]
        batches = identify_batches(rows, window_seconds=10.0)
        assert len(batches) == 1
        assert set(batches[0].correction_ids) == {"a", "b", "c"}

    def test_three_corrections_middle_gap_splits(self) -> None:
        """Gap between second and third correction splits window; first pair forms batch."""
        rows = [
            _make_row(id="a", corrected_at=_at(0)),
            _make_row(id="b", corrected_at=_at(4)),   # gap 4s < 5s → same window
            _make_row(id="c", corrected_at=_at(10)),  # gap 6s >= 5s → new window (solo)
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert len(batches) == 1
        assert set(batches[0].correction_ids) == {"a", "b"}

    def test_zero_gap_same_timestamp_stays_in_batch(self) -> None:
        """Corrections with identical timestamps (0s gap) stay in the same batch."""
        ts = _at(0)
        rows = [
            _make_row(id="a", corrected_at=ts),
            _make_row(id="b", corrected_at=ts),
            _make_row(id="c", corrected_at=ts),
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert len(batches) == 1
        assert set(batches[0].correction_ids) == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# TestIdentifyBatchesNullUserHandling
# ---------------------------------------------------------------------------


class TestIdentifyBatchesNullUserHandling:
    """Tests for NULL corrected_by_user_id grouping behavior."""

    def test_null_user_id_groups_with_other_nulls(self) -> None:
        """Two corrections with NULL user_id and same text must form a batch."""
        rows = [
            _make_row(id="a", corrected_by_user_id=None, corrected_at=_at(0)),
            _make_row(id="b", corrected_by_user_id=None, corrected_at=_at(2)),
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert len(batches) == 1
        assert set(batches[0].correction_ids) == {"a", "b"}

    def test_null_and_non_null_user_are_distinct_groups(self) -> None:
        """NULL user and 'cli' user with same text must NOT be grouped together."""
        rows = [
            _make_row(id="a", corrected_by_user_id=None, corrected_at=_at(0)),
            _make_row(id="b", corrected_by_user_id="cli", corrected_at=_at(1)),
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        # Each group has 1 → no batches
        assert batches == []


# ---------------------------------------------------------------------------
# TestIdentifyBatchesSingleCorrectionGroups
# ---------------------------------------------------------------------------


class TestIdentifyBatchesSingleCorrectionGroups:
    """Single-correction groups must never be included in batch output."""

    def test_single_correction_remains_null(self) -> None:
        """One correction in a group: excluded from returned batches."""
        row = _make_row(id="solo-1")
        batches = identify_batches([row], window_seconds=5.0)
        assert batches == []

    def test_mixed_single_and_multi_corrections(self) -> None:
        """Only multi-member groups are returned; singletons are excluded."""
        rows = [
            # Group A: 2 corrections → batch
            _make_row(id="a1", original_text="foo", corrected_text="bar", corrected_at=_at(0)),
            _make_row(id="a2", original_text="foo", corrected_text="bar", corrected_at=_at(2)),
            # Group B: 1 correction → excluded
            _make_row(id="b1", original_text="hello", corrected_text="world", corrected_at=_at(0)),
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert len(batches) == 1
        assert set(batches[0].correction_ids) == {"a1", "a2"}

    def test_batch_group_has_minimum_two_ids(self) -> None:
        """Every returned BatchGroup must contain at least 2 correction IDs."""
        rows = [
            _make_row(id=f"r{i}", corrected_at=_at(i * 0.5))
            for i in range(5)
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        for batch in batches:
            assert len(batch.correction_ids) >= 2


# ---------------------------------------------------------------------------
# TestIdentifyBatchesLargeGroups
# ---------------------------------------------------------------------------


class TestIdentifyBatchesLargeGroups:
    """Sliding window correctness at scale."""

    def test_large_group_all_within_window(self) -> None:
        """1000 corrections within 5s window must form exactly one batch."""
        # All 0.004s apart → total span = 3.996s < 5s
        rows = [
            _make_row(id=f"r{i}", corrected_at=_at(i * 0.004))
            for i in range(1000)
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert len(batches) == 1
        assert len(batches[0].correction_ids) == 1000

    def test_large_group_split_into_two_batches(self) -> None:
        """500 corrections in window A + 500 in window B produce exactly 2 batches."""
        # First 500: 0–2.49s (gap 0.005s each)
        first = [
            _make_row(id=f"a{i}", corrected_at=_at(i * 0.005))
            for i in range(500)
        ]
        # Second 500: start at 100s (gap of 97.5s from last of first group)
        second = [
            _make_row(id=f"b{i}", corrected_at=_at(100 + i * 0.005))
            for i in range(500)
        ]
        batches = identify_batches(first + second, window_seconds=5.0)
        assert len(batches) == 2
        assert len(batches[0].correction_ids) == 500
        assert len(batches[1].correction_ids) == 500

    def test_large_group_all_beyond_window_no_batch(self) -> None:
        """100 corrections each 10s apart (> 5s window) → no batches formed."""
        rows = [
            _make_row(id=f"r{i}", corrected_at=_at(i * 10.0))
            for i in range(100)
        ]
        batches = identify_batches(rows, window_seconds=5.0)
        assert batches == []


# ---------------------------------------------------------------------------
# TestFetchUnassignedCorrections
# ---------------------------------------------------------------------------


class TestFetchUnassignedCorrections:
    """Tests for ``fetch_unassigned_corrections`` database query function."""

    async def test_returns_correction_rows_from_db(self) -> None:
        """Function must map DB result rows into CorrectionRow dataclass instances."""
        # Build one ORM instance via factory to get realistic field values
        orm = TranscriptCorrectionFactory.build(
            original_text="teh word",
            corrected_text="the word",
            corrected_by_user_id="cli",
        )

        # Mock the session execute → fetchall pipeline
        mock_row = MagicMock()
        mock_row.id = str(orm.id)
        mock_row.corrected_by_user_id = orm.corrected_by_user_id
        mock_row.original_text = orm.original_text
        mock_row.corrected_text = orm.corrected_text
        mock_row.corrected_at = orm.corrected_at

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        rows = await fetch_unassigned_corrections(mock_session)

        assert len(rows) == 1
        assert isinstance(rows[0], CorrectionRow)
        assert rows[0].id == str(orm.id)
        assert rows[0].original_text == "teh word"
        assert rows[0].corrected_text == "the word"
        assert rows[0].corrected_by_user_id == "cli"

    async def test_empty_db_returns_empty_list(self) -> None:
        """No qualifying rows → empty list returned."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        rows = await fetch_unassigned_corrections(mock_session)
        assert rows == []

    async def test_multiple_rows_all_mapped(self) -> None:
        """All rows from fetchall must be mapped to CorrectionRow instances."""
        base_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        raw_rows = []
        for i in range(5):
            r = MagicMock()
            r.id = f"uuid-{i}"
            r.corrected_by_user_id = "user"
            r.original_text = f"orig {i}"
            r.corrected_text = f"corr {i}"
            r.corrected_at = base_time + timedelta(seconds=i)
            raw_rows.append(r)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = raw_rows

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        rows = await fetch_unassigned_corrections(mock_session)
        assert len(rows) == 5
        for idx, row in enumerate(rows):
            assert isinstance(row, CorrectionRow)
            assert row.id == f"uuid-{idx}"


# ---------------------------------------------------------------------------
# TestAssignBatchId
# ---------------------------------------------------------------------------


class TestAssignBatchId:
    """Tests for ``assign_batch_id`` database update function."""

    async def test_executes_update_and_commits(self) -> None:
        """Must call session.execute and session.commit exactly once."""
        mock_session = AsyncMock()
        batch_id = uuid.uuid4()
        ids = ["id-1", "id-2", "id-3"]

        await assign_batch_id(mock_session, ids, batch_id)

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    async def test_passes_batch_id_and_ids_to_execute(self) -> None:
        """Execute must receive an UPDATE statement with batch_id and correction_ids."""
        mock_session = AsyncMock()
        batch_id = uuid.uuid4()
        ids = ["id-1", "id-2"]

        await assign_batch_id(mock_session, ids, batch_id)

        # Verify the ORM update statement was passed to execute
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]  # first positional argument (the statement)
        # Compile the statement to verify it targets transcript_corrections
        compiled = str(stmt)
        assert "transcript_corrections" in compiled
        assert "batch_id" in compiled

    async def test_empty_id_list_still_commits(self) -> None:
        """Even an empty id list must call commit (no error should occur)."""
        mock_session = AsyncMock()
        batch_id = uuid.uuid4()

        await assign_batch_id(mock_session, [], batch_id)

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# TestIdempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Already-assigned corrections (batch_id IS NOT NULL) are never re-processed."""

    def test_fetch_query_filters_by_batch_id_null(self) -> None:
        """The SQL query in fetch_unassigned_corrections must include batch_id IS NULL.

        We verify this by checking the SQL text string passed to session.execute.
        """
        import asyncio

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        asyncio.get_event_loop().run_until_complete(
            fetch_unassigned_corrections(mock_session)
        )

        # Inspect the SQL text argument
        sql_arg = mock_session.execute.call_args[0][0]
        sql_text = str(sql_arg)
        assert "batch_id IS NULL" in sql_text

    def test_identify_batches_on_already_null_empty_corrections(self) -> None:
        """If fetch returns no rows (all already assigned), identify_batches gets []."""
        result = identify_batches([], window_seconds=DEFAULT_WINDOW_SECONDS)
        assert result == []


# ---------------------------------------------------------------------------
# TestRunBackfillDryRun
# ---------------------------------------------------------------------------


class TestRunBackfillDryRun:
    """Dry-run mode must not call assign_batch_id and must return exit code 0."""

    async def test_dry_run_returns_exit_code_zero(self) -> None:
        """run_backfill with dry_run=True must return 0."""
        mock_row_a = MagicMock()
        mock_row_a.id = "aaa"
        mock_row_a.corrected_by_user_id = "cli"
        mock_row_a.original_text = "teh"
        mock_row_a.corrected_text = "the"
        mock_row_a.corrected_at = _at(0)

        mock_row_b = MagicMock()
        mock_row_b.id = "bbb"
        mock_row_b.corrected_by_user_id = "cli"
        mock_row_b.original_text = "teh"
        mock_row_b.corrected_text = "the"
        mock_row_b.corrected_at = _at(2)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row_a, mock_row_b]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def _fake_session_gen(echo: bool) -> Any:
            yield mock_session

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_fake_session_gen,
        ):
            exit_code = await run_backfill(dry_run=True, window_seconds=5.0)

        assert exit_code == 0

    async def test_dry_run_does_not_commit(self) -> None:
        """In dry-run mode, session.commit must NOT be called (no DB mutations)."""
        mock_row_a = MagicMock()
        mock_row_a.id = "aaa"
        mock_row_a.corrected_by_user_id = "cli"
        mock_row_a.original_text = "teh"
        mock_row_a.corrected_text = "the"
        mock_row_a.corrected_at = _at(0)

        mock_row_b = MagicMock()
        mock_row_b.id = "bbb"
        mock_row_b.corrected_by_user_id = "cli"
        mock_row_b.original_text = "teh"
        mock_row_b.corrected_text = "the"
        mock_row_b.corrected_at = _at(2)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row_a, mock_row_b]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def _fake_session_gen(echo: bool) -> Any:
            yield mock_session

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_fake_session_gen,
        ):
            await run_backfill(dry_run=True, window_seconds=5.0)

        # session.commit is called by assign_batch_id; in dry-run it must not be called
        # (Note: the fetch query itself does not commit)
        mock_session.commit.assert_not_called()

    async def test_dry_run_no_corrections_returns_zero(self) -> None:
        """Dry-run with no unassigned corrections must still return 0."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def _fake_session_gen(echo: bool) -> Any:
            yield mock_session

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_fake_session_gen,
        ):
            exit_code = await run_backfill(dry_run=True, window_seconds=5.0)

        assert exit_code == 0


# ---------------------------------------------------------------------------
# TestRunBackfillLiveMode
# ---------------------------------------------------------------------------


class TestRunBackfillLiveMode:
    """Live-mode execution must persist batch IDs and return exit code 0."""

    async def test_live_mode_calls_commit(self) -> None:
        """In live mode with a 2-correction batch, session.commit must be called."""
        mock_row_a = MagicMock()
        mock_row_a.id = "aaa"
        mock_row_a.corrected_by_user_id = "cli"
        mock_row_a.original_text = "teh"
        mock_row_a.corrected_text = "the"
        mock_row_a.corrected_at = _at(0)

        mock_row_b = MagicMock()
        mock_row_b.id = "bbb"
        mock_row_b.corrected_by_user_id = "cli"
        mock_row_b.original_text = "teh"
        mock_row_b.corrected_text = "the"
        mock_row_b.corrected_at = _at(2)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row_a, mock_row_b]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def _fake_session_gen(echo: bool) -> Any:
            yield mock_session

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_fake_session_gen,
        ):
            exit_code = await run_backfill(dry_run=False, window_seconds=5.0)

        assert exit_code == 0
        # commit is called inside assign_batch_id
        mock_session.commit.assert_called()

    async def test_error_during_session_returns_exit_code_one(self) -> None:
        """An exception during the DB session must be caught and return exit code 1."""
        async def _broken_session_gen(echo: bool) -> Any:
            raise RuntimeError("connection refused")
            yield  # type: ignore[unreachable]  # make it a generator

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_broken_session_gen,
        ):
            exit_code = await run_backfill(dry_run=False, window_seconds=5.0)

        assert exit_code == 1

    async def test_live_mode_no_corrections_returns_zero(self) -> None:
        """No unassigned corrections → exit code 0, no commits."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def _fake_session_gen(echo: bool) -> Any:
            yield mock_session

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_fake_session_gen,
        ):
            exit_code = await run_backfill(dry_run=False, window_seconds=5.0)

        assert exit_code == 0
        mock_session.commit.assert_not_called()

    async def test_only_single_corrections_returns_zero_no_commit(self) -> None:
        """All corrections are in singleton groups → no batch assigned, exit code 0."""
        # Two rows with different original_text → different groups, each size 1
        mock_row_a = MagicMock()
        mock_row_a.id = "aaa"
        mock_row_a.corrected_by_user_id = "cli"
        mock_row_a.original_text = "foo"
        mock_row_a.corrected_text = "bar"
        mock_row_a.corrected_at = _at(0)

        mock_row_b = MagicMock()
        mock_row_b.id = "bbb"
        mock_row_b.corrected_by_user_id = "cli"
        mock_row_b.original_text = "baz"
        mock_row_b.corrected_text = "qux"
        mock_row_b.corrected_at = _at(1)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row_a, mock_row_b]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def _fake_session_gen(echo: bool) -> Any:
            yield mock_session

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_fake_session_gen,
        ):
            exit_code = await run_backfill(dry_run=False, window_seconds=5.0)

        assert exit_code == 0
        mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# TestProgressReporting
# ---------------------------------------------------------------------------


class TestProgressReporting:
    """Verify that totals reported by run_backfill are computed correctly."""

    async def test_assigned_count_matches_batch_members(self) -> None:
        """assigned_count in the summary equals the number of corrections in batches."""
        # 3 corrections in one group within window → 1 batch of 3
        mock_rows = []
        for idx, sec in enumerate([0, 2, 4]):
            r = MagicMock()
            r.id = f"row-{idx}"
            r.corrected_by_user_id = "cli"
            r.original_text = "teh"
            r.corrected_text = "the"
            r.corrected_at = _at(sec)
            mock_rows.append(r)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        captured: dict[str, Any] = {}

        original_display = _display_summary

        def _capture_display(**kwargs: Any) -> None:
            captured.update(kwargs)

        async def _fake_session_gen(echo: bool) -> Any:
            yield mock_session

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_fake_session_gen,
        ), patch(
            "scripts.utilities.backfill_batch_ids._display_summary",
            side_effect=_capture_display,
        ):
            await run_backfill(dry_run=False, window_seconds=5.0)

        assert captured["total_corrections"] == 3
        assert captured["batches_identified"] == 1
        assert captured["corrections_assigned"] == 3
        assert captured["corrections_left_null"] == 0

    async def test_singleton_corrections_reported_as_left_null(self) -> None:
        """Singletons must appear in corrections_left_null in the summary."""
        # 1 pair that forms a batch + 1 singleton
        mock_rows = []
        pair_data = [
            ("p1", "teh", "the", _at(0)),
            ("p2", "teh", "the", _at(2)),
        ]
        for rid, orig, corr, ts in pair_data:
            r = MagicMock()
            r.id = rid
            r.corrected_by_user_id = "cli"
            r.original_text = orig
            r.corrected_text = corr
            r.corrected_at = ts
            mock_rows.append(r)

        singleton = MagicMock()
        singleton.id = "s1"
        singleton.corrected_by_user_id = "cli"
        singleton.original_text = "unique text"
        singleton.corrected_text = "unique correction"
        singleton.corrected_at = _at(0)
        mock_rows.append(singleton)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        captured: dict[str, Any] = {}

        def _capture_display(**kwargs: Any) -> None:
            captured.update(kwargs)

        async def _fake_session_gen(echo: bool) -> Any:
            yield mock_session

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_fake_session_gen,
        ), patch(
            "scripts.utilities.backfill_batch_ids._display_summary",
            side_effect=_capture_display,
        ):
            await run_backfill(dry_run=False, window_seconds=5.0)

        assert captured["total_corrections"] == 3
        assert captured["batches_identified"] == 1
        assert captured["corrections_assigned"] == 2
        assert captured["corrections_left_null"] == 1


# ---------------------------------------------------------------------------
# TestBuildParser
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for the CLI argument parser."""

    def test_default_window_is_5_seconds(self) -> None:
        """Default --window value must equal DEFAULT_WINDOW_SECONDS (5.0)."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.window == DEFAULT_WINDOW_SECONDS

    def test_default_dry_run_is_false(self) -> None:
        """--dry-run flag must default to False."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.dry_run is False

    def test_dry_run_flag_sets_true(self) -> None:
        """Passing --dry-run must set dry_run to True."""
        parser = build_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_custom_window_parsed(self) -> None:
        """--window 10 must be parsed as float 10.0."""
        parser = build_parser()
        args = parser.parse_args(["--window", "10"])
        assert args.window == 10.0

    def test_fractional_window_parsed(self) -> None:
        """--window 2.5 must be parsed as float 2.5."""
        parser = build_parser()
        args = parser.parse_args(["--window", "2.5"])
        assert args.window == 2.5

    def test_dry_run_with_window(self) -> None:
        """--dry-run and --window can be combined."""
        parser = build_parser()
        args = parser.parse_args(["--dry-run", "--window", "3"])
        assert args.dry_run is True
        assert args.window == 3.0


# ---------------------------------------------------------------------------
# TestExitCodes
# ---------------------------------------------------------------------------


class TestExitCodes:
    """Verify exit codes from run_backfill."""

    async def test_success_exit_code_zero(self) -> None:
        """Successful run (even with no corrections) must return 0."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        async def _gen(echo: bool) -> Any:
            yield mock_session

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_gen,
        ):
            code = await run_backfill(dry_run=False, window_seconds=5.0)

        assert code == 0

    async def test_exception_returns_exit_code_one(self) -> None:
        """Any unhandled exception must result in exit code 1."""
        async def _broken(echo: bool) -> Any:
            raise ValueError("DB unavailable")
            yield  # type: ignore[unreachable]  # make it an async generator

        with patch(
            "scripts.utilities.backfill_batch_ids.db_manager.get_session",
            side_effect=_broken,
        ):
            code = await run_backfill(dry_run=False, window_seconds=5.0)

        assert code == 1
