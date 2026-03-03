"""
Integration tests for TranscriptCorrectionService.apply_correction.

Uses a real PostgreSQL test database (via the ``db_session`` fixture from
``tests/integration/conftest.py``) to verify the full end-to-end flow:

  create transcript + segment → apply_correction → verify persisted state

Database URL defaults to:
  postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test

Override with DATABASE_INTEGRATION_URL or CHRONOVISTA_INTEGRATION_DB_URL env var.

Tests in this module validate:
  - T010: Full apply_correction flow (T009 = unit, T010 = integration)
  - NFR-007: display_text property returns corrected text after apply_correction
  - Version chain integrity with two consecutive corrections
  - GAP-1/6/7: display_text after revert_correction (to-original and to-prior)
  - GAP-2: Search contract integration (ILIKE on both text and corrected_text)
  - GAP-3: SRT export integration (format_segment_srt uses display_text)
  - GAP-4: Transcript segments API inline ternary logic
  - GAP-5: Transcript metadata fields available on ORM after correction

Feature 033 — Transcript Corrections Audit
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.enums import CorrectionType
from chronovista.models.transcript_segment import TranscriptSegment
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
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
    """Insert a minimal Video row to satisfy the transcript FK constraint."""
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
) -> VideoTranscriptDB:
    """Insert a VideoTranscript row with correction metadata defaults."""
    transcript = VideoTranscriptDB(
        video_id=video_id,
        language_code=language_code,
        transcript_text="teh quick brown fox jumps over the lazy dog",
        transcript_type="manual",
        download_reason="user_request",
        is_cc=False,
        is_auto_synced=False,
        track_kind="standard",
        source="youtube_transcript_api",
        # Feature 033 columns — explicit defaults
        has_corrections=False,
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
    text: str = "teh quick brown fox",
    sequence_number: int = 0,
    corrected_text: str | None = None,
    has_correction: bool = False,
) -> TranscriptSegmentDB:
    """Insert a TranscriptSegment row linked to the given transcript."""
    segment = TranscriptSegmentDB(
        video_id=video_id,
        language_code=language_code,
        text=text,
        start_time=0.0,
        duration=2.5,
        end_time=2.5,
        sequence_number=sequence_number,
        corrected_text=corrected_text,
        has_correction=has_correction,
    )
    session.add(segment)
    await session.flush()
    return segment


# ---------------------------------------------------------------------------
# TestApplyCorrectionIntegration
# ---------------------------------------------------------------------------


class TestApplyCorrectionIntegration:
    """
    End-to-end integration tests for TranscriptCorrectionService.apply_correction
    using a real PostgreSQL test database.

    Each test uses ``db_session`` from ``tests/integration/conftest.py`` which
    creates all tables, yields the session, then rolls back and drops all tables
    for full isolation between tests.
    """

    @pytest.fixture
    def correction_repo(self) -> TranscriptCorrectionRepository:
        """Provide a real TranscriptCorrectionRepository."""
        return TranscriptCorrectionRepository()

    @pytest.fixture
    def segment_repo(self) -> TranscriptSegmentRepository:
        """Provide a real TranscriptSegmentRepository."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def transcript_repo(self) -> VideoTranscriptRepository:
        """Provide a real VideoTranscriptRepository."""
        return VideoTranscriptRepository()

    @pytest.fixture
    def service(
        self,
        correction_repo: TranscriptCorrectionRepository,
        segment_repo: TranscriptSegmentRepository,
        transcript_repo: VideoTranscriptRepository,
    ) -> object:
        """
        Provide a TranscriptCorrectionService wired with real repositories.

        Imported lazily so TDD tests can be written before implementation exists.
        """
        from chronovista.services.transcript_correction_service import (
            TranscriptCorrectionService,
        )

        return TranscriptCorrectionService(
            correction_repo=correction_repo,
            segment_repo=segment_repo,
            transcript_repo=transcript_repo,
        )

    async def test_apply_correction_end_to_end(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        Full end-to-end test for apply_correction (T010).

        Creates a transcript + segment in the DB, calls apply_correction, then
        verifies all six expected state changes are persisted to the database:

        1. TranscriptCorrection audit record exists with correct fields
        2. segment.corrected_text = the new corrected text
        3. segment.has_correction = True
        4. transcript.has_corrections = True
        5. transcript.correction_count = 1
        6. transcript.last_corrected_at is not None

        This validates FR-007 (atomic guarantee) and FR-008 (audit record fields).
        """
        # Arrange: seed the minimum required rows in dependency order
        video_id = "dQw4w9WgXcQ"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
        )
        segment_id = segment.id

        # Act: apply the first correction
        result = await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="the quick brown fox",
            correction_type=CorrectionType.SPELLING,
            correction_note="Fixed typo: teh → the",
            corrected_by_user_id="cli",
        )

        # Flush to surface any constraint violations before assertions
        await db_session.flush()

        # Assert 1: audit record was persisted with correct field values
        correction_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == result.id
            )
        )
        persisted_correction = correction_result.scalar_one_or_none()
        assert persisted_correction is not None, (
            "TranscriptCorrection audit record must be persisted to the database"
        )
        assert persisted_correction.video_id == video_id
        assert persisted_correction.language_code == language_code
        assert persisted_correction.segment_id == segment_id
        assert persisted_correction.version_number == 1, (
            "First correction must have version_number=1"
        )
        assert persisted_correction.original_text == "teh quick brown fox", (
            "original_text must be the segment's pre-correction text"
        )
        assert persisted_correction.corrected_text == "the quick brown fox", (
            "corrected_text must be the new corrected text"
        )
        assert persisted_correction.correction_note == "Fixed typo: teh → the"
        assert persisted_correction.corrected_by_user_id == "cli"

        # Assert 2-3: segment state updated
        segment_result = await db_session.execute(
            select(TranscriptSegmentDB).where(
                TranscriptSegmentDB.id == segment_id
            )
        )
        persisted_segment = segment_result.scalar_one()
        assert persisted_segment.corrected_text == "the quick brown fox", (
            "segment.corrected_text must be set to the corrected text"
        )
        assert persisted_segment.has_correction is True, (
            "segment.has_correction must be True after correction"
        )

        # Assert 4-6: transcript metadata updated
        transcript_result = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        persisted_transcript = transcript_result.scalar_one()
        assert persisted_transcript.has_corrections is True, (
            "transcript.has_corrections must be True after correction"
        )
        assert persisted_transcript.correction_count == 1, (
            "transcript.correction_count must be incremented to 1"
        )
        assert persisted_transcript.last_corrected_at is not None, (
            "transcript.last_corrected_at must be set after correction"
        )

    async def test_display_text_returns_corrected_text_after_apply(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        NFR-007: After apply_correction, loading the segment as a Pydantic
        TranscriptSegment model and calling display_text must return the
        corrected text, not the original.

        This validates the downstream contract used by SRT export and CLI output.
        """
        video_id = "abc1234DEFG"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="i went two the store",
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply correction
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="i went to the store",
            correction_type=CorrectionType.ASR_ERROR,
            correction_note="ASR confused homophone 'two' → 'to'",
        )
        await db_session.flush()

        # Reload the segment from the DB and convert to Pydantic model
        segment_result = await db_session.execute(
            select(TranscriptSegmentDB).where(
                TranscriptSegmentDB.id == segment_id
            )
        )
        db_segment = segment_result.scalar_one()

        pydantic_segment = TranscriptSegment.model_validate(db_segment)

        # NFR-007: display_text must return the corrected text
        assert pydantic_segment.display_text == "i went to the store", (
            "NFR-007: display_text must return corrected_text after apply_correction, "
            f"got '{pydantic_segment.display_text}' instead"
        )
        assert pydantic_segment.text == "i went two the store", (
            "The original text field must be preserved unchanged"
        )
        assert pydantic_segment.has_correction is True
        assert pydantic_segment.corrected_text == "i went to the store"

    async def test_version_chain_integration(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        Apply two corrections to the same segment and verify the version chain:
        - version 1: original_text = segment.text, corrected_text = first_correction
        - version 2: original_text = first_correction (effective after v1), corrected_text = second_correction

        This validates that version_number increments correctly and that
        original_text always captures the "before" state for that specific version
        (enabling revert to reconstruct any point in the chain).
        """
        video_id = "XYZxyz12345"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh lazy dog",
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply first correction (v1)
        correction_v1 = await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="the lazy dog",
            correction_type=CorrectionType.SPELLING,
            corrected_by_user_id="cli",
        )
        await db_session.flush()

        # Apply second correction (v2)
        correction_v2 = await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="The lazy dog.",
            correction_type=CorrectionType.FORMATTING,
            corrected_by_user_id="cli",
        )
        await db_session.flush()

        # Reload both correction records from DB
        v1_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == correction_v1.id
            )
        )
        v1 = v1_result.scalar_one()

        v2_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == correction_v2.id
            )
        )
        v2 = v2_result.scalar_one()

        # Verify version_numbers are 1 and 2
        assert v1.version_number == 1, (
            "First correction must have version_number=1"
        )
        assert v2.version_number == 2, (
            "Second correction must have version_number=2"
        )

        # Verify the chain: v2.original_text == v1.corrected_text
        assert v2.original_text == v1.corrected_text, (
            "The original_text of v2 must equal the corrected_text of v1 "
            "(the effective text between corrections). "
            f"v1.corrected_text='{v1.corrected_text}', "
            f"v2.original_text='{v2.original_text}'"
        )

        # Verify v1.original_text is the raw segment text
        assert v1.original_text == "teh lazy dog", (
            "v1.original_text must be the segment's raw text before any correction"
        )

        # Verify final segment state
        segment_result = await db_session.execute(
            select(TranscriptSegmentDB).where(
                TranscriptSegmentDB.id == segment_id
            )
        )
        final_segment = segment_result.scalar_one()
        assert final_segment.corrected_text == "The lazy dog.", (
            "segment.corrected_text must reflect the most recent correction"
        )
        assert final_segment.has_correction is True

        # Verify transcript correction_count = 2 (two active corrections)
        transcript_result = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        transcript = transcript_result.scalar_one()
        assert transcript.correction_count == 2, (
            "transcript.correction_count must be 2 after two apply_correction calls"
        )
        assert transcript.has_corrections is True
        assert transcript.last_corrected_at is not None

    async def test_apply_correction_raises_for_nonexistent_segment(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        apply_correction must raise ValueError when the segment_id does not
        exist in the database. No audit record must be written.
        """
        video_id = "dQw4w9WgXcQ"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        nonexistent_segment_id = 999_999

        with pytest.raises(ValueError):
            await service.apply_correction(  # type: ignore[attr-defined]
                db_session,
                video_id=video_id,
                language_code=language_code,
                segment_id=nonexistent_segment_id,
                corrected_text="anything",
                correction_type=CorrectionType.SPELLING,
            )

        # Verify no corrections were inserted
        count_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.segment_id == nonexistent_segment_id
            )
        )
        assert count_result.scalar_one_or_none() is None, (
            "No audit record must be created when segment does not exist"
        )

    async def test_apply_correction_raises_for_identical_text(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        apply_correction must raise ValueError when corrected_text is identical
        to the segment's current effective text (no-op prevention).
        """
        video_id = "dQw4w9WgXcQ"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="already correct text",
        )

        with pytest.raises(ValueError):
            await service.apply_correction(  # type: ignore[attr-defined]
                db_session,
                video_id=video_id,
                language_code=language_code,
                segment_id=segment.id,
                corrected_text="already correct text",  # identical to segment.text
                correction_type=CorrectionType.SPELLING,
            )

    async def test_correction_count_increments_on_each_apply(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        Each successive apply_correction call must increment
        transcript.correction_count by exactly 1 each time.
        """
        video_id = "corCount12A"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        segment_a = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="segment a text",
            sequence_number=0,
        )
        segment_b = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="segment b text",
            sequence_number=1,
        )

        # First correction on segment_a
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_a.id,
            corrected_text="segment a corrected",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Second correction on segment_b
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_b.id,
            corrected_text="segment b corrected",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Verify correction_count = 2
        transcript_result = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        transcript = transcript_result.scalar_one()
        assert transcript.correction_count == 2, (
            "correction_count must equal the number of apply_correction calls "
            f"(expected 2, got {transcript.correction_count})"
        )


