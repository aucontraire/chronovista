"""Regression tests for F010 typed exception retrofit.

These tests verify that the retrofitted F010 endpoints return ErrorResponse format
with standardized error.code, error.message, and error.details fields.

The migration from raw HTTPException to typed exceptions (NotFoundError,
BadRequestError, ConflictError) should maintain backward compatibility while
providing consistent error response structure.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestVideosRouterErrorResponse:
    """Verify videos router returns ErrorResponse format."""

    async def test_video_not_found_returns_error_response_format(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 for video returns ErrorResponse with error.code and error.message."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/NONEXISTENT")

            assert response.status_code == 404
            data = response.json()

            # Verify ErrorResponse format
            assert "error" in data
            error = data["error"]
            assert "code" in error
            assert "message" in error
            assert error["code"] == "NOT_FOUND"
            assert "Video" in error["message"]
            assert "NONEXISTENT" in error["message"]

    async def test_video_not_found_includes_details(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 includes details with resource_type and identifier."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/xyzABCDEFGH")

            assert response.status_code == 404
            data = response.json()

            # Verify details structure
            assert "error" in data
            details = data["error"].get("details")
            assert details is not None
            assert details["resource_type"] == "Video"
            assert details["identifier"] == "xyzABCDEFGH"


class TestTranscriptsRouterErrorResponse:
    """Verify transcripts router returns ErrorResponse format."""

    async def test_transcript_video_not_found_returns_error_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 for transcript languages returns ErrorResponse format."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/videos/NONEXISTENT/transcript/languages"
            )

            assert response.status_code == 404
            data = response.json()

            # Verify ErrorResponse format
            assert "error" in data
            error = data["error"]
            assert error["code"] == "NOT_FOUND"
            assert "Video" in error["message"]

    async def test_transcript_not_found_returns_error_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test 404 for missing transcript returns ErrorResponse format."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/NONEXISTENT/transcript")

            assert response.status_code == 404
            data = response.json()

            # Verify ErrorResponse format
            assert "error" in data
            error = data["error"]
            assert error["code"] == "NOT_FOUND"
            assert "Transcript" in error["message"]


class TestSearchRouterErrorResponse:
    """Verify search router returns ErrorResponse format."""

    async def test_empty_search_query_returns_error_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test 400 for empty search query returns ErrorResponse format."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Query with only whitespace
            response = await async_client.get("/api/v1/search/segments?q=%20%20")

            assert response.status_code == 400
            data = response.json()

            # Verify ErrorResponse format
            assert "error" in data
            error = data["error"]
            assert error["code"] == "BAD_REQUEST"
            assert "empty" in error["message"].lower()


class TestPreferencesRouterErrorResponse:
    """Verify preferences router returns ErrorResponse format."""

    async def test_invalid_language_code_returns_error_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test 400 for invalid language code returns ErrorResponse format."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.put(
                "/api/v1/preferences/languages",
                json={
                    "preferences": [
                        {"language_code": "invalid-code", "preference_type": "fluent"}
                    ]
                },
            )

            assert response.status_code == 400
            data = response.json()

            # Verify ErrorResponse format
            assert "error" in data
            error = data["error"]
            assert error["code"] == "BAD_REQUEST"
            assert "Invalid language codes" in error["message"]
            assert "details" in error
            assert "invalid_values" in error["details"]

    async def test_invalid_preference_type_returns_error_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test 400 for invalid preference type returns ErrorResponse format."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.put(
                "/api/v1/preferences/languages",
                json={
                    "preferences": [
                        {"language_code": "en", "preference_type": "invalid-type"}
                    ]
                },
            )

            assert response.status_code == 400
            data = response.json()

            # Verify ErrorResponse format
            assert "error" in data
            error = data["error"]
            assert error["code"] == "BAD_REQUEST"
            assert "Invalid preference types" in error["message"]


class TestSyncRouterErrorResponse:
    """Verify sync router returns ErrorResponse format."""

    async def test_sync_conflict_returns_error_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test 409 for sync conflict returns ErrorResponse format."""
        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.sync.sync_manager"
            ) as mock_sync_manager,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_sync_manager.is_sync_running.return_value = True

            # Create a mock status object
            from unittest.mock import MagicMock
            from datetime import datetime, timezone

            mock_status = MagicMock()
            mock_status.operation_id = "test_op_123"
            mock_status.operation_type = MagicMock()
            mock_status.operation_type.value = "subscriptions"
            mock_status.started_at = datetime.now(timezone.utc)
            mock_sync_manager.get_current_status.return_value = mock_status

            response = await async_client.post("/api/v1/sync/subscriptions")

            assert response.status_code == 409
            data = response.json()

            # Verify ErrorResponse format
            assert "error" in data
            error = data["error"]
            assert error["code"] == "CONFLICT"
            assert "already in progress" in error["message"].lower()
            assert "details" in error
            assert "operation_id" in error["details"]


class TestErrorResponseStructureConsistency:
    """Verify consistent ErrorResponse structure across all endpoints."""

    async def test_all_404_errors_have_consistent_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test that all 404 errors have the same structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Test multiple 404 scenarios
            endpoints = [
                "/api/v1/videos/NONEXISTENT",
                "/api/v1/videos/NONEXISTENT/transcript/languages",
                "/api/v1/videos/NONEXISTENT/transcript",
            ]

            for endpoint in endpoints:
                response = await async_client.get(endpoint)
                assert response.status_code == 404, f"Failed for {endpoint}"
                data = response.json()

                # All should have error wrapper
                assert "error" in data, f"Missing error wrapper in {endpoint}"
                error = data["error"]

                # All should have required fields
                assert "code" in error, f"Missing code in {endpoint}"
                assert "message" in error, f"Missing message in {endpoint}"
                assert error["code"] == "NOT_FOUND", f"Wrong code in {endpoint}"

    async def test_error_response_does_not_have_detail_key(
        self, async_client: AsyncClient
    ) -> None:
        """Test that new format uses 'error' not 'detail'."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/videos/NONEXISTENT")

            assert response.status_code == 404
            data = response.json()

            # Should use 'error' not 'detail' (old format)
            assert "error" in data
            assert "detail" not in data
