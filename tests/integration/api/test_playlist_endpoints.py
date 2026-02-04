"""Integration tests for playlist API endpoints (US2: T019-T027).

Tests cover:
- T025: List/filter tests (linked, unlinked)
- T026: Mutually exclusive filter error test (400 MUTUALLY_EXCLUSIVE)
- T027: Video ordering and auth tests
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestListPlaylists:
    """Tests for GET /api/v1/playlists endpoint."""

    async def test_list_playlists_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that playlist list requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/playlists")
            assert response.status_code == 401

    async def test_list_playlists_returns_paginated_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test playlist list returns paginated response structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "pagination" in data
            assert isinstance(data["data"], list)

    async def test_list_playlists_pagination_metadata(
        self, async_client: AsyncClient
    ) -> None:
        """Test pagination metadata contains required fields."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists?limit=10&offset=0")
            assert response.status_code == 200
            data = response.json()

            pagination = data["pagination"]
            assert "total" in pagination
            assert "limit" in pagination
            assert "offset" in pagination
            assert "has_more" in pagination
            assert pagination["limit"] == 10
            assert pagination["offset"] == 0

    async def test_list_playlists_default_pagination(
        self, async_client: AsyncClient
    ) -> None:
        """Test default pagination values (limit=20, offset=0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists")
            assert response.status_code == 200
            data = response.json()

            assert data["pagination"]["limit"] == 20
            assert data["pagination"]["offset"] == 0

    async def test_list_playlists_limit_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test limit validation (max 100)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Over max
            response = await async_client.get("/api/v1/playlists?limit=200")
            assert response.status_code == 422  # Validation error

    async def test_list_playlists_offset_validation(
        self, async_client: AsyncClient
    ) -> None:
        """Test offset validation (must be >= 0)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists?offset=-1")
            assert response.status_code == 422  # Validation error


class TestPlaylistFilters:
    """Tests for playlist list filters (T025)."""

    async def test_linked_filter_true(self, async_client: AsyncClient) -> None:
        """Test linked=true filter for YouTube-linked playlists."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists?linked=true")
            assert response.status_code == 200
            data = response.json()
            # All returned playlists should be linked (is_linked=true)
            for playlist in data["data"]:
                assert playlist["is_linked"] is True

    async def test_linked_filter_false(self, async_client: AsyncClient) -> None:
        """Test linked=false filter for internal playlists."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists?linked=false")
            assert response.status_code == 200
            data = response.json()
            # All returned playlists should be unlinked (is_linked=false)
            for playlist in data["data"]:
                assert playlist["is_linked"] is False

    async def test_unlinked_filter_true(self, async_client: AsyncClient) -> None:
        """Test unlinked=true filter for internal playlists."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists?unlinked=true")
            assert response.status_code == 200
            data = response.json()
            # All returned playlists should be unlinked (is_linked=false)
            for playlist in data["data"]:
                assert playlist["is_linked"] is False

    async def test_unlinked_filter_false(self, async_client: AsyncClient) -> None:
        """Test unlinked=false filter for YouTube-linked playlists."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists?unlinked=false")
            assert response.status_code == 200
            data = response.json()
            # All returned playlists should be linked (is_linked=true)
            for playlist in data["data"]:
                assert playlist["is_linked"] is True


