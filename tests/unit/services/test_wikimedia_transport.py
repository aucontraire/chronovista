"""Branch-coverage tests for the shared ``WikimediaTransport`` (Feature 102, Phase B1, T007).

The external APIs are mocked via ``httpx.MockTransport`` injected at the ``http=`` seam, so the
real transport runs its real retry/backoff + parse/error contract against recorded RESPONSE
SHAPES. ``asyncio.sleep`` is monkeypatched to record (not incur) backoff waits, so the capping
behavior is asserted without real delay. Fixture values are neutral placeholders (Constitution VI).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from chronovista.services import wikimedia_transport as wt
from chronovista.services.wikimedia_transport import (
    WikidataUnavailable,
    WikimediaTransport,
    wikimedia_user_agent,
)

URL = "https://example.org/w/api.php"


def _client(handler: Any) -> httpx.AsyncClient:
    """An injected client whose transport replays ``handler``."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def recorded_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Capture every ``asyncio.sleep`` duration the transport requests, incurring none."""
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(wt.asyncio, "sleep", fake_sleep)
    return waits


class TestUserAgent:
    """G1: a single-sourced identity carrying product, version, contact, and component."""

    def test_user_agent_shape(self) -> None:
        ua = wikimedia_user_agent("dbpedia/sitelink resolver")
        assert ua.startswith("chronovista/")
        assert "github.com/aucontraire/chronovista" in ua
        assert ua.endswith(
            "(https://github.com/aucontraire/chronovista; " "dbpedia/sitelink resolver)"
        )

    def test_transport_sends_its_component_ua(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["ua"] = request.headers["User-Agent"]
            return httpx.Response(200, json={"ok": True})

        async def _run() -> None:
            async with _client(handler) as http:
                t = WikimediaTransport("category coverage fetch", http=http)
                await t.get_json(URL, params={})

        import asyncio

        asyncio.run(_run())
        assert seen["ua"] == wikimedia_user_agent("category coverage fetch")


class TestBackoff:
    """FR-003 / D6: one unified backoff — Retry-After honored but capped, else exponential."""

    pytestmark = pytest.mark.asyncio

    async def test_429_with_retry_after_then_success(
        self, recorded_sleeps: list[float]
    ) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, headers={"Retry-After": "3"}, json={})
            return httpx.Response(200, json={"ok": True})

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            data = await t.get_json(URL, params={})
        assert data == {"ok": True}
        assert recorded_sleeps == [3.0]  # honored the header verbatim (under the cap)

    async def test_429_retry_after_over_cap_is_capped(
        self, recorded_sleeps: list[float]
    ) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, headers={"Retry-After": "100"}, json={})
            return httpx.Response(200, json={"ok": True})

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            await t.get_json(URL, params={})
        assert recorded_sleeps == [10.0]  # capped at the unified maximum, not 100s

    async def test_429_without_retry_after_uses_exponential(
        self, recorded_sleeps: list[float]
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={})  # always 429 -> exhaust retries

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            with pytest.raises(WikidataUnavailable):
                await t.get_json(URL, params={})
        # 3 attempts -> two waits: base*2^0=1, base*2^1=2 (both under the cap).
        assert recorded_sleeps == [1.0, 2.0]

    async def test_5xx_retried_then_exhausted_raises(
        self, recorded_sleeps: list[float]
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={})

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            with pytest.raises(WikidataUnavailable):
                await t.get_json(URL, params={})
        assert recorded_sleeps == [1.0, 2.0]  # retried within the bounded budget

    async def test_transient_transport_error_is_retried_then_raises(
        self, recorded_sleeps: list[float]
    ) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.ConnectError("connection reset")  # always fails -> exhaust

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            with pytest.raises(WikidataUnavailable):
                await t.get_json(URL, params={})
        # A timeout/connection-reset (the DBpedia failure mode) is retried, not raised at once.
        assert calls["n"] == 3  # _MAX_ATTEMPTS
        assert recorded_sleeps == [1.0, 2.0]  # exponential, response-less

    async def test_transient_transport_error_then_success_recovers(
        self, recorded_sleeps: list[float]
    ) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ReadTimeout("slow upstream")
            return httpx.Response(200, json={"ok": True})

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            data = await t.get_json(URL, params={})
        assert data == {"ok": True}
        assert calls["n"] == 2
        assert recorded_sleeps == [1.0]  # one retry wait, then recovery

    async def test_non_transient_transport_error_raises_immediately(
        self, recorded_sleeps: list[float]
    ) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.UnsupportedProtocol("bad scheme")  # not transient

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            with pytest.raises(WikidataUnavailable):
                await t.get_json(URL, params={})
        assert calls["n"] == 1  # no retry — retrying a malformed request is pointless
        assert recorded_sleeps == []


