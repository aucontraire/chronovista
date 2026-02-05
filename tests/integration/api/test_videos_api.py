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


class TestVideoDetail:
    """Tests for GET /api/v1/videos/{video_id} endpoint (US6)."""

    async def test_get_video_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that video detail requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/videos/dQw4w9WgXcQ")
            assert response.status_code == 401

    async def test_get_video_returns_detail(self, async_client: AsyncClient) -> None:
        """Test video detail returns correct structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Use a likely non-existent video ID to test 404 path at minimum
            response = await async_client.get("/api/v1/videos/dQw4w9WgXcQ")
            # Either 200 with data or 404 if video doesn't exist
            assert response.status_code in [200, 404]

    async def test_get_video_404_for_nonexistent(self, async_client: AsyncClient) -> None:
        """Test 404 response for non-existent video."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Non-existent video ID
            response = await async_client.get("/api/v1/videos/NONEXISTENT")
            assert response.status_code == 404
            data = response.json()
            # RFC 7807 format: code is at top level
            assert data["code"] == "NOT_FOUND"
            assert "Video" in data["detail"]
            assert "NONEXISTENT" in data["detail"]

    async def test_get_video_actionable_error_message(
        self, async_client: AsyncClient
    ) -> None:
        """Test that 404 error has actionable message."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/NONEXISTENT")
            data = response.json()
            # RFC 7807 format: Check actionable guidance in detail field
            assert "sync" in data["detail"].lower()

    async def test_get_video_id_validation_too_short(
        self, async_client: AsyncClient
    ) -> None:
        """Test video_id must be exactly 11 characters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/short")
            assert response.status_code == 422  # Validation error

    async def test_get_video_id_validation_too_long(
        self, async_client: AsyncClient
    ) -> None:
        """Test video_id must be exactly 11 characters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/waytoolongvideoid")
            assert response.status_code == 422  # Validation error

    async def test_get_video_response_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test video detail response has correct structure when found."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/dQw4w9WgXcQ")
            if response.status_code == 200:
                data = response.json()
                assert "data" in data
                video = data["data"]
                # Check required fields
                assert "video_id" in video
                assert "title" in video
                assert "upload_date" in video
                assert "duration" in video
                assert "made_for_kids" in video
                assert "transcript_summary" in video
                assert "tags" in video

    async def test_get_video_transcript_summary(
        self, async_client: AsyncClient
    ) -> None:
        """Test video detail includes transcript summary with count and languages."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/dQw4w9WgXcQ")
            if response.status_code == 200:
                data = response.json()
                summary = data["data"]["transcript_summary"]
                assert "count" in summary
                assert "languages" in summary
                assert "has_manual" in summary
                assert isinstance(summary["count"], int)
                assert isinstance(summary["languages"], list)
                assert isinstance(summary["has_manual"], bool)
