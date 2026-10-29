"""Feature 098 (T009): the review filter reads the stored ``type_hint``.

Downstream-consumer verification: a candidate typed ``place`` must be listed by the
``type_hint='place'`` review filter and excluded by ``type_hint='person'``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.models.candidate_suggestion import CandidateSuggestionCreate
from chronovista.models.enums import EntityType, SourceChannel, TriageCategory
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)

pytestmark = pytest.mark.asyncio


def _candidate(qid: str, type_hint: EntityType) -> CandidateSuggestionCreate:
    return CandidateSuggestionCreate(
        source_channel=SourceChannel.RELATION,
        wikidata_qid=qid,
        label="Placeholder Label",
        label_normalized="placeholder label",
        type_hint=type_hint,
        token_count=2,
        corroboration_count=1,
        dangling_edge_count=1,
        salience=0,
        score=1.0,
        triage=TriageCategory.WORTH_REVIEW,
        provenance={"seed_entity_ids": [str(uuid.uuid4())], "relations": ["founder"]},
    )


async def test_type_filter_includes_matching_and_excludes_other(
    db_session: AsyncSession,
) -> None:
    repo = CandidateSuggestionRepository()
    await repo.upsert_generated(
        db_session, candidate=_candidate("Q7001", EntityType.PLACE)
    )
    await repo.upsert_generated(
        db_session, candidate=_candidate("Q7002", EntityType.PERSON)
    )

    places, place_total = await repo.list_pending(db_session, type_hint="place")
    persons, person_total = await repo.list_pending(db_session, type_hint="person")

    assert [c.wikidata_qid for c in places] == ["Q7001"]
    assert place_total == 1
    assert [c.wikidata_qid for c in persons] == ["Q7002"]
    assert person_total == 1
    assert "Q7001" not in {c.wikidata_qid for c in persons}


async def test_retyped_candidate_moves_between_filters(
    db_session: AsyncSession,
) -> None:
    """Regeneration re-types a pending row; the filter must follow the new value."""
    repo = CandidateSuggestionRepository()
    await repo.upsert_generated(
        db_session, candidate=_candidate("Q7003", EntityType.PERSON)
    )
    await repo.upsert_generated(
        db_session, candidate=_candidate("Q7003", EntityType.PLACE)
    )

    places, _ = await repo.list_pending(db_session, type_hint="place")
    persons, _ = await repo.list_pending(db_session, type_hint="person")
    assert [c.wikidata_qid for c in places] == ["Q7003"]
    assert persons == []
