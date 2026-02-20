"""
Unit tests for channel list endpoint sort and subscription filter params (Feature 027, US-3),
and channel videos endpoint sort and liked filter params (Feature 027, US-5).

Tests:
- Sort fields (video_count asc/desc, name asc/desc)
- Default sort preserves current behavior (video_count desc)
- is_subscribed filter: true/false/omitted
- ChannelListItem response includes is_subscribed field
- Invalid sort_by returns 422
- Channel videos: sort fields (upload_date, title), liked_only filter
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.main import app
from chronovista.api.deps import get_db

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _make_channel_row(
    channel_id: str,
    title: str,
    video_count: int | None,
    is_subscribed: bool = False,
    availability_status: str = "available",
    description: str | None = "A channel",
    subscriber_count: int | None = 1000,
    thumbnail_url: str | None = None,
) -> MagicMock:
    """Create a mock ChannelDB row object."""
    row = MagicMock()
    row.channel_id = channel_id
    row.title = title
    row.video_count = video_count
    row.is_subscribed = is_subscribed
    row.availability_status = availability_status
    row.description = description
    row.subscriber_count = subscriber_count
    row.thumbnail_url = thumbnail_url
    return row


def _create_mock_session(channels: list[MagicMock] | None = None) -> AsyncMock:
    """Create a mock AsyncSession that returns the given channels.

    The session mock handles two db.execute() calls per list_channels:
    1. Count query -> returns scalar() with total count
    2. Data query -> returns scalars().all() with channel list
    """
    if channels is None:
        channels = []

    mock_session = AsyncMock(spec=AsyncSession)

    # Build result mocks for count and data queries
    count_result = MagicMock()
    count_result.scalar.return_value = len(channels)

    data_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = channels
    data_result.scalars.return_value = scalars_mock

    # execute() is called twice: first for count, then for data
    mock_session.execute.side_effect = [count_result, data_result]

    return mock_session


# Standard test data: 4 channels with different sort/filter characteristics
CHANNEL_ALPHA = _make_channel_row(
    channel_id="UCaaaaaaaaaaaaaaaaaaaaa",
    title="Alpha Channel",
    video_count=100,
    is_subscribed=True,
)
CHANNEL_BETA = _make_channel_row(
    channel_id="UCbbbbbbbbbbbbbbbbbbbbbb",
    title="Beta Channel",
    video_count=500,
    is_subscribed=True,
)
CHANNEL_CHARLIE = _make_channel_row(
    channel_id="UCcccccccccccccccccccccc",
    title="Charlie Channel",
    video_count=200,
    is_subscribed=False,
)
CHANNEL_DELTA = _make_channel_row(
    channel_id="UCdddddddddddddddddddd",
    title="Delta Channel",
    video_count=None,
    is_subscribed=False,
)

ALL_CHANNELS = [CHANNEL_ALPHA, CHANNEL_BETA, CHANNEL_CHARLIE, CHANNEL_DELTA]
SUBSCRIBED_CHANNELS = [CHANNEL_ALPHA, CHANNEL_BETA]
NOT_SUBSCRIBED_CHANNELS = [CHANNEL_CHARLIE, CHANNEL_DELTA]


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for FastAPI testing with mocked DB."""
    mock_session = _create_mock_session(ALL_CHANNELS)

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    app.dependency_overrides[get_db] = mock_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def empty_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with no channels in mock DB."""
    mock_session = _create_mock_session([])

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    app.dependency_overrides[get_db] = mock_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Default Sort Behavior
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelListDefaultSort:
    """Tests that default sort preserves current behavior (video_count desc)."""

    async def test_default_sort_returns_200(self, async_client: AsyncClient) -> None:
        """Test that GET /channels with no sort params returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200

    async def test_default_sort_is_video_count_desc(self, async_client: AsyncClient) -> None:
        """Test that default sort field is video_count with desc order."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data

    async def test_default_returns_channels(self, async_client: AsyncClient) -> None:
        """Test that default query returns channels in response."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 4
            assert data["pagination"]["total"] == 4