# ---------------------------------------------------------------------------
# TestRevertCorrectionIntegration
# ---------------------------------------------------------------------------


class TestRevertCorrectionIntegration:
    """
    End-to-end integration tests for TranscriptCorrectionService.revert_correction
    using a real PostgreSQL test database.

    Each test uses ``db_session`` from ``tests/integration/conftest.py`` which
    creates all tables, yields the session, then rolls back and drops all tables
    for full isolation between tests.

    Tests validate:
    - Revert-to-original restores segment state and decrements correction_count
    - Revert with multiple segments correctly recomputes has_corrections
    - Version chain integrity is maintained across apply → revert cycles
    """

    @pytest.fixture
    def correction_repo(self) -> TranscriptCorrectionRepository:
        """Provide a real TranscriptCorrectionRepository."""
        return TranscriptCorrectionRepository()

    @pytest.fixture
    def segment_repo(self) -> TranscriptSegmentRepository:
        """Provide a real TranscriptSegmentRepository."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def transcript_repo(self) -> VideoTranscriptRepository:
        """Provide a real VideoTranscriptRepository."""
        return VideoTranscriptRepository()

    @pytest.fixture
    def service(
        self,
        correction_repo: TranscriptCorrectionRepository,
        segment_repo: TranscriptSegmentRepository,
        transcript_repo: VideoTranscriptRepository,
    ) -> object:
        """
        Provide a TranscriptCorrectionService wired with real repositories.
        """
        from chronovista.services.transcript_correction_service import (
            TranscriptCorrectionService,
        )

        return TranscriptCorrectionService(
            correction_repo=correction_repo,
            segment_repo=segment_repo,
            transcript_repo=transcript_repo,
        )

    async def test_revert_single_correction(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        Apply a single correction then revert it. Verify the segment is fully
        restored to its original uncorrected state:

        1. segment.corrected_text = None
        2. segment.has_correction = False
        3. transcript.has_corrections = False (no other corrected segments)
        4. transcript.correction_count decremented back to 0 (FR-014a)
        5. transcript.last_corrected_at updated (FR-014c)
        6. A revert audit record is persisted with correction_type='revert'
        """
        video_id = "revertSingle1"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply correction (creates v1)
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="the quick brown fox",
            correction_type=CorrectionType.SPELLING,
            correction_note="Fixed typo",
            corrected_by_user_id="cli",
        )
        await db_session.flush()

        # Revert (creates v2 audit record)
        revert_record = await service.revert_correction(  # type: ignore[attr-defined]
            db_session,
            segment_id=segment_id,
        )
        await db_session.flush()

        # Assert 1-2: segment fully restored
        segment_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == segment_id)
        )
        persisted_segment = segment_result.scalar_one()
        assert persisted_segment.corrected_text is None, (
            "After revert-to-original, segment.corrected_text must be None"
        )
        assert persisted_segment.has_correction is False, (
            "After revert-to-original, segment.has_correction must be False"
        )

        # Assert 3-5: transcript metadata reflects the revert
        transcript_result = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        persisted_transcript = transcript_result.scalar_one()
        assert persisted_transcript.has_corrections is False, (
            "transcript.has_corrections must be False after revert to original "
            "(no other corrected segments exist)"
        )
        assert persisted_transcript.correction_count == 0, (
            "FR-014a: transcript.correction_count must be decremented to 0 "
            f"after revert-to-original (got {persisted_transcript.correction_count})"
        )
        assert persisted_transcript.last_corrected_at is not None, (
            "FR-014c: transcript.last_corrected_at must be updated after revert"
        )

        # Assert 6: revert audit record persisted
        revert_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == revert_record.id
            )
        )
        persisted_revert = revert_result.scalar_one_or_none()
        assert persisted_revert is not None, (
            "Revert audit record must be persisted to the database"
        )
        assert persisted_revert.correction_type == "revert", (
            "Revert audit record must have correction_type='revert'"
        )
        assert persisted_revert.version_number == 2, (
            "Revert audit record must have version_number=2 (was v1 correction)"
        )
        assert persisted_revert.original_text == "the quick brown fox", (
            "Revert audit original_text must be the text BEFORE the revert "
            "(i.e., the corrected text from v1)"
        )
        assert persisted_revert.corrected_text == "teh quick brown fox", (
            "Revert audit corrected_text must be the original segment text "
            "(i.e., what the segment is restored to)"
        )

    async def test_revert_with_multiple_segments_scans_has_corrections(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        FR-014b: Two segments have corrections. Revert one segment to its
        original state. Since the other segment still has has_correction=True,
        transcript.has_corrections must remain True after the revert.

        This validates that the EXISTS scan correctly identifies remaining
        corrected segments, not just the segment being reverted.
        """
        video_id = "revertMultSeg"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        segment_a = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="first segment text",
            sequence_number=0,
        )
        segment_b = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="second segment text",
            sequence_number=1,
        )

        # Apply corrections to both segments
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_a.id,
            corrected_text="first segment corrected",
            correction_type=CorrectionType.SPELLING,
        )
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_b.id,
            corrected_text="second segment corrected",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Verify both corrections are in place
        transcript_result = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        transcript_before_revert = transcript_result.scalar_one()
        assert transcript_before_revert.correction_count == 2
        assert transcript_before_revert.has_corrections is True

        # Revert segment_a to original — segment_b still has a correction
        await service.revert_correction(  # type: ignore[attr-defined]
            db_session,
            segment_id=segment_a.id,
        )
        await db_session.flush()

        # Reload transcript and assert has_corrections remains True
        transcript_result = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        transcript_after_revert = transcript_result.scalar_one()
        assert transcript_after_revert.has_corrections is True, (
            "FR-014b: transcript.has_corrections must remain True because "
            "segment_b still has an active correction"
        )
        assert transcript_after_revert.correction_count == 1, (
            "FR-014a: transcript.correction_count must be decremented to 1 "
            f"after reverting segment_a (got {transcript_after_revert.correction_count})"
        )

        # Verify segment_a is fully restored
        seg_a_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == segment_a.id)
        )
        persisted_seg_a = seg_a_result.scalar_one()
        assert persisted_seg_a.corrected_text is None
        assert persisted_seg_a.has_correction is False

        # Verify segment_b is untouched
        seg_b_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == segment_b.id)
        )
        persisted_seg_b = seg_b_result.scalar_one()
        assert persisted_seg_b.corrected_text == "second segment corrected"
        assert persisted_seg_b.has_correction is True

    async def test_version_chain_after_apply_revert_cycle(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        Verify the full version chain after an apply → apply → revert sequence:

        v1: apply "the lazy dog"           (original: "teh lazy dog")
        v2: apply "The lazy dog."          (original: "the lazy dog")
        v3: revert (corrected_text=v2.original_text="the lazy dog")

        Expected state after v3:
        - segment.corrected_text = "the lazy dog" (reverted to v1 corrected text)
        - segment.has_correction = True
        - transcript.correction_count = 2 (unchanged — revert-to-prior, not original)
        - v3.correction_type = 'revert'
        - v3.original_text = "The lazy dog." (what segment had before this revert)
        - v3.corrected_text = "the lazy dog" (what segment is restored to)
        - v3.version_number = 3
        """
        video_id = "revertChain01"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh lazy dog",
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply v1
        correction_v1 = await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="the lazy dog",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Apply v2
        correction_v2 = await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="The lazy dog.",
            correction_type=CorrectionType.FORMATTING,
        )
        await db_session.flush()

        # Revert (creates v3)
        correction_v3 = await service.revert_correction(  # type: ignore[attr-defined]
            db_session,
            segment_id=segment_id,
        )
        await db_session.flush()

        # Reload all records from DB
        v1_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == correction_v1.id
            )
        )
        v1 = v1_result.scalar_one()

        v2_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == correction_v2.id
            )
        )
        v2 = v2_result.scalar_one()

        v3_result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == correction_v3.id
            )
        )
        v3 = v3_result.scalar_one()

        # Assert version chain integrity
        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v3.version_number == 3, (
            "Revert audit record must have version_number = max_version + 1 = 3"
        )

        assert v3.correction_type == "revert", (
            "Revert audit record must have correction_type='revert'"
        )
        assert v3.original_text == "The lazy dog.", (
            "v3.original_text must be what the segment had BEFORE the revert "
            f"(v2.corrected_text='The lazy dog.', got '{v3.original_text}')"
        )
        assert v3.corrected_text == "the lazy dog", (
            "v3.corrected_text must be what the segment is restored to "
            f"(v2.original_text='the lazy dog', got '{v3.corrected_text}')"
        )

        # Assert segment state after revert-to-prior (version > 1)
        segment_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == segment_id)
        )
        final_segment = segment_result.scalar_one()
        assert final_segment.corrected_text == "the lazy dog", (
            "After revert-to-prior, segment.corrected_text must be V_N.original_text "
            f"(expected 'the lazy dog', got '{final_segment.corrected_text}')"
        )
        assert final_segment.has_correction is True, (
            "After revert-to-prior, segment.has_correction must remain True "
            "(segment is still corrected, just to the prior version)"
        )

        # Assert transcript metadata for revert-to-prior
        transcript_result = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        final_transcript = transcript_result.scalar_one()
        assert final_transcript.correction_count == 2, (
            "FR-014a: revert-to-prior must NOT change correction_count "
            f"(expected 2, got {final_transcript.correction_count})"
        )
        assert final_transcript.has_corrections is True, (
            "transcript.has_corrections must remain True after revert-to-prior "
            "(segment still has an active correction)"
        )
        assert final_transcript.last_corrected_at is not None, (
            "FR-014c: transcript.last_corrected_at must be updated after revert"
        )


