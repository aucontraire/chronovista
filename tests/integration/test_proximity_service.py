"""Computor behaviour tests for per-scope proximity processing (Features 116, 117).

Each test seeds synthetic videos, invalidates their ``(video, language)`` scopes,
runs the real ``process_stale_scopes`` against real tables, and asserts on the
persisted record rows and scope states, not on a mock's return value.

Feature 117 removed the corpus-wide support gate: a pair is measured as soon as its
qualifying mentions are close in ONE video (FR-006).
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import pathlib
import random
import signal
import subprocess
import sys
import uuid
from collections.abc import Sequence

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import chronovista.api.main as api_main
from chronovista.api.routers.health import health_check
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import EntityVideoExclusion as EntityVideoExclusionDB
from chronovista.db.models import ProximityGenerationRun as ProximityGenerationRunDB
from chronovista.db.models import ProximityScopeState as ProximityScopeStateDB
from chronovista.db.models import RelationshipCandidate as RelationshipCandidateDB
from chronovista.db.models import RelationshipCandidateSignal as SignalDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.entity_pair_proximity import (
    PairProximitySummary,
    ProcessSummary,
    ProximityScopeStatus,
    ProximityWorkerState,
    ProximityWorkerStatus,
    ScopeFilter,
)
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)
from chronovista.services import proximity_service
from chronovista.services.proximity_service import (
    MEASUREMENT_RULE_VERSION,
    OUTER_WINDOW_SECONDS,
    process_stale_scopes,
    recompute_scope,
)
from tests.factories.proximity_seed import (
    canonical,
    logical_records,
    route_proximity_service_to,
    route_proximity_service_to_engine,
    seed_entity,
    seed_mention,
    seed_pair_in_videos,
    seed_scope_state,
    seed_segment,
    seed_video,
)

pytestmark = pytest.mark.asyncio


def _videos(prefix: str, count: int) -> list[str]:
    return [f"{prefix}{uuid.uuid4().hex[:6]}{n:02d}" for n in range(count)]


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


async def _state(
    session: AsyncSession, video_id: str, language_code: str = "en"
) -> ProximityScopeStateDB:
    result = await session.execute(
        select(ProximityScopeStateDB)
        .where(
            ProximityScopeStateDB.video_id == video_id,
            ProximityScopeStateDB.language_code == language_code,
        )
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _process(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    video_ids: Sequence[str],
    *,
    language_code: str | None = None,
    limit: int = 10_000,
) -> ProcessSummary:
    """Invalidate ``video_ids`` (every language, or one), then process them.

    Processing is filtered to ``video_ids``, so a test never claims another test's
    scopes and the filtered path is the one exercised.
    """
    repo = EntityPairProximityRepository()
    for video_id in video_ids:
        await repo.invalidate_proximity_scopes(
            session, video_id=video_id, language_code=language_code, reason="test"
        )
    route_proximity_service_to(monkeypatch, session)
    return await process_stale_scopes(
        limit=limit, scope_filter=ScopeFilter(video_ids=tuple(video_ids))
    )


async def _seed_close_pair(
    session: AsyncSession,
    *,
    video_id: str,
    language_code: str,
    entity_a: uuid.UUID,
    entity_b: uuid.UUID,
    a_time: float = 10.0,
    b_time: float = 14.0,
) -> tuple[int, int]:
    """Co-mention two entities in an EXISTING video's transcript language."""
    seg_a = await seed_segment(session, video_id, language_code, a_time, 0)
    seg_b = await seed_segment(session, video_id, language_code, b_time, 1)
    for entity_id, segment_id in ((entity_a, seg_a), (entity_b, seg_b)):
        await seed_mention(
            session,
            entity_id=entity_id,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
        )
    return seg_a, seg_b


