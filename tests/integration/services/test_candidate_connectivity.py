"""Connectivity-increase integration test (Feature 096, T033, SC-005).

Approving a candidate must resolve the dangling relationship edges that pointed at
it: the approved QID transitions from not-grounded to grounded, so the seed's edge
now resolves to a library entity. Real DB.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services.candidate_suggestion_service import CandidateSuggestionService

pytestmark = pytest.mark.asyncio


async def test_approval_resolves_dangling_edges(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    db_session.add(
        make_seed_entity(
            name="Seed Edge",
            qid="Q5010",
            relation="spouse",
            target_qid="Q6010",
            target_label="Edge Target",
        )
    )
    db_session.add(
        make_video(
            video_id="vid00000010", title="Edge Target in the news", description=None
        )
    )
    await db_session.flush()

    entity_repo = NamedEntityRepository()

    await candidate_service.generate(db_session)
    cand = await candidate_service._candidates.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6010"
    )
    assert cand is not None
    # One seed points at it → exactly one dangling edge to resolve.
    assert cand.dangling_edge_count == 1

    # SC-005, measured directly: count the seed's inbound edge targets that resolve
    # to a library entity, before vs after approval.
    resolved_before = len(await entity_repo.get_by_wikidata_qids(db_session, ["Q6010"]))
    assert resolved_before == 0  # the edge is dangling before approval

    result = await candidate_service.approve(
        db_session, candidate_id=cand.id, reviewed_by="tester"
    )
    assert result.outcome == "approved"

    resolved_after = len(await entity_repo.get_by_wikidata_qids(db_session, ["Q6010"]))
    # The resolved-edge count increased by exactly the candidate's dangling_edge_count.
    assert resolved_after - resolved_before == cand.dangling_edge_count

    # Re-generation no longer emits Q6010 (it is now a library entity, FR-011).
    await candidate_service.generate(db_session)
    rows = await candidate_service._candidates.emit_relation_candidates(
        db_session, relation_fields=["spouse"]
    )
    assert all(r.wikidata_qid != "Q6010" for r in rows)
