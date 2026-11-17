"""Uniform arbitration: one longest-match-wins pool across the segment boundary (US4).

Scenario S2 (Feature 111 FR-005/FR-006, SC-003).  A long multiword name and a short
name that is a sub-span of it must resolve the SAME way whether the long form sits
inside one segment (Case A) or straddles a segment boundary (Case B): the long mention
is written and the overlapping short mention is not.

Case B is the one that exercises the cross-segment suppression block in
``EntityMentionScanService._scan_cross_segment``.  The per-segment pass writes the
short in-segment mention in its OWN pool (it never sees the spanning span), so only
that block can delete it; a unit test of the ranker cannot see that interaction.

Assertions are on persisted ``entity_mentions`` rows, not scan return values.

Coordination: ``tests/integration/services/test_scan_scope_invariant.py`` guards the
exact-set / far-occurrence-survives behaviour with a THREE-segment fixture; this module
guards the A==B *uniformity* of the resolution with the same shape of data in both cases.
All names are invented placeholders.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
)
from tests.factories.id_factory import video_id
from tests.integration.services.test_entity_mention_scan_integration import (
    _make_session_factory_from_session,
    _seed_channel,
    _seed_entity,
    _seed_segment,
    _seed_transcript,
    _seed_video,
)

# CRITICAL: ensures async tests are not silently skipped under coverage.
pytestmark = [pytest.mark.asyncio, pytest.mark.db, pytest.mark.integration]

# (segment_id, end_segment_id) per persisted mention of one entity.
Anchor = tuple[int, int | None]


async def _anchors(
    session: AsyncSession, entity_id: uuid.UUID, vid: str
) -> list[Anchor]:
    rows = (
        await session.execute(
            select(EntityMentionDB.segment_id, EntityMentionDB.end_segment_id).where(
                EntityMentionDB.entity_id == entity_id,
                EntityMentionDB.video_id == vid,
            )
        )
    ).all()
    return sorted((r.segment_id, r.end_segment_id) for r in rows)


async def _scan(session: AsyncSession) -> None:
    service = EntityMentionScanService(
        session_factory=_make_session_factory_from_session(session)
    )
    await service.scan()


class TestUniformArbitration:
    async def test_case_a_single_segment_long_wins_short_not_written(
        self, db_session: AsyncSession
    ) -> None:
        vid = video_id(seed="uniform_arb_a")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)
        seg = await _seed_segment(
            db_session,
            vid,
            text="Tonight Zephyr Quillon Dray spoke briefly.",
            sequence_number=0,
        )
        short = await _seed_entity(db_session, "Quillon", entity_type="person")
        long_ = await _seed_entity(db_session, "Zephyr Quillon Dray", "person")
        await db_session.commit()

        await _scan(db_session)

        assert await _anchors(db_session, long_.id, vid) == [(seg.id, None)]
        assert await _anchors(db_session, short.id, vid) == []

    @pytest.mark.parametrize("short_name", ["Quillon", "Zephyr"])
    async def test_case_b_cross_segment_resolves_identically_to_case_a(
        self, db_session: AsyncSession, short_name: str
    ) -> None:
        """Same entities as Case A; the long form now straddles the boundary.

        Parametrized over WHICH segment holds the short sub-span: ``Quillon`` sits
        in the second segment, ``Zephyr`` in the first. Both must be suppressed,
        so a start-vs-end overlap bug in the cross-segment block cannot hide.
        """
        vid = video_id(seed=f"uniform_arb_b_{short_name.lower()}")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)
        seg0 = await _seed_segment(
            db_session,
            vid,
            text="Tonight the guest is Zephyr",
            sequence_number=0,
            start_time=0.0,
        )
        seg1 = await _seed_segment(
            db_session,
            vid,
            text="Quillon Dray spoke briefly.",
            sequence_number=1,
            start_time=5.0,
        )
        short = await _seed_entity(db_session, short_name, entity_type="person")
        long_ = await _seed_entity(db_session, "Zephyr Quillon Dray", "person")
        await db_session.commit()

        await _scan(db_session)

        # Long: exactly one SPANNING mention (start seg0, end seg1).
        assert await _anchors(db_session, long_.id, vid) == [(seg0.id, seg1.id)]
        # The short form sits wholly inside one segment and overlaps the spanning
        # match, so the per-segment row the first pass wrote must have been
        # deleted -- the same zero-mention outcome as Case A, whichever segment.
        assert await _anchors(db_session, short.id, vid) == [], (
            f"overlapping in-segment mention {short_name!r} survived next to the "
            "spanning longer match: within- and cross-segment arbitration are not "
            "one pool"
        )
