"""ST-004 — WikidataClient parses pathological real-shaped responses (Feature 067, US3).

The external API is mocked in CI, but via httpx.MockTransport replaying recorded RESPONSE
SHAPES through the real client + real parsing — not a hand-built candidate object. Covers the
signals that separate a substantive match from a machine-generated stub (FR-013), the
mul/en-gb label fallback (FR-016), the empty-vs-unavailable distinction, and graceful
degradation (FR-012/015). Fixture values are neutral placeholders (Constitution VI).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from chronovista.services.wikidata_client import WikidataClient, WikidataUnavailable

pytestmark = pytest.mark.asyncio


def _entities_details() -> dict[str, Any]:
    """wbgetentities props=claims|sitelinks|labels — substantive item + author stub.

    Labels are returned in the same payload (Q000002 only under 'mul' — the FR-016 case).
    """
    return {
        "entities": {
            # Substantive: instance_of human, many statements, has sitelinks.
            "Q000001": {
                "claims": {
                    "P31": [
                        {
                            "mainsnak": {
                                "datavalue": {
                                    "value": {"id": "Q5"},
                                    "type": "wikibase-entityid",
                                }
                            }
                        }
                    ],
                    "P569": [{}, {}],
                    "P106": [{}, {}, {}],
                },
                "sitelinks": {"enwiki": {}, "eswiki": {}},
                "labels": {"en": {"language": "en", "value": "Placeholder One"}},
            },
            # Author stub: ORCID (P496), few statements, no sitelinks; label only under mul.
            "Q000002": {
                "claims": {
                    "P31": [
                        {
                            "mainsnak": {
                                "datavalue": {
                                    "value": {"id": "Q5"},
                                    "type": "wikibase-entityid",
                                }
                            }
                        }
                    ],
                    "P496": [{}],
                },
                "sitelinks": {},
                "labels": {"mul": {"language": "mul", "value": "Placeholder Two"}},
            },
        }
    }


def _handler(search: dict[str, Any]) -> httpx.MockTransport:
    """Build a MockTransport dispatching by action/props like the real API."""

    def respond(request: httpx.Request) -> httpx.Response:
        action = request.url.params.get("action")
        props = request.url.params.get("props")
        if action == "wbsearchentities":
            return httpx.Response(200, json=search)
        if action == "wbgetentities" and props == "claims|sitelinks|labels":
            return httpx.Response(200, json=_entities_details())
        return httpx.Response(200, json={})

    return httpx.MockTransport(respond)


def _client(transport: httpx.MockTransport) -> WikidataClient:
    return WikidataClient(http=httpx.AsyncClient(transport=transport))


class TestSignals:
    async def test_stub_and_type_signals(self) -> None:
        search = {
            "search": [
                {
                    "id": "Q000001",
                    "label": "Placeholder One",
                    "description": "a person",
                },
                {
                    "id": "Q000002",
                    "label": "Placeholder Two",
                    "description": "researcher",
                },
            ]
        }
        cands = await _client(_handler(search)).search_candidates(
            "Placeholder", "person", limit=5
        )
        by_qid = {c.qid: c for c in cands}

        substantive = by_qid["Q000001"]
        assert substantive.is_stub is False
        assert substantive.type_matches is True  # instance_of Q5 vs person
        assert substantive.sitelink_count == 2
        assert substantive.statement_count == 6  # 1 + 2 + 3

        stub = by_qid["Q000002"]
        assert stub.is_stub is True  # P496 + few statements + no sitelinks
        assert stub.sitelink_count == 0

    async def test_type_mismatch_not_flagged_as_matching(self) -> None:
        search = {"search": [{"id": "Q000001", "label": "X", "description": "d"}]}
        # instance_of is Q5 (human); assigning type 'place' must not "match".
        cands = await _client(_handler(search)).search_candidates("X", "place", limit=5)
        assert cands[0].type_matches is False


class TestLabelFallback:
    async def test_mul_only_label_is_resolved_not_no_label(self) -> None:
        # Search hit for Q000002 with an EMPTY label — must fall back to mul (FR-016).
        search = {
            "search": [{"id": "Q000002", "label": "", "description": "researcher"}]
        }
        cands = await _client(_handler(search)).search_candidates(
            "Placeholder", "person", limit=5
        )
        assert cands[0].label == "Placeholder Two"  # from mul, never "no label"
        assert cands[0].label != ""


class TestEmptyVsUnavailable:
    async def test_no_match_returns_empty_list(self) -> None:
        cands = await _client(_handler({"search": []})).search_candidates(
            "Nobody", "person", limit=5
        )
        assert cands == []

    async def test_transport_error_raises_unavailable(self) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = WikidataClient(
            http=httpx.AsyncClient(transport=httpx.MockTransport(boom))
        )
        with pytest.raises(WikidataUnavailable):
            await client.search_candidates("X", "person", limit=5)

    async def test_persistent_429_raises_unavailable(self) -> None:
        def rate_limited(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})

        client = WikidataClient(
            http=httpx.AsyncClient(transport=httpx.MockTransport(rate_limited))
        )
        with pytest.raises(WikidataUnavailable):
            await client.search_candidates("X", "person", limit=5)
