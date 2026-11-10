"""Endpoint tests for the channel-ownership surface (ownership promotion, read-path).

Covers GET /channels/{channel_id}/operators and GET /entities/{entity_id}/channels
against the real (shared, never-reset) integration DB via ASGITransport. Per the
project integration-db shared-state rule, assertions key on the ids/channel THIS test
seeds — never a global count. Seeds the imported ``youtube_channel_id`` identifier block
directly into ``named_entities.properties`` (no schema change — that is the whole point).

Covers: an organization operator surfaces (ownership is NOT person-scoped); the
entity-side in-library vs external distinction; empty states; and the 404 paths
(unknown channel, malformed entity id, unknown entity).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

from tests.factories.entity_association_orm_factory import seed_channel_with_videos
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


def _cid(suffix: str) -> str:
    """A valid, exactly-24-char channel id from a short unique suffix."""
    return ("UC" + suffix + "0" * 24)[:24]


_CH_OWNED = _cid("ownOwned")  # in-library channel with an operator
_CH_EXTERNAL = _cid("ownExt")  # NOT seeded in the library (external link)
_CH_NOOP = _cid("ownNoop")  # in-library channel with no operator
_CH_UNKNOWN = _cid("ownNope")  # never created


async def _seed_channel(
    factory: async_sessionmaker[AsyncSession], channel_id: str
) -> None:
    async with factory() as s:
        await seed_channel_with_videos(
            s,
            channel_id=channel_id,
            available=[],
            channel_title="Ownership Test Channel",
        )


async def _seed_owner_entity(
    factory: async_sessionmaker[AsyncSession],
    *,
    channel_values: list[str],
    entity_type: str = "organization",
    with_identifier: bool = True,
) -> uuid.UUID:
    """Seed one active entity whose stored youtube_channel_id operates ``channel_values``.

    Returns the entity id. Names embed the id so the never-reset DB never collides on
    ``uq_named_entity_canonical``.
    """
    eid = uuid.uuid4()
    name = f"Ownership Test Entity {eid.hex}"
    props = (
        {
            "youtube_channel_id": {
                "values": channel_values,
                "source": "wikidata",
                "set_at": "2026-09-14T00:00:00+00:00",
            }
        }
        if with_identifier
        else {}
    )
    async with factory() as s:
        s.add(
            create_named_entity_db(
                id=eid,
                canonical_name=name,
                canonical_name_normalized=name.lower(),
                entity_type=entity_type,
                status="active",
                properties=props,
            )
        )
        await s.commit()
    return eid


class TestChannelOperatorsEndpoint:
    async def test_returns_operator_not_person_scoped(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _seed_channel(integration_session_factory, _CH_OWNED)
        eid = await _seed_owner_entity(
            integration_session_factory,
            channel_values=[_CH_OWNED],
            entity_type="organization",  # an ORG operator — ownership is not person-scoped
        )

        r = await async_client.get(f"/api/v1/channels/{_CH_OWNED}/operators")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["channel_id"] == _CH_OWNED
        by_id = {i["entity_id"]: i for i in body["items"]}
        assert str(eid) in by_id, body  # key on the seeded id (shared DB)
        item = by_id[str(eid)]
        assert set(item) == {"entity_id", "entity_type", "canonical_name"}
        assert item["entity_type"] == "organization"
        assert body["total_entities"] == len(body["items"])

    async def test_unknown_channel_returns_404_problem_json(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.get(f"/api/v1/channels/{_CH_UNKNOWN}/operators")
        assert r.status_code == 404
        assert "application/problem+json" in r.headers.get("content-type", "")
        assert r.json().get("status") == 404

    async def test_known_channel_no_operator_returns_200_empty(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _seed_channel(integration_session_factory, _CH_NOOP)
        r = await async_client.get(f"/api/v1/channels/{_CH_NOOP}/operators")
        assert r.status_code == 200, r.text
        body = r.json()
        # This channel id is unique to this test and nothing ever seeds an operator for
        # it, so the list is deterministically empty even on the shared, never-reset DB.
        assert body["items"] == []
        assert body["total_entities"] == 0


class TestEntityChannelsEndpoint:
    async def test_in_library_channel_has_title_and_flag(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _seed_channel(integration_session_factory, _CH_OWNED)
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[_CH_OWNED]
        )

        r = await async_client.get(f"/api/v1/entities/{eid}/channels")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        # This entity operates exactly the one seeded channel.
        links = {d["channel_id"]: d for d in data}
        assert _CH_OWNED in links, data
        link = links[_CH_OWNED]
        assert link["in_library"] is True
        assert link["title"] == "Ownership Test Channel"

    async def test_external_channel_flagged_not_in_library(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # The channel id is NOT seeded into the library (an external link).
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[_CH_EXTERNAL]
        )
        r = await async_client.get(f"/api/v1/entities/{eid}/channels")
        assert r.status_code == 200, r.text
        links = {d["channel_id"]: d for d in r.json()["data"]}
        assert _CH_EXTERNAL in links, links
        assert links[_CH_EXTERNAL]["in_library"] is False
        assert links[_CH_EXTERNAL]["title"] is None

    async def test_entity_without_identifier_returns_empty(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        r = await async_client.get(f"/api/v1/entities/{eid}/channels")
        assert r.status_code == 200, r.text
        assert r.json()["data"] == []

    async def test_malformed_entity_id_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.get("/api/v1/entities/not-a-uuid/channels")
        assert r.status_code == 404
        assert "application/problem+json" in r.headers.get("content-type", "")

    async def test_unknown_entity_returns_404(self, async_client: AsyncClient) -> None:
        r = await async_client.get(f"/api/v1/entities/{uuid.uuid4()}/channels")
        assert r.status_code == 404
        assert r.json().get("status") == 404
