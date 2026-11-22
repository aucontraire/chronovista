"""Exclusion -> proximity invalidation over real HTTP (Feature 116, T018).

POST/DELETE ``/entities/{id}/excluded-videos`` must invalidate EVERY transcript
language of the video: ``entity_video_exclusions`` has no language column, so a
single-language dirty mark would leave the other languages' instances stale.
The request goes through the app (``ASGITransport``) and the queue/instance
assertions read committed rows, so the router -> repository -> computor chain is
crossed end to end.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import ProximityDirtyScope as ProximityDirtyScopeDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.services.proximity_service import (
    SUPPORT_MIN,
    drain_dirty_scopes,
    rebuild_proximity,
)
from tests.factories.proximity_seed import (
    canonical,
    route_proximity_service_to,
    seed_entity,
    seed_mention,
    seed_segment,
    seed_video,
)

pytestmark = pytest.mark.asyncio

_LANGUAGES = ("en", "fr")
_RUN = uuid.uuid4().hex[:6]
_VIDEOS = [f"x{_RUN}v{n:02d}" for n in range(SUPPORT_MIN)]
_TARGET = _VIDEOS[0]


class _World:
    def __init__(self, e: uuid.UUID, b: uuid.UUID, c: uuid.UUID) -> None:
        self.e, self.b, self.c = e, b, c


@pytest.fixture
async def world(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[_World]:
    """E, B, C co-mentioned (10s/20s/30s) in 5 videos; the first is en+fr."""
    async with integration_session_factory() as session:
        e = await seed_entity(session, unique=True)
        b = await seed_entity(session, unique=True)
        c = await seed_entity(session, unique=True)
        for video_id in _VIDEOS:
            languages = _LANGUAGES if video_id == _TARGET else ("en",)
            await seed_video(session, video_id, languages)
            for language in languages:
                for sequence, (entity_id, start) in enumerate(
                    ((e, 10.0), (b, 20.0), (c, 30.0))
                ):
                    segment = await seed_segment(
                        session, video_id, language, start, sequence
                    )
                    await seed_mention(
                        session,
                        entity_id=entity_id,
                        video_id=video_id,
                        language_code=language,
                        segment_id=segment,
                    )
        await session.commit()
    try:
        yield _World(e, b, c)
    finally:
        async with integration_session_factory() as session:
            await session.execute(
                delete(ProximityDirtyScopeDB).where(
                    ProximityDirtyScopeDB.video_id.in_(_VIDEOS)
                )
            )
            # Entity delete cascades mentions, exclusions and proximity rows.
            await session.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id.in_([e, b, c]))
            )
            # Segments/transcripts do not cascade from the video.
            await session.execute(
                delete(TranscriptSegmentDB).where(
                    TranscriptSegmentDB.video_id.in_(_VIDEOS)
                )
            )
            await session.execute(
                delete(VideoTranscriptDB).where(VideoTranscriptDB.video_id.in_(_VIDEOS))
            )
            await session.execute(delete(VideoDB).where(VideoDB.video_id.in_(_VIDEOS)))
            await session.commit()


async def _dirty_languages(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(ProximityDirtyScopeDB.language_code)
        .where(ProximityDirtyScopeDB.video_id == _TARGET)
        .order_by(ProximityDirtyScopeDB.language_code)
    )
    return list(result.scalars().all())


async def _instances(
    session: AsyncSession, pair: tuple[uuid.UUID, uuid.UUID], language: str
) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(EntityPairProximityDB)
                .where(
                    EntityPairProximityDB.entity_a_id == pair[0],
                    EntityPairProximityDB.entity_b_id == pair[1],
                    EntityPairProximityDB.video_id == _TARGET,
                    EntityPairProximityDB.language_code == language,
                )
            )
        ).scalar_one()
    )


async def _entity_instances(session: AsyncSession, w: _World, language: str) -> int:
    return await _instances(session, canonical(w.e, w.b), language) + await _instances(
        session, canonical(w.e, w.c), language
    )


class TestExclusionInvalidatesEveryLanguage:
    async def test_exclude_then_restore_round_trip(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        world: _World,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async with integration_session_factory() as session:
            route_proximity_service_to(monkeypatch, session)
            await rebuild_proximity(video_ids=_VIDEOS)
            await session.commit()

            bystander = canonical(world.b, world.c)
            for language in _LANGUAGES:
                assert await _entity_instances(session, world, language) == 2
                assert await _instances(session, bystander, language) == 1
            assert await _dirty_languages(session) == []

            # --- exclude E from the multilingual video -----------------------
            response = await async_client.post(
                f"/api/v1/entities/{world.e}/excluded-videos",
                json={"video_id": _TARGET},
            )
            assert response.status_code == 200

            dirty = await _dirty_languages(session)
            assert dirty == sorted(
                _LANGUAGES
            ), f"one dirty row per language expected, got {dirty}"
            assert len(dirty) == len(_LANGUAGES) == 2
            # Stale until drained: the queue, not the POST, drives recompute.
            assert await _entity_instances(session, world, "fr") == 2

            summary = await drain_dirty_scopes()
            # The routed service flushes but never commits; release its locks
            # so the next HTTP request (a different connection) is not blocked.
            await session.commit()
            assert summary["scopes_drained"] >= 2
            assert await _dirty_languages(session) == []
            for language in _LANGUAGES:
                assert (
                    await _entity_instances(session, world, language) == 0
                ), f"excluded entity's {language} instances survived"
                assert (
                    await _instances(session, bystander, language) == 1
                ), f"bystander pair lost its {language} instance"
            # The exclusion is per-video: E is still close in the other videos.
            other = await session.execute(
                select(func.count())
                .select_from(EntityPairProximityDB)
                .where(
                    EntityPairProximityDB.entity_a_id == canonical(world.e, world.b)[0],
                    EntityPairProximityDB.entity_b_id == canonical(world.e, world.b)[1],
                    EntityPairProximityDB.video_id != _TARGET,
                )
            )
            assert other.scalar_one() == SUPPORT_MIN - 1

            # --- restore ------------------------------------------------------
            response = await async_client.delete(
                f"/api/v1/entities/{world.e}/excluded-videos/{_TARGET}"
            )
            assert response.status_code == 204
            assert await _dirty_languages(session) == sorted(_LANGUAGES)
            assert await _entity_instances(session, world, "en") == 0

            await drain_dirty_scopes()
            await session.commit()
            assert await _dirty_languages(session) == []
            for language in _LANGUAGES:
                assert await _entity_instances(session, world, language) == 2
                assert await _instances(session, bystander, language) == 1

    async def test_idempotent_reexclude_does_not_requeue(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        world: _World,
    ) -> None:
        """An already-excluded pair changes nothing, so it must not dirty anything."""
        url = f"/api/v1/entities/{world.e}/excluded-videos"
        assert (
            await async_client.post(url, json={"video_id": _TARGET})
        ).status_code == 200
        async with integration_session_factory() as session:
            await session.execute(
                delete(ProximityDirtyScopeDB).where(
                    ProximityDirtyScopeDB.video_id == _TARGET
                )
            )
            await session.commit()
            second = await async_client.post(url, json={"video_id": _TARGET})
            assert second.json()["data"]["already_excluded"] is True
            assert await _dirty_languages(session) == []
