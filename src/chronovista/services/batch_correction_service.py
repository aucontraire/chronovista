"""
Batch correction service for orchestrating bulk transcript corrections.

Provides configurable transaction batching with commit/rollback per chunk,
regex pre-validation, progress reporting, and find-and-replace with both
live and dry-run modes.

Feature 036 — Batch Correction Tools (T009, T010, T011, T017, T019, T021, T023, T025)
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.batch_correction_models import (
    BatchCorrectionResult,
    CorrectionExportRecord,
    CorrectionPattern,
    CorrectionStats,
)
from chronovista.models.correction_actors import ACTOR_CLI_BATCH
from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.enums import CorrectionType, EntityAliasType
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
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
    # Public API
    # ------------------------------------------------------------------

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
        correction_type: CorrectionType = CorrectionType.ASR_ERROR,
        correction_note: str | None = None,
        batch_size: int = 100,
        dry_run: bool = False,
        progress_callback: Callable[[int], None] | None = None,
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
            Category of correction (default ``CorrectionType.ASR_ERROR``).
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
            "language=%s, channel=%s, video_ids=%s, dry_run=%s, batch_size=%d",
            pattern,
            regex,
            case_insensitive,
            language,
            channel,
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
            channel=channel,
            video_ids=video_ids,
        )

        # Step 3: Find matching segments
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

        # ------ Dry-run mode ------
        if dry_run:
            previews: list[tuple[str, int, float, str, str]] = []
            for segment in matched_segments:
                effective_text = (
                    segment.corrected_text
                    if segment.has_correction
                    else segment.text
                ) or ""
                new_text = _compute_new_text(segment)
                previews.append((
                    segment.video_id,
                    segment.id,
                    segment.start_time,
                    effective_text,
                    new_text,
                ))
            _elapsed = time.monotonic() - _start_time
            logger.info(
                "find_and_replace completed (dry_run): matched=%d, duration=%.2fs",
                len(previews),
                _elapsed,
            )
            return previews

        # ------ Live mode ------
        # Count unique videos among matched segments
        unique_video_ids = {seg.video_id for seg in matched_segments}
        unique_videos = len(unique_video_ids)

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
            "duration=%.2fs",
            total_scanned,
            total_matched,
            total_applied,
            total_skipped,
            total_failed,
            failed_batches,
            unique_videos,
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
                if isinstance(obj, (UUID, datetime)):
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
    ) -> BatchCorrectionResult | list[tuple[str, int, float, str]]:
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

        total_matched = len(corrected_matches)

        # ------ Dry-run mode ------
        if dry_run:
            previews: list[tuple[str, int, float, str]] = []
            for seg in corrected_matches:
                previews.append((
                    seg.video_id,
                    seg.id,
                    seg.start_time,
                    seg.corrected_text or "",
                ))
            _elapsed = time.monotonic() - _start_time
            logger.info(
                "batch_revert completed (dry_run): matched=%d, duration=%.2fs",
                len(previews),
                _elapsed,
            )
            return previews

        # ------ Live mode ------
        unique_video_ids = {seg.video_id for seg in corrected_matches}
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

        async def _revert_one(session: AsyncSession, segment: Any) -> str:
            try:
                await self._correction_service.revert_correction(
                    session,
                    segment_id=segment.id,
                )
            except ValueError:
                return "skipped"
            return "applied"

        total_applied, total_skipped, total_failed, failed_batches = (
            await self._process_in_batches(
                session,
                list(corrected_matches),
                _revert_one,
                batch_size=batch_size,
                progress_callback=progress_callback,
            )
        )

        _elapsed = time.monotonic() - _start_time
        logger.info(
            "batch_revert completed: scanned=%d, matched=%d, applied=%d, "
            "skipped=%d, failed=%d, failed_batches=%d, unique_videos=%d, "
            "duration=%.2fs",
            total_scanned,
            total_matched,
            total_applied,
            total_skipped,
            total_failed,
            failed_batches,
            unique_videos,
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

        If ``replacement`` matches a known entity canonical name or alias
        (case-insensitive exact match), register ``pattern`` as an
        ``asr_error`` alias for that entity.  If the alias already exists,
        increment its ``occurrence_count`` by ``total_applied``.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        pattern : str
            The search text (potential ASR error form).
        replacement : str
            The replacement text that may match an entity name.
        total_applied : int
            Number of corrections applied (used for occurrence_count).
        """
        try:
            # Resolve entity from replacement text
            entity_id: UUID | None = None
            entity_name: str | None = None

            entity_stmt = select(NamedEntityDB).where(
                NamedEntityDB.status == "active",
                func.lower(NamedEntityDB.canonical_name) == replacement.lower().strip(),
            )
            result = await session.execute(entity_stmt)
            entity = result.scalar_one_or_none()

            if entity is not None:
                entity_id = entity.id
                entity_name = entity.canonical_name
            else:
                # Check aliases for a match
                alias_stmt = select(EntityAliasDB).where(
                    func.lower(EntityAliasDB.alias_name) == replacement.lower().strip(),
                )
                alias_result = await session.execute(alias_stmt)
                matched_alias = alias_result.scalars().first()
                if matched_alias is None:
                    return
                entity_id = matched_alias.entity_id
                entity_name = replacement

            # Check if pattern is already an alias for this entity
            existing_alias_stmt = select(EntityAliasDB).where(
                EntityAliasDB.entity_id == entity_id,
                func.lower(EntityAliasDB.alias_name) == pattern.lower().strip(),
            )
            existing_result = await session.execute(existing_alias_stmt)
            existing_alias = existing_result.scalar_one_or_none()

            if existing_alias is not None:
                existing_alias.occurrence_count = (
                    existing_alias.occurrence_count or 0
                ) + total_applied
                await session.flush()
                await session.commit()
                logger.info(
                    "find-replace alias hook: incremented occurrence_count for "
                    "alias '%s' on entity '%s' (+%d)",
                    pattern,
                    entity_name,
                    total_applied,
                )
            else:
                from chronovista.services.tag_normalization import (
                    TagNormalizationService,
                )

                normalizer = TagNormalizationService()
                normalized = normalizer.normalize(pattern) or pattern.lower()

                new_alias = EntityAliasCreate(
                    entity_id=entity_id,
                    alias_name=pattern,
                    alias_name_normalized=normalized,
                    alias_type=EntityAliasType.ASR_ERROR,
                    occurrence_count=total_applied,
                )
                alias_repo = EntityAliasRepository()
                await alias_repo.create(session, obj_in=new_alias)
                await session.flush()
                await session.commit()
                logger.info(
                    "find-replace alias hook: registered ASR alias '%s' for "
                    "entity '%s' (occurrence_count=%d). Run "
                    "'chronovista entities scan' to update entity mentions.",
                    pattern,
                    entity_name,
                    total_applied,
                )

        except Exception:
            logger.warning(
                "find-replace alias hook failed (non-blocking): "
                "pattern='%s', replacement='%s'",
                pattern,
                replacement,
                exc_info=True,
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
