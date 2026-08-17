"""Unit tests for DbpediaResolver (on-approval DBpedia).

The two external endpoints (DBpedia SPARQL + Wikidata sitelinks) are mocked via ``httpx.MockTransport``
replaying recorded response SHAPES through the real resolver. Covers the owl:sameAs path, the
enwiki-sitelink fallback, the no-match case, and graceful degradation (never raises). Neutral
placeholders (Constitution VI).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from chronovista.services.dbpedia_resolver import (
    PROV_SAMEAS,
    PROV_SITELINK,
    DbpediaResolver,
)

pytestmark = pytest.mark.asyncio


def _transport(
    *, sameas: str | None, enwiki_title: str | None, sparql_error: bool = False
) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "dbpedia.org/sparql" in url:
            if sparql_error:
                return httpx.Response(405, text="Not Allowed")
            bindings = [{"resource": {"value": sameas}}] if sameas else []
            return httpx.Response(200, json={"results": {"bindings": bindings}})
        if "wikidata.org/w/api.php" in url:
            qid = request.url.params.get("ids")
            ent: dict[str, Any] = {}
            if enwiki_title:
                ent = {"sitelinks": {"enwiki": {"title": enwiki_title}}}
            return httpx.Response(200, json={"entities": {qid: ent}})
        return httpx.Response(200, json={})

    return httpx.MockTransport(respond)


def _resolver(transport: httpx.MockTransport) -> DbpediaResolver:
    return DbpediaResolver(http=httpx.AsyncClient(transport=transport))


class TestResolve:
    async def test_owl_sameas_hit(self) -> None:
        iri = "http://dbpedia.org/resource/Placeholder_Person"
        r = _resolver(_transport(sameas=iri, enwiki_title=None))
        assert await r.resolve("Q000001") == (iri, PROV_SAMEAS)

    async def test_sitelink_fallback_when_sameas_empty(self) -> None:
        # owl:sameAs returns nothing → fall back to the enwiki sitelink title.
        r = _resolver(
            _transport(sameas=None, enwiki_title="Placeholder Person (analyst)")
        )
        iri, prov = await r.resolve("Q000001")  # type: ignore[misc]
        # Title → IRI: spaces become underscores; parens preserved by the safe set.
        assert iri == "http://dbpedia.org/resource/Placeholder_Person_(analyst)"
        assert prov == PROV_SITELINK

    async def test_no_match_returns_none(self) -> None:
        # No owl:sameAs and no enwiki article (thin item) → no DBpedia link.
        r = _resolver(_transport(sameas=None, enwiki_title=None))
        assert await r.resolve("Q000001") is None

    async def test_sparql_error_degrades_to_sitelink(self) -> None:
        # DBpedia's endpoint is flaky (405). A SPARQL failure must not raise — fall back to sitelink.
        r = _resolver(
            _transport(
                sameas=None, enwiki_title="Placeholder Person", sparql_error=True
            )
        )
        result = await r.resolve("Q000001")
        assert result == (
            "http://dbpedia.org/resource/Placeholder_Person",
            PROV_SITELINK,
        )

    async def test_total_transport_failure_returns_none(self) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        r = DbpediaResolver(http=httpx.AsyncClient(transport=httpx.MockTransport(boom)))
        assert await r.resolve("Q000001") is None  # never raises
