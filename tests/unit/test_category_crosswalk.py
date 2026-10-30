"""Unit tests for the Feature 100 foreign-language category cross-walk. No live network.

The cross-walk maps a foreign category to English via its own Wikidata item's enwiki sitelink,
unioned across every language an entity has. All article titles / category names here are neutral
placeholders (Constitution VI).
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import parse_qs

import httpx
import pytest

from chronovista.services.category_coverage import (
    crosswalk_foreign_categories,
    resolve_and_crosswalk_entity,
)
from chronovista.services.entity_category_fetch import EntityCategoryFetchService
from chronovista.services.wikidata_client import WikidataClient

pytestmark = pytest.mark.asyncio


class _FakeFetch:
    """Stub category-fetch service: canned category lists and category→QID maps for one language."""

    def __init__(
        self,
        cats: dict[str, list[str]] | None = None,
        cat_qids: dict[str, str] | None = None,
    ) -> None:
        self._cats = cats or {}
        self._cat_qids = cat_qids or {}

    async def categories_for_titles(
        self, titles: Iterable[str]
    ) -> dict[str, list[str]]:
        return {t: self._cats.get(t, []) for t in titles}

    async def wikibase_items_for_categories(
        self, titles: Iterable[str]
    ) -> dict[str, str]:
        return {t: self._cat_qids[t] for t in titles if t in self._cat_qids}


class _FakeWikidata:
    """Stub WikidataClient: canned ``{qid: {dbname: title}}`` sitelinks."""

    def __init__(self, sitelinks: dict[str, dict[str, str]]) -> None:
        self._sitelinks = sitelinks

    async def fetch_sitelinks(self, qids: list[str]) -> dict[str, dict[str, str]]:
        return {q: self._sitelinks.get(q, {}) for q in qids}


class TestCrosswalkForeignCategories:
    async def test_union_dedups_same_english_across_languages(self) -> None:
        def factory(lang: str) -> _FakeFetch:
            return (
                _FakeFetch(cat_qids={"Categoría:A": "Q1"})
                if lang == "es"
                else _FakeFetch(cat_qids={"Catégorie:B": "Q2"})
            )

        wd = _FakeWikidata(
            {"Q1": {"enwiki": "Category:X"}, "Q2": {"enwiki": "Category:X"}}
        )
        res = await crosswalk_foreign_categories(
            {"es": ["Categoría:A"], "fr": ["Catégorie:B"]},
            fetch_factory=factory,  # type: ignore[arg-type]
            wikidata_client=wd,  # type: ignore[arg-type]
        )
        assert res.english_categories == ["X"]
        assert sorted(res.source_langs_by_category["X"]) == ["es", "fr"]
        assert res.dropped_count == 0

    async def test_drops_category_with_no_wikidata_item(self) -> None:
        def factory(lang: str) -> _FakeFetch:
            return _FakeFetch(cat_qids={"Categoría:A": "Q1"})  # B has no item

        wd = _FakeWikidata({"Q1": {"enwiki": "Category:X"}})
        res = await crosswalk_foreign_categories(
            {"es": ["Categoría:A", "Categoría:B"]},
            fetch_factory=factory,  # type: ignore[arg-type]
            wikidata_client=wd,  # type: ignore[arg-type]
        )
        assert res.english_categories == ["X"]
        assert res.dropped_count == 1

    async def test_drops_item_with_no_enwiki_sitelink(self) -> None:
        def factory(lang: str) -> _FakeFetch:
            return _FakeFetch(cat_qids={"Categoría:A": "Q1", "Categoría:B": "Q2"})

        wd = _FakeWikidata(
            {"Q1": {"enwiki": "Category:X"}, "Q2": {"frwiki": "Catégorie:Y"}}
        )
        res = await crosswalk_foreign_categories(
            {"es": ["Categoría:A", "Categoría:B"]},
            fetch_factory=factory,  # type: ignore[arg-type]
            wikidata_client=wd,  # type: ignore[arg-type]
        )
        assert res.english_categories == ["X"]
        assert res.dropped_count == 1


class TestResolveAndCrosswalkEntity:
    async def test_returns_none_when_entity_has_english_article(self) -> None:
        wd = _FakeWikidata({"Q100": {"enwiki": "Foo", "eswiki": "Foo es"}})
        res = await resolve_and_crosswalk_entity(
            "Q100",
            wikidata_client=wd,  # type: ignore[arg-type]
            fetch_factory=lambda lang: _FakeFetch(),  # type: ignore[arg-type]
        )
        assert res is None

    async def test_returns_none_when_no_foreign_article(self) -> None:
        wd = _FakeWikidata({"Q100": {}})
        res = await resolve_and_crosswalk_entity(
            "Q100",
            wikidata_client=wd,  # type: ignore[arg-type]
            fetch_factory=lambda lang: _FakeFetch(),  # type: ignore[arg-type]
        )
        assert res is None

    async def test_recovered_zero_when_nothing_crosswalks(self) -> None:
        wd = _FakeWikidata({"Q100": {"eswiki": "Art es"}})

        def factory(lang: str) -> _FakeFetch:
            return _FakeFetch(cats={"Art es": ["Categoría:Z"]}, cat_qids={})

        res = await resolve_and_crosswalk_entity(
            "Q100",
            wikidata_client=wd,  # type: ignore[arg-type]
            fetch_factory=factory,  # type: ignore[arg-type]
        )
        assert res is not None
        assert res.english_categories == []
        assert res.dropped_count == 1

    async def test_crosswalks_foreign_only_entity_across_languages(self) -> None:
        wd = _FakeWikidata(
            {
                "Q100": {"l1wiki": "Art L1", "l2wiki": "Art L2"},
                "Q1": {"enwiki": "Category:Cat_X"},
                "Q2": {"enwiki": "Category:Cat_Y"},
            }
        )

        def factory(lang: str) -> _FakeFetch:
            if lang == "l1":
                return _FakeFetch(
                    cats={"Art L1": ["Cat_L1:Alpha"]},
                    cat_qids={"Cat_L1:Alpha": "Q1"},
                )
            return _FakeFetch(
                cats={"Art L2": ["Cat_L2:Beta"]},
                cat_qids={"Cat_L2:Beta": "Q2"},
            )

        res = await resolve_and_crosswalk_entity(
            "Q100",
            wikidata_client=wd,  # type: ignore[arg-type]
            fetch_factory=factory,  # type: ignore[arg-type]
        )
        assert res is not None
        assert sorted(res.english_categories) == ["Cat_X", "Cat_Y"]
        assert res.dropped_count == 0


class TestWikidataClientFetchSitelinksSeam:
    """Cross the real WikidataClient HTTP seam (not a mock) for the sitelink filter."""

    async def test_fetch_sitelinks_keeps_wikipedia_drops_sister_projects(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "entities": {
                        "Q1": {
                            "sitelinks": {
                                "enwiki": {"title": "Category:X"},
                                "eswiki": {"title": "Categoría:X"},
                                "commonswiki": {"title": "Category:Y"},
                            }
                        }
                    }
                },
            )

        client = WikidataClient(
            http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        out = await client.fetch_sitelinks(["Q1"])
        assert out == {"Q1": {"enwiki": "Category:X", "eswiki": "Categoría:X"}}


class TestEndToEndRealSeams:
    """Drive resolve_and_crosswalk_entity through the REAL fetch + Wikidata clients (MockTransport),
    so the dbname→host derivation is exercised end-to-end (a stub keyed by an opaque lang cannot).
    """

    async def test_hyphenated_language_dbname_builds_hyphenated_host(self) -> None:
        wiki_hosts: list[str] = []

        def wiki_handler(request: httpx.Request) -> httpx.Response:
            wiki_hosts.append(request.url.host)
            q = parse_qs(request.url.query.decode())
            if q.get("prop") == ["categories"]:
                return httpx.Response(
                    200,
                    json={
                        "query": {
                            "pages": {
                                "1": {
                                    "title": q["titles"][0],
                                    "categories": [{"title": "Cat_L1:Alpha"}],
                                }
                            }
                        }
                    },
                )
            return httpx.Response(  # pageprops
                200,
                json={
                    "query": {
                        "pages": {
                            "1": {
                                "title": "Cat_L1:Alpha",
                                "pageprops": {"wikibase_item": "Q1"},
                            }
                        }
                    }
                },
            )

        def wd_handler(request: httpx.Request) -> httpx.Response:
            ids = parse_qs(request.url.query.decode())["ids"][0]
            if ids == "Q100":  # the entity: a hyphenated-language-only sitelink
                return httpx.Response(
                    200,
                    json={
                        "entities": {
                            "Q100": {"sitelinks": {"zh_yuewiki": {"title": "Art"}}}
                        }
                    },
                )
            return httpx.Response(  # the category item
                200,
                json={
                    "entities": {
                        "Q1": {"sitelinks": {"enwiki": {"title": "Category:Cat_X"}}}
                    }
                },
            )

        def factory(lang: str) -> EntityCategoryFetchService:
            return EntityCategoryFetchService(
                client_factory=lambda: httpx.AsyncClient(
                    transport=httpx.MockTransport(wiki_handler)
                ),
                pause=0.0,
                language=lang,
            )

        wd = WikidataClient(
            http=httpx.AsyncClient(transport=httpx.MockTransport(wd_handler))
        )
        res = await resolve_and_crosswalk_entity(
            "Q100", wikidata_client=wd, fetch_factory=factory
        )
        assert res is not None
        assert res.english_categories == ["Cat_X"]
        # The dbname zh_yuewiki must resolve to the hyphenated host, not the underscore one.
        assert "zh-yue.wikipedia.org" in wiki_hosts
        assert "zh_yue.wikipedia.org" not in wiki_hosts
