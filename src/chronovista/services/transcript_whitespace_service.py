"""Whitespace-normalization backfill for transcript segment text (#293, US3).

Normalizes the stored ``text`` of transcript segments that carry whitespace
artifacts (newlines / nbsp / other Unicode spaces / zero-width / soft hyphen /
non-NFC), and re-scans the affected videos so their auto-detected entity
mentions are regenerated with offsets that match the normalized text. The raw
caption data (``video_transcripts.raw_transcript_data``) is untouched, so the
in-place rewrite is lossless.

Design (see specs/076-normalize-transcript-whitespace):
- In-place ``UPDATE`` of ``transcript_segments.text`` (preserves the PK, so
  corrections and mentions stay linked); never delete+reinsert segments.
- Per-video commit → resumable. Idempotent: a segment already normalized is a
  no-op, and re-scanning clean text reproduces the same mentions.
- Candidate videos = those with a segment needing normalization OR a
  ``rule_match`` mention whose text still carries an artifact (the latter picks
  up a video whose text was normalized but whose re-scan did not complete on a
  previous interrupted run).
- Re-scan reuses ``EntityMentionScanService.scan(full_rescan=True)``, which
  deletes only ``rule_match`` mentions in scope and preserves ``manual`` /
  ``user_correction`` ones.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from pydantic import BaseModel
from sqlalchemy import distinct, func, or_, select, update
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import EntityMention as EntityMentionDB
from ..db.models import TranscriptSegment as TranscriptSegmentDB
from ..utils.text import normalize_segment_text
from .entity_mention_scan_service import EntityMentionScanService

logger = logging.getLogger(__name__)

# Whitespace code points other than a plain ASCII space (0x20). Any of these in
# stored text means normalization will change it. (Verified: Python ``re \s``
# and ``str.isspace()`` cover the identical set; a plain space only needs
# normalizing when it forms a run or sits at a string edge, handled separately.)
_NON_PLAIN_WHITESPACE = (
    0x09,
    0x0A,
    0x0B,
    0x0C,
    0x0D,
    0x1C,
    0x1D,
    0x1E,
    0x1F,
    0x85,
    0xA0,
    0x1680,
    0x2000,
    0x2001,
    0x2002,
    0x2003,
    0x2004,
    0x2005,
    0x2006,
    0x2007,
    0x2008,
    0x2009,
    0x200A,
    0x2028,
    0x2029,
    0x202F,
    0x205F,
    0x3000,
)
# Invisible formatting characters stripped by the normalizer (not whitespace).
_INVISIBLES = (0x00AD, 0x200B, 0x200C, 0x200D, 0xFEFF)
# A Postgres regex character class matching any artifact character. None of
# these code points are regex-special inside a bracket expression.
_ARTIFACT_CLASS = (
    "[" + "".join(chr(c) for c in (*_NON_PLAIN_WHITESPACE, *_INVISIBLES)) + "]"
)

_RULE_MATCH = "rule_match"


class WhitespaceBackfillSummary(BaseModel):
    """Outcome of a whitespace-normalization backfill run."""

    dry_run: bool
    videos_considered: int = 0
    videos_changed: int = 0
    segments_normalized: int = 0
    mentions_regenerated: int = 0
    videos_failed: int = 0


class TranscriptWhitespaceBackfillService:
    """Normalizes stored segment text and re-scans affected videos (#293)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        scan_service: EntityMentionScanService | None = None,
        rebuild_text: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._scan_service = scan_service or EntityMentionScanService(
            session_factory=session_factory
        )
        # Optional hook to rebuild a video's concatenated transcript_text after
        # normalization (wired by the CLI to BatchCorrectionService.rebuild_text
        # for videos that have corrections); skipped when not provided.
        self._rebuild_text = rebuild_text

    async def _candidate_video_ids(
        self, session: AsyncSession, *, video_id: str | None, limit: int | None
    ) -> list[str]:
        """Return video ids that need normalization and/or a recovery re-scan."""
        if video_id is not None:
            return [video_id]

        seg_q = select(distinct(TranscriptSegmentDB.video_id)).where(
            or_(
                TranscriptSegmentDB.text.op("~")(_ARTIFACT_CLASS),
                TranscriptSegmentDB.text.op("~")("  "),
                TranscriptSegmentDB.text.op("~")("^ "),
                TranscriptSegmentDB.text.op("~")(" $"),
                sql_text("transcript_segments.text IS NOT NFC NORMALIZED"),
            )
        )
        # Resumability: a video whose text was normalized on an interrupted run
        # but whose mentions were not yet regenerated still has rule_match
        # mentions carrying the artifact — pick it up so the re-scan runs.
        mention_q = select(distinct(EntityMentionDB.video_id)).where(
            EntityMentionDB.detection_method == _RULE_MATCH,
            EntityMentionDB.mention_text.op("~")(_ARTIFACT_CLASS),
        )
        seg_ids = set((await session.execute(seg_q)).scalars().all())
        mention_ids = set((await session.execute(mention_q)).scalars().all())
        ordered = sorted(seg_ids | mention_ids)
        return ordered[:limit] if limit is not None else ordered

    async def run(
        self,
        *,
        apply: bool = False,
        video_id: str | None = None,
        limit: int | None = None,
    ) -> WhitespaceBackfillSummary:
        """Normalize affected segments and re-scan their videos.

        Parameters
        ----------
        apply : bool
            When False (default), report the projected scope and write nothing.
        video_id : str | None
            Restrict to a single video (verification / staged runs).
        limit : int | None
            Process at most this many videos.
        """
        summary = WhitespaceBackfillSummary(dry_run=not apply)

        async with self._session_factory() as session:
            video_ids = await self._candidate_video_ids(
                session, video_id=video_id, limit=limit
            )
        summary.videos_considered = len(video_ids)

        for vid in video_ids:
            try:
                changed = await self._process_video(vid, apply=apply)
            except Exception:  # noqa: BLE001 — one bad video must not abort the run
                logger.exception("Whitespace backfill failed for video %s", vid)
                summary.videos_failed += 1
                continue
            if changed.segments_normalized or changed.mentions_regenerated:
                summary.videos_changed += 1
                summary.segments_normalized += changed.segments_normalized
                summary.mentions_regenerated += changed.mentions_regenerated

        return summary

    async def _process_video(
        self, video_id: str, *, apply: bool
    ) -> WhitespaceBackfillSummary:
        """Process one video; commit its own transaction (resumable unit)."""
        result = WhitespaceBackfillSummary(dry_run=not apply)

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(TranscriptSegmentDB.id, TranscriptSegmentDB.text).where(
                        TranscriptSegmentDB.video_id == video_id
                    )
                )
            ).all()
            changed: list[tuple[int, str]] = []
            offset_shifting = False
            for seg_id, text_val in rows:
                if text_val is None:
                    continue
                normalized = normalize_segment_text(text_val)
                if normalized != text_val:
                    changed.append((seg_id, normalized))
                    if len(normalized) != len(text_val):
                        # Length changed (invisible stripped / whitespace run
                        # collapsed) → character offsets after that point shift,
                        # so the re-scan is essential to fix mention offsets.
                        offset_shifting = True

            result.segments_normalized = len(changed)

            if not apply:
                # Dry run: also report how many rule_match mentions would be
                # regenerated (deleted + re-detected) for a changed video.
                if changed:
                    result.mentions_regenerated = int(
                        (
                            await session.execute(
                                select(func.count())
                                .select_from(EntityMentionDB)
                                .where(
                                    EntityMentionDB.video_id == video_id,
                                    EntityMentionDB.detection_method == _RULE_MATCH,
                                )
                            )
                        ).scalar_one()
                    )
                return result

            if not changed:
                return result

            for seg_id, normalized in changed:
                await session.execute(
                    update(TranscriptSegmentDB)
                    .where(TranscriptSegmentDB.id == seg_id)
                    .values(text=normalized)
                )
            await session.commit()

        if offset_shifting:
            # The text update committed and length shifted, so existing mention
            # offsets for this video are now stale until the re-scan below runs.
            # If the process is hard-killed between here and the re-scan, resume
            # will not auto-detect this video (its text is already clean); re-run
            # with --video-id for any video named here.
            logger.warning(
                "Whitespace backfill: video %s had offset-shifting normalization; "
                "re-scan is required — re-run with --video-id %s if interrupted "
                "before completion.",
                video_id,
                video_id,
            )

        # Re-scan on the now-normalized text (its own session/transaction):
        # deletes only rule_match mentions for this video and regenerates them
        # with valid offsets; manual / correction mentions are preserved.
        scan_result = await self._scan_service.scan(
            video_ids=[video_id], full_rescan=True
        )
        result.mentions_regenerated = scan_result.mentions_found

        if self._rebuild_text is not None:
            await self._rebuild_text(video_id)

        return result