# ---------------------------------------------------------------------------
# TestRepositoryQueryIntegration
# ---------------------------------------------------------------------------


class TestRepositoryQueryIntegration:
    """
    Integration tests for TranscriptCorrectionRepository domain-specific
    query methods: get_by_segment, get_by_video, count_by_video.

    Each test seeds the minimum required rows (Video → VideoTranscript →
    TranscriptSegment) via the helper functions defined at the top of this
    module, then drives data creation through
    ``TranscriptCorrectionService.apply_correction`` so that every
    correction record is created by realistic production code paths rather
    than raw DB inserts.

    Tests validate:
      - SC-001: get_by_segment returns records ordered version_number DESC
      - SC-002: get_by_video returns paginated (items, total) tuples
      - SC-003: get_by_segment wall-clock time < 1 s for 100 records (smoke)
      - Language-code isolation for both get_by_video and count_by_video
    """

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------

    @pytest.fixture
    def correction_repo(self) -> TranscriptCorrectionRepository:
        """Provide a real TranscriptCorrectionRepository."""
        return TranscriptCorrectionRepository()

    @pytest.fixture
    def segment_repo(self) -> TranscriptSegmentRepository:
        """Provide a real TranscriptSegmentRepository."""
        return TranscriptSegmentRepository()

    @pytest.fixture
    def transcript_repo(self) -> VideoTranscriptRepository:
        """Provide a real VideoTranscriptRepository."""
        return VideoTranscriptRepository()

    @pytest.fixture
    def service(
        self,
        correction_repo: TranscriptCorrectionRepository,
        segment_repo: TranscriptSegmentRepository,
        transcript_repo: VideoTranscriptRepository,
    ) -> object:
        """Provide a TranscriptCorrectionService wired with real repositories."""
        from chronovista.services.transcript_correction_service import (
            TranscriptCorrectionService,
        )

        return TranscriptCorrectionService(
            correction_repo=correction_repo,
            segment_repo=segment_repo,
            transcript_repo=transcript_repo,
        )

    # ------------------------------------------------------------------
    # SC-001: get_by_segment ordering
    # ------------------------------------------------------------------

    async def test_get_by_segment_returns_version_number_desc(
        self,
        db_session: AsyncSession,
        correction_repo: TranscriptCorrectionRepository,
        service: object,
    ) -> None:
        """
        SC-001: get_by_segment must return records ordered by version_number
        DESC (newest correction first).

        Creates three successive corrections on the same segment using
        apply_correction (v1 → v2 → v3), then queries get_by_segment and
        asserts the result list is ordered [v3, v2, v1].
        """
        video_id = "segOrderABC"
        language_code = "en"

        # Seed prerequisite rows
        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="version one text",
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply three consecutive corrections to build a version chain v1→v2→v3
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="version two text",
            correction_type=CorrectionType.SPELLING,
            correction_note="v1 correction",
        )
        await db_session.flush()

        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="version three text",
            correction_type=CorrectionType.SPELLING,
            correction_note="v2 correction",
        )
        await db_session.flush()

        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="version four text",
            correction_type=CorrectionType.FORMATTING,
            correction_note="v3 correction",
        )
        await db_session.flush()

        # Query via repository
        corrections = await correction_repo.get_by_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
        )

        # Must return exactly three records
        assert len(corrections) == 3, (
            f"Expected 3 corrections for segment, got {len(corrections)}"
        )

        # Must be ordered version_number DESC: [3, 2, 1]
        version_numbers = [c.version_number for c in corrections]
        assert version_numbers == [3, 2, 1], (
            "get_by_segment must return corrections ordered by version_number DESC. "
            f"Got order: {version_numbers}"
        )

    # ------------------------------------------------------------------
    # SC-002: get_by_video pagination
    # ------------------------------------------------------------------

    async def test_get_by_video_returns_paginated_results(
        self,
        db_session: AsyncSession,
        correction_repo: TranscriptCorrectionRepository,
        service: object,
    ) -> None:
        """
        SC-002: get_by_video with limit=2 skip=0 must return exactly 2 items
        while reporting total=5 (the full uncapped count for the transcript).

        Creates five separate segments, applies one correction to each, then
        verifies the (items, total) contract of get_by_video.
        """
        video_id = "paginateVID"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        # Seed 5 segments, each with a unique original text
        for seq in range(5):
            segment = await _seed_segment(
                db_session,
                video_id=video_id,
                language_code=language_code,
                text=f"original segment text number {seq}",
                sequence_number=seq,
            )
            await service.apply_correction(  # type: ignore[attr-defined]
                db_session,
                video_id=video_id,
                language_code=language_code,
                segment_id=segment.id,
                corrected_text=f"corrected segment text number {seq}",
                correction_type=CorrectionType.SPELLING,
            )
            await db_session.flush()

        # Fetch first page: limit=2, skip=0
        items, total = await correction_repo.get_by_video(
            db_session,
            video_id=video_id,
            language_code=language_code,
            skip=0,
            limit=2,
        )

        assert len(items) == 2, (
            f"limit=2 must return exactly 2 items; got {len(items)}"
        )
        assert total == 5, (
            f"total must reflect all 5 corrections in the transcript; got {total}"
        )

    # ------------------------------------------------------------------
    # Language-code isolation: get_by_video
    # ------------------------------------------------------------------

    async def test_get_by_video_requires_language_code(
        self,
        db_session: AsyncSession,
        correction_repo: TranscriptCorrectionRepository,
        service: object,
    ) -> None:
        """
        get_by_video must filter strictly by language_code: querying with a
        different language_code must return an empty item list and total=0.

        Creates corrections under language_code "en", then queries for "fr"
        and asserts an empty result.
        """
        video_id = "langIsoVID1"
        en_language_code = "en"
        fr_language_code = "fr"

        await _seed_video(db_session, video_id=video_id)

        # Seed English transcript and one correction
        await _seed_transcript(
            db_session, video_id=video_id, language_code=en_language_code
        )
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=en_language_code,
            text="english original text",
            sequence_number=0,
        )
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=en_language_code,
            segment_id=segment.id,
            corrected_text="english corrected text",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Query using the French language_code — no French transcript or
        # corrections exist, so the result must be empty
        items, total = await correction_repo.get_by_video(
            db_session,
            video_id=video_id,
            language_code=fr_language_code,
        )

        assert items == [], (
            "get_by_video must return an empty item list when no corrections "
            f"exist for language_code='{fr_language_code}'; got {items}"
        )
        assert total == 0, (
            "get_by_video must return total=0 when no corrections exist for "
            f"language_code='{fr_language_code}'; got total={total}"
        )

    # ------------------------------------------------------------------
    # count_by_video per-language scoping
    # ------------------------------------------------------------------

    async def test_count_by_video_across_languages(
        self,
        db_session: AsyncSession,
        correction_repo: TranscriptCorrectionRepository,
        service: object,
    ) -> None:
        """
        count_by_video must scope its count to the requested language_code.

        Creates 3 corrections under "en" and 2 corrections under "es" for the
        same video.  Verifies that:
          - count_by_video(video_id, "en") == 3
          - count_by_video(video_id, "es") == 2

        This confirms the per-language isolation contract: the method never
        conflates corrections from different transcripts of the same video.
        """
        video_id = "countLangVD"
        en_code = "en"
        es_code = "es"

        await _seed_video(db_session, video_id=video_id)

        # English transcript: 3 segments → 3 corrections
        await _seed_transcript(db_session, video_id=video_id, language_code=en_code)
        for seq in range(3):
            seg_en = await _seed_segment(
                db_session,
                video_id=video_id,
                language_code=en_code,
                text=f"en original {seq}",
                sequence_number=seq,
            )
            await service.apply_correction(  # type: ignore[attr-defined]
                db_session,
                video_id=video_id,
                language_code=en_code,
                segment_id=seg_en.id,
                corrected_text=f"en corrected {seq}",
                correction_type=CorrectionType.SPELLING,
            )
            await db_session.flush()

        # Spanish transcript: 2 segments → 2 corrections
        await _seed_transcript(db_session, video_id=video_id, language_code=es_code)
        for seq in range(2):
            seg_es = await _seed_segment(
                db_session,
                video_id=video_id,
                language_code=es_code,
                text=f"es original {seq}",
                sequence_number=seq,
            )
            await service.apply_correction(  # type: ignore[attr-defined]
                db_session,
                video_id=video_id,
                language_code=es_code,
                segment_id=seg_es.id,
                corrected_text=f"es corrected {seq}",
                correction_type=CorrectionType.SPELLING,
            )
            await db_session.flush()

        en_count = await correction_repo.count_by_video(
            db_session, video_id=video_id, language_code=en_code
        )
        es_count = await correction_repo.count_by_video(
            db_session, video_id=video_id, language_code=es_code
        )

        assert en_count == 3, (
            f"count_by_video for 'en' must return 3; got {en_count}"
        )
        assert es_count == 2, (
            f"count_by_video for 'es' must return 2; got {es_count}"
        )

    # ------------------------------------------------------------------
    # Empty segment query
    # ------------------------------------------------------------------

    async def test_get_by_segment_empty_for_no_corrections(
        self,
        db_session: AsyncSession,
        correction_repo: TranscriptCorrectionRepository,
    ) -> None:
        """
        get_by_segment must return an empty list when no corrections exist for
        the given segment_id, without raising an error.

        Creates a valid segment (to satisfy FK constraints) but applies no
        corrections to it.  The repository must return [] gracefully.
        """
        video_id = "emptySegVID"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="a segment with no corrections",
            sequence_number=0,
        )

        corrections = await correction_repo.get_by_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment.id,
        )

        assert corrections == [], (
            "get_by_segment must return an empty list when no corrections exist "
            f"for segment_id={segment.id}; got {corrections}"
        )

    # ------------------------------------------------------------------
    # SC-003: 100-record performance smoke test
    # ------------------------------------------------------------------

    async def test_100_record_performance_smoke_test(
        self,
        db_session: AsyncSession,
        correction_repo: TranscriptCorrectionRepository,
        service: object,
    ) -> None:
        """
        SC-003: get_by_segment wall-clock time must be < 1 second when
        retrieving a 100-record correction chain for a single segment.

        Inserts 100 corrections for a single segment using apply_correction
        (the realistic production path), then measures the elapsed time for
        a single get_by_segment call with limit=100.

        This is a smoke test that catches pathological N+1 or missing-index
        regressions. The threshold of 1 second provides generous headroom for
        CI variability while still catching gross inefficiencies.
        """
        video_id = "perf100VID1"
        language_code = "en"
        correction_count = 100

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="initial text version 0",
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply 100 consecutive corrections to build a long version chain.
        # Each iteration's corrected_text differs from the previous, satisfying
        # the no-op guard inside apply_correction.
        for i in range(1, correction_count + 1):
            await service.apply_correction(  # type: ignore[attr-defined]
                db_session,
                video_id=video_id,
                language_code=language_code,
                segment_id=segment_id,
                corrected_text=f"corrected text version {i}",
                correction_type=CorrectionType.SPELLING,
                correction_note=f"correction #{i}",
            )
        # Flush all 100 records in one batch at the end
        await db_session.flush()

        # Verify all 100 records are actually in the DB before timing the read
        total_inserted = await correction_repo.count_by_video(
            db_session, video_id=video_id, language_code=language_code
        )
        assert total_inserted == correction_count, (
            f"Expected {correction_count} corrections to be inserted; "
            f"got {total_inserted}"
        )

        # Time the get_by_segment query with limit=100
        t_start = time.perf_counter()
        results = await correction_repo.get_by_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            limit=correction_count,
        )
        elapsed = time.perf_counter() - t_start

        assert len(results) == correction_count, (
            f"get_by_segment must return all {correction_count} records; "
            f"got {len(results)}"
        )
        assert elapsed < 1.0, (
            f"SC-003: get_by_segment for {correction_count} records took "
            f"{elapsed:.3f}s, which exceeds the 1-second threshold. "
            "This indicates a missing index or N+1 query regression."
        )


