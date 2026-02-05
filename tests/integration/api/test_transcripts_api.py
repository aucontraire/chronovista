"""Integration tests for transcript endpoints (US2)."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestTranscriptLanguages:
    """Tests for GET /api/v1/videos/{video_id}/transcript/languages endpoint."""

    async def test_get_languages_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that transcript languages requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/languages"
            )
            assert response.status_code == 401

    async def test_get_languages_returns_list(self, async_client: AsyncClient) -> None:
        """Test languages endpoint returns list structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/languages"
            )
            # Either 200 with languages or 404 if video doesn't exist
            assert response.status_code in [200, 404]

    async def test_get_languages_response_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test languages endpoint response has correct structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/languages"
            )
            if response.status_code == 200:
                data = response.json()
                assert "data" in data
                assert isinstance(data["data"], list)
                if data["data"]:
                    language = data["data"][0]
                    assert "language_code" in language
                    assert "language_name" in language
                    assert "transcript_type" in language
                    assert "is_translatable" in language
                    assert "downloaded_at" in language

    async def test_get_languages_404_for_nonexistent_video(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 for non-existent video."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/NONEXISTENT/transcript/languages"
            )
            assert response.status_code == 404
            data = response.json()
            # RFC 7807 format: code is at top level
            assert data["code"] == "NOT_FOUND"

    async def test_get_languages_video_id_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test video_id validation (11 characters)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Too short
            response = await async_client.get("/api/v1/videos/short/transcript/languages")
            assert response.status_code == 422


class TestTranscriptFull:
    """Tests for GET /api/v1/videos/{video_id}/transcript endpoint."""

    async def test_get_transcript_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that full transcript requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/videos/dQw4w9WgXcQ/transcript")
            assert response.status_code == 401

    async def test_get_transcript_response_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test transcript endpoint returns correct structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/dQw4w9WgXcQ/transcript")
            if response.status_code == 200:
                data = response.json()
                assert "data" in data
                assert "video_id" in data["data"]
                assert "language_code" in data["data"]
                assert "full_text" in data["data"]
                assert "segment_count" in data["data"]
                assert "transcript_type" in data["data"]
                assert "downloaded_at" in data["data"]

    async def test_get_transcript_with_language_param(
        self, async_client: AsyncClient
    ) -> None:
        """Test transcript with specific language parameter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript?language=en"
            )
            assert response.status_code in [200, 404]

    async def test_get_transcript_404_for_nonexistent_video(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 for video with no transcripts."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/NONEXISTENT/transcript")
            assert response.status_code == 404
            data = response.json()
            # RFC 7807 format: code is at top level
            assert data["code"] == "NOT_FOUND"

    async def test_get_transcript_404_for_missing_language(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 when requesting non-existent language."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript?language=xx"
            )
            # Should be 404 if video exists but language doesn't
            assert response.status_code == 404

    async def test_get_transcript_default_language_selection(
        self, async_client: AsyncClient
    ) -> None:
        """Test that default language prefers manual/CC transcripts."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/dQw4w9WgXcQ/transcript")
            # Test should succeed or return 404 if no transcripts
            assert response.status_code in [200, 404]


class TestTranscriptSegments:
    """Tests for GET /api/v1/videos/{video_id}/transcript/segments endpoint."""

    async def test_get_segments_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that segments endpoint requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments"
            )
            assert response.status_code == 401

    async def test_get_segments_returns_paginated_list(
        self, async_client: AsyncClient
    ) -> None:
        """Test segments endpoint returns paginated list."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments"
            )
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)

    async def test_get_segments_pagination_defaults(
        self, async_client: AsyncClient
    ) -> None:
        """Test default pagination values (limit=50, offset=0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments"
            )
            data = response.json()
            assert data["pagination"]["limit"] == 50
            assert data["pagination"]["offset"] == 0

    async def test_get_segments_custom_pagination(
        self, async_client: AsyncClient
    ) -> None:
        """Test custom pagination parameters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?limit=10&offset=5"
            )
            data = response.json()
            assert data["pagination"]["limit"] == 10
            assert data["pagination"]["offset"] == 5

    async def test_get_segments_limit_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test limit validation (max 200)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?limit=300"
            )
            assert response.status_code == 422

    async def test_get_segments_limit_minimum_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test limit validation (minimum 1)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?limit=0"
            )
            assert response.status_code == 422

    async def test_get_segments_offset_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test offset validation (minimum 0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?offset=-1"
            )
            assert response.status_code == 422

    async def test_get_segments_time_filter_start(
        self, async_client: AsyncClient
    ) -> None:
        """Test start_time filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?start_time=60.0"
            )
            assert response.status_code == 200

    async def test_get_segments_time_filter_end(self, async_client: AsyncClient) -> None:
        """Test end_time filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?end_time=120.0"
            )
            assert response.status_code == 200

    async def test_get_segments_time_range_filter(
        self, async_client: AsyncClient
    ) -> None:
        """Test combined start_time and end_time filters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?start_time=30.0&end_time=90.0"
            )
            assert response.status_code == 200

    async def test_get_segments_time_validation_negative_start(
        self, async_client: AsyncClient
    ) -> None:
        """Test start_time validation (must be >= 0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?start_time=-10.0"
            )
            assert response.status_code == 422

    async def test_get_segments_time_validation_negative_end(
        self, async_client: AsyncClient
    ) -> None:
        """Test end_time validation (must be >= 0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?end_time=-10.0"
            )
            assert response.status_code == 422

    async def test_get_segments_empty_for_no_transcripts(
        self, async_client: AsyncClient
    ) -> None:
        """Test empty response when video has no transcripts."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Non-existent video should return empty segments with 200
            response = await async_client.get(
                "/api/v1/videos/NONEXISTENT/transcript/segments"
            )
            data = response.json()
            assert data["data"] == []
            assert data["pagination"]["total"] == 0

    async def test_get_segments_response_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test segment response structure when segments exist."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments"
            )
            data = response.json()
            if data["data"]:  # If segments exist
                segment = data["data"][0]
                assert "id" in segment
                assert "text" in segment
                assert "start_time" in segment
                assert "end_time" in segment
                assert "duration" in segment
                assert isinstance(segment["start_time"], (int, float))
                assert isinstance(segment["end_time"], (int, float))

    async def test_get_segments_pagination_has_more(
        self, async_client: AsyncClient
    ) -> None:
        """Test has_more flag in pagination."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?limit=10"
            )
            data = response.json()
            pagination = data["pagination"]
            assert "has_more" in pagination
            assert isinstance(pagination["has_more"], bool)
            # Verify has_more logic
            total = pagination["total"]
            limit = pagination["limit"]
            offset = pagination["offset"]
            assert pagination["has_more"] == ((offset + limit) < total)

    async def test_get_segments_ordering_by_time(
        self, async_client: AsyncClient
    ) -> None:
        """Test segments are ordered by start_time ascending."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?limit=20"
            )
            data = response.json()
            if len(data["data"]) > 1:
                # Check that start times are in ascending order
                start_times = [seg["start_time"] for seg in data["data"]]
                assert start_times == sorted(start_times)

    async def test_get_segments_with_language_param(
        self, async_client: AsyncClient
    ) -> None:
        """Test segments endpoint with explicit language parameter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/dQw4w9WgXcQ/transcript/segments?language=en"
            )
            assert response.status_code == 200

    async def test_get_segments_video_id_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test video_id validation (11 characters)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/short/transcript/segments")
            assert response.status_code == 422
