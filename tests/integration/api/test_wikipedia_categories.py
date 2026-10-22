"""Integration tests for the category detail endpoints (Feature 086).

Reads **through** the two new endpoints against seeded Feature 083/084 rows: category meta
(identity, breadth flag, active-member count), the paginated member list (active-only, total
alphabetical order, bounded), the empty answer, and 404s. Entity/category names are neutral
placeholders (Constitution VI). The integration DB is shared and never reset, so everything is
prefixed and cleaned up.
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

_PREFIX = "wcat086"
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
    """A specific category with 3 active members (one capitalized, out of ASCII order) + 1
    inactive; a broad category (size above the ceiling); an empty category (inactive member
    only)."""
    async with integration_session_factory() as session:
        # "Bravo" is capitalized so a case-sensitive sort would misplace it; lower()-ordering
        # must yield alpha < Bravo < charlie.
        alpha = await _entity(session, "alpha")
        bravo = await _entity(session, "Bravo")
        charlie = await _entity(session, "charlie")
        inactive = await _entity(session, "delta", status="merged")

        specific = await _category(session, "specific", 10)
        broad = await _category(session, "broad", 999_999)
        empty = await _category(session, "empty", 50)

        await _assign(session, alpha, specific)
        await _assign(session, bravo, specific)
        await _assign(session, charlie, specific)
        await _assign(session, inactive, specific)  # inactive → excluded everywhere
        await _assign(session, alpha, broad)
        await _assign(session, bravo, broad)
        await _assign(
            session, inactive, empty
        )  # empty category: only an inactive member
        await session.commit()
        ids = {
            "alpha": alpha,
            "bravo": bravo,
            "charlie": charlie,
            "inactive": inactive,
            "specific": specific,
            "broad": broad,
            "empty": empty,
        }

    yield ids

    async with integration_session_factory() as session:
        eids = [ids[k] for k in ("alpha", "bravo", "charlie", "inactive")]
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


class TestCategoryMeta:
    async def test_specific_category_meta(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/wikipedia-categories/{seed['specific']}"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert _u(data["id"]) == seed["specific"]
        assert data["name"] == f"{_PREFIX}-specific"
        assert data["global_size"] == 10
        assert data["is_broad"] is False
        assert data["member_count"] == 3  # the inactive member is not counted
        # outbound link to the public Wikipedia category page
        assert (
            data["wikipedia_url"]
            == f"https://en.wikipedia.org/wiki/Category:{_PREFIX}-specific"
        )

    async def test_broad_category_flagged(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(f"/api/v1/wikipedia-categories/{seed['broad']}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_broad"] is True
        assert data["member_count"] == 2

    async def test_unknown_id_is_404(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(f"/api/v1/wikipedia-categories/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_malformed_id_is_404(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get("/api/v1/wikipedia-categories/not-a-uuid")
        assert resp.status_code == 404


class TestCategoryEntities:
    async def test_members_active_only_alphabetical(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/wikipedia-categories/{seed['specific']}/entities"
        )
        assert resp.status_code == 200
        body = resp.json()
        ids = [_u(m["entity_id"]) for m in body["data"]]
        # active-only: the inactive member is absent
        assert seed["inactive"] not in ids
        # total order lower(name): alpha < Bravo < charlie (proves case-insensitive ordering)
        assert ids == [seed["alpha"], seed["bravo"], seed["charlie"]]
        assert body["pagination"]["total"] == 3
        assert body["pagination"]["has_more"] is False
        # member rows carry display fields
        assert body["data"][0]["canonical_name"] == f"{_PREFIX} alpha"
        assert body["data"][0]["entity_type"] == "person"

    async def test_pagination_no_overlap(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        page1 = (
            await async_client.get(
                f"/api/v1/wikipedia-categories/{seed['specific']}/entities?limit=2"
            )
        ).json()
        assert [_u(m["entity_id"]) for m in page1["data"]] == [
            seed["alpha"],
            seed["bravo"],
        ]
        assert page1["pagination"]["has_more"] is True

        page2 = (
            await async_client.get(
                f"/api/v1/wikipedia-categories/{seed['specific']}/entities"
                "?limit=2&offset=2"
            )
        ).json()
        assert [_u(m["entity_id"]) for m in page2["data"]] == [seed["charlie"]]
        assert page2["pagination"]["has_more"] is False

    async def test_broad_category_members_still_bounded(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/wikipedia-categories/{seed['broad']}/entities?limit=1"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1  # bounded even for a broad category
        assert body["pagination"]["total"] == 2
        assert body["pagination"]["has_more"] is True

    async def test_empty_category_is_empty_not_error(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/wikipedia-categories/{seed['empty']}/entities"
        )
        assert (
            resp.status_code == 200
        )  # a category with no active members is not an error
        body = resp.json()
        assert body["data"] == []
        assert body["pagination"]["total"] == 0

    async def test_unknown_id_entities_is_404(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/wikipedia-categories/{uuid.uuid4()}/entities"
        )
        assert resp.status_code == 404

    async def test_malformed_id_entities_is_404(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        # The 4th outcome on the entities endpoint: a non-UUID id is a 404 (not a 422),
        # matching the detail endpoint and the 085 convention.
        resp = await async_client.get(
            "/api/v1/wikipedia-categories/not-a-uuid/entities"
        )
        assert resp.status_code == 404
