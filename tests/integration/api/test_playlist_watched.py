"""Integration tests for per-playlist watched/unwatched stats and filtering.

Feature 061, User Story 1 (T009, T010, T011, T011a).

The central thing under test is that the response carries **two different
counts** and that they move independently:

- ``stats.playlist_total`` — the size of the playlist under the *other* filters,
  frozen with respect to the watched filter (FR-005b)
- ``pagination.total`` — the result count for the current view, which tracks the
  watched filter (FR-005c)

An implementation that makes these equal has broken FR-005b; one that makes the
header shrink with the filter has broken it the other way. A spec review caught
exactly that ambiguity, so these are asserted separately and never conflated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel,
    Playlist,
    PlaylistMembership,
    UserVideo,
    Video,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CHANNEL = "UCwatchedtest0000000000"
T0 = datetime(2024, 1, 1, tzinfo=UTC)

# Curated playlist: 4 videos — 2 watched (one of them via a DUPLICATE pair of
# watch rows), 2 unwatched (one of which has a row with a NULL watched_at).
CURATED = "PLwatchedtest001"
WATCH_LATER = "WLwatchedtest001"
HISTORY = "HLwatchedtest001"
EMPTY = "PLwatchedtestempty"


async def _seed(session: AsyncSession) -> None:
    """Seed the shared corpus once.

    The integration database is not reset between tests in this suite, so this
    is idempotent: every test calls it, and only the first one writes.
    """
    existing = await session.execute(
        select(Channel.channel_id).where(Channel.channel_id == CHANNEL)
    )
    if existing.scalar_one_or_none() is not None:
        return

    session.add(Channel(channel_id=CHANNEL, title="T", description="d"))
    for vid in ("vw_watched1", "vw_watched2", "vw_unwatch1", "vw_unwatch2"):
        session.add(
            Video(
                video_id=vid,
                channel_id=CHANNEL,
                title=vid,
                description="d",
                upload_date=T0,
                duration=60,
            )
        )

    for pid, ptype in (
        (CURATED, "regular"),
        (WATCH_LATER, "watch_later"),
        (HISTORY, "history"),
        (EMPTY, "regular"),
    ):
        session.add(
            Playlist(
                playlist_id=pid,
                title=pid,
                description="d",
                video_count=0,
                privacy_status="private",
                playlist_type=ptype,
            )
        )

    for pos, vid in enumerate(
        ("vw_watched1", "vw_watched2", "vw_unwatch1", "vw_unwatch2")
    ):
        session.add(PlaylistMembership(playlist_id=CURATED, video_id=vid, position=pos))
    # Watch Later holds one watched and one unwatched video — the real-world
    # case: YouTube does not remove a video from the queue once watched.
    session.add(
        PlaylistMembership(playlist_id=WATCH_LATER, video_id="vw_watched1", position=0)
    )
    session.add(
        PlaylistMembership(playlist_id=WATCH_LATER, video_id="vw_unwatch1", position=1)
    )
    # History is trivially all-watched.
    session.add(
        PlaylistMembership(playlist_id=HISTORY, video_id="vw_watched2", position=0)
    )

    # vw_watched1 has TWO watch-history rows. FR-002: counts are per distinct
    # video and must not inflate. Feature 060 makes this unreachable in practice,
    # but the counting must not depend on that guarantee.
    session.add(
        UserVideo(user_id="u_a", video_id="vw_watched1", watched_at=T0, rewatch_count=0)
    )
    session.add(
        UserVideo(user_id="u_b", video_id="vw_watched1", watched_at=T0, rewatch_count=0)
    )
    session.add(
        UserVideo(user_id="u_a", video_id="vw_watched2", watched_at=T0, rewatch_count=0)
    )
    # A row with NO watch timestamp counts as unwatched, identical to no row.
    session.add(
        UserVideo(
            user_id="u_a", video_id="vw_unwatch1", watched_at=None, rewatch_count=0
        )
    )
    await session.commit()


async def _get(client: AsyncClient, playlist: str, **params: object) -> dict:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
        mock_oauth.is_authenticated.return_value = True
        response = await client.get(f"/api/v1/playlists/{playlist}/videos?{qs}")
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_counts_are_per_distinct_video_and_duplicate_safe(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T009 / FR-029, FR-002."""
    async with integration_db_session() as session:
        await _seed(session)

    body = await _get(async_client, CURATED, limit=50)
    stats = body["stats"]

    # 4 distinct videos; vw_watched1 has two watch rows and must count once.
    assert stats["playlist_total"] == 4
    assert stats["watched"] == 2
    assert stats["unwatched"] == 2
    assert stats["watched"] + stats["unwatched"] == stats["playlist_total"]


