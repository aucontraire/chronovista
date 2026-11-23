"""Exclusion -> proximity invalidation over real HTTP (Features 116, 117).

POST/DELETE ``/entities/{id}/excluded-videos`` must invalidate EVERY transcript
language of the video: ``entity_video_exclusions`` has no language column, so a
single-language invalidation would leave the other languages' records stale.
The request goes through the app (``ASGITransport``) and the assertions read the
committed ``proximity_scope_states`` rows, so the router -> repository chain is
crossed end to end. The recompute half (records actually dropped and restored per
language) is asserted by the exclusion producer test in
``tests/integration/services/test_proximity_producers.py`` (Feature 117, T024).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import ProximityScopeState as ProximityScopeStateDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from tests.factories.proximity_seed import (
    seed_entity,
    seed_mention,
    seed_segment,
    seed_video,
)

pytestmark = pytest.mark.asyncio

_LANGUAGES = ("en", "fr")
_RUN = uuid.uuid4().hex[:6]
_VIDEOS = [f"x{_RUN}v{n:02d}" for n in range(5)]
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
                delete(ProximityScopeStateDB).where(
                    ProximityScopeStateDB.video_id.in_(_VIDEOS)
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


async def _revisions(session: AsyncSession) -> dict[str, int]:
    """``language_code -> revision`` of the target video's scope-state rows."""
    result = await session.execute(
        select(ProximityScopeStateDB.language_code, ProximityScopeStateDB.revision)
        .where(ProximityScopeStateDB.video_id == _TARGET)
        .execution_options(populate_existing=True)
    )
    return dict(result.tuples().all())


class TestExclusionInvalidatesEveryLanguage:
    async def test_exclude_then_restore_invalidates_every_language(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        world: _World,
    ) -> None:
        async with integration_session_factory() as session:
            assert await _revisions(session) == {}

            response = await async_client.post(
                f"/api/v1/entities/{world.e}/excluded-videos",
                json={"video_id": _TARGET},
            )
            assert response.status_code == 200
            after_exclude = await _revisions(session)
            assert after_exclude == dict.fromkeys(
                _LANGUAGES, 1
            ), f"every language must be invalidated once, got {after_exclude}"

            response = await async_client.delete(
                f"/api/v1/entities/{world.e}/excluded-videos/{_TARGET}"
            )
            assert response.status_code == 204
            assert await _revisions(session) == dict.fromkeys(
                _LANGUAGES, 2
            ), "restore must invalidate every language again"

    async def test_idempotent_reexclude_does_not_requeue(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        world: _World,
    ) -> None:
        """An already-excluded pair changes nothing, so it must not invalidate anything."""
        url = f"/api/v1/entities/{world.e}/excluded-videos"
        assert (
            await async_client.post(url, json={"video_id": _TARGET})
        ).status_code == 200
        async with integration_session_factory() as session:
            before = await _revisions(session)
            assert before == dict.fromkeys(_LANGUAGES, 1)
            second = await async_client.post(url, json={"video_id": _TARGET})
            assert second.json()["data"]["already_excluded"] is True
            assert await _revisions(session) == before
