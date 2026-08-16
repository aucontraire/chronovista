"""US2: the video panel and the entity detail agree on membership.

Against a real Postgres. The integration database is never reset, so every
assertion is keyed on the entity/video this test seeds — never a global total
(project integration-db shared-state rule).

T013 — a tag-only (entity, video) pair, with no mentions of any kind, must be
listed on BOTH the video's entities panel (`GET /videos/{id}/entities`) and the
entity's video list (`GET /entities/{id}/videos`). Before Feature 066 the video
panel was mentions-only, so the pair was visible on the entity side and INVISIBLE
on the video side (#240). FR-006 / SC-002 / data-model I2.

Two further cases guard the seam the resolver introduces:
- a manual-only association surfaces on the panel with mention_count 0 (the
  optimistic-removal contract), has_manual true, and a `manual` source;
- an entity reached by BOTH a visible-name transcript mention AND a tag on the
  same video reports both sources while keeping its transcript mention_count.
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
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

_PFX = "vpp066"


def _uid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


async def _ensure_video(factory: async_sessionmaker[AsyncSession], vid: str) -> None:
    channel_id = f"UC{_PFX}PanelChan0000000"[:24]
    async with factory() as s:
        if await s.get(ChannelDB, channel_id) is None:
            s.add(ChannelDB(channel_id=channel_id, title="Vpp066 Panel Channel"))
            await s.commit()
        if await s.get(VideoDB, vid) is None:
            s.add(
                VideoDB(
                    video_id=vid,
                    channel_id=channel_id,
                    title=f"Vpp066 {vid}",
                    upload_date=datetime(2026, 1, 1, tzinfo=UTC),
                    duration=60,
                    availability_status="available",
                )
            )
            await s.commit()


async def _panel_rows(client: AsyncClient, vid: str) -> list[dict[str, Any]]:
    r = await client.get(f"/api/v1/videos/{vid}/entities")
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _entity_video_ids(client: AsyncClient, entity_id: uuid.UUID) -> set[str]:
    r = await client.get(f"/api/v1/entities/{entity_id}/videos", params={"limit": 100})
    assert r.status_code == 200, r.text
    return {row["video_id"] for row in r.json()["data"]}


class TestTagOnlyPairParity:
    async def test_tag_only_pair_on_both_video_panel_and_entity_list(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vid = f"{_PFX}tagonly1"[:20]
        await _ensure_video(integration_session_factory, vid)

        entity_id = _uid()
        tag_id = _uid()
        name = f"Vpp066 TagOnly {entity_id.hex}"
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

        panel = await _panel_rows(async_client, vid)
        row = next((r for r in panel if r["entity_id"] == str(entity_id)), None)

        # The core #240 fix: the tag-only entity is now on the video panel.
        assert row is not None, "tag-only entity missing from video panel"
        assert row["sources"] == ["tag"]
        assert row["mention_count"] == 0  # no mentions — optimistic-removal contract
        assert row["has_manual"] is False

        # I2: the same pair is on the entity side too — present on both, not one.
        assert vid in await _entity_video_ids(async_client, entity_id)


class TestManualOnlyPairParity:
    async def test_manual_only_association_on_video_panel(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vid = f"{_PFX}manual1"[:20]
        await _ensure_video(integration_session_factory, vid)

        entity_id = _uid()
        name = f"Vpp066 Manual {entity_id.hex}"

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
            await s.commit()
            s.add(
                EntityMentionDB(
                    id=_uid(),
                    entity_id=entity_id,
                    video_id=vid,
                    mention_text=name,
                    mention_source="transcript",  # stored value pre-US4 migration
                    detection_method="manual",
                )
            )
            await s.commit()

        panel = await _panel_rows(async_client, vid)
        row = next((r for r in panel if r["entity_id"] == str(entity_id)), None)

        assert row is not None, "manual-only entity missing from video panel"
        # mention_count excludes manual — a manual-only entity reads 0 so the web
        # client's optimistic removal still reads it as hand-linked.
        assert row["mention_count"] == 0
        assert row["has_manual"] is True
        assert "manual" in row["sources"]
        assert vid in await _entity_video_ids(async_client, entity_id)


class TestMentionPlusTagMergesSources:
    async def test_visible_mention_and_tag_report_both_sources(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vid = f"{_PFX}both1"[:20]
        await _ensure_video(integration_session_factory, vid)

        entity_id = _uid()
        tag_id = _uid()
        name = f"Vpp066 Both {entity_id.hex}"
        raw = f"{_PFX} both form {entity_id.hex}"

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
                CanonicalTagDB(
                    id=tag_id,
                    canonical_form=raw,
                    normalized_form=raw,
                    alias_count=1,
                    video_count=1,
                    status="active",
                    entity_id=entity_id,
                    entity_type="person",
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
            # A visible-name transcript mention (text == canonical name).
            s.add(
                EntityMentionDB(
                    id=_uid(),
                    entity_id=entity_id,
                    video_id=vid,
                    mention_text=name,
                    mention_source="transcript",
                    detection_method="rule_match",
                )
            )
            await s.commit()

        panel = await _panel_rows(async_client, vid)
        row = next((r for r in panel if r["entity_id"] == str(entity_id)), None)

        assert row is not None
        assert set(row["sources"]) == {"transcript", "tag"}
        # The transcript mention still counts; adding the tag source did not
        # touch mention_count.
        assert row["mention_count"] == 1
        assert vid in await _entity_video_ids(async_client, entity_id)


class TestNonVisibleMentionOnlyPairAbsentFromBoth:
    async def test_asr_error_only_association_is_hidden_on_both_views(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The *removal* direction of I2 (strict-parity decision).

        An entity whose only link to a video is a mention that does NOT match a
        visible name — an ASR-error alias, `mention_text` != canonical name and
        != any non-ASR alias — with no tag and no manual, is excluded by the #89
        visible-name rule the entity detail already applies. Feature 066 makes
        the video panel apply the same rule, so the pair is absent from BOTH
        views, not shown on one and hidden on the other. This guards the
        narrowing the api-contract review flagged as under-tested.
        """
        vid = f"{_PFX}asronly1"[:20]
        await _ensure_video(integration_session_factory, vid)

        entity_id = _uid()
        name = f"Vpp066 AsrOnly {entity_id.hex}"

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
            await s.commit()
            # Non-manual mention whose text is NOT a visible name of the entity.
            s.add(
                EntityMentionDB(
                    id=_uid(),
                    entity_id=entity_id,
                    video_id=vid,
                    mention_text=f"asr garble {entity_id.hex}",
                    mention_source="transcript",
                    detection_method="rule_match",
                )
            )
            await s.commit()

        panel = await _panel_rows(async_client, vid)
        assert not any(
            r["entity_id"] == str(entity_id) for r in panel
        ), "non-visible-name-only entity must NOT appear on the video panel"
        # ...and the entity side agrees it is not associated with this video.
        assert vid not in await _entity_video_ids(async_client, entity_id)
