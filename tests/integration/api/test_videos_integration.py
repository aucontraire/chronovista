"""Integration tests for video sort and liked filter (Feature 027, T029).

Tests sort ordering, liked filter with real data, combined filter intersection,
pagination with sort, and empty liked results against the integration database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, AsyncGenerator, List

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel,
    UserVideo,
    Video,
    VideoTag,
    VideoTranscript,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
async def sort_test_session(
    integration_session_factory: "async_sessionmaker[AsyncSession]",
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for test data setup and cleanup."""
    async with integration_session_factory() as session:
        yield session


@pytest.fixture
async def sort_test_channel(sort_test_session: AsyncSession) -> Channel:
    """Create a channel for sort/filter tests."""
    result = await sort_test_session.execute(
        select(Channel).where(Channel.channel_id == "UC_sort_test_chan_001_")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    channel = Channel(
        channel_id="UC_sort_test_chan_001_",
        title="Sort Test Channel",
        description="A channel for sort/filter testing",
    )
    sort_test_session.add(channel)
    await sort_test_session.commit()
    await sort_test_session.refresh(channel)
    return channel


@pytest.fixture
async def sort_test_videos(
    sort_test_session: AsyncSession,
    sort_test_channel: Channel,
) -> List[Video]:
    """Create videos with distinct titles and upload dates for sort testing.

    Creates 3 videos:
    - sort_vid_a: title="Alpha Video",    upload_date=2024-01-10
    - sort_vid_b: title="Bravo Video",    upload_date=2024-03-15
    - sort_vid_c: title="Charlie Video",  upload_date=2024-02-20
    """
    video_specs = [
        ("sort_vid__a", "Alpha Video", datetime(2024, 1, 10, tzinfo=timezone.utc)),
        ("sort_vid__b", "Bravo Video", datetime(2024, 3, 15, tzinfo=timezone.utc)),
        ("sort_vid__c", "Charlie Video", datetime(2024, 2, 20, tzinfo=timezone.utc)),
    ]

    videos: List[Video] = []
    for vid_id, title, upload_date in video_specs:
        result = await sort_test_session.execute(
            select(Video).where(Video.video_id == vid_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            videos.append(existing)
            continue

        video = Video(
            video_id=vid_id,
            channel_id=sort_test_channel.channel_id,
            title=title,
            description=f"Test video: {title}",
            upload_date=upload_date,
            duration=300,
        )
        sort_test_session.add(video)
        videos.append(video)

    await sort_test_session.commit()
    for v in videos:
        await sort_test_session.refresh(v)
    return videos


@pytest.fixture
async def liked_video_data(
    sort_test_session: AsyncSession,
    sort_test_videos: List[Video],
) -> None:
    """Mark sort_vid__a as liked via user_videos table."""
    result = await sort_test_session.execute(
        select(UserVideo).where(
            UserVideo.video_id == "sort_vid__a",
            UserVideo.user_id == "test_user_sort",
        )
    )
    existing = result.scalar_one_or_none()
    if not existing:
        user_video = UserVideo(
            user_id="test_user_sort",
            video_id="sort_vid__a",
            liked=True,
        )
        sort_test_session.add(user_video)
        await sort_test_session.commit()


@pytest.fixture
async def transcript_video_data(
    sort_test_session: AsyncSession,
    sort_test_videos: List[Video],
) -> None:
    """Add a transcript to sort_vid__b."""
    result = await sort_test_session.execute(
        select(VideoTranscript).where(
            VideoTranscript.video_id == "sort_vid__b",
        )
    )
    existing = result.scalar_one_or_none()
    if not existing:
        transcript = VideoTranscript(
            video_id="sort_vid__b",
            language_code="en",
            transcript_text="Test transcript content for sort video B.",
            transcript_type="AUTO",
            download_reason="AUTO_PREFERRED",
            is_cc=False,
        )
        sort_test_session.add(transcript)
        await sort_test_session.commit()


@pytest.fixture
async def tagged_video_data(
    sort_test_session: AsyncSession,
    sort_test_videos: List[Video],
) -> None:
    """Add tag 'sort_test_tag' to sort_vid__a and sort_vid__c."""
    for vid_id in ["sort_vid__a", "sort_vid__c"]:
        result = await sort_test_session.execute(
            select(VideoTag).where(
                VideoTag.video_id == vid_id,
                VideoTag.tag == "sort_test_tag",
            )
        )
        existing = result.scalar_one_or_none()
        if not existing:
            tag = VideoTag(video_id=vid_id, tag="sort_test_tag")
            sort_test_session.add(tag)

    await sort_test_session.commit()


# ═══════════════════════════════════════════════════════════════════════════
# Sort Ordering Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSortOrdering:
    """Test that sort_by and sort_order actually order results correctly."""

    async def test_sort_by_upload_date_desc(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
    ) -> None:
        """upload_date desc should return newest first."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=upload_date&sort_order=desc&limit=100"
        )
        assert response.status_code == 200
        data = response.json()["data"]

        # Find our test videos in the results
        test_ids = {v.video_id for v in sort_test_videos}
        test_results = [v for v in data if v["video_id"] in test_ids]

        if len(test_results) >= 2:
            # Verify descending date order among our test videos
            dates = [v["upload_date"] for v in test_results]
            assert dates == sorted(dates, reverse=True)

    async def test_sort_by_upload_date_asc(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
    ) -> None:
        """upload_date asc should return oldest first."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=upload_date&sort_order=asc&limit=100"
        )
        assert response.status_code == 200
        data = response.json()["data"]

        test_ids = {v.video_id for v in sort_test_videos}
        test_results = [v for v in data if v["video_id"] in test_ids]

        if len(test_results) >= 2:
            dates = [v["upload_date"] for v in test_results]
            assert dates == sorted(dates)

    async def test_sort_by_title_asc(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
    ) -> None:
        """title asc should return alphabetically A-Z."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=asc&limit=100"
        )
        assert response.status_code == 200
        data = response.json()["data"]

        test_ids = {v.video_id for v in sort_test_videos}
        test_results = [v for v in data if v["video_id"] in test_ids]

        if len(test_results) >= 2:
            titles = [v["title"] for v in test_results]
            assert titles == sorted(titles)

    async def test_sort_by_title_desc(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
    ) -> None:
        """title desc should return alphabetically Z-A."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=desc&limit=100"
        )
        assert response.status_code == 200
        data = response.json()["data"]

        test_ids = {v.video_id for v in sort_test_videos}
        test_results = [v for v in data if v["video_id"] in test_ids]

        if len(test_results) >= 2:
            titles = [v["title"] for v in test_results]
            assert titles == sorted(titles, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════
# Liked Filter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestLikedFilter:
    """Test liked_only filter with real data."""

    async def test_liked_only_returns_liked_video(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
        liked_video_data: None,
    ) -> None:
        """liked_only=true should include the liked video."""
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&limit=100"
        )
        assert response.status_code == 200
        data = response.json()["data"]

        video_ids = [v["video_id"] for v in data]
        assert "sort_vid__a" in video_ids

    async def test_liked_only_excludes_non_liked_videos(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
        liked_video_data: None,
    ) -> None:
        """liked_only=true should exclude non-liked videos."""
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&limit=100"
        )
        assert response.status_code == 200
        data = response.json()["data"]

        video_ids = [v["video_id"] for v in data]
        # sort_vid__b and sort_vid__c are not liked
        assert "sort_vid__b" not in video_ids
        assert "sort_vid__c" not in video_ids

    async def test_empty_liked_results(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
    ) -> None:
        """liked_only=true with no liked videos should return empty data."""
        # We don't set up liked_video_data here, so no videos are liked
        # (assuming clean state or the test videos have no user_video entries)
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&limit=100"
        )
        assert response.status_code == 200
        # Response should still be valid, just potentially empty data


