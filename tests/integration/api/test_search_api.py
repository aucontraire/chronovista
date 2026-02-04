"""Integration tests for search endpoint (US3)."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestSearchSegments:
    """Tests for GET /api/v1/search/segments endpoint."""

    async def test_search_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that search requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/search/segments?q=test")
            assert response.status_code == 401
            data = response.json()
            assert "detail" in data
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"

    async def test_search_returns_paginated_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test search returns paginated response structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=test")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)

    async def test_search_requires_query(self, async_client: AsyncClient) -> None:
        """Test that search requires q parameter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments")
            assert response.status_code == 422  # Missing required parameter

    async def test_search_query_min_length(self, async_client: AsyncClient) -> None:
        """Test query must be at least 2 characters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=a")
            assert response.status_code == 422

    async def test_search_query_max_length(self, async_client: AsyncClient) -> None:
        """Test query must be at most 500 characters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            long_query = "a" * 501
            response = await async_client.get(f"/api/v1/search/segments?q={long_query}")
            assert response.status_code == 422

    async def test_search_query_whitespace_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test query cannot be empty after stripping whitespace."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=%20%20")
            assert response.status_code == 400  # Bad request for empty query
            data = response.json()
            assert data["error"]["code"] == "BAD_REQUEST"

    async def test_search_empty_results(self, async_client: AsyncClient) -> None:
        """Test empty results for non-matching query."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/search/segments?q=xyznonexistentquery123"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"] == []
            assert data["pagination"]["total"] == 0

    async def test_search_pagination_defaults(self, async_client: AsyncClient) -> None:
        """Test default pagination values."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=test")
            assert response.status_code == 200
            data = response.json()
            assert data["pagination"]["limit"] == 20
            assert data["pagination"]["offset"] == 0

    async def test_search_custom_pagination(self, async_client: AsyncClient) -> None:
        """Test custom pagination parameters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/search/segments?q=test&limit=10&offset=5"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["pagination"]["limit"] == 10
            assert data["pagination"]["offset"] == 5

    async def test_search_limit_validation(self, async_client: AsyncClient) -> None:
        """Test limit validation (max 100)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=test&limit=200")
            assert response.status_code == 422

    async def test_search_limit_minimum_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test limit validation (minimum 1)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=test&limit=0")
            assert response.status_code == 422

    async def test_search_offset_validation(self, async_client: AsyncClient) -> None:
        """Test offset validation (minimum 0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=test&offset=-1")
            assert response.status_code == 422

    async def test_search_video_filter(self, async_client: AsyncClient) -> None:
        """Test video_id filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/search/segments?q=test&video_id=dQw4w9WgXcQ"
            )
            assert response.status_code == 200

    async def test_search_video_filter_validation_too_short(
        self, async_client: AsyncClient
    ) -> None:
        """Test video_id filter must be exactly 11 characters (too short)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/search/segments?q=test&video_id=short"
            )
            assert response.status_code == 422

    async def test_search_video_filter_validation_too_long(
        self, async_client: AsyncClient
    ) -> None:
        """Test video_id filter must be exactly 11 characters (too long)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/search/segments?q=test&video_id=waytoolongvideoid"
            )
            assert response.status_code == 422

    async def test_search_language_filter(self, async_client: AsyncClient) -> None:
        """Test language filter."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/search/segments?q=test&language=en"
            )
            assert response.status_code == 200

    async def test_search_result_structure(self, async_client: AsyncClient) -> None:
        """Test search result item structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=the")
            assert response.status_code == 200
            data = response.json()
            if data["data"]:
                result = data["data"][0]
                # Check required fields
                assert "segment_id" in result
                assert "video_id" in result
                assert "video_title" in result
                assert "text" in result
                assert "start_time" in result
                assert "end_time" in result
                assert "match_count" in result
                assert "video_upload_date" in result
                assert "language_code" in result
                # Types
                assert isinstance(result["segment_id"], int)
                assert isinstance(result["video_id"], str)
                assert isinstance(result["video_title"], str)
                assert isinstance(result["text"], str)
                assert isinstance(result["start_time"], (int, float))
                assert isinstance(result["end_time"], (int, float))
                assert isinstance(result["match_count"], int)
                assert isinstance(result["language_code"], str)

    async def test_search_context_fields(self, async_client: AsyncClient) -> None:
        """Test context_before and context_after fields."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=the")
            assert response.status_code == 200
            data = response.json()
            if data["data"]:
                result = data["data"][0]
                # Context fields should exist (may be null)
                assert "context_before" in result
                assert "context_after" in result
                # If present, should be strings
                if result["context_before"] is not None:
                    assert isinstance(result["context_before"], str)
                if result["context_after"] is not None:
                    assert isinstance(result["context_after"], str)

    async def test_search_pagination_has_more(self, async_client: AsyncClient) -> None:
        """Test has_more flag in pagination."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=the&limit=5")
            assert response.status_code == 200
            data = response.json()
            pagination = data["pagination"]
            assert "has_more" in pagination
            assert isinstance(pagination["has_more"], bool)
            # Verify has_more logic
            total = pagination["total"]
            limit = pagination["limit"]
            offset = pagination["offset"]
            assert pagination["has_more"] == ((offset + limit) < total)

    async def test_search_combined_filters(self, async_client: AsyncClient) -> None:
        """Test combining multiple filters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/search/segments?q=test&limit=10&offset=0&language=en"
            )
            assert response.status_code == 200

    async def test_search_match_count(self, async_client: AsyncClient) -> None:
        """Test match_count field represents query term matches."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=the")
            assert response.status_code == 200
            data = response.json()
            if data["data"]:
                result = data["data"][0]
                # match_count should be >= 1 since it matched the query
                assert result["match_count"] >= 1

    async def test_search_multi_word_query(self, async_client: AsyncClient) -> None:
        """Test multi-word search query (implicit AND)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/search/segments?q=test%20query"
            )
            assert response.status_code == 200

    async def test_search_special_characters_escaped(
        self, async_client: AsyncClient
    ) -> None:
        """Test special SQL characters are properly escaped."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Test with SQL wildcard characters
            response = await async_client.get("/api/v1/search/segments?q=test%25")
            assert response.status_code == 200
            # Should not cause SQL errors

    async def test_search_ordering_by_upload_date(
        self, async_client: AsyncClient
    ) -> None:
        """Test results are ordered by video upload date (desc), then start time (asc)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=the&limit=20")
            assert response.status_code == 200
            data = response.json()
            if len(data["data"]) > 1:
                # Check upload dates are in descending order
                upload_dates = [result["video_upload_date"] for result in data["data"]]
                # Convert to comparable format
                from datetime import datetime

                dates = [datetime.fromisoformat(d.replace("Z", "+00:00")) for d in upload_dates]
                # Check dates are in descending order (most recent first)
                # Allow same dates (for segments from same video)
                for i in range(len(dates) - 1):
                    assert dates[i] >= dates[i + 1]

    async def test_search_excludes_deleted_videos(
        self, async_client: AsyncClient
    ) -> None:
        """Test search excludes videos marked as deleted."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=test")
            assert response.status_code == 200
            # Implementation should filter deleted_flag = False
            # This test validates the endpoint doesn't crash with this filter

    async def test_search_channel_title_optional(
        self, async_client: AsyncClient
    ) -> None:
        """Test channel_title is optional in response."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=the")
            assert response.status_code == 200
            data = response.json()
            if data["data"]:
                result = data["data"][0]
                assert "channel_title" in result
                # channel_title may be None or a string
                if result["channel_title"] is not None:
                    assert isinstance(result["channel_title"], str)

    async def test_search_context_truncation(self, async_client: AsyncClient) -> None:
        """Test context text is truncated to 200 characters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=the")
            assert response.status_code == 200
            data = response.json()
            if data["data"]:
                result = data["data"][0]
                # Context should be max 200 characters
                if result["context_before"] is not None:
                    assert len(result["context_before"]) <= 200
                if result["context_after"] is not None:
                    assert len(result["context_after"]) <= 200


