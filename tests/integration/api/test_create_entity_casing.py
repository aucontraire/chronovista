"""Integration tests for standalone entity-create casing (Feature 057, T032; US3).

Verifies that an explicitly-provided entity ``name`` is stored verbatim as
``canonical_name`` (no ``str.title()`` flattening) — FR-012 / SC-007.

Requires the integration database (chronovista_integration_test). Each test
cleans up the entities it creates in FK-reverse order.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

_NORMALIZED_NAMES = ["bell hooks", "iphone"]


@pytest.fixture
async def cleanup_created_entities(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[None, None]:
    """Remove entities created by the casing tests (aliases first)."""
    yield
    async with integration_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(NamedEntityDB.id).where(
                        NamedEntityDB.canonical_name_normalized.in_(_NORMALIZED_NAMES)
                    )
                )
            )
            .scalars()
            .all()
        )
        for entity_id in rows:
            await session.execute(
                delete(EntityAliasDB).where(EntityAliasDB.entity_id == entity_id)
            )
        await session.execute(
            delete(NamedEntityDB).where(
                NamedEntityDB.canonical_name_normalized.in_(_NORMALIZED_NAMES)
            )
        )
        await session.commit()


class TestCreateEntityCasing:
    @pytest.mark.parametrize(
        "typed_name",
        ["bell hooks", "iPhone"],
    )
    async def test_name_stored_verbatim(
        self,
        async_client: AsyncClient,
        cleanup_created_entities: None,
        integration_session_factory: async_sessionmaker[AsyncSession],
        typed_name: str,
    ) -> None:
        """POST /entities stores an intentional-casing name exactly as typed."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/entities",
                json={"name": typed_name, "entity_type": "organization"},
            )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["canonical_name"] == typed_name

        # Verify persisted value is verbatim (not title-cased).
        async with integration_session_factory() as session:
            entity = (
                await session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == body["entity_id"])
                )
            ).scalar_one()
            assert entity.canonical_name == typed_name