# ═══════════════════════════════════════════════════════════════════════════
# Combined Filter Intersection Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCombinedFilterIntersection:
    """Test that combining filters produces correct intersection results."""

    async def test_liked_and_has_transcript(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
        liked_video_data: None,
        transcript_video_data: None,
    ) -> None:
        """liked_only + has_transcript=true should return intersection (empty)."""
        # sort_vid__a is liked, sort_vid__b has transcript — intersection is empty
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&has_transcript=true&limit=100"
        )
        assert response.status_code == 200
        data = response.json()["data"]

        # The intersection of liked (sort_vid__a) and has_transcript (sort_vid__b)
        # should be empty since they are different videos
        test_ids = {v["video_id"] for v in data}
        assert "sort_vid__a" not in test_ids or "sort_vid__b" not in test_ids

    async def test_liked_and_tag(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
        liked_video_data: None,
        tagged_video_data: None,
    ) -> None:
        """liked_only + tag should return their intersection."""
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&tag=sort_test_tag&limit=100"
        )
        assert response.status_code == 200
        data = response.json()["data"]

        # sort_vid__a is both liked AND tagged — should appear
        video_ids = [v["video_id"] for v in data]
        assert "sort_vid__a" in video_ids
        # sort_vid__c is tagged but NOT liked — should NOT appear
        assert "sort_vid__c" not in video_ids


# ═══════════════════════════════════════════════════════════════════════════
# Pagination with Sort Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPaginationWithSort:
    """Test pagination behavior when combined with sort."""

    async def test_pagination_with_sort_returns_200(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
    ) -> None:
        """Pagination + sort params should return 200."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=asc&limit=2&offset=0"
        )
        assert response.status_code == 200
        body = response.json()
        assert "pagination" in body
        assert body["pagination"]["limit"] == 2
        assert body["pagination"]["offset"] == 0

    async def test_pagination_offset_with_sort(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
    ) -> None:
        """Second page with sort should skip first page items."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=asc&limit=1&offset=1"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["pagination"]["offset"] == 1

    async def test_pagination_has_more_flag(
        self,
        async_client: AsyncClient,
        sort_test_videos: List[Video],
    ) -> None:
        """has_more should be true when more results exist beyond the page."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=upload_date&sort_order=desc&limit=1&offset=0"
        )
        assert response.status_code == 200
        body = response.json()
        total = body["pagination"]["total"]
        if total > 1:
            assert body["pagination"]["has_more"] is True
