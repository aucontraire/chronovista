"""Integration tests for topic API endpoints (US3).

Tests for GET /api/v1/topics, GET /api/v1/topics/{topic_id}, and
GET /api/v1/topics/{topic_id}/videos endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel,
    ChannelTopic,
    TopicCategory,
    Video,
    VideoTopic,
)


pytestmark = pytest.mark.asyncio


class TestListTopics:
    """Tests for GET /api/v1/topics endpoint."""

    async def test_list_topics_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that topic list requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/topics")
            assert response.status_code == 401

    async def test_list_topics_returns_paginated_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test topic list returns paginated response structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)

    async def test_list_topics_pagination_metadata(
        self, async_client: AsyncClient
    ) -> None:
        """Test pagination metadata contains required fields."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics?limit=10&offset=0")
            assert response.status_code == 200
            data = response.json()

            pagination = data["pagination"]
            assert "total" in pagination
            assert "limit" in pagination
            assert "offset" in pagination
            assert "has_more" in pagination
            assert pagination["limit"] == 10
            assert pagination["offset"] == 0

    async def test_list_topics_default_pagination(
        self, async_client: AsyncClient
    ) -> None:
        """Test default pagination values (limit=20, offset=0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics")
            assert response.status_code == 200
            data = response.json()

            assert data["pagination"]["limit"] == 20
            assert data["pagination"]["offset"] == 0

    async def test_list_topics_limit_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test limit validation (max 100)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Over max
            response = await async_client.get("/api/v1/topics?limit=200")
            assert response.status_code == 422  # Validation error

    async def test_list_topics_offset_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test offset validation (must be >= 0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics?offset=-1")
            assert response.status_code == 422  # Validation error

    async def test_list_topics_item_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test topic list items have correct structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics?limit=1")
            assert response.status_code == 200
            data = response.json()

            if data["data"]:  # If there are topics
                topic = data["data"][0]
                assert "topic_id" in topic
                assert "name" in topic
                assert "video_count" in topic
                assert "channel_count" in topic

    async def test_list_topics_has_more_calculation(
        self, async_client: AsyncClient
    ) -> None:
        """Test has_more is correctly calculated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics?limit=100&offset=0")
            assert response.status_code == 200
            data = response.json()

            total = data["pagination"]["total"]
            limit = data["pagination"]["limit"]
            offset = data["pagination"]["offset"]
            has_more = data["pagination"]["has_more"]

            # Verify has_more logic
            assert has_more == ((offset + limit) < total)


