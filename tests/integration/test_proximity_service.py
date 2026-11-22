"""Computor behaviour tests for ``rebuild_proximity`` (T019).

Each test seeds synthetic videos (>= ``SUPPORT_MIN`` shared videos per pair so the
pair is in scope), runs the real service against real tables, and asserts on the
persisted instance rows - not on a mock's return value.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.services.proximity_service import (
    OUTER_WINDOW_SECONDS,
    SUPPORT_MIN,
    rebuild_proximity,
)
from tests.factories.proximity_seed import (
    canonical,
    route_proximity_service_to,
    seed_entity,
    seed_mention,
    seed_pair_in_videos,
    seed_segment,
    seed_video,
)

pytestmark = pytest.mark.asyncio


def _videos(prefix: str, count: int) -> list[str]:
    return [f"{prefix}{n:02d}" for n in range(count)]


async def _instances_for(
    session: AsyncSession, pair: tuple[uuid.UUID, uuid.UUID]
) -> list[EntityPairProximityDB]:
    result = await session.execute(
        select(EntityPairProximityDB).where(
            EntityPairProximityDB.entity_a_id == pair[0],
            EntityPairProximityDB.entity_b_id == pair[1],
        )
    )
    return list(result.scalars().all())


class TestSupportOnlyBound:
    async def test_hub_pair_that_fails_a_lift_gate_still_gets_instances(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scope bound is co-occurrence SUPPORT, not lift (D5).

        The hub is mentioned in EVERY video of the corpus, so for the hub/rare
        pair  lift = P(both) / (P(hub) * P(rare)) = P(rare) / (1 * P(rare)) = 1:
        no more than chance, which any lift gate would reject. The pair must
        still produce instances, because rescuing hub-anchored pairs is the
        feature's reason to exist. A pair one shared video short of
        ``SUPPORT_MIN`` proves a bound IS applied (the test is not vacuous).
        """
        hub = await seed_entity(db_session)
        rare = await seed_entity(db_session)
        thin = await seed_entity(db_session)

        corpus = _videos("hub116v", SUPPORT_MIN * 6)
        rare_videos = corpus[:SUPPORT_MIN]
        thin_videos = corpus[SUPPORT_MIN : SUPPORT_MIN + SUPPORT_MIN - 1]

        for video_id in corpus:
            await seed_video(db_session, video_id)
            seg_hub = await seed_segment(db_session, video_id, "en", 10.0, 0)
            await seed_mention(
                db_session,
                entity_id=hub,
                video_id=video_id,
                language_code="en",
                segment_id=seg_hub,
            )
            for entity_id, video_set in ((rare, rare_videos), (thin, thin_videos)):
                if video_id in video_set:
                    seg = await seed_segment(db_session, video_id, "en", 20.0, 1)
                    await seed_mention(
                        db_session,
                        entity_id=entity_id,
                        video_id=video_id,
                        language_code="en",
                        segment_id=seg,
                    )
        await db_session.commit()

        # Precondition: the hub really is in every video, i.e. lift == 1.
        hub_rows = await db_session.execute(
            select(EntityMentionDB.video_id).where(EntityMentionDB.entity_id == hub)
        )
        hub_videos = set(hub_rows.scalars())
        assert hub_videos == set(corpus)

        route_proximity_service_to(monkeypatch, db_session)
        await rebuild_proximity()

        hub_rare = await _instances_for(db_session, canonical(hub, rare))
        assert len(hub_rare) == SUPPORT_MIN, "lift-failing hub pair was dropped"
        assert all(i.gap_seconds == 10.0 for i in hub_rare)
        assert (
            await _instances_for(db_session, canonical(hub, thin)) == []
        ), "a pair under SUPPORT_MIN produced instances - no bound is applied"


class TestCrossSegmentStartAnchor:
    async def test_cross_segment_mention_is_positioned_by_its_start_segment(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-021: a mention spanning segment -> end_segment anchors at the start.

        Entity A starts at t=0 and ends at t=100; B sits at t=110. Start-anchored
        gap is 110 (inside the window). An end-anchored implementation would give
        10 - so asserting ``gap == 110`` fails if the anchor flips. The second pair
        uses B at t=130: start-anchored 130 is outside the 120s window (no
        instance), while an end-anchored 30 would wrongly create one.
        """
        a1, b1, a2, b2 = [await seed_entity(db_session) for _ in range(4)]
        await seed_pair_in_videos(
            db_session,
            entity_a=a1,
            entity_b=b1,
            video_ids=_videos("anc116in", SUPPORT_MIN),
            a_time=0.0,
            b_time=110.0,
            a_end_time=100.0,
        )
        await seed_pair_in_videos(
            db_session,
            entity_a=a2,
            entity_b=b2,
            video_ids=_videos("anc116out", SUPPORT_MIN),
            a_time=0.0,
            b_time=130.0,
            a_end_time=100.0,
        )
        await db_session.commit()

        route_proximity_service_to(monkeypatch, db_session)
        await rebuild_proximity()

        inside = await _instances_for(db_session, canonical(a1, b1))
        assert len(inside) == SUPPORT_MIN
        assert {i.gap_seconds for i in inside} == {110.0}, "not start-anchored"
        assert (
            await _instances_for(db_session, canonical(a2, b2)) == []
        ), "end-anchoring leaked: a start-gap of 130s must be outside the window"


class TestOuterWindow:
    @pytest.mark.parametrize(
        ("gap", "expect_instance"),
        [(119.0, True), (OUTER_WINDOW_SECONDS, True), (121.0, False)],
    )
    async def test_window_cutoff(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        gap: float,
        expect_instance: bool,
    ) -> None:
        """A pair at gap 119s (and exactly 120s) yields instances; 121s yields none.

        The pair always clears SUPPORT_MIN (it shares that many videos), so the
        absence at 121s is the WINDOW's doing, not the support bound's.
        """
        entity_a = await seed_entity(db_session)
        entity_b = await seed_entity(db_session)
        await seed_pair_in_videos(
            db_session,
            entity_a=entity_a,
            entity_b=entity_b,
            video_ids=_videos("win116v", SUPPORT_MIN),
            a_time=5.0,
            b_time=5.0 + gap,
        )
        await db_session.commit()

        route_proximity_service_to(monkeypatch, db_session)
        await rebuild_proximity()

        instances = await _instances_for(db_session, canonical(entity_a, entity_b))
        if expect_instance:
            assert len(instances) == SUPPORT_MIN
            assert {i.gap_seconds for i in instances} == {gap}
        else:
            assert instances == []
