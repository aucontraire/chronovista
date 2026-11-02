"""Adding ``product`` drops no entity from any list/filter (Feature 103, US3 — SC-002).

The risk a new enum value introduces is a consumer that silently drops rows it does not
recognize. This seeds entities of several types (including ``product``) under a unique name
prefix and asserts: the unfiltered list returns all of them (none dropped), and each type filter
returns exactly its own partition — ``product`` appears only under ``?type=product``.

No library content: fictional placeholder names and a universal class QID only.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.enums import ENTITY_PRODUCING_TYPES

pytestmark = pytest.mark.asyncio

_PREFIX = "pt reach"  # unique search prefix for this file's seeded entities
# One entity of EVERY entity-producing type (incl. product), so SC-002 is tested across the whole
# vocabulary and auto-covers any future type.
_SEED = {etype: f"{_PREFIX} {etype}" for etype in ENTITY_PRODUCING_TYPES}


class TestProductListReachability:
    @pytest.fixture
    async def seeded(
        self, integration_session_factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[dict[str, uuid.UUID], None]:
        ids = {etype: uuid.uuid4() for etype in _SEED}

        async def _wipe(session: AsyncSession) -> None:
            await session.execute(
                delete(EntityAliasDB).where(
                    EntityAliasDB.entity_id.in_(list(ids.values()))
                )
            )
            await session.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id.in_(list(ids.values())))
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)
            for etype, name in _SEED.items():
                session.add(
                    NamedEntityDB(
                        id=ids[etype],
                        canonical_name=name,
                        canonical_name_normalized=name,
                        entity_type=etype,
                    )
                )
            await session.commit()
        yield ids
        async with integration_session_factory() as session:
            await _wipe(session)

    async def _ids(self, client: AsyncClient, params: dict[str, str]) -> set[str]:
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await client.get("/api/v1/entities", params=params)
        assert resp.status_code == 200, resp.text
        return {e["entity_id"] for e in resp.json()["data"]}

    async def test_unfiltered_drops_no_entity(
        self, async_client: AsyncClient, seeded: dict[str, uuid.UUID]
    ) -> None:
        # Unfiltered (by type) search returns ALL seeded entities — the product one is not dropped.
        found = await self._ids(async_client, {"search": _PREFIX, "limit": "200"})
        for etype, eid in seeded.items():
            assert str(eid) in found, f"{etype} entity dropped from unfiltered list"

    async def test_type_filters_partition_correctly(
        self, async_client: AsyncClient, seeded: dict[str, uuid.UUID]
    ) -> None:
        # Fetch each type's filtered id-set once, then assert each seeded entity appears only
        # under its own type filter (a leak in either direction fails).
        by_type = {
            etype: await self._ids(
                async_client, {"search": _PREFIX, "type": etype, "limit": "200"}
            )
            for etype in _SEED
        }
        for etype, eid in seeded.items():
            assert (
                str(eid) in by_type[etype]
            ), f"{etype} entity missing from ?type={etype}"
            for other, ids in by_type.items():
                if other == etype:
                    continue
                assert str(eid) not in ids, f"{etype} entity leaked into ?type={other}"
