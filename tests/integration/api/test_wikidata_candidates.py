"""Candidate-search endpoint (Feature 067, US3, T023).

The endpoint returns the ranked shortlist and distinguishes a benign no-match (empty +
unavailable:false) from a soft failure (empty + unavailable:true) — never a 5xx that would
block the create modal (FR-012/015). The WikidataClient is monkeypatched so no network call
occurs; the client's own parsing is covered by ST-004 (test_wikidata_client).
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

import chronovista.api.routers.entity_mentions as router_mod
from chronovista.models.wikidata_candidate import WikidataCandidate
from chronovista.services.wikidata_client import WikidataUnavailable

pytestmark = pytest.mark.asyncio


def _install_fake(
    monkeypatch: pytest.MonkeyPatch,
    behavior: list[WikidataCandidate] | Exception,
) -> None:
    class _Fake:
        def __init__(self, *a: Any, **k: Any) -> None: ...

        async def search_candidates(
            self, name: str, entity_type: str, *, limit: int = 5, offset: int = 0
        ) -> list[WikidataCandidate]:
            if isinstance(behavior, Exception):
                raise behavior
            return behavior

        async def resolve_candidate(
            self, qid: str, entity_type: str
        ) -> WikidataCandidate | None:
            if isinstance(behavior, Exception):
                raise behavior
            return behavior[0] if behavior else None

    monkeypatch.setattr(router_mod, "WikidataClient", _Fake)


class TestWikidataCandidatesEndpoint:
    async def test_returns_ranked_shortlist(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(
            monkeypatch,
            [
                WikidataCandidate(
                    qid="Q000001",
                    label="Placeholder One",
                    description="a person",
                    instance_of=["Q5"],
                    statement_count=42,
                    sitelink_count=3,
                    is_stub=False,
                    type_matches=True,
                )
            ],
        )
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates",
            params={"name": "Placeholder", "entity_type": "person"},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["unavailable"] is False
        assert len(data["candidates"]) == 1
        c = data["candidates"][0]
        assert c["qid"] == "Q000001"
        assert c["type_matches"] is True
        assert set(c) >= {
            "qid",
            "label",
            "description",
            "instance_of",
            "statement_count",
            "sitelink_count",
            "is_stub",
            "type_matches",
        }

    async def test_no_match_is_empty_and_available(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, [])
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates",
            params={"name": "Nobody", "entity_type": "person"},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["candidates"] == []
        assert data["unavailable"] is False  # benign "no match"

    async def test_lookup_failure_is_soft_not_5xx(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, WikidataUnavailable("timeout"))
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates",
            params={"name": "X", "entity_type": "person"},
        )
        assert r.status_code == 200, r.text  # NOT a 5xx — must not block the modal
        data = r.json()["data"]
        assert data["candidates"] == []
        assert data["unavailable"] is True  # distinct soft-failure signal

    async def test_static_route_not_captured_as_entity_id(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards the route-ordering fix: the path is not swallowed by /entities/{id}."""
        _install_fake(monkeypatch, [])
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates",
            params={"name": "X", "entity_type": "person"},
        )
        assert r.status_code == 200, r.text
        assert "candidates" in r.json()["data"]  # not a NotFound envelope


class TestWikidataCandidateResolveEndpoint:
    async def test_offset_param_is_accepted(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, [])
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates",
            params={"name": "X", "entity_type": "person", "offset": 7, "limit": 7},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["candidates"] == []

    async def test_negative_offset_rejected(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, [])
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates",
            params={"name": "X", "entity_type": "person", "offset": -1},
        )
        assert r.status_code == 422  # ge=0 guard

    async def test_resolve_returns_the_pasted_candidate(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(
            monkeypatch,
            [
                WikidataCandidate(
                    qid="Q000009",
                    label="Placeholder Nine",
                    description="a person",
                    instance_of=["Q5"],
                    statement_count=50,
                    sitelink_count=8,
                    is_stub=False,
                    type_matches=True,
                )
            ],
        )
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates/Q000009",
            params={"entity_type": "person"},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["unavailable"] is False
        assert data["candidate"]["qid"] == "Q000009"

    async def test_resolve_unknown_qid_is_null_and_available(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, [])  # resolve_candidate returns None
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates/Q999999999",
            params={"entity_type": "person"},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["candidate"] is None
        assert data["unavailable"] is False  # reached the KB; just no such item

    async def test_resolve_failure_is_soft_not_5xx(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, WikidataUnavailable("timeout"))
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates/Q000009",
            params={"entity_type": "person"},
        )
        assert r.status_code == 200, r.text  # never blocks the modal
        data = r.json()["data"]
        assert data["candidate"] is None
        assert data["unavailable"] is True

    async def test_qid_subresource_not_captured_as_entity_detail(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The 3-segment .../wikidata-candidates/{qid} must hit the resolve route,
        never be shadowed by /entities/{entity_id} or an /entities/{entity_id}/... route.
        """
        _install_fake(monkeypatch, [])
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates/Q000009",
            params={"entity_type": "person"},
        )
        assert r.status_code == 200, r.text
        # The resolve envelope carries "candidate"/"unavailable" — an entity-detail
        # hit would carry neither.
        assert set(r.json()["data"]) == {"candidate", "unavailable"}
