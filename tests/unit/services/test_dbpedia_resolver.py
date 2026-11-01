"""Unit tests for DbpediaResolver (on-approval DBpedia).

The two external endpoints (DBpedia SPARQL + Wikidata sitelinks) are mocked via ``httpx.MockTransport``
replaying recorded response SHAPES through the real resolver. Covers the owl:sameAs path, the
enwiki-sitelink fallback, the no-match case, and graceful degradation (never raises). Since Feature
102 the resolver composes the shared ``WikimediaTransport``, so this also covers the new behavior:
a transient failure is **retried** within a bounded budget before the resolver gives up, and an
unreachable outcome is logged distinctly from a genuine no-match (the ``None`` return is preserved
either way). Neutral placeholders (Constitution VI).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

import chronovista.services.wikimedia_transport as wt
from chronovista.services.dbpedia_resolver import (
    _UA_COMPONENT,
    PROV_SAMEAS,
    PROV_SITELINK,
    DbpediaResolver,
)
from chronovista.services.wikimedia_transport import wikimedia_user_agent

pytestmark = pytest.mark.asyncio


@pytest.fixture
def recorded_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Capture every ``asyncio.sleep`` the transport's backoff requests, incurring none."""
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(wt.asyncio, "sleep", fake_sleep)
    return waits


class TestUserAgent:
    """Wikimedia denies (403)/throttles a UA with no contact — the enwiki-sitelink fallback hits
    the Wikidata API, so every outbound request MUST carry the single-sourced, contact-bearing UA.
    Feature 102 moved UA assembly into the transport template (G1); the resolver only names its
    component label, so the test verifies the UA the transport actually sends."""

    def test_component_user_agent_identifies_tool_and_contact(self) -> None:
        ua = wikimedia_user_agent(_UA_COMPONENT)
        # Names the tool...
        assert "chronovista" in ua
        # ...and carries a contact (URL or email) — the missing piece that caused the 403.
        assert (
            ("http://" in ua) or ("https://" in ua) or ("@" in ua)
        ), "Wikimedia User-Agent policy requires a contact URL or email"
        # ...and keeps this client's distinct component label (FR-002).
        assert _UA_COMPONENT in ua

    async def test_requests_carry_the_templated_user_agent(self) -> None:
        seen: dict[str, Any] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            seen["ua"] = request.headers.get("User-Agent")
            return httpx.Response(200, json={"results": {"bindings": []}})

        await _resolver(httpx.MockTransport(respond)).resolve("Q000001")
        assert seen["ua"] == wikimedia_user_agent(_UA_COMPONENT)


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

    async def test_no_match_is_quiet_none_not_unreachable(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # No owl:sameAs and no enwiki article (thin item), both endpoints REACHED → a genuine
        # no-match. It stays a quiet None: NO unreachable warning is logged (FR-006).
        r = _resolver(_transport(sameas=None, enwiki_title=None))
        with caplog.at_level(
            logging.WARNING, logger="chronovista.services.dbpedia_resolver"
        ):
            assert await r.resolve("Q000001") is None
        assert "UNREACHABLE" not in caplog.text

    async def test_sparql_error_degrades_to_sitelink(self) -> None:
        # DBpedia's endpoint is flaky (405, non-retryable). A SPARQL failure must not raise — fall
        # back to the (reached) enwiki sitelink. The successful fallback logs no unreachable warning.
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

    async def test_transient_failure_is_retried_then_returns_none_and_logs_unreachable(
        self, recorded_sleeps: list[float], caplog: pytest.LogCaptureFixture
    ) -> None:
        # A transient transport error (connection reset — DBpedia's dominant failure mode) is now
        # RETRIED within the transport's bounded budget (3 attempts/endpoint), NOT swallowed on the
        # first try. On exhaustion the resolver still returns None (contract preserved), but logs
        # the outcome as UNREACHABLE — distinct from a verified absence (FR-006, FR-012).
        calls = {"sparql": 0, "wikidata": 0}

        def boom(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "dbpedia.org/sparql" in url:
                calls["sparql"] += 1
            elif "wikidata.org" in url:
                calls["wikidata"] += 1
            raise httpx.ConnectError("boom")

        r = DbpediaResolver(http=httpx.AsyncClient(transport=httpx.MockTransport(boom)))
        with caplog.at_level(
            logging.WARNING, logger="chronovista.services.dbpedia_resolver"
        ):
            result = await r.resolve("Q000001")

        assert result is None  # never raises; contract preserved
        # Each step retried to the bounded ceiling (was ONE attempt before Feature 102).
        assert calls["sparql"] == 3
        assert calls["wikidata"] == 3
        assert (
            recorded_sleeps  # bounded backoff waits requested (none actually incurred)
        )
        assert (
            "UNREACHABLE" in caplog.text
        )  # observable transient outage, not a quiet absence


def _malformed_transport(
    *, sparql_body: Any, wikidata_body: Any
) -> httpx.MockTransport:
    """A transport whose 200 bodies are well-formed JSON dicts but structurally unexpected."""

    def respond(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "dbpedia.org/sparql" in url:
            return httpx.Response(200, json=sparql_body)
        if "wikidata.org/w/api.php" in url:
            return httpx.Response(200, json=wikidata_body)
        return httpx.Response(200, json={})

    return httpx.MockTransport(respond)


class TestMalformedButValid200Body:
    """FIX 2: a structurally-odd-but-JSON-valid 200 body must not raise — the transport only
    guarantees ``data`` is a dict with no ``error`` key, so each parse step type-guards its
    structural access and returns ``None``. The resolver's "Never raises" contract holds on any
    dict input, on BOTH the SPARQL (owl:sameAs) step and the enwiki-sitelink fallback step.
    """

    # (sparql_body, wikidata_body): one unexpected shape on the SPARQL step, one on the enwiki step.
    _SPARQL_ODD = [
        {"results": None},  # results explicitly null
        {"results": {"bindings": "not-a-list"}},  # bindings a truthy non-list
        {"results": {"bindings": ["not-a-dict"]}},  # a binding row that is not a dict
    ]
    _ENWIKI_ODD = [
        {"entities": None},  # entities explicitly null
        {"entities": {"Q000001": {"sitelinks": "not-a-dict"}}},  # sitelinks a non-dict
        {"entities": "not-a-dict"},  # entities a truthy non-dict
    ]

    @pytest.mark.parametrize("sparql_body", _SPARQL_ODD)
    async def test_sparql_step_returns_none_not_raise(self, sparql_body: Any) -> None:
        # Odd SPARQL body; the enwiki step is a valid empty answer → overall None, no raise.
        r = _resolver(
            _malformed_transport(
                sparql_body=sparql_body,
                wikidata_body={"entities": {"Q000001": {}}},
            )
        )
        assert await r.resolve("Q000001") is None

    @pytest.mark.parametrize("wikidata_body", _ENWIKI_ODD)
    async def test_enwiki_step_returns_none_not_raise(self, wikidata_body: Any) -> None:
        # Valid-but-empty SPARQL (no owl:sameAs) forces the enwiki fallback, whose body is odd →
        # overall None, no raise.
        r = _resolver(
            _malformed_transport(
                sparql_body={"results": {"bindings": []}},
                wikidata_body=wikidata_body,
            )
        )
        assert await r.resolve("Q000001") is None
