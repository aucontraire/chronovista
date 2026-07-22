"""Cross-feature integration test for an entity rename (Feature 057, T010).

Per the constitution's Cross-Feature Data Contract Verification: after an
identity-changing rename, re-query every consumer of the entity's name and
assert the NEW name appears everywhere it should — list, detail, search,
entity->videos, and video->entities (the last for an entity that has a manual
mention, verifying INV-4: the display uses the live entity name via entity_id,
not the ``mention_text`` frozen at mention-creation). Also asserts the entity's
aliases are unchanged (FR-015).

Requires the integration database (chronovista_integration_test).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

_CHANNEL_ID = "UCect057xf0000000000001"  # <= 24 chars
_VIDEO_ID = "ect057xf_vid01"  # <= 20 chars
_LANG = "en"
_OLD_NAME = "Ect057xf Sourcename"
_OLD_NORM = "ect057xf sourcename"
_NEW_NAME = "Ect057xf Targetname"
_NEW_NORM = "ect057xf targetname"


@pytest.fixture
async def seed(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, Any], None]:
    entity_id = uuid.uuid4()
    async with integration_session_factory() as session:
        await _cleanup(session)
        session.add(ChannelDB(channel_id=_CHANNEL_ID, title="XF Test Channel"))
        session.add(
            VideoDB(
                video_id=_VIDEO_ID,
                channel_id=_CHANNEL_ID,
                title="XF Test Video",
                description="cross-feature test",
                upload_date=datetime(2024, 3, 1, tzinfo=UTC),
                duration=120,
            )
        )
        await session.commit()

        session.add(
            VideoTranscriptDB(
                video_id=_VIDEO_ID,
                language_code=_LANG,
                transcript_text="Ect057xf Sourcename appears here.",
                transcript_type="MANUAL",
                download_reason="USER_REQUEST",
                is_cc=False,
                is_auto_synced=False,
                track_kind="standard",
            )
        )
        await session.commit()

        segment = TranscriptSegmentDB(
            video_id=_VIDEO_ID,
            language_code=_LANG,
            text="Ect057xf Sourcename appears here.",
            start_time=0.0,
            duration=5.0,
            end_time=5.0,
            sequence_number=0,
            has_correction=False,
        )
        session.add(segment)
        await session.commit()
        segment_id = segment.id

        session.add(
            create_named_entity_db(
                id=entity_id,
                canonical_name=_OLD_NAME,
                canonical_name_normalized=_OLD_NORM,
                entity_type="organization",
                description="seed",
            )
        )
        await session.commit()

        # Name-derived alias (must survive the rename — FR-015).
        session.add(
            EntityAliasDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                entity_id=entity_id,
                alias_name=_OLD_NAME,
                alias_name_normalized=_OLD_NORM,
                alias_type="name_variant",
                occurrence_count=0,
            )
        )
        # Manual mention whose frozen mention_text is the OLD name.
        session.add(
            EntityMentionDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                entity_id=entity_id,
                segment_id=segment_id,
                video_id=_VIDEO_ID,
                language_code=_LANG,
                mention_text=_OLD_NAME,
                detection_method="manual",
                confidence=1.0,
            )
        )
        await session.commit()

    yield {"entity_id": str(entity_id), "video_id": _VIDEO_ID}

    async with integration_session_factory() as session:
        await _cleanup(session)


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(
        delete(EntityMentionDB).where(EntityMentionDB.video_id == _VIDEO_ID)
    )
    await session.execute(
        delete(TranscriptSegmentDB).where(TranscriptSegmentDB.video_id == _VIDEO_ID)
    )
    await session.execute(
        delete(VideoTranscriptDB).where(VideoTranscriptDB.video_id == _VIDEO_ID)
    )
    await session.execute(delete(VideoDB).where(VideoDB.video_id == _VIDEO_ID))
    await session.execute(
        delete(NamedEntityDB).where(
            NamedEntityDB.canonical_name_normalized.in_([_OLD_NORM, _NEW_NORM])
        )
    )
    await session.execute(delete(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID))
    await session.commit()


async def test_rename_propagates_to_all_consumers(
    async_client: AsyncClient,
    seed: dict[str, Any],
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    entity_id = seed["entity_id"]
    video_id = seed["video_id"]

    with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
        mock_oauth.is_authenticated.return_value = True

        # --- Rename (identity-changing) ---
        patch_resp = await async_client.patch(
            f"/api/v1/entities/{entity_id}",
            json={"canonical_name": _NEW_NAME},
        )
        assert patch_resp.status_code == 200, patch_resp.text
        assert patch_resp.json()["data"]["canonical_name"] == _NEW_NAME

        # --- Consumer: entity detail ---
        detail = await async_client.get(f"/api/v1/entities/{entity_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["canonical_name"] == _NEW_NAME

        # --- Consumer: list (new name found; old canonical name not found) ---
        found_new = await async_client.get(
            "/api/v1/entities", params={"search": _NEW_NAME, "type": "organization"}
        )
        assert found_new.status_code == 200, found_new.text
        new_ids = {e["entity_id"] for e in found_new.json()["data"]}
        assert entity_id in new_ids

        found_old = await async_client.get(
            "/api/v1/entities", params={"search": _OLD_NAME, "type": "organization"}
        )
        assert found_old.status_code == 200, found_old.text
        old_ids = {e["entity_id"] for e in found_old.json()["data"]}
        assert entity_id not in old_ids

        # --- Consumer: search (autocomplete) finds the new name ---
        search = await async_client.get(
            "/api/v1/entities/search", params={"q": _NEW_NAME}
        )
        assert search.status_code == 200, search.text
        search_hit = next(
            (r for r in search.json()["data"] if r["entity_id"] == entity_id),
            None,
        )
        assert search_hit is not None
        assert search_hit["canonical_name"] == _NEW_NAME

        # --- Consumer: entity -> videos (association by entity_id unchanged) ---
        ev = await async_client.get(f"/api/v1/entities/{entity_id}/videos")
        assert ev.status_code == 200, ev.text
        ev_video_ids = {v["video_id"] for v in ev.json()["data"]}
        assert video_id in ev_video_ids

        # --- Consumer: video -> entities (INV-4: live name, not mention_text) ---
        ve = await async_client.get(f"/api/v1/videos/{video_id}/entities")
        assert ve.status_code == 200, ve.text
        summary = next(
            (s for s in ve.json()["data"] if s["entity_id"] == entity_id),
            None,
        )
        assert summary is not None
        assert summary["canonical_name"] == _NEW_NAME  # NOT the frozen "Sourcename"

    # --- FR-015: aliases unchanged by the rename ---
    # The original name-derived alias survives, the NEW name was NOT added as an
    # alias, and the total alias count is unchanged (rename touches only the
    # display name; aliases are managed solely via the add-alias action).
    async with integration_session_factory() as session:
        aliases = list(
            (
                await session.execute(
                    select(EntityAliasDB.alias_name).where(
                        EntityAliasDB.entity_id == uuid.UUID(entity_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert _OLD_NAME in aliases
        assert _NEW_NAME not in aliases
        assert aliases == [_OLD_NAME]  # exactly the single seeded alias, unchanged
