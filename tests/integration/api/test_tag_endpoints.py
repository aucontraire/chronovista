"""Integration tests for tag API endpoints (US2).

Tests for GET /api/v1/tags, GET /api/v1/tags/{tag}, and
GET /api/v1/tags/{tag}/videos endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel, Video, VideoTag


pytestmark = pytest.mark.asyncio


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
