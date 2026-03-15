"""
Transcript correction service for applying and auditing corrections.

Orchestrates the apply_correction workflow: validates the segment, creates
an append-only audit record, updates the segment's corrected text, and
updates transcript-level correction metadata.  All mutations use
``session.flush()`` only — the caller owns the transaction lifecycle
(same flush-only pattern as ``TagManagementService``).

Feature 033 — Transcript Corrections Audit
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.enums import CorrectionType
from chronovista.models.transcript_correction import TranscriptCorrectionCreate
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)

logger = logging.getLogger(__name__)


class TranscriptCorrectionService:
    """
    Service for applying transcript corrections with full audit trail.

    All operations follow the flush-only pattern: ``session.flush()`` is
    called after each mutation step, but ``session.commit()`` and
    ``session.rollback()`` are never called.  The caller is responsible
    for managing the transaction lifecycle.

    Parameters
    ----------
    correction_repo : TranscriptCorrectionRepository
        Repository for transcript correction audit records.
    segment_repo : TranscriptSegmentRepository
        Repository for transcript segment lookups.
    transcript_repo : VideoTranscriptRepository
        Repository for transcript metadata updates.
    """

    def __init__(
        self,
        correction_repo: TranscriptCorrectionRepository,
        segment_repo: TranscriptSegmentRepository,
        transcript_repo: VideoTranscriptRepository,
    ) -> None:
        self._correction_repo = correction_repo
        self._segment_repo = segment_repo
        self._transcript_repo = transcript_repo

    async def apply_correction(
        self,
        session: AsyncSession,
        *,
        video_id: str,
        language_code: str,
        segment_id: int,
        corrected_text: str,
        correction_type: CorrectionType,
        correction_note: str | None = None,
        corrected_by_user_id: str | None = None,
        batch_id: uuid.UUID | None = None,
    ) -> TranscriptCorrectionDB:
        """
        Apply a correction to a transcript segment.

        Creates an append-only audit record, updates the segment's corrected
        text, and updates transcript-level correction metadata.  All mutations
        are flushed within the caller's transaction.

        Parameters
        ----------
        session : AsyncSession
            Database session (caller manages transaction).
        video_id : str
            YouTube video ID.
        language_code : str
            BCP-47 language code.
        segment_id : int
            Primary key of the transcript segment to correct.
        corrected_text : str
            The new corrected text for the segment.
        correction_type : CorrectionType
            Category of the correction.
        correction_note : str | None, optional
            Human-readable explanation for the correction.
        corrected_by_user_id : str | None, optional
            Identifier of the user who made the correction.
        batch_id : uuid.UUID or None, optional
            UUIDv7 batch identifier for provenance tracking.

        Returns
        -------
        TranscriptCorrectionDB
            The created transcript correction audit record.

        Raises
        ------
        ValueError
            If the segment does not exist.
        ValueError
            If ``corrected_text`` is identical to the segment's current
            effective text (no-op prevention).
        """
        # Step 1: Get segment — raise ValueError if not found
        segment = await self._segment_repo.get(session, segment_id)
        if segment is None:
            raise ValueError(
                f"Transcript segment with id={segment_id} not found"
            )

        # Step 2: Determine effective text
        effective_text: str = (
            segment.corrected_text if segment.has_correction else segment.text
        ) or ""

        # Step 3: No-op prevention
        if corrected_text == effective_text:
            raise ValueError(
                f"corrected_text is identical to the segment's current "
                f"effective text — no-op corrections are not permitted"
            )

        # Step 4: Get latest version (acquires FOR UPDATE lock)
        latest_version = await self._correction_repo.get_latest_version(
            session, video_id, language_code, segment_id
        )
        new_version = latest_version + 1

        # Step 5: Create audit record
        create_model = TranscriptCorrectionCreate(
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            correction_type=correction_type,
            original_text=effective_text,
            corrected_text=corrected_text,
            correction_note=correction_note,
            corrected_by_user_id=corrected_by_user_id,
            version_number=new_version,
            batch_id=batch_id,
        )

        # Step 6: Persist audit record via repo (this flushes internally)
        correction_record = await self._correction_repo.create(
            session, obj_in=create_model
        )

        # Step 7: Update segment
        segment.corrected_text = corrected_text
        segment.has_correction = True
        await session.flush()

        # Step 8-9: Update transcript metadata
        transcript = await self._transcript_repo.get(
            session, (video_id, language_code)
        )
        if transcript is not None:
            transcript.has_corrections = True
            transcript.correction_count = transcript.correction_count + 1
            transcript.last_corrected_at = datetime.now(tz=timezone.utc)
            await session.flush()

        # Step 10: Emit structured INFO log (NFR-006)
        logger.info(
            "Correction applied: video_id=%s, language_code=%s, "
            "segment_id=%s, correction_type=%s, version_number=%d, "
            "corrected_by_user_id=%s",
            video_id,
            language_code,
            segment_id,
            correction_type.value if isinstance(correction_type, CorrectionType) else correction_type,
            new_version,
            corrected_by_user_id,
        )

        # Step 10.5: B-lite hook — auto-record ASR error alias if correction matches entity
        await self._record_asr_alias_if_entity_match(
            session,
            original_text=effective_text,
            corrected_text=corrected_text,
        )

        # Step 11: Return created record
        return correction_record

    async def revert_correction(
        self,
        session: AsyncSession,
        *,
        segment_id: int,
    ) -> TranscriptCorrectionDB:
        """
        Revert the latest correction applied to a transcript segment.

        Creates an append-only revert audit record, restores the segment to
        its previous state, and updates transcript-level correction metadata.
        All mutations are flushed within the caller's transaction.

        The revert semantics are:
        - Fetch V_N (the latest audit record by version_number).
        - If V_N.version_number == 1: restore segment to its original
          uncorrected state (corrected_text=None, has_correction=False).
        - If V_N.version_number > 1: restore segment to V_N.original_text
          (the text immediately prior to that correction), has_correction=True.
        - In both cases create a new audit record with correction_type='revert'.

        Transcript metadata is updated per the revert type:
        - Revert-to-original: decrement correction_count, recompute
          has_corrections via EXISTS scan (FR-014a, FR-014b).
        - Revert-to-prior-version: correction_count unchanged,
          has_corrections remains True.
        - last_corrected_at is always updated (FR-014c).

        Parameters
        ----------
        session : AsyncSession
            Database session (caller manages transaction).
        segment_id : int
            Primary key of the transcript segment to revert.

        Returns
        -------
        TranscriptCorrectionDB
            The created revert audit record.

        Raises
        ------
        ValueError
            If the segment does not exist or has no active correction
            (segment.has_correction is False).
        """
        # Step 1: Get segment — raise ValueError if not found or has_correction=False
        segment = await self._segment_repo.get(session, segment_id)
        if segment is None:
            raise ValueError(
                f"Transcript segment with id={segment_id} not found"
            )
        if not segment.has_correction:
            raise ValueError(
                f"Transcript segment with id={segment_id} has no active "
                f"correction to revert (has_correction=False)"
            )

        # Step 2: Fetch V_N — the latest audit record (highest version_number)
        latest_records = await self._correction_repo.get_by_segment(
            session,
            segment.video_id,
            segment.language_code,
            segment_id,
            limit=1,
        )
        if not latest_records:
            raise ValueError(
                f"Transcript segment with id={segment_id} has has_correction=True "
                f"but no audit records were found — data integrity violation"
            )
        v_n = latest_records[0]

        # Determine revert type:
        # version_number == 1 → revert to original (segment becomes uncorrected)
        # version_number > 1  → revert to prior correction (segment keeps correction)
        is_revert_to_original = v_n.version_number == 1

        # Step 3: Create revert audit record
        # original_text = what the segment had BEFORE this revert (V_N.corrected_text)
        # corrected_text = what the segment will be restored TO (V_N.original_text)
        revert_version = v_n.version_number + 1
        revert_create = TranscriptCorrectionCreate(
            video_id=segment.video_id,
            language_code=segment.language_code,
            segment_id=segment_id,
            correction_type=CorrectionType.REVERT,
            original_text=v_n.corrected_text,
            corrected_text=v_n.original_text,
            version_number=revert_version,
            correction_note=None,
            corrected_by_user_id=None,
        )
        revert_record = await self._correction_repo.create(
            session, obj_in=revert_create
        )

        # Step 4 / 5: Update segment based on revert type
        if is_revert_to_original:
            # Full revert: segment returns to its original uncorrected state
            segment.corrected_text = None
            segment.has_correction = False
        else:
            # Partial revert: restore to the text that was current before V_N
            segment.corrected_text = v_n.original_text
            # has_correction remains True (the segment is still corrected)

        await session.flush()

        # Step 6: Update transcript metadata
        transcript = await self._transcript_repo.get(
            session, (segment.video_id, segment.language_code)
        )
        if transcript is not None:
            # FR-014c: a revert is always a correction event
            transcript.last_corrected_at = datetime.now(tz=timezone.utc)

            if is_revert_to_original:
                # FR-014a: decrement correction_count (one fewer active correction)
                transcript.correction_count = max(0, transcript.correction_count - 1)

                # FR-014b: recompute has_corrections by scanning remaining segments
                # Uses EXISTS so we stop at the first corrected segment (efficient)
                exists_stmt = select(
                    exists().where(
                        TranscriptSegmentDB.video_id == segment.video_id,
                        TranscriptSegmentDB.language_code == segment.language_code,
                        TranscriptSegmentDB.has_correction.is_(True),
                    )
                )
                result = await session.execute(exists_stmt)
                transcript.has_corrections = bool(result.scalar_one())
            # else: revert-to-prior — correction_count and has_corrections unchanged

            await session.flush()

        # Step 7: Emit structured INFO log (NFR-006)
        logger.info(
            "Correction reverted: segment_id=%s, video_id=%s, language_code=%s, "
            "reverted_version_number=%d, revert_version_number=%d, "
            "revert_type=%s",
            segment_id,
            segment.video_id,
            segment.language_code,
            v_n.version_number,
            revert_version,
            "revert_to_original" if is_revert_to_original else "revert_to_prior",
        )

        # Step 8: Return the revert audit record
        return revert_record


    async def _record_asr_alias_if_entity_match(
        self,
        session: AsyncSession,
        *,
        original_text: str,
        corrected_text: str,
    ) -> None:
        """Best-effort hook: auto-record ASR error alias when correction matches an entity.

        Delegates to :func:`~chronovista.services.asr_alias_registry.register_asr_alias`.
        """
        from chronovista.services.asr_alias_registry import register_asr_alias

        await register_asr_alias(
            session,
            original_text=original_text,
            corrected_text=corrected_text,
            occurrence_count=1,
            commit=False,
            log_prefix="B-lite",
        )


__all__ = ["TranscriptCorrectionService"]
