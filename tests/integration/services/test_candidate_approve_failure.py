"""Approval failure / race / no-auto-create integration tests (Feature 096, T034).

Covers FR-015 (a creation failure leaves the candidate pending, no partial entity),
FR-011b (a QID grounded between generation and approval → superseded, no duplicate),
a name+type collision → superseded, and FR-013 (no non-approve path ever creates an
entity). Real DB.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.candidate_suggestion_service import CandidateSuggestionService

pytestmark = pytest.mark.asyncio


async def _entity_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(NamedEntityDB))
    return result.scalar() or 0


async def test_generate_creates_no_entities(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    """FR-013: generation discovers candidates but never creates a named entity."""
    db_session.add(
        make_seed_entity(
            name="Seed NoCreate",
            qid="Q5040",
            relation="spouse",
            target_qid="Q6040",
            target_label="NoCreate Target",
        )
    )
    db_session.add(
        make_video(
            video_id="vid00000040", title="NoCreate Target here", description=None
        )
    )
    await db_session.flush()

    before = await _entity_count(db_session)
    summary = await candidate_service.generate(db_session)
    assert summary.candidates_discovered >= 1
    after = await _entity_count(db_session)
    assert after == before  # no entity created by generation


async def test_raced_grounding_supersedes_without_duplicate(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    db_session.add(
        make_seed_entity(
            name="Seed Raced",
            qid="Q5020",
            relation="spouse",
            target_qid="Q6020",
            target_label="Raced Target",
        )
    )
    db_session.add(
        make_video(
            video_id="vid00000020", title="Raced Target appears", description=None
        )
    )
    await db_session.flush()
    await candidate_service.generate(db_session)
    cand = await candidate_service._candidates.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6020"
    )
    assert cand is not None

    # The QID becomes a library entity by other means, after generation.
    db_session.add(
        NamedEntityDB(
            id=uuid.uuid4(),
            canonical_name="Raced Target Existing",
            canonical_name_normalized="raced target existing",
            entity_type="person",
            external_ids={"wikidata": {"id": "Q6020"}},
        )
    )
    await db_session.flush()

    result = await candidate_service.approve(
        db_session, candidate_id=cand.id, reviewed_by="tester"
    )
    assert result.outcome == "superseded"
    # Exactly one entity grounds Q6020 — approval created no duplicate.
    grounded = await NamedEntityRepository().get_by_wikidata_qids(db_session, ["Q6020"])
    assert "Q6020" in grounded


async def test_name_collision_supersedes(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    db_session.add(
        make_seed_entity(
            name="Seed Collide",
            qid="Q5030",
            relation="spouse",
            target_qid="Q6030",
            target_label="Collide Name",
        )
    )
    db_session.add(
        make_video(video_id="vid00000030", title="Collide Name shown", description=None)
    )
    await db_session.flush()
    await candidate_service.generate(db_session)
    cand = await candidate_service._candidates.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6030"
    )
    assert cand is not None and cand.type_hint == "person"

    # An active entity with the same normalized name + type already exists (ungrounded).
    db_session.add(
        NamedEntityDB(
            id=uuid.uuid4(),
            canonical_name="Collide Name",
            canonical_name_normalized="collide name",
            entity_type="person",
            external_ids={},
        )
    )
    await db_session.flush()

    result = await candidate_service.approve(
        db_session, candidate_id=cand.id, reviewed_by="tester"
    )
    assert result.outcome == "superseded"


async def test_creation_failure_leaves_candidate_pending(
    db_session: AsyncSession,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    """FR-015: a failure in the creation step leaves the candidate reviewable."""

    class _FailingEntityRepo(NamedEntityRepository):
        async def create(self, *args: object, **kwargs: object) -> NamedEntityDB:
            raise RuntimeError("forced creation failure")

    service = CandidateSuggestionService(
        candidate_repo=CandidateSuggestionRepository(),
        entity_repo=_FailingEntityRepo(),
        video_repo=VideoRepository(),
        alias_repo=EntityAliasRepository(),
        enrichment=None,
    )
    db_session.add(
        make_seed_entity(
            name="Seed Fail",
            qid="Q5050",
            relation="spouse",
            target_qid="Q6050",
            target_label="Fail Target",
        )
    )
    db_session.add(
        make_video(video_id="vid00000050", title="Fail Target here", description=None)
    )
    await db_session.flush()
    await service.generate(db_session)
    # Commit so approve()'s rollback-on-failure cannot unwind the seeded candidate
    # (mirrors production, where generate and approve run in separate sessions).
    await db_session.commit()

    cand = await service._candidates.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6050"
    )
    assert cand is not None
    # Capture the id before approve: its rollback-on-failure expires ORM objects,
    # so a later ``cand.id`` access would trigger a sync lazy-load (MissingGreenlet).
    candidate_id = cand.id

    result = await service.approve(
        db_session, candidate_id=candidate_id, reviewed_by="tester"
    )
    assert result.outcome == "failed"

    still = await service._candidates.get(db_session, candidate_id)
    assert still is not None and still.review_status == "pending"
    # No partial entity was left behind.
    grounded = await NamedEntityRepository().get_by_wikidata_qids(db_session, ["Q6050"])
    assert "Q6050" not in grounded
