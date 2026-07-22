"""Integration tests for POST /api/v1/entities/operations/{id}/undo (Feature 057, T011).

Verifies that undoing a logged entity edit restores the previous values and
that a second undo of the same operation returns 409 (already rolled back).

Requires the integration database (chronovista_integration_test).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityOperationLog as EntityOperationLogDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

_NORM = "ect057undo openai"


async def _purge(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        await session.execute(
            delete(NamedEntityDB).where(
                NamedEntityDB.canonical_name_normalized == _NORM
            )
        )
        await session.commit()


@pytest.fixture
async def seed_entity(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[uuid.UUID, None]:
    await _purge(integration_session_factory)
    entity_id = uuid.uuid4()
    async with integration_session_factory() as session:
        session.add(
            create_named_entity_db(
                id=entity_id,
                canonical_name="Ect057undo Openai",
                canonical_name_normalized=_NORM,
                entity_type="organization",
                description="before",
            )
        )
        await session.commit()
    yield entity_id
    await _purge(integration_session_factory)


async def _latest_operation_id(
    factory: async_sessionmaker[AsyncSession], entity_id: uuid.UUID
) -> uuid.UUID:
    async with factory() as session:
        log = (
            await session.execute(
                select(EntityOperationLogDB)
                .where(EntityOperationLogDB.entity_id == entity_id)
                .order_by(desc(EntityOperationLogDB.performed_at))
                .limit(1)
            )
        ).scalar_one()
        return log.id


class TestUndoEntityOperation:
    async def test_undo_restores_previous_values(
        self,
        async_client: AsyncClient,
        seed_entity: uuid.UUID,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Rename (casing) and change the description.
            patch_resp = await async_client.patch(
                f"/api/v1/entities/{seed_entity}",
                json={"canonical_name": "Ect057undo OpenAI", "description": "after"},
            )
            assert patch_resp.status_code == 200, patch_resp.text

            operation_id = await _latest_operation_id(
                integration_session_factory, seed_entity
            )

            undo_resp = await async_client.post(
                f"/api/v1/entities/operations/{operation_id}/undo"
            )
        assert undo_resp.status_code == 200, undo_resp.text
        data = undo_resp.json()["data"]
        assert data["canonical_name"] == "Ect057undo Openai"
        assert data["description"] == "before"

        async with integration_session_factory() as session:
            entity = (
                await session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == seed_entity)
                )
            ).scalar_one()
            assert entity.canonical_name == "Ect057undo Openai"
            assert entity.description == "before"

    async def test_double_undo_409(
        self,
        async_client: AsyncClient,
        seed_entity: uuid.UUID,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            patch_resp = await async_client.patch(
                f"/api/v1/entities/{seed_entity}",
                json={"canonical_name": "Ect057undo OpenAI"},
            )
            assert patch_resp.status_code == 200, patch_resp.text
            operation_id = await _latest_operation_id(
                integration_session_factory, seed_entity
            )
            first = await async_client.post(
                f"/api/v1/entities/operations/{operation_id}/undo"
            )
            assert first.status_code == 200, first.text
            second = await async_client.post(
                f"/api/v1/entities/operations/{operation_id}/undo"
            )
        assert second.status_code == 409, second.text

    async def test_unknown_operation_404(
        self,
        async_client: AsyncClient,
    ) -> None:
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.post(
                f"/api/v1/entities/operations/{uuid.uuid4()}/undo"
            )
        assert resp.status_code == 404, resp.text
