"""Real-DB tests for ``RelationshipCandidateRepository`` (Feature 107).

Exercises what only a real Postgres run verifies: idempotent upsert on the
canonical pair key (refresh metrics in place, preserve identity, never overwrite a
verdict), the lift-ranked read with the eligible-only and min-support filters, and
delete-if-absent reconciliation (remove unverdicted stale pairs, keep verdicted and
re-emitted ones). Uses the ``db_session`` fixture (create_all + drop_all per test).
Name-free placeholders only (Constitution VI).
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

import chronovista.repositories.relationship_candidate_repository as repo_mod
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import RelationshipCandidate as RelationshipCandidateDB
from chronovista.db.models import (
    RelationshipCandidateGenerationRun as RelationshipCandidateGenerationRunDB,
)
from chronovista.models.relationship_candidate import RelationshipCandidateCreate
from chronovista.repositories.relationship_candidate_repository import (
    RelationshipCandidateRepository,
)

pytestmark = pytest.mark.asyncio


async def _make_entity(session: AsyncSession, name: str) -> NamedEntityDB:
    entity = NamedEntityDB(
        id=uuid.uuid4(),
        canonical_name=name,
        canonical_name_normalized=name.lower(),
        entity_type="person",
    )
    session.add(entity)
    await session.flush()
    return entity


def _ordered(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if a < b else (b, a)


def _cand(a: uuid.UUID, b: uuid.UUID, **over: object) -> RelationshipCandidateCreate:
    lo, hi = _ordered(a, b)
    base: dict[str, object] = {
        "entity_a_id": lo,
        "entity_b_id": hi,
        "channel": "title_description",
        "shared_video_count": 7,
        "lift": 50.0,
        "entity_a_video_count": 10,
        "entity_b_video_count": 12,
        "channel_video_universe": 40000,
        "both_typed_eligible": True,
        "kb_corroboration_count": 0,
        "kb_corroboration_detail": {},
        "provenance": {"channel": "title_description", "N": 40000, "corpus_size": 2000},
    }
    base.update(over)
    return RelationshipCandidateCreate(**base)  # type: ignore[arg-type]


class TestUpsert:
    async def test_inserts_then_refreshes_in_place(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "Placeholder A")
        e2 = await _make_entity(db_session, "Placeholder B")

        n = await repo.upsert_many(db_session, candidates=[_cand(e1.id, e2.id)])
        assert n == 1
        rows, total = await repo.list_ranked(db_session)
        assert total == 1
        original_id = rows[0].id
        assert rows[0].lift == 50.0

        # Re-emit the SAME pair with new metrics -> update in place, same id.
        await repo.upsert_many(
            db_session,
            candidates=[_cand(e1.id, e2.id, lift=99.0, shared_video_count=9)],
        )
        rows, total = await repo.list_ranked(db_session)
        assert total == 1  # not duplicated
        assert rows[0].id == original_id  # identity preserved
        assert rows[0].lift == 99.0
        assert rows[0].shared_video_count == 9

    async def test_refresh_leaves_verdict_untouched(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "Placeholder C")
        e2 = await _make_entity(db_session, "Placeholder D")
        await repo.upsert_many(db_session, candidates=[_cand(e1.id, e2.id)])

        # Simulate a future verdict written directly (MVP has no verdict UI).
        await db_session.execute(
            update(RelationshipCandidateDB)
            .where(RelationshipCandidateDB.entity_a_id == min(e1.id, e2.id))
            .values(review_status="related", review_taxonomy_version="v1")
        )
        await db_session.flush()

        # A re-run must NOT overwrite the verdict (WHERE review_status IS NULL).
        await repo.upsert_many(db_session, candidates=[_cand(e1.id, e2.id, lift=77.0)])
        rows, _ = await repo.list_ranked(db_session)
        assert rows[0].review_status == "related"
        assert rows[0].lift == 50.0  # metrics unchanged on a verdicted row


class TestListRanked:
    async def test_orders_by_lift_desc(self, db_session: AsyncSession) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "P1")
        e2 = await _make_entity(db_session, "P2")
        e3 = await _make_entity(db_session, "P3")
        await repo.upsert_many(
            db_session,
            candidates=[
                _cand(e1.id, e2.id, lift=10.0),
                _cand(e1.id, e3.id, lift=500.0),
                _cand(e2.id, e3.id, lift=80.0),
            ],
        )
        rows, total = await repo.list_ranked(db_session)
        assert total == 3
        lifts = [r.lift for r in rows]
        assert lifts == sorted(lifts, reverse=True)
        assert (
            lifts[0] == 500.0
        )  # the support-5-style high-lift head is NOT floored out

    async def test_eligible_only_and_min_support_filters(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "Q1")
        e2 = await _make_entity(db_session, "Q2")
        e3 = await _make_entity(db_session, "Q3")
        await repo.upsert_many(
            db_session,
            candidates=[
                _cand(e1.id, e2.id, both_typed_eligible=True, shared_video_count=5),
                _cand(e1.id, e3.id, both_typed_eligible=False, shared_video_count=20),
            ],
        )
        elig, elig_total = await repo.list_ranked(db_session, eligible_only=True)
        assert elig_total == 1 and elig[0].both_typed_eligible is True

        tight, tight_total = await repo.list_ranked(db_session, min_support=10)
        assert tight_total == 1 and tight[0].shared_video_count == 20


class TestDeleteStale:
    async def test_removes_unemitted_unverdicted_keeps_others(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "R1")
        e2 = await _make_entity(db_session, "R2")
        e3 = await _make_entity(db_session, "R3")
        # Two pairs written "last run".
        await repo.upsert_many(
            db_session,
            candidates=[_cand(e1.id, e2.id), _cand(e1.id, e3.id, lift=60.0)],
        )
        # Verdict one of them so it must survive even if not re-emitted.
        await db_session.execute(
            update(RelationshipCandidateDB)
            .where(RelationshipCandidateDB.entity_b_id == max(e1.id, e3.id))
            .where(RelationshipCandidateDB.entity_a_id == min(e1.id, e3.id))
            .values(review_status="related")
        )
        await db_session.flush()

        # New run re-emits ONLY the first pair.
        run_started = datetime.datetime.now(datetime.UTC)
        await repo.upsert_many(db_session, candidates=[_cand(e1.id, e2.id, lift=70.0)])
        removed = await repo.delete_stale(db_session, run_started_at=run_started)

        assert removed == 0  # the stale pair was verdicted -> kept
        rows, total = await repo.list_ranked(db_session)
        assert total == 2  # re-emitted (unverdicted) + verdicted both present

    async def test_removes_a_stale_unverdicted_pair(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "S1")
        e2 = await _make_entity(db_session, "S2")
        await repo.upsert_many(db_session, candidates=[_cand(e1.id, e2.id)])
        # A later run that re-emits nothing -> the pair is stale and unverdicted.
        later = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=1)
        removed = await repo.delete_stale(db_session, run_started_at=later)
        assert removed == 1
        _, total = await repo.list_ranked(db_session)
        assert total == 0


class TestUpsertRobustness:
    async def test_empty_upsert_returns_zero(self, db_session: AsyncSession) -> None:
        repo = RelationshipCandidateRepository()
        assert await repo.upsert_many(db_session, candidates=[]) == 0

    async def test_chunks_many_pairs(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force the chunk boundary (finding 1 regression): 3 pairs at chunk size 2
        # exercises the multi-chunk path. A single un-chunked INSERT would exceed
        # asyncpg's bind-param ceiling at library scale.
        monkeypatch.setattr(repo_mod, "_UPSERT_CHUNK_SIZE", 2)
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "Chunk 1")
        e2 = await _make_entity(db_session, "Chunk 2")
        e3 = await _make_entity(db_session, "Chunk 3")
        n = await repo.upsert_many(
            db_session,
            candidates=[
                _cand(e1.id, e2.id),
                _cand(e1.id, e3.id),
                _cand(e2.id, e3.id),
            ],
        )
        assert n == 3
        _, total = await repo.list_ranked(db_session)
        assert total == 3

    async def test_dedupes_repeated_pair_in_one_call(
        self, db_session: AsyncSession
    ) -> None:
        # Two create models for the same canonical pair in one call must not raise
        # "ON CONFLICT ... cannot affect row a second time"; last wins.
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "Dup 1")
        e2 = await _make_entity(db_session, "Dup 2")
        n = await repo.upsert_many(
            db_session,
            candidates=[_cand(e1.id, e2.id, lift=10.0), _cand(e1.id, e2.id, lift=88.0)],
        )
        assert n == 1
        rows, total = await repo.list_ranked(db_session)
        assert total == 1 and rows[0].lift == 88.0


class TestNoSupportFloor:
    async def test_min_support_high_lift_row_survives_default_read(
        self, db_session: AsyncSession
    ) -> None:
        # R2 contract: a support==5, very-high-lift pair (the measured best cell) is
        # NOT floored out — it must appear in list_ranked at the default min_support.
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "Floor 1")
        e2 = await _make_entity(db_session, "Floor 2")
        await repo.upsert_many(
            db_session,
            candidates=[_cand(e1.id, e2.id, shared_video_count=5, lift=350.0)],
        )
        rows, total = await repo.list_ranked(db_session)
        assert total == 1
        assert rows[0].shared_video_count == 5 and rows[0].lift == 350.0


class TestGenerationRun:
    async def test_start_then_finish(self, db_session: AsyncSession) -> None:
        repo = RelationshipCandidateRepository()
        await db_session.execute(delete(RelationshipCandidateGenerationRunDB))
        run = await repo.start_run(
            db_session, channel="title_description", generator_version="107.1"
        )
        assert run is not None and run.status == "running"
        await repo.finish_run(
            db_session,
            run_id=run.id,
            status="completed",
            channel_video_universe=1000,
            corpus_size=50,
            candidates_written=42,
            candidates_removed=3,
        )
        refreshed = await db_session.get(RelationshipCandidateGenerationRunDB, run.id)
        assert refreshed is not None
        assert refreshed.status == "completed"
        assert refreshed.candidates_written == 42
        assert refreshed.candidates_removed == 3
        assert refreshed.completed_at is not None

    async def test_running_lock_blocks_a_second_run(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        await db_session.execute(delete(RelationshipCandidateGenerationRunDB))
        first = await repo.start_run(
            db_session, channel="title_description", generator_version="107.1"
        )
        assert first is not None
        # A second start while one is 'running' is refused by the partial unique index.
        second = await repo.start_run(
            db_session, channel="title_description", generator_version="107.1"
        )
        assert second is None
        # After the first finishes, a new run may start.
        await repo.finish_run(
            db_session,
            run_id=first.id,
            status="completed",
            channel_video_universe=0,
            corpus_size=0,
            candidates_written=0,
            candidates_removed=0,
        )
        third = await repo.start_run(
            db_session, channel="title_description", generator_version="107.1"
        )
        assert third is not None
