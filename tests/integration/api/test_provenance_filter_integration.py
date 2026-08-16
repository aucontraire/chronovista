"""US3: the provenance filter is a multi-select union (Feature 066 / T017).

Against a real Postgres. The integration DB is never reset, so every assertion
intersects the endpoint's results with THIS test's seeded video set — never a
global total (project integration-db shared-state rule).

Seeds one entity reachable through three different single sources — one tag-only
video, one transcript-mention video, one title-mention video — then asserts on
`GET /entities/{id}/videos`:

- `?source=tag` returns only the tag video (single value → that source only);
- `?source=transcript&source=title` returns the union of those two, not the tag
  video (multiple values → OR);
- no `source` returns all three (empty → all).
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
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB

pytestmark = pytest.mark.asyncio

_PFX = "prov066"


def _uid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


async def _seed(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, dict[str, str]]:
    """Seed an entity with one tag video, one transcript video, one title video.

    Returns the entity id and a {source: video_id} map for intersection.
    """
    channel_id = f"UC{_PFX}ProvChan00000000"[:24]
    entity_id = _uid()
    tag_id = _uid()
    name = f"Prov066 Entity {entity_id.hex}"
    raw = f"{_PFX} form {entity_id.hex}"
    vids = {
        "tag": f"{_PFX}tag{entity_id.hex[:6]}"[:20],
        "transcript": f"{_PFX}tr{entity_id.hex[:6]}"[:20],
        "title": f"{_PFX}ti{entity_id.hex[:6]}"[:20],
    }

    async with factory() as s:
        if await s.get(ChannelDB, channel_id) is None:
            s.add(ChannelDB(channel_id=channel_id, title="Prov066 Channel"))
            await s.commit()
        for vid in vids.values():
            if await s.get(VideoDB, vid) is None:
                s.add(
                    VideoDB(
                        video_id=vid,
                        channel_id=channel_id,
                        title=f"Prov066 {vid}",
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
        s.add(VideoTagDB(video_id=vids["tag"], tag=raw, tag_order=0))
        # A visible-name transcript mention and a visible-name title mention.
        s.add(
            EntityMentionDB(
                id=_uid(),
                entity_id=entity_id,
                video_id=vids["transcript"],
                mention_text=name,
                mention_source="transcript",
                detection_method="rule_match",
            )
        )
        s.add(
            EntityMentionDB(
                id=_uid(),
                entity_id=entity_id,
                video_id=vids["title"],
                mention_text=name,
                mention_source="title",
                detection_method="rule_match",
            )
        )
        await s.commit()
    return entity_id, vids


async def _video_ids(
    client: AsyncClient, entity_id: uuid.UUID, params: list[tuple[str, str]] | None
) -> set[str]:
    query = list(params or []) + [("limit", "100")]
    r = await client.get(f"/api/v1/entities/{entity_id}/videos", params=query)
    assert r.status_code == 200, r.text
    return {row["video_id"] for row in r.json()["data"]}


class TestProvenanceFilterUnion:
    async def test_single_multi_and_empty(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id, vids = await _seed(integration_session_factory)
        mine = set(vids.values())

        # single value → that source only
        tag_only = await _video_ids(async_client, entity_id, [("source", "tag")])
        assert tag_only & mine == {vids["tag"]}

        # Provenance is honest, not detection-method-derived (#172 regression):
        # the title video is a rule_match mention too, so a conflated filter
        # would have leaked it into `source=transcript`. It must not.
        transcript_only = await _video_ids(
            async_client, entity_id, [("source", "transcript")]
        )
        assert transcript_only & mine == {vids["transcript"]}
        title_only = await _video_ids(async_client, entity_id, [("source", "title")])
        assert title_only & mine == {vids["title"]}

        # multiple values → union (transcript OR title), never the tag video
        union = await _video_ids(
            async_client,
            entity_id,
            [("source", "transcript"), ("source", "title")],
        )
        assert union & mine == {vids["transcript"], vids["title"]}

        # comma-separated form is equivalent
        union_csv = await _video_ids(
            async_client, entity_id, [("source", "transcript,title")]
        )
        assert union_csv & mine == {vids["transcript"], vids["title"]}

        # empty → all sources
        all_sources = await _video_ids(async_client, entity_id, None)
        assert all_sources & mine == mine

    async def test_invalid_source_is_rejected(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id, _ = await _seed(integration_session_factory)
        # A detection-method value is not a provenance source (FR-009).
        r = await async_client.get(
            f"/api/v1/entities/{entity_id}/videos",
            params=[("source", "rule_match")],
        )
        assert r.status_code == 422, r.text