async def test_each_filter_value_returns_exactly_the_right_videos(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T009 / FR-029."""
    async with integration_db_session() as session:
        await _seed(session)

    watched = await _get(async_client, CURATED, watched_status="watched", limit=50)
    unwatched = await _get(async_client, CURATED, watched_status="unwatched", limit=50)

    assert {v["video_id"] for v in watched["data"]} == {"vw_watched1", "vw_watched2"}
    assert {v["video_id"] for v in unwatched["data"]} == {"vw_unwatch1", "vw_unwatch2"}
    # Per-row flag (FR-009) agrees with the filter. Note this pair is weak on its
    # own: under a filter the endpoint derives the flag *from* the filter rather
    # than re-querying, so these can no longer disagree. The unfiltered
    # assertion below is the one that actually tests the flag.
    assert all(v["watched"] is True for v in watched["data"])
    assert all(v["watched"] is False for v in unwatched["data"])


async def test_unfiltered_page_flags_match_an_independent_query(
    async_client: AsyncClient, integration_db_session
) -> None:
    """FR-009 — the per-row flag is verified against the database, not the filter.

    Under ``watched_status=watched|unwatched`` the endpoint knows every row's
    state from the WHERE clause it just applied, so it does not re-query, and an
    assertion that those rows carry the matching flag cannot fail. The unfiltered
    page is the only one that can hold a mix, so it is the only place the flag is
    genuinely derived — and it is checked here against watch history read
    directly, not against anything the endpoint computed.
    """
    async with integration_db_session() as session:
        await _seed(session)

    page = await _get(async_client, CURATED, limit=50)
    assert len(page["data"]) >= 4, "the mixed corpus must actually be mixed"

    async with integration_db_session() as session:
        truth = {
            row[0]
            for row in (
                await session.execute(
                    select(UserVideo.video_id).where(UserVideo.watched_at.is_not(None))
                )
            ).all()
        }

    for item in page["data"]:
        assert item["watched"] is (item["video_id"] in truth), (
            f"{item['video_id']}: endpoint said watched={item['watched']}, "
            f"watch history says {item['video_id'] in truth}"
        )

    # And the page really did contain both states, or the loop proved nothing.
    states = {item["watched"] for item in page["data"]}
    assert states == {True, False}


async def test_header_is_frozen_while_result_count_tracks_the_filter(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T010 / FR-029a, FR-005b, FR-005c — the two quantities, asserted apart."""
    async with integration_db_session() as session:
        await _seed(session)

    expected_stats = {"playlist_total": 4, "watched": 2, "unwatched": 2}
    expected_result_counts = {"all": 4, "watched": 2, "unwatched": 2}

    for status, expected_total in expected_result_counts.items():
        body = await _get(async_client, CURATED, watched_status=status, limit=50)
        assert (
            body["stats"] == expected_stats
        ), f"header must not change with watched_status={status} (FR-005b)"
        assert (
            body["pagination"]["total"] == expected_total
        ), f"result count must track watched_status={status} (FR-005c)"


async def test_stats_narrow_with_other_filters_but_not_the_watched_filter(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T011 / FR-005a."""
    async with integration_db_session() as session:
        await _seed(session)

    # has_transcript matches nothing in this corpus, so it must narrow the header
    # to zero — proving the stats honour filters other than watched_status.
    narrowed = await _get(async_client, CURATED, has_transcript="true", limit=50)
    assert narrowed["stats"]["playlist_total"] == 0
    assert narrowed["stats"]["watched"] == 0
    assert narrowed["stats"]["unwatched"] == 0


async def test_behaves_identically_on_watch_later_and_history(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T011a / FR-008 — same header and filter on every playlist type."""
    async with integration_db_session() as session:
        await _seed(session)

    wl = await _get(async_client, WATCH_LATER, limit=50)
    assert wl["stats"] == {"playlist_total": 2, "watched": 1, "unwatched": 1}

    # History is trivially all-watched; its Unwatched view is empty, not an error.
    hist = await _get(async_client, HISTORY, watched_status="unwatched", limit=50)
    assert hist["stats"] == {"playlist_total": 1, "watched": 1, "unwatched": 0}
    assert hist["data"] == []
    assert hist["pagination"]["total"] == 0


async def test_empty_playlist_renders_zeroed_header(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T011a / FR-013."""
    async with integration_db_session() as session:
        await _seed(session)

    body = await _get(async_client, EMPTY, limit=50)
    assert body["stats"] == {"playlist_total": 0, "watched": 0, "unwatched": 0}
    assert body["data"] == []


async def test_invalid_watched_status_is_rejected(
    async_client: AsyncClient, integration_db_session
) -> None:
    """Enum validation — the API rejects what the UI must never send."""
    async with integration_db_session() as session:
        await _seed(session)

    with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
        mock_oauth.is_authenticated.return_value = True
        response = await async_client.get(
            f"/api/v1/playlists/{CURATED}/videos?watched_status=bogus"
        )
    assert response.status_code == 422
