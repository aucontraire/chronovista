"""US1: the association video_count means the same thing on list and detail.

Against a real Postgres. The integration database is never reset, so every
assertion is keyed on the entity this test seeds — never a global total
(project integration-db shared-state rule).

T008 — a tag-only entity (linked through a canonical tag, zero mentions) must
report the same non-zero video_count from the list and the detail, and the
breakdown must show it under `tag`, nowhere else. Before Feature 066 the list
read a mention-only column and showed 0 while the detail showed the real number.

T009 — an entity matched by two different visible names (its canonical name and
an alias) in the SAME video's description contributes exactly one to the count
(distinct videos; FR-003) and one to the description breakdown, not two. (The DB
forbids two *identical* description mentions via a unique constraint, so the real
double-count is exactly this multi-text-variant case — the 5,610 pairs measured
in production.)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from httpx import AsyncClient
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

_PFX = "assoc066"


def _uid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


async def _seed_channel_and_videos(
    factory: async_sessionmaker[AsyncSession], vids: list[str]
) -> None:
    channel_id = f"UC{_PFX}CountChan00000"[:24]
    async with factory() as s:
        if await s.get(ChannelDB, channel_id) is None:
            s.add(ChannelDB(channel_id=channel_id, title="Assoc066 Count Channel"))
            await s.commit()
        for vid in vids:
            if await s.get(VideoDB, vid) is None:
                s.add(
                    VideoDB(
                        video_id=vid,
                        channel_id=channel_id,
                        title=f"Assoc066 {vid}",
                        upload_date=datetime(2026, 1, 1, tzinfo=UTC),
                        duration=60,
                        availability_status="available",
                    )
                )
        await s.commit()


async def _detail_count(client: AsyncClient, entity_id: uuid.UUID) -> dict[str, Any]:
    r = await client.get(f"/api/v1/entities/{entity_id}")
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _list_row(
    client: AsyncClient, entity_id: uuid.UUID, search: str
) -> dict[str, Any]:
    r = await client.get("/api/v1/entities", params={"search": search, "limit": 200})
    assert r.status_code == 200, r.text
    rows = [row for row in r.json()["data"] if row["entity_id"] == str(entity_id)]
    assert len(rows) == 1, f"entity not found exactly once in list: {len(rows)}"
    return rows[0]


class TestTagOnlyEntityCountAgrees:
    async def test_list_and_detail_agree_for_a_tag_only_entity(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vids = [f"{_PFX}tovid{i}"[:20] for i in range(3)]
        await _seed_channel_and_videos(integration_session_factory, vids)

        entity_id = _uid()
        tag_id = _uid()
        name = f"Assoc066 TagOnly {entity_id.hex}"
        raw = f"{_PFX} tag only form {entity_id.hex}"

        async with integration_session_factory() as s:
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
                    video_count=len(vids),
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
            for order, vid in enumerate(vids):
                s.add(VideoTagDB(video_id=vid, tag=raw, tag_order=order))
            await s.commit()

        detail = await _detail_count(async_client, entity_id)
        row = await _list_row(async_client, entity_id, name)

        # The core invariant: identical, and non-zero (the pre-066 bug was 0 here).
        assert detail["video_count"] == len(vids)
        assert row["video_count"] == detail["video_count"]
        # Attributed to tag, nowhere else — this entity has no mentions.
        assert detail["by_source"]["tag"] == len(vids)
        assert detail["by_source"]["transcript"] == 0
        assert detail["by_source"]["title"] == 0
        assert detail["by_source"]["description"] == 0
        assert row["by_source"] == detail["by_source"]


class TestDescriptionRepetitionIsPresence:
    async def test_a_name_twice_in_one_description_counts_once(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vid = f"{_PFX}descvid1"[:20]
        await _seed_channel_and_videos(integration_session_factory, [vid])

        entity_id = _uid()
        name = f"Assoc066 DescRepeat {entity_id.hex}"
        alias = f"Assoc066 DR Alias {entity_id.hex}"

        async with integration_session_factory() as s:
            s.add(
                NamedEntityDB(
                    id=entity_id,
                    canonical_name=name,
                    canonical_name_normalized=name.lower(),
                    entity_type="person",
                    status="active",
                )
            )
            s.add(
                EntityAliasDB(
                    id=_uid(),
                    entity_id=entity_id,
                    alias_name=alias,
                    alias_name_normalized=alias.lower(),
                    alias_type="name_variant",
                )
            )
            await s.commit()
            # Two DIFFERENT visible names (canonical + alias) in the SAME video's
            # description — both pass the visible-name filter, and the DB unique
            # constraint permits them because their text differs.
            for text in (name, alias):
                s.add(
                    EntityMentionDB(
                        id=_uid(),
                        entity_id=entity_id,
                        video_id=vid,
                        mention_text=text,
                        mention_source="description",
                        detection_method="rule_match",
                    )
                )
            await s.commit()

        detail = await _detail_count(async_client, entity_id)
        row = await _list_row(async_client, entity_id, name)

        # Two description rows, one video → count of 1, not 2.
        assert detail["video_count"] == 1
        assert detail["by_source"]["description"] == 1
        assert row["video_count"] == 1
        assert row["by_source"] == detail["by_source"]
