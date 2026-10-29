"""Feature 098 (Phase 4): approval re-verifies the candidate's type against Wikidata.

The Wikidata fake sits at the HTTP-response boundary (``httpx.MockTransport``), so the
real ``fetch_instance_of`` extraction, the real ``classify_entity_type`` and the real
``_reverify_type`` all run. Placeholder QIDs/labels only (no library content).

Candidates are produced by the real ``generate`` with Wikidata *down* (so the stored
``type_hint`` is the relation heuristic), then the stored hint is overwritten to the
stale value under test; approval is then run against a differently-behaving Wikidata.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import CandidateSuggestion as CandidateDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.candidate_suggestion_service import (
    CandidateSuggestionService,
)
from chronovista.services.wikidata_client import WikidataClient

pytestmark = pytest.mark.asyncio

COUNTRY_P31 = "Q6256"
TARGET_LABEL = "Placeholder Target"


def _entity_payload(p31: str | None) -> dict[str, Any]:
    claims: dict[str, Any] = {}
    if p31 is not None:
        claims["P31"] = [{"mainsnak": {"datavalue": {"value": {"id": p31}}}}]
    return {"claims": claims, "sitelinks": {}, "labels": {}, "descriptions": {}}


def _service(
    handler: Callable[[httpx.Request], httpx.Response],
) -> CandidateSuggestionService:
    return CandidateSuggestionService(
        candidate_repo=CandidateSuggestionRepository(),
        entity_repo=NamedEntityRepository(),
        video_repo=VideoRepository(),
        alias_repo=EntityAliasRepository(),
        enrichment=None,
        wikidata_client=WikidataClient(
            http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        ),
    )


def _down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("boom", request=request)


async def _pending_candidate(
    session: AsyncSession,
    make_seed_entity: Callable[..., NamedEntityDB],
    *,
    seed_qid: str,
    target_qid: str,
    stored_type: str,
) -> CandidateDB:
    """Generate a real candidate (Wikidata down), then set its stale stored type."""
    session.add(
        make_seed_entity(
            name=f"Seed {seed_qid}",
            qid=seed_qid,
            relation="founder",
            target_qid=target_qid,
            target_label=TARGET_LABEL,
        )
    )
    await session.flush()
    await _service(_down).generate(session)
    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        session, source_channel="relation", wikidata_qid=target_qid
    )
    assert cand is not None
    cand.type_hint = stored_type
    await session.flush()
    return cand


async def _entity_types_for_qid(session: AsyncSession, qid: str) -> list[str]:
    grounded = await NamedEntityRepository().get_by_wikidata_qids(session, [qid])
    if qid not in grounded:
        return []
    entity = await NamedEntityRepository().get(session, grounded[qid][0])
    assert entity is not None
    return [entity.entity_type]


async def test_reverify_overrides_stored_type_on_create(
    db_session: AsyncSession, make_seed_entity: Callable[..., NamedEntityDB]
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"entities": {"Q7101": _entity_payload(COUNTRY_P31)}}
        )

    cand = await _pending_candidate(
        db_session,
        make_seed_entity,
        seed_qid="Q5951",
        target_qid="Q7101",
        stored_type="person",
    )
    result = await _service(handler).approve(
        db_session, candidate_id=cand.id, reviewed_by="tester"
    )

    assert result.outcome == "approved"
    assert result.created_entity_id is not None
    created = await NamedEntityRepository().get(db_session, result.created_entity_id)
    assert created is not None
    assert created.entity_type == "place"
    assert requests and "Q7101" in requests[0].url.params["ids"]


async def test_collision_is_keyed_on_reverified_type(
    db_session: AsyncSession, make_seed_entity: Callable[..., NamedEntityDB]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"entities": {"Q7102": _entity_payload(COUNTRY_P31)}}
        )

    cand = await _pending_candidate(
        db_session,
        make_seed_entity,
        seed_qid="Q5952",
        target_qid="Q7102",
        stored_type="person",
    )
    service = _service(handler)
    normalized = service._normalizer.normalize(cand.label) or cand.label_normalized
    existing = NamedEntityDB(
        id=uuid.uuid4(),
        canonical_name=cand.label,
        canonical_name_normalized=normalized,
        entity_type="place",
    )
    db_session.add(existing)
    await db_session.flush()

    result = await service.approve(
        db_session, candidate_id=cand.id, reviewed_by="tester"
    )

    # Keyed on the stored 'person' type there is no collision and a mistyped entity
    # would be created; keyed on the re-verified 'place' type it supersedes.
    assert result.outcome == "superseded"
    assert result.created_entity_id == existing.id
    assert await _entity_types_for_qid(db_session, "Q7102") == []


@pytest.mark.parametrize("failure", ["transport", "server_error"])
async def test_wikidata_unavailable_keeps_stored_type_and_approves(
    db_session: AsyncSession,
    make_seed_entity: Callable[..., NamedEntityDB],
    failure: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "transport":
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(503)

    cand = await _pending_candidate(
        db_session,
        make_seed_entity,
        seed_qid="Q5953",
        target_qid="Q7103",
        stored_type="organization",
    )
    result = await _service(handler).approve(  # must not raise
        db_session, candidate_id=cand.id, reviewed_by="tester"
    )

    assert result.outcome == "approved"
    assert result.created_entity_id is not None
    created = await NamedEntityRepository().get(db_session, result.created_entity_id)
    assert created is not None
    assert created.entity_type == "organization"


@pytest.mark.parametrize("shape", ["absent_from_response", "empty_p31"])
async def test_reachable_but_no_p31_keeps_stored_type(
    db_session: AsyncSession,
    make_seed_entity: Callable[..., NamedEntityDB],
    shape: str,
) -> None:
    # Direction A (FR-006): re-verify overrides the stored type ONLY with positive P31 evidence.
    # Reachable but no usable P31 (QID absent, or present with no instance_of) → keep the stored
    # type, consistent with generation's heuristic-on-no-P31, so a reviewer never approves one
    # type and gets another.
    def handler(request: httpx.Request) -> httpx.Response:
        entities: dict[str, Any] = (
            {} if shape == "absent_from_response" else {"Q7104": _entity_payload(None)}
        )
        return httpx.Response(200, json={"entities": entities})

    cand = await _pending_candidate(
        db_session,
        make_seed_entity,
        seed_qid="Q5954",
        target_qid="Q7104",
        stored_type="person",
    )
    result = await _service(handler).approve(
        db_session, candidate_id=cand.id, reviewed_by="tester"
    )

    assert result.outcome == "approved"
    assert result.created_entity_id is not None
    created = await NamedEntityRepository().get(db_session, result.created_entity_id)
    assert created is not None
    assert created.entity_type == "person"
