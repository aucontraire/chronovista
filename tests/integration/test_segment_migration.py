"""
Integration tests for segment data migration.

Tests the backfill process that extracts segments from raw_transcript_data JSONB.
These tests validate FR-MIG-01 through FR-MIG-19 requirements for data migration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.youtube_types import VideoId

pytestmark = pytest.mark.asyncio


async def create_test_video(
    session: AsyncSession,
    video_id: str,
) -> VideoDB:
    """Helper function to create a test video for transcript foreign key."""
    video = VideoDB(
        video_id=video_id,
        title="Test Video",
        upload_date=datetime.now(timezone.utc),
        duration=300,
    )
    session.add(video)
    await session.flush()
    return video


# Helper function to simulate backfill logic
async def backfill_single_transcript(
    session: AsyncSession,
    video_id: str,
    language_code: str,
) -> tuple[int, int]:
    """
    Backfill segments for a single transcript.

    Returns (segment_count, skipped_count).
    This simulates the logic from the migration script.
    """
    # Get transcript
    stmt = select(VideoTranscriptDB).where(
        VideoTranscriptDB.video_id == video_id,
        VideoTranscriptDB.language_code == language_code,
    )
    result = await session.execute(stmt)
    transcript = result.scalar_one_or_none()

    if not transcript or not transcript.raw_transcript_data:
        return (0, 0)

    # Delete existing segments (idempotent)
    await session.execute(
        text("""
            DELETE FROM transcript_segments
            WHERE video_id = :video_id AND language_code = :language_code
        """),
        {"video_id": video_id, "language_code": language_code},
    )

    # Extract snippets
    raw_data = transcript.raw_transcript_data
    snippets = raw_data.get("snippets", [])

    if not isinstance(snippets, list):
        return (0, 1)

    if not snippets:
        # Update segment_count to 0
        await session.execute(
            text("""
                UPDATE video_transcripts
                SET segment_count = 0
                WHERE video_id = :video_id AND language_code = :language_code
            """),
            {"video_id": video_id, "language_code": language_code},
        )
        await session.commit()
        return (0, 0)

    # Create segments
    segment_count = 0
    skipped_count = 0

    for seq, snippet in enumerate(snippets):
        try:
            text_content = snippet.get("text")
            start = snippet.get("start")
            duration = snippet.get("duration")

            if text_content is None or start is None or duration is None:
                skipped_count += 1
                continue

            start_time = float(start)
            duration_val = float(duration)
            end_time = start_time + duration_val

            await session.execute(
                text("""
                    INSERT INTO transcript_segments
                    (video_id, language_code, text, start_time, duration, end_time, sequence_number, has_correction)
                    VALUES (:video_id, :language_code, :text, :start_time, :duration, :end_time, :seq, FALSE)
                """),
                {
                    "video_id": video_id,
                    "language_code": language_code,
                    "text": text_content,
                    "start_time": start_time,
                    "duration": duration_val,
                    "end_time": end_time,
                    "seq": seq,
                },
            )
            segment_count += 1

        except (TypeError, ValueError):
            skipped_count += 1
            continue

    # Update segment_count
    await session.execute(
        text("""
            UPDATE video_transcripts
            SET segment_count = :count
            WHERE video_id = :video_id AND language_code = :language_code
        """),
        {
            "count": segment_count,
            "video_id": video_id,
            "language_code": language_code,
        },
    )

    await session.commit()
    return (segment_count, skipped_count)


class TestSegmentMigration:
    """Tests for segment backfill migration."""

    async def test_backfill_creates_segments_from_valid_jsonb(
        self, db_session: AsyncSession
    ) -> None:
        """Test that valid raw_transcript_data creates segments.

        Validates FR-MIG-02 (delete before insert) and FR-MIG-03 (commit per transcript).
        """
        video_id = "test_video_1"
        language_code = "en"

        # Create video first (required for foreign key)
        await create_test_video(db_session, video_id)

        # Create transcript with valid raw_transcript_data
        raw_data: Dict[str, Any] = {
            "snippets": [
                {"text": "Hello world", "start": 0.0, "duration": 2.5},
                {"text": "This is a test", "start": 2.5, "duration": 3.0},
                {"text": "Goodbye", "start": 5.5, "duration": 1.5},
            ]
        }

        transcript = VideoTranscriptDB(
            video_id=video_id,
            language_code=language_code,
            transcript_text="Hello world This is a test Goodbye",
            transcript_type="MANUAL",
            download_reason="USER_REQUEST",
            raw_transcript_data=raw_data,
            has_timestamps=True,
            source="youtube_transcript_api",
        )
        db_session.add(transcript)
        await db_session.commit()

        # Run backfill
        segment_count, skipped_count = await backfill_single_transcript(
            db_session, video_id, language_code
        )

        # Verify segments created with correct data
        assert segment_count == 3
        assert skipped_count == 0

        stmt = (
            select(TranscriptSegmentDB)
            .where(
                TranscriptSegmentDB.video_id == video_id,
                TranscriptSegmentDB.language_code == language_code,
            )
            .order_by(TranscriptSegmentDB.sequence_number)
        )
        result = await db_session.execute(stmt)
        segments = result.scalars().all()

        assert len(segments) == 3
        assert segments[0].text == "Hello world"
        assert segments[0].start_time == 0.0
        assert segments[0].duration == 2.5
        assert segments[0].end_time == 2.5
        assert segments[0].sequence_number == 0

        assert segments[1].text == "This is a test"
        assert segments[1].start_time == 2.5
        assert segments[1].end_time == 5.5

        assert segments[2].text == "Goodbye"
        assert segments[2].start_time == 5.5
        assert segments[2].end_time == 7.0

        # Verify segment_count updated
        db_session.expire_all()  # Expire cached objects to force fresh query
        transcript_stmt = select(VideoTranscriptDB).where(
            VideoTranscriptDB.video_id == video_id,
            VideoTranscriptDB.language_code == language_code,
        )
        transcript_result = await db_session.execute(transcript_stmt)
        updated_transcript = transcript_result.scalar_one()
        assert updated_transcript.segment_count == 3

    async def test_backfill_skips_transcript_without_raw_data(
        self, db_session: AsyncSession
    ) -> None:
        """Test that transcripts without raw_transcript_data are skipped.

        Validates FR-MIG-06 (skip transcripts without raw_data).
        """
        video_id = "test_video_2"
        language_code = "en"

        # Create video first
        await create_test_video(db_session, video_id)

        # Create transcript with raw_transcript_data = None
        transcript = VideoTranscriptDB(
            video_id=video_id,
            language_code=language_code,
            transcript_text="Some text",
            transcript_type="MANUAL",
            download_reason="USER_REQUEST",
            raw_transcript_data=None,
            has_timestamps=False,
            source="manual_upload",
        )
        db_session.add(transcript)
        await db_session.commit()

        # Run backfill - should not fail
        segment_count, skipped_count = await backfill_single_transcript(
            db_session, video_id, language_code
        )

        # Verify no segments created
        assert segment_count == 0
        assert skipped_count == 0

        stmt = select(TranscriptSegmentDB).where(
            TranscriptSegmentDB.video_id == video_id,
            TranscriptSegmentDB.language_code == language_code,
        )
        result = await db_session.execute(stmt)
        segments = result.scalars().all()
        assert len(segments) == 0

    async def test_backfill_handles_empty_snippets_array(
        self, db_session: AsyncSession
    ) -> None:
        """Test that empty snippets array is handled gracefully.

        Validates FR-MIG-06 (handle empty arrays) and correct segment_count = 0.
        """
        video_id = "test_video_3"
        language_code = "en"

        # Create video first
        await create_test_video(db_session, video_id)

        # Create transcript with raw_transcript_data = {"snippets": []}
        raw_data: Dict[str, Any] = {"snippets": []}

        transcript = VideoTranscriptDB(
            video_id=video_id,
            language_code=language_code,
            transcript_text="",
            transcript_type="MANUAL",
            download_reason="USER_REQUEST",
            raw_transcript_data=raw_data,
            has_timestamps=True,
            source="youtube_transcript_api",
        )
        db_session.add(transcript)
        await db_session.commit()

        # Run backfill
        segment_count, skipped_count = await backfill_single_transcript(
            db_session, video_id, language_code
        )

        # Verify segment_count = 0
        assert segment_count == 0
        assert skipped_count == 0

        # Verify transcript.segment_count is updated
        db_session.expire_all()  # Expire cached objects to force fresh query
        stmt = select(VideoTranscriptDB).where(
            VideoTranscriptDB.video_id == video_id,
            VideoTranscriptDB.language_code == language_code,
        )
        result = await db_session.execute(stmt)
        transcript = result.scalar_one()
        assert transcript.segment_count == 0

    async def test_backfill_skips_malformed_snippet(
        self, db_session: AsyncSession
    ) -> None:
        """Test that malformed snippets are skipped but migration continues.

        Validates FR-MIG-15 through FR-MIG-19 (malformed data handling).
        """
        video_id = "test_video_4"
        language_code = "en"

        # Create video first
        await create_test_video(db_session, video_id)

        # Create transcript with one valid and one invalid snippet
        raw_data: Dict[str, Any] = {
            "snippets": [
                {"text": "Valid segment", "start": 0.0, "duration": 2.0},
                {"text": "Missing start"},  # Missing start and duration
                {"text": "Another valid", "start": 5.0, "duration": 2.0},
                {"start": 10.0, "duration": 1.0},  # Missing text
            ]
        }

        transcript = VideoTranscriptDB(
            video_id=video_id,
            language_code=language_code,
            transcript_text="Valid segment Another valid",
            transcript_type="MANUAL",
            download_reason="USER_REQUEST",
            raw_transcript_data=raw_data,
            has_timestamps=True,
            source="youtube_transcript_api",
        )
        db_session.add(transcript)
        await db_session.commit()

        # Run backfill
        segment_count, skipped_count = await backfill_single_transcript(
            db_session, video_id, language_code
        )

        # Verify valid segments created, malformed skipped
        assert segment_count == 2
        assert skipped_count == 2

        stmt = (
            select(TranscriptSegmentDB)
            .where(
                TranscriptSegmentDB.video_id == video_id,
                TranscriptSegmentDB.language_code == language_code,
            )
            .order_by(TranscriptSegmentDB.sequence_number)
        )
        result = await db_session.execute(stmt)
        segments = result.scalars().all()

        assert len(segments) == 2
        assert segments[0].text == "Valid segment"
        assert segments[0].sequence_number == 0
        assert segments[1].text == "Another valid"
        assert segments[1].sequence_number == 2  # Preserves original sequence

    async def test_backfill_is_idempotent(self, db_session: AsyncSession) -> None:
        """Test that running backfill twice produces same result.

        Validates FR-MIG-01 (idempotent migration) and FR-MIG-02 (delete before insert).
        """
        video_id = "test_video_5"
        language_code = "en"

        # Create video first
        await create_test_video(db_session, video_id)

        # Create transcript
        raw_data: Dict[str, Any] = {
            "snippets": [
                {"text": "Segment 1", "start": 0.0, "duration": 2.0},
                {"text": "Segment 2", "start": 2.0, "duration": 2.0},
            ]
        }

        transcript = VideoTranscriptDB(
            video_id=video_id,
            language_code=language_code,
            transcript_text="Segment 1 Segment 2",
            transcript_type="MANUAL",
            download_reason="USER_REQUEST",
            raw_transcript_data=raw_data,
            has_timestamps=True,
            source="youtube_transcript_api",
        )
        db_session.add(transcript)
        await db_session.commit()

        # Run backfill first time
        segment_count_1, _ = await backfill_single_transcript(
            db_session, video_id, language_code
        )
        assert segment_count_1 == 2

        stmt = select(TranscriptSegmentDB).where(
            TranscriptSegmentDB.video_id == video_id,
            TranscriptSegmentDB.language_code == language_code,
        )
        result = await db_session.execute(stmt)
        segments_1 = result.scalars().all()
        segment_ids_1 = {seg.id for seg in segments_1}

        # Run backfill second time
        segment_count_2, _ = await backfill_single_transcript(
            db_session, video_id, language_code
        )
        assert segment_count_2 == 2

        result = await db_session.execute(stmt)
        segments_2 = result.scalars().all()
        segment_ids_2 = {seg.id for seg in segments_2}

        # Verify same number of segments, but different IDs (deleted and recreated)
        assert len(segments_1) == len(segments_2) == 2
        # IDs should be different because segments were deleted and recreated
        assert segment_ids_1 != segment_ids_2

        # Verify data is identical
        assert segments_2[0].text == "Segment 1"
        assert segments_2[1].text == "Segment 2"

    async def test_backfill_updates_segment_count(
        self, db_session: AsyncSession
    ) -> None:
        """Test that segment_count is updated on transcript after backfill.

        Validates that transcript.segment_count field is properly maintained.
        """
        video_id = "test_video_6"
        language_code = "en"

        # Create video first
        await create_test_video(db_session, video_id)

        # Create transcript with raw_transcript_data containing 5 snippets
        raw_data: Dict[str, Any] = {
            "snippets": [
                {"text": f"Segment {i}", "start": float(i * 2), "duration": 2.0}
                for i in range(5)
            ]
        }

        transcript = VideoTranscriptDB(
            video_id=video_id,
            language_code=language_code,
            transcript_text=" ".join(f"Segment {i}" for i in range(5)),
            transcript_type="MANUAL",
            download_reason="USER_REQUEST",
            raw_transcript_data=raw_data,
            has_timestamps=True,
            source="youtube_transcript_api",
        )
        db_session.add(transcript)
        await db_session.commit()

        # Run backfill
        segment_count, _ = await backfill_single_transcript(
            db_session, video_id, language_code
        )

        # Verify segment_count == 5
        assert segment_count == 5

        db_session.expire_all()  # Expire cached objects to force fresh query
        stmt = select(VideoTranscriptDB).where(
            VideoTranscriptDB.video_id == video_id,
            VideoTranscriptDB.language_code == language_code,
        )
        result = await db_session.execute(stmt)
        transcript = result.scalar_one()
        assert transcript.segment_count == 5

    async def test_backfill_handles_non_list_snippets(
        self, db_session: AsyncSession
    ) -> None:
        """Test that non-list snippets value is skipped gracefully.

        Validates FR-MIG-15 (malformed data handling).
        """
        video_id = "test_video_7"
        language_code = "en"

        # Create video first
        await create_test_video(db_session, video_id)

        # Create transcript with snippets as a dict instead of list
        raw_data: Dict[str, Any] = {"snippets": {"invalid": "not a list"}}

        transcript = VideoTranscriptDB(
            video_id=video_id,
            language_code=language_code,
            transcript_text="Some text",
            transcript_type="MANUAL",
            download_reason="USER_REQUEST",
            raw_transcript_data=raw_data,
            has_timestamps=True,
            source="youtube_transcript_api",
        )
        db_session.add(transcript)
        await db_session.commit()

        # Run backfill - should skip gracefully
        segment_count, skipped_count = await backfill_single_transcript(
            db_session, video_id, language_code
        )

        # Should be skipped entirely
        assert segment_count == 0
        assert skipped_count == 1

        stmt = select(TranscriptSegmentDB).where(
            TranscriptSegmentDB.video_id == video_id,
            TranscriptSegmentDB.language_code == language_code,
        )
        result = await db_session.execute(stmt)
        segments = result.scalars().all()
        assert len(segments) == 0

    async def test_backfill_handles_type_conversion_errors(
        self, db_session: AsyncSession
    ) -> None:
        """Test that invalid numeric values are skipped.

        Validates FR-MIG-17 (skip invalid numeric types).
        """
        video_id = "test_video_8"
        language_code = "en"

        # Create video first
        await create_test_video(db_session, video_id)

        # Create transcript with invalid numeric values
        raw_data: Dict[str, Any] = {
            "snippets": [
                {"text": "Valid", "start": 0.0, "duration": 2.0},
                {"text": "Invalid start", "start": "not a number", "duration": 2.0},
                {"text": "Invalid duration", "start": 5.0, "duration": "bad"},
                {"text": "Also valid", "start": 10.0, "duration": 2.0},
            ]
        }

        transcript = VideoTranscriptDB(
            video_id=video_id,
            language_code=language_code,
            transcript_text="Valid Also valid",
            transcript_type="MANUAL",
            download_reason="USER_REQUEST",
            raw_transcript_data=raw_data,
            has_timestamps=True,
            source="youtube_transcript_api",
        )
        db_session.add(transcript)
        await db_session.commit()

        # Run backfill
        segment_count, skipped_count = await backfill_single_transcript(
            db_session, video_id, language_code
        )

        # Only valid segments should be created
        assert segment_count == 2
        assert skipped_count == 2

        stmt = (
            select(TranscriptSegmentDB)
            .where(
                TranscriptSegmentDB.video_id == video_id,
                TranscriptSegmentDB.language_code == language_code,
            )
            .order_by(TranscriptSegmentDB.sequence_number)
        )
        result = await db_session.execute(stmt)
        segments = result.scalars().all()

        assert len(segments) == 2
        assert segments[0].text == "Valid"
        assert segments[1].text == "Also valid"
