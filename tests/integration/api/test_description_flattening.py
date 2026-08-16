"""US5: description occurrences flatten to presence (Feature 066 / T024).

Against a real Postgres. Assertions are keyed on the entity/video this test
seeds (project integration-db rule).

FR-012: for a single video's per-source count, transcript reflects true
frequency while description is counted once per entity per video (presence);
title is already presence. The distinct-video association count (US1) is
unaffected — it is presence by construction.

Measured in production: 5,610 (entity, video) pairs carry more than one
description mention (up to five text variants of the same name), which
inflated the video panel's mention_count before this rule.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils import uuid7

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB

pytestmark = pytest.mark.asyncio

_PFX = "descflat066"


def _uid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


async def _ensure_video(factory: async_sessionmaker[AsyncSession], vid: str) -> None:
    channel_id = f"UC{_PFX}Chan00000000"[:24]
    async with factory() as s:
        if await s.get(ChannelDB, channel_id) is None:
            s.add(ChannelDB(channel_id=channel_id, title="DescFlat Channel"))
            await s.commit()
        if await s.get(VideoDB, vid) is None:
            s.add(
                VideoDB(
                    video_id=vid,
                    channel_id=channel_id,
                    title=f"DescFlat {vid}",
                    upload_date=datetime(2026, 1, 1, tzinfo=UTC),
                    duration=60,
                    availability_status="available",
                )
            )
            await s.commit()


async def _panel_row(
    client: AsyncClient, vid: str, entity_id: uuid.UUID
) -> dict | None:
    r = await client.get(f"/api/v1/videos/{vid}/entities")
    assert r.status_code == 200, r.text
    return next((x for x in r.json()["data"] if x["entity_id"] == str(entity_id)), None)


class TestDescriptionFlattening:
    async def test_repeated_description_is_presence_transcript_is_frequency(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vid = f"{_PFX}v1"[:20]
        await _ensure_video(integration_session_factory, vid)

        # Entity D: three DIFFERENT visible-name texts in the description (the
        # DB permits only distinct texts per description). All are visible names
        # so the entity is a panel member and the resolver counts the video.
        entity_d = _uid()
        d_name = f"DescFlat D {entity_d.hex}"
        d_alias1 = f"DescFlat D a1 {entity_d.hex}"
        d_alias2 = f"DescFlat D a2 {entity_d.hex}"

        # Entity T: two transcript mentions on the same video (frequency = 2).
        entity_t = _uid()
        t_name = f"DescFlat T {entity_t.hex}"

        async with integration_session_factory() as s:
            for eid, nm, etype in (
                (entity_d, d_name, "person"),
                (entity_t, t_name, "person"),
            ):
                s.add(
                    NamedEntityDB(
                        id=eid,
                        canonical_name=nm,
                        canonical_name_normalized=nm.lower(),
                        entity_type=etype,
                        status="active",
                    )
                )
            for alias in (d_alias1, d_alias2):
                s.add(
                    EntityAliasDB(
                        id=_uid(),
                        entity_id=entity_d,
                        alias_name=alias,
                        alias_name_normalized=alias.lower(),
                        alias_type="name_variant",
                    )
                )
            await s.commit()

            # Three distinct-text description mentions of the SAME entity D.
            for text in (d_name, d_alias1, d_alias2):
                s.add(
                    EntityMentionDB(
                        id=_uid(),
                        entity_id=entity_d,
                        video_id=vid,
                        mention_text=text,
                        mention_source="description",
                        detection_method="rule_match",
                    )
                )
            # Two transcript mentions of entity T (segment-less; distinct rows).
            for _ in range(2):
                s.add(
                    EntityMentionDB(
                        id=_uid(),
                        entity_id=entity_t,
                        video_id=vid,
                        mention_text=t_name,
                        mention_source="transcript",
                        detection_method="rule_match",
                    )
                )
            await s.commit()

        d_row = await _panel_row(async_client, vid, entity_d)
        t_row = await _panel_row(async_client, vid, entity_t)

        assert d_row is not None and t_row is not None
        # Description flattens: three text variants → one (presence).
        assert d_row["mention_count"] == 1
        assert d_row["sources"] == ["description"]
        # Transcript keeps frequency: two mentions → two.
        assert t_row["mention_count"] == 2

        # US1 distinct-video total is unaffected — presence by construction.
        detail = await async_client.get(f"/api/v1/entities/{entity_d}")
        assert detail.status_code == 200, detail.text
        data = detail.json()["data"]
        assert data["video_count"] == 1
        assert data["by_source"]["description"] == 1
