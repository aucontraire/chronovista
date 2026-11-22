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
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import chronovista.repositories.relationship_candidate_repository as repo_mod
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import RelationshipCandidate as RelationshipCandidateDB
from chronovista.db.models import (
    RelationshipCandidateGenerationRun as RelationshipCandidateGenerationRunDB,
)
from chronovista.db.models import (
    RelationshipCandidateSignal as RelationshipCandidateSignalDB,
)
from chronovista.models.relationship_candidate import (
    CandidateSignal,
    RelationshipCandidateCreate,
    RelationshipCandidateSignalCreate,
)
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


async def _seed(
    session: AsyncSession, *, candidates: list[RelationshipCandidateCreate]
) -> int:
    """Upsert parents AND a title_description child per parent — ``list_ranked`` reads through the
    child (Feature 116), so a read test must seed both, mirroring what the migration and the t/d
    generator do. Drop-in for ``_seed(session, candidates=...)``; returns the parent
    upsert count. Uses its own repo instance so it can replace bare upsert_many call sites.
    """
    _r = RelationshipCandidateRepository()
    written = await _r.upsert_many(session, candidates=candidates)
    pair_ids = await _r.ids_for_pairs(
        session, pairs=[(c.entity_a_id, c.entity_b_id) for c in candidates]
    )
    await _r.upsert_signals(
        session,
        signals=[
            RelationshipCandidateSignalCreate(
                candidate_id=pair_ids[(c.entity_a_id, c.entity_b_id)],
                signal=CandidateSignal.TITLE_DESCRIPTION,
                support=c.shared_video_count,
                lift=c.lift,
                entity_a_video_count=c.entity_a_video_count,
                entity_b_video_count=c.entity_b_video_count,
                signal_universe=c.channel_video_universe,
                both_typed_eligible=c.both_typed_eligible,
                kb_corroboration_count=c.kb_corroboration_count,
                kb_corroboration_detail=c.kb_corroboration_detail,
                provenance=c.provenance,
            )
            for c in candidates
            if (c.entity_a_id, c.entity_b_id) in pair_ids
        ],
    )
    return written


async def _add_signal_child(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    signal: CandidateSignal,
    *,
    support: int,
    lift: float | None,
    min_gap_seconds: float | None = None,
) -> None:
    """Attach one per-signal child to an existing parent (for child-join head tests)."""
    _r = RelationshipCandidateRepository()
    await _r.upsert_signals(
        session,
        signals=[
            RelationshipCandidateSignalCreate(
                candidate_id=candidate_id,
                signal=signal,
                support=support,
                lift=lift,
                min_gap_seconds=min_gap_seconds,
                entity_a_video_count=10,
                entity_b_video_count=12,
                signal_universe=40000,
            )
        ],
    )


