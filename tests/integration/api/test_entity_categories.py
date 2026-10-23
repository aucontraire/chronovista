"""Integration tests for the all-categories endpoint (Feature 090).

Reads **through** the endpoint against seeded Feature 083/084 rows: every category the entity
belongs to, with its **active** member count (including the subject — so a sole-member category
reads 1, == the Distinctive case), ordered most-specific-first; inactive co-members are not
counted; empty answer; 404s; and an inactive subject yields []. Entity/category names are neutral
placeholders (Constitution VI). The integration DB is shared and never reset, so everything is
prefixed and cleaned up.
"""

from __future__ import annotations

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

_PREFIX = "ec090"


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
    """Subject is in: `asolo` (only it → count 1), `bshared` (it + an active other → count 2),
    `csolovia` (it + an inactive ghost → count 1, ghost not counted). Names a/b/c prefixed to
    make the count-ascending + name tiebreak order deterministic."""
    async with integration_session_factory() as session:
        subject = await _entity(session, "subject")
        other = await _entity(session, "other")
        ghost = await _entity(session, "ghost", status="merged")  # inactive
        asolo = await _category(session, "asolo")
        bshared = await _category(session, "bshared")
        csolovia = await _category(session, "csolovia")
        await _assign(session, subject, asolo)
        await _assign(session, subject, bshared)
        await _assign(session, other, bshared)
        await _assign(session, subject, csolovia)
        await _assign(session, ghost, csolovia)
        await session.commit()
        ids = {
            "subject": subject,
            "other": other,
            "ghost": ghost,
            "asolo": asolo,
            "bshared": bshared,
            "csolovia": csolovia,
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


class TestEntityCategories:
    async def test_returns_all_memberships_with_active_counts(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(f"/api/v1/entities/{seed['subject']}/categories")
        assert resp.status_code == 200
        data = resp.json()["data"]
        by_id = {_u(row["id"]): row for row in data}

        # every category the subject is in is present (no overlap/ranking filter)
        assert set(by_id) == {seed["asolo"], seed["bshared"], seed["csolovia"]}
        # member count = active members INCLUDING the subject
        assert by_id[seed["asolo"]]["member_count"] == 1  # subject only → distinctive
        assert by_id[seed["bshared"]]["member_count"] == 2  # subject + active other
        # inactive ghost is NOT counted → subject is the sole ACTIVE member → count 1
        assert by_id[seed["csolovia"]]["member_count"] == 1

    async def test_member_count_1_equals_distinctive(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """The CHK012 guard: member_count == 1 is exactly the Distinctive set."""
        all_resp = await async_client.get(
            f"/api/v1/entities/{seed['subject']}/categories"
        )
        dist_resp = await async_client.get(
            f"/api/v1/entities/{seed['subject']}/distinctive-categories"
        )
        count1 = {
            _u(r["id"]) for r in all_resp.json()["data"] if r["member_count"] == 1
        }
        distinctive = {_u(r["id"]) for r in dist_resp.json()["data"]}
        assert count1 == distinctive == {seed["asolo"], seed["csolovia"]}

    async def test_ordered_by_member_count_ascending(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(f"/api/v1/entities/{seed['subject']}/categories")
        counts = [row["member_count"] for row in resp.json()["data"]]
        assert counts == sorted(counts)  # most-specific (fewest members) first
        # within the two count-1 categories, name tiebreak: asolo before csolovia
        names = [row["name"] for row in resp.json()["data"]]
        assert names[0] == f"{_PREFIX}-asolo"

    async def test_paging_is_stable_no_skip_or_repeat(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """The total-order claim: paging limit=1 across offsets reproduces the full list
        exactly (no skip, no repeat), including the same-count tiebreak (asolo before
        csolovia, both member_count 1)."""
        full = await async_client.get(f"/api/v1/entities/{seed['subject']}/categories")
        full_ids = [row["id"] for row in full.json()["data"]]
        assert len(full_ids) == 3  # asolo, csolovia, bshared

        paged: list[str] = []
        for offset in range(len(full_ids)):
            page = await async_client.get(
                f"/api/v1/entities/{seed['subject']}/categories?limit=1&offset={offset}"
            )
            assert page.status_code == 200
            rows = page.json()["data"]
            assert len(rows) == 1
            paged.append(rows[0]["id"])

        assert (
            paged == full_ids
        )  # same order, every category once, none skipped/repeated

    async def test_entity_with_no_categories_is_empty_not_error(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with integration_session_factory() as session:
            lonely = await _entity(session, "lonely")
            await session.commit()
        try:
            resp = await async_client.get(f"/api/v1/entities/{lonely}/categories")
            assert resp.status_code == 200
            assert resp.json()["data"] == []
        finally:
            async with integration_session_factory() as session:
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == lonely)
                )
                await session.commit()

    async def test_inactive_subject_is_empty(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """The ne_self active guard (consistent with distinctive): an inactive subject yields []."""
        resp = await async_client.get(f"/api/v1/entities/{seed['ghost']}/categories")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_malformed_id_is_404(self, async_client: AsyncClient) -> None:
        resp = await async_client.get("/api/v1/entities/not-a-uuid/categories")
        assert resp.status_code == 404

    async def test_unknown_entity_is_404(self, async_client: AsyncClient) -> None:
        resp = await async_client.get(f"/api/v1/entities/{uuid.uuid4()}/categories")
        assert resp.status_code == 404