class TestErrorVsEmpty:
    """FR-004 / FR-005 / D7: unreachable (raise) vs reached-but-empty (return)."""

    pytestmark = pytest.mark.asyncio

    async def test_non_json_200_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>maintenance</html>")

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            with pytest.raises(WikidataUnavailable):
                await t.get_json(URL, params={})

    async def test_error_object_in_200_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": {"code": "ratelimited"}})

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            with pytest.raises(WikidataUnavailable):
                await t.get_json(URL, params={})

    async def test_non_object_200_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[1, 2, 3])

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            with pytest.raises(WikidataUnavailable):
                await t.get_json(URL, params={})

    async def test_reached_but_empty_returns_data(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"search": []})

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            data = await t.get_json(URL, params={})
        assert data == {"search": []}  # confirmed absence, NOT an error

    async def test_post_form_shares_contract(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.headers["User-Agent"] == wikimedia_user_agent("sparql")
            assert request.headers["Accept"] == "application/json"
            return httpx.Response(200, json={"results": {"bindings": []}})

        async with _client(handler) as http:
            t = WikimediaTransport("sparql", http=http)
            data = await t.post_form(
                "https://dbpedia.org/sparql",
                data={"query": "SELECT 1"},
                headers={"Accept": "application/json"},
            )
        assert data == {"results": {"bindings": []}}


class TestChunk:
    """FR-007: one chunking helper, default 50."""

    def test_default_size_is_50(self) -> None:
        chunks = list(WikimediaTransport.chunk(list(range(120))))
        assert [len(c) for c in chunks] == [50, 50, 20]
        assert chunks[0][0] == 0 and chunks[-1][-1] == 119

    def test_custom_size(self) -> None:
        chunks = list(WikimediaTransport.chunk([1, 2, 3, 4, 5], size=2))
        assert chunks == [[1, 2], [3, 4], [5]]

    def test_empty(self) -> None:
        assert list(WikimediaTransport.chunk([])) == []

    def test_rejects_zero_size(self) -> None:
        with pytest.raises(ValueError):
            list(WikimediaTransport.chunk([1, 2], size=0))


class TestPaginateMediawiki:
    """FR-008: continuation, hop re-attribution, and the incomplete-raises bound."""

    pytestmark = pytest.mark.asyncio

    async def test_follows_continuation_and_merges(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    200,
                    json={
                        "query": {
                            "pages": {
                                "1": {
                                    "title": "Alpha",
                                    "categories": [{"title": "Category:One"}],
                                }
                            }
                        },
                        "continue": {"clcontinue": "1|More"},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "1": {
                                "title": "Alpha",
                                "categories": [{"title": "Category:Two"}],
                            }
                        }
                    }
                },
            )

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            out = await t.paginate_mediawiki(
                URL,
                params={"titles": "Alpha"},
                continue_key="clcontinue",
                max_pages=10,
            )
        assert calls["n"] == 2
        cats = [c["title"] for c in out["Alpha"]["categories"]]
        assert cats == ["Category:One", "Category:Two"]  # merged across pages

    async def test_multi_page_listing_returns_complete_set_reattributed(self) -> None:
        # SC-004, higher-level: a listing spanning 3+ continuation pages (4 requests) returns the
        # COMPLETE merged category list — not a truncated prefix — and, even though MediaWiki
        # resolved the requested "Old Name" to "New Name" via a redirect hop, the fully-drained
        # result is keyed by the caller's ORIGINAL title. This combines continuation-follow and
        # hop re-attribution over many pages; the sibling tests exercise each in isolation
        # (``test_follows_continuation_and_merges`` = 2 pages, no hop;
        # ``test_reattributes_redirect_hop_to_original_title`` = 1 page, hop).
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            n = calls["n"]
            page: dict[str, Any] = {
                "query": {
                    "pages": {
                        "9": {
                            "title": "New Name",
                            "categories": [{"title": f"Category:C{n}"}],
                        }
                    }
                }
            }
            if n == 1:
                # MediaWiki reports the redirect hop once, on the first response.
                page["query"]["redirects"] = [{"from": "Old Name", "to": "New Name"}]
            if n < 4:
                # Pages 1..3 issue a continuation token; page 4 terminates the drain.
                page["continue"] = {"clcontinue": f"9|{n}"}
            return httpx.Response(200, json=page)

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            out = await t.paginate_mediawiki(
                URL,
                params={"titles": "Old Name"},
                continue_key="clcontinue",
                max_pages=10,
            )
        assert (
            calls["n"] == 4
        )  # four pages drained (3 continuation hops + the final page)
        assert "Old Name" in out  # re-attributed to the caller's original title
        assert "New Name" not in out
        cats = [c["title"] for c in out["Old Name"]["categories"]]
        # The COMPLETE set across all four pages, in order — no silent truncation.
        assert cats == ["Category:C1", "Category:C2", "Category:C3", "Category:C4"]

    async def test_reattributes_redirect_hop_to_original_title(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # Requested "Old Name"; MediaWiki resolves it to "New Name" via a redirect hop.
            return httpx.Response(
                200,
                json={
                    "query": {
                        "redirects": [{"from": "Old Name", "to": "New Name"}],
                        "pages": {
                            "9": {
                                "title": "New Name",
                                "categories": [{"title": "Category:Kept"}],
                            }
                        },
                    }
                },
            )

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            out = await t.paginate_mediawiki(
                URL,
                params={"titles": "Old Name"},
                continue_key="clcontinue",
                max_pages=10,
            )
        # Keyed by the caller's original title, not the resolved one (the false-zero fix).
        assert "Old Name" in out
        assert "New Name" not in out

    async def test_missing_invalid_present_empty_and_unmappable_skipped(self) -> None:
        # Feature 102 fix (was test_missing_title_is_omitted): a REACHED batch returns an entry for
        # every requested title. A `missing`/`invalid` page now comes back PRESENT (present-empty,
        # no category list) — a reached-settled title, NOT omitted. Omission now means ONLY that the
        # batch was unreachable (raised). The lone page still skipped is one whose resolved title
        # maps to no requested original (a genuinely unmappable page — defensive).
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "-1": {"title": "Gone", "missing": ""},
                            "-2": {"title": "Bad", "invalid": ""},
                            "2": {"title": "Here", "categories": []},
                            "3": {  # maps to no requested original → skipped (defensive)
                                "title": "Unrequested",
                                "categories": [{"title": "Category:X"}],
                            },
                        }
                    }
                },
            )

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            out = await t.paginate_mediawiki(
                URL,
                params={"titles": "Gone|Bad|Here"},
                continue_key="clcontinue",
                max_pages=10,
            )
        # Missing + invalid are present-empty now (reached, nothing there) — not omitted.
        assert set(out) == {"Gone", "Bad", "Here"}  # Unrequested skipped (unmappable)
        assert (
            out["Gone"].get("categories") is None
        )  # present, carries no category list
        assert out["Bad"].get("categories") is None
        assert out["Here"].get("categories") == []  # present-empty (zero categories)

    async def test_exceeding_max_pages_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # Always issues a continue token -> never terminates on its own.
            return httpx.Response(
                200,
                json={
                    "query": {"pages": {"1": {"title": "Alpha", "categories": []}}},
                    "continue": {"clcontinue": "1|loop"},
                },
            )

        async with _client(handler) as http:
            t = WikimediaTransport("test", http=http)
            with pytest.raises(WikidataUnavailable):
                await t.paginate_mediawiki(
                    URL,
                    params={"titles": "Alpha"},
                    continue_key="clcontinue",
                    max_pages=3,
                )


class TestRunSync:
    """FR-018: a synchronous entry that owns its loop and is safe to call more than once."""

    def test_callable_twice_in_one_process(self) -> None:
        async def factory(transport: WikimediaTransport) -> int:
            assert isinstance(transport, WikimediaTransport)
            return 42

        t = WikimediaTransport("b2 script")
        assert t.run_sync(factory) == 42
        # A module-level shared client would bind to the first call's (now-closed) loop and
        # break here; a per-call loop + client does not.
        assert t.run_sync(factory) == 42