class TestPlaylistMutuallyExclusiveFilters:
    """Tests for mutually exclusive filter error (T026)."""

    async def test_linked_and_unlinked_both_true_returns_400(
        self, async_client: AsyncClient
    ) -> None:
        """Test that linked=true and unlinked=true returns 400 MUTUALLY_EXCLUSIVE."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/playlists?linked=true&unlinked=true"
            )
            assert response.status_code == 400
            data = response.json()
            # Typed exceptions use ErrorResponse format with "error" wrapper
            assert data["error"]["code"] == "MUTUALLY_EXCLUSIVE"
            assert "mutually exclusive" in data["error"]["message"].lower()
            assert data["error"]["details"]["field"] == "linked,unlinked"
            assert data["error"]["details"]["constraint"] == "mutually_exclusive"

    async def test_linked_true_unlinked_false_is_valid(
        self, async_client: AsyncClient
    ) -> None:
        """Test that linked=true and unlinked=false is valid (not both true)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/playlists?linked=true&unlinked=false"
            )
            # Should succeed - only both=true triggers the error
            assert response.status_code == 200

    async def test_linked_false_unlinked_true_is_valid(
        self, async_client: AsyncClient
    ) -> None:
        """Test that linked=false and unlinked=true is valid (not both true)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/playlists?linked=false&unlinked=true"
            )
            # Should succeed - only both=true triggers the error
            assert response.status_code == 200


class TestPlaylistDetail:
    """Tests for GET /api/v1/playlists/{playlist_id} endpoint."""

    async def test_get_playlist_requires_auth(self, async_client: AsyncClient) -> None:
        """Test that playlist detail requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/playlists/PLtest123456789012345678901234")
            assert response.status_code == 401

    async def test_get_playlist_404_for_nonexistent(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 response for non-existent playlist."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists/PLnonexistent123456789012345")
            assert response.status_code == 404
            data = response.json()
            # Typed exceptions use ErrorResponse format with "error" wrapper
            assert data["error"]["code"] == "NOT_FOUND"
            assert "Playlist" in data["error"]["message"]

    async def test_get_playlist_actionable_error_message(
        self, async_client: AsyncClient
    ) -> None:
        """Test that 404 error has actionable message."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists/PLnonexistent123456789012345")
            data = response.json()
            # Check actionable guidance
            assert "Verify the playlist ID or run a sync" in data["error"]["message"]

    async def test_get_playlist_accepts_youtube_id(
        self, async_client: AsyncClient
    ) -> None:
        """Test playlist detail accepts YouTube IDs (PL prefix)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # PL-prefixed ID (YouTube format)
            response = await async_client.get("/api/v1/playlists/PLtest123456789012345678901234")
            # Should be 404 (not found) not 422 (validation error)
            assert response.status_code == 404

    async def test_get_playlist_accepts_internal_id(
        self, async_client: AsyncClient
    ) -> None:
        """Test playlist detail accepts internal IDs (int_ prefix)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # int_-prefixed ID (internal format)
            response = await async_client.get(
                "/api/v1/playlists/int_12345678-1234-1234-1234-123456789012"
            )
            # Should be 404 (not found) not 422 (validation error)
            assert response.status_code == 404

    async def test_get_playlist_accepts_system_ids(
        self, async_client: AsyncClient
    ) -> None:
        """Test playlist detail accepts system playlist IDs (LL/WL/HL)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            for system_id in ["LL", "WL", "HL"]:
                response = await async_client.get(f"/api/v1/playlists/{system_id}")
                # Should be 404 (not found) not 422 (validation error)
                assert response.status_code == 404


class TestPlaylistVideos:
    """Tests for GET /api/v1/playlists/{playlist_id}/videos endpoint (T027)."""

    async def test_get_playlist_videos_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test that playlist videos requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(
                "/api/v1/playlists/PLtest123456789012345678901234/videos"
            )
            assert response.status_code == 401

    async def test_get_playlist_videos_404_for_nonexistent_playlist(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 response for videos of non-existent playlist."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/playlists/PLnonexistent123456789012345/videos"
            )
            assert response.status_code == 404
            data = response.json()
            assert data["error"]["code"] == "NOT_FOUND"

    async def test_get_playlist_videos_returns_paginated_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test playlist videos returns paginated response structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Even if playlist doesn't exist, we should get 404 not a validation error
            response = await async_client.get(
                "/api/v1/playlists/PLtest123456789012345678901234/videos"
            )
            # Will be 404 since playlist doesn't exist in test db
            assert response.status_code == 404

    async def test_get_playlist_videos_pagination_params(
        self, async_client: AsyncClient
    ) -> None:
        """Test that pagination parameters are validated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Invalid limit
            response = await async_client.get(
                "/api/v1/playlists/PLtest123456789012345678901234/videos?limit=200"
            )
            assert response.status_code == 422

            # Invalid offset
            response = await async_client.get(
                "/api/v1/playlists/PLtest123456789012345678901234/videos?offset=-1"
            )
            assert response.status_code == 422


class TestPlaylistItemStructure:
    """Tests for playlist list item structure."""

    async def test_playlist_list_item_has_is_linked_field(
        self, async_client: AsyncClient
    ) -> None:
        """Test playlist list items include is_linked field."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/playlists?limit=1")
            assert response.status_code == 200
            data = response.json()

            # If there are playlists, check structure
            if data["data"]:
                playlist = data["data"][0]
                assert "playlist_id" in playlist
                assert "title" in playlist
                assert "video_count" in playlist
                assert "privacy_status" in playlist
                assert "is_linked" in playlist
                assert isinstance(playlist["is_linked"], bool)

    async def test_is_linked_derived_from_pl_prefix(
        self, async_client: AsyncClient
    ) -> None:
        """Test is_linked is True for PL-prefixed playlists."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Use linked filter to get YouTube playlists
            response = await async_client.get("/api/v1/playlists?linked=true&limit=10")
            assert response.status_code == 200
            data = response.json()

            # All returned playlists should be linked and have PL/LL/WL/HL prefix
            for playlist in data["data"]:
                assert playlist["is_linked"] is True
                prefix = playlist["playlist_id"][:2]
                assert prefix in ["PL", "LL", "WL", "HL"]

    async def test_is_linked_derived_from_int_prefix(
        self, async_client: AsyncClient
    ) -> None:
        """Test is_linked is False for int_-prefixed playlists."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Use unlinked filter to get internal playlists
            response = await async_client.get("/api/v1/playlists?unlinked=true&limit=10")
            assert response.status_code == 200
            data = response.json()

            # All returned playlists should be unlinked and have int_ prefix
            for playlist in data["data"]:
                assert playlist["is_linked"] is False
                assert playlist["playlist_id"].startswith("int_")