class TestPerChannelHeadMembership:
    """Feature 116 / T032 (cdwa-reviewed 2026-11-22) — per-signal head membership via the CHILD
    join. A dual-signal pair appears in BOTH heads; a transcript-only pair never appears in the
    title/description head; and the head is never silently SHORT (``total == HEAD_CUTOFF`` with no
    user filter). The slot-accounting assertion is what catches the active-filter bug: if the
    outer filter scoped on ``parent.channel`` instead of the child, the dual-signal pair would
    take a head slot then be filtered out, leaving ``total < HEAD_CUTOFF`` — a "pair appears in
    both heads" check would still pass, because presence survives that bug.
    """

    async def test_per_signal_heads_and_slot_accounting(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = RelationshipCandidateRepository()
        monkeypatch.setattr(repo_mod, "HEAD_CUTOFF", 2)
        await db_session.execute(delete(RelationshipCandidateDB))
        e = [await _make_entity(db_session, f"PH-{i}") for i in range(8)]

        # Two title/description-only pairs + one DUAL-signal pair (td child via _seed, then a
        # transcript child added). All three get a td child; `c` falls below the 2-row td head.
        a = _cand(e[0].id, e[1].id, lift=500.0)
        c = _cand(e[4].id, e[5].id, lift=80.0)
        dual = _cand(e[2].id, e[3].id, lift=300.0)
        await _seed(db_session, candidates=[a, c, dual])
        ids = await repo.ids_for_pairs(
            db_session, pairs=[(x.entity_a_id, x.entity_b_id) for x in (a, c, dual)]
        )
        await _add_signal_child(
            db_session,
            ids[(dual.entity_a_id, dual.entity_b_id)],
            CandidateSignal.TRANSCRIPT,
            support=70,
            lift=None,
            min_gap_seconds=2.0,
        )
        # A transcript-ONLY pair: a parent with a transcript child and NO td child.
        tlo, thi = _ordered(e[6].id, e[7].id)
        await repo.upsert_many(
            db_session,
            candidates=[
                RelationshipCandidateCreate(
                    entity_a_id=tlo,
                    entity_b_id=thi,
                    channel="transcript",
                    shared_video_count=90,
                    lift=None,
                    entity_a_video_count=10,
                    entity_b_video_count=12,
                    channel_video_universe=40000,
                )
            ],
        )
        tonly_id = (await repo.ids_for_pairs(db_session, pairs=[(tlo, thi)]))[
            (tlo, thi)
        ]
        await _add_signal_child(
            db_session,
            tonly_id,
            CandidateSignal.TRANSCRIPT,
            support=90,
            lift=None,
            min_gap_seconds=1.0,
        )

        # title/description head: pairs with a td child, ranked by child lift (500, 300, 80);
        # HEAD_CUTOFF=2 -> [a, dual]. Slot accounting: total == HEAD_CUTOFF, not short.
        td_rows, td_total, _ = await repo.list_ranked(db_session)
        assert td_total == 2
        td_ids = {r.id for r in td_rows}
        assert ids[(a.entity_a_id, a.entity_b_id)] in td_ids
        assert (
            ids[(dual.entity_a_id, dual.entity_b_id)] in td_ids
        )  # dual pair in td head
        assert tonly_id not in td_ids  # transcript-only pair absent from td head

        # transcript head: pairs with a transcript child, ranked by child support (90, 70);
        # HEAD_CUTOFF=2 -> [tonly, dual]. total == HEAD_CUTOFF proves the dual pair is NOT
        # filtered out by a stale parent.channel predicate (the cdwa bug).
        tr_rows, tr_total, _ = await repo.list_ranked(
            db_session, signal=CandidateSignal.TRANSCRIPT
        )
        assert tr_total == 2
        tr_ids = {r.id for r in tr_rows}
        assert tonly_id in tr_ids
        assert (
            ids[(dual.entity_a_id, dual.entity_b_id)] in tr_ids
        )  # dual pair in BOTH heads
        assert ids[(a.entity_a_id, a.entity_b_id)] not in tr_ids  # td-only absent here


class TestUpsert:
    async def test_inserts_then_refreshes_in_place(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "Placeholder A")
        e2 = await _make_entity(db_session, "Placeholder B")

        n = await _seed(db_session, candidates=[_cand(e1.id, e2.id)])
        assert n == 1
        rows, total, _ = await repo.list_ranked(db_session)
        assert total == 1
        original_id = rows[0].id
        assert rows[0].lift == 50.0

        # Re-emit the SAME pair with new metrics -> update in place, same id.
        await _seed(
            db_session,
            candidates=[_cand(e1.id, e2.id, lift=99.0, shared_video_count=9)],
        )
        rows, total, _ = await repo.list_ranked(db_session)
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
        await _seed(db_session, candidates=[_cand(e1.id, e2.id)])

        # Simulate a future verdict written directly (MVP has no verdict UI).
        await db_session.execute(
            update(RelationshipCandidateDB)
            .where(RelationshipCandidateDB.entity_a_id == min(e1.id, e2.id))
            .values(review_status="related", review_taxonomy_version="v1")
        )
        await db_session.flush()

        # A re-run must NOT overwrite the verdict (WHERE review_status IS NULL).
        await _seed(db_session, candidates=[_cand(e1.id, e2.id, lift=77.0)])
        rows, _, _ = await repo.list_ranked(db_session)
        assert rows[0].review_status == "related"
        assert rows[0].lift == 50.0  # metrics unchanged on a verdicted row


class TestListRanked:
    async def test_orders_by_lift_desc(self, db_session: AsyncSession) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "P1")
        e2 = await _make_entity(db_session, "P2")
        e3 = await _make_entity(db_session, "P3")
        await _seed(
            db_session,
            candidates=[
                _cand(e1.id, e2.id, lift=10.0),
                _cand(e1.id, e3.id, lift=500.0),
                _cand(e2.id, e3.id, lift=80.0),
            ],
        )
        rows, total, _ = await repo.list_ranked(db_session)
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
        await _seed(
            db_session,
            candidates=[
                _cand(e1.id, e2.id, both_typed_eligible=True, shared_video_count=5),
                _cand(e1.id, e3.id, both_typed_eligible=False, shared_video_count=20),
            ],
        )
        elig, elig_total, _ = await repo.list_ranked(db_session, eligible_only=True)
        assert elig_total == 1 and elig[0].both_typed_eligible is True

        tight, tight_total, _ = await repo.list_ranked(db_session, min_support=10)
        assert tight_total == 1 and tight[0].shared_video_count == 20

    async def test_review_filter_subsets_reviewed_unreviewed_all(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "RV1")
        e2 = await _make_entity(db_session, "RV2")
        e3 = await _make_entity(db_session, "RV3")
        await _seed(
            db_session,
            candidates=[
                _cand(e1.id, e2.id, lift=100.0),
                _cand(e1.id, e3.id, lift=50.0),
            ],
        )
        all_rows, all_total, _ = await repo.list_ranked(db_session)
        assert all_total == 2
        # Mark the top-ranked row reviewed (no repo writer exists; set it directly).
        all_rows[0].review_status = "associated_with"
        await db_session.flush()

        rev, rev_total, _ = await repo.list_ranked(db_session, review="reviewed")
        assert rev_total == 1 and rev[0].review_status == "associated_with"
        unrev, unrev_total, _ = await repo.list_ranked(db_session, review="unreviewed")
        assert unrev_total == 1 and unrev[0].review_status is None
        _, all2_total, _ = await repo.list_ranked(db_session, review="all")
        assert all2_total == 2

    async def test_sort_by_reorders_display_without_changing_membership(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "SV1")
        e2 = await _make_entity(db_session, "SV2")
        e3 = await _make_entity(db_session, "SV3")
        await _seed(
            db_session,
            candidates=[
                _cand(e1.id, e2.id, lift=100.0, shared_video_count=5),
                _cand(e1.id, e3.id, lift=50.0, shared_video_count=40),
            ],
        )
        # Default ("rank") = lift desc, so the lift=100 row is first.
        ranked, total, _ = await repo.list_ranked(db_session)
        assert total == 2 and ranked[0].lift == 100.0
        # Sort by shared_video_count asc flips the DISPLAY order (5 before 40); the same two
        # rows are present (membership is still lift-defined, unchanged).
        asc, asc_total, _ = await repo.list_ranked(
            db_session, sort_by="shared_video_count", sort_dir="asc"
        )
        assert asc_total == 2
        assert [r.shared_video_count for r in asc] == [5, 40]

    async def test_review_and_sort_never_promote_a_below_head_row(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # §23: filters/sort subset WITHIN the lift-defined head and must never surface a below-head
        # row. Shrink the head to 2 so the lowest-lift pair is outside it, cheaply.
        from chronovista.repositories import relationship_candidate_repository as mod

        monkeypatch.setattr(mod, "HEAD_CUTOFF", 2)
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "HS1")
        e2 = await _make_entity(db_session, "HS2")
        e3 = await _make_entity(db_session, "HS3")
        e4 = await _make_entity(db_session, "HS4")
        await _seed(
            db_session,
            candidates=[
                _cand(e1.id, e2.id, lift=300.0),
                _cand(e1.id, e3.id, lift=200.0),
                _cand(e1.id, e4.id, lift=10.0),  # rank 3 -> outside the 2-row head
            ],
        )
        # Review the below-head row (read the full set via head_only=False to reach it).
        all_rows, _, _ = await repo.list_ranked(db_session, head_only=False)
        low = next(r for r in all_rows if r.lift == 10.0)
        low.review_status = "associated_with"
        await db_session.flush()

        # review=reviewed must NOT surface it — it is outside the head.
        rev, rev_total, _ = await repo.list_ranked(db_session, review="reviewed")
        assert rev_total == 0 and rev == []
        # Sorting by reviewed_at must not pull it in either (sort reorders the head only).
        srt, _, _ = await repo.list_ranked(
            db_session, sort_by="reviewed_at", sort_dir="desc"
        )
        assert all(r.lift != 10.0 for r in srt)

    async def test_verdict_category_filter(self, db_session: AsyncSession) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "VC1")
        e2 = await _make_entity(db_session, "VC2")
        e3 = await _make_entity(db_session, "VC3")
        await _seed(
            db_session,
            candidates=[
                _cand(e1.id, e2.id, lift=100.0),
                _cand(e1.id, e3.id, lift=50.0),
            ],
        )
        rows, _, _ = await repo.list_ranked(db_session)
        rows[0].review_status = "covers"
        rows[1].review_status = "coincidence"
        await db_session.flush()

        covers, covers_total, _ = await repo.list_ranked(
            db_session, verdicts=("covers",)
        )
        assert covers_total == 1 and covers[0].review_status == "covers"
        # Multiple categories OR within the verdict dimension.
        both, both_total, _ = await repo.list_ranked(
            db_session, verdicts=("covers", "coincidence")
        )
        assert both_total == 2
        # Empty = no category filter.
        _, none_total, _ = await repo.list_ranked(db_session, verdicts=())
        assert none_total == 2


