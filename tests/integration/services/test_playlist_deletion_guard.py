"""A bad enrichment run must not hide the user's playlists (#149).

On 2026-05-14 an enrichment pass set ``deleted_flag = true`` on 288 playlists
at once. Nothing was deleted — the rows were hidden, because every list and
detail endpoint filters ``WHERE deleted_flag IS FALSE`` — and it went unnoticed
for two months. It recurred on 2026-08-05 at a scale no threshold can see: four
playlists, two of them holding real content.

These tests assert against the database after a real ``enrich_playlists`` run.
That is deliberate. The pre-existing unit tests for this method call
``enrich_playlists`` on a ``MagicMock`` and assert the mock's own return value,
so they pass whatever the production code does — including when it hides the
whole library.

Only the YouTube API is stubbed. The query, the loop, the guard and the commit
all run for real.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.services.enrichment.enrichment_service import EnrichmentService

pytestmark = pytest.mark.asyncio

_CHANNEL_ID = "UCguard00000000000001"


async def _seed_playlists(session: AsyncSession, count: int, prefix: str) -> list[str]:
    """Create ``count`` live playlists and return their IDs.

    Pre-existing live playlists are hidden first. ``enrich_playlists`` selects
    every row with ``deleted_flag IS FALSE``, so the guard's ratio is computed
    over the whole table — a stray playlist left behind by another test would
    silently change the denominator and decide whether the guard fires. The
    method commits internally, so the fixture's rollback does not isolate this.
    """
    await session.execute(text("UPDATE playlists SET deleted_flag = true"))
    await session.execute(
        text(
            """
            INSERT INTO channels (channel_id, title, is_subscribed,
                                  availability_status)
            VALUES (:cid, 'Guard Test Channel', false, 'available')
            ON CONFLICT (channel_id) DO NOTHING
            """
        ),
        {"cid": _CHANNEL_ID},
    )
    ids = [f"{prefix}{i:04d}" for i in range(count)]
    for playlist_id in ids:
        await session.execute(
            text(
                """
                INSERT INTO playlists (playlist_id, title, privacy_status,
                                       channel_id, video_count, deleted_flag,
                                       playlist_type)
                VALUES (:pid, 'Guard Test Playlist', 'private', :cid, 1, false,
                        'regular')
                ON CONFLICT (playlist_id) DO NOTHING
                """
            ),
            {"pid": playlist_id, "cid": _CHANNEL_ID},
        )
    await session.flush()
    return ids


def _service(fetch_result: Any) -> EnrichmentService:
    """EnrichmentService whose only real collaborator is the database.

    ``fetch_result`` is the ``(playlists, not_found)`` tuple the API layer
    would return, or an exception to raise.
    """
    youtube = MagicMock()
    if isinstance(fetch_result, Exception):
        youtube.fetch_playlists_batched = AsyncMock(side_effect=fetch_result)
    else:
        youtube.fetch_playlists_batched = AsyncMock(return_value=fetch_result)

    return EnrichmentService(
        video_repository=MagicMock(),
        channel_repository=MagicMock(),
        video_tag_repository=MagicMock(),
        video_topic_repository=MagicMock(),
        video_category_repository=MagicMock(),
        topic_category_repository=MagicMock(),
        youtube_service=youtube,
        playlist_repository=MagicMock(),
    )


async def _hidden_count(session: AsyncSession, ids: list[str]) -> int:
    rows = await session.execute(
        text(
            "SELECT count(*) FROM playlists "
            "WHERE playlist_id = ANY(:ids) AND deleted_flag"
        ),
        {"ids": ids},
    )
    return int(rows.scalar_one())


class TestMassNotFoundIsRefused:
    async def test_a_wholesale_not_found_hides_nothing(
        self, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The 2026-05-14 incident, reproduced.

        The API answers successfully and returns no items, so every playlist
        looks absent. Before the guard, every one of them was hidden.
        """
        ids = await _seed_playlists(db_session, 40, "PLmass")
        service = _service(([], set(ids)))

        _, _, deleted = await service.enrich_playlists(db_session)

        assert deleted == 0
        assert (
            await _hidden_count(db_session, ids) == 0
        ), "an enrichment run that finds nothing must not hide the library"
        assert any(
            "Refusing to mark playlists deleted" in r.message
            for r in caplog.records
            if r.levelname == "WARNING"
        ), "a refusal this consequential must be visible at WARNING"

    async def test_an_incremental_deletion_is_still_honoured(
        self, db_session: AsyncSession
    ) -> None:
        """The guard must not become a blanket refusal.

        A handful of genuinely absent playlists among many present ones is the
        normal case, and it still marks exactly those.
        """
        ids = await _seed_playlists(db_session, 40, "PLincr")
        gone = ids[:3]
        service = _service(([], set(gone)))

        _, _, deleted = await service.enrich_playlists(db_session)

        assert deleted == 3
        assert await _hidden_count(db_session, gone) == 3
        assert await _hidden_count(db_session, ids[3:]) == 0

    async def test_a_short_run_is_exempt_from_the_ratio(
        self, db_session: AsyncSession
    ) -> None:
        """Below the floor the ratio is noise, so it does not apply.

        Enriching a few playlists of which most are genuinely gone is ordinary;
        blocking it would make ``--limit`` unusable.
        """
        ids = await _seed_playlists(db_session, 4, "PLshort")
        service = _service(([], set(ids)))

        _, _, deleted = await service.enrich_playlists(db_session, limit=4)

        assert deleted == 4


class TestFetchFailureHidesNothing:
    async def test_a_total_fetch_failure_hides_nothing(
        self, db_session: AsyncSession
    ) -> None:
        """The primary fix, seen from the caller.

        With every batch failing, ``fetch_playlists_batched`` now reports an
        empty not-found set, so the caller has nothing to act on — no guard
        needed, and no playlist hidden.
        """
        ids = await _seed_playlists(db_session, 40, "PLfail")
        service = _service(([], set()))

        _, _, deleted = await service.enrich_playlists(db_session)

        assert deleted == 0
        assert await _hidden_count(db_session, ids) == 0


class TestDeletionIsSurfaced:
    async def test_hiding_playlists_logs_a_warning(
        self, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Two months of silence is what made the original incident expensive."""
        ids = await _seed_playlists(db_session, 40, "PLwarn")
        service = _service(([], {ids[0]}))

        await service.enrich_playlists(db_session)

        warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any("marked deleted" in m for m in warnings)
