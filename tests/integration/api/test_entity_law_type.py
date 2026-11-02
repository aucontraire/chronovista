"""Integration tests for the ``law`` entity type end to end (Feature 104, US1).

Mirrors the product end-to-end test (Feature 103): standalone creation + list-filter, and a
canonical tag classified as ``law`` promoting to a law entity (exercising
``chk_canonical_tag_entity_type_valid`` and ``chk_entity_type_valid`` end to end). Candidate
``type_hint='law'`` acceptance is covered by the migration content test + the scan validator,
as in 103. No library content: a fictional placeholder law name.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB

pytestmark = pytest.mark.asyncio

_LAW_NAME = "lt placeholder law act"
_LAW_NORMALIZED = "lt placeholder law act"


def _create_entity_url() -> str:
    return "/api/v1/entities"


def _classify_url() -> str:
    return "/api/v1/entities/classify"


async def _wipe_law_entity(session: AsyncSession) -> None:
    rows = (
        (
            await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == _LAW_NORMALIZED,
                    NamedEntityDB.entity_type == "law",
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        await session.execute(
            delete(EntityAliasDB).where(EntityAliasDB.entity_id == row.id)
        )
    await session.execute(
        delete(NamedEntityDB).where(
            NamedEntityDB.canonical_name_normalized == _LAW_NORMALIZED,
            NamedEntityDB.entity_type == "law",
        )
    )
    await session.commit()


class TestStandaloneLawEntity:
    @pytest.fixture(autouse=True)
    async def cleanup(
        self, integration_session_factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[None, None]:
        async with integration_session_factory() as session:
            await _wipe_law_entity(session)
        yield
        async with integration_session_factory() as session:
            await _wipe_law_entity(session)

    async def test_create_and_filter_law_entity(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            created = await async_client.post(
                _create_entity_url(),
                json={"name": _LAW_NAME, "entity_type": "law", "aliases": []},
            )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["entity_type"] == "law", body
        entity_id = body["entity_id"]

        async with integration_session_factory() as session:
            db_entity = await session.get(NamedEntityDB, uuid.UUID(entity_id))
            assert db_entity is not None
            assert db_entity.entity_type == "law"
            assert db_entity.status == "active"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            in_law = await async_client.get(
                _create_entity_url(), params={"search": _LAW_NAME, "type": "law"}
            )
            in_work = await async_client.get(
                _create_entity_url(), params={"search": _LAW_NAME, "type": "work"}
            )
        assert in_law.status_code == 200, in_law.text
        assert entity_id in {e["entity_id"] for e in in_law.json()["data"]}
        assert in_work.status_code == 200, in_work.text
        assert entity_id not in {e["entity_id"] for e in in_work.json()["data"]}


class TestClassifyTagAsLaw:
    _TAG_NORMALIZED = "lt classify law"
    _TAG_CANONICAL = "Lt Classify Law"

    @pytest.fixture
    async def seed_law_tag(
        self, integration_session_factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[dict[str, Any], None]:
        tag_id = uuid.UUID(bytes=uuid7().bytes)

        async def _wipe(session: AsyncSession) -> None:
            tag_row = (
                await session.execute(
                    select(CanonicalTagDB).where(
                        CanonicalTagDB.normalized_form == self._TAG_NORMALIZED
                    )
                )
            ).scalar_one_or_none()
            if tag_row is not None and tag_row.entity_id is not None:
                await session.execute(
                    delete(EntityAliasDB).where(
                        EntityAliasDB.entity_id == tag_row.entity_id
                    )
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == tag_row.entity_id)
                )
            await session.execute(
                delete(TagAliasDB).where(
                    TagAliasDB.normalized_form == self._TAG_NORMALIZED
                )
            )
            await session.execute(
                delete(CanonicalTagDB).where(
                    CanonicalTagDB.normalized_form == self._TAG_NORMALIZED
                )
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)
            tag = CanonicalTagDB(
                id=tag_id,
                canonical_form=self._TAG_CANONICAL,
                normalized_form=self._TAG_NORMALIZED,
                alias_count=1,
                video_count=0,
                status="active",
            )
            session.add(tag)
            await session.commit()
            session.add(
                TagAliasDB(
                    id=uuid.UUID(bytes=uuid7().bytes),
                    raw_form=self._TAG_CANONICAL,
                    normalized_form=self._TAG_NORMALIZED,
                    canonical_tag_id=tag_id,
                    creation_method="auto_normalize",
                    occurrence_count=1,
                )
            )
            await session.commit()

        yield {"tag_id": tag_id, "normalized_form": self._TAG_NORMALIZED}

        async with integration_session_factory() as session:
            await _wipe(session)

    async def test_classify_tag_as_law_promotes_to_law_entity(
        self,
        async_client: AsyncClient,
        seed_law_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.post(
                _classify_url(),
                json={
                    "normalized_form": seed_law_tag["normalized_form"],
                    "entity_type": "law",
                },
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["entity_type"] == "law", body
        assert body["entity_created"] is True

        async with integration_session_factory() as session:
            entity = await session.get(NamedEntityDB, uuid.UUID(body["entity_id"]))
            assert entity is not None and entity.entity_type == "law"
            tag = await session.get(CanonicalTagDB, seed_law_tag["tag_id"])
            assert tag is not None and tag.entity_type == "law"
            assert tag.entity_id == entity.id