# ═══════════════════════════════════════════════════════════════════════════
# Sort Field Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelListSortFields:
    """Tests for sort_by and sort_order query parameters."""

    async def test_sort_by_video_count_desc(self, async_client: AsyncClient) -> None:
        """Test sorting by video_count descending returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=video_count&sort_order=desc"
            )
            assert response.status_code == 200

    async def test_sort_by_video_count_asc(self, async_client: AsyncClient) -> None:
        """Test sorting by video_count ascending returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=video_count&sort_order=asc"
            )
            assert response.status_code == 200

    async def test_sort_by_name_asc(self, async_client: AsyncClient) -> None:
        """Test sorting by name ascending returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=name&sort_order=asc"
            )
            assert response.status_code == 200

    async def test_sort_by_name_desc(self, async_client: AsyncClient) -> None:
        """Test sorting by name descending returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=name&sort_order=desc"
            )
            assert response.status_code == 200

    async def test_invalid_sort_by_returns_422(self, async_client: AsyncClient) -> None:
        """Test that invalid sort_by value returns 422 validation error."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=invalid_field"
            )
            assert response.status_code == 422

    async def test_invalid_sort_order_returns_422(self, async_client: AsyncClient) -> None:
        """Test that invalid sort_order value returns 422 validation error."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_order=invalid"
            )
            assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Subscription Filter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelListSubscriptionFilter:
    """Tests for is_subscribed query parameter."""

    async def test_is_subscribed_true(self, async_client: AsyncClient) -> None:
        """Test filtering to subscribed channels returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?is_subscribed=true"
            )
            assert response.status_code == 200

    async def test_is_subscribed_false(self, async_client: AsyncClient) -> None:
        """Test filtering to not-subscribed channels returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?is_subscribed=false"
            )
            assert response.status_code == 200

    async def test_is_subscribed_omitted_returns_all(self, async_client: AsyncClient) -> None:
        """Test that omitting is_subscribed returns all channels."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Response Schema Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelListItemResponseSchema:
    """Tests that ChannelListItem response includes is_subscribed field."""

    async def test_response_includes_is_subscribed_field(
        self, async_client: AsyncClient
    ) -> None:
        """Test that channel list items include the is_subscribed field."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()

            # All channels should have is_subscribed
            assert len(data["data"]) > 0
            for channel in data["data"]:
                assert "is_subscribed" in channel
                assert isinstance(channel["is_subscribed"], bool)

    async def test_subscribed_channel_has_correct_value(
        self, async_client: AsyncClient
    ) -> None:
        """Test that subscribed channel returns is_subscribed=True."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()

            # Find Alpha Channel (subscribed)
            alpha = next(
                (ch for ch in data["data"] if ch["channel_id"] == "UCaaaaaaaaaaaaaaaaaaaaa"),
                None,
            )
            assert alpha is not None
            assert alpha["is_subscribed"] is True

    async def test_not_subscribed_channel_has_correct_value(
        self, async_client: AsyncClient
    ) -> None:
        """Test that not-subscribed channel returns is_subscribed=False."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()

            # Find Charlie Channel (not subscribed)
            charlie = next(
                (ch for ch in data["data"] if ch["channel_id"] == "UCcccccccccccccccccccccc"),
                None,
            )
            assert charlie is not None
            assert charlie["is_subscribed"] is False

    async def test_response_pagination_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test that response includes proper pagination metadata."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()

            assert "pagination" in data
            pagination = data["pagination"]
            assert "total" in pagination
            assert "limit" in pagination
            assert "offset" in pagination
            assert "has_more" in pagination

    async def test_empty_response_has_is_subscribed_in_schema(
        self, empty_client: AsyncClient
    ) -> None:
        """Test that empty response still has valid structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await empty_client.get("/api/v1/channels")
            assert response.status_code == 200
            data = response.json()

            assert data["data"] == []
            assert data["pagination"]["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Combined Sort + Filter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelListCombinedSortAndFilter:
    """Tests combining sort and subscription filter parameters."""

    async def test_sort_by_name_with_subscribed_filter(
        self, async_client: AsyncClient
    ) -> None:
        """Test sorting by name while filtering to subscribed channels."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=name&sort_order=asc&is_subscribed=true"
            )
            assert response.status_code == 200

    async def test_sort_by_video_count_with_not_subscribed_filter(
        self, async_client: AsyncClient
    ) -> None:
        """Test sorting by video_count while filtering to not-subscribed channels."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=video_count&sort_order=asc&is_subscribed=false"
            )
            assert response.status_code == 200

    async def test_all_params_combined(self, async_client: AsyncClient) -> None:
        """Test all sort/filter params together."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get(
                "/api/v1/channels?sort_by=name&sort_order=desc"
                "&is_subscribed=true&has_videos=true&limit=10&offset=0"
            )
            assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Channel Videos Endpoint — Sort & Liked Filter Tests (Feature 027, US-5)
# ═══════════════════════════════════════════════════════════════════════════


def _make_video_row(
    video_id: str,
    title: str,
    channel_id: str = "UCaaaaaaaaaaaaaaaaaaaaaa",
    upload_date: datetime | None = None,
    duration: int = 300,
    view_count: int = 1000,
    category_id: str | None = None,
    availability_status: str = "available",
) -> MagicMock:
    """Create a mock VideoDB row object for channel videos tests."""
    row = MagicMock()
    row.video_id = video_id
    row.title = title
    row.channel_id = channel_id
    row.upload_date = upload_date or datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    row.duration = duration
    row.view_count = view_count
    row.category_id = category_id
    row.availability_status = availability_status
    row.transcripts = []
    row.tags = []
    row.video_topics = []

    # Mock channel relationship
    channel_mock = MagicMock()
    channel_mock.title = "Test Channel"
    row.channel = channel_mock

    # Mock category relationship
    row.category = None

    return row


