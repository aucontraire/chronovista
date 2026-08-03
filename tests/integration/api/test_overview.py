"""Integration tests for the Overview Dashboard aggregates.

Feature 061, User Stories 2 and 3 (T030, T031, T031a, T032, T049, T050, T051).

The corpus deliberately includes a playlist of a system type this feature's prose
never names (``liked``). The upstream ``PlaylistType`` enum has five members while
production has only three, so a "system list" check written as membership of
``{watch_later, history}`` would pass every other test here and still render a
``liked`` playlist as user-curated. That is the seam defect this file guards.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel,
    Playlist,
    PlaylistMembership,
    UserVideo,
    Video,
)
from chronovista.repositories.playlist_repository import get_library_overview

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CHANNEL = "UCoverviewtest000000000"
T0 = datetime(2024, 1, 1, tzinfo=UTC)

CURATED_A = "PLoverviewA"
CURATED_B = "PLoverviewB"
WATCH_LATER = "WLoverview"
HISTORY = "HLoverview"
LIKED = "LLoverview"

# ov_multi   — in BOTH curated playlists, never watched  -> counts ONCE (FR-017)
# ov_wlonly  — only in Watch Later, never watched        -> excluded (FR-016)
# ov_histonly— only in History, never watched            -> excluded (FR-016)
# ov_likedonly — only in a `liked` playlist, never watched -> excluded (FR-016/029f)
# ov_watched — in a curated playlist AND watched         -> excluded
#
# The integration database is shared across test modules, so absolute totals are
# not stable. Assertions compare the API against an INDEPENDENT query over the
# same database — which is what SC-003 actually specifies ("equals an independent
# count") and is stronger than pinning a constant.


async def _add_if_absent(session: AsyncSession, pk: Any, obj: Any) -> None:
    """Insert ``obj`` only when its primary key is not already present.

    Idempotent **per row**, not per corpus. An all-or-nothing guard keyed on the
    channel would skip every later addition once the corpus existed — and the
    integration database is never reset, so a corpus seeded by an earlier run
    would silently freeze this file's fixtures at their old shape.
    """
    found = await session.execute(select(pk).where(pk == _pk_value(obj, pk)))
    if found.scalar_one_or_none() is None:
        session.add(obj)


def _pk_value(obj: Any, pk: Any) -> Any:
    return getattr(obj, pk.key)


async def _seed(session: AsyncSession) -> None:
    """Seed the shared corpus; the integration DB is not reset per test or run."""
    await _add_if_absent(
        session,
        Channel.channel_id,
        Channel(channel_id=CHANNEL, title="T", description="d"),
    )
    videos = (
        "ov_multi",
        "ov_wlonly",
        "ov_histonly",
        "ov_likedonly",
        "ov_watched",
    )
    for vid in videos:
        await _add_if_absent(
            session,
            Video.video_id,
            Video(
                video_id=vid,
                channel_id=CHANNEL,
                title=vid,
                description="d",
                upload_date=T0,
                duration=60,
            ),
        )

    # Unwatched, in Watch Later, and no longer available. Its only job is to make
    # the two availability defaults produce *different* numbers, so the test that
    # compares the dashboard figure with the page it links to can actually fail.
    # Without it that comparison passes under either default and proves nothing.
    await _add_if_absent(
        session,
        Video.video_id,
        Video(
            video_id="ov_wlgone",
            channel_id=CHANNEL,
            title="ov_wlgone",
            description="d",
            upload_date=T0,
            duration=60,
            availability_status="deleted",
        ),
    )

    for pid, ptype in (
        (CURATED_A, "regular"),
        (CURATED_B, "regular"),
        (WATCH_LATER, "watch_later"),
        (HISTORY, "history"),
        (LIKED, "liked"),
    ):
        await _add_if_absent(
            session,
            Playlist.playlist_id,
            Playlist(
                playlist_id=pid,
                title=pid,
                description="d",
                video_count=0,
                privacy_status="private",
                playlist_type=ptype,
            ),
        )
    await session.flush()

    # In two curated playlists — must contribute exactly 1 (FR-017).
    for pid, vid, pos in (
        (CURATED_A, "ov_multi", 0),
        (CURATED_B, "ov_multi", 0),
        (CURATED_A, "ov_watched", 1),
        (WATCH_LATER, "ov_wlonly", 0),
        (WATCH_LATER, "ov_wlgone", 1),
        (HISTORY, "ov_histonly", 0),
        (LIKED, "ov_likedonly", 0),
    ):
        found = await session.execute(
            select(PlaylistMembership.playlist_id).where(
                PlaylistMembership.playlist_id == pid,
                PlaylistMembership.video_id == vid,
            )
        )
        if found.scalars().first() is None:
            session.add(PlaylistMembership(playlist_id=pid, video_id=vid, position=pos))

    found = await session.execute(
        select(UserVideo.video_id).where(UserVideo.video_id == "ov_watched")
    )
    if found.scalars().first() is None:
        session.add(
            UserVideo(
                user_id="u_a", video_id="ov_watched", watched_at=T0, rewatch_count=0
            )
        )
    await session.commit()


async def _independent_saved_forgotten(session: AsyncSession) -> int:
    """Count Saved & Forgotten with SQL written independently of the endpoint."""
    result = await session.execute(
        text(
            """
            SELECT count(DISTINCT pm.video_id)
            FROM playlist_memberships pm
            JOIN playlists p ON p.playlist_id = pm.playlist_id
            WHERE p.playlist_type = 'regular'
              AND NOT EXISTS (
                SELECT 1 FROM user_videos uv
                WHERE uv.video_id = pm.video_id AND uv.watched_at IS NOT NULL
              )
            """
        )
    )
    return int(result.scalar_one())


async def _is_counted(session: AsyncSession, video_id: str) -> bool:
    """Whether one specific video falls in the Saved & Forgotten set."""
    result = await session.execute(
        text(
            """
            SELECT count(*)
            FROM playlist_memberships pm
            JOIN playlists p ON p.playlist_id = pm.playlist_id
            WHERE p.playlist_type = 'regular'
              AND pm.video_id = :vid
              AND NOT EXISTS (
                SELECT 1 FROM user_videos uv
                WHERE uv.video_id = pm.video_id AND uv.watched_at IS NOT NULL
              )
            """
        ),
        {"vid": video_id},
    )
    return int(result.scalar_one()) > 0


async def _overview(client: AsyncClient) -> dict:
    with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
        mock_oauth.is_authenticated.return_value = True
        response = await client.get("/api/v1/overview")
    assert response.status_code == 200, response.text
    return dict(response.json()["data"])


async def test_saved_and_forgotten_counts_distinct_videos(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T031 / FR-015, FR-017 — a video in two curated playlists counts once."""
    async with integration_db_session() as session:
        await _seed(session)

    data = await _overview(async_client)
    async with integration_db_session() as session:
        expected = await _independent_saved_forgotten(session)
        # In two curated playlists, unwatched — contributes exactly once.
        assert await _is_counted(session, "ov_multi") is True

    assert data["saved_and_forgotten"] == expected


