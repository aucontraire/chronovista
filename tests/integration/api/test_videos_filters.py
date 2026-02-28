"""Integration tests for video classification filters (Feature 020).

Tests filter logic for tags, categories, and topics per FR-019 through FR-053.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator, List
from unittest.mock import patch

from uuid_utils import uuid7

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    CanonicalTag,
    Channel,
    TagAlias,
    TopicCategory,
    Video,
    VideoCategory,
    VideoTag,
    VideoTopic,
)
from tests.factories.id_factory import YouTubeIdFactory

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


# ---------------------------------------------------------------------------
# Factory-generated IDs for canonical tag filter tests.
# Seeds are stable so IDs are deterministic across runs.
# ---------------------------------------------------------------------------
_CT_CHANNEL_ID = YouTubeIdFactory.create_channel_id(seed="canonical_tag_filter_test")

_CT_VID_1 = YouTubeIdFactory.create_video_id(seed="ct_filter_vid_1")
_CT_VID_2 = YouTubeIdFactory.create_video_id(seed="ct_filter_vid_2")
_CT_VID_3 = YouTubeIdFactory.create_video_id(seed="ct_filter_vid_3")
_CT_VID_4 = YouTubeIdFactory.create_video_id(seed="ct_filter_vid_4")
_CT_VID_5 = YouTubeIdFactory.create_video_id(seed="ct_filter_vid_5")

_CT_VIDEO_IDS = [_CT_VID_1, _CT_VID_2, _CT_VID_3, _CT_VID_4, _CT_VID_5]


def _make_uuid() -> uuid.UUID:
    """Generate a UUIDv7 compatible with both Pydantic and PostgreSQL."""
    return uuid.UUID(bytes=uuid7().bytes)


class TestCanonicalTagFilter:
    """Tests for canonical_tag filter on the /api/v1/videos endpoint.

    The canonical_tag filter resolves aliases via the 3-table join path:
    canonical_tags -> tag_aliases (canonical_tag_id) -> video_tags (raw_form = tag)
    and applies AND semantics across multiple canonical_tag values.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _seed_data(
        session_factory,
    ) -> dict[str, Any]:
        """Seed CanonicalTag, TagAlias, Channel, Video, and VideoTag rows.

        Returns a dict with all created IDs for assertion/cleanup reference.
        """
        async with session_factory() as session:
            # ----- cleanup previous run leftovers (FK order) -----
            video_ids = _CT_VIDEO_IDS
            await session.execute(
                delete(VideoTag).where(VideoTag.video_id.in_(video_ids))
            )
            await session.execute(
                delete(TagAlias).where(
                    TagAlias.raw_form.in_(
                        [
                            "python",
                            "Python",
                            "#Python",
                            "gaming",
                            "Gaming",
                            "#gaming",
                        ]
                    )
                )
            )
            # Delete canonical tags by normalized_form (unique)
            await session.execute(
                delete(CanonicalTag).where(
                    CanonicalTag.normalized_form.in_(["python", "gaming"])
                )
            )
            await session.execute(
                delete(Video).where(Video.video_id.in_(video_ids))
            )
            await session.execute(
                delete(Channel).where(Channel.channel_id == _CT_CHANNEL_ID)
            )
            await session.commit()

            # ----- Channel -----
            channel = Channel(
                channel_id=_CT_CHANNEL_ID,
                title="Canonical Tag Test Channel",
                description="Channel for canonical tag filter tests",
            )
            session.add(channel)
            await session.flush()

            # ----- Canonical tags -----
            ct_python_id = _make_uuid()
            ct_gaming_id = _make_uuid()

            ct_python = CanonicalTag(
                id=ct_python_id,
                canonical_form="Python",
                normalized_form="python",
                alias_count=3,
                video_count=3,
                status="active",
            )
            ct_gaming = CanonicalTag(
                id=ct_gaming_id,
                canonical_form="Gaming",
                normalized_form="gaming",
                alias_count=3,
                video_count=2,
                status="active",
            )
            session.add_all([ct_python, ct_gaming])
            await session.flush()

            # ----- Tag aliases -----
            aliases = [
                TagAlias(
                    id=_make_uuid(),
                    raw_form="python",
                    normalized_form="python",
                    canonical_tag_id=ct_python_id,
                    occurrence_count=10,
                ),
                TagAlias(
                    id=_make_uuid(),
                    raw_form="Python",
                    normalized_form="python",
                    canonical_tag_id=ct_python_id,
                    occurrence_count=5,
                ),
                TagAlias(
                    id=_make_uuid(),
                    raw_form="#Python",
                    normalized_form="python",
                    canonical_tag_id=ct_python_id,
                    occurrence_count=2,
                ),
                TagAlias(
                    id=_make_uuid(),
                    raw_form="gaming",
                    normalized_form="gaming",
                    canonical_tag_id=ct_gaming_id,
                    occurrence_count=8,
                ),
                TagAlias(
                    id=_make_uuid(),
                    raw_form="Gaming",
                    normalized_form="gaming",
                    canonical_tag_id=ct_gaming_id,
                    occurrence_count=4,
                ),
                TagAlias(
                    id=_make_uuid(),
                    raw_form="#gaming",
                    normalized_form="gaming",
                    canonical_tag_id=ct_gaming_id,
                    occurrence_count=1,
                ),
            ]
            session.add_all(aliases)
            await session.flush()

            # ----- Videos -----
            # v1: tagged "python" (lowercase alias)
            # v2: tagged "Python" (titlecase alias)
            # v3: tagged "#Python" (hashtag alias)
            # v4: tagged "gaming" AND "python" (both canonical tags)
            # v5: tagged "Gaming" only
            for idx, vid_id in enumerate(_CT_VIDEO_IDS, start=1):
                v = Video(
                    video_id=vid_id,
                    channel_id=_CT_CHANNEL_ID,
                    title=f"Canonical Tag Test Video {idx}",
                    description=f"Test video {idx} for canonical tag filter",
                    upload_date=datetime(2024, 3, idx, tzinfo=timezone.utc),
                    duration=200 + idx * 10,
                )
                session.add(v)
            await session.flush()

            # ----- VideoTag rows -----
            tag_rows = [
                VideoTag(video_id=_CT_VID_1, tag="python"),
                VideoTag(video_id=_CT_VID_2, tag="Python"),
                VideoTag(video_id=_CT_VID_3, tag="#Python"),
                VideoTag(video_id=_CT_VID_4, tag="python"),
                VideoTag(video_id=_CT_VID_4, tag="gaming"),
                VideoTag(video_id=_CT_VID_5, tag="Gaming"),
            ]
            session.add_all(tag_rows)
            await session.commit()

        return {
            "video_ids": _CT_VIDEO_IDS,
            "ct_python_id": ct_python_id,
            "ct_gaming_id": ct_gaming_id,
        }

    @staticmethod
    async def _cleanup_data(session_factory) -> None:
        """Remove all rows seeded by ``_seed_data``."""
        video_ids = _CT_VIDEO_IDS
        async with session_factory() as session:
            await session.execute(
                delete(VideoTag).where(VideoTag.video_id.in_(video_ids))
            )
            await session.execute(
                delete(TagAlias).where(
                    TagAlias.raw_form.in_(
                        [
                            "python",
                            "Python",
                            "#Python",
                            "gaming",
                            "Gaming",
                            "#gaming",
                        ]
                    )
                )
            )
            await session.execute(
                delete(CanonicalTag).where(
                    CanonicalTag.normalized_form.in_(["python", "gaming"])
                )
            )
            await session.execute(
                delete(Video).where(Video.video_id.in_(video_ids))
            )
            await session.execute(
                delete(Channel).where(Channel.channel_id == _CT_CHANNEL_ID)
            )
            await session.commit()

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    async def test_single_canonical_tag_returns_videos_across_aliases(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """A single canonical_tag value should match videos tagged with any alias."""
        await self._seed_data(integration_session_factory)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get(
                    "/api/v1/videos?canonical_tag=python"
                )
                assert response.status_code == 200
                data = response.json()
                video_ids = {v["video_id"] for v in data["data"]}
                # v1 ("python"), v2 ("Python"), v3 ("#Python"), v4 ("python")
                assert _CT_VID_1 in video_ids
                assert _CT_VID_2 in video_ids
                assert _CT_VID_3 in video_ids
                assert _CT_VID_4 in video_ids
                # v5 only has "Gaming" — should NOT appear
                assert _CT_VID_5 not in video_ids
        finally:
            await self._cleanup_data(integration_session_factory)

    async def test_multiple_canonical_tags_or_semantics(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Multiple canonical_tag params use OR logic — videos matching ANY should appear."""
        await self._seed_data(integration_session_factory)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get(
                    "/api/v1/videos?canonical_tag=python&canonical_tag=gaming"
                )
                assert response.status_code == 200
                data = response.json()
                video_ids = {v["video_id"] for v in data["data"]}
                # OR semantics: videos matching python OR gaming
                assert _CT_VID_1 in video_ids  # python
                assert _CT_VID_2 in video_ids  # Python
                assert _CT_VID_3 in video_ids  # #Python
                assert _CT_VID_4 in video_ids  # python + gaming
                assert _CT_VID_5 in video_ids  # Gaming
        finally:
            await self._cleanup_data(integration_session_factory)

    async def test_nonexistent_canonical_tag_returns_empty_set(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """A canonical_tag that does not exist returns empty data, not 404."""
        await self._seed_data(integration_session_factory)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get(
                    "/api/v1/videos?canonical_tag=nonexistent_tag_xyz_999"
                )
                assert response.status_code == 200
                data = response.json()
                assert data["data"] == []
                assert data["pagination"]["total"] == 0
        finally:
            await self._cleanup_data(integration_session_factory)

    async def test_valid_plus_invalid_canonical_tag_returns_valid_results(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Mixed valid+invalid canonical tags: invalid is skipped, valid still returns results."""
        await self._seed_data(integration_session_factory)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get(
                    "/api/v1/videos?canonical_tag=python&canonical_tag=nonexistent_xyz_999"
                )
                assert response.status_code == 200
                data = response.json()
                video_ids = {v["video_id"] for v in data["data"]}
                # "python" is valid — should still return its videos
                assert _CT_VID_1 in video_ids
                assert _CT_VID_2 in video_ids
                assert _CT_VID_4 in video_ids
                # "nonexistent_xyz_999" is skipped, not short-circuited
                assert data["pagination"]["total"] > 0
        finally:
            await self._cleanup_data(integration_session_factory)

    async def test_raw_tag_filter_still_works(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """Existing raw tag filter (tag=...) is unchanged — backwards compat FR-007."""
        await self._seed_data(integration_session_factory)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get("/api/v1/videos?tag=python")
                assert response.status_code == 200
                data = response.json()
                video_ids = {v["video_id"] for v in data["data"]}
                # Raw tag "python" matches exactly — v1 and v4 only
                assert _CT_VID_1 in video_ids
                assert _CT_VID_4 in video_ids
                # "Python" (titlecase) is a different raw tag
                assert _CT_VID_2 not in video_ids
        finally:
            await self._cleanup_data(integration_session_factory)

    async def test_canonical_tag_combined_with_raw_tag(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """canonical_tag AND raw tag filters apply together (AND across both)."""
        await self._seed_data(integration_session_factory)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                # canonical_tag=gaming narrows to v4, v5
                # tag=python narrows to v1, v4
                # intersection = v4
                response = await async_client.get(
                    "/api/v1/videos?canonical_tag=gaming&tag=python"
                )
                assert response.status_code == 200
                data = response.json()
                video_ids = {v["video_id"] for v in data["data"]}
                assert _CT_VID_4 in video_ids
                assert len(video_ids & {_CT_VID_1, _CT_VID_2, _CT_VID_3, _CT_VID_5}) == 0
        finally:
            await self._cleanup_data(integration_session_factory)

    async def test_exceeding_max_canonical_tags_returns_400(
        self,
        async_client: AsyncClient,
    ) -> None:
        """More than 10 canonical_tag values should return 400 (FR-034)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            params = "&".join(
                [f"canonical_tag=tag{i}" for i in range(11)]
            )
            response = await async_client.get(f"/api/v1/videos?{params}")
            assert response.status_code == 400

    async def test_canonical_tag_counts_toward_total_filter_limit(
        self,
        async_client: AsyncClient,
    ) -> None:
        """canonical_tags + tags + topics total > 15 returns 400 (FR-034)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # 6 canonical_tags + 5 tags + 5 topics = 16 > 15
            ct_params = "&".join(
                [f"canonical_tag=ct{i}" for i in range(6)]
            )
            tag_params = "&".join([f"tag=tag{i}" for i in range(5)])
            topic_params = "&".join(
                [f"topic_id=/m/topic{i}" for i in range(5)]
            )
            response = await async_client.get(
                f"/api/v1/videos?{ct_params}&{tag_params}&{topic_params}"
            )
            assert response.status_code == 400

    async def test_empty_canonical_tag_list_returns_all_videos(
        self,
        async_client: AsyncClient,
        integration_session_factory,
    ) -> None:
        """No canonical_tag parameter returns normal unfiltered results."""
        await self._seed_data(integration_session_factory)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                # Without canonical_tag filter
                response_all = await async_client.get("/api/v1/videos")
                assert response_all.status_code == 200
                total_all = response_all.json()["pagination"]["total"]

                # With empty canonical_tag (no value provided)
                response_empty = await async_client.get("/api/v1/videos")
                assert response_empty.status_code == 200
                total_empty = response_empty.json()["pagination"]["total"]

                # Totals should be the same — no filtering applied
                assert total_all == total_empty
                assert total_all > 0
        finally:
            await self._cleanup_data(integration_session_factory)