class TestListTopicsWithCounts:
    """Tests for GET /api/v1/topics with video_count and channel_count aggregation."""

    async def test_list_topics_includes_video_count(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test that topic list includes aggregated video_count."""
        # Create test data
        async with integration_session_factory() as session:
            # Clean up any existing test data
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(ChannelTopic))
            await session.execute(delete(Channel))
            await session.execute(delete(TopicCategory))
            await session.commit()

            # Create a topic
            topic = TopicCategory(
                topic_id="test_topic_001",
                category_name="Test Topic",
                topic_type="youtube",
                source="seeded",
            )
            session.add(topic)
            await session.flush()

            # Create a channel for the video
            channel = Channel(
                channel_id="UC" + "X" * 22,
                title="Test Channel",
                is_subscribed=False,
            )
            session.add(channel)
            await session.flush()

            # Create videos associated with topic
            video1 = Video(
                video_id="test_vid_001",
                channel_id=channel.channel_id,
                title="Test Video 1",
                upload_date=datetime.now(timezone.utc),
                duration=300,
            )
            video2 = Video(
                video_id="test_vid_002",
                channel_id=channel.channel_id,
                title="Test Video 2",
                upload_date=datetime.now(timezone.utc),
                duration=400,
            )
            session.add_all([video1, video2])
            await session.flush()

            # Create video-topic relationships
            vt1 = VideoTopic(video_id=video1.video_id, topic_id=topic.topic_id)
            vt2 = VideoTopic(video_id=video2.video_id, topic_id=topic.topic_id)
            session.add_all([vt1, vt2])
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics")
            assert response.status_code == 200
            data = response.json()

            # Find our test topic
            test_topic = None
            for topic in data["data"]:
                if topic["topic_id"] == "test_topic_001":
                    test_topic = topic
                    break

            assert test_topic is not None, "Test topic not found in response"
            assert test_topic["video_count"] == 2
            assert test_topic["name"] == "Test Topic"

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(ChannelTopic))
            await session.execute(delete(Channel))
            await session.execute(delete(TopicCategory))
            await session.commit()

    async def test_list_topics_includes_channel_count(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test that topic list includes aggregated channel_count."""
        # Create test data
        async with integration_session_factory() as session:
            # Clean up any existing test data
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(ChannelTopic))
            await session.execute(delete(Channel))
            await session.execute(delete(TopicCategory))
            await session.commit()

            # Create a topic
            topic = TopicCategory(
                topic_id="test_topic_002",
                category_name="Test Topic 2",
                topic_type="youtube",
                source="seeded",
            )
            session.add(topic)
            await session.flush()

            # Create channels
            channel1 = Channel(
                channel_id="UC" + "Y" * 22,
                title="Test Channel 1",
                is_subscribed=False,
            )
            channel2 = Channel(
                channel_id="UC" + "Z" * 22,
                title="Test Channel 2",
                is_subscribed=False,
            )
            session.add_all([channel1, channel2])
            await session.flush()

            # Create channel-topic relationships
            ct1 = ChannelTopic(channel_id=channel1.channel_id, topic_id=topic.topic_id)
            ct2 = ChannelTopic(channel_id=channel2.channel_id, topic_id=topic.topic_id)
            session.add_all([ct1, ct2])
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics")
            assert response.status_code == 200
            data = response.json()

            # Find our test topic
            test_topic = None
            for topic in data["data"]:
                if topic["topic_id"] == "test_topic_002":
                    test_topic = topic
                    break

            assert test_topic is not None, "Test topic not found in response"
            assert test_topic["channel_count"] == 2
            assert test_topic["name"] == "Test Topic 2"

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(ChannelTopic))
            await session.execute(delete(Channel))
            await session.execute(delete(TopicCategory))
            await session.commit()