class TestDeleteStale:
    async def test_removes_unemitted_unverdicted_keeps_others(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "R1")
        e2 = await _make_entity(db_session, "R2")
        e3 = await _make_entity(db_session, "R3")
        # Two pairs written "last run".
        await _seed(
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
        await _seed(db_session, candidates=[_cand(e1.id, e2.id, lift=70.0)])
        removed = await repo.delete_stale(db_session, run_started_at=run_started)

        assert removed == 0  # the stale pair was verdicted -> kept
        rows, total, _ = await repo.list_ranked(db_session)
        assert total == 2  # re-emitted (unverdicted) + verdicted both present

    async def test_removes_a_stale_unverdicted_pair(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "S1")
        e2 = await _make_entity(db_session, "S2")
        await _seed(db_session, candidates=[_cand(e1.id, e2.id)])
        # A later run that re-emits nothing -> the pair is stale and unverdicted.
        later = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=1)
        removed = await repo.delete_stale(db_session, run_started_at=later)
        assert removed == 1
        _, total, _ = await repo.list_ranked(db_session)
        assert total == 0


class TestUpsertRobustness:
    async def test_empty_upsert_returns_zero(self, db_session: AsyncSession) -> None:
        assert await _seed(db_session, candidates=[]) == 0

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
        n = await _seed(
            db_session,
            candidates=[
                _cand(e1.id, e2.id),
                _cand(e1.id, e3.id),
                _cand(e2.id, e3.id),
            ],
        )
        assert n == 3
        _, total, _ = await repo.list_ranked(db_session)
        assert total == 3

    async def test_dedupes_repeated_pair_in_one_call(
        self, db_session: AsyncSession
    ) -> None:
        # Two create models for the same canonical pair in one call must not raise
        # "ON CONFLICT ... cannot affect row a second time"; last wins.
        repo = RelationshipCandidateRepository()
        e1 = await _make_entity(db_session, "Dup 1")
        e2 = await _make_entity(db_session, "Dup 2")
        n = await _seed(
            db_session,
            candidates=[_cand(e1.id, e2.id, lift=10.0), _cand(e1.id, e2.id, lift=88.0)],
        )
        assert n == 1
        rows, total, _ = await repo.list_ranked(db_session)
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
        await _seed(
            db_session,
            candidates=[_cand(e1.id, e2.id, shared_video_count=5, lift=350.0)],
        )
        rows, total, _ = await repo.list_ranked(db_session)
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


