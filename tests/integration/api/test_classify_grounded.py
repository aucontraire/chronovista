"""Grounded tag→entity classification (Feature 067, US3 — classify path).

Grounding must be available whether or not a tag exists: promoting a tag to a NEW entity is a
creation moment, so `POST /entities/classify` accepts an `approved_identifier` and persists it
(verified) on the created entity — the same contract as standalone create. A real cross-boundary
write: endpoint → TagManagementService.classify → NamedEntityCreate → DB, read back.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import NamedEntity as NamedEntityDB

pytestmark = pytest.mark.asyncio


async def _seed_tag(factory: async_sessionmaker[AsyncSession]) -> str:
    norm = f"grounded classify {uuid.uuid4().hex[:10]}"
    async with factory() as s:
        s.add(
            CanonicalTagDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                canonical_form=norm.title(),
                normalized_form=norm,
                alias_count=1,
                video_count=0,
                status="active",
            )
        )
        await s.commit()
    return norm


async def _entity_for_tag(
    factory: async_sessionmaker[AsyncSession], norm: str
) -> NamedEntityDB:
    async with factory() as s:
        return (
            await s.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == norm
                )
            )
        ).scalar_one()


class TestGroundedClassify:
    async def test_classify_with_approved_identifier_grounds_new_entity(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        norm = await _seed_tag(integration_session_factory)
        r = await async_client.post(
            "/api/v1/entities/classify",
            json={
                "normalized_form": norm,
                "entity_type": "person",
                "approved_identifier": {"source": "wikidata", "id": "Q000009"},
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["entity_created"] is True
        assert body["grounded"] is True

        entity = await _entity_for_tag(integration_session_factory, norm)
        assert entity.external_ids["wikidata"]["id"] == "Q000009"
        assert entity.external_ids["wikidata"]["verified"] is True
        assert entity.external_ids["wikidata"]["status"] == "verified"

    async def test_classify_without_identifier_is_ungrounded(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        norm = await _seed_tag(integration_session_factory)
        r = await async_client.post(
            "/api/v1/entities/classify",
            json={"normalized_form": norm, "entity_type": "person"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["grounded"] is False

        entity = await _entity_for_tag(integration_session_factory, norm)
        assert entity.external_ids == {}
