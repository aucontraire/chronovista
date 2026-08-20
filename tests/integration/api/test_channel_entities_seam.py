"""Cross-seam test: channel entity panel count == pinned /videos result (Feature 070, T013+T014).

Constitution (Cross-Feature Data Contract): the panel's per-entity
``channel_video_count`` from ``GET /channels/{C}/entities`` MUST equal the row
count of the pinned filter ``GET /videos?channel_id=C&entity_id=E&include_unavailable=true``
for **every** entity on the channel (FR-007 / SC-006). Both sides resolve
associations through the one Feature 066 definition (mentions plus tags,
tag-inclusive since #260), so they agree by construction — this test locks it on
a real DB, including a **tag-only** video and an **unavailable** video, and
mutation-verifies that the ``include_unavailable=true`` flag is load-bearing.

Against the shared, never-reset integration DB: entity names are left to the
factory (unique per run) and every assertion keys on the ids this test seeds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

from tests.factories.entity_association_orm_factory import (
    seed_alias_tag_association,
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


_CH = _cid("s070Seam")
_OTHER = _cid("s070Dec")

# Channel videos: two available, one unavailable.
_AV1 = "s070av1"
_AV2 = "s070av2"
_UV1 = "s070uv1"
_DECOY = "s070decoy1"  # on another channel


async def _seed(factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    """Seed a channel spanning mention / tag-only / alias-tag / unavailable cases.

    Returns entity ids by role. Expected channel_video_count (all-videos basis):
    mention=2 (av1,av2), tag_only=1 (av1), alias=1 (av2), unavailable=2 (av1,uv1).
    """
    async with factory() as s:
        await seed_channel_with_videos(
            s,
            channel_id=_CH,
            available=[_AV1, _AV2],
            unavailable=[_UV1],
            channel_title="S070 Seam Channel",
        )
        await seed_channel_with_videos(
            s, channel_id=_OTHER, available=[_DECOY], channel_title="S070 Decoy Channel"
        )
    async with factory() as s:
        mention = await seed_mention_association(s, video_ids=[_AV1, _AV2])
        tag_only = await seed_tag_only_association(s, video_ids=[_AV1])
        alias = await seed_alias_tag_association(s, video_ids=[_AV2])
        # Associated on an available AND an unavailable channel video: its
        # all-videos channel count (2) exceeds the default /videos count (1).
        unavailable = await seed_mention_association(s, video_ids=[_AV1, _UV1])
        # A decoy entity on another channel's video, so channel scoping is testable.
        decoy = await seed_tag_only_association(s, video_ids=[_DECOY])
    return {
        "mention": str(mention.id),
        "tag_only": str(tag_only.id),
        "alias": str(alias.id),
        "unavailable": str(unavailable.id),
        "decoy": str(decoy.id),
    }


async def _pinned_count(
    client: AsyncClient, entity_id: str, *, include_unavailable: bool
) -> int:
    params: dict[str, str | int] = {
        "channel_id": _CH,
        "entity_id": entity_id,
        "limit": 100,
    }
    if include_unavailable:
        params["include_unavailable"] = "true"
    r = await client.get("/api/v1/videos", params=params)
    assert r.status_code == 200, r.text
    return int(r.json()["pagination"]["total"])


class TestChannelEntitiesSeam:
    async def test_panel_count_equals_pinned_videos_for_every_entity(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """SC-006 sweep: panel channel_video_count == pinned /videos count, per entity."""
        ids = await _seed(integration_session_factory)

        r = await async_client.get(f"/api/v1/channels/{_CH}/entities")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        by_id = {i["entity_id"]: i for i in items}

        # Every seeded (non-decoy) entity is on the panel.
        for role in ("mention", "tag_only", "alias", "unavailable"):
            assert ids[role] in by_id, (role, r.json())
        # The decoy (only on another channel) is NOT on this channel's panel.
        assert ids["decoy"] not in by_id

        # The load-bearing sweep: for EVERY entity the panel lists, its
        # channel_video_count equals the pinned /videos row count (with the
        # mandatory include_unavailable=true). Not just one entity — all of them.
        for entity_id, item in by_id.items():
            pinned = await _pinned_count(
                async_client, entity_id, include_unavailable=True
            )
            assert pinned == item["channel_video_count"], (entity_id, item)

        # Spot-check the seeded expectations (mention=2, tag_only=1, alias=1,
        # unavailable=2) so a uniformly-wrong-both-sides bug can't pass the sweep.
        assert by_id[ids["mention"]]["channel_video_count"] == 2
        assert by_id[ids["tag_only"]]["channel_video_count"] == 1
        assert by_id[ids["alias"]]["channel_video_count"] == 1
        assert by_id[ids["unavailable"]]["channel_video_count"] == 2

    async def test_include_unavailable_flag_is_load_bearing(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Mutation-verify: drop include_unavailable=true and the seam breaks.

        The 'unavailable' entity is associated with one available and one
        unavailable channel video. The panel counts both (all-videos basis); the
        pinned /videos count matches ONLY with include_unavailable=true. Without
        the flag it drops the unavailable video, so the pinned count is strictly
        less than the panel count — proving the flag is mandatory (the earlier
        seam-review finding).
        """
        ids = await _seed(integration_session_factory)
        r = await async_client.get(f"/api/v1/channels/{_CH}/entities")
        panel = {i["entity_id"]: i for i in r.json()["items"]}
        eid = ids["unavailable"]
        panel_count = panel[eid]["channel_video_count"]
        assert panel_count == 2

        with_flag = await _pinned_count(async_client, eid, include_unavailable=True)
        without_flag = await _pinned_count(async_client, eid, include_unavailable=False)

        assert with_flag == panel_count  # agreement holds with the flag
        assert without_flag < panel_count  # and breaks without it (drops uv1)
        assert without_flag == 1

    async def test_channel_id_scopes_and_composes_with_entity_and(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """T013: channel_id scopes /videos; composes with the entity_id AND-intersection."""
        ids = await _seed(integration_session_factory)

        # channel_id alone (include_unavailable) returns exactly this channel's
        # three videos — and never the decoy on another channel (FR-014 scoping).
        r = await async_client.get(
            "/api/v1/videos",
            params={"channel_id": _CH, "include_unavailable": "true", "limit": 100},
        )
        assert r.status_code == 200, r.text
        returned = {row["video_id"] for row in r.json()["data"]}
        assert {_AV1, _AV2, _UV1} <= returned
        assert _DECOY not in returned

        # channel_id + entity_id AND: mention {av1,av2} ∩ alias {av2} = {av2}.
        both = await async_client.get(
            "/api/v1/videos",
            params={
                "channel_id": _CH,
                "entity_id": [ids["mention"], ids["alias"]],
                "include_unavailable": "true",
                "limit": 100,
            },
        )
        assert both.status_code == 200, both.text
        both_ids = {row["video_id"] for row in both.json()["data"]}
        assert both_ids == {_AV2}

        # AND never broadens: the pair count <= each single-entity count.
        mention_only = await _pinned_count(
            async_client, ids["mention"], include_unavailable=True
        )
        assert both.json()["pagination"]["total"] <= mention_only
