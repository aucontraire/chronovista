"""Endpoint tests for GET /channels/{channel_id}/entities (Feature 070 / #171, T007).

Against the real (shared, never-reset) integration DB via ASGITransport, so every
assertion is keyed on the entities/channel THIS test seeds — never a global total
(project integration-db shared-state rule).

Covers: response shape; distinctiveness ordering (SC-001); the >=2 floor marking a
1-video entity ``is_ranked=false`` (FR-008); unknown channel -> 404 problem+json
(FR-016); a known channel with no associated entities -> 200 empty (FR-012).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

from tests.factories.entity_association_orm_factory import (
    seed_channel_with_videos,
    seed_mention_association,
    seed_tag_only_association,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


def _cid(suffix: str) -> str:
    """A valid, exactly-24-char channel id from a short unique suffix."""
    return ("UC" + suffix + "0" * 24)[:24]


_CH = _cid("c070Ent")
_OTHER = _cid("c070Oth")
_EMPTY = _cid("c070Emp")
_UNKNOWN = _cid("c070Nope")


async def _seed(factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    """Seed one channel with a concentrated, a corpus-frequent, and a 1-video entity.

    Returns the three entities' ids by role. Entity names are left to the factory
    (unique per run) so the never-reset integration DB does not collide on
    ``uq_named_entity_canonical``; assertions therefore key on the returned ids,
    not on names.
    """
    async with factory() as s:
        await seed_channel_with_videos(
            s,
            channel_id=_CH,
            available=["c70ea1", "c70ea2", "c70ea3", "c70es1"],
            channel_title="C070 Entities Channel",
        )
        await seed_channel_with_videos(
            s,
            channel_id=_OTHER,
            available=[f"c70eo{i}" for i in range(1, 10)],
            channel_title="C070 Other Channel",
        )
    async with factory() as s:
        # CONCENTRATED: 2 channel videos, no others -> channel=2, corpus=2,
        # share=1.0 (ranked).
        concentrated = await seed_mention_association(s, video_ids=["c70ea1", "c70ea2"])
        # FREQUENT: 3 channel videos + 9 other -> channel=3, corpus=12,
        # share=0.25 (ranked). Higher raw count than CONCENTRATED but lower share.
        frequent = await seed_mention_association(
            s,
            video_ids=[
                "c70ea1",
                "c70ea2",
                "c70ea3",
                *[f"c70eo{i}" for i in range(1, 10)],
            ],
        )
        # SINGLE: exactly 1 channel video (tag-only) -> "also appears" (FR-008).
        single = await seed_tag_only_association(s, video_ids=["c70es1"])
    return {
        "concentrated": str(concentrated.id),
        "frequent": str(frequent.id),
        "single": str(single.id),
    }


class TestChannelEntitiesEndpoint:
    async def test_ranking_shape_and_order(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await _seed(integration_session_factory)

        r = await async_client.get(f"/api/v1/channels/{_CH}/entities")
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["channel_id"] == _CH
        by_id = {i["entity_id"]: i for i in body["items"]}
        # The three seeded entities are present (keyed on id — shared DB).
        for role in ("concentrated", "frequent", "single"):
            assert ids[role] in by_id, body

        # Response item shape.
        conc = by_id[ids["concentrated"]]
        assert set(conc) == {
            "entity_id",
            "display_name",
            "entity_type",
            "channel_video_count",
            "corpus_video_count",
            "share",
            "is_ranked",
        }
        assert (conc["channel_video_count"], conc["corpus_video_count"]) == (2, 2)
        assert conc["share"] == pytest.approx(1.0)
        assert conc["is_ranked"] is True

        freq = by_id[ids["frequent"]]
        assert (freq["channel_video_count"], freq["corpus_video_count"]) == (3, 12)
        assert freq["share"] == pytest.approx(0.25)

        # FR-008: the 1-channel-video entity is in the "also appears" group.
        assert by_id[ids["single"]]["is_ranked"] is False

        # SC-001: CONCENTRATED (share 1.0) precedes FREQUENT (share 0.25) despite
        # FREQUENT's higher raw count. Compare positions within THIS channel's list.
        order = [i["entity_id"] for i in body["items"]]
        assert order.index(ids["concentrated"]) < order.index(ids["frequent"])
        # A ranked entity precedes the also-appears one.
        assert order.index(ids["frequent"]) < order.index(ids["single"])

        # total_entities echoes len(items).
        assert body["total_entities"] == len(body["items"])

    async def test_unknown_channel_returns_404_problem_json(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.get(f"/api/v1/channels/{_UNKNOWN}/entities")
        assert r.status_code == 404
        assert "application/problem+json" in r.headers.get("content-type", "")
        body = r.json()
        assert body.get("status") == 404

    async def test_known_channel_no_entities_returns_200_empty(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with integration_session_factory() as s:
            await seed_channel_with_videos(
                s,
                channel_id=_EMPTY,
                available=["c70eempty1"],
                channel_title="C070 Empty Channel",
            )

        r = await async_client.get(f"/api/v1/channels/{_EMPTY}/entities")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["channel_id"] == _EMPTY
        assert body["items"] == []
        assert body["total_entities"] == 0