class TestRarePairIsMeasured:
    async def test_one_video_close_pair_is_measured_and_traceable(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-006 / SC-001: one video is enough; the record is traceable (FR-009)."""
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        (video_id,) = _videos("rare117", 1)
        ((seg_a, seg_b),) = await seed_pair_in_videos(
            db_session,
            entity_a=a,
            entity_b=b,
            video_ids=[video_id],
            a_time=10.0,
            b_time=14.0,
        )

        summary = await _process(db_session, monkeypatch, [video_id])

        (record,) = await _instances_for(db_session, canonical(a, b))
        assert record.video_id == video_id
        assert record.language_code == "en"
        assert record.gap_seconds == 4.0
        # segment_a is entity_a's (canonically smaller) mention
        expected = (seg_a, seg_b) if canonical(a, b) == (a, b) else (seg_b, seg_a)
        assert (record.segment_a_id, record.segment_b_id) == expected
        assert summary.processed == 1
        assert summary.records_written == 1
        assert summary.remaining == 0
        assert summary.complete is True
        state = await _state(db_session, video_id)
        assert state.computed_revision == state.revision
        assert state.computed_rule_version == MEASUREMENT_RULE_VERSION

    async def test_pair_never_within_the_window_has_no_records_and_is_current(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same video, never close: zero records, but the scope is CURRENT (computed),
        not "not computed" — the distinction FR-020 depends on."""
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        (video_id,) = _videos("far117", 1)
        await seed_pair_in_videos(
            db_session,
            entity_a=a,
            entity_b=b,
            video_ids=[video_id],
            a_time=0.0,
            b_time=OUTER_WINDOW_SECONDS + 30.0,
        )

        await _process(db_session, monkeypatch, [video_id])

        assert await _instances_for(db_session, canonical(a, b)) == []
        state = await _state(db_session, video_id)
        assert state.computed_revision == state.revision
        assert state.computed_rule_version == MEASUREMENT_RULE_VERSION

    async def test_no_support_floor_a_four_video_pair_is_measured(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Feature 116 gate (>= 5 shared videos) is gone: a hub-anchored pair
        that co-occurs in only 4 videos gets a record in each of them."""
        hub, thin = await seed_entity(db_session), await seed_entity(db_session)
        videos = _videos("thin117", 4)
        await seed_pair_in_videos(
            db_session,
            entity_a=hub,
            entity_b=thin,
            video_ids=videos,
            a_time=10.0,
            b_time=20.0,
        )

        await _process(db_session, monkeypatch, videos)

        records = await _instances_for(db_session, canonical(hub, thin))
        assert sorted(r.video_id for r in records) == sorted(videos)
        assert {r.gap_seconds for r in records} == {10.0}

    async def test_reprocessing_replaces_the_scope_as_a_whole(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A scope's records are replaced wholesale: moving B out of the window and
        reprocessing leaves no orphaned old record (FR-017 write rule)."""
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        (video_id,) = _videos("move117", 1)
        await seed_pair_in_videos(
            db_session,
            entity_a=a,
            entity_b=b,
            video_ids=[video_id],
            a_time=10.0,
            b_time=15.0,
        )
        await _process(db_session, monkeypatch, [video_id])
        assert len(await _instances_for(db_session, canonical(a, b))) == 1
        first_revision = (await _state(db_session, video_id)).revision

        await db_session.execute(
            delete(EntityMentionDB).where(
                EntityMentionDB.entity_id == b, EntityMentionDB.video_id == video_id
            )
        )
        far = await seed_segment(db_session, video_id, "en", 500.0, 9)
        await seed_mention(
            db_session,
            entity_id=b,
            video_id=video_id,
            language_code="en",
            segment_id=far,
        )
        await _process(db_session, monkeypatch, [video_id])

        assert await _instances_for(db_session, canonical(a, b)) == []
        state = await _state(db_session, video_id)
        assert state.revision == first_revision + 1
        assert state.computed_revision == state.revision

    async def test_reprocessing_an_unchanged_scope_yields_the_same_single_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Delete-then-insert must not duplicate: reprocessing leaves exactly one."""
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        videos = _videos("same117", 1)
        await seed_pair_in_videos(
            db_session, entity_a=a, entity_b=b, video_ids=videos, a_time=1, b_time=2
        )
        await _process(db_session, monkeypatch, videos)
        await _process(db_session, monkeypatch, videos)

        assert len(await _instances_for(db_session, canonical(a, b))) == 1

    async def test_two_mentions_in_one_segment_produce_one_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two mentions of A in the same segment collapse to one record key."""
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        (video_id,) = _videos("dup117", 1)
        ((seg_a, _),) = await seed_pair_in_videos(
            db_session,
            entity_a=a,
            entity_b=b,
            video_ids=[video_id],
            a_time=1,
            b_time=2,
        )
        await seed_mention(
            db_session,
            entity_id=a,
            video_id=video_id,
            language_code="en",
            segment_id=seg_a,
        )

        summary = await _process(db_session, monkeypatch, [video_id])

        assert len(await _instances_for(db_session, canonical(a, b))) == 1
        assert summary.records_written == 1


class TestScopeIsolation:
    async def test_recomputing_one_language_leaves_the_other_languages_records(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A scope is (video, LANGUAGE): processing ``es`` must not touch ``en``."""
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        (video_id,) = _videos("iso117", 1)
        await seed_video(db_session, video_id, ("en", "es"))
        for language in ("en", "es"):
            await _seed_close_pair(
                db_session,
                video_id=video_id,
                language_code=language,
                entity_a=a,
                entity_b=b,
            )
        both = await _process(db_session, monkeypatch, [video_id])
        assert both.processed == 2

        es_only = await _process(
            db_session, monkeypatch, [video_id], language_code="es"
        )

        assert es_only.processed == 1
        records = await _instances_for(db_session, canonical(a, b))
        assert sorted(r.language_code for r in records) == ["en", "es"]

    async def test_recomputing_one_video_leaves_another_videos_records(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        first, second = _videos("sib117", 2)
        await seed_pair_in_videos(
            db_session,
            entity_a=a,
            entity_b=b,
            video_ids=[first, second],
            a_time=1,
            b_time=2,
        )
        await _process(db_session, monkeypatch, [first, second])

        await _process(db_session, monkeypatch, [first])

        records = await _instances_for(db_session, canonical(a, b))
        assert sorted(r.video_id for r in records) == sorted([first, second])


class TestProcessingContract:
    async def test_limit_bounds_the_call_and_remaining_reports_the_rest(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        videos = _videos("lim117", 2)
        await seed_pair_in_videos(
            db_session, entity_a=a, entity_b=b, video_ids=videos, a_time=1, b_time=2
        )

        summary = await _process(db_session, monkeypatch, videos, limit=1)

        assert summary.processed == 1
        assert summary.remaining == 1
        assert summary.complete is False

    async def test_publish_is_refused_for_a_revision_bumped_after_the_claim(
        self, db_session: AsyncSession
    ) -> None:
        """The revision guard: a scope invalidated mid-computation stays stale.

        Simulates a producer invalidating between the claim and the publish (in
        production the claim's row lock makes the producer wait; the guard is the
        belt-and-braces layer). The publish must not mark the newer revision current.
        """
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        (video_id,) = _videos("bump117", 1)
        await seed_pair_in_videos(
            db_session,
            entity_a=a,
            entity_b=b,
            video_ids=[video_id],
            a_time=1,
            b_time=2,
        )
        repo = EntityPairProximityRepository()
        await repo.invalidate_proximity_scopes(
            db_session, video_id=video_id, reason="test"
        )
        claimed = await repo.claim_next_scope(
            db_session,
            rule_version=MEASUREMENT_RULE_VERSION,
            scope_filter=ScopeFilter(video_ids=(video_id,)),
        )
        assert claimed is not None
        claimed_revision = claimed.revision
        await db_session.execute(
            update(ProximityScopeStateDB)
            .where(ProximityScopeStateDB.video_id == video_id)
            .values(revision=ProximityScopeStateDB.revision + 1)
            # leave the claimed object holding the revision it was claimed at
            .execution_options(synchronize_session=False)
        )
        assert claimed.revision == claimed_revision

        _, published = await recompute_scope(db_session, claimed)

        assert published is False
        state = await _state(db_session, video_id)
        assert state.revision == claimed_revision + 1
        assert state.computed_revision is None


class TestCrossSegmentStartAnchor:
    async def test_cross_segment_mention_is_positioned_by_its_start_segment(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-004 / FR-021: a mention spanning segment -> end_segment anchors at the start.

        A starts at t=0 and ends at t=100; B sits at t=110. The start-anchored gap
        is 110 (inside the window); an end-anchored implementation would give 10.
        The second pair puts B at t=130: start-anchored 130 is outside the 120 s
        window (no record), while an end-anchored 30 would wrongly create one.
        """
        a1, b1, a2, b2 = [await seed_entity(db_session) for _ in range(4)]
        inside_videos = _videos("anc117in", 1)
        outside_videos = _videos("anc117out", 1)
        await seed_pair_in_videos(
            db_session,
            entity_a=a1,
            entity_b=b1,
            video_ids=inside_videos,
            a_time=0.0,
            b_time=110.0,
            a_end_time=100.0,
        )
        await seed_pair_in_videos(
            db_session,
            entity_a=a2,
            entity_b=b2,
            video_ids=outside_videos,
            a_time=0.0,
            b_time=130.0,
            a_end_time=100.0,
        )

        await _process(db_session, monkeypatch, inside_videos + outside_videos)

        inside = await _instances_for(db_session, canonical(a1, b1))
        assert {i.gap_seconds for i in inside} == {110.0}, "not start-anchored"
        assert (
            await _instances_for(db_session, canonical(a2, b2)) == []
        ), "end-anchoring leaked: a start-gap of 130s must be outside the window"


class TestOuterWindow:
    @pytest.mark.parametrize(
        ("gap", "expect_record"),
        [(119.0, True), (OUTER_WINDOW_SECONDS, True), (121.0, False)],
    )
    async def test_window_cutoff_is_inclusive(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        gap: float,
        expect_record: bool,
    ) -> None:
        """FR-004: a gap of 119 s and exactly 120 s qualify (inclusive); 121 s does not."""
        entity_a, entity_b = await seed_entity(db_session), await seed_entity(
            db_session
        )
        videos = _videos("win117", 1)
        await seed_pair_in_videos(
            db_session,
            entity_a=entity_a,
            entity_b=entity_b,
            video_ids=videos,
            a_time=5.0,
            b_time=5.0 + gap,
        )

        await _process(db_session, monkeypatch, videos)

        records = await _instances_for(db_session, canonical(entity_a, entity_b))
        if expect_record:
            assert {r.gap_seconds for r in records} == {gap}
        else:
            assert records == []


_NOT_A_NAME = "text that is no visible name"


async def _seed_qualification_pair(
    session: AsyncSession,
    *,
    a_text: str | None = None,
    b_text: str | None = None,
    a_method: str = "rule_match",
    b_method: str = "rule_match",
) -> tuple[uuid.UUID, uuid.UUID, str]:
    """One video, one close pair; each endpoint's text and method are chosen."""
    a, b = await seed_entity(session), await seed_entity(session)
    (video_id,) = _videos("qual117", 1)
    await seed_video(session, video_id)
    for entity_id, start, text, method, index in (
        (a, 10.0, a_text, a_method, 0),
        (b, 14.0, b_text, b_method, 1),
    ):
        segment = await seed_segment(session, video_id, "en", start, index)
        await seed_mention(
            session,
            entity_id=entity_id,
            video_id=video_id,
            language_code="en",
            segment_id=segment,
            mention_text=text,
            detection_method=method,
        )
    return a, b, video_id


class TestSharedQualificationRule:
    """FR-001..FR-003: proximity qualifies mentions exactly as the evidence panel."""

    @pytest.mark.parametrize(
        ("a_ok", "b_ok", "expect_record"),
        [(True, True, True), (True, False, False), (False, True, False)],
        ids=["both-qualify", "only-endpoint-a", "only-endpoint-b"],
    )
    async def test_each_endpoint_is_qualified_independently(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        a_ok: bool,
        b_ok: bool,
        expect_record: bool,
    ) -> None:
        a, b, video_id = await _seed_qualification_pair(
            db_session,
            a_text=None if a_ok else _NOT_A_NAME,
            b_text=None if b_ok else _NOT_A_NAME,
        )

        await _process(db_session, monkeypatch, [video_id])

        records = await _instances_for(db_session, canonical(a, b))
        assert bool(records) is expect_record

    async def test_text_matching_a_visible_alias_qualifies_and_stops_when_removed(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Visible names include aliases; removing the alias disqualifies the text."""
        alias_text = f"alias form {uuid.uuid4().hex[:6]}"
        a, b, video_id = await _seed_qualification_pair(db_session, a_text=alias_text)
        alias = EntityAliasDB(
            entity_id=a,
            alias_name=alias_text,
            alias_name_normalized=alias_text.lower(),
            alias_type="name_variant",
        )
        db_session.add(alias)
        await db_session.flush()
        await _process(db_session, monkeypatch, [video_id])
        assert len(await _instances_for(db_session, canonical(a, b))) == 1

        await db_session.delete(alias)
        await db_session.flush()
        await _process(db_session, monkeypatch, [video_id])

        assert await _instances_for(db_session, canonical(a, b)) == []

    async def test_name_exempt_asr_match_qualifies_with_garbled_text(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b, video_id = await _seed_qualification_pair(
            db_session, a_text=_NOT_A_NAME, a_method="asr_match"
        )

        await _process(db_session, monkeypatch, [video_id])

        assert len(await _instances_for(db_session, canonical(a, b))) == 1

    async def test_manual_detection_on_a_transcript_mention_does_not_qualify(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``manual`` is name-exempt for association, but never positioned evidence."""
        a, b, video_id = await _seed_qualification_pair(db_session, a_method="manual")

        await _process(db_session, monkeypatch, [video_id])

        assert await _instances_for(db_session, canonical(a, b)) == []

    async def test_manual_video_level_tag_forms_no_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A manual tag (``mention_source='manual'``, no segment) is not positioned."""
        a, b, video_id = await _seed_qualification_pair(db_session)
        await db_session.execute(
            update(EntityMentionDB)
            .where(EntityMentionDB.entity_id == a)
            .values(mention_source="manual", segment_id=None, detection_method="manual")
        )

        await _process(db_session, monkeypatch, [video_id])

        assert await _instances_for(db_session, canonical(a, b)) == []

    async def test_manual_exclusion_removes_the_entitys_records_in_that_video(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b, video_id = await _seed_qualification_pair(db_session)
        db_session.add(
            EntityVideoExclusionDB(entity_id=a, video_id=video_id, excluded_by="test")
        )
        await db_session.flush()

        await _process(db_session, monkeypatch, [video_id])

        assert await _instances_for(db_session, canonical(a, b)) == []

    async def test_mention_language_must_match_its_segments_language(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The panel joins segments on id AND language; a mention whose stored
        language disagrees with its segment's does not qualify there, nor here."""
        a, b, video_id = await _seed_qualification_pair(db_session)
        await db_session.execute(
            update(EntityMentionDB)
            .where(EntityMentionDB.entity_id == a)
            .values(language_code="fr")
        )

        await _process(db_session, monkeypatch, [video_id])

        assert await _instances_for(db_session, canonical(a, b)) == []


class TestPanelEquivalence:
    async def test_panel_and_proximity_select_the_same_mentions(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-001 / SC-002: the panel and proximity draw on the same qualifying mentions.

        In ``decoy`` a NON-qualifying A mention sits closer to B than the qualifying
        one, so a surface that skipped the rule would pick it (the panel) or record
        it (proximity). In ``garbled`` A's only mention is an ``asr_match``
        (name-exempt), and in ``absent`` A's only mention does not qualify at all.
        """
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        decoy, garbled, absent = _videos("eqv117", 3)
        plan = {
            decoy: [
                (b, 10.0, None, "rule_match"),
                (a, 12.0, _NOT_A_NAME, "rule_match"),
                (a, 40.0, None, "rule_match"),
            ],
            garbled: [
                (b, 10.0, None, "rule_match"),
                (a, 20.0, _NOT_A_NAME, "asr_match"),
            ],
            absent: [
                (b, 10.0, None, "rule_match"),
                (a, 11.0, _NOT_A_NAME, "rule_match"),
            ],
        }
        segment_of: dict[tuple[str, uuid.UUID, str | None], int] = {}
        for video_id, mentions in plan.items():
            await seed_video(db_session, video_id)
            for index, (entity_id, start, text, method) in enumerate(mentions):
                segment = await seed_segment(db_session, video_id, "en", start, index)
                segment_of[(video_id, entity_id, text)] = segment
                await seed_mention(
                    db_session,
                    entity_id=entity_id,
                    video_id=video_id,
                    language_code="en",
                    segment_id=segment,
                    mention_text=text,
                    detection_method=method,
                )

        await _process(db_session, monkeypatch, list(plan))
        evidence = await EntityMentionRepository().co_occurrence_evidence(
            db_session, a, b, limit=50
        )

        panel = {
            item.video_id: {
                item.representative.mention_a.segment_id,
                item.representative.mention_b.segment_id,
            }
            for item in evidence.items
        }
        proximity: dict[str, set[int]] = {}
        for record in await _instances_for(db_session, canonical(a, b)):
            proximity.setdefault(record.video_id, set()).update(
                {record.segment_a_id, record.segment_b_id}
            )
        assert panel == proximity
        assert panel[decoy] == {
            segment_of[(decoy, a, None)],
            segment_of[(decoy, b, None)],
        }
        assert garbled in panel and absent not in panel


class _SqlState(Exception):
    """Stand-in for a driver error carrying a Postgres SQLSTATE."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"sqlstate {sqlstate}")
        self.sqlstate = sqlstate


def _fail_for(
    monkeypatch: pytest.MonkeyPatch,
    video_ids: set[str],
    *,
    error: Exception | None = None,
    times: int | None = None,
) -> list[str]:
    """Make record replacement raise for ``video_ids``; return the call log.

    ``times`` limits how many calls raise (then it recomputes normally).
    """
    real = EntityPairProximityRepository.replace_scope_records
    calls: list[str] = []

    async def flaky(self, session, *, video_id, language_code, outer_window):  # type: ignore[no-untyped-def]
        calls.append(video_id)
        failing_calls = sum(1 for v in calls if v in video_ids)
        raising = video_id in video_ids and (times is None or failing_calls <= times)
        if raising:
            raise error or RuntimeError("forced compute failure")
        return await real(
            self,
            session,
            video_id=video_id,
            language_code=language_code,
            outer_window=outer_window,
        )

    monkeypatch.setattr(EntityPairProximityRepository, "replace_scope_records", flaky)
    return calls


async def _seconds_until_retry(session: AsyncSession, video_id: str) -> float:
    state = await _state(session, video_id)
    assert state.next_attempt_at is not None
    now = (await session.execute(select(func.now()))).scalar_one()
    delta: datetime.timedelta = state.next_attempt_at - now
    return delta.total_seconds()


async def _due_now(session: AsyncSession, video_id: str) -> None:
    """Skip the backoff wait: make a failed scope due immediately."""
    await session.execute(
        update(ProximityScopeStateDB)
        .where(ProximityScopeStateDB.video_id == video_id)
        .values(next_attempt_at=func.now() - datetime.timedelta(seconds=1))
    )


async def _two_pair_videos(session: AsyncSession) -> tuple[str, str]:
    a, b = await seed_entity(session), await seed_entity(session)
    bad, good = _videos("fail117", 2)
    await seed_pair_in_videos(
        session, entity_a=a, entity_b=b, video_ids=[bad, good], a_time=1, b_time=2
    )
    return bad, good


class TestFailureHandling:
    async def test_a_failing_scope_is_recorded_and_does_not_starve_the_others(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The poison pill (Phase 3 review): the call continues past a failure."""
        bad, good = await _two_pair_videos(db_session)
        _fail_for(monkeypatch, {bad})

        summary = await _process(db_session, monkeypatch, [bad, good])

        assert (summary.processed, summary.failed) == (1, 1)
        assert summary.remaining == 1 and summary.complete is False
        failed = await _state(db_session, bad)
        assert failed.attempts == 1
        assert failed.failed_rule_version == MEASUREMENT_RULE_VERSION
        assert failed.last_error is not None and "forced" in failed.last_error
        # first-ever computation: still never computed (the null-safe guard applied)
        assert failed.computed_revision is None
        assert 25 <= await _seconds_until_retry(db_session, bad) <= 35
        assert (await _state(db_session, good)).computed_revision is not None

    async def test_backoff_delays_the_retry_and_a_later_retry_succeeds(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad, good = await _two_pair_videos(db_session)
        _fail_for(monkeypatch, {bad}, times=1)
        await _process(db_session, monkeypatch, [bad, good])

        route_proximity_service_to(monkeypatch, db_session)
        waiting = await process_stale_scopes(
            limit=10, scope_filter=ScopeFilter(video_ids=(bad,))
        )
        assert (waiting.processed, waiting.failed, waiting.remaining) == (0, 0, 1)

        await _due_now(db_session, bad)
        retried = await process_stale_scopes(
            limit=10, scope_filter=ScopeFilter(video_ids=(bad,))
        )

        assert (retried.processed, retried.remaining) == (1, 0)
        state = await _state(db_session, bad)
        assert state.computed_revision == state.revision
        assert (state.attempts, state.next_attempt_at, state.last_error) == (
            0,
            None,
            None,
        )

    async def test_backoff_doubles_and_failing_is_reported_at_three_attempts(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad, _ = await _two_pair_videos(db_session)
        _fail_for(monkeypatch, {bad})
        route_proximity_service_to(monkeypatch, db_session)
        repo = EntityPairProximityRepository()
        await repo.invalidate_proximity_scopes(db_session, video_id=bad, reason="test")
        only_bad = ScopeFilter(video_ids=(bad,))

        delays, failing = [], []
        for _ in range(3):
            summary = await process_stale_scopes(limit=10, scope_filter=only_bad)
            delays.append(await _seconds_until_retry(db_session, bad))
            failing.append(summary.failing)
            await _due_now(db_session, bad)

        assert [round(d / 30) for d in delays] == [1, 2, 4]  # 30 s, 60 s, 120 s
        assert failing == [0, 0, 1]
        assert (await _state(db_session, bad)).attempts == 3

    async def test_a_rule_version_change_ignores_earlier_failures(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad, _ = await _two_pair_videos(db_session)
        repo = EntityPairProximityRepository()
        await repo.invalidate_proximity_scopes(db_session, video_id=bad, reason="test")
        await db_session.execute(
            update(ProximityScopeStateDB)
            .where(ProximityScopeStateDB.video_id == bad)
            .values(
                attempts=7,
                failed_rule_version="116.9",
                next_attempt_at=func.now() + datetime.timedelta(hours=1),
            )
        )
        _fail_for(monkeypatch, {bad})
        route_proximity_service_to(monkeypatch, db_session)

        summary = await process_stale_scopes(
            limit=10, scope_filter=ScopeFilter(video_ids=(bad,))
        )

        assert summary.failed == 1  # claimed despite the hour of backoff
        assert (await _state(db_session, bad)).attempts == 1  # counting restarted

    @pytest.mark.parametrize("sqlstate", ["40P01", "55P03", "40001"])
    async def test_lock_errors_retry_promptly_without_counting_an_attempt(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        sqlstate: str,
    ) -> None:
        bad, good = await _two_pair_videos(db_session)
        calls = _fail_for(
            monkeypatch,
            {bad},
            error=DBAPIError("stmt", {}, _SqlState(sqlstate)),
            times=2,
        )

        summary = await _process(db_session, monkeypatch, [bad, good])

        assert (summary.processed, summary.failed, summary.deferred) == (2, 0, 0)
        assert calls.count(bad) == 3  # two transient errors, then success
        assert (await _state(db_session, bad)).attempts == 0

    async def test_lock_errors_still_failing_after_three_retries_defer_the_scope(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad, good = await _two_pair_videos(db_session)
        calls = _fail_for(
            monkeypatch, {bad}, error=DBAPIError("stmt", {}, _SqlState("40P01"))
        )

        summary = await _process(db_session, monkeypatch, [bad, good])

        assert (summary.processed, summary.failed, summary.deferred) == (1, 0, 1)
        assert summary.complete is False
        assert calls.count(bad) == 4  # the first try plus three prompt retries
        deferred = await _state(db_session, bad)
        assert deferred.attempts == 0
        assert 3 <= await _seconds_until_retry(db_session, bad) <= 7

    async def test_a_failure_recorded_for_an_older_revision_is_discarded(
        self, db_session: AsyncSession
    ) -> None:
        """A newer invalidation (or a newer success) wins over a late failure."""
        bad, _ = await _two_pair_videos(db_session)
        repo = EntityPairProximityRepository()
        await repo.invalidate_proximity_scopes(db_session, video_id=bad, reason="test")
        attempted = (await _state(db_session, bad)).revision
        await repo.invalidate_proximity_scopes(db_session, video_id=bad, reason="test")

        recorded = await repo.record_scope_failure(
            db_session,
            video_id=bad,
            language_code="en",
            attempted_revision=attempted,
            rule_version=MEASUREMENT_RULE_VERSION,
            error="late failure",
        )

        assert recorded is False
        state = await _state(db_session, bad)
        assert (state.attempts, state.last_error) == (0, None)

    async def test_a_failure_recorded_after_a_successful_publish_is_discarded(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad, _ = await _two_pair_videos(db_session)
        await _process(db_session, monkeypatch, [bad])
        published = await _state(db_session, bad)

        recorded = await EntityPairProximityRepository().record_scope_failure(
            db_session,
            video_id=bad,
            language_code="en",
            attempted_revision=published.revision,
            rule_version=MEASUREMENT_RULE_VERSION,
            error="late failure",
        )

        assert recorded is False
        assert (await _state(db_session, bad)).attempts == 0


async def _until(predicate: object, *, timeout: float = 10.0) -> None:
    """Yield to the worker until ``predicate()`` holds (no database access here)."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():  # type: ignore[operator]
        assert asyncio.get_running_loop().time() < deadline, "worker did not progress"
        await asyncio.sleep(0.01)


@pytest.fixture
def worker_status(monkeypatch: pytest.MonkeyPatch) -> ProximityWorkerStatus:
    """A fresh in-process status object, so tests never see each other's state."""
    fresh = ProximityWorkerStatus()
    monkeypatch.setattr(proximity_service, "worker_status", fresh)
    return fresh


def _start(stop: asyncio.Event, *, interval_s: float = 60.0) -> asyncio.Task[None]:
    return asyncio.create_task(
        proximity_service.run_proximity_worker(
            stop, interval_s=interval_s, batch=50, reconcile_every=1
        )
    )


async def _zero() -> int:
    return 0


class TestWorkerLifecycle:
    """T028. The worker shares the test session, so the test only touches the
    database while the worker is idle, waiting on its stop event."""

    async def test_it_bootstraps_missing_scopes_processes_them_and_stops_cleanly(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        worker_status: ProximityWorkerStatus,
    ) -> None:
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        (video_id,) = _videos("wrk117", 1)
        await seed_pair_in_videos(
            db_session, entity_a=a, entity_b=b, video_ids=[video_id], a_time=1, b_time=2
        )
        # no scope-state row exists yet: only the worker's bootstrap can create it
        route_proximity_service_to(monkeypatch, db_session)
        stop = asyncio.Event()

        task = _start(stop)
        await _until(lambda: worker_status.last_cycle_at is not None)
        assert worker_status.state is ProximityWorkerState.RUNNING
        stop.set()
        await asyncio.wait_for(task, timeout=5)

        assert worker_status.state is ProximityWorkerState.STOPPED
        state = await _state(db_session, video_id)
        assert state.computed_revision == state.revision
        assert len(await _instances_for(db_session, canonical(a, b))) == 1

    async def test_health_reports_the_running_worker(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        worker_status: ProximityWorkerStatus,
    ) -> None:
        route_proximity_service_to(monkeypatch, db_session)
        stop = asyncio.Event()
        task = _start(stop)
        await _until(lambda: worker_status.last_cycle_at is not None)

        body = (await health_check()).data

        stop.set()
        await asyncio.wait_for(task, timeout=5)
        assert body.proximity_worker is not None
        assert body.proximity_worker.state == "running"
        assert body.proximity_worker.last_cycle_at == worker_status.last_cycle_at

    async def test_cancellation_propagates_and_leaves_it_stopped(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        worker_status: ProximityWorkerStatus,
    ) -> None:
        route_proximity_service_to(monkeypatch, db_session)
        task = _start(asyncio.Event())
        await _until(lambda: worker_status.last_cycle_at is not None)

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert worker_status.state is ProximityWorkerState.STOPPED

    async def test_cancellation_mid_cycle_is_not_swallowed(
        self, monkeypatch: pytest.MonkeyPatch, worker_status: ProximityWorkerStatus
    ) -> None:
        """Cancellation arriving INSIDE a cycle must end the task. (Cancelling while
        it sleeps cannot detect this: the sleep is outside the cycle's handler.)"""
        entered = asyncio.Event()

        async def blocks_forever(**_: object) -> ProcessSummary:
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        monkeypatch.setattr(proximity_service, "bootstrap_scope_states", _zero)
        monkeypatch.setattr(proximity_service, "process_stale_scopes", blocks_forever)
        task = _start(asyncio.Event())
        await asyncio.wait_for(entered.wait(), timeout=5)

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
        assert worker_status.state is ProximityWorkerState.STOPPED

    async def test_a_failed_cycle_is_logged_and_the_loop_continues(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        worker_status: ProximityWorkerStatus,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        route_proximity_service_to(monkeypatch, db_session)
        real = proximity_service.process_stale_scopes
        calls = 0

        async def first_call_fails(**kwargs: object) -> ProcessSummary:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected cycle failure")
            return await real(**kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(proximity_service, "process_stale_scopes", first_call_fails)
        stop = asyncio.Event()

        with caplog.at_level(logging.ERROR, logger=proximity_service.__name__):
            task = _start(stop, interval_s=0.01)
            await _until(lambda: worker_status.last_cycle_at is not None)
            stop.set()
            await asyncio.wait_for(task, timeout=5)

        assert calls >= 2
        assert "proximity worker cycle failed" in caplog.text
        assert worker_status.state is ProximityWorkerState.STOPPED


class TestWorkerWiring:
    async def test_a_worker_that_dies_with_an_error_is_marked_crashed(
        self, worker_status: ProximityWorkerStatus
    ) -> None:
        async def dies() -> None:
            raise RuntimeError("boom")

        task = asyncio.create_task(dies())
        await asyncio.gather(task, return_exceptions=True)

        api_main._on_proximity_worker_done(task)

        assert worker_status.state is ProximityWorkerState.CRASHED

    async def test_a_disabled_worker_is_not_started_and_reports_disabled(
        self, monkeypatch: pytest.MonkeyPatch, worker_status: ProximityWorkerStatus
    ) -> None:
        monkeypatch.setattr(api_main.app_settings, "proximity_worker_enabled", False)

        assert api_main._start_proximity_worker(api_main.app) is None
        assert worker_status.state is ProximityWorkerState.DISABLED


async def _committed_pair_video(session: AsyncSession, prefix: str) -> str:
    a, b = await seed_entity(session), await seed_entity(session)
    (video_id,) = _videos(prefix, 1)
    await seed_pair_in_videos(
        session, entity_a=a, entity_b=b, video_ids=[video_id], a_time=1, b_time=2
    )
    await EntityPairProximityRepository().invalidate_proximity_scopes(
        session, video_id=video_id, reason="test"
    )
    await session.commit()
    return video_id


async def _blocked(task: asyncio.Task[object], engine: object) -> bool:
    """True once Postgres reports a backend WAITING ON A LOCK while ``task`` runs.

    Probing ``pg_stat_activity`` proves the producer is blocked by the claim's row
    lock; a bare sleep could not tell "waiting on the lock" from "slow to connect".
    """
    deadline = asyncio.get_running_loop().time() + 5
    async with engine.connect() as probe:  # type: ignore[attr-defined]
        while asyncio.get_running_loop().time() < deadline:
            waiting = (
                await probe.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND wait_event_type = 'Lock'"
                    )
                )
            ).scalar_one()
            await probe.rollback()
            if waiting:
                return not task.done()
            if task.done():
                return False
            await asyncio.sleep(0.02)
    return False


class TestConcurrency:
    """T025 (R15): two real connections, so row locks actually interact.

    Every producer connection sets ``lock_timeout``: a deadlock or lock regression
    then fails the test quickly instead of hanging the suite.
    """

    async def test_an_invalidation_during_a_computation_is_not_lost(
        self, db_session: AsyncSession
    ) -> None:
        video_id = await _committed_pair_video(db_session, "cc117a")
        factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
        repo = EntityPairProximityRepository()

        async with factory() as processor:
            state = await repo.claim_next_scope(
                processor,
                rule_version=MEASUREMENT_RULE_VERSION,
                scope_filter=ScopeFilter(video_ids=(video_id,)),
            )
            assert state is not None
            computing = state.revision

            async def producer() -> None:
                async with factory() as session:
                    await session.execute(text("SET lock_timeout = '5s'"))
                    await repo.invalidate_proximity_scopes(
                        session, video_id=video_id, reason="concurrent"
                    )
                    await session.commit()

            invalidation = asyncio.create_task(producer())
            assert await _blocked(
                invalidation, db_session.bind
            ), "the claim did not hold the row lock"
            _, published = await recompute_scope(processor, state)
            await processor.commit()
        await asyncio.wait_for(invalidation, timeout=10)

        assert published is True
        after = await _state(db_session, video_id)
        assert after.computed_revision == computing
        assert after.revision == computing + 1  # stale again: nothing was lost

    async def test_a_segment_replacement_during_a_computation_waits_and_ends_consistent(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The producer invalidates BEFORE deleting segments (lock order), so it
        waits on the claimed row instead of deadlocking with the processor."""
        video_id = await _committed_pair_video(db_session, "cc117b")
        factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
        repo = EntityPairProximityRepository()

        async with factory() as processor:
            state = await repo.claim_next_scope(
                processor,
                rule_version=MEASUREMENT_RULE_VERSION,
                scope_filter=ScopeFilter(video_ids=(video_id,)),
            )
            assert state is not None

            async def replace_segments() -> None:
                async with factory() as session:
                    await session.execute(text("SET lock_timeout = '5s'"))
                    await repo.invalidate_proximity_scopes(
                        session, video_id=video_id, reason="transcript_download"
                    )
                    await session.execute(
                        delete(TranscriptSegmentDB).where(
                            TranscriptSegmentDB.video_id == video_id
                        )
                    )
                    await session.commit()

            producer = asyncio.create_task(replace_segments())
            assert await _blocked(producer, db_session.bind)
            await recompute_scope(processor, state)
            await processor.commit()
        await asyncio.wait_for(producer, timeout=10)

        await _process(db_session, monkeypatch, [video_id])
        final = await _state(db_session, video_id)
        assert final.computed_revision == final.revision
        remaining = await db_session.execute(
            select(func.count())
            .select_from(EntityPairProximityDB)
            .where(EntityPairProximityDB.video_id == video_id)
        )
        assert (
            remaining.scalar_one() == 0
        )  # the segments (and so the evidence) are gone

    async def test_an_entity_invalidation_spanning_scopes_completes_beside_processing(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A multi-scope invalidation locks in sorted order while a processor holds
        one of its scopes: it waits, then completes, with no deadlock."""
        hub, other = await seed_entity(db_session), await seed_entity(db_session)
        videos = sorted(_videos("cc117d", 3))
        await seed_pair_in_videos(
            db_session,
            entity_a=hub,
            entity_b=other,
            video_ids=videos,
            a_time=1,
            b_time=2,
        )
        repo = EntityPairProximityRepository()
        await repo.invalidate_proximity_scopes(db_session, entity_id=hub, reason="test")
        await db_session.commit()
        factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

        async with factory() as processor:
            middle = await repo.claim_next_scope(
                processor,
                rule_version=MEASUREMENT_RULE_VERSION,
                scope_filter=ScopeFilter(video_ids=(videos[1],)),
            )
            assert middle is not None

            async def rename() -> None:
                async with factory() as session:
                    await session.execute(text("SET lock_timeout = '5s'"))
                    await repo.invalidate_proximity_scopes(
                        session, entity_id=hub, reason="name"
                    )
                    await session.commit()

            producer = asyncio.create_task(rename())
            assert await _blocked(producer, db_session.bind)
            await recompute_scope(processor, middle)
            await processor.commit()
        await asyncio.wait_for(producer, timeout=10)

        summary = await _process(db_session, monkeypatch, videos)
        assert summary.complete is True


class TestIncrementalEqualsFull:
    """T027 / SC-003: processing only invalidated scopes converges to the same
    records as recomputing everything from scratch."""

    async def test_a_randomized_change_sequence_converges_to_a_full_recompute(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rng = random.Random(117)  # noqa: S311 - deterministic test data, not crypto
        repo = EntityPairProximityRepository()
        entities = [await seed_entity(db_session) for _ in range(5)]
        videos = _videos("eqf117", 4)
        for video_id in videos:
            await seed_video(db_session, video_id, ("en", "es"))
        segments: dict[tuple[str, str], list[int]] = {}
        for video_id in videos:
            for language in ("en", "es"):
                segments[(video_id, language)] = [
                    await seed_segment(db_session, video_id, language, t, i)
                    for i, t in enumerate((1.0, 20.0, 50.0, 140.0, 300.0))
                ]
        route_proximity_service_to(monkeypatch, db_session)

        async def add_mention() -> None:
            video_id, language = rng.choice(videos), rng.choice(("en", "es"))
            await seed_mention(
                db_session,
                entity_id=rng.choice(entities),
                video_id=video_id,
                language_code=language,
                segment_id=rng.choice(segments[(video_id, language)]),
                mention_text=rng.choice([None, None, None, _NOT_A_NAME]),
            )
            await repo.invalidate_proximity_scopes(
                db_session, video_id=video_id, language_code=language, reason="scan"
            )

        async def remove_mention() -> None:
            rows = (
                (
                    await db_session.execute(
                        select(EntityMentionDB).where(
                            EntityMentionDB.video_id.in_(videos)
                        )
                    )
                )
                .scalars()
                .all()
            )
            if rows:
                victim = rng.choice(list(rows))
                await repo.invalidate_proximity_scopes(
                    db_session,
                    video_id=victim.video_id,
                    language_code=victim.language_code,
                    reason="scan",
                )
                await db_session.delete(victim)
                await db_session.flush()

        async def toggle_exclusion() -> None:
            entity_id, video_id = rng.choice(entities), rng.choice(videos)
            await repo.invalidate_proximity_scopes(
                db_session, video_id=video_id, reason="exclusion"
            )
            existing = await db_session.get(
                EntityVideoExclusionDB, (entity_id, video_id)
            )
            if existing is None:
                db_session.add(
                    EntityVideoExclusionDB(
                        entity_id=entity_id, video_id=video_id, excluded_by="test"
                    )
                )
            else:
                await db_session.delete(existing)
            await db_session.flush()

        async def toggle_alias() -> None:
            """The non-name text becomes (or stops being) a visible name."""
            entity_id = rng.choice(entities)
            await repo.invalidate_proximity_scopes(
                db_session, entity_id=entity_id, reason="alias"
            )
            existing = (
                await db_session.execute(
                    select(EntityAliasDB).where(
                        EntityAliasDB.entity_id == entity_id,
                        EntityAliasDB.alias_name == _NOT_A_NAME,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db_session.add(
                    EntityAliasDB(
                        entity_id=entity_id,
                        alias_name=_NOT_A_NAME,
                        alias_name_normalized=_NOT_A_NAME,
                        alias_type="name_variant",
                    )
                )
            else:
                await db_session.delete(existing)
            await db_session.flush()

        changes = [add_mention] * 4 + [remove_mention, toggle_exclusion, toggle_alias]
        for step in range(60):
            await rng.choice(changes)()
            if step % 7 == 0:  # interleave partial processing with the changes
                await process_stale_scopes(
                    limit=rng.randint(1, 3),
                    scope_filter=ScopeFilter(video_ids=tuple(videos)),
                )
        everywhere = ScopeFilter(video_ids=tuple(videos))
        await process_stale_scopes(limit=10_000, scope_filter=everywhere)
        incremental = await logical_records(db_session)
        assert incremental, "the sequence produced no records - the check is vacuous"

        # A fresh full recompute of the same final state.
        await db_session.execute(delete(EntityPairProximityDB))
        await db_session.execute(delete(ProximityScopeStateDB))
        await repo.bootstrap_scope_states(db_session)
        await process_stale_scopes(limit=10_000, scope_filter=everywhere)

        assert await logical_records(db_session) == incremental


_INTEGRATION_URL = os.getenv(
    "DATABASE_INTEGRATION_URL",
    os.getenv(
        "CHRONOVISTA_INTEGRATION_DB_URL",
        "postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test",
    ),
)

# Runs a rebuild in a child process that processes one scope per second, so the
# test can kill it mid-run. It refuses to run against anything but the
# integration database (never dev, never prod).
_SLOW_REBUILD = """
import asyncio, sys
from chronovista.config.settings import settings
url = settings.effective_database_url
assert "chronovista_integration_test" in url and ":5435" not in url, url
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository as Repo,
)
from chronovista.services import proximity_service
real = Repo.replace_scope_records
async def slow(self, *a, **k):
    await asyncio.sleep(1.0)
    return await real(self, *a, **k)
Repo.replace_scope_records = slow
print("started", flush=True)
asyncio.run(proximity_service.rebuild_proximity(batch=1))
"""


async def _seed_videos(session: AsyncSession, prefix: str, count: int) -> list[str]:
    a, b = await seed_entity(session), await seed_entity(session)
    videos = sorted(_videos(prefix, count))
    await seed_pair_in_videos(
        session, entity_a=a, entity_b=b, video_ids=videos, a_time=1, b_time=2
    )
    await session.commit()
    return videos


async def _current(session: AsyncSession, video_ids: Sequence[str]) -> set[str]:
    rows = await session.execute(
        select(ProximityScopeStateDB.video_id).where(
            ProximityScopeStateDB.video_id.in_(list(video_ids)),
            ProximityScopeStateDB.computed_revision == ProximityScopeStateDB.revision,
            ProximityScopeStateDB.computed_rule_version == MEASUREMENT_RULE_VERSION,
        )
    )
    return set(rows.scalars())


async def _runs(session: AsyncSession) -> list[str]:
    rows = await session.execute(
        select(ProximityGenerationRunDB.status)
        .order_by(ProximityGenerationRunDB.started_at)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars())


class TestRebuild:
    """T039 (US4): a resumable, crash-safe, honest rebuild."""

    async def test_a_killed_rebuild_resumes_and_matches_a_rebuild_of_the_final_state(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        videos = await _seed_videos(db_session, "kil117", 6)
        env = {
            **os.environ,
            "DEVELOPMENT_MODE": "false",
            "DATABASE_URL": _INTEGRATION_URL,
            "PROXIMITY_WORKER_ENABLED": "false",
        }
        log = tmp_path / "child.log"
        with log.open("wb") as out:  # a file, never a pipe that could fill up
            child = subprocess.Popen(  # noqa: S603 - fixed interpreter and script
                [sys.executable, "-c", _SLOW_REBUILD],
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        try:
            deadline = asyncio.get_running_loop().time() + 30
            while len(await _current(db_session, videos)) < 2:
                assert child.poll() is None, log.read_text()
                assert asyncio.get_running_loop().time() < deadline, "no progress"
                await asyncio.sleep(0.2)
                await db_session.rollback()  # see the child's commits
        finally:
            child.send_signal(signal.SIGKILL)
            child.wait(timeout=10)
        await db_session.rollback()
        # Postgres drops a killed client's session (and its advisory lock) only once
        # it notices the closed socket; wait for that instead of racing it.
        repo = EntityPairProximityRepository()
        lock_deadline = asyncio.get_running_loop().time() + 10
        while await repo.rebuild_lock_holder(db_session) is not None:
            assert asyncio.get_running_loop().time() < lock_deadline, "lock not freed"
            await db_session.rollback()
            await asyncio.sleep(0.1)
        await db_session.rollback()
        done_before = await _current(db_session, videos)
        assert 2 <= len(done_before) < len(videos), "the kill was not mid-run"
        assert await _runs(db_session) == ["running"]  # left behind by the kill

        # A producer changes one ALREADY-rebuilt video before the rerun.
        changed = sorted(done_before)[0]
        untouched = sorted(done_before - {changed})
        computed_at = {v: (await _state(db_session, v)).computed_at for v in untouched}
        third = await seed_entity(db_session)
        seg = await seed_segment(db_session, changed, "en", 3.0, 7)
        await seed_mention(
            db_session,
            entity_id=third,
            video_id=changed,
            language_code="en",
            segment_id=seg,
        )
        await EntityPairProximityRepository().invalidate_proximity_scopes(
            db_session, video_id=changed, reason="scan"
        )
        await db_session.commit()

        route_proximity_service_to_engine(monkeypatch, db_session.bind)
        outcome = await asyncio.wait_for(proximity_service.rebuild_proximity(), 120)

        assert outcome.status == "completed"
        await db_session.rollback()
        assert await _runs(db_session) == ["abandoned", "completed"]
        assert await _current(db_session, videos) == set(videos)
        for video_id in untouched:  # FR-018: current scopes are skipped
            assert (await _state(db_session, video_id)).computed_at == computed_at[
                video_id
            ]
        resumed = await logical_records(db_session)
        assert any(r[2] == changed for r in resumed if third in (r[0], r[1]))

        fresh = await asyncio.wait_for(
            proximity_service.rebuild_proximity(force=True), 120
        )
        assert fresh.status == "completed"
        await db_session.rollback()
        assert await logical_records(db_session) == resumed

    async def test_a_second_rebuild_is_refused_while_one_holds_the_lock(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _seed_videos(db_session, "lck117", 1)
        route_proximity_service_to_engine(monkeypatch, db_session.bind)
        repo = EntityPairProximityRepository()
        async with db_session.bind.connect() as holder:  # type: ignore[union-attr]
            assert await repo.try_acquire_rebuild_lock(holder) is True
            outcome = await proximity_service.rebuild_proximity()
            await repo.release_rebuild_lock(holder)

        assert outcome.status == "locked"
        await db_session.rollback()
        assert await _runs(db_session) == []

    async def test_a_failed_lock_release_does_not_leave_the_lock_held(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pooled connection keeps its database session, and a session-level lock
        survives being returned to the pool, so a failed release must discard the
        connection. (A second rebuild cannot detect a leak: advisory locks are
        re-entrant in the same session, and the pool may hand back that connection.)
        """
        await _seed_videos(db_session, "rel117", 1)
        route_proximity_service_to_engine(monkeypatch, db_session.bind)

        async def broken_release(self: object, connection: object) -> bool:
            raise RuntimeError("release failed")

        monkeypatch.setattr(
            EntityPairProximityRepository, "release_rebuild_lock", broken_release
        )
        with pytest.raises(RuntimeError, match="release failed"):
            await proximity_service.rebuild_proximity()

        await db_session.rollback()
        holder = await EntityPairProximityRepository().rebuild_lock_holder(db_session)
        assert holder is None, "the rebuild lock leaked into a pooled connection"

    async def test_a_scoped_rebuild_processes_only_the_requested_scopes(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wanted, other = await _seed_videos(db_session, "scp117", 2)
        repo = EntityPairProximityRepository()
        for video_id in (wanted, other):
            await repo.invalidate_proximity_scopes(
                db_session, video_id=video_id, reason="test"
            )
        await db_session.commit()
        route_proximity_service_to_engine(monkeypatch, db_session.bind)

        outcome = await proximity_service.rebuild_proximity(video_ids=[wanted])

        assert outcome.status == "completed"
        await db_session.rollback()
        assert await _current(db_session, [wanted, other]) == {wanted}

    async def test_an_entity_scoped_rebuild_covers_that_entitys_scopes_only(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b, c, d = [await seed_entity(db_session) for _ in range(4)]
        mine, theirs = _videos("ent117", 2)
        await seed_pair_in_videos(
            db_session, entity_a=a, entity_b=b, video_ids=[mine], a_time=1, b_time=2
        )
        await seed_pair_in_videos(
            db_session, entity_a=c, entity_b=d, video_ids=[theirs], a_time=1, b_time=2
        )
        await db_session.commit()
        route_proximity_service_to_engine(monkeypatch, db_session.bind)

        await proximity_service.rebuild_proximity(entity_ids=[a])

        await db_session.rollback()
        assert await _current(db_session, [mine, theirs]) == {mine}

    async def test_dry_run_writes_nothing_and_says_what_it_sampled(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        videos = await _seed_videos(db_session, "dry117", 2)
        route_proximity_service_to_engine(monkeypatch, db_session.bind)
        repo = EntityPairProximityRepository()

        async with db_session.bind.connect() as holder:  # type: ignore[union-attr]
            # holding the rebuild lock proves dry-run does not need it
            assert await repo.try_acquire_rebuild_lock(holder) is True
            report = await proximity_service.dry_run_proximity(video_ids=videos)
            await repo.release_rebuild_lock(holder)

        assert report.sampled is False
        assert sorted(sc.video_id for sc in report.scopes) == videos
        assert all(sc.records == 1 for sc in report.scopes)
        await db_session.rollback()
        assert await _runs(db_session) == []
        states = await db_session.execute(
            select(func.count()).select_from(ProximityScopeStateDB)
        )
        assert states.scalar_one() == 0
        records = await db_session.execute(
            select(func.count()).select_from(EntityPairProximityDB)
        )
        assert records.scalar_one() == 0

    async def test_dry_run_without_a_scope_samples_a_bounded_set(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _seed_videos(db_session, "smp117", 3)
        route_proximity_service_to_engine(monkeypatch, db_session.bind)

        report = await proximity_service.dry_run_proximity(sample=2)

        assert report.sampled is True and len(report.scopes) == 2

    async def test_force_bumps_revisions_and_resets_failures(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (video_id,) = await _seed_videos(db_session, "frc117", 1)
        route_proximity_service_to_engine(monkeypatch, db_session.bind)
        await proximity_service.rebuild_proximity()
        await db_session.execute(
            update(ProximityScopeStateDB)
            .where(ProximityScopeStateDB.video_id == video_id)
            .values(attempts=5, failed_rule_version="116.9", last_error="old")
        )
        await db_session.commit()
        revision_before = (await _state(db_session, video_id)).revision

        outcome = await proximity_service.rebuild_proximity(force=True)

        assert outcome.status == "completed"
        await db_session.rollback()
        after = await _state(db_session, video_id)
        assert after.revision == revision_before + 1
        assert after.computed_revision == after.revision
        assert (after.attempts, after.failed_rule_version, after.last_error) == (
            0,
            None,
            None,
        )

    async def test_an_unresolved_scope_makes_the_run_incomplete(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad, good = await _seed_videos(db_session, "inc117", 2)
        _fail_for(monkeypatch, {bad})
        route_proximity_service_to_engine(monkeypatch, db_session.bind)

        outcome = await proximity_service.rebuild_proximity()

        assert outcome.status == "incomplete"
        assert outcome.summary is not None
        assert (outcome.summary.processed, outcome.summary.failed) == (1, 1)
        assert outcome.summary.remaining == 1
        await db_session.rollback()
        assert await _runs(db_session) == ["incomplete"]

    async def test_a_reader_sees_the_previous_result_marked_stale_never_a_mixture(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (video_id,) = await _seed_videos(db_session, "rdr117", 1)
        route_proximity_service_to_engine(monkeypatch, db_session.bind)
        await proximity_service.rebuild_proximity()
        await db_session.rollback()
        previous = await logical_records(db_session)
        third = await seed_entity(db_session)
        seg = await seed_segment(db_session, video_id, "en", 3.0, 7)
        await seed_mention(
            db_session,
            entity_id=third,
            video_id=video_id,
            language_code="en",
            segment_id=seg,
        )
        repo = EntityPairProximityRepository()
        await repo.invalidate_proximity_scopes(
            db_session, video_id=video_id, reason="scan"
        )
        await db_session.commit()
        factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

        async with factory() as processor:
            state = await repo.claim_next_scope(
                processor,
                rule_version=MEASUREMENT_RULE_VERSION,
                scope_filter=ScopeFilter(video_ids=(video_id,)),
            )
            assert state is not None
            await recompute_scope(processor, state)  # replaced, NOT committed
            async with factory() as reader:
                seen = await logical_records(reader)
                seen_state = (
                    await reader.execute(
                        select(ProximityScopeStateDB).where(
                            ProximityScopeStateDB.video_id == video_id
                        )
                    )
                ).scalar_one()
            await processor.commit()

        assert seen == previous
        assert seen_state.computed_revision != seen_state.revision  # marked stale
        await db_session.rollback()
        assert len(await logical_records(db_session)) > len(previous)

    async def test_rebuild_and_drain_together_never_publish_a_revision_twice(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        videos = await _seed_videos(db_session, "cnc117", 8)
        route_proximity_service_to_engine(monkeypatch, db_session.bind)
        real = EntityPairProximityRepository.publish_scope
        published: list[tuple[str, str, int]] = []

        async def tracking(self, session, *, video_id, language_code, revision, rule_version):  # type: ignore[no-untyped-def]
            ok = await real(
                self,
                session,
                video_id=video_id,
                language_code=language_code,
                revision=revision,
                rule_version=rule_version,
            )
            if ok:
                published.append((video_id, language_code, revision))
            await asyncio.sleep(0.01)  # widen the interleaving window
            return ok

        monkeypatch.setattr(EntityPairProximityRepository, "publish_scope", tracking)

        rebuild, drain = await asyncio.wait_for(
            asyncio.gather(
                proximity_service.rebuild_proximity(batch=2),
                process_stale_scopes(limit=100),
            ),
            120,
        )

        assert len(published) == len(set(published)), "a revision was published twice"
        await db_session.rollback()
        assert await _current(db_session, videos) == set(videos)
        assert rebuild.status in ("completed", "incomplete")


async def _summary_of(
    session: AsyncSession, a: uuid.UUID, b: uuid.UUID
) -> PairProximitySummary:
    (summary,) = await EntityPairProximityRepository().pair_summaries(
        session, pairs=[(a, b)], rule_version=MEASUREMENT_RULE_VERSION
    )
    return summary


class TestHonestStateAndCounts:
    """T044 (US5): consumers read state, counts and completeness honestly."""

    async def test_scope_states_report_each_state(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        none_row, no_result, zero, stale_rev, stale_rule = _videos("sts117", 5)
        for video_id in (none_row, no_result, zero, stale_rev, stale_rule):
            await seed_video(db_session, video_id)
        await seed_scope_state(
            db_session, video_id=no_result, language_code="en", state="not_computed"
        )
        await _process(db_session, monkeypatch, [zero])  # no mentions: current, zero
        await seed_scope_state(
            db_session, video_id=stale_rev, language_code="en", state="stale"
        )
        await seed_scope_state(
            db_session,
            video_id=stale_rule,
            language_code="en",
            state="current",
            rule_version="116.9",
        )

        states = {
            st.video_id: st
            for st in await EntityPairProximityRepository().scope_states(
                db_session,
                video_ids=[none_row, no_result, zero, stale_rev, stale_rule],
                rule_version=MEASUREMENT_RULE_VERSION,
                failing_threshold=proximity_service.FAILING_ATTEMPTS,
            )
        }

        assert states[none_row].state is ProximityScopeStatus.NOT_COMPUTED
        assert states[none_row].revision is None
        assert states[no_result].state is ProximityScopeStatus.NOT_COMPUTED
        assert states[zero].state is ProximityScopeStatus.CURRENT
        assert states[stale_rev].state is ProximityScopeStatus.STALE
        assert states[stale_rule].state is ProximityScopeStatus.STALE

    async def test_the_removal_counterexample_is_incomplete_until_processed(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """B's last mention leaves a CURRENT scope (its stored record is still
        there). Before processing the scope no longer has both entities, yet it
        still contributes, so the summary must not claim to be settled."""
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        kept, removed = _videos("rmv117", 2)
        await seed_pair_in_videos(
            db_session,
            entity_a=a,
            entity_b=b,
            video_ids=[kept, removed],
            a_time=1,
            b_time=2,
        )
        await _process(db_session, monkeypatch, [kept, removed])
        lo, hi = canonical(a, b)
        settled = await _summary_of(db_session, lo, hi)
        assert (settled.videos_within_120, settled.complete) == (2, True)

        repo = EntityPairProximityRepository()
        await repo.invalidate_proximity_scopes(
            db_session, video_id=removed, reason="correction"
        )
        await db_session.execute(
            delete(EntityMentionDB).where(
                EntityMentionDB.entity_id == b, EntityMentionDB.video_id == removed
            )
        )
        pending = await _summary_of(db_session, lo, hi)
        assert pending.complete is False
        assert pending.videos_within_120 == 2  # the stale record still counts

        route_proximity_service_to(monkeypatch, db_session)
        await process_stale_scopes(
            limit=10, scope_filter=ScopeFilter(video_ids=(removed,))
        )
        final = await _summary_of(db_session, lo, hi)
        assert (final.videos_within_120, final.complete) == (1, True)

    async def test_a_requested_pair_with_no_records_gets_a_zero_row(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        lo, hi = canonical(a, b)
        assert await _summary_of(db_session, lo, hi) == PairProximitySummary(
            entity_a_id=lo,
            entity_b_id=hi,
            videos_within_15=0,
            videos_within_30=0,
            videos_within_60=0,
            videos_within_120=0,
            segment_pairs_within_15=0,
            segment_pairs_within_30=0,
            segment_pairs_within_60=0,
            segment_pairs_within_120=0,
            min_gap_seconds=None,
            complete=True,
        )

        # Both mentioned far apart in one video whose scope is not computed yet:
        # still zero records, but not settled.
        (video_id,) = _videos("zro117", 1)
        await seed_pair_in_videos(
            db_session,
            entity_a=a,
            entity_b=b,
            video_ids=[video_id],
            a_time=0,
            b_time=500,
        )
        pending = await _summary_of(db_session, lo, hi)
        assert (pending.videos_within_120, pending.complete) == (0, False)
        await _process(db_session, monkeypatch, [video_id])
        assert (await _summary_of(db_session, lo, hi)).complete is True

    async def test_two_languages_count_one_video_but_both_segment_pairs(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        (video_id,) = _videos("lng117", 1)
        await seed_video(db_session, video_id, ("en", "es"))
        for language in ("en", "es"):
            await _seed_close_pair(
                db_session,
                video_id=video_id,
                language_code=language,
                entity_a=a,
                entity_b=b,
            )
        await _process(db_session, monkeypatch, [video_id])

        summary = await _summary_of(db_session, *canonical(a, b))

        assert summary.videos_within_120 == 1
        assert summary.segment_pairs_within_120 == 2

    async def test_window_counts_are_inclusive_at_each_boundary(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        gaps = (15.0, 30.0, 60.0, 120.0)
        videos = _videos("bnd117", len(gaps))
        for video_id, gap in zip(videos, gaps, strict=True):
            await seed_pair_in_videos(
                db_session,
                entity_a=a,
                entity_b=b,
                video_ids=[video_id],
                a_time=5.0,
                b_time=5.0 + gap,
            )
        await _process(db_session, monkeypatch, videos)

        summary = await _summary_of(db_session, *canonical(a, b))

        assert (
            summary.videos_within_15,
            summary.videos_within_30,
            summary.videos_within_60,
            summary.videos_within_120,
        ) == (1, 2, 3, 4)
        assert summary.segment_pairs_within_60 == 3
        assert summary.min_gap_seconds == 15.0

    async def test_a_failing_contributing_scope_keeps_the_pair_incomplete(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        good, bad = _videos("fai117", 2)
        await seed_pair_in_videos(
            db_session,
            entity_a=a,
            entity_b=b,
            video_ids=[good, bad],
            a_time=1,
            b_time=2,
        )
        _fail_for(monkeypatch, {bad})
        await _process(db_session, monkeypatch, [good, bad])
        lo, hi = canonical(a, b)

        failing = await _summary_of(db_session, lo, hi)
        assert (failing.videos_within_120, failing.complete) == (1, False)

        monkeypatch.undo()
        await _due_now(db_session, bad)
        await _process(db_session, monkeypatch, [bad])
        assert (await _summary_of(db_session, lo, hi)).complete is True

    async def test_many_pairs_are_chunked_and_still_each_get_their_row(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Past the per-statement pair limit (asyncpg's parameter cap), the call is
        split into chunks; every requested pair still gets exactly one row."""
        from chronovista.repositories import (
            entity_pair_proximity_repository as repo_mod,
        )

        monkeypatch.setattr(repo_mod, "_PAIRS_PER_STATEMENT", 1)
        entities = [await seed_entity(db_session) for _ in range(4)]
        (video_id,) = _videos("chk117", 1)
        await seed_pair_in_videos(
            db_session,
            entity_a=entities[0],
            entity_b=entities[1],
            video_ids=[video_id],
            a_time=1,
            b_time=2,
        )
        await _process(db_session, monkeypatch, [video_id])
        pairs = [
            canonical(entities[0], entities[1]),
            canonical(entities[2], entities[3]),
        ]

        rows = await EntityPairProximityRepository().pair_summaries(
            db_session, pairs=pairs + [pairs[0]], rule_version=MEASUREMENT_RULE_VERSION
        )

        assert [(r.entity_a_id, r.entity_b_id) for r in rows] == sorted(pairs)
        assert [r.videos_within_120 for r in rows] == [
            1 if pair == pairs[0] else 0 for pair in sorted(pairs)
        ]

    async def test_records_for_a_pair_are_traceable_and_windowed(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = await seed_entity(db_session), await seed_entity(db_session)
        near, far = _videos("trc117", 2)
        await seed_pair_in_videos(
            db_session, entity_a=a, entity_b=b, video_ids=[near], a_time=1, b_time=11
        )
        await seed_pair_in_videos(
            db_session, entity_a=a, entity_b=b, video_ids=[far], a_time=1, b_time=91
        )
        await _process(db_session, monkeypatch, [near, far])
        repo = EntityPairProximityRepository()
        lo, hi = canonical(a, b)

        within_30 = await repo.records_for_pair(db_session, lo, hi, window_s=30)
        everything = await repo.records_for_pair(db_session, lo, hi, window_s=120)

        assert [(r.video_id, r.gap_seconds) for r in within_30] == [(near, 10.0)]
        assert sorted(r.video_id for r in everything) == sorted([near, far])
        assert all(
            r.segment_a_id and r.segment_b_id and r.language_code for r in everything
        )


class TestCandidatesUntouched:
    async def test_proximity_never_writes_candidates_signals_or_verdicts(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-008 / FR-022 / SC-008: measuring, rebuilding, draining and invalidating
        leave every relationship-candidate parent, signal and verdict byte-identical."""
        videos = await _seed_videos(db_session, "fpr117", 5)
        mentions = (
            await db_session.execute(
                select(EntityMentionDB.entity_id).where(
                    EntityMentionDB.video_id == videos[0]
                )
            )
        ).scalars()
        lo, hi = sorted(set(mentions))
        parent = RelationshipCandidateDB(
            entity_a_id=lo,
            entity_b_id=hi,
            channel="transcript",
            shared_video_count=5,
            lift=None,
            entity_a_video_count=5,
            entity_b_video_count=5,
            channel_video_universe=5,
            review_status="associated_with",
            reviewed_by="test",
        )
        db_session.add(parent)
        await db_session.flush()
        db_session.add(
            SignalDB(
                candidate_id=parent.id,
                signal="transcript",
                support=5,
                lift=None,
                min_gap_seconds=1.0,
                entity_a_video_count=5,
                entity_b_video_count=5,
                signal_universe=5,
            )
        )
        await db_session.commit()

        async def fingerprint() -> list[tuple[str, ...]]:
            await db_session.rollback()
            rows: list[tuple[str, ...]] = []
            for model in (RelationshipCandidateDB, SignalDB):
                result = await db_session.execute(
                    select(*model.__table__.columns).order_by(model.__table__.c.id)
                )
                rows += [tuple(map(str, row)) for row in result.all()]
            return rows

        before = await fingerprint()
        route_proximity_service_to_engine(monkeypatch, db_session.bind)
        await asyncio.wait_for(proximity_service.rebuild_proximity(force=True), 120)
        await EntityPairProximityRepository().invalidate_proximity_scopes(
            db_session, entity_id=lo, reason="test"
        )
        await db_session.commit()
        await asyncio.wait_for(proximity_service.drain_stale_scopes(limit=100), 120)
        await EntityPairProximityRepository().pair_summaries(
            db_session, entity_id=lo, rule_version=MEASUREMENT_RULE_VERSION
        )

        assert await fingerprint() == before
        assert len(before) == 2  # one parent and one signal were really compared


class TestOperatorStatus:
    async def test_status_reports_the_oldest_not_current_scope_and_ignores_current(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-024: the real query, not a hand-built report (the CLI test mocks it)."""
        current, old_stale, new_stale = _videos("old117", 3)
        for video_id in (current, old_stale, new_stale):
            await seed_video(db_session, video_id)
        await seed_scope_state(
            db_session, video_id=current, language_code="en", state="current"
        )
        for video_id in (old_stale, new_stale):
            await seed_scope_state(
                db_session, video_id=video_id, language_code="en", state="stale"
            )
        ages = {
            current: datetime.timedelta(days=30),  # oldest, but current: ignored
            old_stale: datetime.timedelta(days=3),
            new_stale: datetime.timedelta(hours=1),
        }
        for video_id, age in ages.items():
            await db_session.execute(
                update(ProximityScopeStateDB)
                .where(ProximityScopeStateDB.video_id == video_id)
                .values(invalidated_at=func.now() - age)
            )
        await db_session.commit()
        route_proximity_service_to_engine(monkeypatch, db_session.bind)

        report = await proximity_service.proximity_status()

        old = (
            await db_session.execute(
                select(ProximityScopeStateDB.invalidated_at).where(
                    ProximityScopeStateDB.video_id == old_stale
                )
            )
        ).scalar_one()
        assert report.oldest_not_current_at == old
        assert (report.current, report.stale) == (1, 2)


class TestStatementBound:
    async def test_a_rebuild_needs_no_statement_longer_than_one_scope(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SC-006: the full rebuild is bounded per scope, so it completes under a
        statement timeout far below the production 60 s. A corpus-wide statement
        (the Feature 116 design) would exceed it as the library grows."""
        await _seed_videos(db_session, "stm117", 6)
        bounded = create_async_engine(
            db_session.bind.url,  # type: ignore[union-attr]
            connect_args={"server_settings": {"statement_timeout": "1000"}},
        )
        try:
            route_proximity_service_to_engine(monkeypatch, bounded)
            outcome = await asyncio.wait_for(
                proximity_service.rebuild_proximity(force=True, batch=2), 120
            )
        finally:
            await bounded.dispose()

        assert outcome.status == "completed"
