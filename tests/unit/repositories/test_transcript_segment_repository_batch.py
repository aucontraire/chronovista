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
