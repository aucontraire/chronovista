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

from chronovista.services.entity_category_fetch import (
    _UA_COMPONENT,
    EntityCategoryFetchService,
)
from chronovista.services.wikimedia_transport import wikimedia_user_agent

pytestmark = pytest.mark.asyncio


def _service(
    handler: Callable[[httpx.Request], httpx.Response],
) -> EntityCategoryFetchService:
    # Inject a MockTransport-backed client via the shared transport's http= seam (Feature 102);
    # the service composes WikimediaTransport over it.
    return EntityCategoryFetchService(
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)), pause=0.0
    )


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
        assert seen[0]["redirects"] == [
            "1"
        ]  # follow redirect titles to the real article
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

    async def test_missing_title_is_present_empty_not_omitted(self) -> None:
        # Feature 102 fix (was test_missing_title_is_omitted): a reached batch returns every
        # requested title. A title Wikipedia reports `missing` now comes back present-empty
        # (reached-settled), NOT omitted — omission now means only that the batch was UNREACHABLE
        # (the transport raised), covered by the transport-error tests below.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_pages(
                    {"title": "Title_A", "categories": _cats("Category:cat-x")},
                    {"title": "Title_B", "missing": ""},
                ),
            )

        result = await _service(handler).categories_for_titles(["Title_A", "Title_B"])
        # Title_B present-empty (reached, nothing there), distinct from an omitted (unreachable) one.
        assert result == {"Title_A": ["cat-x"], "Title_B": []}

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

    async def test_redirect_title_maps_categories_back_to_input(self) -> None:
        # The Feature 084 redirect bug: the derived title is a redirect, so with redirects=1 the
        # response carries a normalized→redirect hop chain and a page keyed by the *resolved*
        # article title. The result must still be keyed by the caller's original input title, and
        # must carry the resolved article's categories (not an empty "processed-zero" list).
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "query": {
                        "normalized": [{"from": "Old_Name", "to": "Old Name"}],
                        "redirects": [{"from": "Old Name", "to": "New Name"}],
                        "pages": {
                            "1": {
                                "title": "New Name",
                                "categories": _cats("Category:cat-x", "Category:cat-y"),
                            }
                        },
                    }
                },
            )

        assert await _service(handler).categories_for_titles(["Old_Name"]) == {
            "Old_Name": ["cat-x", "cat-y"]
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

    async def test_non_advancing_continue_is_bounded_then_omitted(self) -> None:
        # A server echoing a non-advancing continuation token must not hang. Feature 102 changes
        # the degrade: exceeding _MAX_CONTINUATIONS now raises inside paginate_mediawiki (an
        # explicit incomplete signal, SC-004), which the service ABSORBS by omitting the whole
        # batch — never a silently truncated prefix presented as complete (the old behaviour
        # returned the partial set it had gathered).
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
        assert calls == 50  # _MAX_CONTINUATIONS pages fetched — does not hang
        assert (
            result == {}
        )  # incomplete batch omitted (retry later), not a truncated partial

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
            http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
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

    async def test_requests_carry_the_templated_user_agent(self) -> None:
        # Feature 102: the UA is single-sourced from the transport template with this service's
        # component label (was a hand-assembled ``chronovista/1.0 (...)`` literal), so it carries
        # the LIVE package version — an expected, documented flip from the old static "1.0".
        seen: dict[str, str | None] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["ua"] = request.headers.get("User-Agent")
            return httpx.Response(200, json=_pages())

        await _service(handler).categories_for_titles(["Title_A"])
        assert seen["ua"] == wikimedia_user_agent(_UA_COMPONENT)


class TestLanguageParameter:
    async def test_default_language_queries_english_wikipedia(self) -> None:
        hosts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            hosts.append(request.url.host)
            return httpx.Response(200, json=_pages())

        await _service(handler).categories_for_titles(["Title_A"])
        assert hosts == ["en.wikipedia.org"]

    async def test_language_switches_the_request_host(self) -> None:
        hosts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            hosts.append(request.url.host)
            return httpx.Response(
                200, json=_pages({"title": "Foo", "categories": _cats("Categoría:x")})
            )

        service = EntityCategoryFetchService(
            http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            pause=0.0,
            language="es",
        )
        await service.categories_for_titles(["Foo"])
        assert hosts == ["es.wikipedia.org"]


class TestWikibaseItemsForCategories:
    async def test_maps_titles_to_qids_and_omits_itemless(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            q = parse_qs(request.url.query.decode())
            assert q["prop"] == ["pageprops"]
            assert q["ppprop"] == ["wikibase_item"]
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "1": {
                                "title": "Categoría:A",
                                "pageprops": {"wikibase_item": "Q1"},
                            },
                            "2": {"title": "Categoría:B"},  # no wikibase_item → omitted
                        }
                    }
                },
            )

        result = await _service(handler).wikibase_items_for_categories(
            ["Categoría:A", "Categoría:B"]
        )
        assert result == {"Categoría:A": "Q1"}

    async def test_normalized_title_maps_back_to_caller_input(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "query": {
                        "normalized": [
                            {"from": "Categoría:A_B", "to": "Categoría:A B"}
                        ],
                        "pages": {
                            "1": {
                                "title": "Categoría:A B",
                                "pageprops": {"wikibase_item": "Q9"},
                            }
                        },
                    }
                },
            )

        assert await _service(handler).wikibase_items_for_categories(
            ["Categoría:A_B"]
        ) == {"Categoría:A_B": "Q9"}

    async def test_empty_input_makes_no_request(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        assert await _service(handler).wikibase_items_for_categories([]) == {}
        assert calls == 0