def _create_channel_videos_mock_session(
    videos: list[MagicMock] | None = None,
    channel_exists: bool = True,
) -> AsyncMock:
    """Create a mock session for channel videos endpoint.

    Handles three db.execute() calls:
    1. Channel existence check -> scalar_one_or_none()
    2. Count query -> scalar()
    3. Data query -> scalars().all()
    """
    if videos is None:
        videos = []

    mock_session = AsyncMock(spec=AsyncSession)

    # 1. Channel existence check
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = (
        CHANNEL_VIDEO_ID if channel_exists else None
    )

    # 2. Count query
    count_result = MagicMock()
    count_result.scalar.return_value = len(videos)

    # 3. Data query
    data_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = videos
    data_result.scalars.return_value = scalars_mock

    mock_session.execute.side_effect = [channel_result, count_result, data_result]

    return mock_session


CHANNEL_VIDEO_ID = "UCaaaaaaaaaaaaaaaaaaaaaa"  # Exactly 24 characters

VIDEO_A = _make_video_row(video_id="dQw4w9WgXcQ", title="Alpha Video", channel_id=CHANNEL_VIDEO_ID)
VIDEO_B = _make_video_row(video_id="jNQXAC9IVRw", title="Beta Video", channel_id=CHANNEL_VIDEO_ID)
ALL_VIDEOS = [VIDEO_A, VIDEO_B]

CHANNEL_ID = CHANNEL_VIDEO_ID


@pytest.fixture
async def channel_videos_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for channel videos endpoint tests."""
    mock_session = _create_channel_videos_mock_session(ALL_VIDEOS)

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    app.dependency_overrides[get_db] = mock_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def channel_videos_empty_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with no videos for channel videos endpoint."""
    mock_session = _create_channel_videos_mock_session([])

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    app.dependency_overrides[get_db] = mock_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


class TestChannelVideosSortFields:
    """Tests for sort_by and sort_order query params on GET /channels/{id}/videos."""

    async def test_default_sort_returns_200(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test that GET /channels/{id}/videos with no sort params returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos"
            )
            assert response.status_code == 200

    async def test_default_sort_is_upload_date_desc(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test that default sort returns data and pagination."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos"
            )
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data

    async def test_sort_by_upload_date_asc(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test sorting by upload_date ascending returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos?sort_by=upload_date&sort_order=asc"
            )
            assert response.status_code == 200

    async def test_sort_by_upload_date_desc(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test sorting by upload_date descending returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos?sort_by=upload_date&sort_order=desc"
            )
            assert response.status_code == 200

    async def test_sort_by_title_asc(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test sorting by title ascending returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos?sort_by=title&sort_order=asc"
            )
            assert response.status_code == 200

    async def test_sort_by_title_desc(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test sorting by title descending returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos?sort_by=title&sort_order=desc"
            )
            assert response.status_code == 200

    async def test_invalid_sort_by_returns_422(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test that invalid sort_by value returns 422 validation error."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos?sort_by=invalid_field"
            )
            assert response.status_code == 422

    async def test_invalid_sort_order_returns_422(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test that invalid sort_order value returns 422 validation error."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos?sort_order=invalid"
            )
            assert response.status_code == 422


class TestChannelVideosLikedFilter:
    """Tests for liked_only query param on GET /channels/{id}/videos."""

    async def test_liked_only_false_returns_200(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test that liked_only=false returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos?liked_only=false"
            )
            assert response.status_code == 200

    async def test_liked_only_true_returns_200(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test that liked_only=true returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos?liked_only=true"
            )
            assert response.status_code == 200

    async def test_liked_only_omitted_returns_all(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test that omitting liked_only returns all videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos"
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 2

    async def test_liked_only_empty_results(
        self, channel_videos_empty_client: AsyncClient
    ) -> None:
        """Test liked_only with no results returns empty list."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_empty_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos?liked_only=true"
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 0
            assert data["pagination"]["total"] == 0


class TestChannelVideosCombinedSortAndFilter:
    """Tests combining sort and liked filter on channel videos."""

    async def test_sort_with_liked_filter(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test sorting by title while filtering to liked videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos"
                "?sort_by=title&sort_order=asc&liked_only=true"
            )
            assert response.status_code == 200

    async def test_all_params_combined(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test all sort/filter params together on channel videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos"
                "?sort_by=upload_date&sort_order=desc&liked_only=false&limit=10&offset=0"
            )
            assert response.status_code == 200


class TestChannelVideosResponseSchema:
    """Tests for channel videos response structure with sort/filter params."""

    async def test_response_includes_pagination(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test that response includes pagination metadata."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos"
            )
            assert response.status_code == 200
            data = response.json()

            assert "pagination" in data
            pagination = data["pagination"]
            assert "total" in pagination
            assert "limit" in pagination
            assert "offset" in pagination
            assert "has_more" in pagination

    async def test_response_video_items_structure(
        self, channel_videos_client: AsyncClient
    ) -> None:
        """Test that video items have expected fields."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await channel_videos_client.get(
                f"/api/v1/channels/{CHANNEL_ID}/videos"
            )
            assert response.status_code == 200
            data = response.json()

            assert len(data["data"]) > 0
            video = data["data"][0]
            assert "video_id" in video
            assert "title" in video
            assert "channel_id" in video