async def test_system_lists_are_excluded_from_saved_and_forgotten(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T031 / FR-016 — Watch Later and History never contribute."""
    async with integration_db_session() as session:
        await _seed(session)
        # Unwatched and saved, but in system lists rather than curated ones.
        assert await _is_counted(session, "ov_wlonly") is False
        assert await _is_counted(session, "ov_histonly") is False
        expected = await _independent_saved_forgotten(session)

    data = await _overview(async_client)
    assert data["saved_and_forgotten"] == expected


async def test_unnamed_system_type_is_excluded_and_flagged(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T031a / T050 / FR-016, FR-022, FR-029f — the seam guard.

    ``liked`` is a system type the feature's prose never enumerates. It must be
    excluded from Saved & Forgotten and flagged ``is_system`` in the inventory,
    both of which follow from "type is not regular" rather than from a list.
    """
    async with integration_db_session() as session:
        await _seed(session)

    async with integration_db_session() as session:
        # Unwatched and saved, but `liked` is not a curated type.
        assert await _is_counted(session, "ov_likedonly") is False
        expected = await _independent_saved_forgotten(session)

    data = await _overview(async_client)
    assert data["saved_and_forgotten"] == expected

    by_type = {row["playlist_type"]: row for row in data["playlist_inventory"]}
    assert by_type["liked"]["is_system"] is True, (
        "a `liked` playlist must be flagged as a system list — deriving is_system "
        "from {watch_later, history} would render it as user-curated"
    )
    assert by_type["regular"]["is_system"] is False


async def test_inventory_reports_only_types_present(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T049 / FR-021 — grouped over the data, never a fixed list of types."""
    async with integration_db_session() as session:
        await _seed(session)

    data = await _overview(async_client)
    types = {row["playlist_type"] for row in data["playlist_inventory"]}

    # `favorites` exists in the enum but not in the data, so it must not appear
    # as a permanent zero row.
    assert "favorites" not in types
    assert {"regular", "watch_later", "history", "liked"} <= types
    assert all(row["playlist_count"] > 0 for row in data["playlist_inventory"])


async def test_watch_later_depth(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T051 / FR-020 — total and unwatched for the queue."""
    async with integration_db_session() as session:
        await _seed(session)

    data = await _overview(async_client)
    assert data["watch_later"] is not None
    assert data["watch_later"]["total"] >= 1
    assert data["watch_later"]["unwatched"] >= 1


async def test_watch_later_exposes_a_deep_link_target_only_when_unambiguous(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T058 / FR-025 — the depth card can only link to a single playlist.

    The depth aggregates over every Watch Later playlist. With exactly one, the
    link target is unambiguous and MUST be offered. With two, the figure spans
    both and no single playlist matches it, so the target MUST be withheld and
    the figure rendered non-interactively.
    """
    async with integration_db_session() as session:
        await _seed(session)

    # The integration database is shared and other modules seed their own Watch
    # Later playlists, so "exactly one exists" cannot be assumed globally — it is
    # staged here inside a transaction that is rolled back.
    async with integration_db_session() as session:
        try:
            await session.execute(
                delete(PlaylistMembership).where(
                    PlaylistMembership.playlist_id.in_(
                        select(Playlist.playlist_id).where(
                            Playlist.playlist_type == "watch_later",
                            Playlist.playlist_id != WATCH_LATER,
                        )
                    )
                )
            )
            await session.execute(
                delete(Playlist).where(
                    Playlist.playlist_type == "watch_later",
                    Playlist.playlist_id != WATCH_LATER,
                )
            )
            await session.flush()

            overview = await get_library_overview(session)
            assert overview["watch_later"]["playlist_id"] == WATCH_LATER, (
                "with exactly one Watch Later playlist the link target is "
                "unambiguous and must be offered"
            )
        finally:
            await session.rollback()

    async with integration_db_session() as session:
        try:
            session.add(
                Playlist(
                    playlist_id="WLoverview2",
                    title="second queue",
                    description="d",
                    video_count=0,
                    privacy_status="private",
                    playlist_type="watch_later",
                )
            )
            await session.flush()

            overview = await get_library_overview(session)
            assert overview["watch_later"] is not None
            assert overview["watch_later"]["playlist_id"] is None, (
                "with two Watch Later playlists the depth spans both — linking "
                "to either would land on a count that differs from the figure "
                "the user clicked"
            )
        finally:
            await session.rollback()


async def test_watch_later_link_lands_on_the_permissive_availability_count(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T058 / FR-025 — clicking a number must not land on a different number.

    The dashboard applies no availability condition at all. The playlist videos
    endpoint happens to default ``include_unavailable=True``, so the link agrees
    with the figure *without* carrying an explicit parameter — the opposite of
    the videos-list link, where the default is restrictive and FR-018b forced one
    on. Two endpoints, two opposite defaults, and the dashboard link is correct
    only because of which one it happens to hit.

    This pins that default rather than the resulting number, so it holds however
    many Watch Later playlists the shared database contains: if the default ever
    flips to False "for consistency", the link silently starts under-reporting
    and this fails.
    """
    async with integration_db_session() as session:
        await _seed(session)

    async def total(query: str) -> int:
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{WATCH_LATER}/videos?watched_status=unwatched"
                f"&limit=1{query}"
            )
        assert response.status_code == 200, response.text
        return int(response.json()["pagination"]["total"])

    # Exactly the URL the dashboard links to — no availability parameter.
    as_linked = await total("")
    permissive = await total("&include_unavailable=true")
    restrictive = await total("&include_unavailable=false")

    assert as_linked == permissive, (
        "the dashboard counts unavailable videos, so the page it links to must "
        "too — otherwise the user clicks one number and lands on a smaller one"
    )
    # Non-vacuity: the corpus really does contain an unwatched, unavailable
    # video in Watch Later, so the two availability modes genuinely differ.
    # Without this the assertion above would hold under either default.
    assert restrictive < permissive, (
        "the corpus must distinguish the two availability modes, or this test "
        "passes no matter which default the endpoint uses"
    )


async def test_absent_watch_later_is_null_not_zero(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T051 / FR-020a — no Watch Later playlist yields null, not a zero depth.

    A present-but-empty queue is ``{total: 0, unwatched: 0}``. Rendering both as
    zeros would tell someone who has no Watch Later that their queue is empty.

    The integration database is shared and never reset, so the absence is staged
    inside a transaction that is rolled back: every Watch Later playlist is
    removed, the repository function is called on that same session so it reads
    the uncommitted state, then the transaction is discarded.
    """
    async with integration_db_session() as session:
        await _seed(session)

    async with integration_db_session() as session:
        wl_ids = (
            (
                await session.execute(
                    select(Playlist.playlist_id).where(
                        Playlist.playlist_type == "watch_later"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert wl_ids, "precondition: the corpus has at least one Watch Later playlist"

        try:
            await session.execute(
                delete(PlaylistMembership).where(
                    PlaylistMembership.playlist_id.in_(wl_ids)
                )
            )
            await session.execute(
                delete(Playlist).where(Playlist.playlist_id.in_(wl_ids))
            )
            await session.flush()

            overview = await get_library_overview(session)

            assert overview["watch_later"] is None, (
                "absence of a Watch Later playlist must be null — a zero depth "
                "means the queue exists and is empty"
            )
            # The rest of the dashboard still resolves with the queue absent.
            assert overview["saved_and_forgotten"] >= 0
            assert all(
                row["playlist_type"] != "watch_later"
                for row in overview["playlist_inventory"]
            )
        finally:
            await session.rollback()

    # The rollback left the shared corpus intact for every other test.
    async with integration_db_session() as session:
        still_there = (
            await session.execute(
                select(func.count())
                .select_from(Playlist)
                .where(Playlist.playlist_type == "watch_later")
            )
        ).scalar_one()
    assert still_there == len(wl_ids)


async def test_present_but_empty_watch_later_is_zero_not_null(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T051 / FR-020a — the other side of the distinction.

    Without this, ``watch_later: null`` could be returned for an existing but
    empty queue and the test above would still pass.
    """
    async with integration_db_session() as session:
        await _seed(session)

    async with integration_db_session() as session:
        wl_ids = (
            (
                await session.execute(
                    select(Playlist.playlist_id).where(
                        Playlist.playlist_type == "watch_later"
                    )
                )
            )
            .scalars()
            .all()
        )
        try:
            # Empty the queue but keep the playlist itself.
            await session.execute(
                delete(PlaylistMembership).where(
                    PlaylistMembership.playlist_id.in_(wl_ids)
                )
            )
            await session.flush()

            overview = await get_library_overview(session)

            assert overview["watch_later"] is not None, (
                "a playlist that exists but holds nothing is a zero depth, "
                "never null"
            )
            assert overview["watch_later"]["total"] == 0
            assert overview["watch_later"]["unwatched"] == 0
        finally:
            await session.rollback()


async def test_liked_figure_is_a_video_attribute_not_a_playlist_type(
    async_client: AsyncClient, integration_db_session
) -> None:
    """FR-023, FR-023a — the two `liked` quantities stay distinct.

    A `liked` *playlist type* counts playlists; `rollup.liked_videos` counts
    videos carrying the liked attribute. They come from different tables and
    must not be conflated.
    """
    async with integration_db_session() as session:
        await _seed(session)

    data = await _overview(async_client)

    assert "liked_videos" in data["rollup"]
    # The inventory row counts playlists (1), not videos.
    by_type = {row["playlist_type"]: row for row in data["playlist_inventory"]}
    assert by_type["liked"]["playlist_count"] == 1


async def test_dashboard_figure_and_filtered_list_agree(
    async_client: AsyncClient, integration_db_session
) -> None:
    """T030 / FR-018b, FR-029c — the two consumers of one derivation.

    They agree under the *same availability context*. The videos list hides
    unavailable videos by default while the dashboard applies no availability
    condition, so the comparison passes `include_unavailable=true` — which is
    exactly what the dashboard's link must carry (FR-018).
    """
    async with integration_db_session() as session:
        await _seed(session)

    data = await _overview(async_client)

    with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
        mock_oauth.is_authenticated.return_value = True
        response = await async_client.get(
            "/api/v1/videos?saved_unwatched=true&include_unavailable=true&limit=1"
        )
    assert response.status_code == 200, response.text
    list_total = response.json()["pagination"]["total"]

    assert list_total == data["saved_and_forgotten"], (
        "the dashboard headline and the filtered list must agree — they share "
        "one derivation (FR-029b), so a mismatch means a surrounding filter "
        "differs, not that the definition drifted"
    )
