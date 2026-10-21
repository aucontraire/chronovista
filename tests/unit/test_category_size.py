"""Unit tests for CategorySizeService (Feature 083). No live network."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from chronovista.services.category_size import CategorySizeService

pytestmark = pytest.mark.asyncio


def _service(handler: Callable[[httpx.Request], httpx.Response]) -> CategorySizeService:
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return CategorySizeService(client_factory=factory)


def _pages(*pages: dict[str, Any]) -> dict[str, Any]:
    return {"query": {"pages": {str(i): p for i, p in enumerate(pages)}}}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant)


class TestSizesFor:
    async def test_batch_returns_name_to_size(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_pages(
                    {"title": "Category:cat-x", "categoryinfo": {"size": 12}},
                    {"title": "Category:cat-y", "categoryinfo": {"size": 3400}},
                ),
            )

        result = await _service(handler).sizes_for(["cat-x", "cat-y"])
        assert result == {"cat-x": 12, "cat-y": 3400}

    async def test_request_carries_prefixed_titles_and_categoryinfo_prop(self) -> None:
        seen: list[dict[str, list[str]]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(parse_qs(request.url.query.decode()))
            return httpx.Response(200, json=_pages())

        await _service(handler).sizes_for(["cat-x", "cat-y", "cat-x"])
        assert len(seen) == 1
        assert seen[0]["prop"] == ["categoryinfo"]
        assert seen[0]["titles"] == ["Category:cat-x|Category:cat-y"]

    async def test_title_matching_ignores_underscore_and_case(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_pages({"title": "Category:Foo Bar", "categoryinfo": {"size": 7}}),
            )

        result = await _service(handler).sizes_for(["Foo_Bar"])
        # Keys are the caller's exact input, not Wikipedia's canonical form.
        assert result == {"Foo_Bar": 7}

        result_case = await _service(handler).sizes_for(["foo_BAR"])
        assert result_case == {"foo_BAR": 7}

    async def test_missing_categoryinfo_is_omitted(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_pages(
                    {"title": "Category:cat-x", "categoryinfo": {"size": 5}},
                    {"title": "Category:cat-y", "missing": ""},
                ),
            )

        result = await _service(handler).sizes_for(["cat-x", "cat-y"])
        assert result == {"cat-x": 5}

    async def test_unrequested_title_is_ignored(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_pages({"title": "Category:other", "categoryinfo": {"size": 1}}),
            )

        assert await _service(handler).sizes_for(["cat-x"]) == {}

    async def test_title_without_prefix_still_matches(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json=_pages({"title": "cat-x", "categoryinfo": {"size": 2}})
            )

        assert await _service(handler).sizes_for(["cat-x"]) == {"cat-x": 2}

    async def test_http_error_yields_empty_without_raising(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500)

        result = await _service(handler).sizes_for(["cat-x"])
        assert result == {}
        assert calls == 3  # bounded retries

    async def test_transport_error_yields_empty(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        assert await _service(handler).sizes_for(["cat-x"]) == {}

    async def test_transient_failure_then_success(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503)
            return httpx.Response(
                200,
                json=_pages({"title": "Category:cat-x", "categoryinfo": {"size": 9}}),
            )

        assert await _service(handler).sizes_for(["cat-x"]) == {"cat-x": 9}

    async def test_non_dict_json_and_pages_yield_empty(self) -> None:
        bodies: list[Any] = [[1, 2], {"query": {"pages": [1]}}, {}]
        for body in bodies:

            def handler(request: httpx.Request, b: Any = body) -> httpx.Response:
                return httpx.Response(200, json=b)

            assert await _service(handler).sizes_for(["cat-x"]) == {}

    async def test_more_than_fifty_names_are_batched(self) -> None:
        sizes: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            titles = parse_qs(request.url.query.decode())["titles"][0].split("|")
            sizes.append(len(titles))
            return httpx.Response(200, json=_pages())

        await _service(handler).sizes_for([f"cat-{i}" for i in range(120)])
        assert sizes == [50, 50, 20]

    async def test_pauses_between_batches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[float] = []

        async def record(delay: float) -> None:
            calls.append(delay)

        monkeypatch.setattr(asyncio, "sleep", record)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_pages())

        service = CategorySizeService(
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ),
            pause=1.5,
        )
        # 120 names -> 3 batches -> exactly 2 inter-batch pauses (no retries here).
        await service.sizes_for([f"cat-{i}" for i in range(120)])
        assert calls == [1.5, 1.5]

    async def test_pause_zero_means_no_inter_batch_sleep(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[float] = []

        async def record(delay: float) -> None:
            calls.append(delay)

        monkeypatch.setattr(asyncio, "sleep", record)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_pages())

        service = CategorySizeService(
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ),
            pause=0.0,
        )
        await service.sizes_for([f"cat-{i}" for i in range(60)])  # 2 batches
        assert calls == []

    async def test_default_client_factory_sets_user_agent(self) -> None:
        service = CategorySizeService(timeout=1.0)
        client = service._new_client()
        try:
            assert "chronovista" in client.headers["User-Agent"]
        finally:
            await client.aclose()
