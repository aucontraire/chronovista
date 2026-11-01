"""Unit tests for the shared entity→category coverage logic (Feature 084).

Covers title resolution (IRI-derived and QID-resolved, plus the no-resolvable-article skip,
SC-006/FR-002) and the shared store's safety invariant (a replace never deletes an entity's
categories down to nothing). All titles/category names are neutral placeholders (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.services import category_coverage as cc

pytestmark = pytest.mark.asyncio


class _FakeResolver:
    """Stand-in for DbpediaResolver.resolve(qid) -> (iri, provenance) | None."""

    def __init__(self, result: tuple[str, str] | None) -> None:
        self._result = result
        self.calls: list[str] = []

    async def resolve(self, qid: str) -> tuple[str, str] | None:
        self.calls.append(qid)
        return self._result


class TestTitleFromDbpediaIri:
    # async so the module-level asyncio mark (kept for pytest-cov) applies cleanly; the function
    # under test is synchronous.
    async def test_plain_resource_iri(self) -> None:
        assert (
            cc.title_from_dbpedia_iri("http://dbpedia.org/resource/Example_Title")
            == "Example_Title"
        )

    async def test_percent_encoded_is_unquoted(self) -> None:
        assert (
            cc.title_from_dbpedia_iri("http://dbpedia.org/resource/Caf%C3%A9_Bar")
            == "Café_Bar"
        )

    async def test_empty_or_non_resource_iri_is_none(self) -> None:
        assert cc.title_from_dbpedia_iri("") is None
        assert cc.title_from_dbpedia_iri("http://example.com/not-a-resource") is None

    async def test_resource_marker_with_empty_tail_is_none(self) -> None:
        assert cc.title_from_dbpedia_iri("http://dbpedia.org/resource/") is None


class TestResolveArticleTitle:
    async def test_prefers_stored_dbpedia_iri_without_calling_resolver(self) -> None:
        resolver = _FakeResolver(("http://dbpedia.org/resource/Other", "x"))
        external_ids = {"dbpedia": {"id": "http://dbpedia.org/resource/Stored_Title"}}

        title = await cc.resolve_article_title(external_ids, "Q1", resolver)

        assert title == "Stored_Title"
        assert resolver.calls == []  # the IRI short-circuits the QID resolution

    async def test_falls_back_to_qid_resolution_when_no_iri(self) -> None:
        resolver = _FakeResolver(
            ("http://dbpedia.org/resource/Resolved_Title", "enwiki sitelink")
        )

        title = await cc.resolve_article_title({}, "Q42", resolver)

        assert title == "Resolved_Title"
        assert resolver.calls == ["Q42"]

    async def test_no_iri_and_no_qid_is_skipped(self) -> None:
        # SC-006 / FR-002: an entity with neither a stored IRI nor a QID is skipped and
        # reported (None), not dropped silently and not retried — and the resolver is not called.
        resolver = _FakeResolver(("http://dbpedia.org/resource/Nope", "x"))

        assert await cc.resolve_article_title({}, None, resolver) is None
        assert resolver.calls == []

    async def test_qid_that_resolves_to_nothing_is_skipped(self) -> None:
        # SC-006: QID present but no owl:sameAs and no enwiki sitelink → skipped (None).
        resolver = _FakeResolver(None)

        assert await cc.resolve_article_title({}, "Q7", resolver) is None
        assert resolver.calls == ["Q7"]

    async def test_malformed_stored_iri_falls_through_to_qid(self) -> None:
        resolver = _FakeResolver(
            ("http://dbpedia.org/resource/From_Qid", "owl:sameAs from wikidata")
        )
        external_ids = {"dbpedia": {"id": "not-a-resource-iri"}}

        title = await cc.resolve_article_title(external_ids, "Q9", resolver)

        assert title == "From_Qid"
        assert resolver.calls == ["Q9"]


def _fake_cat_repo(names_missing_size: list[str]) -> MagicMock:
    repo = MagicMock()

    async def upsert(_session: Any, name: str) -> MagicMock:
        cat = MagicMock()
        cat.id = uuid.uuid4()
        cat.name = name
        return cat

    repo.upsert = AsyncMock(side_effect=upsert)
    repo.names_without_global_size = AsyncMock(return_value=names_missing_size)
    repo.set_global_size = AsyncMock()
    return repo


class TestStoreCategoriesForEntitySafety:
    async def test_replace_with_empty_names_never_deletes(self) -> None:
        # The safety invariant: a replace is never allowed to delete an entity's categories
        # down to nothing. Empty new set → total no-op; existing assignments kept.
        cat_repo = _fake_cat_repo([])
        assign_repo = MagicMock()
        assign_repo.delete_for_entity = AsyncMock()
        assign_repo.add = AsyncMock()

        await cc.store_categories_for_entity(
            MagicMock(),
            uuid.uuid4(),
            [],
            cat_repo=cat_repo,
            assign_repo=assign_repo,
            replace=True,
        )

        assign_repo.delete_for_entity.assert_not_awaited()
        assign_repo.add.assert_not_awaited()
        cat_repo.upsert.assert_not_awaited()

    async def test_replace_with_names_deletes_then_adds(self) -> None:
        cat_repo = _fake_cat_repo([])
        assign_repo = MagicMock()
        assign_repo.delete_for_entity = AsyncMock()
        assign_repo.add = AsyncMock()
        entity_id = uuid.uuid4()

        await cc.store_categories_for_entity(
            MagicMock(),
            entity_id,
            ["cat-x", "cat-y"],
            cat_repo=cat_repo,
            assign_repo=assign_repo,
            replace=True,
        )

        assign_repo.delete_for_entity.assert_awaited_once_with(
            assign_repo.delete_for_entity.await_args.args[0], entity_id
        )
        assert cat_repo.upsert.await_count == 2
        assert assign_repo.add.await_count == 2

    async def test_add_only_does_not_delete(self) -> None:
        cat_repo = _fake_cat_repo([])
        assign_repo = MagicMock()
        assign_repo.delete_for_entity = AsyncMock()
        assign_repo.add = AsyncMock()

        await cc.store_categories_for_entity(
            MagicMock(),
            uuid.uuid4(),
            ["cat-x"],
            cat_repo=cat_repo,
            assign_repo=assign_repo,
            replace=False,
        )

        assign_repo.delete_for_entity.assert_not_awaited()
        assert assign_repo.add.await_count == 1

    async def test_prefetched_sizes_are_applied_without_a_size_service(self) -> None:
        # The batch hands in pre-fetched sizes so no network happens in its write txn.
        cat_repo = _fake_cat_repo(["cat-x"])
        assign_repo = MagicMock()
        assign_repo.delete_for_entity = AsyncMock()
        assign_repo.add = AsyncMock()
        size_service = MagicMock()
        size_service.sizes_for = AsyncMock()

        await cc.store_categories_for_entity(
            MagicMock(),
            uuid.uuid4(),
            ["cat-x"],
            cat_repo=cat_repo,
            assign_repo=assign_repo,
            size_service=size_service,
            sizes={"cat-x": 42},
            replace=False,
        )

        size_service.sizes_for.assert_not_awaited()  # pre-fetched → no inline network
        cat_repo.set_global_size.assert_awaited_once()

    async def test_inline_size_service_used_when_no_prefetched_sizes(self) -> None:
        cat_repo = _fake_cat_repo(["cat-x"])
        assign_repo = MagicMock()
        assign_repo.delete_for_entity = AsyncMock()
        assign_repo.add = AsyncMock()
        size_service = MagicMock()
        size_service.sizes_for = AsyncMock(return_value={"cat-x": 7})

        await cc.store_categories_for_entity(
            MagicMock(),
            uuid.uuid4(),
            ["cat-x"],
            cat_repo=cat_repo,
            assign_repo=assign_repo,
            size_service=size_service,
            replace=False,
        )

        size_service.sizes_for.assert_awaited_once()
        cat_repo.set_global_size.assert_awaited_once()


class _TrackingSessionFactory:
    """A ``session_factory`` that records whether a session is currently open.

    Lets a test assert the Feature-094 invariant directly: ``categorize_entity`` must run ALL of
    its network (title resolution, the category fetch, the global-size pre-fetch) with NO DB
    session held, and only then open a short write session. A session held across a cancellable
    network await leaves an ``idle in transaction`` connection that deadlocks later DDL.
    """

    def __init__(self) -> None:
        self.is_open = False
        self.open_count = 0

    def __call__(self) -> _TrackingSessionFactory:
        return self

    async def __aenter__(self) -> MagicMock:
        self.is_open = True
        self.open_count += 1
        session = MagicMock()
        session.commit = AsyncMock()
        return session

    async def __aexit__(self, *exc: object) -> None:
        self.is_open = False


class TestCategorizeEntityHoldsNoSessionAcrossNetwork:
    async def test_network_runs_session_less_then_a_write_session_opens(self) -> None:
        # Encodes the 094 invariant as a regression guard: the fetch + size calls run with NO
        # factory session open; a session IS opened (once) for the write; and the behavior holds —
        # the resolved title is returned and the categories are stored (add-only).
        factory = _TrackingSessionFactory()

        class _AssertClosedFetch:
            def __init__(self) -> None:
                self.called = False

            async def categories_for_titles(self, titles: Any) -> dict[str, list[str]]:
                self.called = True
                assert (
                    factory.is_open is False
                ), "category fetch must run with NO DB session held (Feature 094)"
                return {"Stored_Title": ["cat-a", "cat-b"]}

        class _AssertClosedSizes:
            def __init__(self) -> None:
                self.called = False

            async def sizes_for(self, names: Any) -> dict[str, int]:
                self.called = True
                assert (
                    factory.is_open is False
                ), "size fetch must run with NO DB session held (Feature 094)"
                return {}

        fetch = _AssertClosedFetch()
        sizes = _AssertClosedSizes()
        cat_repo = _fake_cat_repo([])
        assign_repo = MagicMock()
        assign_repo.delete_for_entity = AsyncMock()
        assign_repo.add = AsyncMock()
        external_ids = {"dbpedia": {"id": "http://dbpedia.org/resource/Stored_Title"}}

        title = await cc.categorize_entity(
            uuid.uuid4(),
            None,
            external_ids,
            session_factory=factory,  # type: ignore[arg-type]
            fetch_service=fetch,  # type: ignore[arg-type]
            resolver=_FakeResolver(None),  # type: ignore[arg-type]
            cat_repo=cat_repo,
            assign_repo=assign_repo,
            size_service=sizes,  # type: ignore[arg-type]
            replace=False,
        )

        # The network actually ran (the assertions inside only bite if invoked) ...
        assert fetch.called and sizes.called
        # ... exactly one write session was opened, and it is closed again afterward ...
        assert factory.open_count == 1
        assert factory.is_open is False
        # ... and the behavior is intact: title returned, categories stored add-only.
        assert title == "Stored_Title"
        assert assign_repo.add.await_count == 2
        assign_repo.delete_for_entity.assert_not_awaited()
