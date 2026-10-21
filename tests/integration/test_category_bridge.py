"""Real-database seam tests for the category tables and shared-category bridge (083)."""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityCategory, NamedEntity, WikipediaCategory
from chronovista.repositories.entity_category_repository import (
    EntityCategoryRepository,
)
from chronovista.repositories.wikipedia_category_repository import (
    WikipediaCategoryRepository,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

NOW = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
cat_repo = WikipediaCategoryRepository()
links = EntityCategoryRepository()


async def _entity(session: AsyncSession, name: str) -> uuid.UUID:
    entity = NamedEntity(
        canonical_name=name,
        canonical_name_normalized=name.lower(),
        entity_type="person",
    )
    session.add(entity)
    await session.flush()
    return entity.id


async def _category(
    session: AsyncSession, name: str, size: int | None = None
) -> uuid.UUID:
    cat = await cat_repo.upsert(session, name)
    if size is not None:
        await cat_repo.set_global_size(session, cat.id, size, NOW)
    return cat.id


def _u(value: object) -> uuid.UUID:
    # Python-side defaults are uuid_utils.UUID and asyncpg returns its own subclass;
    # neither equals stdlib uuid.UUID, so normalize both sides before comparing.
    return uuid.UUID(str(value))


async def _link_count(session: AsyncSession) -> int:
    return int(
        (
            await session.execute(select(func.count()).select_from(EntityCategory))
        ).scalar_one()
    )


class TestIncrementalFetch:
    async def test_names_without_global_size_returns_only_null_ones(
        self, db_session: AsyncSession
    ) -> None:
        await _category(db_session, "cat-sized", 42)  # has a size
        await _category(db_session, "cat-null")  # NULL size
        await _category(db_session, "cat-null-2")  # NULL size

        missing = await cat_repo.names_without_global_size(
            db_session, ["cat-sized", "cat-null", "cat-null-2", "cat-absent"]
        )
        # sized category and the never-inserted name are both excluded.
        assert set(missing) == {"cat-null", "cat-null-2"}

    async def test_empty_input_returns_empty(self, db_session: AsyncSession) -> None:
        assert await cat_repo.names_without_global_size(db_session, []) == []


class TestBridge:
    async def test_returns_co_members_and_excludes_self(
        self, db_session: AsyncSession
    ) -> None:
        a = await _entity(db_session, "Entity A")
        b = await _entity(db_session, "Entity B")
        c = await _entity(db_session, "Entity C")
        x = await _category(db_session, "cat-x", 10)
        y = await _category(db_session, "cat-y", 20)
        await links.add(db_session, a, x, "dbpedia")
        await links.add(db_session, b, x, "dbpedia")
        await links.add(db_session, c, y, "dbpedia")
        await links.add(db_session, a, y, "dbpedia")

        out = await links.shared_category_bridge(db_session, a)

        assert {(_u(n.neighbor_id), n.shared_category) for n in out} == {
            (_u(b), "cat-x"),
            (_u(c), "cat-y"),
        }
        assert all(_u(n.neighbor_id) != _u(a) for n in out)
        assert {n.global_size for n in out} == {10, 20}

    async def test_no_shared_category_is_empty_not_error(
        self, db_session: AsyncSession
    ) -> None:
        a = await _entity(db_session, "Entity A")
        b = await _entity(db_session, "Entity B")
        await links.add(db_session, a, await _category(db_session, "cat-x"), "dbpedia")
        await links.add(db_session, b, await _category(db_session, "cat-y"), "dbpedia")

        assert await links.shared_category_bridge(db_session, a) == []

    async def test_entity_without_categories_is_empty(
        self, db_session: AsyncSession
    ) -> None:
        a = await _entity(db_session, "Entity A")
        assert await links.shared_category_bridge(db_session, a) == []

    async def test_cap_excludes_hub_and_null_size_keeps_specific(
        self, db_session: AsyncSession
    ) -> None:
        a = await _entity(db_session, "Entity A")
        b = await _entity(db_session, "Entity B")
        specific = await _category(db_session, "cat-x", 50)
        hub = await _category(db_session, "cat-y", 100000)
        unknown = await _category(db_session, "cat-z", None)
        for cid in (specific, hub, unknown):
            await links.add(db_session, a, cid, "dbpedia")
            await links.add(db_session, b, cid, "dbpedia")

        uncapped = await links.shared_category_bridge(db_session, a)
        capped = await links.shared_category_bridge(db_session, a, max_global_size=1000)

        assert {n.shared_category for n in uncapped} == {"cat-x", "cat-y", "cat-z"}
        assert [n.shared_category for n in capped] == ["cat-x"]

    async def test_cap_boundary_is_inclusive(self, db_session: AsyncSession) -> None:
        a = await _entity(db_session, "Entity A")
        b = await _entity(db_session, "Entity B")
        edge = await _category(db_session, "cat-x", 100)
        await links.add(db_session, a, edge, "dbpedia")
        await links.add(db_session, b, edge, "dbpedia")

        assert len(await links.shared_category_bridge(db_session, a, 100)) == 1
        assert await links.shared_category_bridge(db_session, a, 99) == []


class TestCascade:
    async def test_deleting_entity_removes_its_links(
        self, db_session: AsyncSession
    ) -> None:
        a = await _entity(db_session, "Entity A")
        b = await _entity(db_session, "Entity B")
        x = await _category(db_session, "cat-x")
        await links.add(db_session, a, x, "dbpedia")
        await links.add(db_session, b, x, "dbpedia")

        await db_session.execute(delete(NamedEntity).where(NamedEntity.id == a))

        rows = (
            (await db_session.execute(select(EntityCategory.entity_id))).scalars().all()
        )
        assert [_u(r) for r in rows] == [_u(b)]
        assert await links.categories_for(db_session, a) == []

    async def test_deleting_category_removes_its_links(
        self, db_session: AsyncSession
    ) -> None:
        a = await _entity(db_session, "Entity A")
        x = await _category(db_session, "cat-x")
        y = await _category(db_session, "cat-y")
        await links.add(db_session, a, x, "dbpedia")
        await links.add(db_session, a, y, "dbpedia")

        await db_session.execute(
            delete(WikipediaCategory).where(WikipediaCategory.id == x)
        )

        rows = (
            (await db_session.execute(select(EntityCategory.category_id)))
            .scalars()
            .all()
        )
        assert [_u(r) for r in rows] == [_u(y)]


class TestSingleSourceOfTruthAndIdempotency:
    async def test_global_size_identical_through_two_members(
        self, db_session: AsyncSession
    ) -> None:
        a = await _entity(db_session, "Entity A")
        b = await _entity(db_session, "Entity B")
        c = await _entity(db_session, "Entity C")
        x = await _category(db_session, "cat-x", 77)
        for e in (a, b, c):
            await links.add(db_session, e, x, "dbpedia")

        via_a = await links.shared_category_bridge(db_session, a)
        via_b = await links.shared_category_bridge(db_session, b)

        assert {n.global_size for n in via_a} == {77}
        assert {n.global_size for n in via_b} == {77}
        # The size lives once, on the category row.
        cat = await cat_repo.get_by_name(db_session, "cat-x")
        assert cat is not None and cat.global_size == 77
        assert cat.global_size_fetched_at == NOW

        await cat_repo.set_global_size(db_session, x, 78, NOW)
        assert {
            n.global_size for n in await links.shared_category_bridge(db_session, a)
        } == {78}
        assert {
            n.global_size for n in await links.shared_category_bridge(db_session, b)
        } == {78}

    async def test_upsert_is_idempotent(self, db_session: AsyncSession) -> None:
        first = await cat_repo.upsert(db_session, "cat-x")
        await cat_repo.set_global_size(db_session, first.id, 5, NOW)
        second = await cat_repo.upsert(db_session, "cat-x")

        assert second.id == first.id
        assert second.global_size == 5  # re-upsert must not clobber the size
        count = (
            await db_session.execute(
                select(func.count()).select_from(WikipediaCategory)
            )
        ).scalar_one()
        assert count == 1

    async def test_get_by_name_missing_returns_none(
        self, db_session: AsyncSession
    ) -> None:
        assert await cat_repo.get_by_name(db_session, "cat-absent") is None

    async def test_add_is_idempotent_and_keeps_original_provenance(
        self, db_session: AsyncSession
    ) -> None:
        a = await _entity(db_session, "Entity A")
        x = await _category(db_session, "cat-x")
        await links.add(db_session, a, x, "dbpedia", NOW)
        await links.add(db_session, a, x, "other", None)

        assert await _link_count(db_session) == 1
        row = (await db_session.execute(select(EntityCategory))).scalar_one()
        assert row.source == "dbpedia"
        assert row.set_at == NOW
        assert [c.name for c in await links.categories_for(db_session, a)] == ["cat-x"]
