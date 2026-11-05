"""End-to-end alias grounding through generation (bug fix: salience dropped aliases).

The unit guard (``tests/unit/architecture/test_candidate_salience_aliases_fitness.py``) proves
``_CorpusIndex.salience`` honours aliases; these integration tests prove the aliases actually flow
through the full ``generate`` → ``_build_create`` → ``salience`` seam against a real DB, and that
the ``salience_aliases`` provenance marker records which branch ran — label-only because the fetch
was *unavailable* vs. because the entity genuinely has *no* aliases. The ``candidate_service``
fixture wires no Wikidata client, so the ``aliases_map`` argument drives each branch deterministically
with no network. Placeholder names only — no library content.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)
from chronovista.services.candidate_suggestion_service import CandidateSuggestionService

pytestmark = pytest.mark.asyncio

# Label tokens absent from the corpus; only the acronym alias appears in a video.
_LABEL = "Giant Systems Organization"
_ALIAS = "GSO"


async def test_alias_map_raises_salience_and_marks_used(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
    make_video: Callable[..., VideoDB],
) -> None:
    db_session.add(
        make_seed_entity(
            name="Seed Used",
            qid="Q8101",
            relation="spouse",
            target_qid="Q9101",
            target_label=_LABEL,
        )
    )
    db_session.add(
        make_video(
            video_id="vidsalias_used1",
            title="The GSO annual report is out",
            description="GSO featured in coverage",
        )
    )
    await db_session.flush()

    # Label tokens ("giant/systems/organization") appear in no video; only the alias does, so a
    # non-zero salience here can ONLY come from the alias flowing through to the matcher.
    await candidate_service.generate(db_session, aliases_map={"Q9101": [_ALIAS]})

    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q9101"
    )
    assert cand is not None
    assert cand.salience >= 1
    assert cand.provenance.get("salience_aliases") == "used"


async def test_empty_alias_map_marks_none(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
) -> None:
    db_session.add(
        make_seed_entity(
            name="Seed None",
            qid="Q8102",
            relation="spouse",
            target_qid="Q9102",
            target_label=_LABEL,
        )
    )
    await db_session.flush()

    # A successful fetch that returned no aliases for this QID: label-only salience, but recorded
    # as "none" (the entity has no aliases) — distinct from an unavailable fetch.
    await candidate_service.generate(db_session, aliases_map={})

    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q9102"
    )
    assert cand is not None
    assert cand.provenance.get("salience_aliases") == "none"


async def test_no_alias_fetch_marks_unavailable(
    db_session: AsyncSession,
    candidate_service: CandidateSuggestionService,
    make_seed_entity: Callable[..., NamedEntityDB],
) -> None:
    db_session.add(
        make_seed_entity(
            name="Seed Unavailable",
            qid="Q8103",
            relation="spouse",
            target_qid="Q9103",
            target_label=_LABEL,
        )
    )
    await db_session.flush()

    # No aliases_map and the fixture wires no Wikidata client, so the alias fetch is unavailable.
    # Salience falls back to label-only, recorded as "unavailable" — NOT "none", so a later reader
    # can tell this apart from an entity that truly has no aliases (record-which-fallback-ran).
    await candidate_service.generate(db_session)

    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q9103"
    )
    assert cand is not None
    assert cand.provenance.get("salience_aliases") == "unavailable"
