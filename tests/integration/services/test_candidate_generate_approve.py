"""Cross-feature mutation integration test (Feature 096, T012, Constitution).

Generate → approve → read the created entity back through a downstream entity path,
asserting it is present, grounded, and not duplicated; plus the reject path. Runs
against the real integration DB (not mocks) — the mutation this feature performs on
the shared entity store, verified through the reader's path.
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


async def test_generate_then_approve_creates_grounded_entity(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    db_session.add(
        make_seed_entity(
            name="Seed Person",
            qid="Q5001",
            relation="spouse",
            target_qid="Q6001",
            target_label="Target Person",
        )
    )
    db_session.add_all(
        [
            make_video(
                video_id="vid00000001",
                title="A conversation with Target Person",
                description="Target Person discusses things",
            ),
            make_video(
                video_id="vid00000002", title="unrelated clip", description=None
            ),
        ]
    )
    await db_session.flush()

    summary = await candidate_service.generate(db_session)
    assert summary.seeds_grounded == 1
    assert summary.candidates_discovered >= 1

    repo = candidate_service._candidates
    cand = await repo.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6001"
    )
    assert cand is not None
    assert cand.review_status == "pending"
    assert cand.type_hint == "person"  # spouse → person
    assert cand.salience >= 1  # "Target Person" is in the corpus

    result = await candidate_service.approve(
        db_session, candidate_id=cand.id, reviewed_by="tester"
    )
    assert result.outcome == "approved"
    assert result.created_entity_id is not None

    # Read back through the entity repository — the data path the /entities surfaces use.
    entity_repo = NamedEntityRepository()
    grounded = await entity_repo.get_by_wikidata_qids(db_session, ["Q6001"])
    assert "Q6001" in grounded
    created = await entity_repo.get(db_session, result.created_entity_id)
    assert created is not None
    assert created.status == "active"
    assert created.external_ids["wikidata"]["id"] == "Q6001"

    # No duplicate: approving the same candidate again is refused (already approved).
    again = await candidate_service.approve(
        db_session, candidate_id=cand.id, reviewed_by="tester"
    )
    assert again.outcome == "failed"


async def test_generate_with_seeds_but_empty_corpus_does_not_crash(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
) -> None:
    """Grounded seeds but zero videos: grounding degrades to salience 0, no crash (H1)."""
    db_session.add(
        make_seed_entity(
            name="Seed NoCorpus",
            qid="Q5060",
            relation="spouse",
            target_qid="Q6060",
            target_label="NoCorpus Target",
        )
    )
    await db_session.flush()

    summary = await candidate_service.generate(db_session)  # must not raise
    assert summary.candidates_discovered >= 1
    cand = await candidate_service._candidates.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6060"
    )
    assert cand is not None
    assert cand.salience == 0
    assert cand.triage == "grounds_nowhere"


async def test_generate_tolerates_malformed_qids_shape(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    """A seed whose relation `qids` is a scalar (not an array) is skipped, not fatal."""
    import uuid as _uuid

    # Malformed: qids is a bare string instead of a list → would make
    # jsonb_array_elements_text raise and abort the whole emit without the guard.
    db_session.add(
        NamedEntityDB(
            id=_uuid.uuid4(),
            canonical_name="Seed Malformed",
            canonical_name_normalized="seed malformed",
            entity_type="person",
            external_ids={"wikidata": {"id": "Q5070"}},
            properties={
                "spouse": {"qids": "Q6070", "values": "Bad Shape", "source": "wikidata"}
            },
        )
    )
    # A well-formed seed alongside it must still yield its candidate.
    db_session.add(
        make_seed_entity(
            name="Seed Good",
            qid="Q5071",
            relation="spouse",
            target_qid="Q6071",
            target_label="Good Target",
        )
    )
    db_session.add(
        make_video(video_id="vid00005071", title="Good Target here", description=None)
    )
    await db_session.flush()

    summary = await candidate_service.generate(db_session)  # must not raise
    assert summary.candidates_discovered >= 1
    good = await candidate_service._candidates.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6071"
    )
    assert good is not None
    malformed = await candidate_service._candidates.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6070"
    )
    assert malformed is None  # the malformed seed contributed nothing


async def test_reject_marks_candidate_rejected(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    db_session.add(
        make_seed_entity(
            name="Seed Two",
            qid="Q5002",
            relation="member_of",
            target_qid="Q6002",
            target_label="Target Organization",
        )
    )
    db_session.add(
        make_video(
            video_id="vid00000003",
            title="Target Organization announcement",
            description=None,
        )
    )
    await db_session.flush()

    await candidate_service.generate(db_session)
    repo = candidate_service._candidates
    cand = await repo.get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6002"
    )
    assert cand is not None
    assert cand.type_hint == "organization"  # member_of → organization

    result = await candidate_service.reject(
        db_session, candidate_id=cand.id, reviewed_by="tester"
    )
    assert result.outcome == "rejected"
    refreshed = await repo.get(db_session, cand.id)
    assert refreshed is not None and refreshed.review_status == "rejected"
