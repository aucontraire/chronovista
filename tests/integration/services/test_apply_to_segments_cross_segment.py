"""Integration tests for cross-segment + entity corrections via ``apply_to_segments``.

Feature 081 wiring: the entity-aware API path (``/batch-corrections/apply`` ->
``BatchCorrectionService.apply_to_segments``) must now apply a boundary-spanning
name correction (distributing the name across the pair, T026) and record it as
exactly ONE ``user_correction`` spanning mention (T027), scoped to the anchor
segments the caller selected. These run end-to-end against a real PostgreSQL
database (``db_session`` fixture) because ``apply_to_segments`` coordinates many
collaborators (correction service, span primitive, counters, rebuild) — the seam
is where the real behavior lives. Neutral placeholder names only (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.enums import CorrectionType
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.services.batch_correction_service import BatchCorrectionService
from tests.factories.id_factory import video_id

from .test_cross_segment_corrections import (
    _make_batch_service,
    _seed_channel,
    _seed_segment,
    _seed_transcript,
    _seed_video,
)

pytestmark = __import__("pytest").mark.asyncio

NAME = "Alfa Bravo"  # corrected two-token name
GARBLE = "Alpha Bravado"  # the boundary-spanning garble to correct


async def _seed_entity(session: AsyncSession) -> uuid.UUID:
    entity = NamedEntityDB(
        canonical_name=NAME,
        canonical_name_normalized=NAME.lower(),
        entity_type="person",
        status="active",
        discovery_method="manual",
        confidence=1.0,
        mention_count=0,
        video_count=0,
    )
    session.add(entity)
    await session.flush()
    session.add(
        EntityAliasDB(
            entity_id=entity.id,
            alias_name=NAME,
            alias_name_normalized=NAME.lower(),
            alias_type="name_variant",
            occurrence_count=0,
        )
    )
    await session.flush()
    return entity.id


async def _transcript_mentions(
    db_session: AsyncSession, entity_id: uuid.UUID
) -> list[Any]:
    rows = (
        (
            await db_session.execute(
                select(EntityMentionDB).where(
                    EntityMentionDB.entity_id == entity_id,
                    EntityMentionDB.mention_source == "transcript",
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _batch_id() -> uuid.UUID:
    # Production uses a stdlib UUID built from a uuid7; uuid_utils.UUID is not a
    # uuid.UUID subclass and Pydantic rejects it.
    return uuid.UUID(bytes=uuid7().bytes)


class TestSelectedSpanAppliesAndRecordsOneMention:
    async def test_span_applied_sibling_pair_untouched(
        self, db_session: AsyncSession
    ) -> None:
        vid = video_id(seed="x081ats_sel")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid, language_code="en")
        # Selected spanning pair A/B, plus an UNSELECTED sibling span C/D in the
        # same video (same garble) — selection-scoping must leave C/D alone.
        seg_a = await _seed_segment(
            db_session, vid_id=vid, sequence_number=0, text="the guest is Alpha"
        )
        seg_b = await _seed_segment(
            db_session, vid_id=vid, sequence_number=1, text="Bravado speaks"
        )
        seg_c = await _seed_segment(
            db_session, vid_id=vid, sequence_number=2, text="we meet Alpha"
        )
        seg_d = await _seed_segment(
            db_session, vid_id=vid, sequence_number=3, text="Bravado again"
        )
        entity_id = await _seed_entity(db_session)
        await db_session.commit()

        service: BatchCorrectionService = _make_batch_service()
        result = await service.apply_to_segments(
            db_session,
            pattern=GARBLE,
            replacement=NAME,
            segment_ids=[seg_a.id],
            cross_segment=True,
            correction_type=CorrectionType.PROPER_NOUN,
            entity_id=entity_id,
            batch_id=_batch_id(),
        )

        rows = await _transcript_mentions(db_session, entity_id)
        assert len(rows) == 1
        m = rows[0]
        assert (m.segment_id, m.end_segment_id) == (seg_a.id, seg_b.id)
        assert m.detection_method == "user_correction"
        assert m.correction_id is not None
        assert m.mention_text == NAME

        # T026: the name is distributed across the boundary.
        a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        b = await db_session.get(TranscriptSegmentDB, seg_b.id)
        assert a is not None and b is not None
        text_a, text_b = (a.corrected_text or a.text), (b.corrected_text or b.text)
        assert "Alfa" in text_a and "Bravo" not in text_a
        assert "Bravo" in text_b and "Alfa" not in text_b

        # Selection-scoping: the unselected sibling pair is untouched.
        c = await db_session.get(TranscriptSegmentDB, seg_c.id)
        d = await db_session.get(TranscriptSegmentDB, seg_d.id)
        assert c is not None and not c.has_correction
        assert d is not None and not d.has_correction

        # Counts are per-requested-segment: one segment was selected and its
        # span correction applied, so applied == 1 (the non-requested partner B
        # is collateral, not in the caller's tally). No spurious skip, and the
        # invariant holds: applied + skipped + failed == len(segment_ids).
        assert result.total_applied == 1
        assert result.total_skipped == 0
        assert result.total_failed == 0
        assert result.total_applied + result.total_skipped + result.total_failed == 1


class TestSingleOnlySelectionMakesNoSpan:
    async def test_full_garble_in_one_segment_stays_single(
        self, db_session: AsyncSession
    ) -> None:
        # FR-006: a name wholly inside one segment is corrected single-segment
        # even with cross_segment=True — one ordinary mention, end_segment_id NULL.
        vid = video_id(seed="x081ats_single")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid, language_code="en")
        seg_k = await _seed_segment(
            db_session, vid_id=vid, sequence_number=0, text="Alpha Bravado here"
        )
        await _seed_segment(
            db_session, vid_id=vid, sequence_number=1, text="unrelated text"
        )
        entity_id = await _seed_entity(db_session)
        await db_session.commit()

        service = _make_batch_service()
        await service.apply_to_segments(
            db_session,
            pattern=GARBLE,
            replacement=NAME,
            segment_ids=[seg_k.id],
            cross_segment=True,
            correction_type=CorrectionType.PROPER_NOUN,
            entity_id=entity_id,
            batch_id=_batch_id(),
        )

        rows = await _transcript_mentions(db_session, entity_id)
        assert len(rows) == 1
        assert rows[0].segment_id == seg_k.id
        assert rows[0].end_segment_id is None


class TestConvergenceSingleAndSpanAgree:
    async def test_single_plus_span_counts_agree(
        self, db_session: AsyncSession
    ) -> None:
        # SC-007: one call corrects BOTH a single-segment occurrence and a span
        # for the same entity. Every occurrence surface must agree on 2, with the
        # span counted once (via its start segment) — never 2.
        vid = video_id(seed="x081ats_conv")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid, language_code="en")
        seg_g = await _seed_segment(
            db_session, vid_id=vid, sequence_number=0, text="intro Alpha"
        )
        seg_h = await _seed_segment(
            db_session, vid_id=vid, sequence_number=1, text="Bravado outro"
        )
        seg_k = await _seed_segment(
            db_session, vid_id=vid, sequence_number=2, text="Alpha Bravado inside"
        )
        entity_id = await _seed_entity(db_session)
        await db_session.commit()

        service = _make_batch_service()
        await service.apply_to_segments(
            db_session,
            pattern=GARBLE,
            replacement=NAME,
            segment_ids=[seg_g.id, seg_k.id],
            cross_segment=True,
            correction_type=CorrectionType.PROPER_NOUN,
            entity_id=entity_id,
            batch_id=_batch_id(),
        )

        rows = await _transcript_mentions(db_session, entity_id)
        # One single (K) + one span (G -> H): two rows.
        assert len(rows) == 2
        spanning = [r for r in rows if r.end_segment_id is not None]
        single = [r for r in rows if r.end_segment_id is None]
        assert len(spanning) == 1 and (
            spanning[0].segment_id,
            spanning[0].end_segment_id,
        ) == (seg_g.id, seg_h.id)
        assert len(single) == 1 and single[0].segment_id == seg_k.id

        repo = EntityMentionRepository()
        # Surface A — denormalized counter (recomputed inside apply_to_segments).
        entity = await db_session.get(NamedEntityDB, entity_id)
        assert entity is not None
        assert entity.mention_count == 2

        # Surface B — COUNT(DISTINCT segment_id); the span counts via seg G only.
        summary = await repo.get_video_entity_summary(db_session, vid)
        mine = [d for d in summary if d["entity_id"] == str(entity_id)]
        assert len(mine) == 1
        assert mine[0]["mention_count"] == 2

        # Surface C — raw transcript-mention row count.
        row_count = await db_session.scalar(
            select(func.count())
            .select_from(EntityMentionDB)
            .where(
                EntityMentionDB.entity_id == entity_id,
                EntityMentionDB.mention_source == "transcript",
            )
        )
        assert row_count == 2
        assert entity.mention_count == mine[0]["mention_count"] == row_count == 2


class TestCountInvariantBothSegmentsSelected:
    async def test_both_paired_segments_selected_counts_sum_to_len(
        self, db_session: AsyncSession
    ) -> None:
        # The common UI case: the caller selects BOTH segments of a spanning
        # pair. Each was booked skipped by the per-segment loop (neither holds
        # the whole name); the span applies them both. The result must report
        # applied == 2, skipped == 0, and applied + skipped + failed ==
        # len(segment_ids) == 2 — no segment double-counted as both skipped and
        # applied (the bug the earlier reclaim-anchor-only logic left).
        vid = video_id(seed="x081ats_both")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid, language_code="en")
        seg_a = await _seed_segment(
            db_session, vid_id=vid, sequence_number=0, text="the guest is Alpha"
        )
        seg_b = await _seed_segment(
            db_session, vid_id=vid, sequence_number=1, text="Bravado speaks"
        )
        entity_id = await _seed_entity(db_session)
        await db_session.commit()

        service = _make_batch_service()
        result = await service.apply_to_segments(
            db_session,
            pattern=GARBLE,
            replacement=NAME,
            segment_ids=[seg_a.id, seg_b.id],
            cross_segment=True,
            correction_type=CorrectionType.PROPER_NOUN,
            entity_id=entity_id,
            batch_id=_batch_id(),
        )

        assert result.total_applied == 2
        assert result.total_skipped == 0
        assert result.total_failed == 0
        assert result.total_applied + result.total_skipped + result.total_failed == 2

        # Still exactly one spanning mention for the single occurrence.
        rows = await _transcript_mentions(db_session, entity_id)
        assert len(rows) == 1
        assert (rows[0].segment_id, rows[0].end_segment_id) == (seg_a.id, seg_b.id)
