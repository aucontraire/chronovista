"""Feature 098 (T008): candidate typing from Wikidata P31, and its fallback.

The Wikidata fake sits at the HTTP-response boundary (``httpx.MockTransport``), so the
real ``WikidataClient._get`` -> ``_item_details`` -> ``fetch_instance_of`` extraction and the
real ``classify_entity_type`` all run. Placeholder QIDs/labels only (no library content).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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
HUMAN_P31 = "Q5"


def _entity_payload(p31: str | None) -> dict[str, Any]:
    claims: dict[str, Any] = {}
    if p31 is not None:
        claims["P31"] = [{"mainsnak": {"datavalue": {"value": {"id": p31}}}}]
    return {"claims": claims, "sitelinks": {}, "labels": {}, "descriptions": {}}


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> WikidataClient:
    return WikidataClient(
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


def _service(wikidata: WikidataClient) -> CandidateSuggestionService:
    return CandidateSuggestionService(
        candidate_repo=CandidateSuggestionRepository(),
        entity_repo=NamedEntityRepository(),
        video_repo=VideoRepository(),
        alias_repo=EntityAliasRepository(),
        enrichment=None,
        wikidata_client=wikidata,
    )


async def _seed(
    session: AsyncSession,
    make_seed_entity: Callable[..., NamedEntityDB],
    *,
    target_qid: str,
) -> None:
    # "founder" -> the relation heuristic says PERSON, so a correct PLACE can only
    # come from the P31 path.
    session.add(
        make_seed_entity(
            name="Seed Org",
            qid="Q5900",
            relation="founder",
            target_qid=target_qid,
            target_label="Placeholder Target",
        )
    )
    await session.flush()


async def test_country_p31_types_candidate_place_not_person(
    db_session: AsyncSession, make_seed_entity: Callable[..., NamedEntityDB]
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.params["action"] == "wbgetentities"
        return httpx.Response(
            200, json={"entities": {"Q6901": _entity_payload(COUNTRY_P31)}}
        )

    await _seed(db_session, make_seed_entity, target_qid="Q6901")
    await _service(_client(handler)).generate(db_session)

    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6901"
    )
    assert cand is not None
    assert cand.type_hint == "place"
    # Proves the request really crossed the HTTP boundary, asking for this QID.
    assert requests and "Q6901" in requests[0].url.params["ids"]


async def test_p31_overrides_relation_heuristic_in_both_directions(
    db_session: AsyncSession, make_seed_entity: Callable[..., NamedEntityDB]
) -> None:
    """A Q5 target reached via a place-implying relation is person, not place."""
    db_session.add(
        make_seed_entity(
            name="Seed Birth",
            qid="Q5901",
            relation="place_of_birth",
            target_qid="Q6902",
            target_label="Placeholder Human",
        )
    )
    await db_session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"entities": {"Q6902": _entity_payload(HUMAN_P31)}}
        )

    await _service(_client(handler)).generate(db_session)
    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6902"
    )
    assert cand is not None
    assert cand.type_hint == "person"


@pytest.mark.parametrize("failure", ["transport", "server_error"])
async def test_wikidata_unavailable_falls_back_to_relation_heuristic(
    db_session: AsyncSession,
    make_seed_entity: Callable[..., NamedEntityDB],
    failure: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "transport":
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(503)

    await _seed(db_session, make_seed_entity, target_qid="Q6903")
    summary = await _service(_client(handler)).generate(db_session)  # must not raise

    assert summary.candidates_upserted >= 1
    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6903"
    )
    assert cand is not None
    assert cand.type_hint == "person"  # founder -> person heuristic


async def test_qid_without_p31_falls_back_to_relation_heuristic(
    db_session: AsyncSession, make_seed_entity: Callable[..., NamedEntityDB]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"entities": {"Q6904": _entity_payload(None)}})

    await _seed(db_session, make_seed_entity, target_qid="Q6904")
    await _service(_client(handler)).generate(db_session)
    cand = await CandidateSuggestionRepository().get_by_channel_qid(
        db_session, source_channel="relation", wikidata_qid="Q6904"
    )
    assert cand is not None
    assert cand.type_hint == "person"
