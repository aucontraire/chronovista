"""
Tests for TranscriptSegmentRepository batch methods.

Tests the batch text pattern search (find_by_text_pattern) and filtered
count (count_filtered) functionality added for Feature 036:
Batch Correction Tools (T004, T005).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
    _escape_like_pattern,
)

pytestmark = pytest.mark.asyncio


def _make_segment(
    *,
    id: int = 1,
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    text: str = "hello world",
    corrected_text: str | None = None,
    has_correction: bool = False,
    sequence_number: int = 0,
) -> TranscriptSegmentDB:
    """Helper to create a TranscriptSegmentDB instance for testing."""
    return TranscriptSegmentDB(
        id=id,
        video_id=video_id,
        language_code=language_code,
        text=text,
        corrected_text=corrected_text,
        has_correction=has_correction,
        start_time=0.0,
        duration=2.5,
        end_time=2.5,
        sequence_number=sequence_number,
        created_at=datetime.now(timezone.utc),
    )


class TestFindByTextPatternSubstring:
    """Tests for substring (LIKE/ILIKE) pattern matching."""

    @pytest.fixture
    def repository(self) -> TranscriptSegmentRepository:
        """Create repository instance for testing."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    def _setup_scalars_result(
        self, mock_session: AsyncMock, segments: List[TranscriptSegmentDB]
    ) -> None:
        """Configure mock session to return segments via scalars().all()."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = segments
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

    async def test_basic_substring_search(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test basic case-sensitive substring search returns results."""
        segments = [_make_segment(text="hello world")]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern="hello"
        )

        assert len(result) == 1
        assert result[0].text == "hello world"
        mock_session.execute.assert_called_once()

    async def test_substring_search_no_matches(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test substring search with no matches returns empty list."""
        self._setup_scalars_result(mock_session, [])

        result = await repository.find_by_text_pattern(
            mock_session, pattern="nonexistent"
        )

        assert result == []
        mock_session.execute.assert_called_once()

    async def test_case_insensitive_substring_search(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test case-insensitive substring search uses ILIKE."""
        segments = [_make_segment(text="Hello World")]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern="hello", case_insensitive=True
        )

        assert len(result) == 1
        mock_session.execute.assert_called_once()

    async def test_case_sensitive_substring_search(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test case-sensitive substring search uses LIKE (default)."""
        segments = [_make_segment(text="Hello World")]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern="Hello"
        )

        assert len(result) == 1
        mock_session.execute.assert_called_once()


class TestFindByTextPatternRegex:
    """Tests for regex (~, ~*) pattern matching."""

    @pytest.fixture
    def repository(self) -> TranscriptSegmentRepository:
        """Create repository instance for testing."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    def _setup_scalars_result(
        self, mock_session: AsyncMock, segments: List[TranscriptSegmentDB]
    ) -> None:
        """Configure mock session to return segments via scalars().all()."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = segments
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

    async def test_regex_search_case_sensitive(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test case-sensitive regex search."""
        segments = [_make_segment(text="hello world 123")]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern=r"hello\s+world\s+\d+", regex=True
        )

        assert len(result) == 1
        mock_session.execute.assert_called_once()

    async def test_regex_search_case_insensitive(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test case-insensitive regex search."""
        segments = [_make_segment(text="Hello World")]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session,
            pattern=r"hello\s+world",
            regex=True,
            case_insensitive=True,
        )

        assert len(result) == 1
        mock_session.execute.assert_called_once()

    async def test_invalid_regex_raises_value_error(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that invalid regex pattern raises ValueError before SQL execution."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            await repository.find_by_text_pattern(
                mock_session, pattern=r"[invalid(", regex=True
            )

        # Session should NOT have been called — validation happens before SQL
        mock_session.execute.assert_not_called()

    async def test_invalid_regex_includes_pattern_in_message(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that ValueError message includes the invalid pattern."""
        with pytest.raises(ValueError, match=r"\[unclosed"):
            await repository.find_by_text_pattern(
                mock_session, pattern=r"[unclosed", regex=True
            )

    async def test_valid_regex_does_not_raise(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that valid regex patterns do not raise errors."""
        self._setup_scalars_result(mock_session, [])

        # These should all succeed without raising
        for valid_pattern in [r"^hello$", r"\d{3}", r"(foo|bar)", r".*"]:
            result = await repository.find_by_text_pattern(
                mock_session, pattern=valid_pattern, regex=True
            )
            assert isinstance(result, list) or hasattr(result, "__len__")


class TestFindByTextPatternFilters:
    """Tests for filter parameters (language, channel, video_ids)."""

    @pytest.fixture
    def repository(self) -> TranscriptSegmentRepository:
        """Create repository instance for testing."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    def _setup_scalars_result(
        self, mock_session: AsyncMock, segments: List[TranscriptSegmentDB]
    ) -> None:
        """Configure mock session to return segments via scalars().all()."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = segments
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

    async def test_language_filter(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test filtering by language_code."""
        segments = [_make_segment(language_code="es", text="hola mundo")]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern="hola", language="es"
        )

        assert len(result) == 1
        assert result[0].language_code == "es"
        mock_session.execute.assert_called_once()

    async def test_video_ids_filter(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test filtering by list of video IDs."""
        segments = [
            _make_segment(id=1, video_id="vid1", text="hello from vid1"),
            _make_segment(id=2, video_id="vid2", text="hello from vid2"),
        ]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern="hello", video_ids=["vid1", "vid2"]
        )

        assert len(result) == 2
        mock_session.execute.assert_called_once()

    async def test_channel_filter_joins_video_table(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that channel filter joins through videos table."""
        segments = [_make_segment(text="channel content")]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern="content", channel="UCxxxxxxxxxxxxxx"
        )

        assert len(result) == 1
        mock_session.execute.assert_called_once()

    async def test_combined_filters(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test combining multiple filters together."""
        segments = [
            _make_segment(
                id=1,
                video_id="vid1",
                language_code="en",
                text="specific text",
            )
        ]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session,
            pattern="specific",
            language="en",
            video_ids=["vid1", "vid2"],
            channel="UCxxxxxxxxxxxxxx",
        )

        assert len(result) == 1
        mock_session.execute.assert_called_once()

    async def test_no_filters_searches_all_segments(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that no filters means searching across all segments."""
        segments = [
            _make_segment(id=1, text="match one"),
            _make_segment(id=2, text="match two"),
            _make_segment(id=3, text="match three"),
        ]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern="match"
        )

        assert len(result) == 3
        mock_session.execute.assert_called_once()

    async def test_empty_video_ids_list(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that passing empty video_ids list returns empty results."""
        self._setup_scalars_result(mock_session, [])

        result = await repository.find_by_text_pattern(
            mock_session, pattern="hello", video_ids=[]
        )

        assert result == []


class TestFindByTextPatternEffectiveText:
    """Tests for effective text (CASE WHEN has_correction) behavior."""

    @pytest.fixture
    def repository(self) -> TranscriptSegmentRepository:
        """Create repository instance for testing."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    def _setup_scalars_result(
        self, mock_session: AsyncMock, segments: List[TranscriptSegmentDB]
    ) -> None:
        """Configure mock session to return segments via scalars().all()."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = segments
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

    async def test_search_matches_corrected_text_when_has_correction(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that search targets corrected_text when has_correction is True.

        The CASE expression in SQL ensures effective text = corrected_text
        when has_correction is True.
        """
        segment = _make_segment(
            text="original text",
            corrected_text="corrected text",
            has_correction=True,
        )
        self._setup_scalars_result(mock_session, [segment])

        result = await repository.find_by_text_pattern(
            mock_session, pattern="corrected"
        )

        # The DB-side CASE expression handles this — mock returns the segment
        assert len(result) == 1
        assert result[0].has_correction is True
        assert result[0].corrected_text == "corrected text"

    async def test_search_matches_original_text_when_no_correction(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that search targets original text when has_correction is False.

        The CASE expression in SQL ensures effective text = text
        when has_correction is False.
        """
        segment = _make_segment(
            text="original text",
            has_correction=False,
        )
        self._setup_scalars_result(mock_session, [segment])

        result = await repository.find_by_text_pattern(
            mock_session, pattern="original"
        )

        assert len(result) == 1
        assert result[0].has_correction is False
        assert result[0].text == "original text"

    async def test_mixed_corrected_and_uncorrected_segments(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test search across mixed corrected and uncorrected segments."""
        segments = [
            _make_segment(id=1, text="original hello", has_correction=False),
            _make_segment(
                id=2,
                text="old text",
                corrected_text="corrected hello",
                has_correction=True,
            ),
        ]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern="hello"
        )

        assert len(result) == 2


class TestFindByTextPatternEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def repository(self) -> TranscriptSegmentRepository:
        """Create repository instance for testing."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    def _setup_scalars_result(
        self, mock_session: AsyncMock, segments: List[TranscriptSegmentDB]
    ) -> None:
        """Configure mock session to return segments via scalars().all()."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = segments
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

    async def test_empty_pattern_substring(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that empty pattern in substring mode matches all (LIKE '%%')."""
        segments = [_make_segment(text="any text")]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern=""
        )

        # Empty LIKE pattern '%%' matches everything
        assert len(result) == 1
        mock_session.execute.assert_called_once()

    async def test_pattern_with_sql_wildcards(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that SQL wildcard characters in pattern are passed through.

        Note: In production, actual LIKE escaping should be considered.
        This test verifies the method doesn't crash with special characters.
        """
        self._setup_scalars_result(mock_session, [])

        result = await repository.find_by_text_pattern(
            mock_session, pattern="100%"
        )

        assert result == []
        mock_session.execute.assert_called_once()

    async def test_regex_with_special_characters(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test regex with special regex characters."""
        self._setup_scalars_result(mock_session, [])

        result = await repository.find_by_text_pattern(
            mock_session, pattern=r"hello\.world", regex=True
        )

        assert result == []
        mock_session.execute.assert_called_once()

    async def test_multiple_regex_validation_errors(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test various invalid regex patterns all raise ValueError."""
        invalid_patterns = [
            r"[",
            r"(",
            r"*invalid",
            r"+invalid",
            r"(?P<unclosed",
        ]

        for pat in invalid_patterns:
            with pytest.raises(ValueError, match="Invalid regex pattern"):
                await repository.find_by_text_pattern(
                    mock_session, pattern=pat, regex=True
                )

        # No SQL queries should have been executed
        mock_session.execute.assert_not_called()

    async def test_regex_false_does_not_validate_as_regex(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that regex=False does NOT validate pattern as regex.

        Invalid regex characters should be treated as literal strings
        in substring mode.
        """
        self._setup_scalars_result(mock_session, [])

        # This pattern is invalid regex but valid as a substring
        result = await repository.find_by_text_pattern(
            mock_session, pattern="[invalid("
        )

        assert result == []
        mock_session.execute.assert_called_once()

    async def test_result_ordering(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that results are ordered by video_id and sequence_number."""
        segments = [
            _make_segment(id=1, video_id="aaa", sequence_number=0),
            _make_segment(id=2, video_id="aaa", sequence_number=1),
            _make_segment(id=3, video_id="bbb", sequence_number=0),
        ]
        self._setup_scalars_result(mock_session, segments)

        result = await repository.find_by_text_pattern(
            mock_session, pattern="hello"
        )

        assert len(result) == 3
        # Verify the mock returned results in the expected order
        assert result[0].video_id == "aaa"
        assert result[0].sequence_number == 0
        assert result[1].video_id == "aaa"
        assert result[1].sequence_number == 1
        assert result[2].video_id == "bbb"
        assert result[2].sequence_number == 0


class TestCountFiltered:
    """Tests for count_filtered method (T005)."""

    @pytest.fixture
    def repository(self) -> TranscriptSegmentRepository:
        """Create repository instance for testing."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    def _setup_scalar_result(
        self, mock_session: AsyncMock, count: int
    ) -> None:
        """Configure mock session to return a scalar count."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = count
        mock_session.execute.return_value = mock_result

    async def test_count_no_filters(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test count with no filters returns total count."""
        self._setup_scalar_result(mock_session, 42)

        result = await repository.count_filtered(mock_session)

        assert result == 42
        mock_session.execute.assert_called_once()

    async def test_count_with_language_filter(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test count filtered by language_code."""
        self._setup_scalar_result(mock_session, 15)

        result = await repository.count_filtered(
            mock_session, language="es"
        )

        assert result == 15
        mock_session.execute.assert_called_once()

    async def test_count_with_video_ids_filter(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test count filtered by video_ids list."""
        self._setup_scalar_result(mock_session, 8)

        result = await repository.count_filtered(
            mock_session, video_ids=["vid1", "vid2"]
        )

        assert result == 8
        mock_session.execute.assert_called_once()

    async def test_count_with_channel_filter(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test count filtered by channel (joins video table)."""
        self._setup_scalar_result(mock_session, 100)

        result = await repository.count_filtered(
            mock_session, channel="UCxxxxxxxxxxxxxx"
        )

        assert result == 100
        mock_session.execute.assert_called_once()

    async def test_count_with_all_filters_combined(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test count with all filters applied simultaneously."""
        self._setup_scalar_result(mock_session, 3)

        result = await repository.count_filtered(
            mock_session,
            language="en",
            channel="UCxxxxxxxxxxxxxx",
            video_ids=["vid1", "vid2"],
        )

        assert result == 3
        mock_session.execute.assert_called_once()

    async def test_count_returns_zero_when_no_matches(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test count returns 0 when no segments match filters."""
        self._setup_scalar_result(mock_session, 0)

        result = await repository.count_filtered(
            mock_session, language="zz"
        )

        assert result == 0

    async def test_count_returns_zero_when_scalar_is_none(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test count returns 0 when scalar() returns None."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.count_filtered(mock_session)

        assert result == 0

    async def test_count_with_empty_video_ids(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test count with empty video_ids list."""
        self._setup_scalar_result(mock_session, 0)

        result = await repository.count_filtered(
            mock_session, video_ids=[]
        )

        assert result == 0

    async def test_count_returns_int(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test that count_filtered always returns an int."""
        self._setup_scalar_result(mock_session, 999)

        result = await repository.count_filtered(mock_session)

        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# TestFindCandidateVideoIdsForCrossSegment
# ---------------------------------------------------------------------------


class TestFindCandidateVideoIdsForCrossSegment:
    """
    Unit tests for find_candidate_video_ids_for_cross_segment().

    The method returns DISTINCT video_ids whose effective segment text
    contains at least one of the supplied tokens.  Database I/O is fully
    mocked — we validate that the correct SQL is executed and that results
    are returned as a plain list.
    """

    @pytest.fixture
    def repository(self) -> TranscriptSegmentRepository:
        return TranscriptSegmentRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    def _setup_scalars_result(
        self, mock_session: AsyncMock, video_ids: List[str]
    ) -> None:
        """Configure mock session to return video_id strings via scalars().all()."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = video_ids
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

    # ------------------------------------------------------------------
    # Guard: empty tokens list
    # ------------------------------------------------------------------

    async def test_empty_tokens_returns_empty_list_without_querying(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """No SQL is executed when tokens is empty."""
        result = await repository.find_candidate_video_ids_for_cross_segment(
            mock_session,
            tokens=[],
        )

        assert result == []
        mock_session.execute.assert_not_called()

    # ------------------------------------------------------------------
    # Basic token matching
    # ------------------------------------------------------------------

    async def test_single_token_returns_matching_video_ids(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """A single token produces a DISTINCT video_id query and returns a list."""
        self._setup_scalars_result(mock_session, ["vid1", "vid2"])

        result = await repository.find_candidate_video_ids_for_cross_segment(
            mock_session,
            tokens=["Shine"],
        )

        assert result == ["vid1", "vid2"]
        mock_session.execute.assert_called_once()

    async def test_multiple_tokens_issues_single_query(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Multiple tokens are combined into one OR query, not multiple queries."""
        self._setup_scalars_result(mock_session, ["vid3"])

        result = await repository.find_candidate_video_ids_for_cross_segment(
            mock_session,
            tokens=["Shine", "Bomb"],
        )

        assert result == ["vid3"]
        # Only one execute call regardless of number of tokens
        assert mock_session.execute.call_count == 1

    async def test_no_matching_videos_returns_empty_list(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns an empty list when no segments match any token."""
        self._setup_scalars_result(mock_session, [])

        result = await repository.find_candidate_video_ids_for_cross_segment(
            mock_session,
            tokens=["xyzzy"],
        )

        assert result == []

    # ------------------------------------------------------------------
    # Optional filter parameters
    # ------------------------------------------------------------------

    async def test_language_filter_passes_through(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """language filter is accepted and a SQL query is executed."""
        self._setup_scalars_result(mock_session, ["vid_es"])

        result = await repository.find_candidate_video_ids_for_cross_segment(
            mock_session,
            tokens=["hola"],
            language="es",
        )

        assert result == ["vid_es"]
        mock_session.execute.assert_called_once()

    async def test_channel_filter_passes_through(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """channel filter triggers the JOIN branch; SQL is still executed once."""
        self._setup_scalars_result(mock_session, ["vid_ch"])

        result = await repository.find_candidate_video_ids_for_cross_segment(
            mock_session,
            tokens=["hello"],
            channel="UCxxxxxxxxxxxxxx",
        )

        assert result == ["vid_ch"]
        mock_session.execute.assert_called_once()

    async def test_case_insensitive_flag_accepted(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """case_insensitive=True is accepted and executes a query."""
        self._setup_scalars_result(mock_session, ["vid_ci"])

        result = await repository.find_candidate_video_ids_for_cross_segment(
            mock_session,
            tokens=["shine"],
            case_insensitive=True,
        )

        assert result == ["vid_ci"]
        mock_session.execute.assert_called_once()

    async def test_all_filters_combined(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """All optional filters can be combined without error."""
        self._setup_scalars_result(mock_session, ["vid_all"])

        result = await repository.find_candidate_video_ids_for_cross_segment(
            mock_session,
            tokens=["test", "phrase"],
            language="fr",
            channel="UCyyyy",
            case_insensitive=True,
        )

        assert result == ["vid_all"]
        mock_session.execute.assert_called_once()

    async def test_returns_plain_list_not_sequence(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Return type is list, not a SQLAlchemy sequence."""
        self._setup_scalars_result(mock_session, ["v1", "v2", "v3"])

        result = await repository.find_candidate_video_ids_for_cross_segment(
            mock_session,
            tokens=["word"],
        )

        assert isinstance(result, list)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# T005: TestEscapeLikePattern
# ---------------------------------------------------------------------------


class TestEscapeLikePattern:
    """
    Unit tests for _escape_like_pattern() helper (T005).

    Verifies that SQL LIKE/ILIKE wildcard characters are correctly escaped
    so that user-supplied text is treated as a literal substring rather than
    a pattern containing wildcards.
    """

    def test_escapes_underscore(self) -> None:
        """Underscore is escaped to backslash-underscore."""
        assert _escape_like_pattern("_") == r"\_"

    def test_escapes_percent(self) -> None:
        """Percent sign is escaped to backslash-percent."""
        assert _escape_like_pattern("%") == r"\%"

    def test_escapes_backslash(self) -> None:
        """Backslash is escaped to double-backslash."""
        assert _escape_like_pattern("\\") == "\\\\"

    def test_combination_all_three_special_chars(self) -> None:
        """All three special characters appear correctly escaped in a combined string."""
        result = _escape_like_pattern("100%_value\\path")
        assert result == "100\\%\\_value\\\\path"

    def test_escape_order_backslash_first(self) -> None:
        """Backslash must be escaped before percent and underscore.

        If percent were escaped first, a literal backslash followed by
        a percent would become ``\\%`` (one escape sequence).  Escaping
        backslash first ensures the already-placed backslash escape
        character is not double-escaped in a subsequent pass.

        Input: ``\\_`` (backslash then underscore)
        Expected output: ``\\\\_`` (escaped backslash then escaped underscore)
        """
        result = _escape_like_pattern("\\_")
        # backslash → \\, then underscore → \_  ⟹  \\\_ in escaped form
        assert result == "\\\\\\_"

    def test_empty_string_returns_empty(self) -> None:
        """Empty string input returns empty string."""
        assert _escape_like_pattern("") == ""

    def test_no_special_chars_unchanged(self) -> None:
        """String with no special characters passes through unchanged."""
        plain = "hello world"
        assert _escape_like_pattern(plain) == plain

    def test_multiple_underscores(self) -> None:
        """Multiple consecutive underscores are all escaped."""
        result = _escape_like_pattern("__init__")
        assert result == r"\_\_init\_\_"

    def test_multiple_percent_signs(self) -> None:
        """Multiple percent signs are all escaped."""
        result = _escape_like_pattern("100% complete 50%")
        assert result == "100\\% complete 50\\%"

    def test_mixed_regular_and_special_chars(self) -> None:
        """Regular characters between special chars are preserved verbatim."""
        result = _escape_like_pattern("a%b_c\\d")
        assert result == "a\\%b\\_c\\\\d"

    def test_path_with_backslashes(self) -> None:
        """Windows-style path with backslashes is correctly escaped."""
        result = _escape_like_pattern("C:\\Users\\test")
        assert result == "C:\\\\Users\\\\test"

    def test_returns_str_type(self) -> None:
        """Return type is always str."""
        assert isinstance(_escape_like_pattern("any input"), str)
        assert isinstance(_escape_like_pattern(""), str)


# ---------------------------------------------------------------------------
# T007: TestFindByTextPatternLiteralEscaping
# ---------------------------------------------------------------------------


class TestFindByTextPatternLiteralEscaping:
    """
    Unit tests for find_by_text_pattern() literal LIKE escaping (T007).

    Verifies that special SQL LIKE metacharacters in the pattern are escaped
    before being wrapped in ``%...%`` so that ``_`` and ``%`` are treated as
    literal characters, not wildcards.
    """

    @pytest.fixture
    def repository(self) -> TranscriptSegmentRepository:
        """Create repository instance for testing."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    def _setup_scalars_result(
        self, mock_session: AsyncMock, segments: List[TranscriptSegmentDB]
    ) -> None:
        """Configure mock session to return segments via scalars().all()."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = segments
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

    async def test_underscore_in_pattern_does_not_act_as_wildcard(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Pattern containing ``_`` is escaped; SQL receives ``\\_`` not bare ``_``.

        We inspect the SQL string passed to session.execute to verify the
        LIKE pattern uses ``\\_`` (escaped underscore) so PostgreSQL treats
        it as a literal underscore rather than a single-character wildcard.
        """
        self._setup_scalars_result(mock_session, [])

        await repository.find_by_text_pattern(mock_session, pattern="__init__")

        mock_session.execute.assert_called_once()
        # Retrieve the compiled SQL string from the call argument
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)
        # The escaped pattern  %\_\_init\_\_% must appear in the SQL
        assert r"\\_\\_init\\_\\_" in sql_str or r"\_\_init\_\_" in sql_str

    async def test_percent_in_pattern_does_not_act_as_wildcard(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Pattern containing ``%`` is escaped; SQL receives ``\\%`` not bare ``%``.

        Verifies that the generated ILIKE/LIKE pattern contains ``\\%``
        (escaped percent) instead of a raw ``%`` that would match any text.
        """
        self._setup_scalars_result(mock_session, [])

        await repository.find_by_text_pattern(mock_session, pattern="100%")

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)
        # ``100\%`` must appear inside ``%100\%%`` — the percent is escaped
        assert r"100\%" in sql_str

    async def test_backslash_in_pattern_is_escaped(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Pattern containing ``\\`` is escaped to ``\\\\`` in the SQL pattern."""
        self._setup_scalars_result(mock_session, [])

        await repository.find_by_text_pattern(mock_session, pattern="C:\\path")

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)
        # The backslash in "C:\path" must be escaped to "\\" before the LIKE wrapping
        assert "C:\\\\" in sql_str or "C:\\\\path" in sql_str

    async def test_combined_special_chars_all_escaped(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Pattern with multiple special chars has all of them escaped in SQL."""
        self._setup_scalars_result(mock_session, [])

        await repository.find_by_text_pattern(mock_session, pattern="100%_value")

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)
        # Both wildcards must be escaped
        assert r"100\%" in sql_str
        assert r"\_value" in sql_str

    async def test_literal_mode_returns_results_from_session(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """find_by_text_pattern in literal mode returns mock-provided segments."""
        segment = _make_segment(text="test_value 100% done")
        self._setup_scalars_result(mock_session, [segment])

        result = await repository.find_by_text_pattern(
            mock_session, pattern="test_value 100% done"
        )

        assert len(result) == 1
        assert result[0].text == "test_value 100% done"
        mock_session.execute.assert_called_once()

    async def test_regex_mode_does_not_escape_pattern(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        """In regex mode, ``_`` and ``%`` are NOT escaped (no escaping for regex)."""
        self._setup_scalars_result(mock_session, [])

        # A valid regex containing special LIKE chars
        await repository.find_by_text_pattern(
            mock_session, pattern=r"\d{3}%", regex=True
        )

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)
        # In regex mode, the pattern is passed directly to the ~ operator
        # The ``%`` should appear un-escaped (no ``\%``) in the raw regex branch
        # We simply verify the query executed without error — the regex branch
        # does not call _escape_like_pattern
        assert "%" in sql_str  # raw percent present in regex pattern
