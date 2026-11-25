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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.enums import SCAN_DETECTION_METHODS, CorrectionType
from chronovista.models.transcript_correction import TranscriptCorrectionCreate
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
    MentionMove,
    MentionRelabel,
    MentionSpan,
)
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)
from chronovista.services.mention_offset_rebase import TextEdit, word_bounded
from chronovista.services.transcript_text_index import TranscriptTextIndex

if TYPE_CHECKING:
    from chronovista.services.entity_mention_scan_service import (
        EntityMentionScanService,
        TextMatch,
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
            raise ValueError(f"Transcript segment with id={segment_id} not found")

        # Step 2: Determine effective text
        effective_text: str = (
            segment.corrected_text if segment.has_correction else segment.text
        ) or ""

        # Step 3: No-op prevention
        if corrected_text == effective_text:
            raise ValueError(
                "corrected_text is identical to the segment's current "
                "effective text — no-op corrections are not permitted"
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

        # Step 7: Update segment, and move its mentions with the text (#426)
        segment.corrected_text = corrected_text
        segment.has_correction = True
        await session.flush()
        await self._rebase_segment_mentions(
            session,
            segment_id=segment_id,
            video_id=video_id,
            language_code=language_code,
            old_text=effective_text,
            new_text=corrected_text,
        )

        # Step 8-9: Update transcript metadata
        transcript = await self._transcript_repo.get(session, (video_id, language_code))
        if transcript is not None:
            transcript.has_corrections = True
            transcript.correction_count = transcript.correction_count + 1
            transcript.last_corrected_at = datetime.now(tz=UTC)
            await session.flush()

        # Step 10: Emit structured INFO log (NFR-006)
        logger.info(
            "Correction applied: video_id=%s, language_code=%s, "
            "segment_id=%s, correction_type=%s, version_number=%d, "
            "corrected_by_user_id=%s",
            video_id,
            language_code,
            segment_id,
            (
                correction_type.value
                if isinstance(correction_type, CorrectionType)
                else correction_type
            ),
            new_version,
            corrected_by_user_id,
        )

        # Step 10.5: B-lite hook — auto-record ASR error alias if correction matches entity
        await self._record_asr_alias_if_entity_match(
            session,
            original_text=effective_text,
            corrected_text=corrected_text,
            video_id=video_id,
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
            raise ValueError(f"Transcript segment with id={segment_id} not found")
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
        text_before_revert: str = (
            segment.corrected_text if segment.has_correction else segment.text
        ) or ""
        if is_revert_to_original:
            # Full revert: segment returns to its original uncorrected state
            segment.corrected_text = None
            segment.has_correction = False
        else:
            # Partial revert: restore to the text that was current before V_N
            segment.corrected_text = v_n.original_text
            # has_correction remains True (the segment is still corrected)

        await session.flush()
        await self._rebase_segment_mentions(
            session,
            segment_id=segment_id,
            video_id=segment.video_id,
            language_code=segment.language_code,
            old_text=text_before_revert,
            new_text=(
                segment.corrected_text if segment.has_correction else segment.text
            )
            or "",
        )

        # Step 6: Update transcript metadata
        transcript = await self._transcript_repo.get(
            session, (segment.video_id, segment.language_code)
        )
        if transcript is not None:
            # FR-014c: a revert is always a correction event
            transcript.last_corrected_at = datetime.now(tz=UTC)

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

    async def _rebase_segment_mentions(
        self,
        session: AsyncSession,
        *,
        segment_id: int,
        video_id: str,
        language_code: str,
        old_text: str,
        new_text: str,
    ) -> None:
        """Keep the segment's mentions on their own words through an edit (#426).

        For every transcript mention starting, ending or running through the segment
        that reads correctly before the edit (:meth:`TranscriptTextIndex.mention_reads`):

        - an edit elsewhere moves its offsets;
        - an edit of a scan-owned row's own words re-points it to what those words
          became, when the scan's matching rule
          (:meth:`EntityMentionScanService.detect_in_text`) finds the same entity
          there: fixing a misheard name keeps its mention, now reading as the name. A
          split name is re-pointed only to an occurrence that still runs across the
          same segments;
        - otherwise it is removed: the entity is no longer said there, a correction
          row's asserted words are gone, or the name was glued to a longer word.

        A mention already wrong before the edit is left as it is (a repair is a
        deliberate step), except that it gives way when a correct mention of the same
        entity lands on its start. Two correct mentions of one entity on one start are
        one occurrence; the one kept is decided by :meth:`MentionSpan.survivor_rank`,
        the rule the repair uses too.

        Removing or re-pointing a mention can change which mentions qualify, so the
        scope is invalidated before any delete (the lock order every correction path
        uses) and the entity's counters are recomputed. Moving one cannot: proximity
        records key on segments and their start times, never on character offsets.
        """
        if old_text == new_text:
            return
        mention_repo = EntityMentionRepository()
        spans = await mention_repo.transcript_mention_spans(
            session, segment_ids=[segment_id]
        ) + await mention_repo.spans_crossing_segment(session, segment_id=segment_id)
        if not spans:
            return
        edit = TextEdit(old_text, new_text)
        old_index = TranscriptTextIndex.of([(segment_id, old_text)])

        stale: set[uuid.UUID] = set()
        final: dict[uuid.UUID, tuple[int, int]] = {}
        rewritten: dict[uuid.UUID, tuple[int, int]] = {}
        removed: dict[uuid.UUID, MentionSpan] = {}
        relabels: list[MentionRelabel] = []
        for span in spans:
            if span.end_segment_id is not None:
                outcome, offsets, match = await self._rebase_spanning(
                    mention_repo,
                    session,
                    span=span,
                    segment_id=segment_id,
                    language_code=language_code,
                    old_text=old_text,
                    edit=edit,
                )
                if outcome == "stale":
                    stale.add(span.id)
                elif offsets is None:
                    removed[span.id] = span
                else:
                    final[span.id] = offsets
                    if match is not None:
                        relabels.append(_relabel(span.id, match))
                continue
            if not old_index.mention_reads(
                segment_id=segment_id,
                end_segment_id=None,
                match_start=span.match_start,
                match_end=span.match_end,
                mention_text=span.mention_text,
            ):
                stale.add(span.id)
                continue
            moved = edit.rebase(
                match_start=span.match_start,
                match_end=span.match_end,
                mention_text=span.mention_text,
            )
            if moved is not None:
                final[span.id] = moved
                continue
            # Only a scan-owned row is re-pointed: the scan would re-derive it from the
            # new words. A correction row asserted these exact words; once an edit
            # rewrites them (including reverting its own correction) it goes.
            region = (
                edit.map_region(span.match_start, span.match_end)
                if span.detection_method in SCAN_DETECTION_METHODS
                else None
            )
            if region is None:
                removed[span.id] = span
            else:
                rewritten[span.id] = region

        if rewritten:
            by_id = {span.id: span for span in spans}
            matches = await _detector().detect_in_text(
                session,
                text=new_text,
                language_code=language_code,
                entity_ids=sorted({by_id[i].entity_id for i in rewritten}, key=str),
                segment_id=segment_id,
            )
            for mention_id, region in rewritten.items():
                found = _repointed(matches, by_id[mention_id].entity_id, region)
                if found is None:
                    removed[mention_id] = by_id[mention_id]
                    continue
                final[mention_id] = (found.match_start, found.match_end)
                relabels.append(_relabel(mention_id, found))

        # One mention per (entity, segment, start): a correct mention wins over a
        # stale one on the same start; between correct ones the survivor rank decides.
        holder: dict[tuple[uuid.UUID, int, int], MentionSpan] = {}
        for span in sorted(spans, key=lambda s: s.survivor_rank()):
            if span.id in removed:
                continue
            start = final[span.id][0] if span.id in final else span.match_start
            key = (span.entity_id, span.segment_id, start)
            other = holder.get(key)
            if other is None:
                holder[key] = span
            elif other.id in stale and span.id not in stale:
                removed[other.id] = other
                holder[key] = span
            else:
                removed[span.id] = span
        relabels = [r for r in relabels if r.id not in removed]
        moves = [
            MentionMove(
                id=span.id,
                match_start=final[span.id][0],
                match_end=final[span.id][1],
                start_changed=final[span.id][0] != span.match_start,
            )
            for span in spans
            if span.id in final
            and span.id not in removed
            and final[span.id] != (span.match_start, span.match_end)
        ]

        entity_of = {span.id: span.entity_id for span in spans}
        changed = {span.entity_id for span in removed.values()} | {
            entity_of[r.id] for r in relabels
        }
        if changed:
            await EntityPairProximityRepository().invalidate_proximity_scopes(
                session,
                video_id=video_id,
                language_code=language_code,
                reason="correction",
            )
        # Delete before moving: a moved mention may land on the start a removed one
        # still holds, and the unique index on (entity, segment, start) would reject it.
        if removed:
            await mention_repo.delete_mentions_by_ids(session, list(removed))
        await mention_repo.move_mention_offsets(session, moves)
        await mention_repo.relabel_mentions(session, relabels)
        if changed:
            entity_ids = sorted(changed, key=str)
            await mention_repo.update_entity_counters(session, entity_ids)
            await mention_repo.update_alias_counters(session, entity_ids)
        await session.flush()

    @staticmethod
    async def _rebase_spanning(
        mention_repo: EntityMentionRepository,
        session: AsyncSession,
        *,
        span: MentionSpan,
        segment_id: int,
        language_code: str,
        old_text: str,
        edit: TextEdit,
    ) -> tuple[Literal["stale", "kept"], tuple[int, int] | None, TextMatch | None]:
        """A cross-segment mention through an edit of one of its segments (#426).

        Read across all its segments joined, as the scan assembles them. Returns
        ``("stale", None, None)`` when it did not read before the edit either (left
        for a deliberate repair); ``("kept", offsets, match)`` with its new offsets,
        and the detected match when a scan-owned row was re-pointed; or
        ``("kept", None, None)`` when it is to be removed. The edited segment's new
        text is already flushed.
        """
        assert span.end_segment_id is not None
        texts = await mention_repo.segment_texts(
            session,
            start_segment_id=span.segment_id,
            end_segment_id=span.end_segment_id,
        )
        new_index = TranscriptTextIndex.of(texts)
        old_index = TranscriptTextIndex.of(
            [(sid, old_text if sid == segment_id else text) for sid, text in texts]
        )
        if not old_index.mention_reads(
            segment_id=span.segment_id,
            end_segment_id=span.end_segment_id,
            match_start=span.match_start,
            match_end=span.match_end,
            mention_text=span.mention_text,
        ):
            return "stale", None, None
        start, end = span.match_start, span.match_end
        mapped_start = edit.map_start(start) if span.segment_id == segment_id else start
        mapped_end = edit.map_end(end) if span.end_segment_id == segment_id else end
        if mapped_start is not None and mapped_end is not None:
            reads = new_index.mention_reads(
                segment_id=span.segment_id,
                end_segment_id=span.end_segment_id,
                match_start=mapped_start,
                match_end=mapped_end,
                mention_text=span.mention_text,
            )
            old_at = old_index.locate(
                segment_id=span.segment_id,
                end_segment_id=span.end_segment_id,
                match_start=start,
                match_end=end,
            )
            new_at = new_index.locate(
                segment_id=span.segment_id,
                end_segment_id=span.end_segment_id,
                match_start=mapped_start,
                match_end=mapped_end,
            )
            glued = (
                old_at is not None
                and new_at is not None
                and word_bounded(old_index.text, *old_at)
                and not word_bounded(new_index.text, *new_at)
            )
            if reads and not glued:
                return "kept", (mapped_start, mapped_end), None
        if span.detection_method not in SCAN_DETECTION_METHODS:
            return "kept", None, None
        # A scan-owned split name whose words were rewritten: re-point it to what the
        # scan finds there, if the entity still runs across the same segments.
        matches = await _detector().detect_in_text(
            session,
            text=new_index.text,
            language_code=language_code,
            entity_ids=[span.entity_id],
            segment_id=span.segment_id,
        )
        anchored = []
        for match in matches:
            anchor = new_index.resolve_span(match.match_start, match.match_end)
            if (anchor.segment_id, anchor.end_segment_id) == (
                span.segment_id,
                span.end_segment_id,
            ):
                anchored.append((match, anchor.match_start, anchor.match_end))
        if not anchored:
            return "kept", None, None
        match, local_start, local_end = max(
            anchored, key=lambda m: m[0].match_end - m[0].match_start
        )
        return "kept", (local_start, local_end), match

    async def _record_asr_alias_if_entity_match(
        self,
        session: AsyncSession,
        *,
        original_text: str,
        corrected_text: str,
        video_id: str | None = None,
    ) -> None:
        """Best-effort hook: auto-record ASR error alias when correction matches an entity.

        Delegates to :func:`~chronovista.services.asr_alias_registry.register_asr_alias`.
        The *video_id* lets the registry disambiguate a shared name against the
        entities already known in that video (Feature 111 FR-008).
        """
        from chronovista.services.asr_alias_registry import register_asr_alias

        await register_asr_alias(
            session,
            original_text=original_text,
            corrected_text=corrected_text,
            occurrence_count=1,
            commit=False,
            log_prefix="B-lite",
            video_id=video_id,
        )


def _detector() -> EntityMentionScanService:
    """The scan's matching rule, on the caller's session (imported here: the scan
    service imports cross-segment discovery, which imports this module's callers)."""
    from chronovista.services.entity_mention_scan_service import (
        EntityMentionScanService,
    )

    return EntityMentionScanService()


def _repointed(
    matches: list[TextMatch], entity_id: uuid.UUID, region: tuple[int, int]
) -> TextMatch | None:
    """The longest detected occurrence of the entity overlapping ``region``."""
    lo, hi = region
    found = [
        m
        for m in matches
        if m.entity_id == entity_id
        and m.match_start < max(hi, lo + 1)
        and lo < m.match_end
    ]
    if not found:
        return None
    return max(found, key=lambda m: m.match_end - m.match_start)


def _relabel(mention_id: uuid.UUID, match: TextMatch) -> MentionRelabel:
    return MentionRelabel(
        id=mention_id,
        mention_text=match.mention_text,
        detection_method=match.detection_method.value,
        alias_id=match.alias_id,
    )


__all__ = ["TranscriptCorrectionService"]
