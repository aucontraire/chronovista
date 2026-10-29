"""Feature 098 (T015): Wikidata candidate endpoints return ``suggested_entity_type``.

Unlike ``test_wikidata_candidates.py`` (which fakes the whole client), this drives the real
``WikidataClient`` and the real ``suggest_entity_type`` classifier through the HTTP layer, faking
Wikidata only at the ``httpx.MockTransport`` boundary with ``wbgetentities`` / ``wbsearchentities``
payloads that carry a P31 claim. A stubbed classifier would make these tests pass regardless of
whether the client wired the suggestion into the response. Fixture values are neutral placeholders.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

import chronovista.api.routers.entity_mentions as router_mod
from chronovista.services.wikidata_client import WikidataClient

pytestmark = pytest.mark.asyncio


def _entity(p31: list[str] | None, label: str) -> dict[str, Any]:
    claims: dict[str, Any] = {}
    if p31 is not None:
        claims["P31"] = [
            {
                "mainsnak": {
                    "datavalue": {
                        "value": {"id": cid},
                        "type": "wikibase-entityid",
                    }
                }
            }
            for cid in p31
        ]
    return {
        "claims": claims,
        "sitelinks": {"enwiki": {}},
        "labels": {"en": {"language": "en", "value": label}},
        "descriptions": {"en": {"language": "en", "value": "placeholder"}},
    }


def _install_wikidata(
    monkeypatch: pytest.MonkeyPatch,
    entities: dict[str, dict[str, Any]],
) -> None:
    """Back the router's ``WikidataClient()`` with a real client over a MockTransport."""

    def respond(request: httpx.Request) -> httpx.Response:
        action = request.url.params.get("action")
        if action == "wbsearchentities":
            hits = [
                {"id": qid, "label": ent["labels"]["en"]["value"], "description": "x"}
                for qid, ent in entities.items()
            ]
            return httpx.Response(200, json={"search": hits})
        if action == "wbgetentities":
            ids = (request.url.params.get("ids") or "").split("|")
            return httpx.Response(
                200, json={"entities": {q: entities[q] for q in ids if q in entities}}
            )
        return httpx.Response(200, json={})

    def factory(*_a: Any, **_k: Any) -> WikidataClient:
        return WikidataClient(
            http=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        )

    monkeypatch.setattr(router_mod, "WikidataClient", factory)


class TestResolveSuggestedEntityType:
    async def test_country_p31_suggests_place(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_wikidata(
            monkeypatch, {"Q000101": _entity(["Q6256"], "Placeholder Country")}
        )
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates/Q000101",
            params={"entity_type": "place"},
        )
        assert r.status_code == 200, r.text
        cand = r.json()["data"]["candidate"]
        assert cand["instance_of"] == ["Q6256"]
        assert cand["suggested_entity_type"] == "place"

    async def test_human_p31_suggests_person(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_wikidata(
            monkeypatch, {"Q000102": _entity(["Q5"], "Placeholder Human")}
        )
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates/Q000102",
            params={"entity_type": "person"},
        )
        assert r.status_code == 200, r.text
        cand = r.json()["data"]["candidate"]
        assert cand["suggested_entity_type"] == "person"
        assert cand["type_matches"] is True

    @pytest.mark.parametrize("p31", [None, [], ["Q999999999"]])
    async def test_no_usable_p31_is_null_suggestion_and_neutral_badge(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        p31: list[str] | None,
    ) -> None:
        _install_wikidata(monkeypatch, {"Q000103": _entity(p31, "Placeholder Unknown")})
        # "concept" has no corroboration set, so the badge is neutral; the suggestion must
        # agree (null), since both derive from the shared classifier.
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates/Q000103",
            params={"entity_type": "concept"},
        )
        assert r.status_code == 200, r.text
        cand = r.json()["data"]["candidate"]
        assert "suggested_entity_type" in cand
        assert cand["suggested_entity_type"] is None
        assert cand["type_matches"] is None


class TestSearchSuggestedEntityType:
    async def test_each_candidate_carries_its_own_suggestion(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_wikidata(
            monkeypatch,
            {
                "Q000201": _entity(["Q5"], "Placeholder Human"),
                "Q000202": _entity(["Q6256"], "Placeholder Country"),
                "Q000203": _entity([], "Placeholder Unknown"),
            },
        )
        r = await async_client.get(
            "/api/v1/entities/wikidata-candidates",
            params={"name": "Placeholder", "entity_type": "person"},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["unavailable"] is False
        by_qid = {c["qid"]: c for c in data["candidates"]}
        assert set(by_qid) == {"Q000201", "Q000202", "Q000203"}
        assert all("suggested_entity_type" in c for c in by_qid.values())
        assert by_qid["Q000201"]["suggested_entity_type"] == "person"
        assert by_qid["Q000202"]["suggested_entity_type"] == "place"
        assert by_qid["Q000203"]["suggested_entity_type"] is None
