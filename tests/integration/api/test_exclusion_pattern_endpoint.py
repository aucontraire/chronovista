"""Integration tests for the exclusion-pattern endpoints (#256).

``POST`` / ``DELETE /api/v1/entities/{id}/exclusion-patterns`` mutate the
entity's ``exclusion_patterns`` JSONB column. These endpoints had no test
coverage before the #256 repository migration swapped their ``session.get``
for ``NamedEntityRepository.get``; these tests exercise the mutation
end-to-end on the integration DB and assert it persists.

Requires the integration database (chronovista_integration_test).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

_NORM = "excl256 primary"


def _url(entity_id: uuid.UUID) -> str:
    return f"/api/v1/entities/{entity_id}/exclusion-patterns"


async def _purge(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        await session.execute(
            delete(NamedEntityDB).where(
                NamedEntityDB.canonical_name_normalized == _NORM
            )
        )
        await session.commit()


async def _seed(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    entity_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            create_named_entity_db(
                id=entity_id,
                canonical_name=_NORM.title(),
                canonical_name_normalized=_NORM,
                entity_type="person",
            )
        )
        await session.commit()
    return entity_id


@pytest.fixture
async def seeded(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[uuid.UUID, None]:
    await _purge(integration_session_factory)
    entity_id = await _seed(integration_session_factory)
    yield entity_id
    await _purge(integration_session_factory)


def _auth():  # type: ignore[no-untyped-def]
    return patch("chronovista.api.deps.youtube_oauth")


async def _stored_patterns(
    factory: async_sessionmaker[AsyncSession], entity_id: uuid.UUID
) -> list[str]:
    async with factory() as session:
        entity = (
            await session.execute(
                select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
            )
        ).scalar_one()
        return list(entity.exclusion_patterns or [])


class TestAddExclusionPattern:
    async def test_add_trims_persists_and_returns_201(
        self,
        async_client: AsyncClient,
        seeded: uuid.UUID,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.post(
                _url(entity_id), json={"pattern": "  exclm-alpha  "}
            )
        assert resp.status_code == 201, resp.text
        # Whitespace is trimmed before storing.
        assert resp.json()["data"]["exclusion_patterns"] == ["exclm-alpha"]
        assert await _stored_patterns(integration_session_factory, entity_id) == [
            "exclm-alpha"
        ]

    async def test_add_duplicate_returns_409_without_double_append(
        self,
        async_client: AsyncClient,
        seeded: uuid.UUID,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            await async_client.post(_url(entity_id), json={"pattern": "exclm-dup"})
            resp = await async_client.post(
                _url(entity_id), json={"pattern": "exclm-dup"}
            )
        assert resp.status_code == 409, resp.text
        # The rejected duplicate must NOT have been appended a second time.
        assert await _stored_patterns(integration_session_factory, entity_id) == [
            "exclm-dup"
        ]

    async def test_add_empty_after_trim_returns_409(
        self, async_client: AsyncClient, seeded: uuid.UUID
    ) -> None:
        entity_id = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.post(_url(entity_id), json={"pattern": "   "})
        assert resp.status_code == 409, resp.text

    async def test_add_unknown_entity_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.post(
                _url(uuid.uuid4()), json={"pattern": "exclm-x"}
            )
        assert resp.status_code == 404, resp.text

    async def test_add_invalid_uuid_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.post(
                "/api/v1/entities/not-a-uuid/exclusion-patterns",
                json={"pattern": "exclm-x"},
            )
        assert resp.status_code == 404, resp.text


class TestRemoveExclusionPattern:
    async def test_remove_persists_and_returns_200(
        self,
        async_client: AsyncClient,
        seeded: uuid.UUID,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            await async_client.post(_url(entity_id), json={"pattern": "exclm-keep"})
            await async_client.post(_url(entity_id), json={"pattern": "exclm-drop"})
            resp = await async_client.request(
                "DELETE", _url(entity_id), json={"pattern": "exclm-drop"}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["exclusion_patterns"] == ["exclm-keep"]
        assert await _stored_patterns(integration_session_factory, entity_id) == [
            "exclm-keep"
        ]

    async def test_remove_missing_pattern_returns_404(
        self, async_client: AsyncClient, seeded: uuid.UUID
    ) -> None:
        entity_id = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.request(
                "DELETE", _url(entity_id), json={"pattern": "exclm-absent"}
            )
        assert resp.status_code == 404, resp.text

    async def test_remove_empty_after_trim_returns_404(
        self, async_client: AsyncClient, seeded: uuid.UUID
    ) -> None:
        # Empty-after-trim is never in the list, so remove reports 404 (unlike
        # add, which rejects an empty pattern with 409).
        entity_id = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.request(
                "DELETE", _url(entity_id), json={"pattern": "   "}
            )
        assert resp.status_code == 404, resp.text

    async def test_remove_unknown_entity_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.request(
                "DELETE", _url(uuid.uuid4()), json={"pattern": "exclm-x"}
            )
        assert resp.status_code == 404, resp.text

    async def test_remove_invalid_uuid_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.request(
                "DELETE",
                "/api/v1/entities/not-a-uuid/exclusion-patterns",
                json={"pattern": "exclm-x"},
            )
        assert resp.status_code == 404, resp.text
