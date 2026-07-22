"""Integration tests for PATCH /api/v1/entities/{id} (Feature 057, T009; US1).

Covers name edit, description-only edit, casing-only success, typo rename,
400 (empty / normalizes-to-empty), 404, and 409 collision (nothing mutated).

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

_PREFIX = "ect057upd"
_NORMS = [
    f"{_PREFIX} openai",
    f"{_PREFIX} anthropic",
    f"{_PREFIX} dupe",
    f"{_PREFIX} crosstype",
]


def _url(entity_id: str) -> str:
    return f"/api/v1/entities/{entity_id}"


async def _purge(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        await session.execute(
            delete(NamedEntityDB).where(
                NamedEntityDB.canonical_name_normalized.in_(_NORMS)
            )
        )
        await session.commit()


async def _seed_entity(
    factory: async_sessionmaker[AsyncSession],
    *,
    canonical_name: str,
    normalized: str,
    entity_type: str = "organization",
    description: str | None = "seed desc",
) -> uuid.UUID:
    entity_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            create_named_entity_db(
                id=entity_id,
                canonical_name=canonical_name,
                canonical_name_normalized=normalized,
                entity_type=entity_type,
                description=description,
            )
        )
        await session.commit()
    return entity_id


@pytest.fixture
async def seed_entity(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[uuid.UUID, None]:
    await _purge(integration_session_factory)
    entity_id = await _seed_entity(
        integration_session_factory,
        canonical_name="Ect057upd Openai",
        normalized=f"{_PREFIX} openai",
    )
    yield entity_id
    await _purge(integration_session_factory)


def _auth():  # type: ignore[no-untyped-def]
    m = patch("chronovista.api.deps.youtube_oauth")
    return m


class TestUpdateEntityEndpoint:
    async def test_casing_only_rename_200(
        self,
        async_client: AsyncClient,
        seed_entity: uuid.UUID,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(str(seed_entity)), json={"canonical_name": "Ect057upd OpenAI"}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["canonical_name"] == "Ect057upd OpenAI"

        async with integration_session_factory() as session:
            entity = (
                await session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == seed_entity)
                )
            ).scalar_one()
            # Casing-only change: normalized identity is unchanged.
            assert entity.canonical_name == "Ect057upd OpenAI"
            assert entity.canonical_name_normalized == f"{_PREFIX} openai"

    async def test_description_only_edit_200(
        self,
        async_client: AsyncClient,
        seed_entity: uuid.UUID,
    ) -> None:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(str(seed_entity)),
                json={"description": "A different description"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["description"] == "A different description"

    async def test_typo_rename_200(
        self,
        async_client: AsyncClient,
        seed_entity: uuid.UUID,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(str(seed_entity)), json={"canonical_name": "Ect057upd Anthropic"}
            )
        assert resp.status_code == 200, resp.text
        async with integration_session_factory() as session:
            entity = (
                await session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == seed_entity)
                )
            ).scalar_one()
            # Identity-changing rename: normalized recomputed together (INV-1).
            assert entity.canonical_name == "Ect057upd Anthropic"
            assert entity.canonical_name_normalized == f"{_PREFIX} anthropic"

    async def test_empty_name_400(
        self,
        async_client: AsyncClient,
        seed_entity: uuid.UUID,
    ) -> None:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(str(seed_entity)), json={"canonical_name": "   "}
            )
        assert resp.status_code == 400, resp.text

    async def test_normalizes_to_empty_400(
        self,
        async_client: AsyncClient,
        seed_entity: uuid.UUID,
    ) -> None:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(str(seed_entity)), json={"canonical_name": "###"}
            )
        assert resp.status_code == 400, resp.text

    async def test_unknown_entity_404(
        self,
        async_client: AsyncClient,
    ) -> None:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(str(uuid.uuid4())), json={"canonical_name": "Whatever"}
            )
        assert resp.status_code == 404, resp.text

    async def test_collision_409_nothing_mutated(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _purge(integration_session_factory)
        entity_a = await _seed_entity(
            integration_session_factory,
            canonical_name="Source Org",
            normalized=f"{_PREFIX} openai",
        )
        await _seed_entity(
            integration_session_factory,
            canonical_name="Ect057upd Dupe",
            normalized=f"{_PREFIX} dupe",
        )
        try:
            with _auth() as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                # New name normalizes to the dupe entity's normalized form.
                resp = await async_client.patch(
                    _url(str(entity_a)), json={"canonical_name": "Ect057upd Dupe"}
                )
            assert resp.status_code == 409, resp.text
            # Nothing mutated on entity A.
            async with integration_session_factory() as session:
                entity = (
                    await session.execute(
                        select(NamedEntityDB).where(NamedEntityDB.id == entity_a)
                    )
                ).scalar_one()
                assert entity.canonical_name == "Source Org"
                assert entity.canonical_name_normalized == f"{_PREFIX} openai"
        finally:
            await _purge(integration_session_factory)

    async def test_name_too_long_422(
        self,
        async_client: AsyncClient,
        seed_entity: uuid.UUID,
    ) -> None:
        # Spec Edge Case: over-length name is rejected before saving. The
        # UpdateEntityRequest schema caps canonical_name at 500 chars, so this
        # is a 422 (schema validation) rather than a 400 from the service.
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(str(seed_entity)), json={"canonical_name": "x" * 501}
            )
        assert resp.status_code == 422, resp.text

    async def test_description_too_long_422(
        self,
        async_client: AsyncClient,
        seed_entity: uuid.UUID,
    ) -> None:
        # Spec Edge Case: over-length description is rejected before saving.
        # The schema caps description at 5000 chars → 422 (schema validation).
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(str(seed_entity)), json={"description": "y" * 5001}
            )
        assert resp.status_code == 422, resp.text

    async def test_cross_type_name_match_allowed_200(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Edge Case / FR-005 scope: uniqueness is (normalized, entity_type).
        # Renaming an entity into a name whose normalized form already exists
        # under a DIFFERENT entity_type must succeed — guards the entity_type
        # filter in EntityCurationService._assert_no_collision.
        await _purge(integration_session_factory)
        # Existing PERSON entity owning the target normalized form.
        await _seed_entity(
            integration_session_factory,
            canonical_name="Ect057upd Crosstype Person",
            normalized=f"{_PREFIX} crosstype",
            entity_type="person",
        )
        # ORGANIZATION entity we will rename into the same normalized form.
        org_id = await _seed_entity(
            integration_session_factory,
            canonical_name="Ect057upd Openai",
            normalized=f"{_PREFIX} openai",
            entity_type="organization",
        )
        try:
            with _auth() as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                resp = await async_client.patch(
                    _url(str(org_id)),
                    json={"canonical_name": "Ect057upd Crosstype"},
                )
            assert resp.status_code == 200, resp.text
            async with integration_session_factory() as session:
                entity = (
                    await session.execute(
                        select(NamedEntityDB).where(NamedEntityDB.id == org_id)
                    )
                ).scalar_one()
                assert entity.canonical_name == "Ect057upd Crosstype"
                assert entity.canonical_name_normalized == f"{_PREFIX} crosstype"
                assert entity.entity_type == "organization"
        finally:
            await _purge(integration_session_factory)
