"""
Batch correction service for orchestrating bulk transcript corrections.

Provides configurable transaction batching with commit/rollback per chunk,
regex pre-validation, progress reporting, and find-and-replace with both
live and dry-run modes.

Feature 036 — Batch Correction Tools (T009, T010, T011, T017, T019, T021, T023, T025)
Feature 038 — Entity Mention Detection (T005, T006, T007, T011, T012, T013)
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.schemas.batch_corrections import (
    BatchApplyResult,
    BatchPreviewMatch,
)
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.batch_correction_models import (
    BatchCorrectionResult,
    CorrectionExportRecord,
    CorrectionPattern,
    CorrectionStats,
    CrossSegmentMatch,
    SegmentPair,
)
from chronovista.models.correction_actors import ACTOR_CLI_BATCH
from chronovista.models.enums import CorrectionType
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.services.transcript_correction_service import (
    TranscriptCorrectionService,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BatchCorrectionService:
    """
    Orchestration layer for batch transcript correction operations.

    Wraps ``TranscriptCorrectionService`` (single-segment corrections) with
    chunked transaction batching, progress reporting, and regex pre-validation.
    Each batch of items is committed independently so that a failure in one
    batch does not roll back previously committed work.

    Parameters
    ----------
    correction_service : TranscriptCorrectionService
        The single-correction service used for per-segment apply/revert.
    segment_repo : TranscriptSegmentRepository
        Repository for transcript segment queries (find_by_text_pattern, etc.).
    correction_repo : TranscriptCorrectionRepository
        Repository for transcript correction audit queries (stats, patterns).
    """

    def __init__(
        self,
        correction_service: TranscriptCorrectionService,
        segment_repo: TranscriptSegmentRepository,
        correction_repo: TranscriptCorrectionRepository,
    ) -> None:
        self._correction_service = correction_service
        self._segment_repo = segment_repo
        self._correction_repo = correction_repo

    # ------------------------------------------------------------------
    # Regex timeout constant (T011)
    # ------------------------------------------------------------------
    _REGEX_TIMEOUT_SECONDS: float = 5.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def find_matching_segments(
        self,
        session: AsyncSession,
        *,
        pattern: str,
        replacement: str,
        regex: bool = False,
        case_insensitive: bool = False,
        language: str | None = None,
        channel: str | None = None,
        video_ids: list[str] | None = None,
        cross_segment: bool = False,
        max_matches: int = 200,
    ) -> tuple[list[BatchPreviewMatch], int]:
        """
        Return matching segments with proposed replacement text.

        Validates the pattern, finds segments whose effective text matches,
        optionally includes cross-segment matches, computes proposed text,
        and caps the returned list at *max_matches* while reporting the
        true total count.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        pattern : str
            The search pattern (substring or regex).
        replacement : str
            The replacement text. Empty string is allowed for deletion.
        regex : bool, optional
            If True, treat *pattern* as a regular expression (default False).
        case_insensitive : bool, optional
            If True, use case-insensitive matching (default False).
        language : str or None, optional
            Filter by language_code.
        channel : str or None, optional
            Filter by channel_id.
        video_ids : list of str or None, optional
            Filter by video_id list.
        cross_segment : bool, optional
            Whether to match patterns that span segment boundaries
            (default False).
        max_matches : int, optional
            Maximum number of matches to return (default 200). The true
            total count is always reported.

        Returns
        -------
        tuple[list[BatchPreviewMatch], int]
            ``(matches, total_count)`` where *matches* is capped at
            *max_matches* and *total_count* is the uncapped total.

        Raises
        ------
        ValueError
            If *regex* is True and the pattern cannot be compiled, or
            if a regex operation times out.
        """
        _start_time = time.monotonic()
        logger.info(
            "find_matching_segments started: pattern=%r, regex=%s, "
            "case_insensitive=%s, language=%s, channel=%s, video_ids=%s, "
            "cross_segment=%s, max_matches=%d",
            pattern,
            regex,
            case_insensitive,
            language,
            channel,
            video_ids,
            cross_segment,
            max_matches,
        )

        # Step 1: Validate pattern
        self._validate_pattern(pattern, regex=regex)

        # Step 2: Find matching segments (single-segment)
        matched_segments = await self._segment_repo.find_by_text_pattern(
            session,
            pattern=pattern,
            regex=regex,
            case_insensitive=case_insensitive,
            language=language,
            channel=channel,
            video_ids=video_ids,
        )

        re_flags = re.IGNORECASE if case_insensitive else 0

        # Step 3: Cross-segment matching
        cross_segment_matches: list[CrossSegmentMatch] = []
        if cross_segment:
            cross_segment_matches = await self._find_cross_segment_matches(
                session,
                pattern=pattern,
                replacement=replacement,
                regex=regex,
                case_insensitive=case_insensitive,
                re_flags=re_flags,
                language=language,
                channel=channel,
                video_ids=video_ids,
                single_segment_ids={seg.id for seg in matched_segments},
            )

        # Step 4: Collect all video_ids for batch title/channel lookup
        all_video_ids: set[str] = set()
        for seg in matched_segments:
            all_video_ids.add(seg.video_id)
        for csm in cross_segment_matches:
            all_video_ids.add(csm.pair.segment_a.video_id)

        # Batch fetch video titles and channel titles
        video_title_map: dict[str, str] = {}
        channel_title_map: dict[str, str] = {}
        if all_video_ids:
            video_result = await session.execute(
                select(VideoDB.video_id, VideoDB.title, VideoDB.channel_id).where(
                    VideoDB.video_id.in_(list(all_video_ids))
                )
            )
            video_rows = list(video_result.all())
            channel_ids_to_fetch: set[str] = set()
            for row in video_rows:
                video_title_map[row.video_id] = row.title or ""
                if row.channel_id:
                    channel_ids_to_fetch.add(row.channel_id)

            if channel_ids_to_fetch:
                channel_result = await session.execute(
                    select(ChannelDB.channel_id, ChannelDB.title).where(
                        ChannelDB.channel_id.in_(list(channel_ids_to_fetch))
                    )
                )
                for ch_row in channel_result.all():
                    channel_title_map[ch_row.channel_id] = ch_row.title or ""

        # Build a map from video_id -> channel_id for lookups
        video_channel_map: dict[str, str | None] = {}
        for row in video_rows if all_video_ids else []:
            video_channel_map[row.video_id] = row.channel_id

        # Step 5: Fetch context segments (prev/next by sequence_number)
        # Collect (video_id, language_code, sequence_number) for all matched
        # segments, then batch-query neighbors.
        context_map: dict[int, tuple[str | None, str | None]] = {}
        if matched_segments or cross_segment_matches:
            await self._batch_fetch_context_segments(
                session,
                matched_segments,
                cross_segment_matches,
                context_map,
            )

        # Step 6: Build BatchPreviewMatch objects
        all_matches: list[BatchPreviewMatch] = []

        # Single-segment matches
        for segment in matched_segments:
            effective_text: str = (
                segment.corrected_text
                if segment.has_correction
                else segment.text
            ) or ""

            # T011: Regex timeout enforcement
            proposed_text = await self._compute_replacement_with_timeout(
                effective_text, pattern, replacement, regex, re_flags,
                case_insensitive,
            )

            # T013: Skip no-op matches
            if proposed_text == effective_text:
                continue

            # Compute match offset
            match_start, match_end = self._find_match_offsets(
                effective_text, pattern, regex, re_flags, case_insensitive,
            )

            v_title = video_title_map.get(segment.video_id, "")
            ch_id = video_channel_map.get(segment.video_id)
            ch_title = channel_title_map.get(ch_id, "") if ch_id else ""

            ctx_before, ctx_after = context_map.get(segment.id, (None, None))

            deep_link = (
                f"/videos/{segment.video_id}"
                f"?lang={segment.language_code}"
                f"&seg={segment.id}"
                f"&t={segment.start_time}"
            )

            all_matches.append(BatchPreviewMatch(
                segment_id=segment.id,
                video_id=segment.video_id,
                video_title=v_title,
                channel_title=ch_title,
                language_code=segment.language_code,
                start_time=segment.start_time,
                current_text=effective_text,
                proposed_text=proposed_text,
                match_start=match_start,
                match_end=match_end,
                context_before=ctx_before,
                context_after=ctx_after,
                has_existing_correction=segment.has_correction,
                is_cross_segment=False,
                pair_id=None,
                deep_link_url=deep_link,
            ))

        # Cross-segment matches (two rows per pair)
        for csm in cross_segment_matches:
            pair = csm.pair
            seg_a = pair.segment_a
            seg_b = pair.segment_b
            eff_a: str = (
                seg_a.corrected_text if seg_a.has_correction else seg_a.text
            ) or ""
            eff_b: str = (
                seg_b.corrected_text if seg_b.has_correction else seg_b.text
            ) or ""

            # T013: Skip no-op cross-segment matches
            if csm.text_for_seg_a == eff_a and csm.text_for_seg_b == eff_b:
                continue

            pair_id_str = str(uuid.uuid4())

            # Segment A
            v_title_a = video_title_map.get(seg_a.video_id, "")
            ch_id_a = video_channel_map.get(seg_a.video_id)
            ch_title_a = channel_title_map.get(ch_id_a, "") if ch_id_a else ""
            ctx_before_a, ctx_after_a = context_map.get(seg_a.id, (None, None))

            deep_link_a = (
                f"/videos/{seg_a.video_id}"
                f"?lang={seg_a.language_code}"
                f"&seg={seg_a.id}"
                f"&t={seg_a.start_time}"
            )

            # Match offsets are relative to the combined text, so we compute
            # the offset within seg_a's text for the portion that falls in A.
            # For cross-segment, the match spans the boundary, so match_start
            # for seg_a is csm.match_start (within combined text).
            boundary = pair.boundary_offset
            a_match_start = min(csm.match_start, len(eff_a))
            a_match_end = min(csm.match_end, len(eff_a))

            all_matches.append(BatchPreviewMatch(
                segment_id=seg_a.id,
                video_id=seg_a.video_id,
                video_title=v_title_a,
                channel_title=ch_title_a,
                language_code=seg_a.language_code,
                start_time=seg_a.start_time,
                current_text=eff_a,
                proposed_text=csm.text_for_seg_a,
                match_start=a_match_start,
                match_end=a_match_end,
                context_before=ctx_before_a,
                context_after=ctx_after_a,
                has_existing_correction=seg_a.has_correction,
                is_cross_segment=True,
                pair_id=pair_id_str,
                deep_link_url=deep_link_a,
            ))

            # Segment B
            v_title_b = video_title_map.get(seg_b.video_id, "")
            ch_id_b = video_channel_map.get(seg_b.video_id)
            ch_title_b = channel_title_map.get(ch_id_b, "") if ch_id_b else ""
            ctx_before_b, ctx_after_b = context_map.get(seg_b.id, (None, None))

            deep_link_b = (
                f"/videos/{seg_b.video_id}"
                f"?lang={seg_b.language_code}"
                f"&seg={seg_b.id}"
                f"&t={seg_b.start_time}"
            )

            # For seg B the consumed portion starts at offset 0
            b_match_start = 0
            b_consumed = csm.match_end - (boundary + 1)
            b_match_end = max(b_consumed, 0)

            all_matches.append(BatchPreviewMatch(
                segment_id=seg_b.id,
                video_id=seg_b.video_id,
                video_title=v_title_b,
                channel_title=ch_title_b,
                language_code=seg_b.language_code,
                start_time=seg_b.start_time,
                current_text=eff_b,
                proposed_text=csm.text_for_seg_b,
                match_start=b_match_start,
                match_end=b_match_end,
                context_before=ctx_before_b,
                context_after=ctx_after_b,
                has_existing_correction=seg_b.has_correction,
                is_cross_segment=True,
                pair_id=pair_id_str,
                deep_link_url=deep_link_b,
            ))

        # T012: Cap at max_matches but report true total
        total_count = len(all_matches)
        capped_matches = all_matches[:max_matches]

        _elapsed = time.monotonic() - _start_time
        logger.info(
            "find_matching_segments completed: total_count=%d, "
            "returned=%d, duration=%.2fs",
            total_count,
            len(capped_matches),
            _elapsed,
        )

        return capped_matches, total_count

    async def apply_to_segments(
        self,
        session: AsyncSession,
        *,
        pattern: str,
        replacement: str,
        segment_ids: list[int],
        regex: bool = False,
        case_insensitive: bool = False,
        cross_segment: bool = False,
        correction_type: CorrectionType = CorrectionType.PROPER_NOUN,
        correction_note: str | None = None,
        auto_rebuild: bool = True,
        corrected_by_user_id: str = ACTOR_CLI_BATCH,
    ) -> BatchApplyResult:
        """
        Apply find-replace corrections to an explicit set of segment IDs.

        Fetches segments by the provided IDs, re-validates that the pattern
        still matches each segment's effective text, applies corrections
        via ``TranscriptCorrectionService``, and optionally rebuilds full
        transcript text for affected videos.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        pattern : str
            The search pattern (substring or regex).
        replacement : str
            The replacement text.
        segment_ids : list[int]
            Segment IDs to apply corrections to.
        regex : bool, optional
            If True, treat *pattern* as a regex (default False).
        case_insensitive : bool, optional
            If True, use case-insensitive matching (default False).
        cross_segment : bool, optional
            Whether cross-segment matching was used (default False).
        correction_type : CorrectionType, optional
            Category of correction (default ``CorrectionType.PROPER_NOUN``).
        correction_note : str or None, optional
            Human-readable explanation for the correction.
        auto_rebuild : bool, optional
            If True, rebuild full text for affected videos (default True).

        Returns
        -------
        BatchApplyResult
            Counts of applied, skipped, and failed corrections.
        """
        _start_time = time.monotonic()
        logger.info(
            "apply_to_segments started: pattern=%r, segment_ids_count=%d, "
            "regex=%s, case_insensitive=%s, cross_segment=%s, "
            "correction_type=%s, auto_rebuild=%s",
            pattern,
            len(segment_ids),
            regex,
            case_insensitive,
            cross_segment,
            correction_type,
            auto_rebuild,
        )

        # Step 1: Validate pattern
        self._validate_pattern(pattern, regex=regex)

        re_flags = re.IGNORECASE if case_insensitive else 0

        # Step 2: Fetch segments by IDs
        segments_result = await session.execute(
            select(TranscriptSegmentDB).where(
                TranscriptSegmentDB.id.in_(segment_ids)
            )
        )
        segments = list(segments_result.scalars().all())
        segment_map = {seg.id: seg for seg in segments}

        total_applied = 0
        total_skipped = 0
        total_failed = 0
        failed_segment_ids: list[int] = []
        affected_video_ids: set[str] = set()
        matched_form_counts: dict[str, int] = {}

        # Step 3: Process each segment
        for seg_id in segment_ids:
            segment = segment_map.get(seg_id)
            if segment is None:
                total_skipped += 1
                logger.warning(
                    "apply_to_segments: segment %d not found, skipping",
                    seg_id,
                )
                continue

            effective_text: str = (
                segment.corrected_text
                if segment.has_correction
                else segment.text
            ) or ""

            # Re-validate that pattern still matches
            if regex:
                match = re.search(pattern, effective_text, flags=re_flags)
            elif case_insensitive:
                match = re.search(
                    re.escape(pattern), effective_text, flags=re.IGNORECASE
                )
            else:
                match = pattern in effective_text  # type: ignore[assignment]

            if not match:
                total_skipped += 1
                logger.debug(
                    "apply_to_segments: pattern no longer matches "
                    "segment %d, skipping",
                    seg_id,
                )
                continue

            # Compute replacement
            if regex:
                new_text = re.sub(
                    pattern, replacement, effective_text, flags=re_flags
                )
            elif case_insensitive:
                new_text = re.sub(
                    re.escape(pattern),
                    replacement,
                    effective_text,
                    flags=re.IGNORECASE,
                )
            else:
                new_text = effective_text.replace(pattern, replacement)

            # Skip no-ops
            if new_text == effective_text:
                total_skipped += 1
                continue

            # Apply correction
            try:
                await self._correction_service.apply_correction(
                    session,
                    video_id=segment.video_id,
                    language_code=segment.language_code,
                    segment_id=segment.id,
                    corrected_text=new_text,
                    correction_type=correction_type,
                    correction_note=correction_note,
                    corrected_by_user_id=corrected_by_user_id,
                )
                total_applied += 1
                affected_video_ids.add(segment.video_id)

                # Track matched forms for ASR alias registration
                if regex:
                    for m in re.findall(
                        pattern, effective_text, flags=re_flags
                    ):
                        matched_form_counts[m] = (
                            matched_form_counts.get(m, 0) + 1
                        )
                else:
                    matched_form_counts[pattern] = (
                        matched_form_counts.get(pattern, 0) + 1
                    )
            except ValueError:
                total_skipped += 1
            except Exception:
                total_failed += 1
                failed_segment_ids.append(seg_id)
                logger.warning(
                    "apply_to_segments: failed to apply correction "
                    "to segment %d",
                    seg_id,
                    exc_info=True,
                )

        # Step 4: Register ASR aliases
        if total_applied > 0:
            for form, count in matched_form_counts.items():
                await self._record_asr_alias_for_batch_replacement(
                    session,
                    pattern=form,
                    replacement=replacement,
                    total_applied=count,
                )

        # Step 5: Auto-rebuild
        rebuild_triggered = False
        if auto_rebuild and affected_video_ids:
            await self.rebuild_text(
                session, video_ids=list(affected_video_ids)
            )
            rebuild_triggered = True

        await session.commit()

        _elapsed = time.monotonic() - _start_time
        logger.info(
            "apply_to_segments completed: applied=%d, skipped=%d, "
            "failed=%d, affected_videos=%d, rebuild=%s, duration=%.2fs",
            total_applied,
            total_skipped,
            total_failed,
            len(affected_video_ids),
            rebuild_triggered,
            _elapsed,
        )

        return BatchApplyResult(
            total_applied=total_applied,
            total_skipped=total_skipped,
            total_failed=total_failed,
            failed_segment_ids=failed_segment_ids,
            affected_video_ids=list(affected_video_ids),
            rebuild_triggered=rebuild_triggered,
        )

    async def find_and_replace(
        self,
        session: AsyncSession,
        *,
        pattern: str,
        replacement: str,
        regex: bool = False,
        case_insensitive: bool = False,
        language: str | None = None,
        channel: str | None = None,
        video_ids: list[str] | None = None,
        correction_type: CorrectionType = CorrectionType.PROPER_NOUN,
        correction_note: str | None = None,
        batch_size: int = 100,
        dry_run: bool = False,
        progress_callback: Callable[[int], None] | None = None,
        cross_segment: bool = False,
    ) -> BatchCorrectionResult | list[tuple[str, int, float, str, str]]:
        """
        Find segments matching *pattern* and replace with *replacement*.

        In **live mode** (``dry_run=False``), corrections are applied via
        ``TranscriptCorrectionService.apply_correction`` in transaction-safe
        batches.  In **dry-run mode** (``dry_run=True``), no mutations are
        performed — a list of preview tuples is returned instead.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        pattern : str
            The search pattern (substring or regex).
        replacement : str
            The replacement text.
        regex : bool, optional
            If True, treat *pattern* as a regular expression (default False).
        case_insensitive : bool, optional
            If True, use case-insensitive matching (default False).
        language : str or None, optional
            Filter by language_code.
        channel : str or None, optional
            Filter by channel_id.
        video_ids : list of str or None, optional
            Filter by video_id list.
        correction_type : CorrectionType, optional
            Category of correction (default ``CorrectionType.PROPER_NOUN``).
        correction_note : str or None, optional
            Human-readable explanation for the correction.
        batch_size : int, optional
            Number of items per transaction chunk (default 100).
        dry_run : bool, optional
            If True, return preview tuples instead of applying corrections
            (default False).
        progress_callback : Callable[[int], None] or None, optional
            Called with the chunk length after each batch completes
            (live mode only).

        Returns
        -------
        BatchCorrectionResult
            When ``dry_run=False``: full result with counts.
        list[tuple[str, int, float, str, str]]
            When ``dry_run=True``: list of
            ``(video_id, segment_id, start_time, current_text, proposed_text)``
            preview tuples.

        Raises
        ------
        ValueError
            If *regex* is True and the pattern cannot be compiled.
        """
        # T016: Structured logging — start
        _start_time = time.monotonic()
        logger.info(
            "find_and_replace started: pattern=%r, regex=%s, case_insensitive=%s, "
            "language=%s, channel=%s, video_ids=%s, dry_run=%s, batch_size=%d, "
            "cross_segment=%s",
            pattern,
            regex,
            case_insensitive,
            language,
            channel,
            video_ids,
            dry_run,
            batch_size,
            cross_segment,
        )

        # Step 1: Validate pattern
        self._validate_pattern(pattern, regex=regex)

        # ------ Dry-run mode: delegate to find_matching_segments() ------
        if dry_run:
            preview_matches, _total = await self.find_matching_segments(
                session,
                pattern=pattern,
                replacement=replacement,
                regex=regex,
                case_insensitive=case_insensitive,
                language=language,
                channel=channel,
                video_ids=video_ids,
                cross_segment=cross_segment,
                max_matches=999_999,  # no cap for CLI dry-run
            )
            # Convert BatchPreviewMatch objects to legacy tuple format
            previews: list[tuple[str, int, float, str, str]] = []
            for m in preview_matches:
                previews.append((
                    m.video_id,
                    m.segment_id,
                    m.start_time,
                    m.current_text,
                    m.proposed_text,
                ))
            _elapsed = time.monotonic() - _start_time
            logger.info(
                "find_and_replace completed (dry_run): matched=%d, "
                "duration=%.2fs",
                len(previews),
                _elapsed,
            )
            return previews

        # ------ Live mode: keep existing apply logic for CLI ------

        # Step 2: Count total segments in filter scope
        total_scanned = await self._segment_repo.count_filtered(
            session,
            language=language,
            channel=channel,
            video_ids=video_ids,
        )

        # Step 3: Find matching segments (single-segment matching)
        matched_segments = await self._segment_repo.find_by_text_pattern(
            session,
            pattern=pattern,
            regex=regex,
            case_insensitive=case_insensitive,
            language=language,
            channel=channel,
            video_ids=video_ids,
        )

        total_matched = len(matched_segments)

        # Build regex flags for Python-side replacement
        re_flags = re.IGNORECASE if case_insensitive else 0

        # Helper: compute the new text for a segment
        def _compute_new_text(segment: Any) -> str:
            effective_text: str = (
                segment.corrected_text
                if segment.has_correction
                else segment.text
            ) or ""
            if regex:
                return re.sub(pattern, replacement, effective_text, flags=re_flags)
            if case_insensitive:
                return re.sub(
                    re.escape(pattern),
                    replacement,
                    effective_text,
                    flags=re.IGNORECASE,
                )
            return effective_text.replace(pattern, replacement)

        # ------------------------------------------------------------------
        # Cross-segment matching (T020-T025)
        # ------------------------------------------------------------------
        cross_segment_matches: list[CrossSegmentMatch] = []

        if cross_segment:
            cross_segment_matches = await self._find_cross_segment_matches(
                session,
                pattern=pattern,
                replacement=replacement,
                regex=regex,
                case_insensitive=case_insensitive,
                re_flags=re_flags,
                language=language,
                channel=channel,
                video_ids=video_ids,
                single_segment_ids={seg.id for seg in matched_segments},
            )

        # ------ Live mode ------
        # Count unique videos among matched segments
        unique_video_ids = {seg.video_id for seg in matched_segments}
        # Include cross-segment matches in unique video count
        for csm in cross_segment_matches:
            unique_video_ids.add(csm.pair.segment_a.video_id)
        unique_videos = len(unique_video_ids)

        # Add cross-segment matched segments to total_matched count
        # Each segment in a pair counts as 1
        total_matched += len(cross_segment_matches) * 2

        # Zero matches → short-circuit
        if total_matched == 0:
            _elapsed = time.monotonic() - _start_time
            logger.info(
                "find_and_replace completed (zero matches): scanned=%d, duration=%.2fs",
                total_scanned,
                _elapsed,
            )
            return BatchCorrectionResult(
                total_scanned=total_scanned,
                total_matched=0,
                total_applied=0,
                total_skipped=0,
                total_failed=0,
                failed_batches=0,
                unique_videos=0,
            )

        # Collect distinct matched forms for ASR alias registration.
        # For substring mode this is just {pattern: count}; for regex mode
        # re.findall() extracts the actual matched text from each segment.
        matched_form_counts: dict[str, int] = {}

        # Per-item processing function for _process_in_batches
        async def _apply_one(session: AsyncSession, segment: Any) -> str:
            # Capture effective text BEFORE apply_correction mutates the ORM object
            # (apply_correction sets segment.corrected_text and has_correction=True).
            effective_text: str = (
                segment.corrected_text
                if segment.has_correction
                else segment.text
            ) or ""

            new_text = _compute_new_text(segment)
            try:
                await self._correction_service.apply_correction(
                    session,
                    video_id=segment.video_id,
                    language_code=segment.language_code,
                    segment_id=segment.id,
                    corrected_text=new_text,
                    correction_type=correction_type,
                    correction_note=correction_note,
                    corrected_by_user_id=ACTOR_CLI_BATCH,
                )
            except ValueError:
                # No-op: corrected_text == effective text → skip
                return "skipped"

            # Track actual matched forms for alias registration
            if regex:
                for match in re.findall(pattern, effective_text, flags=re_flags):
                    matched_form_counts[match] = matched_form_counts.get(match, 0) + 1
            else:
                matched_form_counts[pattern] = matched_form_counts.get(pattern, 0) + 1

            return "applied"

        total_applied, total_skipped, total_failed, failed_batches = (
            await self._process_in_batches(
                session,
                list(matched_segments),
                _apply_one,
                batch_size=batch_size,
                progress_callback=progress_callback,
            )
        )

        # ------------------------------------------------------------------
        # Apply cross-segment corrections (T023-T025)
        # ------------------------------------------------------------------
        if cross_segment_matches:
            cs_applied, cs_skipped, cs_failed, cs_failed_batches = (
                await self._apply_cross_segment_corrections(
                    session,
                    cross_segment_matches,
                    correction_type=correction_type,
                    correction_note=correction_note,
                    batch_size=batch_size,
                    progress_callback=progress_callback,
                )
            )
            total_applied += cs_applied
            total_skipped += cs_skipped
            total_failed += cs_failed
            failed_batches += cs_failed_batches

            # Track matched forms for cross-segment alias registration
            for csm in cross_segment_matches:
                combined = csm.pair.combined_text
                matched_text = combined[csm.match_start:csm.match_end]
                matched_form_counts[matched_text] = (
                    matched_form_counts.get(matched_text, 0) + 1
                )

        # Auto-register ASR aliases: each distinct matched form is registered
        # as a separate alias with its own occurrence count.
        if total_applied > 0:
            for form, count in matched_form_counts.items():
                await self._record_asr_alias_for_batch_replacement(
                    session,
                    pattern=form,
                    replacement=replacement,
                    total_applied=count,
                )

        _elapsed = time.monotonic() - _start_time
        logger.info(
            "find_and_replace completed: scanned=%d, matched=%d, applied=%d, "
            "skipped=%d, failed=%d, failed_batches=%d, unique_videos=%d, "
            "cross_segment_pairs=%d, duration=%.2fs",
            total_scanned,
            total_matched,
            total_applied,
            total_skipped,
            total_failed,
            failed_batches,
            unique_videos,
            len(cross_segment_matches),
            _elapsed,
        )

        return BatchCorrectionResult(
            total_scanned=total_scanned,
            total_matched=total_matched,
            total_applied=total_applied,
            total_skipped=total_skipped,
            total_failed=total_failed,
            failed_batches=failed_batches,
            unique_videos=unique_videos,
        )

    async def rebuild_text(
        self,
        session: AsyncSession,
        *,
        video_ids: list[str] | None = None,
        language: str | None = None,
        dry_run: bool = False,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[dict[str, Any]] | tuple[int, int]:
        """
        Rebuild transcript_text from corrected segments.

        For each transcript with ``has_corrections = True``, re-concatenates
        the effective text of all segments (ordered by ``start_time``) and
        updates ``transcript_text``.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_ids : list[str] or None, optional
            If provided, restrict to these video IDs.
        language : str or None, optional
            If provided, restrict to this language code.
        dry_run : bool, optional
            If True, return preview dicts instead of mutating (default False).
        progress_callback : Callable[[int], None] or None, optional
            Called with 1 after each transcript is processed.

        Returns
        -------
        list[dict]
            When ``dry_run=True``: list of preview dicts with keys
            ``video_id``, ``language_code``, ``current_length``, ``new_length``.
        tuple[int, int]
            When ``dry_run=False``: ``(total_transcripts_rebuilt, total_segments_processed)``.
        """
        _start_time = time.monotonic()
        logger.info(
            "rebuild_text started: video_ids=%s, language=%s, dry_run=%s",
            video_ids,
            language,
            dry_run,
        )

        # Query transcripts with has_corrections = True
        conditions: list[Any] = [VideoTranscriptDB.has_corrections.is_(True)]
        if video_ids is not None:
            conditions.append(VideoTranscriptDB.video_id.in_(video_ids))
        if language is not None:
            conditions.append(VideoTranscriptDB.language_code == language)

        stmt = select(VideoTranscriptDB).where(and_(*conditions))
        result = await session.execute(stmt)
        transcripts = list(result.scalars().all())

        previews: list[dict[str, Any]] = []
        total_rebuilt = 0
        total_segments = 0

        for transcript in transcripts:
            # Get segments ordered by start_time
            seg_stmt = (
                select(TranscriptSegmentDB)
                .where(
                    and_(
                        TranscriptSegmentDB.video_id == transcript.video_id,
                        TranscriptSegmentDB.language_code == transcript.language_code,
                    )
                )
                .order_by(TranscriptSegmentDB.start_time)
            )
            seg_result = await session.execute(seg_stmt)
            segments = list(seg_result.scalars().all())

            # Check if any segment actually has a correction
            corrected_segments = [s for s in segments if s.has_correction]
            if not corrected_segments:
                if progress_callback is not None:
                    progress_callback(1)
                continue

            # Build new text from effective texts
            effective_texts = []
            for seg in segments:
                effective = (
                    seg.corrected_text if seg.has_correction else seg.text
                ) or ""
                effective_texts.append(effective)

            new_text = " ".join(effective_texts)
            current_text = transcript.transcript_text or ""

            if dry_run:
                previews.append({
                    "video_id": transcript.video_id,
                    "language_code": transcript.language_code,
                    "current_length": len(current_text),
                    "new_length": len(new_text),
                })
            else:
                transcript.transcript_text = new_text
                await session.flush()
                total_rebuilt += 1
                total_segments += len(segments)

            if progress_callback is not None:
                progress_callback(1)

        _elapsed = time.monotonic() - _start_time

        if dry_run:
            logger.info(
                "rebuild_text completed (dry_run): previews=%d, duration=%.2fs",
                len(previews),
                _elapsed,
            )
            return previews

        logger.info(
            "rebuild_text completed: rebuilt=%d, segments=%d, duration=%.2fs",
            total_rebuilt,
            total_segments,
            _elapsed,
        )
        return total_rebuilt, total_segments

    async def export_corrections(
        self,
        session: AsyncSession,
        *,
        video_ids: list[str] | None = None,
        correction_type: CorrectionType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        compact: bool = False,
        format: str = "csv",
        progress_callback: Callable[[int], None] | None = None,
    ) -> tuple[int, str]:
        """
        Export corrections as CSV or JSON string.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_ids : list[str] or None, optional
            Filter by video IDs.
        correction_type : CorrectionType or None, optional
            Filter by correction type.
        since : datetime or None, optional
            Inclusive lower bound on corrected_at.
        until : datetime or None, optional
            Inclusive upper bound on corrected_at.
        compact : bool, optional
            If True, JSON output has no indentation (default False).
        format : str, optional
            Output format: ``"csv"`` or ``"json"`` (default ``"csv"``).
        progress_callback : Callable[[int], None] or None, optional
            Called with 1 after each record is processed.

        Returns
        -------
        tuple[int, str]
            ``(record_count, serialized_string)``.
        """
        _start_time = time.monotonic()
        logger.info(
            "export_corrections started: video_ids=%s, correction_type=%s, "
            "since=%s, until=%s, format=%s, compact=%s",
            video_ids,
            correction_type,
            since,
            until,
            format,
            compact,
        )

        corrections = await self._correction_repo.get_all_filtered(
            session,
            video_ids=video_ids,
            correction_type=correction_type,
            since=since,
            until=until,
        )

        records: list[CorrectionExportRecord] = []
        for c in corrections:
            record = CorrectionExportRecord(
                id=str(c.id),
                video_id=c.video_id,
                language_code=c.language_code,
                segment_id=c.segment_id,
                correction_type=c.correction_type,
                original_text=c.original_text,
                corrected_text=c.corrected_text,
                correction_note=c.correction_note,
                corrected_by_user_id=c.corrected_by_user_id,
                corrected_at=c.corrected_at.isoformat() if c.corrected_at else "",
                version_number=c.version_number,
            )
            records.append(record)
            if progress_callback is not None:
                progress_callback(1)

        if format == "json":
            # Custom serializer for UUID and datetime
            def _json_default(obj: Any) -> str:
                if isinstance(obj, UUID | datetime):
                    return str(obj)
                raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

            data = [r.model_dump() for r in records]
            indent = None if compact else 2
            serialized = json.dumps(data, default=_json_default, indent=indent)
        else:
            # CSV format
            output = io.StringIO()
            fieldnames = [
                "id", "video_id", "language_code", "segment_id",
                "correction_type", "original_text", "corrected_text",
                "correction_note", "corrected_by_user_id", "corrected_at",
                "version_number",
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow(record.model_dump())
            serialized = output.getvalue()

        _elapsed = time.monotonic() - _start_time
        logger.info(
            "export_corrections completed: records=%d, format=%s, duration=%.2fs",
            len(records),
            format,
            _elapsed,
        )
        return len(records), serialized

    async def get_statistics(
        self,
        session: AsyncSession,
        *,
        language: str | None = None,
        top: int = 10,
    ) -> CorrectionStats:
        """
        Get aggregate correction statistics.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        language : str or None, optional
            Restrict statistics to this language code.
        top : int, optional
            Number of top videos to return (default 10).

        Returns
        -------
        CorrectionStats
            Aggregate statistics model.
        """
        _start_time = time.monotonic()
        logger.info(
            "get_statistics started: language=%s, top=%d",
            language,
            top,
        )

        result = await self._correction_repo.get_stats(
            session, language=language, top=top,
        )

        stats = CorrectionStats(**result)

        _elapsed = time.monotonic() - _start_time
        logger.info(
            "get_statistics completed: total_corrections=%d, total_reverts=%d, "
            "duration=%.2fs",
            stats.total_corrections,
            stats.total_reverts,
            _elapsed,
        )
        return stats

    async def get_patterns(
        self,
        session: AsyncSession,
        *,
        min_occurrences: int = 2,
        limit: int = 25,
        show_completed: bool = False,
    ) -> list[CorrectionPattern]:
        """
        Discover recurring correction patterns.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        min_occurrences : int, optional
            Minimum occurrences to include (default 2).
        limit : int, optional
            Maximum patterns to return (default 25).
        show_completed : bool, optional
            Include patterns with zero remaining matches (default False).

        Returns
        -------
        list[CorrectionPattern]
            Patterns sorted by remaining_matches DESC.
        """
        _start_time = time.monotonic()
        logger.info(
            "get_patterns started: min_occurrences=%d, limit=%d, show_completed=%s",
            min_occurrences,
            limit,
            show_completed,
        )

        patterns = await self._correction_repo.get_correction_patterns(
            session,
            min_occurrences=min_occurrences,
            limit=limit,
            show_completed=show_completed,
        )

        _elapsed = time.monotonic() - _start_time
        logger.info(
            "get_patterns completed: patterns_found=%d, duration=%.2fs",
            len(patterns),
            _elapsed,
        )
        return patterns

    async def batch_revert(
        self,
        session: AsyncSession,
        *,
        pattern: str,
        regex: bool = False,
        case_insensitive: bool = False,
        language: str | None = None,
        video_ids: list[str] | None = None,
        batch_size: int = 100,
        dry_run: bool = False,
        progress_callback: Callable[[int], None] | None = None,
    ) -> BatchCorrectionResult | list[tuple[str, int, float, str, bool]]:
        """
        Revert corrections on segments whose corrected_text matches *pattern*.

        In **live mode**, each matched segment is reverted via
        ``TranscriptCorrectionService.revert_correction`` in transaction-safe
        batches.  In **dry-run mode**, a list of preview tuples is returned.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        pattern : str
            The search pattern (substring or regex).
        regex : bool, optional
            If True, treat *pattern* as a regular expression (default False).
        case_insensitive : bool, optional
            If True, use case-insensitive matching (default False).
        language : str or None, optional
            Filter by language_code.
        video_ids : list of str or None, optional
            Filter by video_id list.
        batch_size : int, optional
            Number of items per transaction chunk (default 100).
        dry_run : bool, optional
            If True, return preview tuples (default False).
        progress_callback : Callable[[int], None] or None, optional
            Called with the chunk length after each batch.

        Returns
        -------
        BatchCorrectionResult
            When ``dry_run=False``.
        list[tuple[str, int, float, str]]
            When ``dry_run=True``: list of
            ``(video_id, segment_id, start_time, corrected_text)`` tuples.

        Raises
        ------
        ValueError
            If *regex* is True and the pattern cannot be compiled.
        """
        _start_time = time.monotonic()
        logger.info(
            "batch_revert started: pattern=%r, regex=%s, case_insensitive=%s, "
            "language=%s, video_ids=%s, dry_run=%s, batch_size=%d",
            pattern,
            regex,
            case_insensitive,
            language,
            video_ids,
            dry_run,
            batch_size,
        )

        # Step 1: Validate pattern
        self._validate_pattern(pattern, regex=regex)

        # Step 2: Count total segments in filter scope
        total_scanned = await self._segment_repo.count_filtered(
            session,
            language=language,
            video_ids=video_ids,
        )

        # Step 3: Find matching segments (searches effective text)
        matched_segments = await self._segment_repo.find_by_text_pattern(
            session,
            pattern=pattern,
            regex=regex,
            case_insensitive=case_insensitive,
            language=language,
            video_ids=video_ids,
        )

        # Step 4: Filter to only segments with active corrections
        corrected_matches = [
            seg for seg in matched_segments if seg.has_correction
        ]

        # Step 5: Discover cross-segment partners (T038)
        # For each matched segment, check if its latest correction has a
        # [cross-segment:partner=N] marker.  If so, include the partner
        # in the revert set even if it didn't match the search pattern.
        seen_segment_ids = {seg.id for seg in corrected_matches}
        partner_segments: list[Any] = []
        # Maps segment_id → partner_segment_id for display purposes
        partner_map: dict[int, int] = {}

        for seg in corrected_matches:
            partner_id = await self._get_cross_segment_partner_id(
                session, seg
            )
            if partner_id is not None and partner_id not in seen_segment_ids:
                partner_seg = await session.get(
                    TranscriptSegmentDB, partner_id
                )
                if partner_seg is not None and partner_seg.has_correction:
                    partner_segments.append(partner_seg)
                    seen_segment_ids.add(partner_id)
                    partner_map[seg.id] = partner_id
                elif partner_seg is None:
                    # T039: Missing partner — log warning, continue
                    logger.warning(
                        "Cross-segment partner segment %d not found "
                        "(may have been re-downloaded). Reverting only "
                        "the surviving segment %d.",
                        partner_id,
                        seg.id,
                    )

        all_to_revert = list(corrected_matches) + partner_segments
        total_matched = len(all_to_revert)
        partner_cascade_count = len(partner_segments)

        # ------ Dry-run mode ------
        if dry_run:
            # Return tuples with 5 elements: the 5th is a bool indicating
            # whether the segment was added via partner cascade.
            previews: list[tuple[str, int, float, str, bool]] = []
            for seg in corrected_matches:
                previews.append((
                    seg.video_id,
                    seg.id,
                    seg.start_time,
                    seg.corrected_text or "",
                    False,
                ))
            for seg in partner_segments:
                previews.append((
                    seg.video_id,
                    seg.id,
                    seg.start_time,
                    seg.corrected_text or "",
                    True,
                ))
            _elapsed = time.monotonic() - _start_time
            logger.info(
                "batch_revert completed (dry_run): matched=%d, "
                "partner_cascade=%d, duration=%.2fs",
                len(previews),
                partner_cascade_count,
                _elapsed,
            )
            return previews

        # ------ Live mode ------
        unique_video_ids = {seg.video_id for seg in all_to_revert}
        unique_videos = len(unique_video_ids)

        if total_matched == 0:
            _elapsed = time.monotonic() - _start_time
            logger.info(
                "batch_revert completed (zero matches): scanned=%d, duration=%.2fs",
                total_scanned,
                _elapsed,
            )
            return BatchCorrectionResult(
                total_scanned=total_scanned,
                total_matched=0,
                total_applied=0,
                total_skipped=0,
                total_failed=0,
                failed_batches=0,
                unique_videos=0,
            )

        # Track which segments have already been reverted (to avoid
        # double-reverting when both segments in a pair match the pattern).
        reverted_ids: set[int] = set()

        async def _revert_one(session: AsyncSession, segment: Any) -> str:
            if segment.id in reverted_ids:
                return "skipped"
            try:
                await self._correction_service.revert_correction(
                    session,
                    segment_id=segment.id,
                )
                reverted_ids.add(segment.id)
            except ValueError:
                return "skipped"
            return "applied"

        total_applied, total_skipped, total_failed, failed_batches = (
            await self._process_in_batches(
                session,
                all_to_revert,
                _revert_one,
                batch_size=batch_size,
                progress_callback=progress_callback,
            )
        )

        _elapsed = time.monotonic() - _start_time
        logger.info(
            "batch_revert completed: scanned=%d, matched=%d, applied=%d, "
            "skipped=%d, failed=%d, failed_batches=%d, unique_videos=%d, "
            "partner_cascade=%d, duration=%.2fs",
            total_scanned,
            total_matched,
            total_applied,
            total_skipped,
            total_failed,
            failed_batches,
            unique_videos,
            partner_cascade_count,
            _elapsed,
        )

        return BatchCorrectionResult(
            total_scanned=total_scanned,
            total_matched=total_matched,
            total_applied=total_applied,
            total_skipped=total_skipped,
            total_failed=total_failed,
            failed_batches=failed_batches,
            unique_videos=unique_videos,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _compute_replacement_with_timeout(
        self,
        effective_text: str,
        pattern: str,
        replacement: str,
        regex: bool,
        re_flags: int,
        case_insensitive: bool,
    ) -> str:
        """
        Compute replacement text with regex timeout enforcement (T011).

        Wraps the regex compilation and substitution in an asyncio timeout
        to prevent catastrophic backtracking from blocking the event loop.

        Parameters
        ----------
        effective_text : str
            The current segment text.
        pattern : str
            The search pattern.
        replacement : str
            The replacement text.
        regex : bool
            Whether the pattern is a regex.
        re_flags : int
            Pre-computed regex flags.
        case_insensitive : bool
            Whether matching is case-insensitive.

        Returns
        -------
        str
            The text after replacement.

        Raises
        ------
        ValueError
            If regex operations time out.
        """
        def _do_replace() -> str:
            if regex:
                return re.sub(pattern, replacement, effective_text, flags=re_flags)
            if case_insensitive:
                return re.sub(
                    re.escape(pattern),
                    replacement,
                    effective_text,
                    flags=re.IGNORECASE,
                )
            return effective_text.replace(pattern, replacement)

        if not regex:
            # No timeout needed for non-regex operations
            return _do_replace()

        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _do_replace),
                timeout=self._REGEX_TIMEOUT_SECONDS,
            )
            return result
        except asyncio.TimeoutError:
            raise ValueError(
                "Pattern timed out after 5 seconds \u2014 simplify your regex"
            )

    @staticmethod
    def _find_match_offsets(
        text: str,
        pattern: str,
        regex: bool,
        re_flags: int,
        case_insensitive: bool,
    ) -> tuple[int, int]:
        """
        Find the character offsets of the first match in *text*.

        Parameters
        ----------
        text : str
            The text to search.
        pattern : str
            The search pattern.
        regex : bool
            Whether the pattern is a regex.
        re_flags : int
            Pre-computed regex flags.
        case_insensitive : bool
            Whether matching is case-insensitive.

        Returns
        -------
        tuple[int, int]
            ``(match_start, match_end)`` character offsets, or
            ``(0, 0)`` if no match is found.
        """
        if regex:
            m = re.search(pattern, text, flags=re_flags)
        elif case_insensitive:
            m = re.search(re.escape(pattern), text, flags=re.IGNORECASE)
        else:
            idx = text.find(pattern)
            if idx >= 0:
                return idx, idx + len(pattern)
            return 0, 0

        if m:
            return m.start(), m.end()
        return 0, 0

    async def _batch_fetch_context_segments(
        self,
        session: AsyncSession,
        matched_segments: Sequence[Any],
        cross_segment_matches: list[CrossSegmentMatch],
        context_map: dict[int, tuple[str | None, str | None]],
    ) -> None:
        """
        Batch-fetch context segments (prev/next by sequence_number).

        For each matched segment, queries the previous and next segment's
        effective text and populates *context_map* keyed by segment ID.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        matched_segments : Sequence
            Single-segment matches.
        cross_segment_matches : list[CrossSegmentMatch]
            Cross-segment matches.
        context_map : dict[int, tuple[str | None, str | None]]
            Output map: segment_id -> (context_before, context_after).
        """
        # Collect all segment info we need context for
        segments_info: list[tuple[int, str, str, int]] = []
        for seg in matched_segments:
            segments_info.append((
                seg.id, seg.video_id, seg.language_code, seg.sequence_number,
            ))
        for csm in cross_segment_matches:
            for seg in (csm.pair.segment_a, csm.pair.segment_b):
                segments_info.append((
                    seg.id, seg.video_id, seg.language_code,
                    seg.sequence_number,
                ))

        if not segments_info:
            return

        # Batch query: for each (video_id, language_code), get all segments
        # in that group that are neighbors of our matched segments.
        # Build a set of (video_id, lang, seq_num +/- 1) to query.
        neighbor_keys: set[tuple[str, str, int]] = set()
        for _seg_id, vid, lang, seq in segments_info:
            neighbor_keys.add((vid, lang, seq - 1))
            neighbor_keys.add((vid, lang, seq + 1))

        # Group by (video_id, language_code) for efficient querying
        from collections import defaultdict

        grouped: dict[tuple[str, str], set[int]] = defaultdict(set)
        for vid, lang, seq in neighbor_keys:
            if seq >= 0:
                grouped[(vid, lang)].add(seq)

        # Fetch all needed neighbor segments
        neighbor_map: dict[tuple[str, str, int], str] = {}
        for (vid, lang), seq_nums in grouped.items():
            result = await session.execute(
                select(
                    TranscriptSegmentDB.sequence_number,
                    TranscriptSegmentDB.text,
                    TranscriptSegmentDB.corrected_text,
                    TranscriptSegmentDB.has_correction,
                ).where(
                    and_(
                        TranscriptSegmentDB.video_id == vid,
                        TranscriptSegmentDB.language_code == lang,
                        TranscriptSegmentDB.sequence_number.in_(list(seq_nums)),
                    )
                )
            )
            for row in result.all():
                eff = (
                    row.corrected_text if row.has_correction else row.text
                ) or ""
                neighbor_map[(vid, lang, row.sequence_number)] = eff

        # Populate context_map
        for seg_id, vid, lang, seq in segments_info:
            before = neighbor_map.get((vid, lang, seq - 1))
            after = neighbor_map.get((vid, lang, seq + 1))
            context_map[seg_id] = (before, after)

    _CROSS_SEGMENT_PARTNER_RE = re.compile(
        r"\[cross-segment:partner=(\d+)\]"
    )

    async def _get_cross_segment_partner_id(
        self,
        session: AsyncSession,
        segment: Any,
    ) -> int | None:
        """
        Check whether a segment's latest correction has a cross-segment
        partner marker and return the partner segment ID if found.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        segment : TranscriptSegmentDB
            The segment to inspect.

        Returns
        -------
        int or None
            The partner segment ID, or ``None`` if no marker is present.
        """
        # Query the latest correction record for this segment
        latest_records = await self._correction_repo.get_by_segment(
            session,
            segment.video_id,
            segment.language_code,
            segment.id,
            limit=1,
        )
        if not latest_records:
            return None

        latest = latest_records[0]
        if not latest.correction_note:
            return None

        match = self._CROSS_SEGMENT_PARTNER_RE.search(
            latest.correction_note
        )
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_pattern_tokens(pattern: str, regex: bool) -> list[str]:
        """
        Extract meaningful word tokens from a search pattern for pre-filtering.

        For plain substring patterns the words are the whitespace-split tokens
        of the pattern itself (e.g. "Shine Bomb" -> ["Shine", "Bomb"]).

        For regex patterns we strip all regex metacharacters and split on
        whitespace, returning only tokens that are three or more characters
        long to avoid overly broad LIKE conditions.

        Single-token patterns (or regex patterns that reduce to nothing useful)
        return the original pattern string as the sole token so the caller can
        still do a simple LIKE scan.

        Parameters
        ----------
        pattern : str
            The raw search pattern.
        regex : bool
            Whether the pattern is a regular expression.

        Returns
        -------
        list of str
            Non-empty tokens suitable for ``LIKE '%token%'`` queries.
        """
        if not regex:
            tokens = pattern.split()
            return [t for t in tokens if t] or [pattern]

        # For regex: strip metacharacters and word-boundary escape sequences
        # first, then keep alphanumeric runs of length >= 3.
        # Order matters: strip \b, \B, \d, \w etc. before stripping lone backslashes
        # so that "bShine" is not left as a token when the input was "\bShine\b".
        stripped = re.sub(r"\\[a-zA-Z]", " ", pattern)          # \b \B \d \w …
        stripped = re.sub(r"[\\^$.*+?()[\]{}|]", " ", stripped)  # remaining metas
        tokens = [t for t in stripped.split() if len(t) >= 3]
        return tokens if tokens else [pattern]

    async def _get_candidate_video_ids(
        self,
        session: AsyncSession,
        *,
        pattern: str,
        regex: bool,
        case_insensitive: bool,
        language: str | None,
        channel: str | None,
    ) -> list[str]:
        """
        Return video_ids that are candidates for cross-segment matches.

        Runs a lightweight ``SELECT DISTINCT video_id`` query that checks
        segment text for the presence of any token extracted from the pattern.
        This narrows the segment fetch from the entire database down to only
        videos that could plausibly contain a cross-segment match.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        pattern : str
            The search pattern.
        regex : bool
            Whether the pattern is a regular expression.
        case_insensitive : bool
            Whether matching should be case-insensitive.
        language : str or None
            Language filter forwarded to the repository.
        channel : str or None
            Channel filter forwarded to the repository.

        Returns
        -------
        list of str
            Candidate video_ids (may be an empty list if no segments match).
        """
        tokens = self._extract_pattern_tokens(pattern, regex)
        logger.debug(
            "Cross-segment pre-filter: querying candidate video_ids for tokens %r",
            tokens,
        )
        return await self._segment_repo.find_candidate_video_ids_for_cross_segment(
            session,
            tokens=tokens,
            language=language,
            channel=channel,
            case_insensitive=case_insensitive,
        )

    async def _find_cross_segment_matches(
        self,
        session: AsyncSession,
        *,
        pattern: str,
        replacement: str,
        regex: bool,
        case_insensitive: bool,
        re_flags: int,
        language: str | None,
        channel: str | None,
        video_ids: list[str] | None,
        single_segment_ids: set[int],
    ) -> list[CrossSegmentMatch]:
        """
        Find cross-segment pattern matches (T020-T022).

        Fetches all segments in scope, groups by (video_id, language_code),
        pairs strictly consecutive segments, and matches the pattern against
        the combined text of each pair. Only matches that span the boundary
        between the two segments are considered cross-segment matches.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        pattern : str
            Search pattern (substring or regex).
        replacement : str
            Replacement text.
        regex : bool
            Whether pattern is a regex.
        case_insensitive : bool
            Whether to use case-insensitive matching.
        re_flags : int
            Pre-computed regex flags.
        language : str or None
            Language filter.
        channel : str or None
            Channel filter.
        video_ids : list[str] or None
            Video ID filter.
        single_segment_ids : set[int]
            IDs of segments already matched by single-segment matching.
            These segments are excluded from cross-segment pairing.

        Returns
        -------
        list[CrossSegmentMatch]
            Cross-segment matches found, with replacement text split
            across the two segments.
        """
        # T020: Fetch segments in scope.
        #
        # Optimization: when no video_ids filter is provided by the caller we
        # perform a lightweight pre-filter query that returns only the
        # video_ids whose segments contain at least one token from the
        # pattern.  This avoids loading every segment in the database for
        # broad searches (e.g. no video_id / no channel / no language filter).
        #
        # The pre-filter is intentionally a superset — it may return video_ids
        # that ultimately produce zero cross-segment matches, but it will never
        # omit a video that could produce one.
        scoped_video_ids = video_ids
        if video_ids is None:
            candidate_ids = await self._get_candidate_video_ids(
                session,
                pattern=pattern,
                regex=regex,
                case_insensitive=case_insensitive,
                language=language,
                channel=channel,
            )
            if not candidate_ids:
                logger.info(
                    "Cross-segment pre-filter returned 0 candidate videos — "
                    "no cross-segment matches possible"
                )
                return []
            scoped_video_ids = candidate_ids
            logger.debug(
                "Cross-segment pre-filter narrowed scope to %d candidate video(s)",
                len(scoped_video_ids),
            )

        all_segments = await self._segment_repo.find_segments_in_scope(
            session,
            language=language,
            channel=channel,
            video_ids=scoped_video_ids,
        )

        # Group by (video_id, language_code)
        from collections import defaultdict

        groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
        for seg in all_segments:
            groups[(seg.video_id, seg.language_code)].append(seg)

        # Build pairs of strictly consecutive segments
        pairs: list[SegmentPair] = []
        for _key, segs in groups.items():
            # Segments are already ordered by sequence_number from the repo
            for i in range(len(segs) - 1):
                seg_a = segs[i]
                seg_b = segs[i + 1]

                # Strictly consecutive: seq_b == seq_a + 1
                if seg_b.sequence_number != seg_a.sequence_number + 1:
                    continue

                # Exclude pairs where either segment has a single-segment match
                if seg_a.id in single_segment_ids or seg_b.id in single_segment_ids:
                    continue

                # Get effective text
                eff_a: str = (
                    seg_a.corrected_text if seg_a.has_correction else seg_a.text
                ) or ""
                eff_b: str = (
                    seg_b.corrected_text if seg_b.has_correction else seg_b.text
                ) or ""

                # Strip whitespace at boundary
                eff_a_stripped = eff_a.rstrip()
                eff_b_stripped = eff_b.lstrip()

                # Skip pairs where either segment has empty effective text
                if not eff_a_stripped or not eff_b_stripped:
                    continue

                # Build combined text and boundary offset
                combined = eff_a_stripped + " " + eff_b_stripped
                boundary = len(eff_a_stripped)

                pairs.append(SegmentPair(
                    segment_a=seg_a,
                    segment_b=seg_b,
                    combined_text=combined,
                    boundary_offset=boundary,
                ))

        # T021: Match pattern against combined text
        # T022: Conflict detection — track claimed segment IDs
        claimed_ids: set[int] = set()
        matches: list[CrossSegmentMatch] = []

        for pair in pairs:
            # Skip if either segment already claimed by a prior cross-segment pair
            if pair.segment_a.id in claimed_ids or pair.segment_b.id in claimed_ids:
                logger.warning(
                    "Cross-segment conflict: segment %d or %d already claimed "
                    "by an earlier pair — skipping pair (seq %d, %d)",
                    pair.segment_a.id,
                    pair.segment_b.id,
                    pair.segment_a.sequence_number,
                    pair.segment_b.sequence_number,
                )
                continue

            combined = pair.combined_text
            boundary = pair.boundary_offset

            # Find matches in combined text
            if regex:
                found_matches = list(
                    re.finditer(pattern, combined, flags=re_flags)
                )
            else:
                # Build match objects for substring search
                search_pattern = re.escape(pattern)
                flags = re.IGNORECASE if case_insensitive else 0
                found_matches = list(
                    re.finditer(search_pattern, combined, flags=flags)
                )

            # Filter to matches that span the boundary
            # A match spans the boundary if it starts at or before boundary
            # AND ends after boundary (the space at position boundary)
            cross_matches = [
                m for m in found_matches
                if m.start() <= boundary and m.end() > boundary
            ]

            if not cross_matches:
                continue

            # Take the first boundary-spanning match (non-overlapping patterns
            # can produce at most one match spanning any given position)
            match = cross_matches[0]
            ms, me = match.start(), match.end()

            # Compute replacement text for each segment
            # For regex with backreferences, use match.expand()
            actual_replacement = match.expand(replacement) if regex else replacement

            # Decompose: replacement goes entirely into seg A,
            # matched fragment removed from seg B
            eff_a_stripped = combined[:boundary]
            eff_b_stripped = combined[boundary + 1:]  # skip the space

            new_a = eff_a_stripped[:ms] + actual_replacement
            b_consumed = me - (boundary + 1)  # chars of seg B consumed by match
            new_b = eff_b_stripped[b_consumed:]

            # Whitespace normalize
            new_a = " ".join(new_a.split()).strip()
            new_b = " ".join(new_b.split()).strip()

            # Warn if seg B becomes empty (FR-008)
            if not new_b.strip():
                logger.warning(
                    "Cross-segment correction left segment %d "
                    "(seq %d) empty or whitespace-only (FR-008)",
                    pair.segment_b.id,
                    pair.segment_b.sequence_number,
                )

            csm = CrossSegmentMatch(
                pair=pair,
                match_start=ms,
                match_end=me,
                text_for_seg_a=new_a,
                text_for_seg_b=new_b,
            )
            matches.append(csm)

            # Claim both segments
            claimed_ids.add(pair.segment_a.id)
            claimed_ids.add(pair.segment_b.id)

        logger.info(
            "Cross-segment matching: %d pairs evaluated, %d matches found",
            len(pairs),
            len(matches),
        )
        return matches

    async def _apply_cross_segment_corrections(
        self,
        session: AsyncSession,
        matches: list[CrossSegmentMatch],
        *,
        correction_type: CorrectionType,
        correction_note: str | None,
        batch_size: int,
        progress_callback: Callable[[int], None] | None = None,
    ) -> tuple[int, int, int, int]:
        """
        Apply cross-segment corrections (T023-T025).

        For each cross-segment match, applies corrections to both segments
        in the pair using ``TranscriptCorrectionService.apply_correction``.
        Each segment gets a correction note indicating its cross-segment
        partner.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        matches : list[CrossSegmentMatch]
            Cross-segment matches to apply.
        correction_type : CorrectionType
            Category of correction.
        correction_note : str or None
            Base correction note.
        batch_size : int
            Number of pairs per transaction chunk.
        progress_callback : Callable or None
            Progress callback.

        Returns
        -------
        tuple[int, int, int, int]
            ``(total_applied, total_skipped, total_failed, failed_batches)``
        """
        total_applied = 0
        total_skipped = 0
        total_failed = 0
        failed_batches = 0

        # Process in batches (batch_size counts pairs)
        for offset in range(0, len(matches), batch_size):
            chunk = matches[offset:offset + batch_size]
            try:
                chunk_applied = 0
                chunk_skipped = 0

                for csm in chunk:
                    pair = csm.pair
                    seg_a = pair.segment_a
                    seg_b = pair.segment_b

                    # T025: Correction notes with cross-segment partner info
                    note_a = (
                        f"{correction_note} " if correction_note else ""
                    ) + f"[cross-segment:partner={seg_b.id}]"
                    note_b = (
                        f"{correction_note} " if correction_note else ""
                    ) + f"[cross-segment:partner={seg_a.id}]"

                    # Apply correction to segment A
                    a_applied = False
                    try:
                        await self._correction_service.apply_correction(
                            session,
                            video_id=seg_a.video_id,
                            language_code=seg_a.language_code,
                            segment_id=seg_a.id,
                            corrected_text=csm.text_for_seg_a,
                            correction_type=correction_type,
                            correction_note=note_a,
                            corrected_by_user_id=ACTOR_CLI_BATCH,
                        )
                        a_applied = True
                    except ValueError:
                        # No-op: text unchanged
                        pass

                    # Apply correction to segment B
                    # FR-008: if correction empties seg B, use a single space
                    # to preserve truthiness (Python "" is falsy, which breaks
                    # the standard ``corrected_text or text`` pattern used in
                    # downstream reads).
                    b_corrected_text = csm.text_for_seg_b or " "
                    b_applied = False
                    try:
                        await self._correction_service.apply_correction(
                            session,
                            video_id=seg_b.video_id,
                            language_code=seg_b.language_code,
                            segment_id=seg_b.id,
                            corrected_text=b_corrected_text,
                            correction_type=correction_type,
                            correction_note=note_b,
                            corrected_by_user_id=ACTOR_CLI_BATCH,
                        )
                        b_applied = True
                    except ValueError:
                        # No-op: text unchanged
                        pass

                    if a_applied or b_applied:
                        chunk_applied += (1 if a_applied else 0) + (
                            1 if b_applied else 0
                        )
                    else:
                        chunk_skipped += 2

                await session.commit()
                total_applied += chunk_applied
                total_skipped += chunk_skipped

                logger.debug(
                    "Cross-segment batch committed: offset=%d, applied=%d, "
                    "skipped=%d",
                    offset,
                    chunk_applied,
                    chunk_skipped,
                )
            except Exception:
                await session.rollback()
                failed_batches += 1
                total_failed += len(chunk) * 2  # 2 segments per pair

                logger.warning(
                    "Cross-segment batch failed and rolled back: "
                    "offset=%d, chunk_size=%d",
                    offset,
                    len(chunk),
                    exc_info=True,
                )

            if progress_callback is not None:
                progress_callback(len(chunk))

        return total_applied, total_skipped, total_failed, failed_batches

    async def _process_in_batches(
        self,
        session: AsyncSession,
        items: Sequence[T],
        process_fn: Callable[[AsyncSession, T], Awaitable[str]],
        *,
        batch_size: int = 100,
        progress_callback: Callable[[int], None] | None = None,
    ) -> tuple[int, int, int, int]:
        """
        Process *items* in transaction-safe chunks of *batch_size*.

        After each chunk the session is committed.  If a chunk raises an
        exception the session is rolled back, the ``failed_batches`` counter
        is incremented, and processing continues with the next chunk.

        The *process_fn* is an async callable that receives ``(session, item)``
        and returns a status string:

        * ``"applied"`` — the correction was applied successfully.
        * ``"skipped"`` — the item was a no-op (e.g. text already matches).
        * Any other value is treated as ``"applied"``.

        Parameters
        ----------
        session : AsyncSession
            Database session (this method manages commit/rollback).
        items : Sequence[T]
            Items to process.
        process_fn : Callable[[AsyncSession, T], Awaitable[str]]
            Async callable invoked once per item.  Must return ``"applied"``
            or ``"skipped"``.
        batch_size : int, optional
            Number of items per transaction chunk (default 100).
        progress_callback : Callable[[int], None] or None, optional
            Called with the chunk length after each chunk completes (both
            success and failure).

        Returns
        -------
        tuple[int, int, int, int]
            ``(total_applied, total_skipped, total_failed, failed_batches)``
        """
        total_applied = 0
        total_skipped = 0
        total_failed = 0
        failed_batches = 0

        for offset in range(0, len(items), batch_size):
            chunk = items[offset : offset + batch_size]
            try:
                chunk_applied = 0
                chunk_skipped = 0
                for item in chunk:
                    status = await process_fn(session, item)
                    if status == "skipped":
                        chunk_skipped += 1
                    else:
                        chunk_applied += 1

                await session.commit()
                total_applied += chunk_applied
                total_skipped += chunk_skipped

                logger.debug(
                    "Batch committed: offset=%d, applied=%d, skipped=%d",
                    offset,
                    chunk_applied,
                    chunk_skipped,
                )
            except Exception:
                await session.rollback()
                failed_batches += 1
                total_failed += len(chunk)

                logger.warning(
                    "Batch failed and rolled back: offset=%d, chunk_size=%d",
                    offset,
                    len(chunk),
                    exc_info=True,
                )

            if progress_callback is not None:
                progress_callback(len(chunk))

        return total_applied, total_skipped, total_failed, failed_batches

    async def _record_asr_alias_for_batch_replacement(
        self,
        session: AsyncSession,
        *,
        pattern: str,
        replacement: str,
        total_applied: int,
    ) -> None:
        """Best-effort hook: register the search pattern as an ASR error alias.

        Delegates to :func:`~chronovista.services.asr_alias_registry.register_asr_alias`.
        """
        from chronovista.services.asr_alias_registry import register_asr_alias

        await register_asr_alias(
            session,
            original_text=pattern,
            corrected_text=replacement,
            occurrence_count=total_applied,
            commit=True,
            log_prefix="find-replace",
        )

    @staticmethod
    def _validate_pattern(pattern: str, *, regex: bool) -> None:
        """
        Pre-validate a search pattern before constructing SQL queries.

        When *regex* is ``True``, attempts to compile the pattern using
        ``re.compile`` and raises ``ValueError`` with a user-friendly
        message if the pattern is invalid.  When *regex* is ``False``
        (substring matching), no validation is performed.

        Parameters
        ----------
        pattern : str
            The search pattern (substring or regex).
        regex : bool
            Whether to treat *pattern* as a regular expression.

        Raises
        ------
        ValueError
            If *regex* is ``True`` and the pattern cannot be compiled.
        """
        if not regex:
            return

        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"Invalid regex pattern '{pattern}': {exc}"
            ) from exc


__all__ = ["BatchCorrectionService"]
