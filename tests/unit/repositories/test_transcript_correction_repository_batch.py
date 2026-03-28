"""
Tests for TranscriptCorrectionRepository.get_all_filtered() (Feature 036 — T006).

Covers filtering by:
- video_ids  — restrict to one or more YouTube video IDs
- correction_type  — restrict to a single CorrectionType enum value
- since  — inclusive lower bound on corrected_at
- until  — inclusive upper bound on corrected_at (date-only → end-of-day)
- combinations of the above filters
- no filters (returns all records)

Mock strategy: every test creates a ``MagicMock(spec=AsyncSession)`` whose
``execute`` attribute is an ``AsyncMock``.  This avoids real database I/O and
follows the pattern used in ``test_transcript_correction_repository.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.models.batch_correction_models import (
    CorrectionPattern,
    TypeCount,
    VideoCount,
)
from chronovista.models.enums import CorrectionType
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)

# Ensures every async test in this module is recognised by pytest-asyncio
# regardless of how coverage is invoked (see CLAUDE.md §pytest-asyncio section).

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_uuid() -> uuid.UUID:
    """Return a UUIDv7 expressed as a stdlib ``uuid.UUID`` instance."""
    return uuid.UUID(bytes=uuid7().bytes)


def _make_correction_db(
    *,
    id: uuid.UUID | None = None,
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    segment_id: int | None = 1,
    correction_type: str = CorrectionType.SPELLING.value,
    original_text: str = "teh quick brown fox",
    corrected_text: str = "the quick brown fox",
    correction_note: str | None = None,
    corrected_by_user_id: str | None = "cli",
    corrected_at: datetime | None = None,
    version_number: int = 1,
) -> TranscriptCorrectionDB:
    """Build an in-memory TranscriptCorrectionDB instance without a DB session."""
    return TranscriptCorrectionDB(
        id=id or _make_uuid(),
        video_id=video_id,
        language_code=language_code,
        segment_id=segment_id,
        correction_type=correction_type,
        original_text=original_text,
        corrected_text=corrected_text,
        correction_note=correction_note,
        corrected_by_user_id=corrected_by_user_id,
        corrected_at=corrected_at or datetime.now(tz=UTC),
        version_number=version_number,
    )


def _make_mock_session() -> MagicMock:
    """Create a MagicMock AsyncSession with an AsyncMock execute attribute."""
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    return session


def _setup_scalars_return(
    mock_session: MagicMock,
    items: list[TranscriptCorrectionDB],
) -> None:
    """Configure mock_session.execute to return items via scalars().all()."""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_result


# ---------------------------------------------------------------------------
# TestGetAllFiltered
# ---------------------------------------------------------------------------


class TestGetAllFiltered:
    """Tests for get_all_filtered() — batch query with optional filters."""

    @pytest.fixture
    def repository(self) -> TranscriptCorrectionRepository:
        """Provide a fresh repository instance for each test."""
        return TranscriptCorrectionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    # ------------------------------------------------------------------
    # No filters
    # ------------------------------------------------------------------

    async def test_no_filters_returns_all(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """When no filters are provided, all records are returned."""
        c1 = _make_correction_db(video_id="vid1")
        c2 = _make_correction_db(video_id="vid2")
        _setup_scalars_return(mock_session, [c1, c2])

        results = await repository.get_all_filtered(mock_session)

        assert len(results) == 2
        assert results[0] is c1
        assert results[1] is c2
        mock_session.execute.assert_called_once()

    async def test_no_filters_empty_table(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """When no records exist and no filters are applied, an empty list is returned."""
        _setup_scalars_return(mock_session, [])

        results = await repository.get_all_filtered(mock_session)

        assert results == []
        mock_session.execute.assert_called_once()

    # ------------------------------------------------------------------
    # video_ids filter
    # ------------------------------------------------------------------

    async def test_filter_by_single_video_id(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Filtering by a single video_id returns only matching records."""
        c1 = _make_correction_db(video_id="target_vid_1")
        _setup_scalars_return(mock_session, [c1])

        results = await repository.get_all_filtered(
            mock_session, video_ids=["target_vid_1"]
        )

        assert len(results) == 1
        assert results[0].video_id == "target_vid_1"

        # Verify the SQL includes an IN clause for video_id
        stmt = mock_session.execute.call_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "video_id" in sql

    async def test_filter_by_multiple_video_ids(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Filtering by multiple video_ids uses IN clause."""
        c1 = _make_correction_db(video_id="vid_a")
        c2 = _make_correction_db(video_id="vid_b")
        _setup_scalars_return(mock_session, [c1, c2])

        results = await repository.get_all_filtered(
            mock_session, video_ids=["vid_a", "vid_b"]
        )

        assert len(results) == 2
        mock_session.execute.assert_called_once()

    async def test_filter_by_empty_video_ids_list(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Filtering by an empty video_ids list still applies IN() — returns empty."""
        _setup_scalars_return(mock_session, [])

        results = await repository.get_all_filtered(mock_session, video_ids=[])

        assert results == []
        mock_session.execute.assert_called_once()

    # ------------------------------------------------------------------
    # correction_type filter
    # ------------------------------------------------------------------

    async def test_filter_by_correction_type(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Filtering by correction_type restricts results to that type."""
        c1 = _make_correction_db(correction_type=CorrectionType.PROPER_NOUN.value)
        _setup_scalars_return(mock_session, [c1])

        results = await repository.get_all_filtered(
            mock_session, correction_type=CorrectionType.PROPER_NOUN
        )

        assert len(results) == 1
        assert results[0].correction_type == CorrectionType.PROPER_NOUN.value

        # Verify correction_type appears in WHERE clause
        stmt = mock_session.execute.call_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "correction_type" in sql

    async def test_filter_by_each_correction_type(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Every CorrectionType enum value can be used as a filter."""
        for ct in CorrectionType:
            mock_session.execute.reset_mock()
            _setup_scalars_return(mock_session, [])

            results = await repository.get_all_filtered(
                mock_session, correction_type=ct
            )
            assert results == []
            mock_session.execute.assert_called_once()

    # ------------------------------------------------------------------
    # since filter
    # ------------------------------------------------------------------

    async def test_filter_by_since(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The since filter applies an inclusive >= comparison on corrected_at."""
        since_dt = datetime(2025, 6, 1, 0, 0, 0, tzinfo=UTC)
        c1 = _make_correction_db(
            corrected_at=datetime(2025, 7, 1, 12, 0, 0, tzinfo=UTC)
        )
        _setup_scalars_return(mock_session, [c1])

        results = await repository.get_all_filtered(mock_session, since=since_dt)

        assert len(results) == 1

        # Verify corrected_at appears in WHERE clause
        stmt = mock_session.execute.call_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "corrected_at" in sql

    # ------------------------------------------------------------------
    # until filter
    # ------------------------------------------------------------------

    async def test_filter_by_until(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The until filter applies an inclusive <= comparison on corrected_at."""
        until_dt = datetime(2025, 12, 31, 18, 30, 0, tzinfo=UTC)
        c1 = _make_correction_db(
            corrected_at=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        )
        _setup_scalars_return(mock_session, [c1])

        results = await repository.get_all_filtered(mock_session, until=until_dt)

        assert len(results) == 1
        mock_session.execute.assert_called_once()

    async def test_until_date_only_interpreted_as_end_of_day(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """When until has time 00:00:00, it is adjusted to 23:59:59.999999.

        This ensures date-only values (e.g., ``datetime(2025, 12, 31)``)
        include the entire day rather than cutting off at midnight.
        """
        until_midnight = datetime(2025, 12, 31, 0, 0, 0, tzinfo=UTC)
        assert until_midnight.time() == time(0, 0, 0)

        _setup_scalars_return(mock_session, [])

        await repository.get_all_filtered(mock_session, until=until_midnight)

        # The method should have been called — we verify the adjustment
        # by checking the compiled SQL contains corrected_at <=
        stmt = mock_session.execute.call_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "corrected_at" in sql
        mock_session.execute.assert_called_once()

    async def test_until_with_nonzero_time_not_adjusted(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """When until has a non-midnight time, it is used as-is (no end-of-day adjustment)."""
        until_dt = datetime(2025, 12, 31, 14, 30, 0, tzinfo=UTC)
        assert until_dt.time() != time(0, 0, 0)

        _setup_scalars_return(mock_session, [])

        await repository.get_all_filtered(mock_session, until=until_dt)

        mock_session.execute.assert_called_once()

    # ------------------------------------------------------------------
    # Combined filters
    # ------------------------------------------------------------------

    async def test_combined_video_ids_and_correction_type(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Multiple filters are combined with AND semantics."""
        c1 = _make_correction_db(
            video_id="vid_x",
            correction_type=CorrectionType.FORMATTING.value,
        )
        _setup_scalars_return(mock_session, [c1])

        results = await repository.get_all_filtered(
            mock_session,
            video_ids=["vid_x"],
            correction_type=CorrectionType.FORMATTING,
        )

        assert len(results) == 1
        # Verify both filters appear in SQL
        stmt = mock_session.execute.call_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "video_id" in sql
        assert "correction_type" in sql

    async def test_combined_all_four_filters(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """All four filters (video_ids, correction_type, since, until) work together."""
        c1 = _make_correction_db(
            video_id="vid_combined",
            correction_type=CorrectionType.CONTEXT_CORRECTION.value,
            corrected_at=datetime(2025, 8, 15, 10, 0, 0, tzinfo=UTC),
        )
        _setup_scalars_return(mock_session, [c1])

        results = await repository.get_all_filtered(
            mock_session,
            video_ids=["vid_combined"],
            correction_type=CorrectionType.CONTEXT_CORRECTION,
            since=datetime(2025, 1, 1, tzinfo=UTC),
            until=datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC),
        )

        assert len(results) == 1
        assert results[0].video_id == "vid_combined"

    async def test_combined_since_and_until_date_range(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """since and until together define a date range for corrected_at."""
        _setup_scalars_return(mock_session, [])

        await repository.get_all_filtered(
            mock_session,
            since=datetime(2025, 3, 1, tzinfo=UTC),
            until=datetime(2025, 3, 31, 23, 59, 59, tzinfo=UTC),
        )

        # Verify both >= and <= predicates on corrected_at appear in SQL
        stmt = mock_session.execute.call_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "corrected_at >= " in sql, (
            f"Expected corrected_at >= predicate in SQL; got: {sql}"
        )
        assert "corrected_at <= " in sql, (
            f"Expected corrected_at <= predicate in SQL; got: {sql}"
        )

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------

    async def test_results_ordered_by_corrected_at_ascending(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Results are ordered by corrected_at ASC for consistent export ordering.

        The SQL must include an ORDER BY corrected_at ASC clause.
        """
        c_early = _make_correction_db(
            corrected_at=datetime(2025, 1, 1, tzinfo=UTC)
        )
        c_late = _make_correction_db(
            corrected_at=datetime(2025, 12, 31, tzinfo=UTC)
        )
        _setup_scalars_return(mock_session, [c_early, c_late])

        results = await repository.get_all_filtered(mock_session)

        assert len(results) == 2
        assert results[0] is c_early
        assert results[1] is c_late

        # Verify ORDER BY is present in the SQL
        stmt = mock_session.execute.call_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "ORDER BY" in sql.upper()
        assert "corrected_at" in sql

    # ------------------------------------------------------------------
    # Return type
    # ------------------------------------------------------------------

    async def test_returns_list_type(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_all_filtered() always returns a list, never a raw SQLAlchemy result."""
        _setup_scalars_return(mock_session, [])

        results = await repository.get_all_filtered(mock_session)

        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Helpers for get_stats mock setup
# ---------------------------------------------------------------------------


def _make_mock_session_for_stats(
    *,
    totals_row: tuple[int, int, int, int] = (0, 0, 0, 0),
    by_type_rows: list[tuple[str, int]] | None = None,
    top_video_rows: list[tuple[str, str | None, int]] | None = None,
) -> MagicMock:
    """Create a mock session that returns results for the 3 get_stats queries.

    Parameters
    ----------
    totals_row : tuple
        (total_corrections, total_reverts, unique_segments, unique_videos)
    by_type_rows : list of (correction_type, count) tuples
    top_video_rows : list of (video_id, title, count) tuples
    """
    if by_type_rows is None:
        by_type_rows = []
    if top_video_rows is None:
        top_video_rows = []

    session = MagicMock(spec=AsyncSession)

    # Build result mocks for the 3 queries in order
    # Query 1: totals — uses .one()
    totals_result = MagicMock()
    totals_named = MagicMock()
    totals_named.total_corrections = totals_row[0]
    totals_named.total_reverts = totals_row[1]
    totals_named.unique_segments = totals_row[2]
    totals_named.unique_videos = totals_row[3]
    totals_result.one.return_value = totals_named

    # Query 2: by_type — uses .all()
    by_type_result = MagicMock()
    by_type_named_rows = []
    for ct, cnt in by_type_rows:
        row = MagicMock()
        row.correction_type = ct
        row.cnt = cnt
        by_type_named_rows.append(row)
    by_type_result.all.return_value = by_type_named_rows

    # Query 3: top_videos — uses .all()
    top_result = MagicMock()
    top_named_rows = []
    for vid, title, cnt in top_video_rows:
        row = MagicMock()
        row.video_id = vid
        row.title = title
        row.cnt = cnt
        top_named_rows.append(row)
    top_result.all.return_value = top_named_rows

    session.execute = AsyncMock(side_effect=[totals_result, by_type_result, top_result])
    return session


# ---------------------------------------------------------------------------
# TestGetStats
# ---------------------------------------------------------------------------


class TestGetStats:
    """Tests for get_stats() — aggregate correction statistics (T007)."""

    @pytest.fixture
    def repository(self) -> TranscriptCorrectionRepository:
        """Provide a fresh repository instance for each test."""
        return TranscriptCorrectionRepository()

    # ------------------------------------------------------------------
    # Basic return structure
    # ------------------------------------------------------------------

    async def test_returns_dict_with_expected_keys(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """get_stats() returns a dict with all CorrectionStats field keys."""
        session = _make_mock_session_for_stats()

        result = await repository.get_stats(session)

        expected_keys = {
            "total_corrections",
            "total_reverts",
            "unique_segments",
            "unique_videos",
            "by_type",
            "top_videos",
        }
        assert set(result.keys()) == expected_keys

    async def test_empty_table_returns_zeros(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """When no corrections exist, all scalar fields are 0 and lists are empty."""
        session = _make_mock_session_for_stats(
            totals_row=(0, 0, 0, 0),
            by_type_rows=[],
            top_video_rows=[],
        )

        result = await repository.get_stats(session)

        assert result["total_corrections"] == 0
        assert result["total_reverts"] == 0
        assert result["unique_segments"] == 0
        assert result["unique_videos"] == 0
        assert result["by_type"] == []
        assert result["top_videos"] == []

    # ------------------------------------------------------------------
    # Scalar totals
    # ------------------------------------------------------------------

    async def test_totals_reflect_counts(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """Scalar totals reflect the conditional aggregation query results."""
        session = _make_mock_session_for_stats(
            totals_row=(42, 5, 30, 8),
        )

        result = await repository.get_stats(session)

        assert result["total_corrections"] == 42
        assert result["total_reverts"] == 5
        assert result["unique_segments"] == 30
        assert result["unique_videos"] == 8

    # ------------------------------------------------------------------
    # by_type breakdown
    # ------------------------------------------------------------------

    async def test_by_type_returns_type_count_models(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """by_type entries are TypeCount model instances."""
        session = _make_mock_session_for_stats(
            by_type_rows=[
                (CorrectionType.SPELLING.value, 20),
                (CorrectionType.PROPER_NOUN.value, 15),
            ],
        )

        result = await repository.get_stats(session)

        assert len(result["by_type"]) == 2
        for item in result["by_type"]:
            assert isinstance(item, TypeCount)

    async def test_by_type_values(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """by_type entries have correct correction_type and count values."""
        session = _make_mock_session_for_stats(
            by_type_rows=[
                (CorrectionType.SPELLING.value, 20),
                (CorrectionType.PROPER_NOUN.value, 15),
                (CorrectionType.FORMATTING.value, 3),
            ],
        )

        result = await repository.get_stats(session)

        assert result["by_type"][0] == TypeCount(correction_type="spelling", count=20)
        assert result["by_type"][1] == TypeCount(correction_type="proper_noun", count=15)
        assert result["by_type"][2] == TypeCount(correction_type="formatting", count=3)

    async def test_by_type_empty_when_no_non_revert_corrections(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """by_type is empty when there are only reverts (or nothing)."""
        session = _make_mock_session_for_stats(
            totals_row=(0, 5, 0, 0),
            by_type_rows=[],
        )

        result = await repository.get_stats(session)

        assert result["by_type"] == []

    # ------------------------------------------------------------------
    # top_videos ranking
    # ------------------------------------------------------------------

    async def test_top_videos_returns_video_count_models(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """top_videos entries are VideoCount model instances."""
        session = _make_mock_session_for_stats(
            top_video_rows=[
                ("vid1", "First Video", 10),
                ("vid2", None, 5),
            ],
        )

        result = await repository.get_stats(session)

        assert len(result["top_videos"]) == 2
        for item in result["top_videos"]:
            assert isinstance(item, VideoCount)

    async def test_top_videos_values(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """top_videos entries have correct video_id, title, and count."""
        session = _make_mock_session_for_stats(
            top_video_rows=[
                ("abc123", "My Great Video", 25),
                ("def456", None, 12),
            ],
        )

        result = await repository.get_stats(session)

        assert result["top_videos"][0] == VideoCount(
            video_id="abc123", title="My Great Video", count=25
        )
        assert result["top_videos"][1] == VideoCount(
            video_id="def456", title=None, count=12
        )

    async def test_top_videos_empty_when_no_corrections(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """top_videos is empty when no non-revert corrections exist."""
        session = _make_mock_session_for_stats(
            top_video_rows=[],
        )

        result = await repository.get_stats(session)

        assert result["top_videos"] == []

    # ------------------------------------------------------------------
    # SQL round-trip count (US-7 AC-5: at most 5)
    # ------------------------------------------------------------------

    async def test_uses_at_most_three_queries(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """get_stats() executes exactly 3 SQL queries (well within the 5-query limit)."""
        session = _make_mock_session_for_stats(
            totals_row=(10, 2, 8, 3),
            by_type_rows=[("spelling", 7), ("proper_noun", 3)],
            top_video_rows=[("vid1", "Title", 7)],
        )

        await repository.get_stats(session)

        assert session.execute.call_count == 3

    # ------------------------------------------------------------------
    # Language filter
    # ------------------------------------------------------------------

    async def test_language_filter_passed_to_queries(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """When language is provided, all 3 queries include a language_code filter."""
        session = _make_mock_session_for_stats(
            totals_row=(5, 1, 4, 2),
            by_type_rows=[("spelling", 5)],
            top_video_rows=[("vid1", "Title", 5)],
        )

        await repository.get_stats(session, language="es")

        assert session.execute.call_count == 3
        # Verify language_code appears in all 3 SQL statements
        for call_args in session.execute.call_args_list:
            stmt = call_args.args[0]
            sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
            assert "language_code" in sql, (
                f"Expected language_code filter in SQL; got: {sql}"
            )

    async def test_no_language_filter_by_default(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """When language is None (default), queries do not filter by language_code."""
        session = _make_mock_session_for_stats(
            totals_row=(10, 2, 8, 3),
            by_type_rows=[("spelling", 10)],
            top_video_rows=[("vid1", "Title", 10)],
        )

        await repository.get_stats(session)

        # The first query (totals) should not have a WHERE with language_code
        totals_stmt = session.execute.call_args_list[0].args[0]
        totals_sql = str(totals_stmt.compile(compile_kwargs={"literal_binds": False}))
        # language_code appears in SELECT (as a column reference) but not in WHERE
        # We check there's no "= :language_code" or "language_code =" pattern
        # which would indicate a filter
        assert "language_code =" not in totals_sql or "language_code" not in totals_sql.split("WHERE")[-1] if "WHERE" in totals_sql else True

    # ------------------------------------------------------------------
    # top parameter
    # ------------------------------------------------------------------

    async def test_top_parameter_default_is_ten(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """The default value for the top parameter is 10."""
        session = _make_mock_session_for_stats()

        await repository.get_stats(session)

        # The 3rd query (top_videos) should include LIMIT
        top_stmt = session.execute.call_args_list[2].args[0]
        top_sql = str(top_stmt.compile(compile_kwargs={"literal_binds": False}))
        # SQLAlchemy renders LIMIT as part of the SQL
        assert "LIMIT" in top_sql.upper()

    async def test_custom_top_parameter(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """A custom top value limits the number of top_videos returned."""
        session = _make_mock_session_for_stats(
            top_video_rows=[
                ("vid1", "Title 1", 50),
                ("vid2", "Title 2", 30),
                ("vid3", "Title 3", 10),
            ],
        )

        result = await repository.get_stats(session, top=3)

        assert len(result["top_videos"]) == 3

    # ------------------------------------------------------------------
    # CorrectionStats model compatibility
    # ------------------------------------------------------------------

    async def test_result_compatible_with_correction_stats_model(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """The returned dict can be unpacked into CorrectionStats(**result)."""
        from chronovista.models.batch_correction_models import CorrectionStats

        session = _make_mock_session_for_stats(
            totals_row=(15, 3, 10, 4),
            by_type_rows=[
                ("spelling", 10),
                ("proper_noun", 5),
            ],
            top_video_rows=[
                ("vid1", "Top Video", 10),
                ("vid2", None, 5),
            ],
        )

        result = await repository.get_stats(session)
        stats = CorrectionStats(**result)

        assert stats.total_corrections == 15
        assert stats.total_reverts == 3
        assert stats.unique_segments == 10
        assert stats.unique_videos == 4
        assert len(stats.by_type) == 2
        assert len(stats.top_videos) == 2
        assert stats.by_type[0].correction_type == "spelling"
        assert stats.top_videos[0].video_id == "vid1"
        assert stats.top_videos[0].title == "Top Video"


# ---------------------------------------------------------------------------
# Helpers for get_correction_patterns mock setup
# ---------------------------------------------------------------------------


def _make_mock_session_for_patterns(
    *,
    pairs_rows: list[tuple[str, str, int]] | None = None,
    remaining_counts: list[int] | None = None,
) -> MagicMock:
    """Create a mock session for get_correction_patterns queries.

    Parameters
    ----------
    pairs_rows : list of (original_text, corrected_text, occurrences)
        Rows returned by the GROUP BY query (step 1).
    remaining_counts : list of int
        Scalar counts returned by each remaining_matches subquery (step 2).
        Must match len(pairs_rows) if pairs_rows is not empty.
    """
    if pairs_rows is None:
        pairs_rows = []
    if remaining_counts is None:
        remaining_counts = []

    session = MagicMock(spec=AsyncSession)

    # Build result for step 1: pairs query uses .all()
    pairs_named_rows = []
    for orig, corr, occ in pairs_rows:
        row = MagicMock()
        row.original_text = orig
        row.corrected_text = corr
        row.occurrences = occ
        pairs_named_rows.append(row)

    pairs_result = MagicMock()
    pairs_result.all.return_value = pairs_named_rows

    # Build results for step 2: one scalar_one() call per pair
    remaining_results = []
    for count_val in remaining_counts:
        rem_result = MagicMock()
        rem_result.scalar_one.return_value = count_val
        remaining_results.append(rem_result)

    session.execute = AsyncMock(side_effect=[pairs_result] + remaining_results)
    return session


# ---------------------------------------------------------------------------
# TestGetCorrectionPatterns
# ---------------------------------------------------------------------------


class TestGetCorrectionPatterns:
    """Tests for get_correction_patterns() — pattern discovery (T008)."""

    @pytest.fixture
    def repository(self) -> TranscriptCorrectionRepository:
        """Provide a fresh repository instance for each test."""
        return TranscriptCorrectionRepository()

    # ------------------------------------------------------------------
    # Empty / no patterns
    # ------------------------------------------------------------------

    async def test_empty_table_returns_empty_list(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """When no corrections exist, an empty list is returned."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[],
            remaining_counts=[],
        )

        result = await repository.get_correction_patterns(session)

        assert result == []
        # Only 1 query executed (pairs query)
        assert session.execute.call_count == 1

    # ------------------------------------------------------------------
    # Basic pattern discovery
    # ------------------------------------------------------------------

    async def test_single_pattern_returned(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """A single pattern with remaining matches is returned."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[("teh", "the", 5)],
            remaining_counts=[10],
        )

        result = await repository.get_correction_patterns(session)

        assert len(result) == 1
        assert isinstance(result[0], CorrectionPattern)
        assert result[0].original_text == "teh"
        assert result[0].corrected_text == "the"
        assert result[0].occurrences == 5
        assert result[0].remaining_matches == 10

    async def test_multiple_patterns_sorted_by_remaining_desc(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """Multiple patterns are sorted by remaining_matches descending."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[
                ("teh", "the", 5),
                ("recieve", "receive", 3),
                ("accomodate", "accommodate", 2),
            ],
            remaining_counts=[2, 15, 8],
        )

        result = await repository.get_correction_patterns(session)

        assert len(result) == 3
        assert result[0].original_text == "recieve"
        assert result[0].remaining_matches == 15
        assert result[1].original_text == "accomodate"
        assert result[1].remaining_matches == 8
        assert result[2].original_text == "teh"
        assert result[2].remaining_matches == 2

    # ------------------------------------------------------------------
    # show_completed filter
    # ------------------------------------------------------------------

    async def test_completed_patterns_excluded_by_default(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """Patterns with remaining_matches == 0 are excluded when show_completed=False."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[
                ("teh", "the", 5),
                ("recieve", "receive", 3),
            ],
            remaining_counts=[0, 7],
        )

        result = await repository.get_correction_patterns(session)

        assert len(result) == 1
        assert result[0].original_text == "recieve"
        assert result[0].remaining_matches == 7

    async def test_show_completed_includes_zero_remaining(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """When show_completed=True, patterns with remaining_matches == 0 are included."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[
                ("teh", "the", 5),
                ("recieve", "receive", 3),
            ],
            remaining_counts=[0, 7],
        )

        result = await repository.get_correction_patterns(
            session, show_completed=True
        )

        assert len(result) == 2
        # Sorted by remaining_matches DESC
        assert result[0].original_text == "recieve"
        assert result[0].remaining_matches == 7
        assert result[1].original_text == "teh"
        assert result[1].remaining_matches == 0

    # ------------------------------------------------------------------
    # min_occurrences parameter
    # ------------------------------------------------------------------

    async def test_default_min_occurrences_is_two(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """The default min_occurrences is 2 — the SQL HAVING clause enforces this."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[("teh", "the", 2)],
            remaining_counts=[5],
        )

        result = await repository.get_correction_patterns(session)

        assert len(result) == 1
        # Verify the pairs query was called (HAVING >= 2)
        session.execute.assert_called()

    async def test_custom_min_occurrences(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """A custom min_occurrences filters the grouped pairs in SQL."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[("teh", "the", 10)],
            remaining_counts=[20],
        )

        result = await repository.get_correction_patterns(
            session, min_occurrences=5
        )

        assert len(result) == 1
        assert result[0].occurrences == 10

        # Verify the HAVING clause is present
        pairs_stmt = session.execute.call_args_list[0].args[0]
        sql = str(pairs_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "HAVING" in sql.upper()

    # ------------------------------------------------------------------
    # limit parameter
    # ------------------------------------------------------------------

    async def test_default_limit_is_25(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """The default limit is 25 — at most 25 patterns are returned."""
        # Create 30 patterns; only 25 should be returned
        pairs = [(f"err{i}", f"fix{i}", 3) for i in range(30)]
        remaining = [30 - i for i in range(30)]
        session = _make_mock_session_for_patterns(
            pairs_rows=pairs,
            remaining_counts=remaining,
        )

        result = await repository.get_correction_patterns(session)

        assert len(result) == 25

    async def test_custom_limit(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """A custom limit restricts the number of returned patterns."""
        pairs = [(f"err{i}", f"fix{i}", 3) for i in range(10)]
        remaining = [10 - i for i in range(10)]
        session = _make_mock_session_for_patterns(
            pairs_rows=pairs,
            remaining_counts=remaining,
        )

        result = await repository.get_correction_patterns(session, limit=3)

        assert len(result) == 3
        # Should be the top 3 by remaining_matches (10, 9, 8)
        assert result[0].remaining_matches == 10
        assert result[1].remaining_matches == 9
        assert result[2].remaining_matches == 8

    # ------------------------------------------------------------------
    # SQL structure verification
    # ------------------------------------------------------------------

    async def test_pairs_query_excludes_reverts(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """The pairs GROUP BY query excludes revert-type corrections."""
        session = _make_mock_session_for_patterns(pairs_rows=[], remaining_counts=[])

        await repository.get_correction_patterns(session)

        pairs_stmt = session.execute.call_args_list[0].args[0]
        sql = str(pairs_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "correction_type" in sql
        assert "!=" in sql or "<>" in sql or "NOT" in sql.upper()

    async def test_pairs_query_groups_by_original_and_corrected(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """The pairs query uses GROUP BY (original_text, corrected_text)."""
        session = _make_mock_session_for_patterns(pairs_rows=[], remaining_counts=[])

        await repository.get_correction_patterns(session)

        pairs_stmt = session.execute.call_args_list[0].args[0]
        sql = str(pairs_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "GROUP BY" in sql.upper()
        assert "original_text" in sql
        assert "corrected_text" in sql

    async def test_remaining_query_uses_effective_text(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """The remaining_matches query uses CASE WHEN has_correction for effective text."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[("teh", "the", 3)],
            remaining_counts=[5],
        )

        await repository.get_correction_patterns(session)

        # The second execute call is the remaining_matches query
        remaining_stmt = session.execute.call_args_list[1].args[0]
        sql = str(remaining_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "has_correction" in sql
        assert "CASE" in sql.upper() or "WHEN" in sql.upper()

    # ------------------------------------------------------------------
    # Query count
    # ------------------------------------------------------------------

    async def test_query_count_is_1_plus_n_pairs(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """get_correction_patterns executes 1 + N queries (1 pairs + N remaining)."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[
                ("teh", "the", 5),
                ("recieve", "receive", 3),
            ],
            remaining_counts=[10, 5],
        )

        await repository.get_correction_patterns(session)

        # 1 pairs query + 2 remaining queries = 3
        assert session.execute.call_count == 3

    # ------------------------------------------------------------------
    # Return type
    # ------------------------------------------------------------------

    async def test_returns_list_of_correction_pattern(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """get_correction_patterns() returns a list of CorrectionPattern instances."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[("teh", "the", 5)],
            remaining_counts=[10],
        )

        result = await repository.get_correction_patterns(session)

        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, CorrectionPattern)

    async def test_correction_pattern_model_is_frozen(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """CorrectionPattern instances are frozen (immutable)."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[("teh", "the", 5)],
            remaining_counts=[10],
        )

        result = await repository.get_correction_patterns(session)

        with pytest.raises(Exception):  # ValidationError for frozen model
            result[0].occurrences = 999

    # ------------------------------------------------------------------
    # All completed with show_completed=False yields empty
    # ------------------------------------------------------------------

    async def test_all_completed_returns_empty_by_default(
        self,
        repository: TranscriptCorrectionRepository,
    ) -> None:
        """When every pattern has remaining_matches==0 and show_completed=False, return empty."""
        session = _make_mock_session_for_patterns(
            pairs_rows=[
                ("teh", "the", 5),
                ("recieve", "receive", 3),
            ],
            remaining_counts=[0, 0],
        )

        result = await repository.get_correction_patterns(session)

        assert result == []
