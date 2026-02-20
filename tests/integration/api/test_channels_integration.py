"""Integration tests for channel list sort, subscription filter, and channel video sort/liked (Feature 027, US-3/US-5).

Tests sort ordering with real data, subscription filter accuracy,
count reflects filtered results, and pagination with subscription filter.
Also tests channel video sort and liked filter (US-5).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncGenerator, List
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel, UserVideo, Video
from chronovista.models.enums import AvailabilityStatus

pytestmark = pytest.mark.asyncio

# Test channel IDs (all exactly 24 characters)
CH_SUB_A = "UCsort_sub_a_1234567890"  # subscribed, video_count=500, title="Alpha"
CH_SUB_B = "UCsort_sub_b_1234567890"  # subscribed, video_count=100, title="Beta"
CH_NOSUB = "UCsort_nosub_12345678901"  # not subscribed, video_count=300, title="Gamma"
CH_NULL = "UCsort_null_123456789012"  # not subscribed, video_count=None, title="Delta"

ALL_TEST_IDS = [CH_SUB_A, CH_SUB_B, CH_NOSUB, CH_NULL]


@pytest.fixture
async def test_data_session(
    integration_session_factory,
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for test data setup and cleanup."""
    async with integration_session_factory() as session:
        yield session


@pytest.fixture
async def channel_sort_data(
    test_data_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Create test channels with known sort/filter characteristics."""
    # Clean up any existing test channels first
    await test_data_session.execute(
        delete(Channel).where(Channel.channel_id.in_(ALL_TEST_IDS))
    )
    await test_data_session.flush()

    channels = [
        Channel(
            channel_id=CH_SUB_A,
            title="Alpha",
            description="Subscribed channel A",
            subscriber_count=1000,
            video_count=500,
            is_subscribed=True,
            availability_status=AvailabilityStatus.AVAILABLE.value,
        ),
        Channel(
            channel_id=CH_SUB_B,
            title="Beta",
            description="Subscribed channel B",
            subscriber_count=2000,
            video_count=100,
            is_subscribed=True,
            availability_status=AvailabilityStatus.AVAILABLE.value,
        ),
        Channel(
            channel_id=CH_NOSUB,
            title="Gamma",
            description="Not subscribed channel",
            subscriber_count=500,
            video_count=300,
            is_subscribed=False,
            availability_status=AvailabilityStatus.AVAILABLE.value,
        ),
        Channel(
            channel_id=CH_NULL,
            title="Delta",
            description="Not subscribed, null video_count",
            subscriber_count=100,
            video_count=None,
            is_subscribed=False,
            availability_status=AvailabilityStatus.AVAILABLE.value,
        ),
    ]
    for ch in channels:
        test_data_session.add(ch)

    await test_data_session.commit()

    yield

    # Cleanup
    await test_data_session.execute(
        delete(Channel).where(Channel.channel_id.in_(ALL_TEST_IDS))
    )
    await test_data_session.commit()


def _get_test_channels(data: list[dict[str, Any]], test_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Filter response data to only include our test channels."""
    ids = test_ids or ALL_TEST_IDS
    return [ch for ch in data if ch["channel_id"] in ids]


# ═══════════════════════════════════════════════════════════════════════════
# Sort Ordering Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelSortOrdering:
    """Tests for sort ordering with real data."""

    async def test_sort_by_video_count_desc(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test video_count desc returns highest video_count first."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=video_count&sort_order=desc&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_channels = _get_test_channels(data["data"])
            assert len(test_channels) >= 3  # At least our 3 non-null channels

            # Verify descending order for our test channels
            channel_ids = [ch["channel_id"] for ch in test_channels]
            # Alpha(500) should come before Gamma(300) which should come before Beta(100)
            assert channel_ids.index(CH_SUB_A) < channel_ids.index(CH_NOSUB)
            assert channel_ids.index(CH_NOSUB) < channel_ids.index(CH_SUB_B)

    async def test_sort_by_video_count_asc(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test video_count asc returns lowest video_count first."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=video_count&sort_order=asc&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_channels = _get_test_channels(data["data"])
            channel_ids = [ch["channel_id"] for ch in test_channels]
            # Beta(100) should come before Gamma(300) which should come before Alpha(500)
            assert channel_ids.index(CH_SUB_B) < channel_ids.index(CH_NOSUB)
            assert channel_ids.index(CH_NOSUB) < channel_ids.index(CH_SUB_A)

    async def test_sort_by_name_asc(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test name asc returns alphabetical order."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=name&sort_order=asc&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_channels = _get_test_channels(data["data"])
            channel_ids = [ch["channel_id"] for ch in test_channels]
            # Alpha < Beta < Delta < Gamma
            assert channel_ids.index(CH_SUB_A) < channel_ids.index(CH_SUB_B)
            assert channel_ids.index(CH_SUB_B) < channel_ids.index(CH_NULL)
            assert channel_ids.index(CH_NULL) < channel_ids.index(CH_NOSUB)

    async def test_sort_by_name_desc(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test name desc returns reverse alphabetical order."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=name&sort_order=desc&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_channels = _get_test_channels(data["data"])
            channel_ids = [ch["channel_id"] for ch in test_channels]
            # Gamma > Delta > Beta > Alpha
            assert channel_ids.index(CH_NOSUB) < channel_ids.index(CH_NULL)
            assert channel_ids.index(CH_NULL) < channel_ids.index(CH_SUB_B)
            assert channel_ids.index(CH_SUB_B) < channel_ids.index(CH_SUB_A)

    async def test_null_video_count_appears_last(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test that channels with NULL video_count appear last in both sort orders."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # DESC: NULL should be last
            response = await async_client.get(
                "/api/v1/channels?sort_by=video_count&sort_order=desc&limit=100"
            )
            assert response.status_code == 200
            data = response.json()
            test_channels = _get_test_channels(data["data"])
            channel_ids = [ch["channel_id"] for ch in test_channels]

            # Delta (NULL video_count) should be after all non-null channels
            delta_idx = channel_ids.index(CH_NULL)
            for non_null_id in [CH_SUB_A, CH_SUB_B, CH_NOSUB]:
                assert channel_ids.index(non_null_id) < delta_idx

            # ASC: NULL should also be last (NULLS LAST)
            response = await async_client.get(
                "/api/v1/channels?sort_by=video_count&sort_order=asc&limit=100"
            )
            assert response.status_code == 200
            data = response.json()
            test_channels = _get_test_channels(data["data"])
            channel_ids = [ch["channel_id"] for ch in test_channels]

            delta_idx = channel_ids.index(CH_NULL)
            for non_null_id in [CH_SUB_A, CH_SUB_B, CH_NOSUB]:
                assert channel_ids.index(non_null_id) < delta_idx


# ═══════════════════════════════════════════════════════════════════════════
# Subscription Filter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelSubscriptionFilter:
    """Tests for subscription filter accuracy with real data."""

    async def test_is_subscribed_true_returns_only_subscribed(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test that is_subscribed=true returns only subscribed channels."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?is_subscribed=true&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_channels = _get_test_channels(data["data"])
            test_ids = {ch["channel_id"] for ch in test_channels}

            # Should include subscribed channels
            assert CH_SUB_A in test_ids
            assert CH_SUB_B in test_ids

            # Should NOT include unsubscribed channels
            assert CH_NOSUB not in test_ids
            assert CH_NULL not in test_ids

            # All returned test channels should be subscribed
            for ch in test_channels:
                assert ch["is_subscribed"] is True

    async def test_is_subscribed_false_returns_only_not_subscribed(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test that is_subscribed=false returns only not-subscribed channels."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?is_subscribed=false&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_channels = _get_test_channels(data["data"])
            test_ids = {ch["channel_id"] for ch in test_channels}

            # Should include not-subscribed channels
            assert CH_NOSUB in test_ids
            assert CH_NULL in test_ids

            # Should NOT include subscribed channels
            assert CH_SUB_A not in test_ids
            assert CH_SUB_B not in test_ids

            # All returned test channels should be not subscribed
            for ch in test_channels:
                assert ch["is_subscribed"] is False

    async def test_is_subscribed_omitted_returns_all(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test that omitting is_subscribed returns all channels."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels?limit=100")
            assert response.status_code == 200
            data = response.json()

            test_channels = _get_test_channels(data["data"])
            test_ids = {ch["channel_id"] for ch in test_channels}

            # All test channels should be present
            assert CH_SUB_A in test_ids
            assert CH_SUB_B in test_ids
            assert CH_NOSUB in test_ids
            assert CH_NULL in test_ids


# ═══════════════════════════════════════════════════════════════════════════
# Count Accuracy Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelFilteredCount:
    """Tests that pagination count reflects filtered results."""

    async def test_count_reflects_subscription_filter(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test that total count reflects the is_subscribed filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Get total without filter
            resp_all = await async_client.get("/api/v1/channels?limit=100")
            total_all = resp_all.json()["pagination"]["total"]

            # Get total with is_subscribed=true
            resp_sub = await async_client.get(
                "/api/v1/channels?is_subscribed=true&limit=100"
            )
            total_sub = resp_sub.json()["pagination"]["total"]

            # Get total with is_subscribed=false
            resp_nosub = await async_client.get(
                "/api/v1/channels?is_subscribed=false&limit=100"
            )
            total_nosub = resp_nosub.json()["pagination"]["total"]

            # Subscribed + not subscribed should equal total
            assert total_sub + total_nosub == total_all

            # Filtered counts should be less than total (unless all are one type)
            assert total_sub <= total_all
            assert total_nosub <= total_all


# ═══════════════════════════════════════════════════════════════════════════
# Pagination with Subscription Filter
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelPaginationWithFilter:
    """Tests pagination behavior with subscription filter applied."""

    async def test_pagination_with_subscription_filter(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test that pagination works correctly with subscription filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Get first page of subscribed channels with small limit
            response = await async_client.get(
                "/api/v1/channels?is_subscribed=true&limit=1&offset=0"
            )
            assert response.status_code == 200
            data = response.json()

            # Should have exactly 1 item on page
            assert len(data["data"]) == 1
            # Total should reflect all subscribed channels (at least our 2 test ones)
            assert data["pagination"]["total"] >= 2
            # has_more should be true since there are more subscribed channels
            assert data["pagination"]["has_more"] is True

            # Get second page
            response2 = await async_client.get(
                "/api/v1/channels?is_subscribed=true&limit=1&offset=1"
            )
            assert response2.status_code == 200
            data2 = response2.json()

            # Second page should have different channel
            assert len(data2["data"]) == 1
            assert data2["data"][0]["channel_id"] != data["data"][0]["channel_id"]

    async def test_pagination_offset_beyond_filtered_results(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test that offset beyond filtered result count returns empty list."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?is_subscribed=true&limit=100&offset=10000"
            )
            assert response.status_code == 200
            data = response.json()

            assert len(data["data"]) == 0
            assert data["pagination"]["has_more"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Response Schema Verification
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelListItemSchema:
    """Tests that ChannelListItem response includes is_subscribed field with real data."""

    async def test_channel_list_items_include_is_subscribed(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test that all channel list items include the is_subscribed boolean field."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels?limit=100")
            assert response.status_code == 200
            data = response.json()

            for channel in data["data"]:
                assert "is_subscribed" in channel
                assert isinstance(channel["is_subscribed"], bool)

    async def test_subscribed_channel_has_is_subscribed_true(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test that a known subscribed channel has is_subscribed=True."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels?limit=100")
            assert response.status_code == 200
            data = response.json()

            test_channels = _get_test_channels(data["data"])
            alpha = next(ch for ch in test_channels if ch["channel_id"] == CH_SUB_A)
            assert alpha["is_subscribed"] is True

    async def test_not_subscribed_channel_has_is_subscribed_false(
        self,
        async_client: AsyncClient,
        channel_sort_data: None,
    ) -> None:
        """Test that a known not-subscribed channel has is_subscribed=False."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels?limit=100")
            assert response.status_code == 200
            data = response.json()

            test_channels = _get_test_channels(data["data"])
            gamma = next(ch for ch in test_channels if ch["channel_id"] == CH_NOSUB)
            assert gamma["is_subscribed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Channel Videos Endpoint — Sort & Liked Filter Integration Tests (US-5)
# ═══════════════════════════════════════════════════════════════════════════


# Channel for video tests (exactly 24 characters)
CH_VID_TEST = "UCchvid_test_12345678901"

# Video IDs (exactly 11 characters)
VID_ALPHA = "chv_alpha01"
VID_BRAVO = "chv_bravo01"
VID_CHARLIE = "chv_charli1"

ALL_VIDEO_TEST_IDS = [VID_ALPHA, VID_BRAVO, VID_CHARLIE]


@pytest.fixture
async def channel_video_session(
    integration_session_factory,
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for channel video test data setup and cleanup."""
    async with integration_session_factory() as session:
        yield session


@pytest.fixture
async def channel_video_data(
    channel_video_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Create test channel and videos with known sort characteristics.

    Creates:
    - Channel: CH_VID_TEST
    - Videos:
      - VID_ALPHA: title="Alpha Video", upload_date=2024-01-10
      - VID_BRAVO: title="Bravo Video", upload_date=2024-03-15
      - VID_CHARLIE: title="Charlie Video", upload_date=2024-02-20
    """
    # Clean up first
    await channel_video_session.execute(
        delete(UserVideo).where(UserVideo.video_id.in_(ALL_VIDEO_TEST_IDS))
    )
    await channel_video_session.execute(
        delete(Video).where(Video.video_id.in_(ALL_VIDEO_TEST_IDS))
    )
    await channel_video_session.execute(
        delete(Channel).where(Channel.channel_id == CH_VID_TEST)
    )
    await channel_video_session.flush()

    # Create channel
    channel = Channel(
        channel_id=CH_VID_TEST,
        title="Channel Video Test",
        description="Channel for video sort/liked testing",
        subscriber_count=1000,
        video_count=3,
        is_subscribed=True,
        availability_status=AvailabilityStatus.AVAILABLE.value,
    )
    channel_video_session.add(channel)
    await channel_video_session.flush()

    # Create videos
    video_specs = [
        (VID_ALPHA, "Alpha Video", datetime(2024, 1, 10, tzinfo=timezone.utc)),
        (VID_BRAVO, "Bravo Video", datetime(2024, 3, 15, tzinfo=timezone.utc)),
        (VID_CHARLIE, "Charlie Video", datetime(2024, 2, 20, tzinfo=timezone.utc)),
    ]
    for vid_id, title, upload_date in video_specs:
        video = Video(
            video_id=vid_id,
            channel_id=CH_VID_TEST,
            title=title,
            description=f"Test video: {title}",
            upload_date=upload_date,
            duration=300,
            availability_status=AvailabilityStatus.AVAILABLE.value,
        )
        channel_video_session.add(video)

    await channel_video_session.commit()

    yield

    # Cleanup
    await channel_video_session.execute(
        delete(UserVideo).where(UserVideo.video_id.in_(ALL_VIDEO_TEST_IDS))
    )
    await channel_video_session.execute(
        delete(Video).where(Video.video_id.in_(ALL_VIDEO_TEST_IDS))
    )
    await channel_video_session.execute(
        delete(Channel).where(Channel.channel_id == CH_VID_TEST)
    )
    await channel_video_session.commit()


@pytest.fixture
async def channel_video_liked_data(
    channel_video_session: AsyncSession,
    channel_video_data: None,
) -> None:
    """Mark VID_ALPHA as liked via user_videos table."""
    result = await channel_video_session.execute(
        select(UserVideo).where(
            UserVideo.video_id == VID_ALPHA,
            UserVideo.user_id == "test_user_chvid",
        )
    )
    existing = result.scalar_one_or_none()
    if not existing:
        user_video = UserVideo(
            user_id="test_user_chvid",
            video_id=VID_ALPHA,
            liked=True,
        )
        channel_video_session.add(user_video)
        await channel_video_session.commit()


def _get_test_videos(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter response data to only include our test videos."""
    return [v for v in data if v["video_id"] in ALL_VIDEO_TEST_IDS]


class TestChannelVideoSortOrdering:
    """Tests for channel video sort ordering with real data."""

    async def test_sort_by_upload_date_desc(
        self,
        async_client: AsyncClient,
        channel_video_data: None,
    ) -> None:
        """Test upload_date desc returns most recent first."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos"
                "?sort_by=upload_date&sort_order=desc&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_videos = _get_test_videos(data["data"])
            assert len(test_videos) == 3

            video_ids = [v["video_id"] for v in test_videos]
            # Bravo (2024-03-15) > Charlie (2024-02-20) > Alpha (2024-01-10)
            assert video_ids.index(VID_BRAVO) < video_ids.index(VID_CHARLIE)
            assert video_ids.index(VID_CHARLIE) < video_ids.index(VID_ALPHA)

    async def test_sort_by_upload_date_asc(
        self,
        async_client: AsyncClient,
        channel_video_data: None,
    ) -> None:
        """Test upload_date asc returns oldest first."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos"
                "?sort_by=upload_date&sort_order=asc&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_videos = _get_test_videos(data["data"])
            video_ids = [v["video_id"] for v in test_videos]
            # Alpha (2024-01-10) < Charlie (2024-02-20) < Bravo (2024-03-15)
            assert video_ids.index(VID_ALPHA) < video_ids.index(VID_CHARLIE)
            assert video_ids.index(VID_CHARLIE) < video_ids.index(VID_BRAVO)

    async def test_sort_by_title_asc(
        self,
        async_client: AsyncClient,
        channel_video_data: None,
    ) -> None:
        """Test title asc returns alphabetical order."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos"
                "?sort_by=title&sort_order=asc&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_videos = _get_test_videos(data["data"])
            video_ids = [v["video_id"] for v in test_videos]
            # Alpha < Bravo < Charlie
            assert video_ids.index(VID_ALPHA) < video_ids.index(VID_BRAVO)
            assert video_ids.index(VID_BRAVO) < video_ids.index(VID_CHARLIE)

    async def test_sort_by_title_desc(
        self,
        async_client: AsyncClient,
        channel_video_data: None,
    ) -> None:
        """Test title desc returns reverse alphabetical order."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos"
                "?sort_by=title&sort_order=desc&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_videos = _get_test_videos(data["data"])
            video_ids = [v["video_id"] for v in test_videos]
            # Charlie > Bravo > Alpha
            assert video_ids.index(VID_CHARLIE) < video_ids.index(VID_BRAVO)
            assert video_ids.index(VID_BRAVO) < video_ids.index(VID_ALPHA)


class TestChannelVideoLikedFilter:
    """Tests for channel video liked filter accuracy with real data."""

    async def test_liked_only_returns_liked_videos(
        self,
        async_client: AsyncClient,
        channel_video_liked_data: None,
    ) -> None:
        """Test that liked_only=true returns only liked videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos"
                "?liked_only=true&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_videos = _get_test_videos(data["data"])
            test_ids = {v["video_id"] for v in test_videos}

            # Only Alpha should be present (it is liked)
            assert VID_ALPHA in test_ids
            assert VID_BRAVO not in test_ids
            assert VID_CHARLIE not in test_ids

    async def test_liked_only_empty_results(
        self,
        async_client: AsyncClient,
        channel_video_data: None,
    ) -> None:
        """Test that liked_only=true with no liked videos returns empty results."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # No liked data fixture loaded — no user_videos rows
            response = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos"
                "?liked_only=true&limit=100"
            )
            assert response.status_code == 200
            data = response.json()

            test_videos = _get_test_videos(data["data"])
            assert len(test_videos) == 0

    async def test_liked_filter_count_accuracy(
        self,
        async_client: AsyncClient,
        channel_video_liked_data: None,
    ) -> None:
        """Test that pagination count reflects liked filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Without liked filter
            resp_all = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos?limit=100"
            )
            total_all = resp_all.json()["pagination"]["total"]

            # With liked filter
            resp_liked = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos?liked_only=true&limit=100"
            )
            total_liked = resp_liked.json()["pagination"]["total"]

            # Liked count should be less than or equal to total
            assert total_liked <= total_all
            assert total_liked >= 1  # At least our liked video


class TestChannelVideoPaginationWithSort:
    """Tests for pagination behavior with sort applied to channel videos."""

    async def test_pagination_with_sort(
        self,
        async_client: AsyncClient,
        channel_video_data: None,
    ) -> None:
        """Test that pagination works correctly with sort."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Get first page with limit=1
            response = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos"
                "?sort_by=title&sort_order=asc&limit=1&offset=0"
            )
            assert response.status_code == 200
            data = response.json()

            assert len(data["data"]) == 1
            assert data["pagination"]["has_more"] is True

            # Get second page
            response2 = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos"
                "?sort_by=title&sort_order=asc&limit=1&offset=1"
            )
            assert response2.status_code == 200
            data2 = response2.json()

            assert len(data2["data"]) == 1
            # Second page should have different video
            assert data2["data"][0]["video_id"] != data["data"][0]["video_id"]

    async def test_offset_beyond_results_returns_empty(
        self,
        async_client: AsyncClient,
        channel_video_data: None,
    ) -> None:
        """Test that offset beyond available results returns empty list."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                f"/api/v1/channels/{CH_VID_TEST}/videos"
                "?sort_by=upload_date&sort_order=desc&limit=100&offset=10000"
            )
            assert response.status_code == 200
            data = response.json()

            assert len(data["data"]) == 0
            assert data["pagination"]["has_more"] is False
