"""Integration tests for the transcript-channel generator (Feature 116).

The critical guard (cdwa review 2026-11-21): a transcript run must NOT corrupt an existing
UNREVIEWED title/description parent. Nullable parent lift removed the accidental NOT-NULL guard
at the upsert site, so the net is rebuilt deliberately as the anti-join (net-new only). Disable
the anti-join in ``compute_transcript_candidates`` and the mutation guard below fails. Uses the
``db_manager.session`` patch pattern so the whole orchestration runs against the test session.
Name-free placeholders only (Constitution VI).
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import chronovista.config.database as db_mod
from chronovista.db.models import EntityPairProximityRollup as RollupDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import RelationshipCandidate as RelationshipCandidateDB
from chronovista.db.models import RelationshipCandidateSignal as SignalDB
from chronovista.models.relationship_candidate import RelationshipCandidateCreate
from chronovista.repositories.relationship_candidate_repository import (
    RelationshipCandidateRepository,
)
from chronovista.services import relationship_candidate_service as svc

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
    session.add(
        RollupDB(
            entity_a_id=lo,
            entity_b_id=hi,
            close_co_mentions_15=4,
            close_co_mentions_30=4,
            close_co_mentions_60=4,
            min_gap_seconds=min_gap,
            shared_videos=shared,
            computed_at=datetime.datetime.now(datetime.UTC),
        )
    )
    await session.flush()


async def _clear(session: AsyncSession) -> None:
    # Shared integration DB: control the populations the generator reads (candidates cascade
    # to their children; rollup rows are the transcript pair source).
    await session.execute(delete(RelationshipCandidateDB))
    await session.execute(delete(RollupDB))
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
        assert summary["deferred"] == 0
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

    async def test_transcript_run_does_not_corrupt_unreviewed_td_parent(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MUTATION GUARD (cdwa #3). Disable the anti-join in
        ``compute_transcript_candidates`` and this fails: the unreviewed title/description
        parent's lift is nulled and its channel relabelled by the upsert."""
        repo = RelationshipCandidateRepository()
        await _clear(db_session)
        a = await _entity(db_session, "Dup A")
        b = await _entity(db_session, "Dup B")
        lo, hi = (a, b) if a < b else (b, a)
        # An UNREVIEWED title/description parent — the population the guard removed exposed.
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

        assert summary["deferred"] == 1  # anti-joined, not emitted
        assert summary["written"] == 0
        parent = (
            await db_session.execute(
                select(RelationshipCandidateDB)
                .where(RelationshipCandidateDB.entity_a_id == lo)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        # UNCHANGED: a transcript run must not corrupt an unreviewed title/description parent.
        assert parent.lift == 42.0
        assert parent.channel == "title_description"
        # ...and no transcript child was attached to it either.
        children: list[Any] = (
            (
                await db_session.execute(
                    select(SignalDB).where(SignalDB.candidate_id == parent.id)
                )
            )
            .scalars()
            .all()
        )
        assert children == []


class TestTranscriptGenerateSafety:
    """Feature 116 / US3 regeneration safety — invariants independent of the substep-(b)
    head-query decision: reviewed rows untouched (SC-003), title/description head membership
    unchanged (SC-004), and idempotency (SC-007)."""

    async def test_transcript_run_leaves_a_reviewed_td_parent_untouched(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SC-003: a transcript run must not alter a REVIEWED title/description parent —
        verdict, metrics, and channel all stand (the pair is anti-joined)."""
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

        assert summary["deferred"] == 1
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
        assert children == []  # dual-signal evidence deferred, not merged here

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
        before, before_total, _ = await repo.list_ranked(db_session)
        before_ids = [r.id for r in before]
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
        anti-joins run 1's pairs (now existing) — it writes nothing and defers them all.
        """
        await _clear(db_session)
        a = await _entity(db_session, "Idem A")
        b = await _entity(db_session, "Idem B")
        lo, hi = sorted([a, b])
        await _rollup(db_session, lo, hi, shared=7)
        _patch_session(monkeypatch, db_session)

        first = await svc.generate_transcript_candidates()
        assert first["written"] == 1 and first["deferred"] == 0

        second = await svc.generate_transcript_candidates()
        assert second["written"] == 0  # the pair now exists -> anti-joined
        assert second["deferred"] == 1

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
