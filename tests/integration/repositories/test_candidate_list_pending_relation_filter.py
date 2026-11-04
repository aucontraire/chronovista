"""Feature 105 (T021 / FR-014): the ``list_pending`` ``relation`` filter.

A newly-seeded set scores ~0 (ideologies/edges are spoken, not titled), so it buries in the
``grounds_nowhere`` bucket under the default ranking. The relation filter must return EVERY pending
candidate whose ``provenance.relations`` array contains the given field — regardless of score or
triage — so that set is findable. Downstream-consumer verification of the JSONB containment predicate.
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


def _candidate(
    qid: str,
    relations: list[str],
    *,
    score: float,
    triage: TriageCategory,
) -> CandidateSuggestionCreate:
    return CandidateSuggestionCreate(
        source_channel=SourceChannel.RELATION,
        wikidata_qid=qid,
        label="Placeholder Label",
        label_normalized="placeholder label",
        type_hint=EntityType.PERSON,
        token_count=2,
        corroboration_count=1,
        dangling_edge_count=1,
        salience=0,
        score=score,
        triage=triage,
        provenance={"seed_entity_ids": [str(uuid.uuid4())], "relations": relations},
    )


async def test_relation_filter_returns_full_set_regardless_of_score(
    db_session: AsyncSession,
) -> None:
    repo = CandidateSuggestionRepository()
    # influenced_by: one buried at score 0 / grounds_nowhere, one high in worth_review.
    await repo.upsert_generated(
        db_session,
        candidate=_candidate(
            "Q9101", ["influenced_by"], score=0.0, triage=TriageCategory.GROUNDS_NOWHERE
        ),
    )
    await repo.upsert_generated(
        db_session,
        candidate=_candidate(
            "Q9102",
            ["influenced_by", "member_of"],
            score=42.0,
            triage=TriageCategory.WORTH_REVIEW,
        ),
    )
    await repo.upsert_generated(
        db_session,
        candidate=_candidate(
            "Q9103", ["funder"], score=5.0, triage=TriageCategory.WORTH_REVIEW
        ),
    )

    infl, infl_total = await repo.list_pending(db_session, relation="influenced_by")
    # the zero-scoring, grounds_nowhere candidate is returned — the whole point of the filter.
    assert {c.wikidata_qid for c in infl} == {"Q9101", "Q9102"}
    assert infl_total == 2

    funder, funder_total = await repo.list_pending(db_session, relation="funder")
    assert {c.wikidata_qid for c in funder} == {"Q9103"}
    assert funder_total == 1

    # a relation nothing carries returns the clean empty set, not an error.
    none_rows, none_total = await repo.list_pending(db_session, relation="perpetrator")
    assert none_rows == []
    assert none_total == 0
