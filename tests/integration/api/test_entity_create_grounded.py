"""ST-007 — grounded-create write path (Feature 067, US3).

Creating an entity with an approved identifier is a real cross-boundary write: endpoint →
NamedEntityCreate → database. This reads the row back from a real DB and asserts the verified
identifier landed and the display fields are untouched; a create without an approved identifier
persists an ungrounded entity. A mock asserting "the endpoint was called" would not cross this
seam.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import NamedEntity as NamedEntityDB

pytestmark = pytest.mark.asyncio


async def _row_by_name(
    factory: async_sessionmaker[AsyncSession], normalized: str
) -> NamedEntityDB:
    async with factory() as s:
        return (
            await s.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == normalized
                )
            )
        ).scalar_one()


class TestGroundedCreate:
    async def test_create_with_approved_identifier_persists_verified(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        name = f"Grounded {uuid.uuid4().hex[:10]}"
        r = await async_client.post(
            "/api/v1/entities",
            json={
                "name": name,
                "entity_type": "person",
                "approved_identifier": {"source": "wikidata", "id": "Q000009"},
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["grounded"] is True

        row = await _row_by_name(integration_session_factory, name.lower())
        assert row.external_ids["wikidata"]["id"] == "Q000009"
        assert row.external_ids["wikidata"]["verified"] is True
        assert row.external_ids["wikidata"]["status"] == "verified"
        # display fields carry the human input, not clobbered
        assert row.canonical_name == name

    async def test_create_without_identifier_is_ungrounded(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        name = f"Ungrounded {uuid.uuid4().hex[:10]}"
        r = await async_client.post(
            "/api/v1/entities",
            json={"name": name, "entity_type": "person"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["grounded"] is False

        row = await _row_by_name(integration_session_factory, name.lower())
        assert row.external_ids == {}
