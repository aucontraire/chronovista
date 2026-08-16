"""Feature 066 T026: one (entity, video) pair, consistent across every surface.

Against a real Postgres. Assertions are keyed on the entity/video this test
seeds (project integration-db rule).

This is the single test whose absence let #169 (list vs detail disagreeing on
video_count) and #240 (tag-only associations invisible on the video panel)
ship. It seeds ONE entity with a tag-only association to ONE video and asserts
all four surfaces agree by construction (FR-016, SC-006):

1. entity list        GET /api/v1/entities
2. entity detail      GET /api/v1/entities/{id}
3. video panel        GET /api/v1/videos/{id}/entities
4. provenance filter  GET /api/v1/entities/{id}/videos?source=...
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB

pytestmark = pytest.mark.asyncio

_PFX = "xview066"


def _uid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


class TestCrossViewConsistency:
    async def test_tag_only_pair_consistent_on_all_four_surfaces(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vid = f"{_PFX}v1"[:20]
        channel_id = f"UC{_PFX}Chan0000000000"[:24]
        entity_id = _uid()
        tag_id = _uid()
        name = f"Xview066 Entity {entity_id.hex}"
        raw = f"{_PFX} form {entity_id.hex}"

        async with integration_session_factory() as s:
            if await s.get(ChannelDB, channel_id) is None:
                s.add(ChannelDB(channel_id=channel_id, title="Xview066 Channel"))
                await s.commit()
            if await s.get(VideoDB, vid) is None:
                s.add(
                    VideoDB(
                        video_id=vid,
                        channel_id=channel_id,
                        title=f"Xview066 {vid}",
                        upload_date=datetime(2026, 1, 1, tzinfo=UTC),
                        duration=60,
                        availability_status="available",
                    )
                )
            s.add(
                NamedEntityDB(
                    id=entity_id,
                    canonical_name=name,
                    canonical_name_normalized=name.lower(),
                    entity_type="organization",
                    status="active",
                )
            )
            s.add(
                CanonicalTagDB(
                    id=tag_id,
                    canonical_form=raw,
                    normalized_form=raw,
                    alias_count=1,
                    video_count=1,
                    status="active",
                    entity_id=entity_id,
                    entity_type="organization",
                )
            )
            await s.commit()
            s.add(
                TagAliasDB(
                    id=_uid(),
                    raw_form=raw,
                    normalized_form=raw,
                    canonical_tag_id=tag_id,
                    creation_method="auto_normalize",
                    occurrence_count=1,
                )
            )
            s.add(VideoTagDB(video_id=vid, tag=raw, tag_order=0))
            await s.commit()

        # 1. Entity LIST
        lr = await async_client.get(
            "/api/v1/entities", params={"search": name, "limit": 200}
        )
        assert lr.status_code == 200, lr.text
        list_rows = [r for r in lr.json()["data"] if r["entity_id"] == str(entity_id)]
        assert len(list_rows) == 1
        list_row = list_rows[0]

        # 2. Entity DETAIL
        dr = await async_client.get(f"/api/v1/entities/{entity_id}")
        assert dr.status_code == 200, dr.text
        detail = dr.json()["data"]

        # #169: list and detail agree, and are non-zero, on the combined count.
        assert list_row["video_count"] == detail["video_count"] == 1
        assert list_row["by_source"] == detail["by_source"]
        assert detail["by_source"]["tag"] == 1
        assert detail["by_source"]["transcript"] == 0

        # 3. Video PANEL — #240: the tag-only entity is visible on the video side.
        pr = await async_client.get(f"/api/v1/videos/{vid}/entities")
        assert pr.status_code == 200, pr.text
        panel_row = next(
            (r for r in pr.json()["data"] if r["entity_id"] == str(entity_id)), None
        )
        assert panel_row is not None
        assert panel_row["sources"] == ["tag"]

        # 4. Provenance FILTER — the pair is under 'tag', and only 'tag'.
        async def _filtered(source: str) -> set[str]:
            fr = await async_client.get(
                f"/api/v1/entities/{entity_id}/videos",
                params={"source": source, "limit": 100},
            )
            assert fr.status_code == 200, fr.text
            return {row["video_id"] for row in fr.json()["data"]}

        assert vid in await _filtered("tag")
        assert vid not in await _filtered("transcript")
