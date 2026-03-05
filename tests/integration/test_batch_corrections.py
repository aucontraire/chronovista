"""
Integration tests for BatchCorrectionService (Feature 036).

Uses a real PostgreSQL test database (via the ``db_session`` fixture from
``tests/integration/conftest.py``) to verify the full end-to-end flow of
batch correction operations:

  find_and_replace, batch_revert, export_corrections, rebuild_text,
  get_statistics, and get_patterns

Database URL defaults to:
  postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test

Override with DATABASE_INTEGRATION_URL or CHRONOVISTA_INTEGRATION_DB_URL env var.

Tests in this module validate:
  - T029: Integration scenario validation (workflows, dry-run, idempotency)
  - T030: Cross-feature data contract verification (API schema, frontend,
    rebuild text format, actor string format)

Feature 036 -- Batch Correction Tools
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.batch_correction_models import BatchCorrectionResult
from chronovista.models.correction_actors import ACTOR_CLI_BATCH
from chronovista.models.enums import CorrectionType
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)
from chronovista.services.batch_correction_service import BatchCorrectionService
from chronovista.services.transcript_correction_service import (
    TranscriptCorrectionService,
)

# ---------------------------------------------------------------------------
# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# DB seed helpers
# ---------------------------------------------------------------------------


async def _seed_video(session: AsyncSession, video_id: str = "dQw4w9WgXcQ") -> VideoDB:
    """Insert a minimal Video row to satisfy FK constraints."""
    video = VideoDB(
        video_id=video_id,
        title="Integration Test Video",
        upload_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        duration=300,
    )
    session.add(video)
    await session.flush()
    return video


async def _seed_transcript(
    session: AsyncSession,
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    transcript_text: str = "placeholder transcript text",
    has_corrections: bool = False,
) -> VideoTranscriptDB:
    """Insert a VideoTranscript row with correction metadata defaults."""
    transcript = VideoTranscriptDB(
        video_id=video_id,
        language_code=language_code,
        transcript_text=transcript_text,
        transcript_type="manual",
        download_reason="user_request",
        is_cc=False,
        is_auto_synced=False,
        track_kind="standard",
        source="youtube_transcript_api",
        has_corrections=has_corrections,
        correction_count=0,
        last_corrected_at=None,
    )
    session.add(transcript)
    await session.flush()
    return transcript


async def _seed_segment(
    session: AsyncSession,
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    text: str = "some segment text",
    sequence_number: int = 0,
    start_time: float = 0.0,
    duration: float = 2.5,
    corrected_text: str | None = None,
    has_correction: bool = False,
) -> TranscriptSegmentDB:
    """Insert a TranscriptSegment row linked to the given transcript."""
    segment = TranscriptSegmentDB(
        video_id=video_id,
        language_code=language_code,
        text=text,
        start_time=start_time,
        duration=duration,
        end_time=start_time + duration,
        sequence_number=sequence_number,
        corrected_text=corrected_text,
        has_correction=has_correction,
    )
    session.add(segment)
    await session.flush()
    return segment


# ---------------------------------------------------------------------------
# T029: Integration Scenario Validation
# ---------------------------------------------------------------------------


class TestBatchCorrectionIntegration:
    """
    End-to-end integration tests for BatchCorrectionService using a real
    PostgreSQL test database.

    Each test uses ``db_session`` from ``tests/integration/conftest.py`` which
    creates all tables, yields the session, then rolls back and drops all tables
    for full isolation between tests.
    """

    @pytest.fixture
    def correction_repo(self) -> TranscriptCorrectionRepository:
        return TranscriptCorrectionRepository()

    @pytest.fixture
    def segment_repo(self) -> TranscriptSegmentRepository:
        return TranscriptSegmentRepository()

    @pytest.fixture
    def transcript_repo(self) -> VideoTranscriptRepository:
        return VideoTranscriptRepository()

    @pytest.fixture
    def correction_service(
        self,
        correction_repo: TranscriptCorrectionRepository,
        segment_repo: TranscriptSegmentRepository,
        transcript_repo: VideoTranscriptRepository,
    ) -> TranscriptCorrectionService:
        return TranscriptCorrectionService(
            correction_repo=correction_repo,
            segment_repo=segment_repo,
            transcript_repo=transcript_repo,
        )

    @pytest.fixture
    def batch_service(
        self,
        correction_service: TranscriptCorrectionService,
        segment_repo: TranscriptSegmentRepository,
        correction_repo: TranscriptCorrectionRepository,
    ) -> BatchCorrectionService:
        return BatchCorrectionService(
            correction_service=correction_service,
            segment_repo=segment_repo,
            correction_repo=correction_repo,
        )

    # ------------------------------------------------------------------
    # 1. Find-replace workflow
    # ------------------------------------------------------------------

    async def test_find_and_replace_workflow(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
    ) -> None:
        """
        Create segments with a known pattern, run find_and_replace in live
        mode, and verify corrections are applied to matching segments.
        """
        video_id = "batchFR0001"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )

        # Seed three segments: two with the pattern, one without
        seg_a = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
            start_time=0.0,
        )
        seg_b = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh lazy dog",
            sequence_number=1,
            start_time=3.0,
        )
        _seg_c = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="no match here",
            sequence_number=2,
            start_time=6.0,
        )

        result = await batch_service.find_and_replace(
            db_session,
            pattern="teh",
            replacement="the",
            video_ids=[video_id],
        )

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_matched == 2, (
            f"Expected 2 matched segments, got {result.total_matched}"
        )
        assert result.total_applied == 2, (
            f"Expected 2 applied corrections, got {result.total_applied}"
        )
        assert result.total_skipped == 0
        assert result.total_failed == 0
        assert result.unique_videos == 1

        # Verify segment state in DB
        seg_a_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == seg_a.id)
        )
        persisted_seg_a = seg_a_result.scalar_one()
        assert persisted_seg_a.has_correction is True
        assert persisted_seg_a.corrected_text == "the quick brown fox"

        seg_b_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == seg_b.id)
        )
        persisted_seg_b = seg_b_result.scalar_one()
        assert persisted_seg_b.has_correction is True
        assert persisted_seg_b.corrected_text == "the lazy dog"

    # ------------------------------------------------------------------
    # 2. Dry-run safety
    # ------------------------------------------------------------------

    async def test_dry_run_produces_no_mutations(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
    ) -> None:
        """
        Run find_and_replace with dry_run=True and verify no mutations
        are applied to segments or the corrections table.
        """
        video_id = "batchDRY001"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )

        seg = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
        )

        previews = await batch_service.find_and_replace(
            db_session,
            pattern="teh",
            replacement="the",
            video_ids=[video_id],
            dry_run=True,
        )

        # Dry-run returns a list of preview tuples
        assert isinstance(previews, list)
        assert len(previews) == 1
        # Preview tuple: (video_id, segment_id, start_time, current_text, proposed_text)
        assert previews[0][0] == video_id
        assert previews[0][3] == "teh quick brown fox"
        assert previews[0][4] == "the quick brown fox"

        # Verify no mutations in DB
        seg_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == seg.id)
        )
        persisted_seg = seg_result.scalar_one()
        assert persisted_seg.has_correction is False, (
            "Dry-run must not modify segment.has_correction"
        )
        assert persisted_seg.corrected_text is None, (
            "Dry-run must not modify segment.corrected_text"
        )

        # Verify no correction audit records created
        corrections_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.video_id == video_id,
            )
        )
        corrections = list(corrections_result.scalars().all())
        assert len(corrections) == 0, (
            "Dry-run must not create any audit records"
        )

    # ------------------------------------------------------------------
    # 3. Idempotency (NFR-005)
    # ------------------------------------------------------------------

    async def test_find_and_replace_idempotency(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
    ) -> None:
        """
        NFR-005: Run find_and_replace twice with the same pattern/replacement.
        The second run must report 0 applied because the corrected_text
        already contains the replacement.
        """
        video_id = "batchIdem01"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )
        await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
        )

        # First run: should apply the correction
        result_1 = await batch_service.find_and_replace(
            db_session,
            pattern="teh",
            replacement="the",
            video_ids=[video_id],
        )
        assert isinstance(result_1, BatchCorrectionResult)
        assert result_1.total_applied == 1

        # Second run: same pattern/replacement -- segment already corrected
        # The pattern "teh" no longer appears in the effective text
        # (corrected_text = "the quick brown fox"), so total_matched = 0
        result_2 = await batch_service.find_and_replace(
            db_session,
            pattern="teh",
            replacement="the",
            video_ids=[video_id],
        )
        assert isinstance(result_2, BatchCorrectionResult)
        assert result_2.total_applied == 0, (
            "NFR-005: Second run with same pattern/replacement must apply 0 "
            f"corrections, got {result_2.total_applied}"
        )

    # ------------------------------------------------------------------
    # 4. Batch revert workflow
    # ------------------------------------------------------------------

    async def test_batch_revert_workflow(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
    ) -> None:
        """
        Apply corrections via find_and_replace, then batch_revert matching
        the replacement pattern, and verify segments are reverted.
        """
        video_id = "batchRev001"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )

        seg_a = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
            start_time=0.0,
        )
        seg_b = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh lazy dog",
            sequence_number=1,
            start_time=3.0,
        )

        # Step 1: Apply corrections
        apply_result = await batch_service.find_and_replace(
            db_session,
            pattern="teh",
            replacement="the",
            video_ids=[video_id],
        )
        assert isinstance(apply_result, BatchCorrectionResult)
        assert apply_result.total_applied == 2

        # Step 2: Batch revert -- match on "the" in corrected text
        revert_result = await batch_service.batch_revert(
            db_session,
            pattern="the",
            video_ids=[video_id],
        )
        assert isinstance(revert_result, BatchCorrectionResult)
        assert revert_result.total_applied == 2, (
            f"Expected 2 reverted segments, got {revert_result.total_applied}"
        )

        # Verify segments are reverted (has_correction=False for single-correction revert)
        seg_a_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == seg_a.id)
        )
        persisted_a = seg_a_result.scalar_one()
        assert persisted_a.has_correction is False, (
            "After batch revert of single correction, segment must be fully reverted"
        )
        assert persisted_a.corrected_text is None

        seg_b_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == seg_b.id)
        )
        persisted_b = seg_b_result.scalar_one()
        assert persisted_b.has_correction is False
        assert persisted_b.corrected_text is None

    # ------------------------------------------------------------------
    # 5. Export round-trip (CSV)
    # ------------------------------------------------------------------

    async def test_export_csv_round_trip(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
        correction_service: TranscriptCorrectionService,
    ) -> None:
        """
        Create corrections via apply_correction, export as CSV, and verify
        the column count and content.
        """
        video_id = "batchExp001"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )
        seg = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
        )

        await correction_service.apply_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg.id,
            corrected_text="the quick brown fox",
            correction_type=CorrectionType.SPELLING,
            correction_note="Fixed typo",
            corrected_by_user_id=ACTOR_CLI_BATCH,
        )
        await db_session.flush()

        count, csv_string = await batch_service.export_corrections(
            db_session,
            video_ids=[video_id],
            format="csv",
        )

        assert count == 1, f"Expected 1 record, got {count}"

        # Parse CSV and verify structure
        reader = csv.DictReader(io.StringIO(csv_string))
        rows = list(reader)
        assert len(rows) == 1

        expected_columns = {
            "id", "video_id", "language_code", "segment_id",
            "correction_type", "original_text", "corrected_text",
            "correction_note", "corrected_by_user_id", "corrected_at",
            "version_number",
        }
        assert reader.fieldnames is not None
        assert set(reader.fieldnames) == expected_columns, (
            f"CSV columns mismatch: {set(reader.fieldnames)} != {expected_columns}"
        )

        row = rows[0]
        assert row["video_id"] == video_id
        assert row["original_text"] == "teh quick brown fox"
        assert row["corrected_text"] == "the quick brown fox"
        assert row["correction_note"] == "Fixed typo"
        assert row["corrected_by_user_id"] == ACTOR_CLI_BATCH

    # ------------------------------------------------------------------
    # 6. Export JSON
    # ------------------------------------------------------------------

    async def test_export_json(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
        correction_service: TranscriptCorrectionService,
    ) -> None:
        """
        Create corrections, export as JSON, and verify it is valid JSON
        with the correct fields.
        """
        video_id = "batchJSON01"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )
        seg = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh lazy dog",
            sequence_number=0,
        )

        await correction_service.apply_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg.id,
            corrected_text="the lazy dog",
            correction_type=CorrectionType.ASR_ERROR,
            corrected_by_user_id=ACTOR_CLI_BATCH,
        )
        await db_session.flush()

        count, json_string = await batch_service.export_corrections(
            db_session,
            video_ids=[video_id],
            format="json",
        )

        assert count == 1
        data = json.loads(json_string)
        assert isinstance(data, list)
        assert len(data) == 1

        record = data[0]
        expected_keys = {
            "id", "video_id", "language_code", "segment_id",
            "correction_type", "original_text", "corrected_text",
            "correction_note", "corrected_by_user_id", "corrected_at",
            "version_number",
        }
        assert set(record.keys()) == expected_keys, (
            f"JSON keys mismatch: {set(record.keys())} != {expected_keys}"
        )
        assert record["video_id"] == video_id
        assert record["corrected_text"] == "the lazy dog"
        assert record["version_number"] == 1

    # ------------------------------------------------------------------
    # 7. Statistics
    # ------------------------------------------------------------------

    async def test_statistics(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
        correction_service: TranscriptCorrectionService,
    ) -> None:
        """
        Create mixed corrections (different types + a revert), then verify
        get_statistics returns correct aggregate counts.
        """
        video_id = "batchStat01"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )

        seg_a = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
            start_time=0.0,
        )
        seg_b = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="wrold peace",
            sequence_number=1,
            start_time=3.0,
        )

        # Apply two corrections of different types
        await correction_service.apply_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg_a.id,
            corrected_text="the quick brown fox",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        await correction_service.apply_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg_b.id,
            corrected_text="world peace",
            correction_type=CorrectionType.ASR_ERROR,
        )
        await db_session.flush()

        # Revert one correction
        await correction_service.revert_correction(
            db_session,
            segment_id=seg_a.id,
        )
        await db_session.flush()

        stats = await batch_service.get_statistics(db_session)

        # 2 non-revert corrections + 1 revert = 3 total records
        # total_corrections counts non-revert records
        assert stats.total_corrections >= 2, (
            f"Expected at least 2 non-revert corrections, got {stats.total_corrections}"
        )
        assert stats.total_reverts >= 1, (
            f"Expected at least 1 revert, got {stats.total_reverts}"
        )
        assert stats.unique_videos >= 1
        assert stats.unique_segments >= 1

    # ------------------------------------------------------------------
    # 8. Patterns discovery
    # ------------------------------------------------------------------

    async def test_get_patterns(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
        correction_service: TranscriptCorrectionService,
    ) -> None:
        """
        Create repeated correction patterns and verify get_patterns returns
        them with correct occurrence counts.
        """
        video_id = "batchPat001"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )

        # Create two segments with the same original text pattern
        seg_a = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick",
            sequence_number=0,
            start_time=0.0,
        )
        seg_b = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick",
            sequence_number=1,
            start_time=3.0,
        )

        # Apply the same correction to both
        await correction_service.apply_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg_a.id,
            corrected_text="the quick",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        await correction_service.apply_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg_b.id,
            corrected_text="the quick",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        patterns = await batch_service.get_patterns(
            db_session,
            min_occurrences=2,
            show_completed=True,
        )

        assert len(patterns) >= 1, (
            f"Expected at least 1 pattern, got {len(patterns)}"
        )

        # Find our specific pattern
        matching = [
            p for p in patterns
            if p.original_text == "teh quick" and p.corrected_text == "the quick"
        ]
        assert len(matching) == 1, (
            f"Expected exactly 1 matching pattern, got {len(matching)}"
        )
        assert matching[0].occurrences == 2, (
            f"Expected 2 occurrences, got {matching[0].occurrences}"
        )

    # ------------------------------------------------------------------
    # 9. Rebuild text
    # ------------------------------------------------------------------

    async def test_rebuild_text(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
        correction_service: TranscriptCorrectionService,
    ) -> None:
        """
        Create a transcript with corrected segments, rebuild the transcript
        text, and verify it contains the corrected text concatenated in
        start_time order with space separators.
        """
        video_id = "batchRbld01"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session,
            video_id=video_id,
            language_code=language_code,
            transcript_text="original full text",
        )

        # Seed three segments in start_time order
        seg_a = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
            start_time=0.0,
        )
        seg_b = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="jumps over",
            sequence_number=1,
            start_time=3.0,
        )
        seg_c = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh lazy dog",
            sequence_number=2,
            start_time=6.0,
        )

        # Apply corrections to seg_a and seg_c (seg_b stays uncorrected)
        await correction_service.apply_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg_a.id,
            corrected_text="the quick brown fox",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        await correction_service.apply_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg_c.id,
            corrected_text="the lazy dog",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Rebuild the transcript text
        rebuilt, total_segments = await batch_service.rebuild_text(
            db_session,
            video_ids=[video_id],
        )

        assert rebuilt == 1, f"Expected 1 transcript rebuilt, got {rebuilt}"
        assert total_segments == 3, f"Expected 3 segments processed, got {total_segments}"

        # Verify the rebuilt transcript text
        transcript_result = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        transcript = transcript_result.scalar_one()

        expected_text = "the quick brown fox jumps over the lazy dog"
        assert transcript.transcript_text == expected_text, (
            f"Rebuilt transcript text mismatch:\n"
            f"Expected: {expected_text!r}\n"
            f"Got:      {transcript.transcript_text!r}"
        )


# ---------------------------------------------------------------------------
# T030: Cross-Feature Data Contract Verification
# ---------------------------------------------------------------------------


class TestCrossFeatureDataContract:
    """
    Cross-feature data contract verification tests ensuring that batch
    correction operations produce data compatible with:

    - Feature 034 (Correction Submission API)
    - Feature 035 (Frontend Inline Correction UI)
    - Rebuild-text output format
    - Actor string format constraints
    """

    @pytest.fixture
    def correction_repo(self) -> TranscriptCorrectionRepository:
        return TranscriptCorrectionRepository()

    @pytest.fixture
    def segment_repo(self) -> TranscriptSegmentRepository:
        return TranscriptSegmentRepository()

    @pytest.fixture
    def transcript_repo(self) -> VideoTranscriptRepository:
        return VideoTranscriptRepository()

    @pytest.fixture
    def correction_service(
        self,
        correction_repo: TranscriptCorrectionRepository,
        segment_repo: TranscriptSegmentRepository,
        transcript_repo: VideoTranscriptRepository,
    ) -> TranscriptCorrectionService:
        return TranscriptCorrectionService(
            correction_repo=correction_repo,
            segment_repo=segment_repo,
            transcript_repo=transcript_repo,
        )

    @pytest.fixture
    def batch_service(
        self,
        correction_service: TranscriptCorrectionService,
        segment_repo: TranscriptSegmentRepository,
        correction_repo: TranscriptCorrectionRepository,
    ) -> BatchCorrectionService:
        return BatchCorrectionService(
            correction_service=correction_service,
            segment_repo=segment_repo,
            correction_repo=correction_repo,
        )

    # ------------------------------------------------------------------
    # Contract 1: Batch correction schema matches API correction schema
    # ------------------------------------------------------------------

    async def test_batch_correction_schema_matches_api_correction_schema(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
    ) -> None:
        """
        Feature 034 contract: Corrections created by batch operations must
        have the same schema as API-created corrections -- same required
        fields populated, valid CorrectionType, valid corrected_by_user_id.
        """
        video_id = "contractAPI"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )
        await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
        )

        result = await batch_service.find_and_replace(
            db_session,
            pattern="teh",
            replacement="the",
            video_ids=[video_id],
            correction_type=CorrectionType.ASR_ERROR,
        )
        assert isinstance(result, BatchCorrectionResult)
        assert result.total_applied == 1

        # Retrieve the audit record created by the batch operation
        corrections_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.video_id == video_id,
            )
        )
        corrections = list(corrections_result.scalars().all())
        assert len(corrections) == 1

        correction = corrections[0]

        # Verify all required fields match the Feature 034 API schema
        assert correction.id is not None, "Correction must have a UUID id"
        assert correction.video_id == video_id
        assert correction.language_code == language_code
        assert correction.segment_id is not None, (
            "Correction must reference a segment_id"
        )
        assert correction.correction_type == CorrectionType.ASR_ERROR.value, (
            f"correction_type must be a valid CorrectionType value, "
            f"got {correction.correction_type!r}"
        )
        assert correction.original_text is not None, (
            "original_text must be populated"
        )
        assert correction.corrected_text is not None, (
            "corrected_text must be populated"
        )
        assert correction.corrected_by_user_id == ACTOR_CLI_BATCH, (
            f"corrected_by_user_id must be ACTOR_CLI_BATCH ('{ACTOR_CLI_BATCH}'), "
            f"got {correction.corrected_by_user_id!r}"
        )
        assert correction.corrected_at is not None, (
            "corrected_at timestamp must be set"
        )
        assert correction.version_number >= 1, (
            f"version_number must be >= 1, got {correction.version_number}"
        )

        # Verify correction_type is a valid CorrectionType enum value
        valid_types = {ct.value for ct in CorrectionType}
        assert correction.correction_type in valid_types, (
            f"correction_type {correction.correction_type!r} is not a valid "
            f"CorrectionType. Valid values: {valid_types}"
        )

    # ------------------------------------------------------------------
    # Contract 2: Batch-corrected segments visible to frontend
    # ------------------------------------------------------------------

    async def test_batch_corrected_segment_visible_to_frontend(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
    ) -> None:
        """
        Feature 035 contract: Segments updated by batch corrections must
        have has_correction=True and corrected_text set, which the frontend
        inline edit component reads via the API.
        """
        video_id = "contractFE1"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )
        seg = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
        )

        result = await batch_service.find_and_replace(
            db_session,
            pattern="teh",
            replacement="the",
            video_ids=[video_id],
        )
        assert isinstance(result, BatchCorrectionResult)
        assert result.total_applied == 1

        # Reload segment from DB (as the frontend API would)
        seg_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == seg.id)
        )
        persisted_seg = seg_result.scalar_one()

        # Frontend inline edit component checks these two fields
        assert persisted_seg.has_correction is True, (
            "Feature 035: segment.has_correction must be True after batch correction"
        )
        assert persisted_seg.corrected_text is not None, (
            "Feature 035: segment.corrected_text must be set after batch correction"
        )
        assert persisted_seg.corrected_text == "the quick brown fox", (
            f"Feature 035: segment.corrected_text must be the corrected text, "
            f"got {persisted_seg.corrected_text!r}"
        )

        # Verify the frontend's inline ternary logic works correctly
        # (from transcripts.py:303)
        display = (
            persisted_seg.corrected_text
            if persisted_seg.has_correction and persisted_seg.corrected_text
            else persisted_seg.text
        )
        assert display == "the quick brown fox", (
            f"Frontend inline ternary must return corrected text, got {display!r}"
        )

    # ------------------------------------------------------------------
    # Contract 3: Rebuilt text format
    # ------------------------------------------------------------------

    async def test_rebuilt_text_format(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
        correction_service: TranscriptCorrectionService,
    ) -> None:
        """
        Rebuild-text contract: The rebuilt transcript_text must be
        space-separated and ordered by start_time, matching the format
        used by the original transcript download (plain_text property).
        """
        video_id = "contractRbl"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session,
            video_id=video_id,
            language_code=language_code,
            transcript_text="old text",
        )

        # Seed segments in non-sequential order but with defined start_times
        await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="third segment",
            sequence_number=2,
            start_time=6.0,
        )
        seg_first = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="first segment original",
            sequence_number=0,
            start_time=0.0,
        )
        await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="second segment",
            sequence_number=1,
            start_time=3.0,
        )

        # Apply correction to the first segment (to trigger has_corrections)
        await correction_service.apply_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg_first.id,
            corrected_text="first segment corrected",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        rebuilt, _ = await batch_service.rebuild_text(
            db_session,
            video_ids=[video_id],
        )
        assert rebuilt == 1

        # Reload transcript
        transcript_result = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        transcript = transcript_result.scalar_one()

        # Verify space-separated format matching original transcript assembly
        expected = "first segment corrected second segment third segment"
        assert transcript.transcript_text == expected, (
            f"Rebuilt text must be space-separated in start_time order, "
            f"got {transcript.transcript_text!r}"
        )

    # ------------------------------------------------------------------
    # Contract 4: Actor string format
    # ------------------------------------------------------------------

    async def test_actor_string_format(
        self,
        db_session: AsyncSession,
        batch_service: BatchCorrectionService,
    ) -> None:
        """
        Actor string contract: Verify that ACTOR_CLI_BATCH ("cli:batch") is
        a valid value for the corrected_by_user_id column:

        1. Fits within String(100) column limit
        2. Matches the expected prefix:detail format
        3. Is actually persisted when batch corrections are applied
        """
        # Contract: ACTOR_CLI_BATCH format and length
        assert ACTOR_CLI_BATCH == "cli:batch", (
            f"ACTOR_CLI_BATCH must be 'cli:batch', got {ACTOR_CLI_BATCH!r}"
        )
        assert len(ACTOR_CLI_BATCH) <= 100, (
            f"ACTOR_CLI_BATCH must fit in String(100) column, "
            f"length={len(ACTOR_CLI_BATCH)}"
        )
        assert ":" in ACTOR_CLI_BATCH, (
            "ACTOR_CLI_BATCH must follow prefix:detail format"
        )
        prefix, detail = ACTOR_CLI_BATCH.split(":", 1)
        assert prefix == "cli", (
            f"Actor prefix must be 'cli', got {prefix!r}"
        )
        assert detail == "batch", (
            f"Actor detail must be 'batch', got {detail!r}"
        )

        # Verify the actor string is actually persisted in the DB
        video_id = "contractAct"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(
            db_session, video_id=video_id, language_code=language_code,
        )
        await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh lazy dog",
            sequence_number=0,
        )

        result = await batch_service.find_and_replace(
            db_session,
            pattern="teh",
            replacement="the",
            video_ids=[video_id],
        )
        assert isinstance(result, BatchCorrectionResult)
        assert result.total_applied == 1

        # Verify the actor string is persisted in the audit record
        corrections_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.video_id == video_id,
            )
        )
        correction = corrections_result.scalar_one()
        assert correction.corrected_by_user_id == ACTOR_CLI_BATCH, (
            f"Audit record must have corrected_by_user_id='{ACTOR_CLI_BATCH}', "
            f"got {correction.corrected_by_user_id!r}"
        )