class TestTopicDetail:
    """Tests for GET /api/v1/topics/{topic_id} endpoint."""

    async def test_get_topic_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that topic detail requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/topics/gaming")
            assert response.status_code == 401

    async def test_get_topic_returns_detail(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test topic detail returns correct structure."""
        # Create test topic
        async with integration_session_factory() as session:
            await session.execute(delete(TopicCategory).where(
                TopicCategory.topic_id == "test_detail_topic"
            ))
            await session.commit()

            topic = TopicCategory(
                topic_id="test_detail_topic",
                category_name="Test Detail Topic",
                topic_type="youtube",
                source="seeded",
                wikipedia_url="https://en.wikipedia.org/wiki/Test",
                normalized_name="test detail topic",
            )
            session.add(topic)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics/test_detail_topic")
            assert response.status_code == 200
            data = response.json()

            assert "data" in data
            topic_data = data["data"]
            assert topic_data["topic_id"] == "test_detail_topic"
            assert topic_data["name"] == "Test Detail Topic"
            assert topic_data["topic_type"] == "youtube"
            assert topic_data["source"] == "seeded"
            assert "video_count" in topic_data
            assert "channel_count" in topic_data
            assert "created_at" in topic_data

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(TopicCategory).where(
                TopicCategory.topic_id == "test_detail_topic"
            ))
            await session.commit()

    async def test_get_topic_404_for_nonexistent(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 response for non-existent topic."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics/nonexistent_topic_xyz")
            assert response.status_code == 404
            data = response.json()
            assert "error" in data
            assert data["error"]["code"] == "NOT_FOUND"
            assert "Topic" in data["error"]["message"]

    async def test_get_topic_actionable_error_message(
        self, async_client: AsyncClient
    ) -> None:
        """Test that 404 error has actionable message."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics/nonexistent_topic")
            data = response.json()
            # Check actionable guidance
            assert "Verify the topic ID" in data["error"]["message"]

    async def test_get_topic_with_alphanumeric_id(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test topic lookup with alphanumeric format ID.

        Note: Knowledge graph format IDs (like /m/xxx) contain slashes which
        require special path handling. This test verifies the more common
        alphanumeric format works correctly.
        """
        # Create test topic with alphanumeric ID
        async with integration_session_factory() as session:
            await session.execute(delete(TopicCategory).where(
                TopicCategory.topic_id == "m_test123_alpha"
            ))
            await session.commit()

            topic = TopicCategory(
                topic_id="m_test123_alpha",
                category_name="Alphanumeric Topic",
                topic_type="youtube",
                source="seeded",
            )
            session.add(topic)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/topics/m_test123_alpha")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["topic_id"] == "m_test123_alpha"

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(TopicCategory).where(
                TopicCategory.topic_id == "m_test123_alpha"
            ))
            await session.commit()


class TestTopicVideos:
    """Tests for GET /api/v1/topics/{topic_id}/videos endpoint."""

    async def test_get_topic_videos_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test that topic videos requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/topics/gaming/videos")
            assert response.status_code == 401

    async def test_get_topic_videos_404_for_nonexistent_topic(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 when topic doesn't exist."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/topics/nonexistent_topic_xyz/videos"
            )
            assert response.status_code == 404
            data = response.json()
            assert data["error"]["code"] == "NOT_FOUND"

    async def test_get_topic_videos_returns_paginated_response(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test topic videos returns paginated response structure."""
        # Create test data
        async with integration_session_factory() as session:
            # Clean up any existing test data
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(TopicCategory).where(
                TopicCategory.topic_id == "test_videos_topic"
            ))
            await session.commit()

            # Create topic
            topic = TopicCategory(
                topic_id="test_videos_topic",
                category_name="Videos Test Topic",
                topic_type="youtube",
                source="seeded",
            )
            session.add(topic)

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
                video_id="vid_test_00",
                channel_id=channel.channel_id,
                title="Test Video",
                upload_date=datetime.now(timezone.utc),
                duration=300,
            )
            session.add(video)
            await session.flush()

            # Create video-topic relationship
            vt = VideoTopic(video_id=video.video_id, topic_id=topic.topic_id)
            session.add(vt)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/topics/test_videos_topic/videos"
            )
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)
            assert len(data["data"]) >= 1

            # Check video structure
            video = data["data"][0]
            assert "video_id" in video
            assert "title" in video
            assert "upload_date" in video
            assert "transcript_summary" in video

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(TopicCategory).where(
                TopicCategory.topic_id == "test_videos_topic"
            ))
            await session.commit()

    async def test_get_topic_videos_pagination(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Test topic videos pagination parameters."""
        # Create test data with multiple videos
        async with integration_session_factory() as session:
            # Clean up
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(TopicCategory).where(
                TopicCategory.topic_id == "test_pagination_topic"
            ))
            await session.commit()

            # Create topic
            topic = TopicCategory(
                topic_id="test_pagination_topic",
                category_name="Pagination Test Topic",
                topic_type="youtube",
                source="seeded",
            )
            session.add(topic)

            # Create channel
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
                    video_id=f"pag_test_{i:02d}",
                    channel_id=channel.channel_id,
                    title=f"Pagination Test Video {i}",
                    upload_date=datetime.now(timezone.utc),
                    duration=300 + i * 10,
                )
                videos.append(video)
            session.add_all(videos)
            await session.flush()

            # Create video-topic relationships
            for video in videos:
                vt = VideoTopic(video_id=video.video_id, topic_id=topic.topic_id)
                session.add(vt)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Test with limit
            response = await async_client.get(
                "/api/v1/topics/test_pagination_topic/videos?limit=2&offset=0"
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
                "/api/v1/topics/test_pagination_topic/videos?limit=2&offset=4"
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["pagination"]["has_more"] is False

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(delete(VideoTopic))
            await session.execute(delete(Video))
            await session.execute(delete(Channel))
            await session.execute(delete(TopicCategory).where(
                TopicCategory.topic_id == "test_pagination_topic"
            ))
            await session.commit()


class TestTopicAuthRequirements:
    """Tests for authentication requirements on all topic endpoints (T035)."""

    async def test_list_topics_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test GET /topics requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/topics")
            assert response.status_code == 401
            data = response.json()
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"

    async def test_get_topic_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test GET /topics/{topic_id} requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/topics/gaming")
            assert response.status_code == 401
            data = response.json()
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"

    async def test_get_topic_videos_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test GET /topics/{topic_id}/videos requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/topics/gaming/videos")
            assert response.status_code == 401
            data = response.json()
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"
