"""Real-database seam tests for entity→category coverage (Feature 084).

Exercises the shared add path (``categorize_entity``) against the real integration DB with the
Wikipedia fetch stubbed, and verifies the Cross-Feature Data Contract: the mutation is visible by
reading **through** Feature 083's shared-category bridge, not merely by asserting rows changed.
All titles/category names are neutral placeholders (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import EntityCategory, NamedEntity
from chronovista.repositories.entity_category_repository import EntityCategoryRepository
from chronovista.repositories.wikipedia_category_repository import (
    WikipediaCategoryRepository,
)
from chronovista.services import category_coverage as cc
from chronovista.services.category_size import CategorySizeService
from chronovista.services.entity_enrichment_service import EntityEnrichmentService

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

cat_repo = WikipediaCategoryRepository()
assign_repo = EntityCategoryRepository()


class _StubFetch:
    """Stand-in for EntityCategoryFetchService: returns a preset title→categories map."""

    def __init__(self, preset: dict[str, list[str]]) -> None:
        self._preset = preset
        self.calls: list[list[str]] = []

    async def categories_for_titles(self, titles: Any) -> dict[str, list[str]]:
        requested = list(titles)
        self.calls.append(requested)
        return {t: self._preset[t] for t in requested if t in self._preset}


class _StubSizes(CategorySizeService):
    """CategorySizeService that returns no sizes (new categories keep NULL global_size)."""

    def __init__(self) -> None:
        super().__init__()

    async def sizes_for(self, names: Any) -> dict[str, int]:
        return {}


class _NoResolver:
    """Resolver that must not be called — these entities carry a stored DBpedia IRI."""

    async def resolve(self, qid: str) -> tuple[str, str] | None:  # pragma: no cover
        raise AssertionError(
            "resolver should not be called when a stored IRI is present"
        )


def _u(value: object) -> uuid.UUID:
    return uuid.UUID(str(value))


async def _uncategorized_entity(
    session: AsyncSession, name: str, title: str
) -> uuid.UUID:
    """Seed a grounded entity with a resolvable article (stored IRI) and no categories."""
    entity = NamedEntity(
        canonical_name=name,
        canonical_name_normalized=name.lower(),
        entity_type="person",
        external_ids={
            "wikidata": {"id": f"Q{abs(hash(name)) % 100000}"},
            "dbpedia": {"id": f"http://dbpedia.org/resource/{title}"},
        },
    )
    session.add(entity)
    await session.flush()
    return entity.id


async def _assignments_for(session: AsyncSession, entity_id: uuid.UUID) -> list[str]:
    rows = await session.execute(
        select(EntityCategory.source).where(EntityCategory.entity_id == entity_id)
    )
    return list(rows.scalars().all())


async def _run_add(
    session: AsyncSession,
    entity_id: uuid.UUID,
    external_ids: dict[str, Any],
    fetch: _StubFetch,
) -> str | None:
    # These entities resolve via their stored DBpedia IRI, so the QID is unused here (None).
    return await cc.categorize_entity(
        session,
        entity_id,
        None,
        external_ids,
        fetch_service=fetch,  # type: ignore[arg-type]
        resolver=_NoResolver(),  # type: ignore[arg-type]
        cat_repo=cat_repo,
        assign_repo=assign_repo,
        size_service=_StubSizes(),
        replace=False,
    )


class TestAddPathThroughBridge:
    async def test_backfilled_entities_become_bridge_neighbors(
        self, db_session: AsyncSession
    ) -> None:
        # Two previously un-categorized entities that will share one category.
        a_ext = {"dbpedia": {"id": "http://dbpedia.org/resource/Title_A"}}
        b_ext = {"dbpedia": {"id": "http://dbpedia.org/resource/Title_B"}}
        a = await _uncategorized_entity(db_session, "Entity A", "Title_A")
        b = await _uncategorized_entity(db_session, "Entity B", "Title_B")
        fetch = _StubFetch(
            {
                "Title_A": ["cat-shared", "cat-a-only"],
                "Title_B": ["cat-shared", "cat-b-only"],
            }
        )

        # Before: the bridge sees nothing for A (no categories yet).
        assert await assign_repo.shared_category_bridge(db_session, a) == []

        await _run_add(db_session, a, a_ext, fetch)
        await _run_add(db_session, b, b_ext, fetch)

        # All written assignments are the one Wikipedia namespace (FR-007).
        assert set(await _assignments_for(db_session, a)) == {"wikipedia"}
        assert set(await _assignments_for(db_session, b)) == {"wikipedia"}

        # Cross-Feature contract: read THROUGH the 083 bridge — A now neighbors B via cat-shared.
        neighbors = await assign_repo.shared_category_bridge(db_session, a)
        assert (_u(b), "cat-shared") in {
            (_u(n.neighbor_id), n.shared_category) for n in neighbors
        }
        # cat-a-only / cat-b-only are not shared, so they produce no neighbor edge.
        assert all(n.shared_category == "cat-shared" for n in neighbors)

    async def test_add_path_is_idempotent(self, db_session: AsyncSession) -> None:
        ext = {"dbpedia": {"id": "http://dbpedia.org/resource/Title_C"}}
        c = await _uncategorized_entity(db_session, "Entity C", "Title_C")
        fetch = _StubFetch({"Title_C": ["cat-x", "cat-y"]})

        await _run_add(db_session, c, ext, fetch)
        first = (
            await db_session.execute(
                select(func.count())
                .select_from(EntityCategory)
                .where(EntityCategory.entity_id == c)
            )
        ).scalar_one()

        await _run_add(
            db_session, c, ext, fetch
        )  # second run — add is ON CONFLICT DO NOTHING
        second = (
            await db_session.execute(
                select(func.count())
                .select_from(EntityCategory)
                .where(EntityCategory.entity_id == c)
            )
        ).scalar_one()

        assert first == 2
        assert second == 2  # no duplicate assignments

    async def test_unresolvable_article_writes_nothing(
        self, db_session: AsyncSession
    ) -> None:
        # No stored IRI and the resolver yields nothing → skipped (SC-006), no rows written.
        entity = NamedEntity(
            canonical_name="Entity D",
            canonical_name_normalized="entity d",
            entity_type="person",
            external_ids={"wikidata": {"id": "Q999999"}},
        )
        db_session.add(entity)
        await db_session.flush()

        class _ResolvesNothing:
            async def resolve(self, qid: str) -> tuple[str, str] | None:
                return None

        title = await cc.categorize_entity(
            db_session,
            entity.id,
            "Q999999",
            {"wikidata": {"id": "Q999999"}},
            fetch_service=_StubFetch({}),  # type: ignore[arg-type]
            resolver=_ResolvesNothing(),  # type: ignore[arg-type]
            cat_repo=cat_repo,
            assign_repo=assign_repo,
            size_service=_StubSizes(),
            replace=False,
        )

        assert title is None
        assert await _assignments_for(db_session, entity.id) == []


# --- US2: on-approval seam (real enrich_on_approval over the real DB) ---------------------


class _OkWikidataClient:
    """Minimal Wikidata client stub: returns one curated property block (no live call)."""

    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        return {"occupation": {"values": ["x"], "qids": [], "source": "wikidata"}}


class _LinkResolver:
    """Resolves the QID to a DBpedia IRI so a title resolves for the category step."""

    async def resolve(self, qid: str) -> tuple[str, str] | None:
        return "http://dbpedia.org/resource/Title_Seam", "owl:sameAs from wikidata"


class _SeamFetch:
    def __init__(self, result: dict[str, list[str]] | None = None) -> None:
        self._result = result

    async def categories_for_titles(self, titles: Any) -> dict[str, list[str]]:
        if self._result is None:
            raise RuntimeError("category fetch unavailable")
        return {t: self._result.get(t, []) for t in titles}


async def _ground_new_entity(session: AsyncSession, qid: str) -> uuid.UUID:
    entity = NamedEntity(
        canonical_name=f"Seam {uuid.uuid4().hex[:8]}",
        canonical_name_normalized=f"seam {uuid.uuid4().hex[:8]}",
        entity_type="person",
        status="active",
        external_ids={"wikidata": {"id": qid, "verified": True, "status": "verified"}},
        properties={},
    )
    session.add(entity)
    await session.commit()
    return uuid.UUID(str(entity.id))


class TestOnApprovalCategorizes:
    async def test_new_entity_carries_categories_after_approval(
        self, db_session: AsyncSession
    ) -> None:
        qid = "Q000501"
        entity_id = await _ground_new_entity(db_session, qid)
        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
        service = EntityEnrichmentService(
            factory,
            client_factory=lambda: _OkWikidataClient(),
            dbpedia_factory=lambda: _LinkResolver(),
            category_fetch_factory=lambda: _SeamFetch(
                {"Title_Seam": ["cat-seam-a", "cat-seam-b"]}
            ),
            size_factory=lambda: _StubSizes(),
        )

        await service.enrich_on_approval(entity_id, qid)

        async with factory() as s2:
            sources = (
                (
                    await s2.execute(
                        select(EntityCategory.source).where(
                            EntityCategory.entity_id == entity_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert sorted(sources) == [
            "wikipedia",
            "wikipedia",
        ]  # both added, one namespace

    async def test_category_fetch_failure_leaves_entity_grounded(
        self, db_session: AsyncSession
    ) -> None:
        qid = "Q000502"
        entity_id = await _ground_new_entity(db_session, qid)
        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
        service = EntityEnrichmentService(
            factory,
            client_factory=lambda: _OkWikidataClient(),
            dbpedia_factory=lambda: _LinkResolver(),
            category_fetch_factory=lambda: _SeamFetch(None),  # raises on fetch
            size_factory=lambda: _StubSizes(),
        )

        # Must not raise despite the category fetch blowing up (best-effort, FR-004).
        await service.enrich_on_approval(entity_id, qid)

        async with factory() as s2:
            row = (
                await s2.execute(select(NamedEntity).where(NamedEntity.id == entity_id))
            ).scalar_one()
            # Entity stays grounded and its PRIMARY enrichment (properties) landed intact.
            assert "occupation" in row.properties
            assert row.external_ids["wikidata"]["id"] == qid
            n_assigned = (
                await s2.execute(
                    select(func.count())
                    .select_from(EntityCategory)
                    .where(EntityCategory.entity_id == entity_id)
                )
            ).scalar_one()
            assert n_assigned == 0  # the failed category step wrote nothing


# --- US3: the 373 replace (DBpedia → Wikipedia) through the bridge --------------------------


async def _plain_entity(session: AsyncSession, name: str) -> uuid.UUID:
    entity = NamedEntity(
        canonical_name=name,
        canonical_name_normalized=name.lower(),
        entity_type="person",
    )
    session.add(entity)
    await session.flush()
    return entity.id


class TestReplaceThroughBridge:
    async def test_dbpedia_categories_replaced_and_visible_through_bridge(
        self, db_session: AsyncSession
    ) -> None:
        # R starts on the DBpedia source (cat-old, cat-keep); N already carries cat-new (Wikipedia).
        r = await _plain_entity(db_session, "Entity R")
        n = await _plain_entity(db_session, "Entity N")
        cat_old = await cat_repo.upsert(db_session, "cat-old")
        cat_keep = await cat_repo.upsert(db_session, "cat-keep")
        cat_new = await cat_repo.upsert(db_session, "cat-new")
        await assign_repo.add(db_session, r, cat_old.id, "dbpedia")
        await assign_repo.add(db_session, r, cat_keep.id, "dbpedia")
        await assign_repo.add(db_session, n, cat_new.id, "wikipedia")

        # Before: R shares nothing with N (R is on DBpedia categories N doesn't have).
        assert await assign_repo.shared_category_bridge(db_session, r) == []

        # Replace R's DBpedia categories with the Wikipedia namespace {cat-keep, cat-new}.
        await cc.store_categories_for_entity(
            db_session,
            r,
            ["cat-keep", "cat-new"],
            cat_repo=cat_repo,
            assign_repo=assign_repo,
            size_service=_StubSizes(),
            replace=True,
        )

        # Every one of R's assignments is now the Wikipedia namespace (FR-007); cat-old is gone.
        after = await assign_repo.categories_for(db_session, r)
        assert {c.name for c in after} == {"cat-keep", "cat-new"}
        sources = (
            (
                await db_session.execute(
                    select(EntityCategory.source).where(EntityCategory.entity_id == r)
                )
            )
            .scalars()
            .all()
        )
        assert set(sources) == {"wikipedia"}

        # Cross-Feature contract: read THROUGH the 083 bridge — R now neighbors N via cat-new,
        # a link that did not exist before the replace (the mutation is visible to the reader).
        neighbors = await assign_repo.shared_category_bridge(db_session, r)
        assert (_u(n), "cat-new") in {
            (_u(x.neighbor_id), x.shared_category) for x in neighbors
        }

    async def test_replace_with_empty_fetch_keeps_dbpedia_categories(
        self, db_session: AsyncSession
    ) -> None:
        # The safety invariant at the DB seam: a replace with an empty new set never deletes.
        r = await _plain_entity(db_session, "Entity R2")
        cat_old = await cat_repo.upsert(db_session, "cat-old-2")
        await assign_repo.add(db_session, r, cat_old.id, "dbpedia")

        await cc.store_categories_for_entity(
            db_session,
            r,
            [],  # empty fetch
            cat_repo=cat_repo,
            assign_repo=assign_repo,
            size_service=_StubSizes(),
            replace=True,
        )

        kept = await assign_repo.categories_for(db_session, r)
        assert {c.name for c in kept} == {"cat-old-2"}  # untouched
