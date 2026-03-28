"""
Integration tests for the backfill_batch_ids script (Feature 045).

Uses a real PostgreSQL test database (via the ``db_session`` fixture from
``tests/integration/conftest.py``) to verify the full end-to-end flow of
the batch-ID backfill process:

  insert corrections → run fetch + identify → assign batch IDs → verify DB state

Database URL defaults to:
  postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test

Override with DATABASE_INTEGRATION_URL or CHRONOVISTA_INTEGRATION_DB_URL env var.

Tests in this module validate:
  - T020 [US2]: End-to-end backfill of batch_id values
  - Idempotency: re-running leaves already-assigned rows unchanged
  - Mixed data: singletons stay NULL, multi-correction groups receive batch_id

Feature 045 — Correction Intelligence Pipeline
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.enums import CorrectionType
from scripts.utilities.backfill_batch_ids import (
    assign_batch_id,
    fetch_unassigned_corrections,
)
from scripts.utilities.backfill_batch_ids import (
    identify_batches_by_text as identify_batches,
)

# ---------------------------------------------------------------------------
# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DB seed helpers
# ---------------------------------------------------------------------------


async def _seed_video(
    session: AsyncSession,
    video_id: str = "backfillV01",
) -> VideoDB:
    """Insert a minimal Video row to satisfy transcript FK constraints.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    video_id : str
        YouTube video ID string (max 20 chars).

    Returns
    -------
    VideoDB
        The persisted Video ORM instance.
    """
    video = VideoDB(
        video_id=video_id,
        title="Backfill Integration Test Video",
        upload_date=datetime(2020, 6, 1, tzinfo=UTC),
        duration=600,
    )
    session.add(video)
    await session.flush()
    return video


async def _seed_transcript(
    session: AsyncSession,
    video_id: str = "backfillV01",
    language_code: str = "en",
) -> VideoTranscriptDB:
    """Insert a VideoTranscript row required by the corrections FK.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    video_id : str
        Parent video's ID.
    language_code : str
        Language code for the transcript (e.g. "en").

    Returns
    -------
    VideoTranscriptDB
        The persisted VideoTranscript ORM instance.
    """
    transcript = VideoTranscriptDB(
        video_id=video_id,
        language_code=language_code,
        transcript_text="backfill integration test transcript",
        transcript_type="manual",
        download_reason="user_request",
        is_cc=False,
        is_auto_synced=False,
        track_kind="standard",
        source="youtube_transcript_api",
        has_corrections=False,
        correction_count=0,
        last_corrected_at=None,
    )
    session.add(transcript)
    await session.flush()
    return transcript


async def _seed_correction(
    session: AsyncSession,
    video_id: str = "backfillV01",
    language_code: str = "en",
    original_text: str = "teh quick brown fox",
    corrected_text: str = "the quick brown fox",
    corrected_by_user_id: str | None = "cli",
    corrected_at: datetime | None = None,
    batch_id: uuid.UUID | None = None,
    version_number: int = 1,
) -> TranscriptCorrectionDB:
    """Insert a TranscriptCorrection row for backfill testing.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    video_id : str
        Parent video's ID.
    language_code : str
        Parent transcript's language code.
    original_text : str
        The text before the correction.
    corrected_text : str
        The text after the correction.
    corrected_by_user_id : str | None
        Actor string; None represents anonymous corrections.
    corrected_at : datetime | None
        Timestamp of the correction; defaults to ``2024-03-01T12:00:00Z``.
    batch_id : uuid.UUID | None
        Pre-existing batch_id; None means the row is unassigned (the common
        case for backfill testing).
    version_number : int
        Monotonically increasing correction chain version.

    Returns
    -------
    TranscriptCorrectionDB
        The persisted TranscriptCorrection ORM instance.
    """
    if corrected_at is None:
        corrected_at = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)

    correction = TranscriptCorrectionDB(
        video_id=video_id,
        language_code=language_code,
        correction_type=CorrectionType.SPELLING.value,
        original_text=original_text,
        corrected_text=corrected_text,
        corrected_by_user_id=corrected_by_user_id,
        corrected_at=corrected_at,
        version_number=version_number,
        batch_id=batch_id,
    )
    session.add(correction)
    await session.flush()
    return correction


def _ts(seconds_offset: float) -> datetime:
    """Return a UTC datetime offset from a fixed anchor by ``seconds_offset``.

    Parameters
    ----------
    seconds_offset : float
        Offset in seconds from ``2024-03-01T12:00:00Z``.

    Returns
    -------
    datetime
        Anchor time plus the given offset.
    """
    base = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)
    return base + timedelta(seconds=seconds_offset)


# ---------------------------------------------------------------------------
# T020: End-to-end backfill scenario
# ---------------------------------------------------------------------------


class TestBackfillEndToEnd:
    """
    End-to-end integration tests for the backfill_batch_ids script functions.

    Each test uses ``db_session`` from ``tests/integration/conftest.py`` which
    creates all tables fresh, yields the session, then rolls back and drops
    all tables for full isolation between tests.
    """

    # ------------------------------------------------------------------
    # 1. Insert corrections, run backfill, verify batch_id assignments
    # ------------------------------------------------------------------

    async def test_two_corrections_in_window_receive_same_batch_id(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Two corrections sharing the same (user, original_text, corrected_text)
        within the 5s window must both receive a non-NULL batch_id, and that
        batch_id must be the same UUID for both rows.
        """
        video_id = "e2eBackf001"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        corr_a = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(0),
            version_number=1,
        )
        corr_b = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(3),  # 3s gap < 5s window
            version_number=2,
        )

        # --- run the backfill logic ---
        corrections = await fetch_unassigned_corrections(db_session)
        assert len(corrections) == 2

        batches = identify_batches(corrections, window_seconds=5.0)
        assert len(batches) == 1

        batch_uuid = uuid.uuid4()
        await assign_batch_id(db_session, batches[0].correction_ids, batch_uuid)

        # --- verify DB state ---
        result_a = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == corr_a.id
            )
        )
        result_b = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == corr_b.id
            )
        )
        persisted_a = result_a.scalar_one()
        persisted_b = result_b.scalar_one()

        assert persisted_a.batch_id is not None, "corr_a must have a batch_id assigned"
        assert persisted_b.batch_id is not None, "corr_b must have a batch_id assigned"
        assert persisted_a.batch_id == persisted_b.batch_id, (
            "Both corrections in the same window must share the same batch_id"
        )
        assert persisted_a.batch_id == batch_uuid

    async def test_singleton_correction_remains_null(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        A correction in a group of size 1 must NOT receive a batch_id.
        ``identify_batches`` returns only groups with 2+ members.
        """
        video_id = "e2eSingle01"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        corr = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="unique text only once",
            corrected_text="unique corrected text",
            corrected_by_user_id="cli",
            corrected_at=_ts(0),
        )

        corrections = await fetch_unassigned_corrections(db_session)
        assert len(corrections) == 1

        batches = identify_batches(corrections, window_seconds=5.0)
        assert batches == [], "Singleton group must produce no batches"

        # No assign_batch_id call → row remains NULL
        result = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == corr.id
            )
        )
        persisted = result.scalar_one()
        assert persisted.batch_id is None, "Singleton correction must stay NULL"

    async def test_gap_exceeds_window_corrections_stay_null(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Two corrections in the same group but separated by more than the window
        must each remain in their own sub-window of size 1 → both stay NULL.
        """
        video_id = "e2eGap00001"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        corr_a = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(0),
        )
        corr_b = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(60),  # 60s gap >> 5s window → split
        )

        corrections = await fetch_unassigned_corrections(db_session)
        batches = identify_batches(corrections, window_seconds=5.0)

        # Each sub-window has 1 correction → no batches
        assert batches == []

        # Neither correction should have a batch_id
        result_a = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == corr_a.id
            )
        )
        result_b = await db_session.execute(
            select(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.id == corr_b.id
            )
        )
        assert result_a.scalar_one().batch_id is None
        assert result_b.scalar_one().batch_id is None

    # ------------------------------------------------------------------
    # 2. Idempotency: re-run leaves already-assigned rows unchanged
    # ------------------------------------------------------------------

    async def test_second_run_does_not_reassign_existing_batch_ids(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        After the first backfill assigns a batch_id, a second fetch must
        return 0 unassigned corrections (they are already assigned).
        ``identify_batches`` then returns [] → no further assigns.
        """
        video_id = "e2eIdem0001"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(0),
        )
        await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(2),
        )

        # --- First run ---
        corrections_run1 = await fetch_unassigned_corrections(db_session)
        assert len(corrections_run1) == 2
        batches_run1 = identify_batches(corrections_run1, window_seconds=5.0)
        assert len(batches_run1) == 1

        first_batch_id = uuid.uuid4()
        await assign_batch_id(db_session, batches_run1[0].correction_ids, first_batch_id)

        # --- Second run ---
        corrections_run2 = await fetch_unassigned_corrections(db_session)
        assert len(corrections_run2) == 0, (
            "Second fetch must return 0 rows: all already have batch_id"
        )

        batches_run2 = identify_batches(corrections_run2, window_seconds=5.0)
        assert batches_run2 == [], "No new batches on second run"

    async def test_second_run_preserves_first_run_batch_ids(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        After first backfill, the batch_ids assigned in run 1 must remain
        unchanged on the rows after a simulated second run.
        """
        video_id = "e2eIdem0002"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        corr_a = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(0),
        )
        corr_b = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(1),
        )

        # First run
        corrections = await fetch_unassigned_corrections(db_session)
        batches = identify_batches(corrections, window_seconds=5.0)
        assert len(batches) == 1

        first_batch_id = uuid.uuid4()
        await assign_batch_id(db_session, batches[0].correction_ids, first_batch_id)

        # Second run (no-op)
        corrections_run2 = await fetch_unassigned_corrections(db_session)
        assert len(corrections_run2) == 0

        # Verify original batch_ids are still intact
        result_a = await db_session.execute(
            select(TranscriptCorrectionDB).where(TranscriptCorrectionDB.id == corr_a.id)
        )
        result_b = await db_session.execute(
            select(TranscriptCorrectionDB).where(TranscriptCorrectionDB.id == corr_b.id)
        )
        assert result_a.scalar_one().batch_id == first_batch_id
        assert result_b.scalar_one().batch_id == first_batch_id

    async def test_pre_assigned_rows_excluded_from_fetch(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Corrections that already have batch_id set must not appear in the fetch
        result, even when other unassigned corrections exist in the same table.
        """
        video_id = "e2ePreAssn1"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        existing_batch = uuid.uuid4()

        # Row already assigned (must be skipped by fetch)
        await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="already grouped text",
            corrected_text="already grouped correction",
            corrected_by_user_id="cli",
            corrected_at=_ts(0),
            batch_id=existing_batch,
        )

        # Unassigned row (must appear in fetch)
        corr_unassigned = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="new unassigned text",
            corrected_text="new unassigned correction",
            corrected_by_user_id="cli",
            corrected_at=_ts(5),
        )

        corrections = await fetch_unassigned_corrections(db_session)

        assert len(corrections) == 1, (
            "Only unassigned corrections must be returned"
        )
        assert corrections[0].id == str(corr_unassigned.id)

    # ------------------------------------------------------------------
    # 3. Mixed data: singletons stay NULL, batches get assigned
    # ------------------------------------------------------------------

    async def test_mixed_singletons_and_batches(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Insert a mix of:
          - 2 corrections forming a valid batch (same key, within window)
          - 1 singleton correction (unique text, no partner)

        After backfill:
          - Batch pair has a shared non-NULL batch_id.
          - Singleton remains NULL.
        """
        video_id = "e2eMixed001"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        # Pair that forms a batch
        pair_a = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(0),
            version_number=1,
        )
        pair_b = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(2),
            version_number=2,
        )

        # Singleton (unique text, no partner)
        singleton = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="unique correction that stands alone",
            corrected_text="unique corrected result that stands alone",
            corrected_by_user_id="cli",
            corrected_at=_ts(0),
            version_number=3,
        )

        # Run backfill
        corrections = await fetch_unassigned_corrections(db_session)
        assert len(corrections) == 3

        batches = identify_batches(corrections, window_seconds=5.0)
        assert len(batches) == 1, "Only the pair should form a batch"

        batch_uuid = uuid.uuid4()
        await assign_batch_id(db_session, batches[0].correction_ids, batch_uuid)

        # Verify pair has batch_id
        res_a = await db_session.execute(
            select(TranscriptCorrectionDB).where(TranscriptCorrectionDB.id == pair_a.id)
        )
        res_b = await db_session.execute(
            select(TranscriptCorrectionDB).where(TranscriptCorrectionDB.id == pair_b.id)
        )
        res_s = await db_session.execute(
            select(TranscriptCorrectionDB).where(TranscriptCorrectionDB.id == singleton.id)
        )

        persisted_a = res_a.scalar_one()
        persisted_b = res_b.scalar_one()
        persisted_s = res_s.scalar_one()

        assert persisted_a.batch_id == batch_uuid, "pair_a must have batch_id assigned"
        assert persisted_b.batch_id == batch_uuid, "pair_b must have batch_id assigned"
        assert persisted_s.batch_id is None, "Singleton must remain NULL"

    async def test_two_separate_groups_each_with_pair(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Two distinct correction groups each with a pair must each receive
        different batch_ids, while rows within each group share the same id.
        """
        video_id = "e2eTwoGrp01"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        # Group 1: teh → the
        g1_a = await _seed_correction(
            db_session, video_id=video_id, language_code=language_code,
            original_text="teh", corrected_text="the",
            corrected_by_user_id="cli", corrected_at=_ts(0), version_number=1,
        )
        g1_b = await _seed_correction(
            db_session, video_id=video_id, language_code=language_code,
            original_text="teh", corrected_text="the",
            corrected_by_user_id="cli", corrected_at=_ts(2), version_number=2,
        )

        # Group 2: recieve → receive
        g2_a = await _seed_correction(
            db_session, video_id=video_id, language_code=language_code,
            original_text="recieve", corrected_text="receive",
            corrected_by_user_id="cli", corrected_at=_ts(10), version_number=3,
        )
        g2_b = await _seed_correction(
            db_session, video_id=video_id, language_code=language_code,
            original_text="recieve", corrected_text="receive",
            corrected_by_user_id="cli", corrected_at=_ts(12), version_number=4,
        )

        corrections = await fetch_unassigned_corrections(db_session)
        assert len(corrections) == 4

        batches = identify_batches(corrections, window_seconds=5.0)
        assert len(batches) == 2

        batch_id_1 = uuid.uuid4()
        batch_id_2 = uuid.uuid4()

        await assign_batch_id(db_session, batches[0].correction_ids, batch_id_1)
        await assign_batch_id(db_session, batches[1].correction_ids, batch_id_2)

        # Reload all 4 corrections
        rows = {}
        for corr_obj in [g1_a, g1_b, g2_a, g2_b]:
            res = await db_session.execute(
                select(TranscriptCorrectionDB).where(
                    TranscriptCorrectionDB.id == corr_obj.id
                )
            )
            rows[str(corr_obj.id)] = res.scalar_one()

        # Each pair within its group must share a batch_id
        assert rows[str(g1_a.id)].batch_id == rows[str(g1_b.id)].batch_id
        assert rows[str(g2_a.id)].batch_id == rows[str(g2_b.id)].batch_id

        # The two groups must have different batch_ids
        assert rows[str(g1_a.id)].batch_id != rows[str(g2_a.id)].batch_id

        # All four must be non-NULL
        for corr_id, row in rows.items():
            assert row.batch_id is not None, f"Row {corr_id} must have a batch_id"

    async def test_null_user_id_corrections_grouped_together(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Corrections with NULL corrected_by_user_id and matching text/replacement
        must form a batch just like non-NULL users do.
        """
        video_id = "e2eNullUsr1"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        null_a = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="seperate",
            corrected_text="separate",
            corrected_by_user_id=None,
            corrected_at=_ts(0),
            version_number=1,
        )
        null_b = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="seperate",
            corrected_text="separate",
            corrected_by_user_id=None,
            corrected_at=_ts(3),
            version_number=2,
        )

        corrections = await fetch_unassigned_corrections(db_session)
        batches = identify_batches(corrections, window_seconds=5.0)
        assert len(batches) == 1

        batch_uuid = uuid.uuid4()
        await assign_batch_id(db_session, batches[0].correction_ids, batch_uuid)

        res_a = await db_session.execute(
            select(TranscriptCorrectionDB).where(TranscriptCorrectionDB.id == null_a.id)
        )
        res_b = await db_session.execute(
            select(TranscriptCorrectionDB).where(TranscriptCorrectionDB.id == null_b.id)
        )

        assert res_a.scalar_one().batch_id == batch_uuid
        assert res_b.scalar_one().batch_id == batch_uuid

    async def test_fetch_excludes_empty_text_corrections(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        The SQL query filters out rows where original_text or corrected_text
        is empty or NULL.  We verify by inserting such rows and confirming
        they do not appear in the fetch result.

        Note: The DB schema has original_text/corrected_text as NOT NULL (Text),
        so we can only test the empty-string case here.
        """
        video_id = "e2eEmptyTxt"
        language_code = "en"

        await _seed_video(db_session, video_id=video_id)
        await _seed_transcript(db_session, video_id=video_id, language_code=language_code)

        # Valid row — must be included
        valid_corr = await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(0),
        )

        # Row with empty original_text — must be excluded
        await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="",
            corrected_text="the",
            corrected_by_user_id="cli",
            corrected_at=_ts(1),
            version_number=2,
        )

        # Row with empty corrected_text — must be excluded
        await _seed_correction(
            db_session,
            video_id=video_id,
            language_code=language_code,
            original_text="teh",
            corrected_text="",
            corrected_by_user_id="cli",
            corrected_at=_ts(2),
            version_number=3,
        )

        corrections = await fetch_unassigned_corrections(db_session)

        assert len(corrections) == 1, (
            "Only the valid correction must be returned; empty-text rows must be excluded"
        )
        assert corrections[0].id == str(valid_corr.id)
