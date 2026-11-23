"""Integration tests for the transcript-channel generator (Feature 116).

The critical guard (cdwa review 2026-11-21, extended for the T026b dual-signal merge
2026-11-22): a transcript run must NEVER modify an existing title/description parent — reviewed
or not. Net-new pairs become transcript parents; an existing parent that co-occurs in
transcripts is merged as a DUAL signal — a transcript child attached via ``upsert_signals``
(child table only), with the parent row untouched. The merge is verdict-preserving BY
CONSTRUCTION because only net-new parents are upserted: add the existing parents to the
``upsert_many`` set and the mutation guards below fail (the existing parent's lift is nulled and
its channel relabelled). Uses the ``db_manager.session`` patch pattern so the whole
orchestration runs against the test session. Name-free placeholders only (Constitution VI).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import chronovista.config.database as db_mod
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import RelationshipCandidate as RelationshipCandidateDB
from chronovista.db.models import RelationshipCandidateSignal as SignalDB
from chronovista.models.relationship_candidate import (
    CandidateSignal,
    RelationshipCandidateCreate,
    RelationshipCandidateSignalCreate,
)
from chronovista.repositories.relationship_candidate_repository import (
    RelationshipCandidateRepository,
)
from chronovista.services import relationship_candidate_service as svc
from tests.factories.proximity_seed import seed_segment, seed_video

pytestmark = pytest.mark.asyncio


async def _entity(session: AsyncSession, name: str) -> uuid.UUID:
    eid = uuid.uuid4()
    session.add(
        NamedEntityDB(
            id=eid,
            canonical_name=name,
            canonical_name_normalized=name.lower(),
            entity_type="person",
        )
    )
    await session.flush()
    return eid


async def _rollup(
    session: AsyncSession,
    lo: uuid.UUID,
    hi: uuid.UUID,
    *,
    shared: int,
    min_gap: float = 3.0,
) -> None:
    """Seed co-mention records so the DERIVED ``read_rollup`` reports ``(shared, min_gap)``.

    Since Feature 117 the queue's input is derived on read from the records, so this
    writes ``shared`` distinct videos, each with one record at ``min_gap`` seconds.
    """
    for n in range(shared):
        video_id = f"tc{uuid.uuid4().hex[:12]}{n:02d}"
        await seed_video(session, video_id)
        seg_a = await seed_segment(session, video_id, "en", 10.0, 0)
        seg_b = await seed_segment(session, video_id, "en", 10.0 + min_gap, 1)
        session.add(
            EntityPairProximityDB(
                entity_a_id=lo,
                entity_b_id=hi,
                video_id=video_id,
                language_code="en",
                segment_a_id=seg_a,
                segment_b_id=seg_b,
                gap_seconds=min_gap,
            )
        )
    await session.flush()


async def _clear(session: AsyncSession) -> None:
    # Shared integration DB: control the populations the generator reads (candidates cascade
    # to their children; co-mention records are the transcript pair source).
    await session.execute(delete(RelationshipCandidateDB))
    await session.execute(delete(EntityPairProximityDB))
    await session.flush()


def _patch_session(monkeypatch: pytest.MonkeyPatch, session: AsyncSession) -> None:
    @asynccontextmanager
    async def _scope() -> AsyncGenerator[AsyncSession, None]:
        yield session

    monkeypatch.setattr(db_mod.db_manager, "session", _scope)


class TestTranscriptGenerate:
    async def test_net_new_pair_creates_transcript_parent_and_child(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _clear(db_session)
        a = await _entity(db_session, "Gen A")
        b = await _entity(db_session, "Gen B")
        lo, hi = (a, b) if a < b else (b, a)
        await _rollup(db_session, lo, hi, shared=7)
        _patch_session(monkeypatch, db_session)

        summary = await svc.generate_transcript_candidates()

        assert summary["written"] == 1
        assert summary["children"] == 1
        assert summary["merged"] == 0 and summary["dropped"] == 0
        parent = (
            await db_session.execute(
                select(RelationshipCandidateDB)
                .where(RelationshipCandidateDB.entity_a_id == lo)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert parent.channel == "transcript"
        assert parent.lift is None
        assert parent.shared_video_count == 7  # support == shared_videos
        child = (
            await db_session.execute(
                select(SignalDB).where(SignalDB.candidate_id == parent.id)
            )
        ).scalar_one()
        assert child.signal == "transcript"
        assert child.support == 7
        assert child.lift is None
        assert child.min_gap_seconds == 3.0

    async def test_queue_keeps_its_own_support_floor_over_ungated_records(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Feature 117 removed the gate from MEASUREMENT, not from the queue (FR-008).

        One-video and four-video pairs now have records, but only the pair at the
        queue's ``SUPPORT_MIN`` becomes a candidate, so ungating the primitive cannot
        flood the deferred queue.
        """
        await _clear(db_session)
        pairs = []
        for shared in (1, svc.SUPPORT_MIN - 1, svc.SUPPORT_MIN):
            a = await _entity(db_session, f"Floor {shared} A {uuid.uuid4().hex[:6]}")
            b = await _entity(db_session, f"Floor {shared} B {uuid.uuid4().hex[:6]}")
            lo, hi = (a, b) if a < b else (b, a)
            await _rollup(db_session, lo, hi, shared=shared)
            pairs.append((shared, lo))
        _patch_session(monkeypatch, db_session)

        summary = await svc.generate_transcript_candidates()

        assert summary["written"] == 1
        parents = (
            (await db_session.execute(select(RelationshipCandidateDB.entity_a_id)))
            .scalars()
            .all()
        )
        assert parents == [lo for shared, lo in pairs if shared == svc.SUPPORT_MIN]

    async def test_transcript_merge_leaves_unreviewed_td_parent_row_untouched(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MUTATION GUARD (cdwa #3, T026b). The dual-signal merge attaches a transcript child to
        an existing UNREVIEWED title/description parent WITHOUT upserting the parent. Add the
        existing parents to the ``upsert_many`` set and this fails: the parent's lift is nulled
        (42.0 -> None) and its channel relabelled to ``transcript``."""
        repo = RelationshipCandidateRepository()
        await _clear(db_session)
        a = await _entity(db_session, "Dup A")
        b = await _entity(db_session, "Dup B")
        lo, hi = (a, b) if a < b else (b, a)
        # An UNREVIEWED title/description parent that also co-occurs in transcripts.
        await repo.upsert_many(
            db_session,
            candidates=[
                RelationshipCandidateCreate(
                    entity_a_id=lo,
                    entity_b_id=hi,
                    channel="title_description",
                    shared_video_count=9,
                    lift=42.0,
                    entity_a_video_count=10,
                    entity_b_video_count=12,
                    channel_video_universe=40000,
                )
            ],
        )
        await _rollup(
            db_session, lo, hi, shared=7
        )  # same pair, in the transcript rollup
        _patch_session(monkeypatch, db_session)

        summary = await svc.generate_transcript_candidates()

        assert summary["written"] == 0  # no net-new parent
        assert summary["merged"] == 1  # the existing parent gained a transcript child
        parent = (
            await db_session.execute(
                select(RelationshipCandidateDB)
                .where(RelationshipCandidateDB.entity_a_id == lo)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        # UNCHANGED parent row: the merge must not upsert the parent.
        assert parent.lift == 42.0
        assert parent.channel == "title_description"
        # ...but a transcript child IS now attached (the dual signal).
        children: list[Any] = (
            (
                await db_session.execute(
                    select(SignalDB).where(SignalDB.candidate_id == parent.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(children) == 1
        assert children[0].signal == "transcript"
        assert children[0].support == 7
        assert children[0].lift is None


class TestTranscriptGenerateSafety:
    """Feature 116 / US3 regeneration safety — invariants independent of the substep-(b)
    head-query decision: reviewed rows untouched (SC-003), title/description head membership
    unchanged (SC-004), and idempotency (SC-007)."""

    async def test_transcript_merge_preserves_a_reviewed_td_verdict(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SC-003 + T026b: a transcript run attaches a transcript child to a REVIEWED
        title/description parent (a free calibration label — the human already judged the pair)
        but must NOT alter its verdict, metrics, or channel. The parent is never upserted, so the
        verdict is preserved by construction; break that (upsert the existing parent) and the
        verdict/lift/channel assertions fail."""
        repo = RelationshipCandidateRepository()
        await _clear(db_session)
        a = await _entity(db_session, "Rev A")
        b = await _entity(db_session, "Rev B")
        lo, hi = sorted([a, b])
        await repo.upsert_many(
            db_session,
            candidates=[
                RelationshipCandidateCreate(
                    entity_a_id=lo,
                    entity_b_id=hi,
                    channel="title_description",
                    shared_video_count=9,
                    lift=42.0,
                    entity_a_video_count=10,
                    entity_b_video_count=12,
                    channel_video_universe=40000,
                )
            ],
        )
        await db_session.execute(
            update(RelationshipCandidateDB)
            .where(RelationshipCandidateDB.entity_a_id == lo)
            .values(review_status="related", review_taxonomy_version="v1")
        )
        await db_session.flush()
        await _rollup(
            db_session, lo, hi, shared=7
        )  # same pair, transcript co-occurrence
        _patch_session(monkeypatch, db_session)

        summary = await svc.generate_transcript_candidates()

        assert summary["merged"] == 1  # reviewed parent gained a transcript child
        assert summary["written"] == 0
        parent = (
            await db_session.execute(
                select(RelationshipCandidateDB)
                .where(RelationshipCandidateDB.entity_a_id == lo)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert parent.review_status == "related"  # verdict untouched
        assert parent.lift == 42.0
        assert parent.channel == "title_description"
        children = (
            (
                await db_session.execute(
                    select(SignalDB).where(SignalDB.candidate_id == parent.id)
                )
            )
            .scalars()
            .all()
        )
        assert (
            len(children) == 1
        )  # the calibration label (transcript evidence) is attached
        assert children[0].signal == "transcript"

    async def test_transcript_run_leaves_td_head_membership_unchanged(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SC-004: a transcript run does not change the title/description head membership."""
        repo = RelationshipCandidateRepository()
        await _clear(db_session)
        tda = await _entity(db_session, "TD A")
        tdb = await _entity(db_session, "TD B")
        tlo, thi = sorted([tda, tdb])
        await repo.upsert_many(
            db_session,
            candidates=[
                RelationshipCandidateCreate(
                    entity_a_id=tlo,
                    entity_b_id=thi,
                    channel="title_description",
                    shared_video_count=9,
                    lift=42.0,
                    entity_a_video_count=10,
                    entity_b_video_count=12,
                    channel_video_universe=40000,
                )
            ],
        )
        # The td parent needs its td child to be visible in the child-join head (D3a/T032);
        # without it the before/after comparison below would be a vacuous [] == [].
        td_ids = await repo.ids_for_pairs(db_session, pairs=[(tlo, thi)])
        await repo.upsert_signals(
            db_session,
            signals=[
                RelationshipCandidateSignalCreate(
                    candidate_id=td_ids[(tlo, thi)],
                    signal=CandidateSignal.TITLE_DESCRIPTION,
                    support=9,
                    lift=42.0,
                    entity_a_video_count=10,
                    entity_b_video_count=12,
                    signal_universe=40000,
                )
            ],
        )
        before, before_total, _ = await repo.list_ranked(db_session)
        before_ids = [r.id for r in before]
        assert before_total == 1  # non-vacuous: the td parent is in the head
        # A NET-NEW transcript pair (different entities).
        tra = await _entity(db_session, "TR A")
        trb = await _entity(db_session, "TR B")
        rlo, rhi = sorted([tra, trb])
        await _rollup(db_session, rlo, rhi, shared=7)
        _patch_session(monkeypatch, db_session)

        await svc.generate_transcript_candidates()

        after, after_total, _ = await repo.list_ranked(db_session)
        assert [
            r.id for r in after
        ] == before_ids  # SC-004: membership + order unchanged
        assert after_total == before_total

    async def test_transcript_generation_is_idempotent(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SC-007: re-running a transcript generation yields the same DB state. The second run
        finds run 1's pair already present and MERGES it — it creates no new parent and
        re-upserts the same transcript child in place (ON CONFLICT), so the parent and child
        counts are unchanged.
        """
        await _clear(db_session)
        a = await _entity(db_session, "Idem A")
        b = await _entity(db_session, "Idem B")
        lo, hi = sorted([a, b])
        await _rollup(db_session, lo, hi, shared=7)
        _patch_session(monkeypatch, db_session)

        first = await svc.generate_transcript_candidates()
        assert first["written"] == 1 and first["merged"] == 0

        second = await svc.generate_transcript_candidates()
        assert second["written"] == 0  # the pair now exists -> merged, not re-created
        assert (
            second["merged"] == 1
        )  # its transcript child is re-upserted (ON CONFLICT)

        parents = (
            (
                await db_session.execute(
                    select(RelationshipCandidateDB)
                    .where(RelationshipCandidateDB.channel == "transcript")
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        assert len(parents) == 1  # not duplicated
        children = (
            (
                await db_session.execute(
                    select(SignalDB).where(SignalDB.candidate_id == parents[0].id)
                )
            )
            .scalars()
            .all()
        )
        assert len(children) == 1


class TestOrphanGuard:
    """Feature 116 / D2 (cdwa 2026-11-22). The Option-C invariant — every parent carries a
    per-signal child — is ENFORCED, not hoped: `count_childless_parents` is the consistency
    check that makes the child-join read (T032) safe. Mutation-verified against the t/d
    generator's child write (D1)."""

    async def test_count_childless_parents_detects_and_clears(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        await _clear(db_session)
        a = await _entity(db_session, "Orphan A")
        b = await _entity(db_session, "Orphan B")
        lo, hi = sorted([a, b])
        await repo.upsert_many(
            db_session,
            candidates=[
                RelationshipCandidateCreate(
                    entity_a_id=lo,
                    entity_b_id=hi,
                    channel="title_description",
                    shared_video_count=9,
                    lift=42.0,
                    entity_a_video_count=10,
                    entity_b_video_count=12,
                    channel_video_universe=40000,
                )
            ],
        )
        assert (
            await repo.count_childless_parents(db_session) == 1
        )  # childless -> detected
        pair_ids = await repo.ids_for_pairs(db_session, pairs=[(lo, hi)])
        await repo.upsert_signals(
            db_session,
            signals=[
                RelationshipCandidateSignalCreate(
                    candidate_id=pair_ids[(lo, hi)],
                    signal=CandidateSignal.TITLE_DESCRIPTION,
                    support=9,
                    lift=42.0,
                    entity_a_video_count=10,
                    entity_b_video_count=12,
                    signal_universe=40000,
                )
            ],
        )
        assert (
            await repo.count_childless_parents(db_session) == 0
        )  # child attached -> cleared

    async def test_td_generator_leaves_no_childless_parent(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D1 mutation-verified: the t/d generator writes a title_description child per parent.
        Remove that write and this fails (count_childless_parents > 0)."""
        repo = RelationshipCandidateRepository()
        await db_session.execute(delete(EntityMentionDB))
        await db_session.execute(delete(RelationshipCandidateDB))
        await db_session.flush()
        a = await _entity(db_session, "Gtd A")
        b = await _entity(db_session, "Gtd B")
        filler = await _entity(db_session, "Gtd Filler")
        # a and b co-occur in 5 videos (support 5); 20 filler videos push N to 25, so
        # lift = 5*25/(5*5) = 5 clears the floor and one candidate is produced.
        for i in range(5):
            db_session.add(
                EntityMentionDB(
                    id=uuid.uuid4(),
                    entity_id=a,
                    video_id=f"v{i}",
                    mention_text="x",
                    mention_source="title",
                )
            )
            db_session.add(
                EntityMentionDB(
                    id=uuid.uuid4(),
                    entity_id=b,
                    video_id=f"v{i}",
                    mention_text="x",
                    mention_source="title",
                )
            )
        for i in range(5, 25):
            db_session.add(
                EntityMentionDB(
                    id=uuid.uuid4(),
                    entity_id=filler,
                    video_id=f"v{i}",
                    mention_text="x",
                    mention_source="title",
                )
            )
        await db_session.flush()
        _patch_session(monkeypatch, db_session)

        summary = await svc.generate_relationship_candidates()

        assert summary["written"] == 1  # the (a, b) pair
        assert summary["children"] == 1  # D1: the td child was written
        assert await repo.count_childless_parents(db_session) == 0
