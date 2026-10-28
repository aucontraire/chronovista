"""Real-DB tests for ``CandidateSuggestionRepository`` (Feature 096).

Exercises the state machine that only a real Postgres run can verify: idempotent
upsert (refresh pending, leave terminal untouched — FR-014), verdict transitions,
supersede reconciliation (FR-011b), status/triage counts (FR-016), and the ranked
pending read with filters (FR-007). Uses the ``db_session`` fixture (create_all +
drop_all per test). Name-free placeholders only (Constitution VI).
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.candidate_suggestion import CandidateSuggestionCreate
from chronovista.models.enums import (
    EntityType,
    ReviewStatus,
    SourceChannel,
    TriageCategory,
)
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)

pytestmark = pytest.mark.asyncio


def _candidate(qid: str, **over: object) -> CandidateSuggestionCreate:
    base: dict[str, object] = {
        "source_channel": SourceChannel.RELATION,
        "wikidata_qid": qid,
        "label": "Placeholder Label",
        "label_normalized": "placeholder label",
        "type_hint": EntityType.ORGANIZATION,
        "token_count": 2,
        "corroboration_count": 1,
        "dangling_edge_count": 1,
        "salience": 0,
        "score": 1.0,
        "triage": TriageCategory.WORTH_REVIEW,
        "provenance": {
            "seed_entity_ids": [str(uuid.uuid4())],
            "relations": ["member_of"],
        },
    }
    base.update(over)
    return CandidateSuggestionCreate(**base)  # type: ignore[arg-type]


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


class TestUpsertGenerated:
    async def test_inserts_then_refreshes_pending(
        self, db_session: AsyncSession
    ) -> None:
        repo = CandidateSuggestionRepository()
        first = await repo.upsert_generated(db_session, candidate=_candidate("Q101"))
        assert first.review_status == ReviewStatus.PENDING.value
        assert first.score == 1.0
        original_generated_at = first.last_generated_at

        refreshed = await repo.upsert_generated(
            db_session,
            candidate=_candidate("Q101", score=9.0, salience=5, corroboration_count=3),
        )
        assert refreshed.id == first.id  # same row, not a duplicate
        assert refreshed.score == 9.0
        assert refreshed.salience == 5
        assert refreshed.corroboration_count == 3
        assert refreshed.last_generated_at >= original_generated_at

    async def test_leaves_terminal_rows_untouched(
        self, db_session: AsyncSession
    ) -> None:
        repo = CandidateSuggestionRepository()
        entity = await _make_entity(db_session, "Terminal Target 201")
        row = await repo.upsert_generated(db_session, candidate=_candidate("Q201"))
        await repo.set_verdict(
            db_session,
            candidate_id=row.id,
            review_status=ReviewStatus.APPROVED,
            reviewed_by="operator",
            reviewed_at=datetime.datetime.now(datetime.UTC),
            created_entity_id=entity.id,
        )

        # A re-run must NOT overwrite the human verdict (FR-014).
        after = await repo.upsert_generated(
            db_session, candidate=_candidate("Q201", score=99.0)
        )
        assert after.review_status == ReviewStatus.APPROVED.value
        assert after.score == 1.0  # unchanged
        assert after.created_entity_id == entity.id


class TestVerdict:
    async def test_approve_sets_entity_and_reject_clears(
        self, db_session: AsyncSession
    ) -> None:
        repo = CandidateSuggestionRepository()
        entity = await _make_entity(db_session, "Approved Target 301")
        approved_row = await repo.upsert_generated(
            db_session, candidate=_candidate("Q301")
        )
        approved = await repo.set_verdict(
            db_session,
            candidate_id=approved_row.id,
            review_status=ReviewStatus.APPROVED,
            reviewed_by="operator",
            reviewed_at=datetime.datetime.now(datetime.UTC),
            created_entity_id=entity.id,
        )
        assert approved is not None
        assert approved.review_status == ReviewStatus.APPROVED.value
        assert approved.created_entity_id == entity.id

        rejected_row = await repo.upsert_generated(
            db_session, candidate=_candidate("Q302")
        )
        rejected = await repo.set_verdict(
            db_session,
            candidate_id=rejected_row.id,
            review_status=ReviewStatus.REJECTED,
            reviewed_by="operator",
            reviewed_at=datetime.datetime.now(datetime.UTC),
        )
        assert rejected is not None
        assert rejected.review_status == ReviewStatus.REJECTED.value
        assert rejected.created_entity_id is None

    async def test_verdict_on_terminal_row_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        """A second verdict on an already-terminal candidate is refused (H1 guard)."""
        repo = CandidateSuggestionRepository()
        row = await repo.upsert_generated(db_session, candidate=_candidate("Q310"))
        first = await repo.set_verdict(
            db_session,
            candidate_id=row.id,
            review_status=ReviewStatus.REJECTED,
            reviewed_by="operator",
            reviewed_at=datetime.datetime.now(datetime.UTC),
        )
        assert first is not None and first.review_status == ReviewStatus.REJECTED.value

        # A stale re-approval must NOT flip the rejected row.
        second = await repo.set_verdict(
            db_session,
            candidate_id=row.id,
            review_status=ReviewStatus.APPROVED,
            reviewed_by="operator",
            reviewed_at=datetime.datetime.now(datetime.UTC),
        )
        assert second is None  # compare-and-set refused the transition
        still = await repo.get(db_session, row.id)
        assert still is not None
        assert still.review_status == ReviewStatus.REJECTED.value


class TestSupersede:
    async def test_supersedes_only_matching_pending(
        self, db_session: AsyncSession
    ) -> None:
        repo = CandidateSuggestionRepository()
        await repo.upsert_generated(db_session, candidate=_candidate("Q401"))
        await repo.upsert_generated(db_session, candidate=_candidate("Q402"))

        count = await repo.supersede_grounded(
            db_session, source_channel="relation", grounded_qids={"Q401"}
        )
        assert count == 1
        q401 = await repo.get_by_channel_qid(
            db_session, source_channel="relation", wikidata_qid="Q401"
        )
        q402 = await repo.get_by_channel_qid(
            db_session, source_channel="relation", wikidata_qid="Q402"
        )
        assert q401 is not None and q401.review_status == ReviewStatus.SUPERSEDED.value
        assert q402 is not None and q402.review_status == ReviewStatus.PENDING.value

    async def test_empty_set_is_noop(self, db_session: AsyncSession) -> None:
        repo = CandidateSuggestionRepository()
        assert (
            await repo.supersede_grounded(
                db_session, source_channel="relation", grounded_qids=set()
            )
            == 0
        )


class TestCountsByStatus:
    async def test_counts_status_and_pending_triage(
        self, db_session: AsyncSession
    ) -> None:
        repo = CandidateSuggestionRepository()
        await repo.upsert_generated(
            db_session, candidate=_candidate("Q501", triage=TriageCategory.WORTH_REVIEW)
        )
        await repo.upsert_generated(
            db_session,
            candidate=_candidate("Q502", triage=TriageCategory.GROUNDS_NOWHERE),
        )
        rejected = await repo.upsert_generated(db_session, candidate=_candidate("Q503"))
        await repo.set_verdict(
            db_session,
            candidate_id=rejected.id,
            review_status=ReviewStatus.REJECTED,
            reviewed_by="operator",
            reviewed_at=datetime.datetime.now(datetime.UTC),
        )

        counts = await repo.counts_by_status(db_session, source_channel="relation")
        assert counts["pending"] == 2
        assert counts["rejected"] == 1
        assert counts["approved"] == 0
        assert counts["superseded"] == 0
        # pending triage distribution
        assert counts["worth_review"] == 1
        assert counts["grounds_nowhere"] == 1


class TestListPending:
    async def test_orders_by_score_and_filters(self, db_session: AsyncSession) -> None:
        repo = CandidateSuggestionRepository()
        dup_entity = await _make_entity(db_session, "Collide 601")
        await repo.upsert_generated(db_session, candidate=_candidate("Q601", score=3.0))
        await repo.upsert_generated(db_session, candidate=_candidate("Q602", score=9.0))
        await repo.upsert_generated(
            db_session,
            candidate=_candidate(
                "Q603",
                score=1.0,
                token_count=1,
                triage=TriageCategory.LIKELY_ELIMINABLE,
                label="Solo",
                label_normalized="solo",
                possible_duplicate_of_id=dup_entity.id,
            ),
        )

        rows, total = await repo.list_pending(db_session)
        assert total == 3
        assert [r.wikidata_qid for r in rows] == ["Q602", "Q601", "Q603"]  # score desc

        # min_token_count filter excludes the single-token candidate
        multi, multi_total = await repo.list_pending(db_session, min_token_count=2)
        assert multi_total == 2
        assert {r.wikidata_qid for r in multi} == {"Q601", "Q602"}

        # triage filter
        elim, elim_total = await repo.list_pending(
            db_session, triage=TriageCategory.LIKELY_ELIMINABLE.value
        )
        assert elim_total == 1 and elim[0].wikidata_qid == "Q603"

        # possible-duplicate filter
        dups, dups_total = await repo.list_pending(db_session, possible_duplicate=True)
        assert dups_total == 1 and dups[0].wikidata_qid == "Q603"
