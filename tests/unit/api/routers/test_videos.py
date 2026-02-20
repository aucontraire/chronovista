"""
Unit tests for video list endpoint sort and filter params (Feature 027, T028).

Tests the VideoSortField enum, sort_by/sort_order query params, liked_only
filter, and their combination with existing filters (has_transcript,
include_unavailable, tag, category, topic_id).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app
from chronovista.api.routers.videos import VideoSortField

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _make_video_row(
    video_id: str,
    title: str = "Test Video",
    upload_date: datetime | None = None,
    channel_id: str = "UC_test_channel_12345_",
) -> MagicMock:
    """Create a mock Video database row."""
    video = MagicMock()
    video.video_id = video_id
    video.title = title
    video.channel_id = channel_id
    video.upload_date = upload_date or datetime(2024, 1, 15, tzinfo=timezone.utc)
    video.duration = 300
    video.view_count = 1000
    video.category_id = None
    video.availability_status = "available"
    video.alternative_url = None
    video.recovered_at = None
    video.recovery_source = None

    # Mock relationships
    video.transcripts = []
    video.channel = MagicMock(title="Test Channel")
    video.tags = []
    video.category = None
    video.video_topics = []

    return video


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for FastAPI testing."""
    mock_session = AsyncMock(spec=AsyncSession)

    # Default: return empty result set
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar.return_value = 0

    # For count queries
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 0

    mock_session.execute = AsyncMock(return_value=mock_count_result)

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def mock_require_auth() -> None:
        return None

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[require_auth] = mock_require_auth

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# VideoSortField Enum Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestVideoSortFieldEnum:
    """Tests for VideoSortField enum definition."""

    def test_upload_date_value(self) -> None:
        """Verify upload_date enum value matches API parameter."""
        assert VideoSortField.UPLOAD_DATE.value == "upload_date"

    def test_title_value(self) -> None:
        """Verify title enum value matches API parameter."""
        assert VideoSortField.TITLE.value == "title"

    def test_enum_has_exactly_two_members(self) -> None:
        """Verify enum has only upload_date and title (no date_added)."""
        members = list(VideoSortField)
        assert len(members) == 2
        assert VideoSortField.UPLOAD_DATE in members
        assert VideoSortField.TITLE in members

    def test_is_string_enum(self) -> None:
        """Verify VideoSortField is a str enum for FastAPI query param parsing."""
        assert isinstance(VideoSortField.UPLOAD_DATE, str)
        assert isinstance(VideoSortField.TITLE, str)


# ═══════════════════════════════════════════════════════════════════════════
# Default Sort Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestDefaultSort:
    """Tests for default sort behavior (upload_date desc)."""

    async def test_default_sort_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        """Default request (no sort params) should return 200."""
        response = await async_client.get("/api/v1/videos")
        assert response.status_code == 200

    async def test_default_sort_response_has_data(
        self, async_client: AsyncClient
    ) -> None:
        """Default request should have data and pagination keys."""
        response = await async_client.get("/api/v1/videos")
        body = response.json()
        assert "data" in body
        assert "pagination" in body


# ═══════════════════════════════════════════════════════════════════════════
# Sort Field Parameter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSortFieldParams:
    """Tests for sort_by and sort_order query parameters."""

    async def test_sort_by_upload_date_asc(
        self, async_client: AsyncClient
    ) -> None:
        """sort_by=upload_date&sort_order=asc should return 200."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=upload_date&sort_order=asc"
        )
        assert response.status_code == 200

    async def test_sort_by_upload_date_desc(
        self, async_client: AsyncClient
    ) -> None:
        """sort_by=upload_date&sort_order=desc should return 200."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=upload_date&sort_order=desc"
        )
        assert response.status_code == 200

    async def test_sort_by_title_asc(
        self, async_client: AsyncClient
    ) -> None:
        """sort_by=title&sort_order=asc should return 200."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=asc"
        )
        assert response.status_code == 200

    async def test_sort_by_title_desc(
        self, async_client: AsyncClient
    ) -> None:
        """sort_by=title&sort_order=desc should return 200."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=desc"
        )
        assert response.status_code == 200

    async def test_invalid_sort_by_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """Invalid sort_by value should return 422 validation error."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=invalid_field"
        )
        assert response.status_code == 422

    async def test_invalid_sort_order_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """Invalid sort_order value should return 422 validation error."""
        response = await async_client.get(
            "/api/v1/videos?sort_order=invalid"
        )
        assert response.status_code == 422

    async def test_sort_by_date_added_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """sort_by=date_added is NOT a valid field (maps to upload_date on frontend only)."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=date_added"
        )
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Liked-Only Filter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestLikedOnlyFilter:
    """Tests for liked_only query parameter."""

    async def test_liked_only_true_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        """liked_only=true should return 200."""
        response = await async_client.get("/api/v1/videos?liked_only=true")
        assert response.status_code == 200

    async def test_liked_only_false_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        """liked_only=false should return 200 (effectively no filter)."""
        response = await async_client.get("/api/v1/videos?liked_only=false")
        assert response.status_code == 200

    async def test_liked_only_absent_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        """No liked_only param should return 200 (default false)."""
        response = await async_client.get("/api/v1/videos")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Combined Filter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCombinedFilters:
    """Tests for combining sort/liked with existing filter parameters."""

    async def test_liked_with_has_transcript(
        self, async_client: AsyncClient
    ) -> None:
        """liked_only + has_transcript should both be accepted."""
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&has_transcript=true"
        )
        assert response.status_code == 200

    async def test_liked_with_include_unavailable(
        self, async_client: AsyncClient
    ) -> None:
        """liked_only + include_unavailable should both be accepted."""
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&include_unavailable=true"
        )
        assert response.status_code == 200

    async def test_liked_with_tag_filter(
        self, async_client: AsyncClient
    ) -> None:
        """liked_only + tag filter should both be accepted."""
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&tag=music"
        )
        assert response.status_code == 200

    async def test_sort_with_existing_filters(
        self, async_client: AsyncClient
    ) -> None:
        """sort_by + sort_order with existing classification filters."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=asc&tag=music&category=10"
        )
        assert response.status_code == 200

    async def test_all_filters_combined(
        self, async_client: AsyncClient
    ) -> None:
        """All filter types combined should return 200."""
        response = await async_client.get(
            "/api/v1/videos"
            "?sort_by=title&sort_order=asc"
            "&liked_only=true"
            "&has_transcript=true"
            "&include_unavailable=true"
            "&tag=music"
        )
        assert response.status_code == 200

    async def test_sort_with_pagination(
        self, async_client: AsyncClient
    ) -> None:
        """Sort params should work with pagination params."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=desc&limit=10&offset=5"
        )
        assert response.status_code == 200

    async def test_liked_with_channel_filter(
        self, async_client: AsyncClient
    ) -> None:
        """liked_only + channel_id should both be accepted."""
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&channel_id=UCtest_channel_123456789"
        )
        assert response.status_code == 200
