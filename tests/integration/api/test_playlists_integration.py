"""
Integration tests for playlist video sort and filter API endpoints (US2: T016).

Tests cover:
- Sort ordering with real data (position, upload_date, title)
- Filter intersection accuracy (liked_only, has_transcript, unavailable_only)
- Pagination boundary consistency with sort
- Empty result sets with filters

Uses the integration test database with real data insertion.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel,
    Playlist as PlaylistDB,
    PlaylistMembership,
    UserVideo,
    Video as VideoDB,
    VideoTranscript,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


# ═══════════════════════════════════════════════════════════════════════════
# Test Data Fixtures
# ═══════════════════════════════════════════════════════════════════════════


PLAYLIST_ID = "PLtestintegration1234567890abc"
CHANNEL_ID = "UCintegtest123456789012"


@pytest.fixture
async def seed_playlist_data(
    integration_session_factory,
) -> AsyncGenerator[None, None]:
    """Seed the database with playlist and video test data.

    Creates:
    - 1 channel
    - 1 playlist with 5 videos at various positions
    - 1 video marked as liked (via user_videos)
    - 2 videos with transcripts
    - 1 unavailable video
    """
    async with integration_session_factory() as session:
        # Clean up any existing test data first
        await session.execute(
            delete(PlaylistMembership).where(
                PlaylistMembership.playlist_id == PLAYLIST_ID
            )
        )
        await session.execute(
            delete(UserVideo).where(
                UserVideo.video_id.in_(
                    [f"vid_test_{i:04d}" for i in range(1, 6)]
                )
            )
        )
        await session.execute(
            delete(VideoTranscript).where(
                VideoTranscript.video_id.in_(
                    [f"vid_test_{i:04d}" for i in range(1, 6)]
                )
            )
        )
        await session.execute(
            delete(VideoDB).where(
                VideoDB.video_id.in_(
                    [f"vid_test_{i:04d}" for i in range(1, 6)]
                )
            )
        )
        await session.execute(
            delete(PlaylistDB).where(PlaylistDB.playlist_id == PLAYLIST_ID)
        )
        await session.execute(
            delete(Channel).where(Channel.channel_id == CHANNEL_ID)
        )
        await session.commit()

        # Create channel
        channel = Channel(
            channel_id=CHANNEL_ID,
            title="Integration Test Channel",
            description="Test channel for integration tests",
        )
        session.add(channel)
        await session.flush()

        # Create playlist
        playlist = PlaylistDB(
            playlist_id=PLAYLIST_ID,
            title="Integration Test Playlist",
            description="Test playlist for sort/filter integration tests",
            privacy_status="public",
            video_count=5,
        )
        session.add(playlist)
        await session.flush()

        # Create 5 videos with different dates and titles
        videos = [
            VideoDB(
                video_id="vid_test_0001",
                channel_id=CHANNEL_ID,
                title="Alpha Video",
                upload_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
                duration=300,
                availability_status="available",
            ),
            VideoDB(
                video_id="vid_test_0002",
                channel_id=CHANNEL_ID,
                title="Beta Video",
                upload_date=datetime(2024, 3, 20, tzinfo=timezone.utc),
                duration=450,
                availability_status="available",
            ),
            VideoDB(
                video_id="vid_test_0003",
                channel_id=CHANNEL_ID,
                title="Charlie Video",
                upload_date=datetime(2024, 2, 10, tzinfo=timezone.utc),
                duration=600,
                availability_status="deleted",  # unavailable
            ),
            VideoDB(
                video_id="vid_test_0004",
                channel_id=CHANNEL_ID,
                title="Delta Video",
                upload_date=datetime(2024, 5, 1, tzinfo=timezone.utc),
                duration=180,
                availability_status="available",
            ),
            VideoDB(
                video_id="vid_test_0005",
                channel_id=CHANNEL_ID,
                title="Echo Video",
                upload_date=datetime(2024, 4, 10, tzinfo=timezone.utc),
                duration=240,
                availability_status="available",
            ),
        ]
        for v in videos:
            session.add(v)
        await session.flush()

        # Create memberships with positions
        memberships = [
            PlaylistMembership(
                playlist_id=PLAYLIST_ID,
                video_id="vid_test_0001",
                position=0,
            ),
            PlaylistMembership(
                playlist_id=PLAYLIST_ID,
                video_id="vid_test_0002",
                position=1,
            ),
            PlaylistMembership(
                playlist_id=PLAYLIST_ID,
                video_id="vid_test_0003",
                position=2,
            ),
            PlaylistMembership(
                playlist_id=PLAYLIST_ID,
                video_id="vid_test_0004",
                position=3,
            ),
            PlaylistMembership(
                playlist_id=PLAYLIST_ID,
                video_id="vid_test_0005",
                position=4,
            ),
        ]
        for m in memberships:
            session.add(m)
        await session.flush()

        # Mark vid_test_0001 as liked
        liked = UserVideo(
            user_id="test_user",
            video_id="vid_test_0001",
            liked=True,
        )
        session.add(liked)
        await session.flush()

        # Add transcripts to vid_test_0002 and vid_test_0004
        transcripts = [
            VideoTranscript(
                video_id="vid_test_0002",
                language_code="en",
                transcript_text="This is a test transcript for Beta Video.",
                transcript_type="AUTO",
                download_reason="AUTO_PREFERRED",
                is_cc=False,
                is_auto_synced=True,
                track_kind="standard",
            ),
            VideoTranscript(
                video_id="vid_test_0004",
                language_code="en",
                transcript_text="This is a test transcript for Delta Video.",
                transcript_type="MANUAL",
                download_reason="USER_REQUEST",
                is_cc=True,
                is_auto_synced=False,
                track_kind="standard",
            ),
        ]
        for t in transcripts:
            session.add(t)

        await session.commit()

    yield

    # Cleanup after test
    async with integration_session_factory() as session:
        await session.execute(
            delete(PlaylistMembership).where(
                PlaylistMembership.playlist_id == PLAYLIST_ID
            )
        )
        await session.execute(
            delete(UserVideo).where(
                UserVideo.video_id.in_(
                    [f"vid_test_{i:04d}" for i in range(1, 6)]
                )
            )
        )
        await session.execute(
            delete(VideoTranscript).where(
                VideoTranscript.video_id.in_(
                    [f"vid_test_{i:04d}" for i in range(1, 6)]
                )
            )
        )
        await session.execute(
            delete(VideoDB).where(
                VideoDB.video_id.in_(
                    [f"vid_test_{i:04d}" for i in range(1, 6)]
                )
            )
        )
        await session.execute(
            delete(PlaylistDB).where(PlaylistDB.playlist_id == PLAYLIST_ID)
        )
        await session.execute(
            delete(Channel).where(Channel.channel_id == CHANNEL_ID)
        )
        await session.commit()


# ═══════════════════════════════════════════════════════════════════════════
# Sort Ordering Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPlaylistVideoSortOrdering:
    """Tests for playlist video sort ordering with real data."""

    async def test_sort_by_position_asc_default(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test default sort returns videos ordered by position ascending."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
            )
            assert response.status_code == 200
            data = response.json()
            positions = [v["position"] for v in data["data"]]
            assert positions == sorted(positions)

    async def test_sort_by_position_desc(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test sort by position descending."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
                "?sort_by=position&sort_order=desc"
            )
            assert response.status_code == 200
            data = response.json()
            positions = [v["position"] for v in data["data"]]
            assert positions == sorted(positions, reverse=True)

    async def test_sort_by_upload_date_asc(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test sort by upload_date ascending."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
                "?sort_by=upload_date&sort_order=asc"
            )
            assert response.status_code == 200
            data = response.json()
            dates = [v["upload_date"] for v in data["data"]]
            assert dates == sorted(dates)

    async def test_sort_by_upload_date_desc(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test sort by upload_date descending."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
                "?sort_by=upload_date&sort_order=desc"
            )
            assert response.status_code == 200
            data = response.json()
            dates = [v["upload_date"] for v in data["data"]]
            assert dates == sorted(dates, reverse=True)

    async def test_sort_by_title_asc(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test sort by title ascending."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
                "?sort_by=title&sort_order=asc"
            )
            assert response.status_code == 200
            data = response.json()
            titles = [v["title"] for v in data["data"]]
            assert titles == sorted(titles)

    async def test_sort_by_title_desc(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test sort by title descending."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
                "?sort_by=title&sort_order=desc"
            )
            assert response.status_code == 200
            data = response.json()
            titles = [v["title"] for v in data["data"]]
            assert titles == sorted(titles, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════
# Filter Accuracy Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPlaylistVideoFilterAccuracy:
    """Tests for playlist video filter intersection accuracy."""

    async def test_liked_only_filter(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test liked_only returns only liked videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos?liked_only=true"
            )
            assert response.status_code == 200
            data = response.json()
            # Only vid_test_0001 is liked
            assert data["pagination"]["total"] == 1
            assert data["data"][0]["video_id"] == "vid_test_0001"

    async def test_has_transcript_filter(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test has_transcript returns only videos with transcripts."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos?has_transcript=true"
            )
            assert response.status_code == 200
            data = response.json()
            # vid_test_0002 and vid_test_0004 have transcripts
            assert data["pagination"]["total"] == 2
            video_ids = {v["video_id"] for v in data["data"]}
            assert video_ids == {"vid_test_0002", "vid_test_0004"}

    async def test_unavailable_only_filter(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test unavailable_only returns only unavailable videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos?unavailable_only=true"
            )
            assert response.status_code == 200
            data = response.json()
            # Only vid_test_0003 is deleted (unavailable)
            assert data["pagination"]["total"] == 1
            assert data["data"][0]["video_id"] == "vid_test_0003"
            assert data["data"][0]["availability_status"] != "available"

    async def test_combined_liked_and_transcript_filters(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test AND logic: liked_only + has_transcript returns intersection."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
                "?liked_only=true&has_transcript=true"
            )
            assert response.status_code == 200
            data = response.json()
            # vid_test_0001 is liked but has no transcript
            # vid_test_0002 has transcript but is not liked
            # Intersection is empty
            assert data["pagination"]["total"] == 0
            assert data["data"] == []

    async def test_combined_unavailable_and_transcript(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test AND logic: unavailable_only + has_transcript returns intersection."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
                "?unavailable_only=true&has_transcript=true"
            )
            assert response.status_code == 200
            data = response.json()
            # vid_test_0003 is unavailable but has no transcript
            # Intersection is empty
            assert data["pagination"]["total"] == 0

    async def test_no_filters_returns_all(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test that without filters, all 5 videos are returned."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["pagination"]["total"] == 5


# ═══════════════════════════════════════════════════════════════════════════
# Pagination Boundary Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPlaylistVideoPaginationWithSort:
    """Tests for pagination boundary consistency with sort."""

    async def test_pagination_with_sort_by_title(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test pagination works correctly with title sort."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Get first page
            response1 = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
                "?sort_by=title&sort_order=asc&limit=2&offset=0"
            )
            assert response1.status_code == 200
            data1 = response1.json()
            assert len(data1["data"]) == 2
            assert data1["pagination"]["has_more"] is True

            # Get second page
            response2 = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
                "?sort_by=title&sort_order=asc&limit=2&offset=2"
            )
            assert response2.status_code == 200
            data2 = response2.json()
            assert len(data2["data"]) == 2

            # Verify no overlap between pages
            page1_ids = {v["video_id"] for v in data1["data"]}
            page2_ids = {v["video_id"] for v in data2["data"]}
            assert page1_ids.isdisjoint(page2_ids)

            # Verify sort order is maintained across pages
            all_titles = [v["title"] for v in data1["data"]] + [
                v["title"] for v in data2["data"]
            ]
            assert all_titles == sorted(all_titles)

    async def test_pagination_with_filter_reduces_total(
        self, async_client: AsyncClient, seed_playlist_data: None
    ) -> None:
        """Test that applying a filter reduces the total count in pagination."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Without filter
            resp_all = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos"
            )
            total_all = resp_all.json()["pagination"]["total"]

            # With transcript filter
            resp_filtered = await async_client.get(
                f"/api/v1/playlists/{PLAYLIST_ID}/videos?has_transcript=true"
            )
            total_filtered = resp_filtered.json()["pagination"]["total"]

            assert total_filtered < total_all
