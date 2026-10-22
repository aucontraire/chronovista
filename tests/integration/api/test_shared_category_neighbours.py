"""Integration tests for the shares-categories-with endpoint (Feature 085).

Reads **through** the endpoint against seeded Feature 083/084 rows (the Cross-Feature read path):
ranking by shared-category count, mega-hub suppression, active-only neighbours, self-exclusion,
pagination, the empty answer, and 404s. Entity/category names are neutral placeholders
(Constitution VI). The integration DB is shared and never reset, so everything is prefixed and
cleaned up.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from uuid_utils import uuid7

from chronovista.db.models import EntityCategory as EntityCategoryDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import WikipediaCategory as WikipediaCategoryDB

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

_PREFIX = "scs085"
_NOW = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


def _u(value: object) -> uuid.UUID:
    return uuid.UUID(str(value))


async def _entity(
    session: AsyncSession, name: str, *, status: str = "active"
) -> uuid.UUID:
    entity = NamedEntityDB(
        id=uuid7(),
        canonical_name=f"{_PREFIX} {name}",
        canonical_name_normalized=f"{_PREFIX} {name}".lower(),
        entity_type="person",
        status=status,
    )
    session.add(entity)
    await session.flush()
    return _u(entity.id)


async def _category(session: AsyncSession, name: str, size: int) -> uuid.UUID:
    cat = WikipediaCategoryDB(
        id=uuid7(),
        name=f"{_PREFIX}-{name}",
        global_size=size,
        global_size_fetched_at=_NOW,
    )
    session.add(cat)
    await session.flush()
    return _u(cat.id)


async def _assign(
    session: AsyncSession, entity_id: uuid.UUID, category_id: uuid.UUID
) -> None:
    session.add(
        EntityCategoryDB(
            entity_id=entity_id, category_id=category_id, source="wikipedia"
        )
    )


@pytest.fixture
async def seed(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, Any], None]:
    """Subject S shares: 2 specific categories with A, 1 with B, only a mega-hub with C;
    D shares a specific one but is inactive. E is unrelated."""
    async with integration_session_factory() as session:
        subject = await _entity(session, "subject")
        a = await _entity(session, "alpha")
        b = await _entity(session, "beta")
        c = await _entity(session, "gamma")
        d = await _entity(session, "delta", status="merged")  # inactive
        spec1 = await _category(session, "spec1", 10)
        spec2 = await _category(session, "spec2", 20)
        hub = await _category(session, "hub", 999_999)  # mega-hub (> default ceiling)
        await _assign(session, subject, spec1)
        await _assign(session, subject, spec2)
        await _assign(session, subject, hub)
        await _assign(session, a, spec1)
        await _assign(session, a, spec2)  # A shares 2 → ranks first
        await _assign(session, b, spec1)  # B shares 1
        await _assign(session, c, hub)  # C shares only the hub → suppressed
        await _assign(session, d, spec1)  # D shares 1 but inactive → absent
        await session.commit()
        ids = {"subject": subject, "a": a, "b": b, "c": c, "d": d}

    yield ids

    async with integration_session_factory() as session:
        eids = list(ids.values())
        await session.execute(
            delete(EntityCategoryDB).where(EntityCategoryDB.entity_id.in_(eids))
        )
        await session.execute(
            delete(WikipediaCategoryDB).where(
                WikipediaCategoryDB.name.like(f"{_PREFIX}-%")
            )
        )
        await session.execute(delete(NamedEntityDB).where(NamedEntityDB.id.in_(eids)))
        await session.commit()


class TestSharedCategoryNeighbours:
    async def test_ranks_active_neighbours_suppresses_hub_excludes_self(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/entities/{seed['subject']}/shared-categories"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        ids = [_u(row["entity_id"]) for row in data]

        assert (
            seed["a"] in ids and seed["b"] in ids
        )  # specific-category neighbours present
        assert seed["c"] not in ids  # hub-only → suppressed (FR-004)
        assert seed["d"] not in ids  # inactive → excluded (FR-006)
        assert seed["subject"] not in ids  # self never in its own list

        # A (2 shared) ranks before B (1 shared) — count desc (FR-003)
        assert ids.index(seed["a"]) < ids.index(seed["b"])
        a_row = next(r for r in data if _u(r["entity_id"]) == seed["a"])
        assert a_row["shared_category_count"] == 2
        # Feature 086: each shared category is now an {id, name} ref (so a chip can link by id),
        # not a bare name string.
        assert {c["name"] for c in a_row["shared_categories"]} == {
            f"{_PREFIX}-spec1",
            f"{_PREFIX}-spec2",
        }
        assert all(
            c["id"] for c in a_row["shared_categories"]
        )  # id present for linking

    async def test_pagination_bounds_results(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/entities/{seed['subject']}/shared-categories?limit=1"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert _u(data[0]["entity_id"]) == seed["a"]  # highest-ranked first

    async def test_entity_with_no_neighbours_is_empty_not_error(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with integration_session_factory() as session:
            lonely = await _entity(session, "lonely")
            await session.commit()
        try:
            resp = await async_client.get(
                f"/api/v1/entities/{lonely}/shared-categories"
            )
            assert resp.status_code == 200
            assert resp.json()["data"] == []
        finally:
            async with integration_session_factory() as session:
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == lonely)
                )
                await session.commit()

    async def test_malformed_id_is_404(self, async_client: AsyncClient) -> None:
        resp = await async_client.get("/api/v1/entities/not-a-uuid/shared-categories")
        assert resp.status_code == 404

    async def test_unknown_entity_is_404(self, async_client: AsyncClient) -> None:
        resp = await async_client.get(
            f"/api/v1/entities/{uuid.uuid4()}/shared-categories"
        )
        assert resp.status_code == 404
