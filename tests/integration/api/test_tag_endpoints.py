"""Integration tests for tag API endpoints (US2).

Tests for GET /api/v1/tags, GET /api/v1/tags/{tag}, and
GET /api/v1/tags/{tag}/videos endpoints.

Also contains TestTagEndpointRegression (Feature 030, SC-005) which verifies
zero regressions on existing raw tag endpoints after canonical tag routes
were added.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel, Video, VideoTag
from tests.factories.id_factory import YouTubeIdFactory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Namespace constants for TestTagEndpointRegression fixtures
# ---------------------------------------------------------------------------
_REG_CHANNEL_ID = YouTubeIdFactory.create_channel_id(seed="reg_tag_endpoint_test")
_REG_VID1_ID = YouTubeIdFactory.create_video_id(seed="reg_tag_vid_1")
_REG_VID2_ID = YouTubeIdFactory.create_video_id(seed="reg_tag_vid_2")
_REG_VID3_ID = YouTubeIdFactory.create_video_id(seed="reg_tag_vid_3")
_REG_TAG_PREFIX = "reg_tag_test_"


class TestListTags:
    """Tests for GET /api/v1/tags endpoint."""

    async def test_list_tags_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that tag list requires authentication (T039)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/tags")
            assert response.status_code == 401

    async def test_list_tags_returns_paginated_list(
        self, async_client: AsyncClient
    ) -> None:
        """Test tag list returns paginated response structure (T031)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)

    async def test_list_tags_pagination_metadata(
        self, async_client: AsyncClient
    ) -> None:
        """Test pagination metadata contains required fields (T033)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags?limit=10&offset=0")
            assert response.status_code == 200
            data = response.json()

            pagination = data["pagination"]
            assert "total" in pagination
            assert "limit" in pagination
            assert "offset" in pagination
            assert "has_more" in pagination
            assert pagination["limit"] == 10
            assert pagination["offset"] == 0

    async def test_list_tags_default_pagination(
        self, async_client: AsyncClient
    ) -> None:
        """Test default pagination values (limit=20, offset=0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags")
            assert response.status_code == 200
            data = response.json()

            assert data["pagination"]["limit"] == 20
            assert data["pagination"]["offset"] == 0

    async def test_list_tags_invalid_pagination(
        self, async_client: AsyncClient
    ) -> None:
        """Test validation for invalid pagination parameters (T041)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Over max limit
            response = await async_client.get("/api/v1/tags?limit=200")
            assert response.status_code == 422  # Validation error

            # Negative offset
            response = await async_client.get("/api/v1/tags?offset=-1")
            assert response.status_code == 422  # Validation error

    async def test_list_tags_item_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test tag list items have correct structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags?limit=1")
            assert response.status_code == 200
            data = response.json()

            if data["data"]:  # If there are tags
                tag_item = data["data"][0]
                assert "tag" in tag_item
                assert "video_count" in tag_item

    async def test_list_tags_has_more_calculation(
        self, async_client: AsyncClient
    ) -> None:
        """Test has_more is correctly calculated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags?limit=100&offset=0")
            assert response.status_code == 200
            data = response.json()

            total = data["pagination"]["total"]
            limit = data["pagination"]["limit"]
            offset = data["pagination"]["offset"]
            has_more = data["pagination"]["has_more"]

            # Verify has_more logic
            assert has_more == ((offset + limit) < total)

    async def test_list_tags_offset_exceeds_total(
        self, async_client: AsyncClient
    ) -> None:
        """Test offset exceeding total returns empty data with has_more=false (T043, FR-019)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # First get the total count
            response = await async_client.get("/api/v1/tags?limit=1")
            assert response.status_code == 200
            total = response.json()["pagination"]["total"]

            # Request with offset beyond total
            response = await async_client.get(f"/api/v1/tags?offset={total + 100}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"] == []
            assert data["pagination"]["has_more"] is False


class TestListTagsWithCounts:
    """Tests for GET /api/v1/tags with video_count aggregation."""

    async def test_list_tags_sorted_by_video_count_desc(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test that tags are sorted by video_count descending (T032)."""
        # Create test data
        async with integration_session_factory() as session:
            # Clean up any existing test data
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()

            # Create a channel
            channel = Channel(
                channel_id="UC" + "T" * 22,
                title="Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            # Create videos with different tags
            videos = []
            for i in range(5):
                video = Video(
                    video_id=f"tag_sort_{i:02d}",
                    channel_id=channel.channel_id,
                    title=f"Test Video {i}",
                    upload_date=datetime.now(timezone.utc),
                    duration=300,
                )
                videos.append(video)
            session.add_all(videos)
            await session.flush()

            # Tag 'popular' appears on 3 videos
            for i in range(3):
                vt = VideoTag(video_id=videos[i].video_id, tag="popular")
                session.add(vt)

            # Tag 'niche' appears on 1 video
            vt = VideoTag(video_id=videos[3].video_id, tag="niche")
            session.add(vt)

            # Tag 'common' appears on 2 videos
            for i in range(2):
                vt = VideoTag(video_id=videos[i].video_id, tag="common")
                session.add(vt)

            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags?limit=10")
            assert response.status_code == 200
            data = response.json()

            # Find our test tags
            tag_counts = {
                item["tag"]: item["video_count"]
                for item in data["data"]
                if item["tag"] in ["popular", "common", "niche"]
            }

            # Verify counts
            assert tag_counts.get("popular") == 3
            assert tag_counts.get("common") == 2
            assert tag_counts.get("niche") == 1

            # Verify sorted order (most popular first)
            test_tags = [
                item for item in data["data"] if item["tag"] in tag_counts
            ]
            if len(test_tags) >= 2:
                for i in range(len(test_tags) - 1):
                    assert test_tags[i]["video_count"] >= test_tags[i + 1]["video_count"]

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()


class TestTagDetail:
    """Tests for GET /api/v1/tags/{tag} endpoint."""

    async def test_get_tag_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that tag detail requires authentication (T039)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/tags/music")
            assert response.status_code == 401

    async def test_get_tag_returns_detail(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test tag detail returns correct structure (T034)."""
        # Create test tag
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()

            channel = Channel(
                channel_id="UC" + "D" * 22,
                title="Detail Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            video = Video(
                video_id="tag_detail_vid",
                channel_id=channel.channel_id,
                title="Tag Detail Video",
                upload_date=datetime.now(timezone.utc),
                duration=300,
            )
            session.add(video)
            await session.flush()

            tag = VideoTag(video_id=video.video_id, tag="test_detail_tag")
            session.add(tag)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags/test_detail_tag")
            assert response.status_code == 200
            data = response.json()

            assert "data" in data
            tag_data = data["data"]
            assert tag_data["tag"] == "test_detail_tag"
            assert "video_count" in tag_data
            assert tag_data["video_count"] == 1

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()

    async def test_get_tag_not_found(self, async_client: AsyncClient) -> None:
        """Test 404 response for non-existent tag (T035)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags/nonexistent_tag_xyz_12345")
            assert response.status_code == 404
            data = response.json()
            # RFC 7807 format: code is at top level
            assert data["code"] == "NOT_FOUND"
            assert "Tag" in data["detail"]

    async def test_get_empty_tag_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        """Test empty string tag returns 404 (T042)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Empty string in URL becomes /tags/ which should be handled by FastAPI routing
            # Test with whitespace-only tag
            response = await async_client.get("/api/v1/tags/%20")
            # Tag with only whitespace should return 404 if it doesn't exist
            assert response.status_code == 404

    async def test_tag_url_encoding(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test URL-encoded tags work correctly (T040)."""
        # Create test tag with special characters
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()

            channel = Channel(
                channel_id="UC" + "E" * 22,
                title="Encoding Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            video = Video(
                video_id="tag_encode_vid",
                channel_id=channel.channel_id,
                title="Encoding Test Video",
                upload_date=datetime.now(timezone.utc),
                duration=300,
            )
            session.add(video)
            await session.flush()

            # Tag with # symbol
            tag = VideoTag(video_id=video.video_id, tag="#music")
            session.add(tag)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # URL-encode the # symbol
            response = await async_client.get("/api/v1/tags/%23music")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["tag"] == "#music"

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()


class TestTagVideos:
    """Tests for GET /api/v1/tags/{tag}/videos endpoint."""

    async def test_get_tag_videos_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test that tag videos requires authentication (T039)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/tags/music/videos")
            assert response.status_code == 401

    async def test_get_tag_videos_404_for_nonexistent_tag(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 when tag doesn't exist."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/tags/nonexistent_tag_xyz_99999/videos"
            )
            assert response.status_code == 404
            data = response.json()
            # RFC 7807 format: code is at top level
            assert data["code"] == "NOT_FOUND"

    async def test_get_tag_videos_returns_paginated_list(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test tag videos returns paginated response structure (T036)."""
        # Create test data
        async with integration_session_factory() as session:
            # Clean up any existing test data
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()

            # Create channel
            channel = Channel(
                channel_id="UC" + "V" * 22,
                title="Videos Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            # Create video
            video = Video(
                video_id="tag_vid_test_00",
                channel_id=channel.channel_id,
                title="Test Video",
                upload_date=datetime.now(timezone.utc),
                duration=300,
            )
            session.add(video)
            await session.flush()

            # Create video-tag relationship
            vt = VideoTag(video_id=video.video_id, tag="test_videos_tag")
            session.add(vt)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags/test_videos_tag/videos")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)
            assert len(data["data"]) >= 1

            # Check video structure
            video_item = data["data"][0]
            assert "video_id" in video_item
            assert "title" in video_item
            assert "upload_date" in video_item
            assert "transcript_summary" in video_item

        # Cleanup - delete in correct order (foreign key constraints)
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag).where(VideoTag.video_id == "tag_vid_test_00"))
            await session.execute(delete(Video).where(Video.video_id == "tag_vid_test_00"))
            await session.execute(delete(Channel).where(Channel.channel_id == "UC" + "V" * 22))
            await session.commit()

    async def test_get_tag_videos_excludes_deleted(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test tag videos excludes videos with availability_status=unavailable (T037)."""
        # Create test data
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()

            channel = Channel(
                channel_id="UC" + "X" * 22,
                title="Deleted Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            # Create active video
            video_active = Video(
                video_id="tag_active_vid",
                channel_id=channel.channel_id,
                title="Active Video",
                upload_date=datetime.now(timezone.utc),
                duration=300,
                availability_status="available",
            )
            session.add(video_active)

            # Create deleted video
            video_deleted = Video(
                video_id="tag_deleted_vid",
                channel_id=channel.channel_id,
                title="Deleted Video",
                upload_date=datetime.now(timezone.utc),
                duration=300,
                availability_status="unavailable",
            )
            session.add(video_deleted)
            await session.flush()

            # Both videos have the same tag
            vt1 = VideoTag(video_id=video_active.video_id, tag="deletion_test_tag")
            vt2 = VideoTag(video_id=video_deleted.video_id, tag="deletion_test_tag")
            session.add_all([vt1, vt2])
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags/deletion_test_tag/videos")
            assert response.status_code == 200
            data = response.json()

            # Should only return 1 video (the active one)
            assert len(data["data"]) == 1
            assert data["data"][0]["video_id"] == "tag_active_vid"
            assert data["pagination"]["total"] == 1

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()

    async def test_get_tag_videos_sorted_by_upload_date_desc(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test tag videos sorted by upload_date descending (T038)."""
        # Create test data with multiple videos
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()

            channel = Channel(
                channel_id="UC" + "S" * 22,
                title="Sort Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            # Create videos with different upload dates
            video1 = Video(
                video_id="tag_sort_vid_1",
                channel_id=channel.channel_id,
                title="Oldest Video",
                upload_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
                duration=300,
            )
            video2 = Video(
                video_id="tag_sort_vid_2",
                channel_id=channel.channel_id,
                title="Middle Video",
                upload_date=datetime(2023, 6, 1, tzinfo=timezone.utc),
                duration=300,
            )
            video3 = Video(
                video_id="tag_sort_vid_3",
                channel_id=channel.channel_id,
                title="Newest Video",
                upload_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                duration=300,
            )
            session.add_all([video1, video2, video3])
            await session.flush()

            # All videos have the same tag
            for video in [video1, video2, video3]:
                vt = VideoTag(video_id=video.video_id, tag="sort_test_tag")
                session.add(vt)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags/sort_test_tag/videos")
            assert response.status_code == 200
            data = response.json()

            # Should return 3 videos, sorted by upload_date DESC
            assert len(data["data"]) == 3
            assert data["data"][0]["video_id"] == "tag_sort_vid_3"  # Newest first
            assert data["data"][1]["video_id"] == "tag_sort_vid_2"
            assert data["data"][2]["video_id"] == "tag_sort_vid_1"  # Oldest last

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()

    async def test_get_tag_videos_pagination(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test tag videos pagination parameters (T033)."""
        # Create test data with multiple videos
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()

            channel = Channel(
                channel_id="UC" + "P" * 22,
                title="Pagination Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            # Create multiple videos
            videos = []
            for i in range(5):
                video = Video(
                    video_id=f"tag_pag_test_{i:02d}",
                    channel_id=channel.channel_id,
                    title=f"Pagination Test Video {i}",
                    upload_date=datetime.now(timezone.utc),
                    duration=300 + i * 10,
                )
                videos.append(video)
            session.add_all(videos)
            await session.flush()

            # All videos have the same tag
            for video in videos:
                vt = VideoTag(video_id=video.video_id, tag="pagination_test_tag")
                session.add(vt)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Test with limit
            response = await async_client.get(
                "/api/v1/tags/pagination_test_tag/videos?limit=2&offset=0"
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 2
            assert data["pagination"]["limit"] == 2
            assert data["pagination"]["offset"] == 0
            assert data["pagination"]["total"] == 5
            assert data["pagination"]["has_more"] is True

            # Test with offset
            response = await async_client.get(
                "/api/v1/tags/pagination_test_tag/videos?limit=2&offset=4"
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["pagination"]["has_more"] is False

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTag))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.commit()


# ---------------------------------------------------------------------------
# Fixtures for TestTagEndpointRegression
# ---------------------------------------------------------------------------


@pytest.fixture
async def _reg_test_session(
    integration_session_factory: "async_sessionmaker[AsyncSession]",
) -> AsyncGenerator[AsyncSession, None]:
    """Bare session for regression test data setup and cleanup.

    Uses the same integration_session_factory as async_client so inserted
    data is visible through the overridden get_db dependency.
    """
    async with integration_session_factory() as session:
        yield session


@pytest.fixture
async def _reg_sample_channel(_reg_test_session: AsyncSession) -> Channel:
    """Create (or retrieve) the regression test channel.

    channel_id is exactly 24 characters to satisfy the VARCHAR(24) constraint.
    """
    result = await _reg_test_session.execute(
        select(Channel).where(Channel.channel_id == _REG_CHANNEL_ID)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    channel = Channel(
        channel_id=_REG_CHANNEL_ID,
        title="Raw Tag Regression Test Channel",
    )
    _reg_test_session.add(channel)
    await _reg_test_session.commit()
    await _reg_test_session.refresh(channel)
    return channel


@pytest.fixture
async def _reg_sample_data(
    _reg_test_session: AsyncSession,
    _reg_sample_channel: Channel,
) -> dict[str, Any]:
    """Insert Video and VideoTag rows for SC-005 regression tests.

    Creates:
      - vid1 (available) — tagged with reg_tag_test_python
      - vid2 (available) — tagged with reg_tag_test_python AND reg_tag_test_testing
      - vid3 (deleted)   — tagged with reg_tag_test_python (excluded by default)

    Returns a dict with keys:
      channel   : Channel ORM object
      videos    : dict[str, Video] with keys 'vid1', 'vid2', 'vid3_deleted'
      tags      : dict[str, str] with keys 'python' and 'testing' (full tag strings)
      video_tags: list[VideoTag]
    """
    vid1 = Video(
        video_id=_REG_VID1_ID,
        channel_id=_REG_CHANNEL_ID,
        title="Python Basics",
        upload_date=datetime(2024, 3, 10, tzinfo=timezone.utc),
        duration=600,
        availability_status="available",
    )
    vid2 = Video(
        video_id=_REG_VID2_ID,
        channel_id=_REG_CHANNEL_ID,
        title="Python and Testing",
        upload_date=datetime(2024, 5, 20, tzinfo=timezone.utc),
        duration=900,
        availability_status="available",
    )
    vid3_deleted = Video(
        video_id=_REG_VID3_ID,
        channel_id=_REG_CHANNEL_ID,
        title="Deleted Python Video",
        upload_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        duration=300,
        availability_status="deleted",
    )

    for v in [vid1, vid2, vid3_deleted]:
        _reg_test_session.add(v)
    await _reg_test_session.flush()

    tag_python = f"{_REG_TAG_PREFIX}python"
    tag_testing = f"{_REG_TAG_PREFIX}testing"

    vt_specs = [
        (vid1.video_id, tag_python),
        (vid2.video_id, tag_python),
        (vid2.video_id, tag_testing),
        (vid3_deleted.video_id, tag_python),  # deleted — excluded by default
    ]
    video_tags: list[VideoTag] = []
    for vid_id, tag_str in vt_specs:
        vt = VideoTag(video_id=vid_id, tag=tag_str)
        _reg_test_session.add(vt)
        video_tags.append(vt)

    await _reg_test_session.commit()

    return {
        "channel": _reg_sample_channel,
        "videos": {
            "vid1": vid1,
            "vid2": vid2,
            "vid3_deleted": vid3_deleted,
        },
        "tags": {
            "python": tag_python,
            "testing": tag_testing,
        },
        "video_tags": video_tags,
    }


@pytest.fixture
async def _reg_cleanup(
    _reg_test_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Delete all regression test data after each test in FK-safe order.

    Cleanup order: VideoTag -> Video -> Channel
    """
    yield

    video_ids = [
        _REG_VID1_ID,
        _REG_VID2_ID,
        _REG_VID3_ID,
    ]

    await _reg_test_session.execute(
        delete(VideoTag).where(VideoTag.video_id.in_(video_ids))
    )
    await _reg_test_session.execute(
        delete(Video).where(Video.video_id.in_(video_ids))
    )
    await _reg_test_session.execute(
        delete(Channel).where(Channel.channel_id == _REG_CHANNEL_ID)
    )
    await _reg_test_session.commit()


# ---------------------------------------------------------------------------
# TestTagEndpointRegression
# ---------------------------------------------------------------------------


class TestTagEndpointRegression:
    """Regression suite for existing raw tag API endpoints (SC-005).

    SC-005 acceptance criterion: zero regressions on GET /api/v1/tags*
    endpoints after the canonical tag feature (Feature 030) was added.

    All tests mock chronovista.api.deps.youtube_oauth to simulate an
    authenticated session without real OAuth credentials.

    Endpoints under test:
      GET /api/v1/tags                - list raw tags with video_count
      GET /api/v1/tags/{tag}          - single raw tag detail
      GET /api/v1/tags/{tag}/videos   - videos for exact raw tag string
    """

    async def test_get_tags_list_returns_raw_tag_data(
        self,
        async_client: AsyncClient,
        _reg_sample_data: dict[str, Any],
        _reg_cleanup: None,
    ) -> None:
        """GET /api/v1/tags still returns raw tag data with video_count after Feature 030.

        Inserts 2 available videos + 1 deleted video all tagged with
        'reg_tag_test_python'.  Asserts the list endpoint:
          - responds 200
          - includes a 'data' list and 'pagination' meta
          - shows video_count=2 for 'reg_tag_test_python' (deleted excluded)
          - shows video_count=1 for 'reg_tag_test_testing'
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/tags")

        assert response.status_code == 200, (
            f"Expected 200 from /api/v1/tags, got {response.status_code}"
        )
        body = response.json()

        assert "data" in body, "Response missing 'data' key"
        assert "pagination" in body, "Response missing 'pagination' key"
        assert isinstance(body["data"], list), "'data' must be a list"

        # Index our test tags from the full result set
        our_tags = {
            item["tag"]: item
            for item in body["data"]
            if item["tag"].startswith(_REG_TAG_PREFIX)
        }

        tag_python = _reg_sample_data["tags"]["python"]
        tag_testing = _reg_sample_data["tags"]["testing"]

        assert tag_python in our_tags, (
            f"Expected '{tag_python}' in tag list response"
        )
        assert our_tags[tag_python]["video_count"] == 2, (
            f"Expected video_count=2 for '{tag_python}' (deleted video excluded), "
            f"got {our_tags[tag_python]['video_count']}"
        )

        assert tag_testing in our_tags, (
            f"Expected '{tag_testing}' in tag list response"
        )
        assert our_tags[tag_testing]["video_count"] == 1, (
            f"Expected video_count=1 for '{tag_testing}', "
            f"got {our_tags[tag_testing]['video_count']}"
        )

    async def test_get_tag_detail_returns_tag(
        self,
        async_client: AsyncClient,
        _reg_sample_data: dict[str, Any],
        _reg_cleanup: None,
    ) -> None:
        """GET /api/v1/tags/{tag} still returns tag detail with correct video_count.

        Verifies the detail endpoint returns 200 with:
          - data.tag        == the exact raw tag string used as path parameter
          - data.video_count == 2 (only available videos counted)
        """
        tag = _reg_sample_data["tags"]["python"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(f"/api/v1/tags/{tag}")

        assert response.status_code == 200, (
            f"Expected 200 for tag detail, got {response.status_code}: {response.text}"
        )
        body = response.json()

        assert "data" in body, "Tag detail response missing 'data' key"
        detail = body["data"]

        assert detail["tag"] == tag, (
            f"Expected tag='{tag}', got '{detail.get('tag')}'"
        )
        assert detail["video_count"] == 2, (
            f"Expected video_count=2 (available videos only), "
            f"got {detail.get('video_count')}"
        )

    async def test_get_tag_videos_returns_videos(
        self,
        async_client: AsyncClient,
        _reg_sample_data: dict[str, Any],
        _reg_cleanup: None,
    ) -> None:
        """GET /api/v1/tags/{tag}/videos still returns videos for exact raw tag string.

        Verifies:
          - 200 response with 'data' list and 'pagination' meta
          - vid1 and vid2 (available) are present in response
          - vid3_deleted is absent (include_unavailable defaults to False)
          - pagination.total == 2
        """
        tag = _reg_sample_data["tags"]["python"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(f"/api/v1/tags/{tag}/videos")

        assert response.status_code == 200, (
            f"Expected 200 from /api/v1/tags/{tag}/videos, "
            f"got {response.status_code}: {response.text}"
        )
        body = response.json()

        assert "data" in body, "Tag videos response missing 'data' key"
        assert "pagination" in body, "Tag videos response missing 'pagination' key"

        video_ids = [v["video_id"] for v in body["data"]]

        assert _REG_VID1_ID in video_ids, (
            "vid1 (available) should appear in tag videos response"
        )
        assert _REG_VID2_ID in video_ids, (
            "vid2 (available) should appear in tag videos response"
        )
        assert _REG_VID3_ID not in video_ids, (
            "vid3_deleted must NOT appear when include_unavailable=false (default)"
        )

        assert body["pagination"]["total"] == 2, (
            f"Expected total=2 available videos, got {body['pagination']['total']}"
        )

    async def test_response_shapes_unchanged(
        self,
        async_client: AsyncClient,
        _reg_sample_data: dict[str, Any],
        _reg_cleanup: None,
    ) -> None:
        """All three tag endpoints still expose the same response shapes (SC-005).

        This is the primary backward-compatibility guard.  Any field removal or
        type change breaks this test, alerting the team to a regression.

        Expected fields:

        List (/api/v1/tags):
          data[].tag             str
          data[].video_count     int
          pagination.total       int
          pagination.limit       int
          pagination.offset      int
          pagination.has_more    bool

        Detail (/api/v1/tags/{tag}):
          data.tag               str
          data.video_count       int

        Videos (/api/v1/tags/{tag}/videos):
          data[].video_id             str
          data[].title                str
          data[].channel_id           str
          data[].upload_date          str  (ISO-8601)
          data[].duration             int
          data[].transcript_summary   dict
          data[].availability_status  str
          pagination.total            int
        """
        tag = _reg_sample_data["tags"]["python"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            list_resp = await async_client.get("/api/v1/tags")
            detail_resp = await async_client.get(f"/api/v1/tags/{tag}")
            videos_resp = await async_client.get(f"/api/v1/tags/{tag}/videos")

        # --- List shape ---
        assert list_resp.status_code == 200
        list_body = list_resp.json()

        assert "data" in list_body, "List response missing 'data'"
        assert "pagination" in list_body, "List response missing 'pagination'"

        required_pag = {"total", "limit", "offset", "has_more"}
        missing_pag = required_pag - set(list_body["pagination"].keys())
        assert not missing_pag, f"List pagination missing fields: {missing_pag}"

        # Locate a known test item so we can assert field types
        our_items = [
            i for i in list_body["data"] if i["tag"].startswith(_REG_TAG_PREFIX)
        ]
        assert our_items, "No regression test tags found in list response"
        item = our_items[0]
        assert isinstance(item["tag"], str), "'tag' must be a string"
        assert isinstance(item["video_count"], int), "'video_count' must be an int"

        # --- Detail shape ---
        assert detail_resp.status_code == 200
        detail_body = detail_resp.json()

        assert "data" in detail_body, "Detail response missing 'data'"
        detail = detail_body["data"]
        for field in ("tag", "video_count"):
            assert field in detail, f"Detail response missing field '{field}'"
        assert isinstance(detail["tag"], str), "'tag' in detail must be a string"
        assert isinstance(detail["video_count"], int), (
            "'video_count' in detail must be an int"
        )

        # --- Videos shape ---
        assert videos_resp.status_code == 200
        videos_body = videos_resp.json()

        assert "data" in videos_body, "Videos response missing 'data'"
        assert "pagination" in videos_body, "Videos response missing 'pagination'"
        assert "total" in videos_body["pagination"], (
            "Videos pagination missing 'total'"
        )

        assert videos_body["data"], "Expected at least one video in response"
        video_item = videos_body["data"][0]
        required_video_fields = {
            "video_id",
            "title",
            "channel_id",
            "upload_date",
            "duration",
            "transcript_summary",
            "availability_status",
        }
        missing_video_fields = required_video_fields - set(video_item.keys())
        assert not missing_video_fields, (
            f"Tag videos item missing fields: {missing_video_fields}"
        )
        assert isinstance(video_item["video_id"], str)
        assert isinstance(video_item["title"], str)
        assert isinstance(video_item["duration"], int)
        assert isinstance(video_item["transcript_summary"], dict)
