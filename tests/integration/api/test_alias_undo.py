"""Integration tests for undoable alias deletion (#298, US1/US3).

Exercises the full delete→undo round-trip through the real endpoints and DB:
  - DELETE returns an ``operation_id`` and removes the alias's auto-detected
    mentions (preserving manual ones);
  - the existing ``POST /entities/operations/{id}/undo`` route restores the
    alias and its removed mentions and recomputes counts;
  - undo-again → 409; restore-collision → 409 (no partial); a removed mention
    whose segment vanished is skipped on undo (partial, not a hard failure).

Requires the integration database (chronovista_integration_test).
Auth bypass mirrors the sibling alias endpoint tests.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityOperationLog as EntityOperationLogDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
)
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

_PREFIX = "aundo298"
_CHANNEL_ID = "UCaundo298000000001"
_VIDEO_ID = "aundo298_vid1"
_LANG = "en"
_ENTITY_NORM = f"{_PREFIX} primary"


def _auth():  # type: ignore[no-untyped-def]
    return patch("chronovista.api.deps.youtube_oauth")


def _delete_url(entity_id: uuid.UUID, alias_id: uuid.UUID) -> str:
    return f"/api/v1/entities/{entity_id}/aliases/{alias_id}"


def _undo_url(operation_id: str) -> str:
    return f"/api/v1/entities/operations/{operation_id}/undo"


class TestAliasUndo:
    @pytest.fixture
    async def seeded(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, object], None]:
        """Entity with alias 'Aardvark' → 2 rule_match mentions + 1 manual mention."""
        entity_id = uuid.uuid4()
        alias_id = uuid.uuid4()

        async def _wipe(session: AsyncSession) -> None:
            await session.execute(
                delete(EntityMentionDB).where(EntityMentionDB.video_id == _VIDEO_ID)
            )
            await session.execute(
                delete(TranscriptSegmentDB).where(
                    TranscriptSegmentDB.video_id == _VIDEO_ID
                )
            )
            await session.execute(
                delete(VideoTranscriptDB).where(VideoTranscriptDB.video_id == _VIDEO_ID)
            )
            ids = (
                (
                    await session.execute(
                        select(NamedEntityDB.id).where(
                            NamedEntityDB.canonical_name_normalized == _ENTITY_NORM
                        )
                    )
                )
                .scalars()
                .all()
            )
            if ids:
                await session.execute(
                    delete(EntityOperationLogDB).where(
                        EntityOperationLogDB.entity_id.in_(list(ids))
                    )
                )
                await session.execute(
                    delete(EntityAliasDB).where(EntityAliasDB.entity_id.in_(list(ids)))
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id.in_(list(ids)))
                )
            await session.execute(delete(VideoDB).where(VideoDB.video_id == _VIDEO_ID))
            await session.execute(
                delete(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)
            session.add(ChannelDB(channel_id=_CHANNEL_ID, title="AUndo Channel"))
            session.add(
                VideoDB(
                    video_id=_VIDEO_ID,
                    channel_id=_CHANNEL_ID,
                    title="AUndo Video",
                    description="undo round-trip test",
                    upload_date=datetime(2024, 6, 1, tzinfo=UTC),
                    duration=90,
                )
            )
            await session.commit()
            session.add(
                VideoTranscriptDB(
                    video_id=_VIDEO_ID,
                    language_code=_LANG,
                    transcript_text="Aardvark appears twice: Aardvark.",
                    transcript_type="MANUAL",
                    download_reason="USER_REQUEST",
                    is_cc=False,
                    is_auto_synced=False,
                    track_kind="standard",
                )
            )
            await session.commit()
            seg_ids: list[int] = []
            for i in range(2):
                seg = TranscriptSegmentDB(
                    video_id=_VIDEO_ID,
                    language_code=_LANG,
                    text="Aardvark appears here.",
                    start_time=float(i * 5),
                    duration=5.0,
                    end_time=float(i * 5 + 5),
                    sequence_number=i,
                    has_correction=False,
                )
                session.add(seg)
                await session.flush()
                seg_ids.append(seg.id)
            session.add(
                create_named_entity_db(
                    id=entity_id,
                    canonical_name="Aundo298 Primary",
                    canonical_name_normalized=_ENTITY_NORM,
                    entity_type="person",
                )
            )
            session.add(
                EntityAliasDB(
                    id=alias_id,
                    entity_id=entity_id,
                    alias_name="Aardvark",
                    alias_name_normalized="aardvark",
                    alias_type="name_variant",
                    occurrence_count=2,
                )
            )
            await session.flush()
            # Two auto-detected mentions (one per segment) + one manual mention.
            for seg_id in seg_ids:
                session.add(
                    EntityMentionDB(
                        id=uuid.uuid4(),
                        entity_id=entity_id,
                        segment_id=seg_id,
                        video_id=_VIDEO_ID,
                        language_code=_LANG,
                        mention_text="Aardvark",
                        detection_method="rule_match",
                        confidence=1.0,
                    )
                )
            session.add(
                EntityMentionDB(
                    id=uuid.uuid4(),
                    entity_id=entity_id,
                    video_id=_VIDEO_ID,
                    mention_text="Aardvark",
                    detection_method="manual",
                )
            )
            await session.commit()

        yield {"entity_id": entity_id, "alias_id": alias_id, "seg_ids": seg_ids}
        async with integration_session_factory() as session:
            await _wipe(session)

    async def _delete(
        self, client: AsyncClient, entity_id: uuid.UUID, alias_id: uuid.UUID
    ) -> dict[str, object]:
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await client.delete(_delete_url(entity_id, alias_id))
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]

    async def test_delete_then_undo_round_trip(
        self,
        async_client: AsyncClient,
        seeded: dict[str, object],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id = seeded["entity_id"]
        alias_id = seeded["alias_id"]

        data = await self._delete(async_client, entity_id, alias_id)  # type: ignore[arg-type]
        assert data["removed_mention_count"] == 2  # 2 rule_match; manual preserved
        operation_id = data["operation_id"]

        async with integration_session_factory() as session:
            # Alias gone; only the manual mention remains.
            assert (await session.get(EntityAliasDB, alias_id)) is None
            rows = (
                (
                    await session.execute(
                        select(EntityMentionDB.detection_method).where(
                            EntityMentionDB.entity_id == entity_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(rows) == ["manual"]

        # Undo → alias + 2 auto mentions restored.
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            undo = await async_client.post(_undo_url(str(operation_id)))
        assert undo.status_code == 200, undo.text

        async with integration_session_factory() as session:
            assert (await session.get(EntityAliasDB, alias_id)) is not None
            methods = (
                (
                    await session.execute(
                        select(EntityMentionDB.detection_method).where(
                            EntityMentionDB.entity_id == entity_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(methods) == ["manual", "rule_match", "rule_match"]

    async def test_undo_twice_is_409(
        self,
        async_client: AsyncClient,
        seeded: dict[str, object],
    ) -> None:
        entity_id = seeded["entity_id"]
        alias_id = seeded["alias_id"]
        data = await self._delete(async_client, entity_id, alias_id)  # type: ignore[arg-type]
        op = str(data["operation_id"])
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            first = await async_client.post(_undo_url(op))
            second = await async_client.post(_undo_url(op))
        assert first.status_code == 200, first.text
        assert second.status_code == 409, second.text

    async def test_undo_collision_is_409_no_partial(
        self,
        async_client: AsyncClient,
        seeded: dict[str, object],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id = seeded["entity_id"]
        alias_id = seeded["alias_id"]
        data = await self._delete(async_client, entity_id, alias_id)  # type: ignore[arg-type]
        op = str(data["operation_id"])

        # Re-create an alias that normalizes to the deleted one.
        async with integration_session_factory() as session:
            session.add(
                EntityAliasDB(
                    id=uuid.uuid4(),
                    entity_id=entity_id,  # type: ignore[arg-type]
                    alias_name="AARDVARK",
                    alias_name_normalized="aardvark",
                    alias_type="name_variant",
                    occurrence_count=0,
                )
            )
            await session.commit()

        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            undo = await async_client.post(_undo_url(op))
        assert undo.status_code == 409, undo.text

        # No partial restore: the removed rule_match mentions are still gone.
        async with integration_session_factory() as session:
            methods = (
                (
                    await session.execute(
                        select(EntityMentionDB.detection_method).where(
                            EntityMentionDB.entity_id == entity_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert "rule_match" not in methods

    async def test_undo_skips_mention_whose_segment_vanished(
        self,
        async_client: AsyncClient,
        seeded: dict[str, object],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id = seeded["entity_id"]
        alias_id = seeded["alias_id"]
        seg_ids = seeded["seg_ids"]
        data = await self._delete(async_client, entity_id, alias_id)  # type: ignore[arg-type]
        op = str(data["operation_id"])

        # Delete one of the segments the removed mentions referenced.
        async with integration_session_factory() as session:
            await session.execute(
                delete(TranscriptSegmentDB).where(
                    TranscriptSegmentDB.id == seg_ids[0]  # type: ignore[index]
                )
            )
            await session.commit()

        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            undo = await async_client.post(_undo_url(op))
        # Partial restore, not a hard failure.
        assert undo.status_code == 200, undo.text

        async with integration_session_factory() as session:
            rule_rows = (
                (
                    await session.execute(
                        select(EntityMentionDB.segment_id).where(
                            EntityMentionDB.entity_id == entity_id,
                            EntityMentionDB.detection_method == "rule_match",
                        )
                    )
                )
                .scalars()
                .all()
            )
            # Only the surviving-segment mention came back (1 of 2).
            assert rule_rows == [seg_ids[1]]  # type: ignore[index]

    async def test_delete_records_audit_and_undo_marks_rolled_back(
        self,
        async_client: AsyncClient,
        seeded: dict[str, object],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """US3: the delete writes one 'alias_delete' op capturing the alias +
        removed mentions; undo marks it rolled_back and it can't re-drive."""
        entity_id = seeded["entity_id"]
        alias_id = seeded["alias_id"]
        data = await self._delete(async_client, entity_id, alias_id)  # type: ignore[arg-type]
        op_id = uuid.UUID(str(data["operation_id"]))

        async with integration_session_factory() as session:
            log = await session.get(EntityOperationLogDB, op_id)
            assert log is not None
            assert log.operation_type == "alias_delete"
            assert log.rolled_back is False
            rb = log.rollback_data
            assert rb["alias"]["alias_name"] == "Aardvark"
            assert len(rb["removed_mentions"]) == 2
            assert all(
                m["detection_method"] == "rule_match" for m in rb["removed_mentions"]
            )

        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            undo = await async_client.post(_undo_url(str(op_id)))
        assert undo.status_code == 200, undo.text

        async with integration_session_factory() as session:
            log = await session.get(EntityOperationLogDB, op_id)
            assert log is not None and log.rolled_back is True

    async def test_cross_feature_reads_round_trip_through_undo(
        self,
        async_client: AsyncClient,
        seeded: dict[str, object],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """T022 (Cross-Feature Data Contract): mention count, entity->videos, and
        co-occurrence for the entity are identical before a delete and after its
        undo. Seeds a co-occurring partner so the co-occurrence path is exercised."""
        entity_id = seeded["entity_id"]
        alias_id = seeded["alias_id"]
        seg_ids = seeded["seg_ids"]

        # Seed a partner entity with a mention on the same video (co-occurrence).
        partner_id = uuid.uuid4()
        partner_norm = "aundo298 partner"
        async with integration_session_factory() as session:
            # Idempotent: clear any partner left by a prior run (shared DB).
            stale = (
                (
                    await session.execute(
                        select(NamedEntityDB.id).where(
                            NamedEntityDB.canonical_name_normalized == partner_norm
                        )
                    )
                )
                .scalars()
                .all()
            )
            for sid in stale:
                await session.execute(
                    delete(EntityMentionDB).where(EntityMentionDB.entity_id == sid)
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == sid)
                )
            session.add(
                create_named_entity_db(
                    id=partner_id,
                    canonical_name="Aundo298 Partner",
                    canonical_name_normalized=partner_norm,
                    entity_type="person",
                )
            )
            session.add(
                EntityMentionDB(
                    id=uuid.uuid4(),
                    entity_id=partner_id,
                    segment_id=seg_ids[0],  # type: ignore[index]
                    video_id=_VIDEO_ID,
                    language_code=_LANG,
                    mention_text="Partner",
                    detection_method="rule_match",
                    confidence=1.0,
                )
            )
            await session.flush()
            # The fixture seeded mentions directly without recomputing the
            # denormalized counters; delete+undo DO recompute them, so recompute
            # here first or the round-trip would spuriously differ (stale→fresh).
            await EntityMentionRepository().update_entity_counters(
                session, [entity_id, partner_id]  # type: ignore[list-item]
            )
            await session.commit()

        async def snapshot() -> dict[str, object]:
            detail = (await async_client.get(f"/api/v1/entities/{entity_id}")).json()[
                "data"
            ]
            videos = (
                await async_client.get(f"/api/v1/entities/{entity_id}/videos")
            ).json()["data"]
            cooc = (
                await async_client.get(f"/api/v1/entities/{entity_id}/co-occurring")
            ).json()["data"]
            return {
                "mention_count": detail["mention_count"],
                "video_count": detail["video_count"],
                "videos": sorted(v["video_id"] for v in videos),
                "cooccurring": sorted(
                    (c["entity_id"], c["shared_video_count"]) for c in cooc
                ),
            }

        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            before = await snapshot()
            # Non-trivial: the entity is mentioned and co-occurs with the partner.
            assert before["mention_count"] >= 1
            assert any(cid == str(partner_id) for cid, _ in before["cooccurring"])

            data = await self._delete(async_client, entity_id, alias_id)  # type: ignore[arg-type]
            undo = await async_client.post(_undo_url(str(data["operation_id"])))
            assert undo.status_code == 200, undo.text
            after = await snapshot()

        assert (
            after == before
        ), f"round-trip changed reads\nbefore={before}\nafter={after}"
