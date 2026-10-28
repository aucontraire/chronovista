"""Durable, resumable re-generation integration tests (Feature 096, T026, US3).

A second generation run must: preserve verdicts (SC-007), never re-offer a rejected
candidate (FR-010), refresh pending signals (FR-014), retire a pending candidate
whose QID became grounded (FR-011b, superseded), and produce a clean empty queue
when there are no grounded seeds (FR-018). Real DB.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.services.candidate_suggestion_service import CandidateSuggestionService

pytestmark = pytest.mark.asyncio


async def test_rerun_preserves_verdicts_and_refreshes_pending(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    db_session.add_all(
        [
            make_seed_entity(
                name="Seed Keep",
                qid="Q4001",
                relation="spouse",
                target_qid="Q4101",
                target_label="Keep Target",
            ),
            make_seed_entity(
                name="Seed Reject",
                qid="Q4002",
                relation="spouse",
                target_qid="Q4102",
                target_label="Reject Target",
            ),
        ]
    )
    db_session.add(
        make_video(video_id="vid00004001", title="Keep Target news", description=None)
    )
    await db_session.flush()

    await candidate_service.generate(db_session)
    repo = candidate_service._candidates
    keep = await repo.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q4101"
    )
    reject = await repo.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q4102"
    )
    assert keep is not None and reject is not None
    reject_id = reject.id

    # Reject one; it must never be re-offered (FR-010).
    await candidate_service.reject(
        db_session, candidate_id=reject_id, reviewed_by="tester"
    )

    # Add corpus presence for the kept target, then re-generate.
    db_session.add(
        make_video(
            video_id="vid00004002", title="more about Keep Target", description=None
        )
    )
    await db_session.flush()
    await candidate_service.generate(db_session)

    # Verdict preserved (SC-007): the rejected candidate is still rejected, not pending.
    reject_after = await repo.get(db_session, reject_id)
    assert reject_after is not None and reject_after.review_status == "rejected"

    # Pending signal refreshed (FR-014): the kept candidate's salience grew (2 videos now).
    keep_after = await repo.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q4101"
    )
    assert keep_after is not None
    assert keep_after.review_status == "pending"
    assert keep_after.salience >= 2

    # The rejected target is not re-offered as pending.
    pending_rows, _ = await repo.list_pending(db_session, source_channel="relation")
    assert all(r.wikidata_qid != "Q4102" for r in pending_rows)


async def test_rerun_supersedes_pending_now_grounded(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    db_session.add(
        make_seed_entity(
            name="Seed Super",
            qid="Q4003",
            relation="spouse",
            target_qid="Q4103",
            target_label="Super Target",
        )
    )
    db_session.add(
        make_video(video_id="vid00004003", title="Super Target shown", description=None)
    )
    await db_session.flush()
    await candidate_service.generate(db_session)

    # The target becomes a library entity by other means.
    db_session.add(
        NamedEntityDB(
            id=uuid.uuid4(),
            canonical_name="Super Target Existing",
            canonical_name_normalized="super target existing",
            entity_type="person",
            external_ids={"wikidata": {"id": "Q4103"}},
        )
    )
    await db_session.flush()

    # Re-generation reconciles it: the pending candidate is superseded (FR-011b).
    await candidate_service.generate(db_session)
    cand = await candidate_service._candidates.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q4103"
    )
    assert cand is not None and cand.review_status == "superseded"


async def test_generate_with_no_seeds_is_clean_empty(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_video: Callable[..., VideoDB],
) -> None:
    # No grounded seed entities at all (just corpus) → empty queue with a reason (FR-018).
    db_session.add(
        make_video(video_id="vid00004004", title="some video", description=None)
    )
    await db_session.flush()

    summary = await candidate_service.generate(db_session)
    assert summary.seeds_grounded == 0
    assert summary.candidates_discovered == 0
    assert summary.pending_total == 0
    assert summary.empty_reason is not None
    assert "ground" in summary.empty_reason.lower()
