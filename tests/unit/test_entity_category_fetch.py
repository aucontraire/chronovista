"""Unit tests for EntityCategoryFetchService (Feature 084). No live network.

The entity→categories fetch: given article titles, return each one's non-hidden Wikipedia
category names. All titles/category names here are neutral placeholders (Constitution VI).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from chronovista.services.entity_category_fetch import EntityCategoryFetchService

pytestmark = pytest.mark.asyncio


def _service(
    handler: Callable[[httpx.Request], httpx.Response],
) -> EntityCategoryFetchService:
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return EntityCategoryFetchService(client_factory=factory, pause=0.0)


def _cats(*titles: str) -> list[dict[str, str]]:
    return [{"title": t} for t in titles]


def _pages(*pages: dict[str, Any]) -> dict[str, Any]:
    return {"query": {"pages": {str(i): p for i, p in enumerate(pages)}}}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant)


class TestCategoriesForTitles:
    async def test_returns_non_hidden_category_names(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_pages(
                    {
                        "title": "Title_A",
                        "categories": _cats("Category:cat-x", "Category:cat-y"),
                    }
                ),
            )

        result = await _service(handler).categories_for_titles(["Title_A"])
        assert result == {"Title_A": ["cat-x", "cat-y"]}

    async def test_request_carries_prop_and_clshow_hidden(self) -> None:
        seen: list[dict[str, list[str]]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(parse_qs(request.url.query.decode()))
            return httpx.Response(200, json=_pages())

        await _service(handler).categories_for_titles(["Title_A", "Title_B", "Title_A"])
        assert len(seen) == 1  # de-duplicated to one batch
        assert seen[0]["prop"] == ["categories"]
        assert seen[0]["clshow"] == [
            "!hidden"
        ]  # hidden categories excluded at the source
        assert seen[0]["titles"] == ["Title_A|Title_B"]

    async def test_seen_title_with_zero_categories_is_empty_list_not_omitted(
        self,
    ) -> None:
        # A page that exists but has no non-hidden categories → present with [] (processed, zero),
        # distinct from a fetch failure (which omits the title).
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_pages({"title": "Title_A"}))

        assert await _service(handler).categories_for_titles(["Title_A"]) == {
            "Title_A": []
        }

    async def test_missing_title_is_omitted(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_pages(
                    {"title": "Title_A", "categories": _cats("Category:cat-x")},
                    {"title": "Title_B", "missing": ""},
                ),
            )

        result = await _service(handler).categories_for_titles(["Title_A", "Title_B"])
        assert result == {"Title_A": ["cat-x"]}  # Title_B omitted (retry later)

    async def test_title_matching_ignores_underscore_and_case(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_pages(
                    {"title": "Foo Bar", "categories": _cats("Category:cat-x")}
                ),
            )

        # Key is the caller's exact input, not Wikipedia's canonicalized form.
        assert await _service(handler).categories_for_titles(["Foo_Bar"]) == {
            "Foo_Bar": ["cat-x"]
        }

    async def test_continue_token_accumulates_pages(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    200,
                    json={
                        "query": {
                            "pages": {
                                "1": {
                                    "title": "Title_A",
                                    "categories": _cats("Category:cat-x"),
                                }
                            }
                        },
                        "continue": {"clcontinue": "A|next", "continue": "||"},
                    },
                )
            return httpx.Response(
                200,
                json=_pages(
                    {"title": "Title_A", "categories": _cats("Category:cat-y")}
                ),
            )

        result = await _service(handler).categories_for_titles(["Title_A"])
        assert calls == 2
        assert result == {"Title_A": ["cat-x", "cat-y"]}

    async def test_non_advancing_continue_is_bounded(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "1": {
                                "title": "Title_A",
                                "categories": _cats("Category:cat-x"),
                            }
                        }
                    },
                    "continue": {"clcontinue": "STUCK", "continue": "||"},
                },
            )

        result = await asyncio.wait_for(
            _service(handler).categories_for_titles(["Title_A"]), timeout=5
        )
        assert calls == 50  # _MAX_CONTINUATIONS — does not hang
        assert result["Title_A"]  # whatever it gathered before the cap

    async def test_http_error_yields_omission_without_raising(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500)

        result = await _service(handler).categories_for_titles(["Title_A"])
        assert result == {}  # omitted, not raised
        assert calls == 3  # bounded retries

    async def test_transport_error_yields_omission(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        assert await _service(handler).categories_for_titles(["Title_A"]) == {}

    async def test_more_than_fifty_titles_are_batched(self) -> None:
        batch_sizes: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            titles = parse_qs(request.url.query.decode())["titles"][0].split("|")
            batch_sizes.append(len(titles))
            return httpx.Response(200, json=_pages())

        await _service(handler).categories_for_titles(
            [f"Title_{i}" for i in range(120)]
        )
        assert batch_sizes == [50, 50, 20]

    async def test_pauses_between_batches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[float] = []

        async def record(delay: float) -> None:
            calls.append(delay)

        monkeypatch.setattr(asyncio, "sleep", record)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_pages())

        service = EntityCategoryFetchService(
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ),
            pause=1.5,
        )
        # 120 titles -> 3 batches -> exactly 2 inter-batch pauses (no retries, no continue).
        await service.categories_for_titles([f"Title_{i}" for i in range(120)])
        assert calls == [1.5, 1.5]

    async def test_non_dict_json_and_pages_yield_empty(self) -> None:
        bodies: list[Any] = [[1, 2], {"query": {"pages": [1]}}, {}]
        for body in bodies:

            def handler(request: httpx.Request, b: Any = body) -> httpx.Response:
                return httpx.Response(200, json=b)

            assert await _service(handler).categories_for_titles(["Title_A"]) == {}

    async def test_default_client_factory_sets_user_agent(self) -> None:
        service = EntityCategoryFetchService(timeout=1.0)
        client = service._new_client()
        try:
            assert "chronovista" in client.headers["User-Agent"]
        finally:
            await client.aclose()