class TestHeadScope:
    """Feature 108: head cutoff (hard cap), head_only override, ordering, provenance counts."""

    async def test_hard_cap_scopes_head_and_reports_both_totals(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Small cutoff so the cap is testable without seeding 500+ rows.
        monkeypatch.setattr(repo_mod, "HEAD_CUTOFF", 3)
        repo = RelationshipCandidateRepository()
        hub = await _make_entity(db_session, "Hub")
        cands = [
            _cand(
                hub.id,
                (await _make_entity(db_session, f"Partner {i}")).id,
                lift=float(100 - i),  # distinct lifts -> deterministic rank
            )
            for i in range(5)
        ]
        await _seed(db_session, candidates=cands)

        # A large limit cannot bypass the cap (FR-004): the cap is enforced in the repo.
        rows, total, total_before = await repo.list_ranked(db_session, limit=100)
        assert len(rows) == 3
        assert total == 3  # scoped = min(5, HEAD_CUTOFF=3)
        assert total_before == 5  # provenance: full qualifying count (FR-006)

        # A page starting at/after the cutoff is empty (cannot page into the tail).
        empty, _, _ = await repo.list_ranked(db_session, skip=3, limit=100)
        assert empty == []

    async def test_head_only_false_returns_full_tail(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(repo_mod, "HEAD_CUTOFF", 3)
        repo = RelationshipCandidateRepository()
        hub = await _make_entity(db_session, "Hub2")
        cands = [
            _cand(
                hub.id,
                (await _make_entity(db_session, f"Tail {i}")).id,
                lift=float(100 - i),
            )
            for i in range(5)
        ]
        await _seed(db_session, candidates=cands)

        # The deliberate override reaches the retained tail (FR-003); the API never does.
        rows, total, total_before = await repo.list_ranked(
            db_session, limit=100, head_only=False
        )
        assert len(rows) == 5
        assert total == 5 and total_before == 5

    async def test_equal_lift_higher_corroboration_first(
        self, db_session: AsyncSession
    ) -> None:
        # FR-002 / SC-003: corroboration is the secondary sort key. The higher-corroboration
        # row is given the LOWER shared_video_count, so without the corroboration key the order
        # would INVERT (shared_video is the next key) — this fails if corroboration is dropped.
        repo = RelationshipCandidateRepository()
        hub = await _make_entity(db_session, "CorrHub")
        p_low = await _make_entity(db_session, "CorrLow")
        p_high = await _make_entity(db_session, "CorrHigh")
        await _seed(
            db_session,
            candidates=[
                _cand(
                    hub.id,
                    p_low.id,
                    lift=50.0,
                    kb_corroboration_count=0,
                    shared_video_count=9,
                ),
                _cand(
                    hub.id,
                    p_high.id,
                    lift=50.0,
                    kb_corroboration_count=5,
                    shared_video_count=5,
                ),
            ],
        )
        rows, _, _ = await repo.list_ranked(db_session)
        assert rows[0].kb_corroboration_count == 5  # higher corroboration first...
        assert (
            rows[0].shared_video_count == 5
        )  # ...despite its LOWER shared_video_count

    async def test_list_ranked_sql_ends_order_by_with_id(
        self, db_session: AsyncSession
    ) -> None:
        # EFFECT guard (§22/§23): capture the SQL list_ranked ACTUALLY emits and assert its
        # ORDER BY ENDS with the regen-stable id key. The structural guard on _HEAD_ORDER_BY
        # passes even if list_ranked stops using the tuple (inlined order_by) — this does not:
        # it asserts the emitted statement, not a constant's contents.
        from sqlalchemy import event

        repo = RelationshipCandidateRepository()
        hub = await _make_entity(db_session, "SqlHub")
        partner = await _make_entity(db_session, "SqlPartner")
        await _seed(db_session, candidates=[_cand(hub.id, partner.id)])

        captured: list[str] = []
        sync_conn = (await db_session.connection()).sync_connection

        def _cap(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
            if (
                "relationship_candidates" in statement
                and " order by " in statement.lower()
            ):
                captured.append(statement)

        event.listen(sync_conn, "before_cursor_execute", _cap)
        try:
            await repo.list_ranked(db_session)
        finally:
            event.remove(sync_conn, "before_cursor_execute", _cap)

        assert captured, "list_ranked emitted no SELECT with an ORDER BY"
        # The head query has TWO order-by clauses (the head-membership subquery and the outer
        # row order); EVERY one must end in the id key, or either boundary can flicker.
        import re

        sql = captured[-1].lower()
        clauses = sql.split(" order by ")[1:]
        assert clauses, "no ORDER BY in emitted SQL"
        for clause in clauses:
            keys = re.split(r"\s+(?:limit|offset)\b|\)", clause, maxsplit=1)[0]
            last_key = keys.rsplit(",", 1)[-1].strip()
            assert "relationship_candidates.id" in last_key, (clause, last_key)

    async def test_filters_subset_within_head_never_promote_tail(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # §23 regression guard: head membership is the GLOBAL top-HEAD_CUTOFF of the floor,
        # independent of user filters. A high-support row BELOW the head must NOT be promoted
        # into view by a narrow min_support (the old filter-then-cap behaviour would return it).
        monkeypatch.setattr(repo_mod, "HEAD_CUTOFF", 3)
        repo = RelationshipCandidateRepository()
        hub = await _make_entity(db_session, "PromHub")
        # 3 head rows (highest lift) but LOW support (5) -> fail min_support=10.
        head = [
            _cand(
                hub.id,
                (await _make_entity(db_session, f"Head {i}")).id,
                lift=float(1000 - i),
                shared_video_count=5,
            )
            for i in range(3)
        ]
        # 2 below-head rows (low lift) with HIGH support (20) -> would be promoted under the
        # old behaviour; under §23 they are outside the top-3 head and must stay hidden.
        tail = [
            _cand(
                hub.id,
                (await _make_entity(db_session, f"Tail {i}")).id,
                lift=float(10 - i),
                shared_video_count=20,
            )
            for i in range(2)
        ]
        await _seed(db_session, candidates=head + tail)

        rows, total, total_before = await repo.list_ranked(db_session, min_support=10)
        # Head = top-3 (the support-5 rows); none survive support>=10 WITHIN the head.
        assert rows == [] and total == 0
        # Provenance is about the filtered population: 2 rows match support>=10 queue-wide.
        assert total_before == 2
        # And head_only=False (measurement path) DOES see those 2 (ranked, uncapped).
        tail_rows, _, _ = await repo.list_ranked(
            db_session, min_support=10, head_only=False
        )
        assert len(tail_rows) == 2


def _signal_create(
    candidate_id: uuid.UUID, signal: CandidateSignal, **over: object
) -> RelationshipCandidateSignalCreate:
    td = signal is CandidateSignal.TITLE_DESCRIPTION
    base: dict[str, object] = {
        "candidate_id": candidate_id,
        "signal": signal,
        "support": 7 if td else 12,
        "lift": 50.0 if td else None,
        "min_gap_seconds": None if td else 3.0,
        "entity_a_video_count": 10,
        "entity_b_video_count": 12,
        "signal_universe": 40000,
        "both_typed_eligible": True,
    }
    base.update(over)
    return RelationshipCandidateSignalCreate(**base)  # type: ignore[arg-type]


class TestUpsertSignals:
    """Feature 116 / T026 foundation: the per-signal evidence child write path."""

    async def test_inserts_both_signals_then_refreshes_in_place(
        self, db_session: AsyncSession
    ) -> None:
        repo = RelationshipCandidateRepository()
        # Clear first: shared integration DB; the FK ON DELETE CASCADE drops children too.
        await db_session.execute(delete(RelationshipCandidateDB))
        e1 = await _make_entity(db_session, "Sig A")
        e2 = await _make_entity(db_session, "Sig B")
        await _seed(db_session, candidates=[_cand(e1.id, e2.id)])
        rows, _, _ = await repo.list_ranked(db_session)
        parent_id = rows[0].id

        # Dual-signal: ONE pair carries a title_description child AND a transcript child.
        n = await repo.upsert_signals(
            db_session,
            signals=[
                _signal_create(parent_id, CandidateSignal.TITLE_DESCRIPTION),
                _signal_create(parent_id, CandidateSignal.TRANSCRIPT),
            ],
        )
        assert n == 2

        children = (
            (
                await db_session.execute(
                    select(RelationshipCandidateSignalDB)
                    .where(RelationshipCandidateSignalDB.candidate_id == parent_id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        by_signal = {c.signal: c for c in children}
        # str-Enum bound as its string value in the INSERT.
        assert set(by_signal) == {"title_description", "transcript"}
        assert by_signal["title_description"].lift == 50.0
        assert by_signal["transcript"].lift is None
        assert by_signal["transcript"].min_gap_seconds == 3.0

        # Re-emit ONLY the transcript child with new support -> refresh in place, no duplicate,
        # and the title_description child is untouched (no verdict guard needed on the child).
        n2 = await repo.upsert_signals(
            db_session,
            signals=[_signal_create(parent_id, CandidateSignal.TRANSCRIPT, support=99)],
        )
        assert n2 == 1
        children2 = (
            (
                await db_session.execute(
                    select(RelationshipCandidateSignalDB)
                    .where(RelationshipCandidateSignalDB.candidate_id == parent_id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        assert len(children2) == 2  # still two rows, not three
        by_signal2 = {c.signal: c for c in children2}
        assert by_signal2["transcript"].support == 99  # refreshed
        assert by_signal2["title_description"].support == 7  # untouched
