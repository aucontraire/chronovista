"""Integration tests for video list endpoint (US1)."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestListVideos:
    """Tests for GET /api/v1/videos endpoint."""

    async def test_list_videos_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that video list requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/videos")
            assert response.status_code == 401

    async def test_list_videos_returns_paginated_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test video list returns paginated response structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)

    async def test_list_videos_pagination_metadata(
        self, async_client: AsyncClient
    ) -> None:
        """Test pagination metadata contains required fields."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?limit=10&offset=0")
            assert response.status_code == 200
            data = response.json()

            pagination = data["pagination"]
            assert "total" in pagination
            assert "limit" in pagination
            assert "offset" in pagination
            assert "has_more" in pagination
            assert pagination["limit"] == 10
            assert pagination["offset"] == 0

    async def test_list_videos_default_pagination(
        self, async_client: AsyncClient
    ) -> None:
        """Test default pagination values (limit=20, offset=0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos")
            assert response.status_code == 200
            data = response.json()

            assert data["pagination"]["limit"] == 20
            assert data["pagination"]["offset"] == 0

    async def test_list_videos_limit_validation(self, async_client: AsyncClient) -> None:
        """Test limit validation (max 100)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Over max
            response = await async_client.get("/api/v1/videos?limit=200")
            assert response.status_code == 422  # Validation error

    async def test_list_videos_offset_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test offset validation (must be >= 0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?offset=-1")
            assert response.status_code == 422  # Validation error

    async def test_list_videos_channel_filter_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test channel_id filter requires 24 characters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Too short
            response = await async_client.get("/api/v1/videos?channel_id=short")
            assert response.status_code == 422

    async def test_list_videos_has_more_false_when_no_more_results(
        self, async_client: AsyncClient
    ) -> None:
        """Test has_more is false when offset + limit >= total."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?limit=100&offset=0")
            assert response.status_code == 200
            data = response.json()

            total = data["pagination"]["total"]
            limit = data["pagination"]["limit"]
            offset = data["pagination"]["offset"]
            has_more = data["pagination"]["has_more"]

            # Verify has_more logic
            assert has_more == ((offset + limit) < total)

    async def test_list_videos_item_structure(self, async_client: AsyncClient) -> None:
        """Test video list items have correct structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?limit=1")
            assert response.status_code == 200
            data = response.json()

            if data["data"]:  # If there are videos
                video = data["data"][0]
                assert "video_id" in video
                assert "title" in video
                assert "upload_date" in video
                assert "duration" in video
                assert "transcript_summary" in video

                # Check transcript summary structure
                summary = video["transcript_summary"]
                assert "count" in summary
                assert "languages" in summary
                assert "has_manual" in summary


class TestVideoFilters:
    """Tests for video list filters."""

    async def test_channel_filter_format(self, async_client: AsyncClient) -> None:
        """Test channel_id filter accepts valid 24-char IDs."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Valid 24-char channel ID
            response = await async_client.get(
                "/api/v1/videos?channel_id=UCddiUEpeqJcYeBxX1IVBKvQ"
            )
            # Should not be a validation error
            assert response.status_code == 200

    async def test_has_transcript_filter_true(self, async_client: AsyncClient) -> None:
        """Test has_transcript=true filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?has_transcript=true")
            assert response.status_code == 200

    async def test_has_transcript_filter_false(self, async_client: AsyncClient) -> None:
        """Test has_transcript=false filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos?has_transcript=false")
            assert response.status_code == 200

    async def test_date_filter_uploaded_after(self, async_client: AsyncClient) -> None:
        """Test uploaded_after date filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Use URL-encoded ISO format with timezone
            date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
                "%Y-%m-%dT%H:%M:%S+00:00"
            )
            encoded_date = quote(date)
            response = await async_client.get(
                f"/api/v1/videos?uploaded_after={encoded_date}"
            )
            assert response.status_code == 200

    async def test_date_filter_uploaded_before(self, async_client: AsyncClient) -> None:
        """Test uploaded_before date filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Use URL-encoded ISO format with timezone
            date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            encoded_date = quote(date)
            response = await async_client.get(
                f"/api/v1/videos?uploaded_before={encoded_date}"
            )
            assert response.status_code == 200

    async def test_combined_filters(self, async_client: AsyncClient) -> None:
        """Test combining multiple filters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos?has_transcript=true&limit=10&offset=0"
            )
            assert response.status_code == 200
