"""Unit tests for the Wikipedia free-Commons image fallback gate (Feature 093).

The three Wikimedia endpoints (Wikidata sitelinks, enwiki pageprops, enwiki/Commons imageinfo) are
mocked via ``httpx.MockTransport`` replaying recorded response SHAPES through the real service. The
load-bearing legal gate (FR-002) is exercised across every accept/decline path, plus the proven
absences (FR-007) and graceful degradation on an exhausted rate limit (FR-008). Synthetic page
titles and Commons filenames only — never library content (Constitution VI).
"""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from chronovista.models.wikipedia_image import FallbackOutcome
from chronovista.services.wikipedia_image_fallback import (
    USER_AGENT,
    WikipediaImageFallback,
)

pytestmark = pytest.mark.asyncio

_EID = UUID("00000000-0000-7000-8000-000000000001")
_QID = "Q000001"


def _transport(
    *,
    title: str | None = "Placeholder Person",
    lead_image: str | None = "Placeholder_Portrait.jpg",
    repository: str | None = "shared",
    non_free: bool = False,
    non_free_value: str = "1",
    imageinfo_present: bool = True,
    rate_limited: bool = False,
    transport_error: bool = False,
    error_body: bool = False,
    non_json: bool = False,
    legacy_empty_sitelinks: bool = False,
) -> httpx.MockTransport:
    """A Wikimedia transport whose responses are tuned by the gate scenario under test."""

    def respond(request: httpx.Request) -> httpx.Response:
        if transport_error:
            raise httpx.ConnectError("boom")
        if rate_limited:
            # Retry-After "0" keeps the bounded-retry test instant.
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        if non_json:
            # A 200 whose body is an HTML interstitial (proxy / CAPTCHA), not JSON.
            return httpx.Response(200, text="<html>not json</html>")
        if error_body:
            # MediaWiki's HTTP-200 error envelope (ratelimited, maxlag, bad params).
            return httpx.Response(200, json={"error": {"code": "ratelimited"}})
        url = str(request.url)
        params = request.url.params
        if "wikidata.org/w/api.php" in url:
            qid = params.get("ids")
            if title:
                ent: object = {"sitelinks": {"enwiki": {"title": title}}}
            elif legacy_empty_sitelinks:
                # Legacy JSON format serialises an empty associative array as [] (not {}).
                ent = {"sitelinks": []}
            else:
                ent = {}
            return httpx.Response(200, json={"entities": {qid: ent}})
        if "en.wikipedia.org/w/api.php" in url:
            prop = params.get("prop")
            if prop == "pageprops":
                pageprops = {"page_image_free": lead_image} if lead_image else {}
                return httpx.Response(
                    200,
                    json={
                        "query": {"pages": {"1": {"pageid": 1, "pageprops": pageprops}}}
                    },
                )
            if prop == "imageinfo":
                page: dict[str, object] = {"title": params.get("titles")}
                if repository is not None:
                    page["imagerepository"] = repository
                if imageinfo_present:
                    extmeta = {"NonFree": {"value": non_free_value}} if non_free else {}
                    page["imageinfo"] = [{"extmetadata": extmeta}]
                return httpx.Response(200, json={"query": {"pages": {"1": page}}})
        return httpx.Response(200, json={})

    return httpx.MockTransport(respond)


def _service(transport: httpx.MockTransport) -> WikipediaImageFallback:
    return WikipediaImageFallback(http=httpx.AsyncClient(transport=transport))


class TestUserAgent:
    """Wikimedia denies (403) a UA with no contact — the service reuses the compliant UA (FR-008)."""

    async def test_user_agent_identifies_tool_and_contact(self) -> None:
        assert "chronovista" in USER_AGENT
        assert (
            ("http://" in USER_AGENT)
            or ("https://" in USER_AGENT)
            or ("@" in USER_AGENT)
        )

    async def test_new_client_sends_the_user_agent(self) -> None:
        client = WikipediaImageFallback()._new_client()
        try:
            assert client.headers["User-Agent"] == USER_AGENT
        finally:
            await client.aclose()


class TestGate:
    """The FR-002 legal gate: store ONLY a Commons-hosted, not-non-free image."""

    async def test_accept_free_commons(self) -> None:
        result = await _service(_transport()).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.STORED
        assert result.filename == "Placeholder_Portrait.jpg"

    async def test_decline_non_free_on_commons(self) -> None:
        # A rare Commons-hosted file explicitly flagged non-free: honour the flag, store nothing.
        result = await _service(_transport(non_free=True)).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.DECLINED_NON_FREE
        assert result.filename is None

    async def test_decline_local_upload_not_on_commons(self) -> None:
        # imagerepository "local" = a fair-use upload local to English Wikipedia.
        result = await _service(_transport(repository="local")).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.DECLINED_NOT_COMMONS
        assert result.filename is None

    async def test_decline_unverifiable_absent_repository(self) -> None:
        # Hosting metadata cannot be obtained (no imagerepository) → declined conservatively.
        result = await _service(_transport(repository=None)).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.DECLINED_NON_FREE
        assert result.filename is None

    async def test_decline_unverifiable_missing_imageinfo(self) -> None:
        # Shared repository but no imageinfo block → cannot confirm non-free → conservative decline.
        result = await _service(
            _transport(repository="shared", imageinfo_present=False)
        ).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.DECLINED_NON_FREE


class TestAbsencesAndErrors:
    """Proven absences counted apart from failures (FR-007, FR-008)."""

    async def test_no_enwiki_page(self) -> None:
        result = await _service(_transport(title=None)).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.NO_PAGE

    async def test_no_lead_image(self) -> None:
        result = await _service(_transport(lead_image=None)).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.NO_LEAD_IMAGE

    async def test_rate_limited_past_budget_is_error_not_absence(self) -> None:
        result = await _service(_transport(rate_limited=True)).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.ERROR
        assert result.filename is None

    async def test_transport_failure_is_error(self) -> None:
        result = await _service(_transport(transport_error=True)).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.ERROR


class TestMalformedResponsesStayInsideBoundary:
    """Adversarial: real Wikimedia quirks must not crash or be miscounted (FR-007, FR-008)."""

    async def test_non_json_200_body_is_error_not_crash(self) -> None:
        # A 200 with an HTML interstitial body must resolve to ERROR, never escape evaluate().
        result = await _service(_transport(non_json=True)).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.ERROR

    async def test_api_error_envelope_is_error_not_absence(self) -> None:
        # HTTP 200 {"error": {...}} is a failure, NOT a proven absence — else it is settled
        # permanently as "no page" and never retried.
        result = await _service(_transport(error_body=True)).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.ERROR
        assert result.outcome is not FallbackOutcome.NO_PAGE

    async def test_legacy_empty_sitelinks_array_is_no_page_not_crash(self) -> None:
        # Legacy format returns "sitelinks": [] for a no-sitelink item; parse it as a genuine
        # absence (NO_PAGE), not an AttributeError that escapes the per-entity boundary.
        result = await _service(
            _transport(title=None, legacy_empty_sitelinks=True)
        ).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.NO_PAGE

    @pytest.mark.parametrize("encoding", ["true", "yes", "TRUE", "Yes"])
    async def test_non_free_alternate_encodings_still_decline(
        self, encoding: str
    ) -> None:
        # A NonFree flag encoded as "true"/"yes" (any case) must still decline — never STORED.
        result = await _service(
            _transport(non_free=True, non_free_value=encoding)
        ).evaluate(_EID, _QID)
        assert result.outcome is FallbackOutcome.DECLINED_NON_FREE
        assert result.filename is None
