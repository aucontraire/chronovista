"""
Tests for TranscriptSegmentRepository.

Tests timestamp-based query methods including half-open interval semantics
per Feature 008: Transcript Segment Table (Phase 2).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.transcript_segment import TranscriptSegmentCreate
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)

pytestmark = pytest.mark.asyncio


class TestTranscriptSegmentRepository:
    """Tests for TranscriptSegmentRepository methods."""

    @pytest.fixture
    def repository(self) -> TranscriptSegmentRepository:
        """Create repository instance for testing."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def sample_segments(self) -> List[TranscriptSegmentDB]:
        """Create sample segments: [0-2.5], [2.5-5.0], [5.0-7.5]."""
        base_time = datetime.now(timezone.utc)
        return [
            TranscriptSegmentDB(
                id=1,
                video_id="dQw4w9WgXcQ",
                language_code="en",
                text="Segment one",
                start_time=0.0,
                duration=2.5,
                end_time=2.5,
                sequence_number=0,
                has_correction=False,
                corrected_text=None,
                created_at=base_time,
            ),
            TranscriptSegmentDB(
                id=2,
                video_id="dQw4w9WgXcQ",
                language_code="en",
                text="Segment two",
                start_time=2.5,
                duration=2.5,
                end_time=5.0,
                sequence_number=1,
                has_correction=False,
                corrected_text=None,
                created_at=base_time,
            ),
            TranscriptSegmentDB(
                id=3,
                video_id="dQw4w9WgXcQ",
                language_code="en",
                text="Segment three",
                start_time=5.0,
                duration=2.5,
                end_time=7.5,
                sequence_number=2,
                has_correction=False,
                corrected_text=None,
                created_at=base_time,
            ),
        ]

    @pytest.fixture
    def sample_segments_with_gap(self) -> List[TranscriptSegmentDB]:
        """Create sample segments with gap: [0-2.0], [5.0-7.0] (gap 2.0-5.0)."""
        base_time = datetime.now(timezone.utc)
        return [
            TranscriptSegmentDB(
                id=1,
                video_id="gapTest1234",
                language_code="en",
                text="First segment",
                start_time=0.0,
                duration=2.0,
                end_time=2.0,
                sequence_number=0,
                has_correction=False,
                corrected_text=None,
                created_at=base_time,
            ),
            TranscriptSegmentDB(
                id=2,
                video_id="gapTest1234",
                language_code="en",
                text="Second segment after gap",
                start_time=5.0,
                duration=2.0,
                end_time=7.0,
                sequence_number=1,
                has_correction=False,
                corrected_text=None,
                created_at=base_time,
            ),
        ]

    async def test_get_segment_at_time_returns_containing_segment(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
        sample_segments: List[TranscriptSegmentDB],
    ):
        """Test that get_segment_at_time returns the segment containing the timestamp.

        Create segments: [0-2.5], [2.5-5.0], [5.0-7.5]
        Query timestamp 1.0 should return first segment.
        Query timestamp 3.0 should return second segment.
        """
        # First query: timestamp 1.0 should return first segment
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_segments[0]
        mock_session.execute.return_value = mock_result

        result = await repository.get_segment_at_time(
            mock_session, "dQw4w9WgXcQ", "en", 1.0
        )

        assert result is not None
        assert result.id == 1
        assert result.text == "Segment one"
        mock_session.execute.assert_called_once()

    async def test_get_segment_at_time_half_open_interval(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
        sample_segments: List[TranscriptSegmentDB],
    ):
        """Test half-open interval: timestamp at boundary returns segment starting there (FR-EDGE-01).

        Create segments: [0-2.5], [2.5-5.0]
        Query timestamp 2.5 should return SECOND segment (starts at 2.5).
        """
        # When querying at exact boundary (2.5), should return segment that starts at 2.5
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_segments[1]
        mock_session.execute.return_value = mock_result

        result = await repository.get_segment_at_time(
            mock_session, "dQw4w9WgXcQ", "en", 2.5
        )

        # Half-open interval [start, end) means:
        # - First segment contains times in [0, 2.5)
        # - Second segment contains times in [2.5, 5.0)
        # So timestamp 2.5 should return second segment
        assert result is not None
        assert result.id == 2
        assert result.start_time == 2.5

    async def test_get_segment_at_time_in_gap_returns_previous(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
        sample_segments_with_gap: List[TranscriptSegmentDB],
    ):
        """Test that timestamp in gap between segments returns previous segment.

        Create segments: [0-2.0], [5.0-7.0] (gap from 2.0-5.0)
        Query timestamp 3.0 should return first segment (previous).
        """
        # First call for exact match returns None (timestamp 3.0 is in gap)
        mock_result_exact = MagicMock()
        mock_result_exact.scalar_one_or_none.return_value = None

        # Second call for gap fallback returns first segment
        mock_result_gap = MagicMock()
        mock_result_gap.scalar_one_or_none.return_value = sample_segments_with_gap[0]

        mock_session.execute.side_effect = [mock_result_exact, mock_result_gap]

        result = await repository.get_segment_at_time(
            mock_session, "gapTest1234", "en", 3.0
        )

        # Should return the previous segment (first one that ends before timestamp)
        assert result is not None
        assert result.id == 1
        assert result.end_time == 2.0
        assert mock_session.execute.call_count == 2

    async def test_get_segment_at_time_before_first_returns_none(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ):
        """Test that timestamp before first segment returns None.

        Create segment starting at 5.0
        Query timestamp 1.0 should return None.
        """
        # Both exact match and gap fallback return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_segment_at_time(
            mock_session, "dQw4w9WgXcQ", "en", 1.0
        )

        assert result is None

    async def test_get_segments_in_range_returns_overlapping(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
        sample_segments: List[TranscriptSegmentDB],
    ):
        """Test that get_segments_in_range returns all overlapping segments.

        Create segments: [0-2.5], [2.5-5.0], [5.0-7.5]
        Query range 3.0-5.5 should return segments 2 and 3.
        """
        # Segments overlapping with range 3.0-5.5:
        # - Segment 2 [2.5-5.0]: overlaps (2.5 < 5.5 AND 5.0 > 3.0)
        # - Segment 3 [5.0-7.5]: overlaps (5.0 < 5.5 AND 7.5 > 3.0)
        overlapping_segments = [sample_segments[1], sample_segments[2]]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = overlapping_segments
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_segments_in_range(
            mock_session, "dQw4w9WgXcQ", "en", 3.0, 5.5
        )

        assert len(result) == 2
        assert result[0].id == 2
        assert result[1].id == 3
        mock_session.execute.assert_called_once()

    async def test_get_segments_in_range_empty_returns_empty_list(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ):
        """Test that query with no matching segments returns empty list."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_segments_in_range(
            mock_session, "dQw4w9WgXcQ", "en", 100.0, 200.0
        )

        assert result == []
        mock_session.execute.assert_called_once()

    async def test_get_context_window_symmetric(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
        sample_segments: List[TranscriptSegmentDB],
    ):
        """Test that get_context_window returns segments +/-window_seconds from timestamp.

        Create segments across 0-7.5 seconds
        Query timestamp 4.0 with window 3 should return segments from 1.0-7.0
        which overlaps all three segments.
        """
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = sample_segments
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_context_window(
            mock_session, "dQw4w9WgXcQ", "en", 4.0, 3.0
        )

        # Window is [1.0, 7.0] which overlaps all segments
        assert len(result) == 3
        mock_session.execute.assert_called_once()

    async def test_get_context_window_clamps_start_at_zero(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
        sample_segments: List[TranscriptSegmentDB],
    ):
        """Test that context window clamps start time at 0."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_segments[0]]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Query at timestamp 1.0 with window 5.0 would give range [-4.0, 6.0]
        # But start should be clamped to 0, so range is [0.0, 6.0]
        result = await repository.get_context_window(
            mock_session, "dQw4w9WgXcQ", "en", 1.0, 5.0
        )

        assert len(result) >= 1
        mock_session.execute.assert_called_once()

    async def test_bulk_create_segments_creates_all(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ):
        """Test that bulk_create_segments creates all provided segments."""
        segments_to_create = [
            TranscriptSegmentCreate(
                video_id="dQw4w9WgXcQ",
                language_code="en",
                text="Segment one",
                start_time=0.0,
                duration=2.5,
                end_time=2.5,
                sequence_number=0,
            ),
            TranscriptSegmentCreate(
                video_id="dQw4w9WgXcQ",
                language_code="en",
                text="Segment two",
                start_time=2.5,
                duration=2.5,
                end_time=5.0,
                sequence_number=1,
            ),
        ]

        mock_session.add_all.return_value = None
        mock_session.flush.return_value = None

        count = await repository.bulk_create_segments(mock_session, segments_to_create)

        assert count == 2
        mock_session.add_all.assert_called_once()
        mock_session.flush.assert_called_once()

        # Verify the objects passed to add_all
        added_objects = mock_session.add_all.call_args[0][0]
        assert len(added_objects) == 2
        assert all(isinstance(obj, TranscriptSegmentDB) for obj in added_objects)

    async def test_bulk_create_segments_empty_list(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ):
        """Test that bulk_create_segments handles empty list."""
        mock_session.add_all.return_value = None
        mock_session.flush.return_value = None

        count = await repository.bulk_create_segments(mock_session, [])

        assert count == 0
        mock_session.add_all.assert_called_once()

    async def test_delete_segments_for_transcript(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ):
        """Test idempotent deletion of segments for a transcript."""
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        count = await repository.delete_segments_for_transcript(
            mock_session, "dQw4w9WgXcQ", "en"
        )

        assert count == 3
        mock_session.execute.assert_called_once()

    async def test_delete_segments_for_transcript_none_found(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ):
        """Test deletion when no segments exist (idempotent)."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await repository.delete_segments_for_transcript(
            mock_session, "nonExist1234", "en"
        )

        assert count == 0
        mock_session.execute.assert_called_once()


class TestTranscriptSegmentRepositoryEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def repository(self) -> TranscriptSegmentRepository:
        """Create repository instance for testing."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    async def test_get_segment_at_time_zero(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ):
        """Test querying at timestamp 0.0."""
        first_segment = TranscriptSegmentDB(
            id=1,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="First segment",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
            has_correction=False,
            corrected_text=None,
            created_at=datetime.now(timezone.utc),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = first_segment
        mock_session.execute.return_value = mock_result

        result = await repository.get_segment_at_time(
            mock_session, "dQw4w9WgXcQ", "en", 0.0
        )

        assert result is not None
        assert result.start_time == 0.0

    async def test_get_segments_in_range_exact_boundaries(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ):
        """Test range query with exact segment boundaries."""
        segment = TranscriptSegmentDB(
            id=1,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Segment",
            start_time=2.5,
            duration=2.5,
            end_time=5.0,
            sequence_number=0,
            has_correction=False,
            corrected_text=None,
            created_at=datetime.now(timezone.utc),
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [segment]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Range exactly matches segment boundaries
        result = await repository.get_segments_in_range(
            mock_session, "dQw4w9WgXcQ", "en", 2.5, 5.0
        )

        assert len(result) == 1

    async def test_get_segment_at_exact_end_time(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ):
        """Test querying at exact end_time of a segment.

        Per half-open interval [start, end), timestamp at end_time should NOT
        match the segment - it should match the next segment if one starts there.
        """
        # First query (exact match) returns None because 5.0 is at end of segment 2
        # and start of segment 3 (if there's a next segment)
        mock_result_exact = MagicMock()
        mock_result_exact.scalar_one_or_none.return_value = None

        # Second query (gap fallback) returns the previous segment
        mock_result_gap = MagicMock()
        mock_result_gap.scalar_one_or_none.return_value = TranscriptSegmentDB(
            id=2,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Segment two",
            start_time=2.5,
            duration=2.5,
            end_time=5.0,
            sequence_number=1,
            has_correction=False,
            corrected_text=None,
            created_at=datetime.now(timezone.utc),
        )

        mock_session.execute.side_effect = [mock_result_exact, mock_result_gap]

        result = await repository.get_segment_at_time(
            mock_session, "dQw4w9WgXcQ", "en", 5.0
        )

        # If no segment starts at 5.0, should return previous segment as gap fallback
        # This tests the gap handling for timestamps at segment boundaries
        assert result is not None

    async def test_zero_duration_segment(
        self,
        repository: TranscriptSegmentRepository,
        mock_session: AsyncMock,
    ):
        """Test handling of zero-duration segments (FR-EDGE-07)."""
        zero_duration_segment = TranscriptSegmentDB(
            id=1,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="[Music]",
            start_time=10.0,
            duration=0.0,
            end_time=10.0,  # Same as start
            sequence_number=0,
            has_correction=False,
            corrected_text=None,
            created_at=datetime.now(timezone.utc),
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [zero_duration_segment]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Zero duration segment should still be queryable in range
        result = await repository.get_segments_in_range(
            mock_session, "dQw4w9WgXcQ", "en", 9.0, 11.0
        )

        assert len(result) == 1
        assert result[0].duration == 0.0


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
class TestTranscriptSegmentRepositoryInitialization:
    """Tests for repository initialization.

    Note: These are synchronous tests but pytestmark applies to entire module.
    The filterwarnings decorator suppresses the related pytest warnings.
    """

    def test_repository_initialization(self):
        """Test repository can be instantiated."""
        repo = TranscriptSegmentRepository()
        assert repo is not None

    def test_repository_model_attribute(self):
        """Test repository has correct model attribute."""
        repo = TranscriptSegmentRepository()
        assert repo.model == TranscriptSegmentDB
