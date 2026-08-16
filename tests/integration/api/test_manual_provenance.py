"""US4: honest manual provenance (Feature 066 / T020, T023 + cross-feature guard).

Against a real Postgres. The integration DB is never reset, so every assertion
is keyed on the entity/video this test seeds (project integration-db rule).

- T020 (label only, never membership): reclassifying a manual mention's
  `mention_source` from the false `transcript` to the honest `manual` changes
  ONLY the label. The association count (US1) and the video-panel membership
  (US2) are identical before and after, because both key manual off
  `detection_method`, not `mention_source` (plan mutation-impact analysis).

- Cross-feature guard (the mutation-impact case the plan missed): a manual
  association still counts as evidence under the entity-intersection
  `min_evidence=transcript` scope after reclassification. `EvidenceScope.
  TRANSCRIPT` now matches `mention_source IN ('transcript','manual')`, so the
  highest-trust evidence is retained rather than silently shed. Reverting that
  filter to `== 'transcript'` fails this test.

- T023: the manual-add endpoint stores `mention_source='manual'` for a
  text-less assertion, not `transcript`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils import uuid7

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB

pytestmark = pytest.mark.asyncio

_PFX = "mprov066"


def _uid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


async def _ensure_video(factory: async_sessionmaker[AsyncSession], vid: str) -> None:
    channel_id = f"UC{_PFX}ManChan000000000"[:24]
    async with factory() as s:
        if await s.get(ChannelDB, channel_id) is None:
            s.add(ChannelDB(channel_id=channel_id, title="Mprov066 Channel"))
            await s.commit()
        if await s.get(VideoDB, vid) is None:
            s.add(
                VideoDB(
                    video_id=vid,
                    channel_id=channel_id,
                    title=f"Mprov066 {vid}",
                    upload_date=datetime(2026, 1, 1, tzinfo=UTC),
                    duration=60,
                    availability_status="available",
                )
            )
            await s.commit()


async def _add_entity(
    factory: async_sessionmaker[AsyncSession], name: str
) -> uuid.UUID:
    entity_id = _uid()
    async with factory() as s:
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
    return entity_id


async def _add_manual_mention(
    factory: async_sessionmaker[AsyncSession],
    entity_id: uuid.UUID,
    vid: str,
    name: str,
    mention_source: str,
) -> uuid.UUID:
    mention_id = _uid()
    async with factory() as s:
        s.add(
            EntityMentionDB(
                id=mention_id,
                entity_id=entity_id,
                video_id=vid,
                mention_text=name,
                mention_source=mention_source,
                detection_method="manual",
            )
        )
        await s.commit()
    return mention_id


async def _detail(client: AsyncClient, entity_id: uuid.UUID) -> dict:
    r = await client.get(f"/api/v1/entities/{entity_id}")
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _panel_row(
    client: AsyncClient, vid: str, entity_id: uuid.UUID
) -> dict | None:
    r = await client.get(f"/api/v1/videos/{vid}/entities")
    assert r.status_code == 200, r.text
    return next((x for x in r.json()["data"] if x["entity_id"] == str(entity_id)), None)


class TestReclassificationIsLabelOnly:
    async def test_count_and_panel_membership_unchanged_by_relabel(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vid = f"{_PFX}label1"[:20]
        await _ensure_video(integration_session_factory, vid)
        name = f"Mprov066 Label {_uid().hex}"
        entity_id = await _add_entity(integration_session_factory, name)
        mention_id = await _add_manual_mention(
            integration_session_factory, entity_id, vid, name, "transcript"
        )

        # BEFORE: manual row carries the (old) false 'transcript' label.
        before_detail = await _detail(async_client, entity_id)
        before_panel = await _panel_row(async_client, vid, entity_id)
        assert before_panel is not None
        assert before_detail["video_count"] >= 1
        assert before_detail["by_source"]["manual"] >= 1

        # Reclassify the label — the exact mutation the migration performs.
        async with integration_session_factory() as s:
            await s.execute(
                update(EntityMentionDB)
                .where(EntityMentionDB.id == mention_id)
                .values(mention_source="manual")
            )
            await s.commit()

        # AFTER: only the label changed; count + panel membership are identical.
        after_detail = await _detail(async_client, entity_id)
        after_panel = await _panel_row(async_client, vid, entity_id)
        assert after_panel is not None
        assert after_detail["video_count"] == before_detail["video_count"]
        assert after_detail["by_source"] == before_detail["by_source"]
        assert after_panel["has_manual"] == before_panel["has_manual"] is True
        assert after_panel["mention_count"] == before_panel["mention_count"] == 0
        assert set(after_panel["sources"]) == set(before_panel["sources"])
        assert "manual" in after_panel["sources"]


class TestManualCountsAsTranscriptEvidence:
    async def test_manual_association_retained_under_transcript_scope(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vid = f"{_PFX}coocc1"[:20]
        await _ensure_video(integration_session_factory, vid)
        name_a = f"Mprov066 CoA {_uid().hex}"
        name_b = f"Mprov066 CoB {_uid().hex}"
        entity_a = await _add_entity(integration_session_factory, name_a)
        entity_b = await _add_entity(integration_session_factory, name_b)
        # Both entities are linked to the same video ONLY via manual assertions
        # carrying the honest 'manual' source (post-reclassification state).
        await _add_manual_mention(
            integration_session_factory, entity_a, vid, name_a, "manual"
        )
        await _add_manual_mention(
            integration_session_factory, entity_b, vid, name_b, "manual"
        )

        r = await async_client.get(
            f"/api/v1/entities/{entity_a}/co-occurring",
            params={"min_evidence": "transcript", "limit": 50},
        )
        assert r.status_code == 200, r.text
        partners = {row["entity_id"]: row for row in r.json()["data"]}

        # The cross-feature guarantee: manual evidence still co-occurs under the
        # TRANSCRIPT scope. Reverting EvidenceScope.TRANSCRIPT to a bare
        # `== 'transcript'` filter drops B and fails here.
        assert (
            str(entity_b) in partners
        ), "manual association shed from TRANSCRIPT-scoped intersection"
        assert partners[str(entity_b)]["shared_video_count"] >= 1


class TestManualAddStoresManualSource:
    async def test_manual_add_endpoint_stores_manual_source(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vid = f"{_PFX}addep1"[:20]
        await _ensure_video(integration_session_factory, vid)
        name = f"Mprov066 AddEp {_uid().hex}"
        entity_id = await _add_entity(integration_session_factory, name)

        r = await async_client.post(f"/api/v1/videos/{vid}/entities/{entity_id}/manual")
        assert r.status_code == 201, r.text

        # T023: the stored provenance is honest 'manual', not 'transcript'.
        async with integration_session_factory() as s:
            row = (
                await s.execute(
                    select(EntityMentionDB.mention_source).where(
                        EntityMentionDB.entity_id == entity_id,
                        EntityMentionDB.video_id == vid,
                        EntityMentionDB.detection_method == "manual",
                    )
                )
            ).scalar_one()
        assert row == "manual"
