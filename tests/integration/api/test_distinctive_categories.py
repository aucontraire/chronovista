"""Integration tests for the distinctive-categories endpoint (Feature 089).

Reads **through** the endpoint against seeded Feature 083/084 rows (the Cross-Feature read path):
a category whose sole active member is the subject is "distinctive"; a shared one is not; a
category whose only *other* member is inactive is still distinctive (the active-only count), the
empty answer, and 404s. Entity/category names are neutral placeholders (Constitution VI). The
integration DB is shared and never reset, so everything is prefixed and cleaned up.
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

_PREFIX = "dc089"
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


async def _category(session: AsyncSession, name: str) -> uuid.UUID:
    cat = WikipediaCategoryDB(
        id=uuid7(),
        name=f"{_PREFIX}-{name}",
        global_size=None,
        global_size_fetched_at=None,
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
    """Subject is the sole active member of `solo` and `solo_via_inactive`; it shares
    `shared` with another active entity. `ghost` (inactive) co-sits in `solo_via_inactive`.
    """
    async with integration_session_factory() as session:
        subject = await _entity(session, "subject")
        other = await _entity(session, "other")
        ghost = await _entity(session, "ghost", status="merged")  # inactive
        solo = await _category(session, "solo")  # subject only → distinctive
        shared = await _category(session, "shared")  # subject + other → NOT distinctive
        solo_via_inactive = await _category(
            session, "solovia"
        )  # subject + inactive ghost → distinctive (ghost not counted)
        await _assign(session, subject, solo)
        await _assign(session, subject, shared)
        await _assign(session, other, shared)
        await _assign(session, subject, solo_via_inactive)
        await _assign(session, ghost, solo_via_inactive)
        await session.commit()
        ids = {
            "subject": subject,
            "other": other,
            "ghost": ghost,
            "solo": solo,
            "shared": shared,
            "solo_via_inactive": solo_via_inactive,
        }

    yield ids

    async with integration_session_factory() as session:
        eids = [ids["subject"], ids["other"], ids["ghost"]]
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


class TestDistinctiveCategories:
    async def test_returns_sole_active_member_categories_only(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/entities/{seed['subject']}/distinctive-categories"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        ids = {_u(row["id"]) for row in data}

        # sole-member category is distinctive
        assert seed["solo"] in ids
        # category whose only OTHER member is inactive → subject is sole ACTIVE member
        assert seed["solo_via_inactive"] in ids
        # category shared with another active entity is NOT distinctive
        assert seed["shared"] not in ids
        assert ids == {seed["solo"], seed["solo_via_inactive"]}

        # each row carries id + name so a chip can link to the category page
        by_id = {_u(row["id"]): row for row in data}
        assert by_id[seed["solo"]]["name"] == f"{_PREFIX}-solo"
        assert all(row["name"] for row in data)

    async def test_stable_order_by_name(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/entities/{seed['subject']}/distinctive-categories"
        )
        assert resp.status_code == 200
        names = [row["name"] for row in resp.json()["data"]]
        # "dc089-solo" < "dc089-solovia" case-insensitively → deterministic order
        assert names == sorted(names, key=str.lower)

    async def test_entity_with_no_distinctive_categories_is_empty_not_error(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        # `other` sits only in the shared category (2 active members) → nothing distinctive
        resp = await async_client.get(
            f"/api/v1/entities/{seed['other']}/distinctive-categories"
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_inactive_subject_is_empty_proving_the_active_guard(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """The `ne_self` active guard: an inactive entity is never distinctive.

        `ghost` is inactive (status='merged') and co-sits in `solo_via_inactive`, a
        category whose sole ACTIVE member is the subject. WITHOUT the `ne_self.status`
        guard, grouping ghost's memberships and counting active members would yield
        count==1 (the subject) and mis-report that category as distinctive FOR GHOST.
        With the guard, an inactive subject produces no rows → empty. This test fails
        if the guard is removed, which the other cases do not.
        """
        resp = await async_client.get(
            f"/api/v1/entities/{seed['ghost']}/distinctive-categories"
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_malformed_id_is_404(self, async_client: AsyncClient) -> None:
        resp = await async_client.get(
            "/api/v1/entities/not-a-uuid/distinctive-categories"
        )
        assert resp.status_code == 404

    async def test_unknown_entity_is_404(self, async_client: AsyncClient) -> None:
        resp = await async_client.get(
            f"/api/v1/entities/{uuid.uuid4()}/distinctive-categories"
        )
        assert resp.status_code == 404
