"""Integration tests for PATCH /api/v1/entities/{id}/aliases/{alias_id} (#177).

An alias that is also an ordinary word matches every occurrence of that word.
This endpoint lets a human mark one alias as exact-cased after reading the
evidence — never a default, never inferred.

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

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

_PREFIX = "acs177"
_NORMS = [f"{_PREFIX} primary", f"{_PREFIX} other"]


def _url(entity_id: uuid.UUID, alias_id: uuid.UUID) -> str:
    return f"/api/v1/entities/{entity_id}/aliases/{alias_id}"


async def _purge(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        ids = (
            (
                await session.execute(
                    select(NamedEntityDB.id).where(
                        NamedEntityDB.canonical_name_normalized.in_(_NORMS)
                    )
                )
            )
            .scalars()
            .all()
        )
        if ids:
            await session.execute(
                delete(EntityAliasDB).where(EntityAliasDB.entity_id.in_(list(ids)))
            )
            await session.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id.in_(list(ids)))
            )
        await session.commit()


async def _seed(
    factory: async_sessionmaker[AsyncSession],
    *,
    normalized: str,
    alias_name: str,
) -> tuple[uuid.UUID, uuid.UUID]:
    entity_id = uuid.uuid4()
    alias_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            create_named_entity_db(
                id=entity_id,
                canonical_name=normalized.title(),
                canonical_name_normalized=normalized,
                entity_type="person",
            )
        )
        await session.flush()
        session.add(
            EntityAliasDB(
                id=alias_id,
                entity_id=entity_id,
                alias_name=alias_name,
                alias_name_normalized=alias_name.lower(),
                alias_type="name_variant",
                occurrence_count=0,
            )
        )
        await session.commit()
    return entity_id, alias_id


@pytest.fixture
async def seeded(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[tuple[uuid.UUID, uuid.UUID], None]:
    await _purge(integration_session_factory)
    pair = await _seed(
        integration_session_factory,
        normalized=f"{_PREFIX} primary",
        alias_name="Ordinaryword",
    )
    yield pair
    await _purge(integration_session_factory)


def _auth():  # type: ignore[no-untyped-def]
    return patch("chronovista.api.deps.youtube_oauth")


class TestAliasCaseSensitivityEndpoint:
    async def test_defaults_to_case_insensitive(
        self,
        async_client: AsyncClient,
        seeded: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        # A newly created alias must behave exactly as aliases always have.
        entity_id, _ = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.get(f"/api/v1/entities/{entity_id}")
        assert resp.status_code == 200, resp.text
        aliases = resp.json()["data"]["aliases"]
        assert aliases, "seeded alias should be returned"
        assert aliases[0]["case_sensitive"] is False

    async def test_enabling_persists_and_is_returned(
        self,
        async_client: AsyncClient,
        seeded: tuple[uuid.UUID, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id, alias_id = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(entity_id, alias_id), json={"case_sensitive": True}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["case_sensitive"] is True

        async with integration_session_factory() as session:
            alias = (
                await session.execute(
                    select(EntityAliasDB).where(EntityAliasDB.id == alias_id)
                )
            ).scalar_one()
            assert alias.case_sensitive is True

    async def test_toggling_back_off_works(
        self,
        async_client: AsyncClient,
        seeded: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        # Reversible: a wrong call is a mistake, not a trap.
        entity_id, alias_id = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            await async_client.patch(
                _url(entity_id, alias_id), json={"case_sensitive": True}
            )
            resp = await async_client.patch(
                _url(entity_id, alias_id), json={"case_sensitive": False}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["case_sensitive"] is False

    async def test_alias_belonging_to_another_entity_is_404(
        self,
        async_client: AsyncClient,
        seeded: tuple[uuid.UUID, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # The ownership check is what makes the path meaningful. Without it an
        # alias is reachable through any entity's URL, and a mismatched pair
        # silently succeeds instead of 404ing.
        _, alias_id = seeded
        other_entity_id, _ = await _seed(
            integration_session_factory,
            normalized=f"{_PREFIX} other",
            alias_name="Unrelated",
        )

        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(other_entity_id, alias_id), json={"case_sensitive": True}
            )
        assert resp.status_code == 404, resp.text

        # And the alias must be untouched by the rejected call.
        async with integration_session_factory() as session:
            alias = (
                await session.execute(
                    select(EntityAliasDB).where(EntityAliasDB.id == alias_id)
                )
            ).scalar_one()
            assert alias.case_sensitive is False

    async def test_unknown_entity_is_404(
        self, async_client: AsyncClient, seeded: tuple[uuid.UUID, uuid.UUID]
    ) -> None:
        _, alias_id = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(uuid.uuid4(), alias_id), json={"case_sensitive": True}
            )
        assert resp.status_code == 404, resp.text

    async def test_unknown_alias_is_404(
        self, async_client: AsyncClient, seeded: tuple[uuid.UUID, uuid.UUID]
    ) -> None:
        entity_id, _ = seeded
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(entity_id, uuid.uuid4()), json={"case_sensitive": True}
            )
        assert resp.status_code == 404, resp.text