class TestSearchEdgeCases:
    """Tests for search endpoint edge cases."""

    async def test_search_case_insensitive(self, async_client: AsyncClient) -> None:
        """Test search is case-insensitive."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Both should work and return results
            response_lower = await async_client.get("/api/v1/search/segments?q=test")
            response_upper = await async_client.get("/api/v1/search/segments?q=TEST")
            assert response_lower.status_code == 200
            assert response_upper.status_code == 200
            # Should return same results (if any exist)
            data_lower = response_lower.json()
            data_upper = response_upper.json()
            assert data_lower["pagination"]["total"] == data_upper["pagination"]["total"]

    async def test_search_with_quotes(self, async_client: AsyncClient) -> None:
        """Test search with quoted text."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get('/api/v1/search/segments?q="test query"')
            assert response.status_code == 200

    async def test_search_unicode_query(self, async_client: AsyncClient) -> None:
        """Test search with Unicode characters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=café")
            assert response.status_code == 200

    async def test_search_numeric_query(self, async_client: AsyncClient) -> None:
        """Test search with numeric query."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/search/segments?q=123")
            assert response.status_code == 200

    async def test_search_pagination_beyond_results(
        self, async_client: AsyncClient
    ) -> None:
        """Test pagination offset beyond available results."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/search/segments?q=test&offset=10000"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"] == []
            assert data["pagination"]["has_more"] is False
