"""
Tests for TranscriptSegment SQLAlchemy model and Pydantic models.

Tests model field types, constraints, relationships, and cascade delete behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, cast

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel,
    TranscriptSegment as TranscriptSegmentDB,
    Video,
    VideoTranscript,
)
from chronovista.models.transcript_segment import (
    TranscriptSegment,
    TranscriptSegmentBase,
    TranscriptSegmentCreate,
    TranscriptSegmentResponse,
)
from tests.factories.transcript_segment_factory import (
    TranscriptSegmentFactory,
    TranscriptSegmentTestData,
    create_batch_transcript_segments,
    create_corrected_transcript_segment,
    create_transcript_segment,
    create_transcript_segment_base,
    create_transcript_segment_create,
)

# Mark all tests in this file as asyncio (for async tests only)
# pytestmark = pytest.mark.asyncio  # We'll use this selectively instead


# =============================================================================
# SQLAlchemy Model Tests
# =============================================================================

# Note: SQLAlchemy tests require a database connection.
# These tests will be skipped if database is not available.
# Use pytest-asyncio decorator for async tests.


@pytest.mark.db
@pytest.mark.asyncio
class TestTranscriptSegmentSQLAlchemyModel:
    """Tests for TranscriptSegment SQLAlchemy model."""

    async def test_create_segment_with_required_fields(self, db_session: AsyncSession):
        """Test creating a segment with all required fields."""
        # Create prerequisite records (channel -> video -> transcript)
        channel = Channel(
            channel_id="UC_test_channel",
            title="Test Channel",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="dQw4w9WgXcQ",
            channel_id=channel.channel_id,
            title="Test Video",
            upload_date=datetime.now(timezone.utc),
            duration=300,
        )
        db_session.add(video)
        await db_session.flush()

        transcript = VideoTranscript(
            video_id=video.video_id,
            language_code="en",
            transcript_text="Full transcript text",
            transcript_type="AUTO",
            download_reason="USER_REQUEST",
        )
        db_session.add(transcript)
        await db_session.flush()

        # Create segment
        segment = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="Hello world",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
        )
        db_session.add(segment)
        await db_session.commit()

        # Verify segment was created
        assert segment.id is not None
        assert segment.video_id == "dQw4w9WgXcQ"
        assert segment.text == "Hello world"
        assert segment.start_time == 0.0
        assert segment.duration == 2.5
        assert segment.end_time == 2.5
        assert segment.sequence_number == 0
        assert segment.has_correction is False
        assert segment.corrected_text is None

    async def test_segment_relationship_to_transcript(self, db_session: AsyncSession):
        """Test that segment.transcript returns the parent VideoTranscript."""
        # Create chain: channel -> video -> transcript -> segment
        channel = Channel(
            channel_id="UC_test_channel",
            title="Test Channel",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="dQw4w9WgXcQ",
            channel_id=channel.channel_id,
            title="Test Video",
            upload_date=datetime.now(timezone.utc),
            duration=300,
        )
        db_session.add(video)
        await db_session.flush()

        transcript = VideoTranscript(
            video_id=video.video_id,
            language_code="en",
            transcript_text="Full transcript text",
            transcript_type="AUTO",
            download_reason="USER_REQUEST",
        )
        db_session.add(transcript)
        await db_session.flush()

        segment = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="Hello world",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
        )
        db_session.add(segment)
        await db_session.commit()

        # Refresh segment to load relationships
        await db_session.refresh(segment)

        # Verify relationship
        assert segment.transcript is not None
        assert segment.transcript.video_id == transcript.video_id
        assert segment.transcript.language_code == transcript.language_code

    async def test_transcript_segments_relationship(self, db_session: AsyncSession):
        """Test that transcript.segments returns ordered segments."""
        # Create transcript with multiple segments
        channel = Channel(
            channel_id="UC_test_channel",
            title="Test Channel",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="dQw4w9WgXcQ",
            channel_id=channel.channel_id,
            title="Test Video",
            upload_date=datetime.now(timezone.utc),
            duration=300,
        )
        db_session.add(video)
        await db_session.flush()

        transcript = VideoTranscript(
            video_id=video.video_id,
            language_code="en",
            transcript_text="Full transcript text",
            transcript_type="AUTO",
            download_reason="USER_REQUEST",
        )
        db_session.add(transcript)
        await db_session.flush()

        # Create segments out of order
        segment2 = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="Second segment",
            start_time=2.5,
            duration=2.5,
            end_time=5.0,
            sequence_number=1,
        )
        segment0 = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="First segment",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
        )
        segment1 = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="Third segment",
            start_time=5.0,
            duration=2.5,
            end_time=7.5,
            sequence_number=2,
        )
        db_session.add_all([segment2, segment0, segment1])
        await db_session.commit()

        # Query with eager loading for async context
        from sqlalchemy.orm import selectinload

        result = await db_session.execute(
            select(VideoTranscript)
            .where(VideoTranscript.video_id == video.video_id)
            .where(VideoTranscript.language_code == "en")
            .options(selectinload(VideoTranscript.segments))
        )
        transcript_with_segments = result.scalar_one()

        # Verify segments are returned in sequence_number order
        assert len(transcript_with_segments.segments) == 3
        assert transcript_with_segments.segments[0].sequence_number == 0
        assert transcript_with_segments.segments[0].text == "First segment"
        assert transcript_with_segments.segments[1].sequence_number == 1
        assert transcript_with_segments.segments[1].text == "Second segment"
        assert transcript_with_segments.segments[2].sequence_number == 2
        assert transcript_with_segments.segments[2].text == "Third segment"

    async def test_cascade_delete_removes_segments(self, db_session: AsyncSession):
        """Test that deleting a transcript also deletes its segments."""
        # Create transcript with segments
        channel = Channel(
            channel_id="UC_test_channel",
            title="Test Channel",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="dQw4w9WgXcQ",
            channel_id=channel.channel_id,
            title="Test Video",
            upload_date=datetime.now(timezone.utc),
            duration=300,
        )
        db_session.add(video)
        await db_session.flush()

        transcript = VideoTranscript(
            video_id=video.video_id,
            language_code="en",
            transcript_text="Full transcript text",
            transcript_type="AUTO",
            download_reason="USER_REQUEST",
        )
        db_session.add(transcript)
        await db_session.flush()

        segment = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="Hello world",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
        )
        db_session.add(segment)
        await db_session.commit()

        segment_id = segment.id

        # Delete transcript
        await db_session.delete(transcript)
        await db_session.commit()

        # Verify segment was also deleted (CASCADE)
        result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == segment_id)
        )
        deleted_segment = result.scalar_one_or_none()
        assert deleted_segment is None

    async def test_zero_duration_segment_allowed(self, db_session: AsyncSession):
        """Test that zero-duration segments are valid per FR-EDGE-07."""
        # Create prerequisite records
        channel = Channel(
            channel_id="UC_test_channel",
            title="Test Channel",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="dQw4w9WgXcQ",
            channel_id=channel.channel_id,
            title="Test Video",
            upload_date=datetime.now(timezone.utc),
            duration=300,
        )
        db_session.add(video)
        await db_session.flush()

        transcript = VideoTranscript(
            video_id=video.video_id,
            language_code="en",
            transcript_text="Full transcript text",
            transcript_type="AUTO",
            download_reason="USER_REQUEST",
        )
        db_session.add(transcript)
        await db_session.flush()

        # Create segment with duration=0, end_time=start_time
        segment = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="Point in time",
            start_time=5.0,
            duration=0.0,
            end_time=5.0,
            sequence_number=0,
        )
        db_session.add(segment)
        await db_session.commit()

        # Verify it saved successfully
        assert segment.id is not None
        assert segment.duration == 0.0
        assert segment.end_time == segment.start_time

    async def test_foreign_key_constraint_enforced(self, db_session: AsyncSession):
        """Test that foreign key constraint is enforced."""
        # Try to create segment without corresponding transcript
        segment = TranscriptSegmentDB(
            video_id="nonexistent_video",
            language_code="en",
            text="Orphan segment",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
        )
        db_session.add(segment)

        # Should raise integrity error
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_check_constraint_negative_start_time(self, db_session: AsyncSession):
        """Test that negative start_time is rejected by CHECK constraint."""
        # Create prerequisite records
        channel = Channel(
            channel_id="UC_test_channel",
            title="Test Channel",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="dQw4w9WgXcQ",
            channel_id=channel.channel_id,
            title="Test Video",
            upload_date=datetime.now(timezone.utc),
            duration=300,
        )
        db_session.add(video)
        await db_session.flush()

        transcript = VideoTranscript(
            video_id=video.video_id,
            language_code="en",
            transcript_text="Full transcript text",
            transcript_type="AUTO",
            download_reason="USER_REQUEST",
        )
        db_session.add(transcript)
        await db_session.flush()

        # Create segment with negative start_time
        segment = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="Invalid segment",
            start_time=-1.0,
            duration=2.5,
            end_time=1.5,
            sequence_number=0,
        )
        db_session.add(segment)

        # Should raise integrity error from CHECK constraint
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_check_constraint_negative_duration(self, db_session: AsyncSession):
        """Test that negative duration is rejected by CHECK constraint."""
        # Create prerequisite records
        channel = Channel(
            channel_id="UC_test_channel",
            title="Test Channel",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="dQw4w9WgXcQ",
            channel_id=channel.channel_id,
            title="Test Video",
            upload_date=datetime.now(timezone.utc),
            duration=300,
        )
        db_session.add(video)
        await db_session.flush()

        transcript = VideoTranscript(
            video_id=video.video_id,
            language_code="en",
            transcript_text="Full transcript text",
            transcript_type="AUTO",
            download_reason="USER_REQUEST",
        )
        db_session.add(transcript)
        await db_session.flush()

        # Create segment with negative duration
        segment = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="Invalid segment",
            start_time=5.0,
            duration=-2.5,
            end_time=2.5,
            sequence_number=0,
        )
        db_session.add(segment)

        # Should raise integrity error from CHECK constraint
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_check_constraint_negative_sequence_number(
        self, db_session: AsyncSession
    ):
        """Test that negative sequence_number is rejected by CHECK constraint."""
        # Create prerequisite records
        channel = Channel(
            channel_id="UC_test_channel",
            title="Test Channel",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="dQw4w9WgXcQ",
            channel_id=channel.channel_id,
            title="Test Video",
            upload_date=datetime.now(timezone.utc),
            duration=300,
        )
        db_session.add(video)
        await db_session.flush()

        transcript = VideoTranscript(
            video_id=video.video_id,
            language_code="en",
            transcript_text="Full transcript text",
            transcript_type="AUTO",
            download_reason="USER_REQUEST",
        )
        db_session.add(transcript)
        await db_session.flush()

        # Create segment with negative sequence_number
        segment = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="Invalid segment",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=-1,
        )
        db_session.add(segment)

        # Should raise integrity error from CHECK constraint
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_segment_with_correction(self, db_session: AsyncSession):
        """Test creating a segment with correction fields."""
        # Create prerequisite records
        channel = Channel(
            channel_id="UC_test_channel",
            title="Test Channel",
        )
        db_session.add(channel)
        await db_session.flush()

        video = Video(
            video_id="dQw4w9WgXcQ",
            channel_id=channel.channel_id,
            title="Test Video",
            upload_date=datetime.now(timezone.utc),
            duration=300,
        )
        db_session.add(video)
        await db_session.flush()

        transcript = VideoTranscript(
            video_id=video.video_id,
            language_code="en",
            transcript_text="Full transcript text",
            transcript_type="AUTO",
            download_reason="USER_REQUEST",
        )
        db_session.add(transcript)
        await db_session.flush()

        # Create segment with correction
        segment = TranscriptSegmentDB(
            video_id=video.video_id,
            language_code="en",
            text="Original text with typo",
            corrected_text="Corrected text without typo",
            has_correction=True,
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
        )
        db_session.add(segment)
        await db_session.commit()

        # Verify correction fields
        assert segment.has_correction is True
        assert segment.corrected_text == "Corrected text without typo"
        assert segment.text == "Original text with typo"


# =============================================================================
# Pydantic Model Tests
# =============================================================================


class TestTranscriptSegmentPydanticModels:
    """Tests for TranscriptSegment Pydantic models."""

    def test_base_model_validates_end_time(self):
        """Test that end_time must equal start_time + duration."""
        with pytest.raises(ValueError, match="end_time.*must equal"):
            TranscriptSegmentBase(
                video_id="dQw4w9WgXcQ",
                language_code="en",
                text="Hello",
                start_time=0.0,
                duration=2.5,
                end_time=5.0,  # Wrong! Should be 2.5
                sequence_number=0,
            )

    def test_base_model_accepts_correct_end_time(self):
        """Test that correct end_time passes validation."""
        segment = TranscriptSegmentBase(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Hello",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
        )
        assert segment.end_time == 2.5

    def test_create_from_snippet(self):
        """Test TranscriptSegmentCreate.from_snippet() factory method."""
        snippet = {"text": "Hello world", "start": 1.5, "duration": 3.0}
        segment = TranscriptSegmentCreate.from_snippet(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            snippet=snippet,
            sequence_number=5,
        )
        assert segment.text == "Hello world"
        assert segment.start_time == 1.5
        assert segment.duration == 3.0
        assert segment.end_time == 4.5
        assert segment.sequence_number == 5

    def test_full_model_display_text_original(self):
        """Test display_text returns original text when no correction."""
        segment = TranscriptSegment(
            id=1,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Original text",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
            has_correction=False,
            corrected_text=None,
            created_at=datetime.now(timezone.utc),
        )
        assert segment.display_text == "Original text"

    def test_full_model_display_text_corrected(self):
        """Test display_text returns corrected text when available."""
        segment = TranscriptSegment(
            id=1,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Original text",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
            has_correction=True,
            corrected_text="Corrected text",
            created_at=datetime.now(timezone.utc),
        )
        assert segment.display_text == "Corrected text"

    def test_zero_duration_segment_valid(self):
        """Test that zero duration is allowed per FR-EDGE-07."""
        segment = TranscriptSegmentBase(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Point in time",
            start_time=5.0,
            duration=0.0,
            end_time=5.0,
            sequence_number=0,
        )
        assert segment.duration == 0.0
        assert segment.end_time == segment.start_time

    def test_negative_start_time_rejected(self):
        """Test that negative start_time is rejected."""
        with pytest.raises(ValidationError):
            TranscriptSegmentBase(
                video_id="dQw4w9WgXcQ",
                language_code="en",
                text="Hello",
                start_time=-1.0,
                duration=2.5,
                end_time=1.5,
                sequence_number=0,
            )

    def test_negative_duration_rejected(self):
        """Test that negative duration is rejected."""
        with pytest.raises(ValidationError):
            TranscriptSegmentBase(
                video_id="dQw4w9WgXcQ",
                language_code="en",
                text="Hello",
                start_time=5.0,
                duration=-2.5,
                end_time=2.5,
                sequence_number=0,
            )

    def test_negative_sequence_number_rejected(self):
        """Test that negative sequence_number is rejected."""
        with pytest.raises(ValidationError):
            TranscriptSegmentBase(
                video_id="dQw4w9WgXcQ",
                language_code="en",
                text="Hello",
                start_time=0.0,
                duration=2.5,
                end_time=2.5,
                sequence_number=-1,
            )

    def test_response_model_from_segment(self):
        """Test TranscriptSegmentResponse.from_segment() conversion."""
        full_segment = TranscriptSegment(
            id=42,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Hello world",
            start_time=90.0,
            duration=3.0,
            end_time=93.0,
            sequence_number=10,
            has_correction=False,
            corrected_text=None,
            created_at=datetime.now(timezone.utc),
        )
        response = TranscriptSegmentResponse.from_segment(full_segment)
        assert response.segment_id == 42
        assert response.text == "Hello world"
        assert response.start_formatted == "1:30"
        assert response.end_formatted == "1:33"

    def test_response_model_with_corrected_text(self):
        """Test TranscriptSegmentResponse uses display_text for corrected segments."""
        full_segment = TranscriptSegment(
            id=42,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Original text",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
            has_correction=True,
            corrected_text="Corrected text",
            created_at=datetime.now(timezone.utc),
        )
        response = TranscriptSegmentResponse.from_segment(full_segment)
        assert response.text == "Corrected text"

    def test_empty_text_rejected(self):
        """Test that empty text is rejected."""
        with pytest.raises(ValidationError):
            TranscriptSegmentBase(
                video_id="dQw4w9WgXcQ",
                language_code="en",
                text="",
                start_time=0.0,
                duration=2.5,
                end_time=2.5,
                sequence_number=0,
            )

    def test_invalid_video_id_rejected(self):
        """Test that invalid video IDs are rejected."""
        with pytest.raises(ValidationError):
            TranscriptSegmentBase(
                video_id="invalid",  # Too short
                language_code="en",
                text="Hello",
                start_time=0.0,
                duration=2.5,
                end_time=2.5,
                sequence_number=0,
            )

    def test_from_snippet_with_zero_duration(self):
        """Test from_snippet with zero duration."""
        snippet = {"text": "Quick flash", "start": 10.0, "duration": 0.0}
        segment = TranscriptSegmentCreate.from_snippet(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            snippet=snippet,
            sequence_number=0,
        )
        assert segment.duration == 0.0
        assert segment.end_time == 10.0


# =============================================================================
# Factory Tests
# =============================================================================


class TestTranscriptSegmentFactory:
    """Tests for TranscriptSegment factory patterns."""

    def test_base_factory_creates_valid_segment(self):
        """Test that base factory creates valid segment."""
        segment = create_transcript_segment_base()
        assert isinstance(segment, TranscriptSegmentBase)
        assert segment.video_id == "dQw4w9WgXcQ"
        assert segment.language_code == "en"
        assert len(segment.text) > 0
        assert segment.start_time >= 0.0
        assert segment.duration >= 0.0
        assert segment.end_time == segment.start_time + segment.duration
        assert segment.sequence_number >= 0

    def test_create_factory_creates_valid_segment(self):
        """Test that create factory creates valid segment."""
        segment = create_transcript_segment_create(
            video_id="dQw4w9WgXcQ", language_code="es", text="Hola mundo"
        )
        assert isinstance(segment, TranscriptSegmentCreate)
        assert segment.video_id == "dQw4w9WgXcQ"
        assert segment.language_code == "es"
        assert segment.text == "Hola mundo"

    def test_full_factory_creates_valid_segment(self):
        """Test that full factory creates valid segment with DB fields."""
        segment = create_transcript_segment()
        assert isinstance(segment, TranscriptSegment)
        assert segment.id >= 1
        assert segment.has_correction in [True, False]
        assert segment.created_at is not None

    def test_corrected_segment_factory(self):
        """Test factory for corrected segments."""
        segment = create_corrected_transcript_segment()
        assert segment.has_correction is True
        assert segment.corrected_text is not None
        assert segment.display_text == segment.corrected_text

    def test_batch_creation(self):
        """Test batch segment creation with sequential timing."""
        segments = create_batch_transcript_segments(
            video_id="dQw4w9WgXcQ", language_code="fr", count=3
        )
        assert len(segments) == 3
        assert all(s.video_id == "dQw4w9WgXcQ" for s in segments)
        assert all(s.language_code == "fr" for s in segments)
        # Verify sequential ordering
        for i, segment in enumerate(segments):
            assert segment.sequence_number == i
            if i > 0:
                # Each segment starts after previous one ends
                assert segment.start_time == segments[i - 1].end_time


# =============================================================================
# Validation Edge Cases
# =============================================================================


class TestValidationEdgeCases:
    """Test edge cases and validation scenarios."""

    @pytest.mark.parametrize("video_id", TranscriptSegmentTestData.VALID_VIDEO_IDS)
    def test_valid_video_ids(self, video_id):
        """Test various valid video IDs."""
        segment = create_transcript_segment_base(video_id=video_id)
        assert segment.video_id == video_id

    @pytest.mark.parametrize("video_id", TranscriptSegmentTestData.INVALID_VIDEO_IDS)
    def test_invalid_video_ids(self, video_id):
        """Test various invalid video IDs."""
        with pytest.raises(ValidationError):
            create_transcript_segment_base(video_id=video_id)

    @pytest.mark.parametrize(
        "language_code", TranscriptSegmentTestData.VALID_LANGUAGE_CODES
    )
    def test_valid_language_codes(self, language_code):
        """Test various valid language codes."""
        segment = create_transcript_segment_base(language_code=language_code)
        assert segment.language_code == language_code  # No normalization in this model

    @pytest.mark.parametrize(
        "language_code", TranscriptSegmentTestData.INVALID_LANGUAGE_CODES
    )
    def test_invalid_language_codes(self, language_code):
        """Test various invalid language codes."""
        with pytest.raises(ValidationError):
            create_transcript_segment_base(language_code=language_code)

    @pytest.mark.parametrize("text", TranscriptSegmentTestData.VALID_TEXTS)
    def test_valid_texts(self, text):
        """Test various valid text values."""
        segment = create_transcript_segment_base(text=text)
        assert segment.text == text.strip()

    def test_model_dump(self):
        """Test model_dump functionality."""
        segment = create_transcript_segment_base(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Test text",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
        )
        data = segment.model_dump()
        assert isinstance(data, dict)
        assert data["video_id"] == "dQw4w9WgXcQ"
        assert data["language_code"] == "en"
        assert data["text"] == "Test text"
        assert data["start_time"] == 0.0
        assert data["duration"] == 2.5
        assert data["end_time"] == 2.5
        assert data["sequence_number"] == 0

    def test_model_validate(self):
        """Test model_validate functionality."""
        data = TranscriptSegmentTestData.valid_segment_data()
        segment = TranscriptSegmentBase.model_validate(data)
        assert segment.video_id == data["video_id"]
        assert segment.language_code == data["language_code"]
        assert segment.text == data["text"]

    def test_end_time_tolerance(self):
        """Test that end_time validation has float tolerance."""
        # Should pass with tiny floating point difference
        segment = TranscriptSegmentBase(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            text="Hello",
            start_time=0.0,
            duration=2.5,
            end_time=2.5000001,  # Tiny difference
            sequence_number=0,
        )
        assert segment.end_time == 2.5000001

    def test_snippet_conversion_edge_cases(self):
        """Test from_snippet with various edge cases."""
        # Test sample snippets from test data
        for i, snippet in enumerate(TranscriptSegmentTestData.SAMPLE_SNIPPETS):
            # Type annotations for mypy
            snippet_dict = cast(Dict[str, Any], snippet)
            segment = TranscriptSegmentCreate.from_snippet(
                video_id="dQw4w9WgXcQ",
                language_code="en",
                snippet=snippet_dict,
                sequence_number=i,
            )
            text_val = cast(str, snippet_dict["text"])
            start_val = cast(float, snippet_dict["start"])
            duration_val = cast(float, snippet_dict["duration"])

            assert segment.text == text_val
            assert segment.start_time == start_val
            assert segment.duration == duration_val
            assert segment.end_time == start_val + duration_val
            assert segment.sequence_number == i

    def test_from_attributes_config(self):
        """Test from_attributes config for ORM compatibility."""
        # Create segment data as if from ORM
        data = TranscriptSegmentTestData.valid_full_segment_data()
        segment = TranscriptSegment.model_validate(data)
        assert segment.id == data["id"]
        assert segment.has_correction == data["has_correction"]
        assert segment.created_at == data["created_at"]

    def test_whitespace_stripping(self):
        """Test that text whitespace is stripped."""
        segment = create_transcript_segment_base(text="  Hello world  ")
        assert segment.text == "Hello world"

    def test_language_code_case_preservation(self):
        """Test that language codes preserve case (no automatic lowercasing)."""
        segment = create_transcript_segment_base(language_code="EN-US")
        assert segment.language_code == "EN-US"  # Case is preserved
