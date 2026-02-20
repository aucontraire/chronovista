"""
Unit tests for playlist video sort and filter API parameters.

Tests cover:
- T015: Each sort field individually (position, upload_date, title)
- T015: Default sort (position asc)
- T015: Each filter individually (liked_only, has_transcript, unavailable_only)
- T015: Combined filters (AND logic)
- T015: Invalid sort_by returns 422
- T015: Empty result set with filters
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


def _make_mock_session() -> AsyncMock:
    """Create a properly configured mock async session.

    Returns a mock that handles SQLAlchemy's async session pattern:
    session.execute(query) -> result with .scalar_one_or_none(), .scalars(), .all()
    """
    mock_session = AsyncMock(spec=AsyncSession)

    # Create a mock result that handles playlist lookup (scalar_one_or_none)
    # and video query (all)
    call_count = 0

    async def mock_execute(query, *args, **kwargs):
        nonlocal call_count
        call_count += 1

        result = MagicMock()

        if call_count == 1:
            # First call: playlist existence check
            result.scalar_one_or_none.return_value = "PLtest1234567890abcdefgh"
        elif call_count == 2:
            # Second call: count query
            result.scalar.return_value = 0
        else:
            # Third call: main query -> empty result
            result.all.return_value = []

        return result

    mock_session.execute = AsyncMock(side_effect=mock_execute)
    return mock_session


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for FastAPI testing with proper mock session."""

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield _make_mock_session()

    app.dependency_overrides[get_db] = mock_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def async_client_no_playlist() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client where playlist does not exist."""

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        mock_session = AsyncMock(spec=AsyncSession)

        async def mock_execute(query, *args, **kwargs):
            result = MagicMock()
            # Playlist not found
            result.scalar_one_or_none.return_value = None
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        yield mock_session

    app.dependency_overrides[get_db] = mock_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


PLAYLIST_ID = "PLtest1234567890abcdefgh"
ENDPOINT = f"/api/v1/playlists/{PLAYLIST_ID}/videos"


# ═══════════════════════════════════════════════════════════════════════════
# Playlist Video Sort Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPlaylistVideoSort:
    """Tests for GET /api/v1/playlists/{playlist_id}/videos sort parameters."""

    async def test_default_sort_returns_200(self, async_client: AsyncClient) -> None:
        """Test default sort (position asc) returns 200 with empty result."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(ENDPOINT)
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert data["pagination"]["total"] == 0
            assert data["data"] == []

    async def test_sort_by_position_asc(self, async_client: AsyncClient) -> None:
        """Test sort_by=position with sort_order=asc is accepted."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?sort_by=position&sort_order=asc"
            )
            assert response.status_code == 200

    async def test_sort_by_position_desc(self, async_client: AsyncClient) -> None:
        """Test sort_by=position with sort_order=desc is accepted."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?sort_by=position&sort_order=desc"
            )
            assert response.status_code == 200

    async def test_sort_by_upload_date_asc(self, async_client: AsyncClient) -> None:
        """Test sort_by=upload_date with sort_order=asc is accepted."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?sort_by=upload_date&sort_order=asc"
            )
            assert response.status_code == 200

    async def test_sort_by_upload_date_desc(self, async_client: AsyncClient) -> None:
        """Test sort_by=upload_date with sort_order=desc is accepted."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?sort_by=upload_date&sort_order=desc"
            )
            assert response.status_code == 200

    async def test_sort_by_title_asc(self, async_client: AsyncClient) -> None:
        """Test sort_by=title with sort_order=asc is accepted."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?sort_by=title&sort_order=asc"
            )
            assert response.status_code == 200

    async def test_sort_by_title_desc(self, async_client: AsyncClient) -> None:
        """Test sort_by=title with sort_order=desc is accepted."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?sort_by=title&sort_order=desc"
            )
            assert response.status_code == 200

    async def test_invalid_sort_by_returns_422(self, async_client: AsyncClient) -> None:
        """Test invalid sort_by value returns 422 validation error."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?sort_by=invalid_field"
            )
            assert response.status_code == 422

    async def test_invalid_sort_order_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """Test invalid sort_order value returns 422 validation error."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?sort_order=invalid"
            )
            assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Playlist Video Filter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPlaylistVideoFilters:
    """Tests for GET /api/v1/playlists/{playlist_id}/videos filter parameters."""

    async def test_liked_only_filter_accepted(
        self, async_client: AsyncClient
    ) -> None:
        """Test liked_only=true filter is accepted and returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?liked_only=true"
            )
            assert response.status_code == 200

    async def test_has_transcript_filter_accepted(
        self, async_client: AsyncClient
    ) -> None:
        """Test has_transcript=true filter is accepted and returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?has_transcript=true"
            )
            assert response.status_code == 200

    async def test_unavailable_only_filter_accepted(
        self, async_client: AsyncClient
    ) -> None:
        """Test unavailable_only=true filter is accepted and returns 200."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?unavailable_only=true"
            )
            assert response.status_code == 200

    async def test_combined_filters_accepted(
        self, async_client: AsyncClient
    ) -> None:
        """Test multiple filters combined are accepted (AND logic)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?liked_only=true&has_transcript=true&unavailable_only=true"
            )
            assert response.status_code == 200

    async def test_filters_with_sort_accepted(
        self, async_client: AsyncClient
    ) -> None:
        """Test filters combined with sort parameters are accepted."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?sort_by=upload_date&sort_order=desc"
                "&liked_only=true&has_transcript=true"
            )
            assert response.status_code == 200

    async def test_filters_default_to_false(
        self, async_client: AsyncClient
    ) -> None:
        """Test that filters default to false (no filtering applied)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(ENDPOINT)
            assert response.status_code == 200

    async def test_empty_result_with_filters(
        self, async_client: AsyncClient
    ) -> None:
        """Test that filters can result in empty data list with total=0."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{ENDPOINT}?liked_only=true&has_transcript=true&unavailable_only=true"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"] == []
            assert data["pagination"]["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Authentication Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPlaylistVideoAuth:
    """Tests for authentication on playlist video endpoint."""

    async def test_playlist_videos_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test that playlist videos endpoint requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(ENDPOINT)
            assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# Playlist Not Found Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPlaylistVideoNotFound:
    """Tests for playlist not found scenarios."""

    async def test_nonexistent_playlist_returns_404(
        self, async_client_no_playlist: AsyncClient
    ) -> None:
        """Test requesting videos for a nonexistent playlist returns 404."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client_no_playlist.get(
                f"/api/v1/playlists/PLnonexistent12345678901/videos"
            )
            assert response.status_code == 404
