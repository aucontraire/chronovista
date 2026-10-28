"""Downstream-integrity integration tests (Feature 096, T035, Cross-Feature contract).

After a candidate is approved into an entity, a later mutation of that entity by
another feature must not corrupt the candidate record:
- **hard delete** → the FK ``created_entity_id`` is nulled (ON DELETE SET NULL),
  the candidate stays ``approved``;
- **merge/deprecate** → the entity row persists, so ``created_entity_id`` stays set,
  and the candidate stays ``approved`` (never reverts to pending).
Real DB.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services.candidate_suggestion_service import CandidateSuggestionService

pytestmark = pytest.mark.asyncio


async def _approve_one(
    db_session: AsyncSession,
    service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
    *,
    seed_qid: str,
    target_qid: str,
    label: str,
    video_id: str,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed → generate → approve. Returns (candidate_id, created_entity_id)."""
    db_session.add(
        make_seed_entity(
            name=f"Seed {seed_qid}",
            qid=seed_qid,
            relation="spouse",
            target_qid=target_qid,
            target_label=label,
        )
    )
    db_session.add(
        make_video(video_id=video_id, title=f"{label} appears", description=None)
    )
    await db_session.flush()
    await service.generate(db_session)
    cand = await service._candidates.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid=target_qid
    )
    assert cand is not None
    candidate_id = cand.id
    result = await service.approve(
        db_session, candidate_id=candidate_id, reviewed_by="tester"
    )
    assert result.outcome == "approved"
    assert result.created_entity_id is not None
    return candidate_id, result.created_entity_id


async def test_hard_delete_nulls_reference_candidate_stays_approved(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    candidate_id, entity_id = await _approve_one(
        db_session,
        candidate_service,
        make_seed_entity,
        make_video,
        seed_qid="Q7010",
        target_qid="Q7110",
        label="DeleteMe Target",
        video_id="vid00007010",
    )

    entity = await NamedEntityRepository().get(db_session, entity_id)
    assert entity is not None
    await db_session.delete(entity)
    await db_session.commit()

    cand = await candidate_service._candidates.get(db_session, candidate_id)
    assert cand is not None
    assert cand.review_status == "approved"  # not reverted to pending
    assert cand.created_entity_id is None  # FK ON DELETE SET NULL fired


async def test_merge_keeps_reference_candidate_stays_approved(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    candidate_id, entity_id = await _approve_one(
        db_session,
        candidate_service,
        make_seed_entity,
        make_video,
        seed_qid="Q7020",
        target_qid="Q7120",
        label="MergeMe Target",
        video_id="vid00007020",
    )

    # A merge survivor, then merge the created entity into it (row persists).
    survivor = NamedEntityDB(
        id=uuid.uuid4(),
        canonical_name="Merge Survivor",
        canonical_name_normalized="merge survivor",
        entity_type="person",
        external_ids={},
    )
    db_session.add(survivor)
    await db_session.flush()
    entity = await NamedEntityRepository().get(db_session, entity_id)
    assert entity is not None
    entity.status = "merged"
    entity.merged_into_id = survivor.id
    db_session.add(entity)
    await db_session.commit()

    cand = await candidate_service._candidates.get(db_session, candidate_id)
    assert cand is not None
    assert cand.review_status == "approved"  # never reverts
    assert cand.created_entity_id == entity_id  # row persists → reference stays set
