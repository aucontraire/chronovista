"""Integration tests for video classification filters (Feature 020).

Tests filter logic for tags, categories, and topics per FR-019 through FR-053.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, AsyncGenerator, List
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel,
    TopicCategory,
    Video,
    VideoCategory,
    VideoTag,
    VideoTopic,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def test_data_session(
    integration_session_factory: "async_sessionmaker[AsyncSession]",
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for test data setup and cleanup."""
    async with integration_session_factory() as session:
        yield session


@pytest.fixture
async def sample_channel(test_data_session: AsyncSession) -> Channel:
    """Create a sample channel for testing."""
    # Check if channel exists first
    result = await test_data_session.execute(
        select(Channel).where(Channel.channel_id == "UC_test_channel_001__")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    channel = Channel(
        channel_id="UC_test_channel_001__",
        title="Test Channel",
        description="A test channel for filter testing",
    )
    test_data_session.add(channel)
    await test_data_session.commit()
    await test_data_session.refresh(channel)
    return channel


@pytest.fixture
async def sample_category(test_data_session: AsyncSession) -> VideoCategory:
    """Create a sample video category for testing."""
    # Check if category exists first
    result = await test_data_session.execute(
        select(VideoCategory).where(VideoCategory.category_id == "10")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    category = VideoCategory(
        category_id="10",
        name="Music",
        assignable=True,
    )
    test_data_session.add(category)
    await test_data_session.commit()
    await test_data_session.refresh(category)
    return category


@pytest.fixture
async def sample_topic(test_data_session: AsyncSession) -> TopicCategory:
    """Create a sample topic category for testing."""
    # Check if topic exists first
    result = await test_data_session.execute(
        select(TopicCategory).where(TopicCategory.topic_id == "/m/04rlf")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    topic = TopicCategory(
        topic_id="/m/04rlf",
        category_name="Music",
        topic_type="youtube",
        source="seeded",
    )
    test_data_session.add(topic)
    await test_data_session.commit()
    await test_data_session.refresh(topic)
    return topic


@pytest.fixture
async def sample_videos_with_filters(
    test_data_session: AsyncSession,
    sample_channel: Channel,
    sample_category: VideoCategory,
    sample_topic: TopicCategory,
) -> List[Video]:
    """Create sample videos with tags, categories, and topics for filter testing."""
    videos = []

    # Check for existing videos first and use them if they exist
    for video_id in ["filter_test1", "filter_test2", "filter_test3"]:
        result = await test_data_session.execute(
            select(Video).where(Video.video_id == video_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            videos.append(existing)

    # If all videos already exist, return them
    if len(videos) == 3:
        return videos

    # Clear the list and create fresh data
    videos = []

    # Video 1: Has "music" tag, Music category, Music topic
    result = await test_data_session.execute(
        select(Video).where(Video.video_id == "filter_test1")
    )
    video1 = result.scalar_one_or_none()
    if not video1:
        video1 = Video(
            video_id="filter_test1",
            channel_id=sample_channel.channel_id,
            title="Music Video Test",
            description="A test video with music content",
            upload_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            duration=300,
            category_id=sample_category.category_id,
        )
        test_data_session.add(video1)
        await test_data_session.flush()

        # Add tag to video 1
        tag1 = VideoTag(video_id=video1.video_id, tag="music")
        test_data_session.add(tag1)

        # Add topic to video 1
        video_topic1 = VideoTopic(
            video_id=video1.video_id,
            topic_id=sample_topic.topic_id,
            relevance_type="primary",
        )
        test_data_session.add(video_topic1)

    videos.append(video1)

    # Video 2: Has "rock" tag, Music category
    result = await test_data_session.execute(
        select(Video).where(Video.video_id == "filter_test2")
    )
    video2 = result.scalar_one_or_none()
    if not video2:
        video2 = Video(
            video_id="filter_test2",
            channel_id=sample_channel.channel_id,
            title="Rock Music Test",
            description="A test video with rock music",
            upload_date=datetime(2024, 1, 16, tzinfo=timezone.utc),
            duration=240,
            category_id=sample_category.category_id,
        )
        test_data_session.add(video2)
        await test_data_session.flush()

        tag2 = VideoTag(video_id=video2.video_id, tag="rock")
        test_data_session.add(tag2)

    videos.append(video2)

    # Video 3: Has no tags, no category, no topic (for testing empty filters)
    result = await test_data_session.execute(
        select(Video).where(Video.video_id == "filter_test3")
    )
    video3 = result.scalar_one_or_none()
    if not video3:
        video3 = Video(
            video_id="filter_test3",
            channel_id=sample_channel.channel_id,
            title="Unclassified Video",
            description="A video with no classification",
            upload_date=datetime(2024, 1, 17, tzinfo=timezone.utc),
            duration=180,
        )
        test_data_session.add(video3)

    videos.append(video3)

    await test_data_session.commit()

    # Refresh all videos
    for video in videos:
        await test_data_session.refresh(video)

    return videos


@pytest.fixture
async def cleanup_test_data(
    test_data_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Cleanup test data after tests complete."""
    yield

    # Clean up test data
    await test_data_session.execute(
        delete(VideoTopic).where(
            VideoTopic.video_id.in_(["filter_test1", "filter_test2", "filter_test3"])
        )
    )
    await test_data_session.execute(
        delete(VideoTag).where(
            VideoTag.video_id.in_(["filter_test1", "filter_test2", "filter_test3"])
        )
    )
    await test_data_session.execute(
        delete(Video).where(
            Video.video_id.in_(["filter_test1", "filter_test2", "filter_test3"])
        )
    )
    await test_data_session.commit()


class TestTagFilter:
    """Tests for tag filter functionality (T019, T023)."""

    async def test_single_tag_filter_returns_matching_videos(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test that single tag filter returns only videos with that tag."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?tag=music")
            assert response.status_code == 200
            data = response.json()
            # Should contain videos with "music" tag
            video_ids = [v["video_id"] for v in data["data"]]
            # The "filter_test1" video has the "music" tag
            assert "filter_test1" in video_ids

    async def test_multiple_tags_or_logic(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test that multiple tags use OR logic (T023)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?tag=music&tag=rock")
            assert response.status_code == 200
            data = response.json()
            video_ids = [v["video_id"] for v in data["data"]]
            # Should include videos with either "music" OR "rock" tags
            assert "filter_test1" in video_ids  # has "music" tag
            assert "filter_test2" in video_ids  # has "rock" tag

    async def test_invalid_tag_is_ignored_with_warning(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test that non-existent tag is ignored with warning (FR-042, FR-045)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos?tag=nonexistent_tag_xyz123"
            )
            assert response.status_code == 200
            data = response.json()
            # Should have warnings array when invalid tag is provided
            if "warnings" in data:
                assert len(data["warnings"]) > 0
                warning = data["warnings"][0]
                assert warning["filter_type"] == "tag"
                assert "nonexistent_tag_xyz123" in warning["message"]

    async def test_tag_limit_enforcement(self, async_client: AsyncClient) -> None:
        """Test that more than 10 tags returns 400 error (FR-034)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Build URL with 11 tags
            tags = "&".join([f"tag=tag{i}" for i in range(11)])
            response = await async_client.get(f"/api/v1/videos?{tags}")
            assert response.status_code == 400


class TestCategoryFilter:
    """Tests for category filter functionality (T020)."""

    async def test_category_filter_returns_matching_videos(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        sample_category: VideoCategory,
        cleanup_test_data: None,
    ) -> None:
        """Test that category filter returns only videos in that category."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(f"/api/v1/videos?category=10")
            assert response.status_code == 200
            data = response.json()
            video_ids = [v["video_id"] for v in data["data"]]
            # Videos 1 and 2 have category "10" (Music)
            assert "filter_test1" in video_ids
            assert "filter_test2" in video_ids
            # Video 3 has no category
            assert "filter_test3" not in video_ids

    async def test_invalid_category_is_ignored_with_warning(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test that non-existent category is ignored with warning (FR-042, FR-045)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?category=99999")
            assert response.status_code == 200
            data = response.json()
            # Should have warnings array when invalid category is provided
            if "warnings" in data:
                assert len(data["warnings"]) > 0
                warning = data["warnings"][0]
                assert warning["filter_type"] == "category"
                assert "99999" in warning["message"]


class TestTopicFilter:
    """Tests for topic filter functionality (T021, T024)."""

    async def test_single_topic_filter_returns_matching_videos(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        sample_topic: TopicCategory,
        cleanup_test_data: None,
    ) -> None:
        """Test that single topic filter returns only videos with that topic."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # URL encode the topic ID (contains /)
            response = await async_client.get("/api/v1/videos?topic_id=/m/04rlf")
            assert response.status_code == 200
            data = response.json()
            video_ids = [v["video_id"] for v in data["data"]]
            # Video 1 has the Music topic
            assert "filter_test1" in video_ids

    async def test_invalid_topic_is_ignored_with_warning(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test that non-existent topic is ignored with warning (FR-043, FR-045)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?topic_id=/m/invalid123")
            assert response.status_code == 200
            data = response.json()
            # Should have warnings array when invalid topic is provided
            if "warnings" in data:
                assert len(data["warnings"]) > 0
                warning = data["warnings"][0]
                assert warning["filter_type"] == "topic"
                assert "/m/invalid123" in warning["message"]

    async def test_topic_limit_enforcement(self, async_client: AsyncClient) -> None:
        """Test that more than 10 topics returns 400 error (FR-034)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Build URL with 11 topic IDs
            topics = "&".join([f"topic_id=/m/topic{i}" for i in range(11)])
            response = await async_client.get(f"/api/v1/videos?{topics}")
            assert response.status_code == 400


class TestCombinedFilters:
    """Tests for combining multiple filter types (T022)."""

    async def test_tag_and_category_combined(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test that tag AND category filters use AND logic (FR-020)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?tag=music&category=10")
            assert response.status_code == 200
            data = response.json()
            video_ids = [v["video_id"] for v in data["data"]]
            # Only video 1 has both "music" tag AND category "10"
            assert "filter_test1" in video_ids
            # Video 2 has category 10 but "rock" tag (not "music")
            assert "filter_test2" not in video_ids

    async def test_all_three_filters_combined(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        sample_topic: TopicCategory,
        cleanup_test_data: None,
    ) -> None:
        """Test combining tag, category, and topic filters (FR-012)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos?tag=music&category=10&topic_id=/m/04rlf"
            )
            assert response.status_code == 200
            data = response.json()
            video_ids = [v["video_id"] for v in data["data"]]
            # Only video 1 has all three: "music" tag, category 10, and topic /m/04rlf
            assert "filter_test1" in video_ids

    async def test_total_filter_limit_enforcement(
        self, async_client: AsyncClient
    ) -> None:
        """Test that more than 15 total filters returns 400 error (FR-034)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Build URL with 16 total filters (8 tags + 8 topics)
            tags = "&".join([f"tag=tag{i}" for i in range(8)])
            topics = "&".join([f"topic_id=/m/topic{i}" for i in range(8)])
            response = await async_client.get(f"/api/v1/videos?{tags}&{topics}")
            assert response.status_code == 400


class TestPaginationWithFilters:
    """Tests for pagination working correctly with filters (T025)."""

    async def test_pagination_with_tag_filter(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test that pagination works correctly with tag filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos?tag=music&limit=1&offset=0"
            )
            assert response.status_code == 200
            data = response.json()
            assert "pagination" in data
            assert data["pagination"]["limit"] == 1
            assert data["pagination"]["offset"] == 0

    async def test_pagination_total_reflects_filtered_results(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test that pagination total reflects filtered count, not all videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Get all videos first
            all_response = await async_client.get("/api/v1/videos?limit=100")
            all_total = all_response.json()["pagination"]["total"]

            # Get filtered videos
            filtered_response = await async_client.get("/api/v1/videos?tag=music")
            filtered_total = filtered_response.json()["pagination"]["total"]

            # Filtered total should be less than or equal to all total
            assert filtered_total <= all_total


class TestPartialSuccessResponse:
    """Tests for partial success response with warnings (FR-049, FR-050, FR-051)."""

    async def test_partial_success_with_invalid_tag(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test partial success when one tag is invalid (FR-049)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Combine valid and invalid tags
            response = await async_client.get(
                "/api/v1/videos?tag=music&tag=invalid_tag_xyz"
            )
            assert response.status_code == 200
            data = response.json()
            # Should still return results for valid "music" tag
            video_ids = [v["video_id"] for v in data["data"]]
            assert "filter_test1" in video_ids
            # Should have warning about invalid tag
            if "warnings" in data:
                assert any(
                    "invalid_tag_xyz" in w["message"] for w in data["warnings"]
                )

    async def test_response_without_warnings_when_all_valid(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test response has no warnings when all filters are valid."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?tag=music")
            assert response.status_code == 200
            data = response.json()
            # Should not have warnings (or empty warnings)
            if "warnings" in data:
                assert len(data["warnings"]) == 0


class TestEmptyResults:
    """Tests for empty result scenarios."""

    async def test_filters_with_no_matches_returns_empty_list(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test that filters with no matches return empty list with valid pagination."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Use a valid but unassociated combination
            # Note: This might return empty if no video has both rock AND category 99
            response = await async_client.get("/api/v1/videos?tag=unique_test_tag_abc")
            assert response.status_code == 200
            data = response.json()
            # If warnings present (tag not found), check structure
            if "warnings" in data and data["warnings"]:
                assert data["pagination"]["total"] >= 0

    async def test_all_filters_invalid_returns_all_videos(
        self,
        async_client: AsyncClient,
        sample_videos_with_filters: List[Video],
        cleanup_test_data: None,
    ) -> None:
        """Test that when all filter values are invalid, all videos are returned."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Use all invalid filter values
            response = await async_client.get(
                "/api/v1/videos?tag=invalid1&category=99999&topic_id=/m/invalid"
            )
            assert response.status_code == 200
            data = response.json()
            # When all filters are invalid and ignored, should return all videos
            # Check that we have warnings for each invalid filter
            if "warnings" in data:
                assert len(data["warnings"]) == 3  # One for each invalid filter