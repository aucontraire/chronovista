"""Unit tests for WikidataClient.fetch_properties (Feature 068, T004).

The external API is mocked via ``httpx.MockTransport`` replaying recorded RESPONSE SHAPES through the
real client + real extractors — not hand-built property dicts. Covers the two-round fetch (claims →
value-QID labels), value-QID→label resolution, an unresolved value-QID staying as a QID (FR-007), the
no-wanted-property case, and graceful degradation (FR-006). Fixture values are neutral placeholders
(Constitution VI).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from chronovista.services.wikidata_client import WikidataClient, WikidataUnavailable

pytestmark = pytest.mark.asyncio


def _claims_response() -> dict[str, Any]:
    """One entity (Q000001) with an item field (occupation) and a literal field (birth_date)."""
    return {
        "entities": {
            "Q000001": {
                "claims": {
                    "P106": [
                        {
                            "mainsnak": {
                                "snaktype": "value",
                                "datavalue": {
                                    "type": "wikibase-entityid",
                                    "value": {"id": "Q000010"},
                                },
                            }
                        },
                        {
                            "mainsnak": {
                                "snaktype": "value",
                                "datavalue": {
                                    "type": "wikibase-entityid",
                                    "value": {"id": "Q000011"},
                                },
                            }
                        },
                    ],
                    "P569": [
                        {
                            "mainsnak": {
                                "snaktype": "value",
                                "datavalue": {
                                    "type": "time",
                                    "value": {
                                        "time": "+1970-05-06T00:00:00Z",
                                        "precision": 11,
                                    },
                                },
                            }
                        }
                    ],
                }
            }
        }
    }


def _labels_response(resolve_second: bool = True) -> dict[str, Any]:
    """Labels for the value-QIDs. When ``resolve_second`` is False, Q000011 has no label."""
    entities: dict[str, Any] = {
        "Q000010": {
            "labels": {"en": {"language": "en", "value": "Placeholder Occupation A"}}
        },
    }
    if resolve_second:
        entities["Q000011"] = {
            "labels": {"mul": {"language": "mul", "value": "Placeholder Occupation B"}}
        }
    else:
        entities["Q000011"] = {"labels": {}}
    return {"entities": entities}


def _handler(*, claims: dict[str, Any], labels: dict[str, Any]) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        action = request.url.params.get("action")
        props = request.url.params.get("props")
        if action == "wbgetentities" and props == "claims":
            return httpx.Response(200, json=claims)
        if action == "wbgetentities" and props == "labels":
            return httpx.Response(200, json=labels)
        return httpx.Response(200, json={})

    return httpx.MockTransport(respond)


def _client(transport: httpx.MockTransport) -> WikidataClient:
    return WikidataClient(http=httpx.AsyncClient(transport=transport))


class TestFetchProperties:
    async def test_resolves_labels_and_keeps_literals(self) -> None:
        client = _client(
            _handler(
                claims=_claims_response(), labels=_labels_response(resolve_second=True)
            )
        )
        props = await client.fetch_properties("Q000001")

        assert set(props.keys()) == {"occupation", "birth_date"}
        assert props["occupation"]["values"] == [
            "Placeholder Occupation A",
            "Placeholder Occupation B",
        ]
        assert props["occupation"]["qids"] == ["Q000010", "Q000011"]
        assert props["birth_date"]["values"] == ["1970-05-06"]
        for block in props.values():
            assert set(block.keys()) == {"values", "qids", "source", "set_at"}
            assert block["source"] == "wikidata"

    async def test_unresolved_value_qid_stays_as_qid(self) -> None:
        # FR-007: a value-QID whose label did not resolve is stored as its QID, never dropped.
        client = _client(
            _handler(
                claims=_claims_response(), labels=_labels_response(resolve_second=False)
            )
        )
        props = await client.fetch_properties("Q000001")
        assert props["occupation"]["values"] == ["Placeholder Occupation A", "Q000011"]

    async def test_no_wanted_property_returns_empty(self) -> None:
        claims = {"entities": {"Q000001": {"claims": {"P9999": []}}}}
        client = _client(_handler(claims=claims, labels={"entities": {}}))
        assert await client.fetch_properties("Q000001") == {}

    async def test_literal_only_entity_skips_label_round(self) -> None:
        claims = {
            "entities": {
                "Q000001": {
                    "claims": {
                        "P2002": [
                            {
                                "mainsnak": {
                                    "snaktype": "value",
                                    "datavalue": {
                                        "type": "string",
                                        "value": "example_handle",
                                    },
                                }
                            }
                        ]
                    }
                }
            }
        }
        # No value-QIDs → the label round MUST be skipped (a real `ids=` empty call 400s).
        calls: dict[str, int] = {"claims": 0, "labels": 0}

        def respond(request: httpx.Request) -> httpx.Response:
            props = request.url.params.get("props")
            if props == "claims":
                calls["claims"] += 1
                return httpx.Response(200, json=claims)
            if props == "labels":
                calls["labels"] += 1
                return httpx.Response(200, json={"entities": {}})
            return httpx.Response(200, json={})

        client = _client(httpx.MockTransport(respond))
        props = await client.fetch_properties("Q000001")
        assert props["x_username"]["values"] == ["example_handle"]
        assert props["x_username"]["qids"] == []
        assert calls == {
            "claims": 1,
            "labels": 0,
        }, "label round must be skipped for literal-only"

    async def test_empty_label_value_qid_stays_unresolved(self) -> None:
        # Parity (FR-002): a present-but-empty label resolves to "no label" — the value-QID is kept
        # as its QID, exactly as the batch pipeline does. Selecting a later non-empty language would
        # diverge from a subsequent load.
        labels = {
            "entities": {
                "Q000010": {
                    "labels": {"mul": {"value": ""}, "en": {"value": "English A"}}
                },
                "Q000011": {"labels": {"en": {"value": "Placeholder Occupation B"}}},
            }
        }
        client = _client(_handler(claims=_claims_response(), labels=labels))
        props = await client.fetch_properties("Q000001")
        # Q000010's first-present label (mul) is empty → dropped → QID kept; Q000011 resolves.
        assert props["occupation"]["values"] == ["Q000010", "Placeholder Occupation B"]

    async def test_transport_error_raises_unavailable(self) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = WikidataClient(
            http=httpx.AsyncClient(transport=httpx.MockTransport(boom))
        )
        with pytest.raises(WikidataUnavailable):
            await client.fetch_properties("Q000001")
