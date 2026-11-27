"""Repair transcript mentions left stale or duplicated before #426.

Corrections used to leave existing mentions at their old offsets, record only the
corrected fragment of a name, and let a later scan record the same occurrence
again. The write paths no longer do; this repairs rows written before that, by the
same rules, one transcript at a time:

1. A mention that no longer reads as its text
   (:meth:`TranscriptTextIndex.mention_reads`) moves to the nearest occurrence of its
   entity that no kept mention covers: within its segment, or for a split name across
   the same segments. When there is none it is removed: a stale twin of a mention
   that already reads, or the entity is no longer said there.
2. Of overlapping mentions of one entity, one is kept, by
   :meth:`MentionSpan.survivor_rank` (the rule the correction rebase uses too): one
   that counts toward the entity's totals first, so the repair never loses a counted
   occurrence, then the longer name.

Positions are compared in the transcript's assembled text, so a split name and an
alias inside either of its halves are seen to overlap.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator, Sequence

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.models.enums import SCAN_DETECTION_METHODS
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
    MentionMove,
    MentionRelabel,
    MentionSpan,
)
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from chronovista.services.transcript_text_index import TranscriptTextIndex

logger = logging.getLogger(__name__)

# Transcripts repaired per commit. Each commit carries its transcripts' changes and
# their entities' recomputed counters, so an interrupted run leaves no half-done
# transcript and a re-run finishes the rest.
_COMMIT_EVERY = 50


class MentionRepairReport(BaseModel):
    """What a repair found and (unless a dry run) changed."""

    transcripts_examined: int = 0
    stale_moved: int = 0
    stale_removed: int = 0
    duplicates_removed: int = 0
    entities_changed: int = 0
    scopes_invalidated: int = 0
    dry_run: bool = True


class MentionRepairFindings(BaseModel):
    """The rows a repair would treat, by kind (register M1 and M2)."""

    stale: set[uuid.UUID] = set()
    """Mentions that do not read as their text, whether they would move or go."""
    duplicates: set[uuid.UUID] = set()
    """Mentions that would be removed as a second record of one occurrence."""


class _TranscriptPlan(BaseModel):
    removals: list[uuid.UUID] = []
    moves: list[MentionMove] = []
    relabels: list[MentionRelabel] = []
    entities: set[uuid.UUID] = set()
    stale_moved: int = 0
    stale_removed: int = 0
    duplicates_removed: int = 0
    stale_ids: set[uuid.UUID] = set()
    duplicate_ids: set[uuid.UUID] = set()


class MentionRepairService:
    """Plans and applies the repair in the caller's session."""

    def __init__(self) -> None:
        self._mentions = EntityMentionRepository()
        self._detector = EntityMentionScanService()

    async def repair(
        self,
        session: AsyncSession,
        *,
        video_ids: Sequence[str] | None = None,
        dry_run: bool = True,
    ) -> MentionRepairReport:
        """Repair every candidate transcript; on ``dry_run`` only report.

        A real run commits every ``_COMMIT_EVERY`` transcripts. Before writing to a
        transcript it marks the transcript's proximity scope stale, the lock order
        every correction path uses, so it cannot deadlock with a correction running
        at the same time. A dry run writes nothing; the caller rolls it back.
        """
        report = MentionRepairReport(dry_run=dry_run)
        changed_entities: set[uuid.UUID] = set()
        pending: set[uuid.UUID] = set()
        uncommitted = 0
        proximity = EntityPairProximityRepository()
        async for video_id, language_code, plan in self._plans(session, video_ids):
            report.transcripts_examined += 1
            report.stale_moved += plan.stale_moved
            report.stale_removed += plan.stale_removed
            report.duplicates_removed += plan.duplicates_removed
            if not plan.entities:
                continue
            report.scopes_invalidated += 1
            changed_entities |= plan.entities
            if dry_run:
                continue
            await proximity.invalidate_proximity_scopes(
                session,
                video_id=video_id,
                language_code=language_code,
                reason="mention-repair",
            )
            await self._mentions.delete_mentions_by_ids(session, plan.removals)
            await self._mentions.move_mention_offsets(session, plan.moves)
            await self._mentions.relabel_mentions(session, plan.relabels)
            pending |= plan.entities
            uncommitted += 1
            if uncommitted >= _COMMIT_EVERY:
                await self._commit(session, pending)
                pending, uncommitted = set(), 0
        if pending:
            await self._commit(session, pending)
        report.entities_changed = len(changed_entities)
        if not dry_run:
            logger.info("Mention repair applied: %s", report.model_dump())
        return report

    async def findings(
        self, session: AsyncSession, *, video_ids: Sequence[str] | None = None
    ) -> MentionRepairFindings:
        """The stale and duplicate mentions a repair would treat; writes nothing.

        The same plans :meth:`repair` applies, so the audit (register M1, M2) and the
        repair cannot disagree. It sees the repair's candidate transcripts only.
        """
        found = MentionRepairFindings()
        async for _video_id, _language_code, plan in self._plans(session, video_ids):
            found.stale |= plan.stale_ids
            found.duplicates |= plan.duplicate_ids
        return found

    async def _plans(
        self, session: AsyncSession, video_ids: Sequence[str] | None
    ) -> AsyncIterator[tuple[str, str, _TranscriptPlan]]:
        """Each candidate transcript, in order, with its repair plan."""
        transcripts: dict[tuple[str, str], None] = {}
        for (
            _segment_id,
            video_id,
            language_code,
        ) in await self._mentions.mention_repair_candidates(
            session, video_ids=video_ids
        ):
            transcripts[(video_id, language_code)] = None
        for video_id, language_code in transcripts:
            yield video_id, language_code, await self._plan_transcript(
                session, video_id, language_code
            )

    async def _commit(self, session: AsyncSession, entities: set[uuid.UUID]) -> None:
        entity_ids = sorted(entities, key=str)
        await self._mentions.update_entity_counters(session, entity_ids)
        await self._mentions.update_alias_counters(session, entity_ids)
        await session.commit()

    async def _plan_transcript(
        self, session: AsyncSession, video_id: str, language_code: str
    ) -> _TranscriptPlan:
        plan = _TranscriptPlan()
        texts = await self._mentions.transcript_texts(
            session, video_id=video_id, language_code=language_code
        )
        index = TranscriptTextIndex.of(texts)
        text_of = dict(texts)
        spans = await self._mentions.transcript_mention_spans(
            session, transcript=(video_id, language_code)
        )

        def at(span: MentionSpan) -> tuple[int, int] | None:
            return index.locate(
                segment_id=span.segment_id,
                end_segment_id=span.end_segment_id,
                match_start=span.match_start,
                match_end=span.match_end,
            )

        # Where each kept mention lies in the assembled text, and which starts are
        # held (the unique index is per entity, start segment and start offset).
        placed: dict[uuid.UUID, tuple[int, int]] = {}
        stale: list[MentionSpan] = []
        for span in spans:
            located = at(span)
            if located is not None and index.mention_reads(
                segment_id=span.segment_id,
                end_segment_id=span.end_segment_id,
                match_start=span.match_start,
                match_end=span.match_end,
                mention_text=span.mention_text,
            ):
                placed[span.id] = located
            else:
                stale.append(span)
                plan.stale_ids.add(span.id)
        # 1. Stale rows: move to the nearest free occurrence of the entity, else remove.
        current: dict[uuid.UUID, MentionSpan] = {span.id: span for span in spans}
        for span in stale:
            covered = {
                other.id: placed[other.id]
                for other in spans
                if other.id in placed and other.entity_id == span.entity_id
            }
            found = await self._free_occurrence(
                session,
                span,
                index,
                text_of,
                language_code,
                covered,
                current,
            )
            if found is None:
                plan.removals.append(span.id)
                plan.stale_removed += 1
                plan.entities.add(span.entity_id)
                continue
            (start, end), relabel, counts = found
            plan.moves.append(
                MentionMove(
                    id=span.id,
                    match_start=start,
                    match_end=end,
                    start_changed=start != span.match_start,
                )
            )
            if relabel is not None:
                plan.relabels.append(relabel)
            moved = span._replace(
                match_start=start,
                match_end=end,
                mention_text=relabel.mention_text if relabel else span.mention_text,
                detection_method=(
                    relabel.detection_method if relabel else span.detection_method
                ),
                counts=counts,
            )
            current[span.id] = moved
            located = at(moved)
            if located is not None:
                placed[span.id] = located
            plan.stale_moved += 1
            plan.entities.add(span.entity_id)

        # 2. Overlapping kept mentions of one entity: keep the best-ranked one.
        kept: list[uuid.UUID] = []
        for mention_id in sorted(placed, key=lambda i: current[i].survivor_rank()):
            lo, hi = placed[mention_id]
            entity_id = current[mention_id].entity_id
            if any(
                current[other].entity_id == entity_id
                and placed[other][0] < hi
                and lo < placed[other][1]
                for other in kept
            ):
                plan.removals.append(mention_id)
                plan.entities.add(entity_id)
                if any(move.id == mention_id for move in plan.moves):
                    # A stale row moved onto an occurrence a better row holds: it
                    # was a stale twin after all.
                    plan.moves = [m for m in plan.moves if m.id != mention_id]
                    plan.relabels = [r for r in plan.relabels if r.id != mention_id]
                    plan.stale_moved -= 1
                    plan.stale_removed += 1
                else:
                    plan.duplicates_removed += 1
                    plan.duplicate_ids.add(mention_id)
                continue
            kept.append(mention_id)
        return plan

    async def _free_occurrence(
        self,
        session: AsyncSession,
        span: MentionSpan,
        index: TranscriptTextIndex,
        text_of: dict[int, str],
        language_code: str,
        covered: dict[uuid.UUID, tuple[int, int]],
        current: dict[uuid.UUID, MentionSpan],
    ) -> tuple[tuple[int, int], MentionRelabel | None, bool] | None:
        """The occurrence of ``span``'s entity nearest its old start that runs over
        the same segments and that no kept mention of the entity it would lose to
        overlaps: ``((start, end), relabel, counts)``. A row in the way gives way when
        the moved row outranks it on what counts, then length (the survivor rule
        without its tie-breaks: an equal row stands, and this stale row is its twin);
        the duplicate step removes it afterwards. Overlap covers a shared start too:
        every kept row is in ``covered``, and removals are written before moves, so
        the unique index on the start cannot be hit."""
        same_segments = (span.segment_id, span.end_segment_id)
        options: list[tuple[int, int, MentionRelabel | None, bool]] = []
        if (
            span.end_segment_id is None
            and span.detection_method in SCAN_DETECTION_METHODS
        ):
            # A scan row is found again by the scan's own rule.
            for match in await self._detector.detect_in_text(
                session,
                text=text_of.get(span.segment_id, ""),
                language_code=language_code,
                entity_ids=[span.entity_id],
                segment_id=span.segment_id,
            ):
                relabel = None
                if (match.mention_text, match.detection_method.value) != (
                    span.mention_text,
                    span.detection_method,
                ):
                    relabel = MentionRelabel(
                        id=span.id,
                        mention_text=match.mention_text,
                        detection_method=match.detection_method.value,
                        alias_id=match.alias_id,
                    )
                options.append(
                    (match.match_start, match.match_end, relabel, match.counts)
                )
        else:
            # A correction row, or a split name: its own words, case-insensitively.
            for found in re.finditer(
                re.escape(span.mention_text), index.text, flags=re.IGNORECASE
            ):
                anchor = index.resolve_span(found.start(), found.end())
                if (anchor.segment_id, anchor.end_segment_id) == same_segments:
                    options.append(
                        (anchor.match_start, anchor.match_end, None, span.counts)
                    )

        free = []
        for start, end, relabel, counts in options:
            located = index.locate(
                segment_id=span.segment_id,
                end_segment_id=span.end_segment_id,
                match_start=start,
                match_end=end,
            )
            if located is None:
                continue
            length = len(relabel.mention_text if relabel else span.mention_text)
            blockers = {
                other
                for other, (lo, hi) in covered.items()
                if lo < located[1] and located[0] < hi
            }
            if any(
                (current[other].counts, len(current[other].mention_text))
                >= (counts, length)
                for other in blockers
            ):
                continue
            free.append(((start, end), relabel, counts))
        if not free:
            return None
        return min(free, key=lambda option: abs(option[0][0] - span.match_start))