# ---------------------------------------------------------------------------
# GAP-1 / GAP-6 / GAP-7: display_text after revert_correction
# ---------------------------------------------------------------------------


class TestDisplayTextAfterRevert:
    """
    Integration tests validating that the ``display_text`` property returns
    the correct value after revert_correction in both scenarios:

    - Revert-to-original (single correction reverted → display_text = raw text)
    - Revert-to-prior (two corrections, revert second → display_text = first
      correction's text)

    These tests close GAP-1, GAP-6, and GAP-7 from the Feature 033 cross-feature
    data contract audit.
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
    def service(
        self,
        correction_repo: TranscriptCorrectionRepository,
        segment_repo: TranscriptSegmentRepository,
        transcript_repo: VideoTranscriptRepository,
    ) -> object:
        from chronovista.services.transcript_correction_service import (
            TranscriptCorrectionService,
        )

        return TranscriptCorrectionService(
            correction_repo=correction_repo,
            segment_repo=segment_repo,
            transcript_repo=transcript_repo,
        )

    async def test_display_text_returns_original_after_revert_to_original(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        GAP-1: After a single correction is reverted (revert-to-original),
        the Pydantic model's display_text must return the original raw text.

        Steps:
        1. Seed a segment with raw text
        2. Apply one correction
        3. Revert it (single correction → revert-to-original)
        4. Reload segment from DB, convert to Pydantic model
        5. Assert display_text == original raw text
        """
        video_id = "dspRevOrig1"
        language_code = "en"
        original_text = "teh orignal text"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text=original_text,
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply one correction
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="the original text",
            correction_type=CorrectionType.SPELLING,
            correction_note="Fixed typos",
        )
        await db_session.flush()

        # Revert (single correction → revert-to-original)
        await service.revert_correction(  # type: ignore[attr-defined]
            db_session,
            segment_id=segment_id,
        )
        await db_session.flush()

        # Reload segment from DB and convert to Pydantic model
        segment_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == segment_id)
        )
        db_segment = segment_result.scalar_one()
        pydantic_segment = TranscriptSegment.model_validate(db_segment)

        # Assert: display_text returns the original raw text
        assert pydantic_segment.display_text == original_text, (
            "GAP-1: After revert-to-original, display_text must return the "
            f"original raw text '{original_text}', "
            f"got '{pydantic_segment.display_text}'"
        )
        assert pydantic_segment.has_correction is False, (
            "After revert-to-original, has_correction must be False"
        )
        assert pydantic_segment.corrected_text is None, (
            "After revert-to-original, corrected_text must be None"
        )

    async def test_display_text_returns_prior_correction_after_revert_to_prior(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        GAP-6/7: After two corrections, reverting the second must leave
        display_text returning the FIRST correction's text (not the raw text).

        Steps:
        1. Seed a segment with raw text
        2. Apply first correction
        3. Apply second correction
        4. Revert the second correction (revert-to-prior)
        5. Reload segment from DB, convert to Pydantic model
        6. Assert display_text == first correction's text
        """
        video_id = "dspRevPrior"
        language_code = "en"
        raw_text = "teh lazy dgo"
        first_correction = "the lazy dgo"
        second_correction = "the lazy dog"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text=raw_text,
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply first correction (v1)
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text=first_correction,
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Apply second correction (v2)
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text=second_correction,
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Revert (v3 — revert-to-prior, not to original)
        await service.revert_correction(  # type: ignore[attr-defined]
            db_session,
            segment_id=segment_id,
        )
        await db_session.flush()

        # Reload segment from DB and convert to Pydantic model
        segment_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == segment_id)
        )
        db_segment = segment_result.scalar_one()
        pydantic_segment = TranscriptSegment.model_validate(db_segment)

        # Assert: display_text returns the FIRST correction's text
        assert pydantic_segment.display_text == first_correction, (
            "GAP-6/7: After revert-to-prior, display_text must return the "
            f"first correction's text '{first_correction}', "
            f"got '{pydantic_segment.display_text}'"
        )
        assert pydantic_segment.has_correction is True, (
            "After revert-to-prior, has_correction must remain True"
        )
        assert pydantic_segment.corrected_text == first_correction, (
            "After revert-to-prior, corrected_text must be the first "
            f"correction's text '{first_correction}', "
            f"got '{pydantic_segment.corrected_text}'"
        )
        # Also verify raw text is still untouched
        assert pydantic_segment.text == raw_text, (
            "The original raw text must never be modified by corrections"
        )


# ---------------------------------------------------------------------------
# GAP-2: Search contract integration
# ---------------------------------------------------------------------------


class TestSearchContractIntegration:
    """
    Integration tests validating that the search router's ILIKE queries
    can find segments by both ``text`` and ``corrected_text`` columns.

    The search router (``search.py:140-147``) uses ``or_(text.ilike(...),
    corrected_text.ilike(...))`` — this test verifies both columns are set
    correctly after apply_correction and that ILIKE on corrected_text would
    find the corrected content.

    Closes GAP-2 from the Feature 033 cross-feature data contract audit.
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
    def service(
        self,
        correction_repo: TranscriptCorrectionRepository,
        segment_repo: TranscriptSegmentRepository,
        transcript_repo: VideoTranscriptRepository,
    ) -> object:
        from chronovista.services.transcript_correction_service import (
            TranscriptCorrectionService,
        )

        return TranscriptCorrectionService(
            correction_repo=correction_repo,
            segment_repo=segment_repo,
            transcript_repo=transcript_repo,
        )

    async def test_search_finds_corrected_text_via_ilike(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        GAP-2: After apply_correction, the segment's corrected_text column
        must be set so that an ILIKE search on corrected_text can find the
        corrected content.

        Steps:
        1. Seed a segment with text "teh quick brown fox"
        2. Apply a correction changing it to "the quick brown fox"
        3. Verify both text and corrected_text columns are set correctly
        4. Verify corrected_text is findable by ILIKE search
        """
        video_id = "srchGap2VD1"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="teh quick brown fox",
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply correction
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text="the quick brown fox",
            correction_type=CorrectionType.SPELLING,
            correction_note="Fixed typo: teh → the",
        )
        await db_session.flush()

        # Verify both columns are set correctly on the DB row
        segment_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == segment_id)
        )
        db_seg = segment_result.scalar_one()
        assert db_seg.text == "teh quick brown fox", (
            "Original text column must be preserved unchanged"
        )
        assert db_seg.corrected_text == "the quick brown fox", (
            "corrected_text column must contain the corrected content"
        )

        # Verify ILIKE on corrected_text finds the segment
        # This mirrors the search router's or_(text.ilike(...), corrected_text.ilike(...))
        ilike_result = await db_session.execute(
            select(TranscriptSegmentDB).where(
                or_(
                    TranscriptSegmentDB.text.ilike("%the quick brown%"),
                    TranscriptSegmentDB.corrected_text.ilike("%the quick brown%"),
                )
            )
        )
        found_segments = list(ilike_result.scalars().all())
        found_ids = [s.id for s in found_segments]
        assert segment_id in found_ids, (
            "GAP-2: ILIKE search on corrected_text must find the segment "
            f"(segment_id={segment_id} not found in {found_ids})"
        )

        # Verify that searching for the ORIGINAL (misspelled) text also works
        ilike_original = await db_session.execute(
            select(TranscriptSegmentDB).where(
                or_(
                    TranscriptSegmentDB.text.ilike("%teh quick%"),
                    TranscriptSegmentDB.corrected_text.ilike("%teh quick%"),
                )
            )
        )
        found_original = list(ilike_original.scalars().all())
        found_original_ids = [s.id for s in found_original]
        assert segment_id in found_original_ids, (
            "Search must also find the segment by its original (uncorrected) text"
        )


# ---------------------------------------------------------------------------
# GAP-3 / GAP-4 / GAP-5: Downstream consumer integration
# ---------------------------------------------------------------------------


class TestDownstreamConsumerIntegration:
    """
    Integration tests validating that downstream consumers (SRT export,
    transcript segments API, transcript metadata) correctly surface
    corrected text after apply_correction.

    Closes GAP-3 (SRT export), GAP-4 (API inline ternary), and GAP-5
    (transcript metadata) from the Feature 033 cross-feature data contract
    audit.
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
    def service(
        self,
        correction_repo: TranscriptCorrectionRepository,
        segment_repo: TranscriptSegmentRepository,
        transcript_repo: VideoTranscriptRepository,
    ) -> object:
        from chronovista.services.transcript_correction_service import (
            TranscriptCorrectionService,
        )

        return TranscriptCorrectionService(
            correction_repo=correction_repo,
            segment_repo=segment_repo,
            transcript_repo=transcript_repo,
        )

    async def test_srt_export_uses_corrected_text(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        GAP-3: format_segment_srt uses segment.display_text, which must
        return corrected_text after apply_correction. The SRT output
        must contain the corrected text, not the original.

        Steps:
        1. Seed a segment and apply a correction
        2. Reload the segment, convert to Pydantic model
        3. Call format_segment_srt(segment, sequence=1)
        4. Assert the SRT output contains the corrected text
        """
        from chronovista.services.segment_service import format_segment_srt

        video_id = "srtExprtGp3"
        language_code = "en"
        original_text = "teh cat sat on teh mat"
        corrected_text = "the cat sat on the mat"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text=original_text,
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply correction
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text=corrected_text,
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Reload segment and convert to Pydantic model
        segment_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == segment_id)
        )
        db_seg = segment_result.scalar_one()
        pydantic_seg = TranscriptSegment.model_validate(db_seg)

        # Format as SRT
        srt_output = format_segment_srt(pydantic_seg, sequence=1)

        assert corrected_text in srt_output, (
            "GAP-3: SRT output must contain the corrected text "
            f"'{corrected_text}', got:\n{srt_output}"
        )
        assert original_text not in srt_output, (
            "GAP-3: SRT output must NOT contain the original uncorrected text "
            f"'{original_text}', got:\n{srt_output}"
        )
        # Verify SRT structure: sequence number, timestamps, and text
        assert srt_output.startswith("1\n"), (
            "SRT output must start with the sequence number"
        )
        assert "-->" in srt_output, (
            "SRT output must contain the timestamp arrow separator"
        )

    async def test_api_inline_ternary_returns_corrected_text(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        GAP-4: The transcript segments API endpoint (transcripts.py:303)
        uses an inline ternary:
            seg.corrected_text if seg.has_correction and seg.corrected_text else seg.text
        This test verifies that logic returns the corrected text.

        Steps:
        1. Seed a segment with a correction
        2. Read the segment from DB (ORM object)
        3. Simulate the inline ternary logic
        4. Assert the result is the corrected text
        """
        video_id = "apiTernGap4"
        language_code = "en"
        original_text = "wrold peace"
        corrected_text = "world peace"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text=original_text,
            sequence_number=0,
        )
        segment_id = segment.id

        # Apply correction
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text=corrected_text,
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Read the ORM object (as the API does)
        segment_result = await db_session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == segment_id)
        )
        seg = segment_result.scalar_one()

        # Simulate the exact inline ternary from transcripts.py:303
        display = (
            seg.corrected_text
            if seg.has_correction and seg.corrected_text
            else seg.text
        )

        assert display == corrected_text, (
            "GAP-4: The API inline ternary must return the corrected text "
            f"'{corrected_text}', got '{display}'"
        )

        # Also verify the uncorrected path (for completeness)
        # A segment without corrections should return the raw text
        uncorrected_segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="no corrections here",
            sequence_number=1,
        )
        await db_session.flush()

        uncorrected_result = await db_session.execute(
            select(TranscriptSegmentDB).where(
                TranscriptSegmentDB.id == uncorrected_segment.id
            )
        )
        uncorr_seg = uncorrected_result.scalar_one()

        uncorrected_display = (
            uncorr_seg.corrected_text
            if uncorr_seg.has_correction and uncorr_seg.corrected_text
            else uncorr_seg.text
        )
        assert uncorrected_display == "no corrections here", (
            "Uncorrected segment must return raw text from the API ternary"
        )

    async def test_transcript_metadata_after_correction(
        self,
        db_session: AsyncSession,
        service: object,
    ) -> None:
        """
        GAP-5: After apply_correction, the transcript ORM object must have
        has_corrections, correction_count, and last_corrected_at set correctly
        — confirming these fields would be available for API serialization.

        Steps:
        1. Seed a transcript and segment
        2. Apply a correction via the service
        3. Reload the transcript from DB
        4. Assert has_corrections, correction_count, and last_corrected_at
        """
        video_id = "metaGap5VID"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)
        segment = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="original text for metadata test",
            sequence_number=0,
        )

        # Apply correction
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment.id,
            corrected_text="corrected text for metadata test",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Reload transcript from DB
        transcript_result = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        transcript = transcript_result.scalar_one()

        # Assert metadata fields are set correctly
        assert transcript.has_corrections is True, (
            "GAP-5: has_corrections must be True after apply_correction"
        )
        assert transcript.correction_count == 1, (
            "GAP-5: correction_count must be 1 after one apply_correction call, "
            f"got {transcript.correction_count}"
        )
        assert transcript.last_corrected_at is not None, (
            "GAP-5: last_corrected_at must be set after apply_correction"
        )

        # Verify the fields are accessible attributes on the ORM object
        # (confirming they'd be available for API serialization)
        assert hasattr(transcript, "has_corrections"), (
            "ORM object must have has_corrections attribute for API serialization"
        )
        assert hasattr(transcript, "correction_count"), (
            "ORM object must have correction_count attribute for API serialization"
        )
        assert hasattr(transcript, "last_corrected_at"), (
            "ORM object must have last_corrected_at attribute for API serialization"
        )

        # Apply a second correction to another segment and verify count increments
        segment_b = await _seed_segment(
            db_session,
            video_id=video_id,
            language_code=language_code,
            text="second segment text",
            sequence_number=1,
        )
        await service.apply_correction(  # type: ignore[attr-defined]
            db_session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_b.id,
            corrected_text="second segment corrected",
            correction_type=CorrectionType.SPELLING,
        )
        await db_session.flush()

        # Reload and verify incremented count
        transcript_result_2 = await db_session.execute(
            select(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == video_id,
                VideoTranscriptDB.language_code == language_code,
            )
        )
        transcript_2 = transcript_result_2.scalar_one()
        assert transcript_2.correction_count == 2, (
            "GAP-5: correction_count must be 2 after two apply_correction calls, "
            f"got {transcript_2.correction_count}"
        )
