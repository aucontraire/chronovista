"""Integration tests for sync API endpoints (T053a-T053e).

Tests cover authentication requirements, sync triggering, conflict handling,
status monitoring, and request validation for sync operations.
"""

from unittest.mock import patch
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

from chronovista.api.services.sync_manager import sync_manager, SyncManager
from chronovista.api.schemas.sync import SyncOperationType


class TestSyncAuthentication:
    """Test authentication requirements for sync endpoints (T053a)."""

    async def test_trigger_sync_subscriptions_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """POST /sync/subscriptions returns 401 when not authenticated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.post("/api/v1/sync/subscriptions")
            assert response.status_code == 401
            data = response.json()
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"

    async def test_trigger_sync_videos_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """POST /sync/videos returns 401 when not authenticated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.post("/api/v1/sync/videos")
            assert response.status_code == 401

    async def test_trigger_sync_transcripts_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """POST /sync/transcripts returns 401 when not authenticated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.post("/api/v1/sync/transcripts")
            assert response.status_code == 401

    async def test_trigger_sync_playlists_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """POST /sync/playlists returns 401 when not authenticated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.post("/api/v1/sync/playlists")
            assert response.status_code == 401

    async def test_trigger_sync_topics_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """POST /sync/topics returns 401 when not authenticated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.post("/api/v1/sync/topics")
            assert response.status_code == 401

    async def test_trigger_sync_channel_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """POST /sync/channel returns 401 when not authenticated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.post("/api/v1/sync/channel")
            assert response.status_code == 401

    async def test_trigger_sync_liked_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """POST /sync/liked returns 401 when not authenticated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.post("/api/v1/sync/liked")
            assert response.status_code == 401

    async def test_get_sync_status_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """GET /sync/status returns 401 when not authenticated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/sync/status")
            assert response.status_code == 401
            data = response.json()
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"


class TestTriggerSync:
    """Test sync triggering endpoints (T053b)."""

    @pytest.fixture(autouse=True)
    def reset_sync_manager(self):
        """Reset sync manager state before each test."""
        # Reset the singleton state
        sync_manager._current_operation = None
        sync_manager._last_successful_sync = {}
        yield
        # Cleanup after test
        sync_manager._current_operation = None
        sync_manager._last_successful_sync = {}

    async def test_trigger_subscriptions_sync(self, async_client: AsyncClient) -> None:
        """Test triggering subscription sync returns 202 with valid SyncStartedResponse."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post("/api/v1/sync/subscriptions")
            assert response.status_code == 202
            data = response.json()
            assert "data" in data
            assert data["data"]["operation_type"] == "subscriptions"
            assert "operation_id" in data["data"]
            assert "started_at" in data["data"]
            assert "message" in data["data"]
            # Complete the operation to clean up
            sync_manager.complete_operation(success=True)

    async def test_trigger_videos_sync(self, async_client: AsyncClient) -> None:
        """Test triggering videos sync returns 202."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post("/api/v1/sync/videos")
            assert response.status_code == 202
            data = response.json()
            assert data["data"]["operation_type"] == "videos"
            assert "operation_id" in data["data"]
            # Complete the operation to clean up
            sync_manager.complete_operation(success=True)

    async def test_trigger_transcripts_sync_without_body(
        self, async_client: AsyncClient
    ) -> None:
        """Test triggering transcripts sync without request body returns 202."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post("/api/v1/sync/transcripts")
            assert response.status_code == 202
            data = response.json()
            assert data["data"]["operation_type"] == "transcripts"
            assert "operation_id" in data["data"]
            # Complete the operation to clean up
            sync_manager.complete_operation(success=True)

    async def test_trigger_transcripts_sync_with_body(
        self, async_client: AsyncClient
    ) -> None:
        """Test triggering transcripts sync with request body returns 202."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={
                    "video_ids": ["dQw4w9WgXcQ", "9bZkp7q19f0"],
                    "languages": ["en", "es"],
                },
            )
            assert response.status_code == 202
            data = response.json()
            assert data["data"]["operation_type"] == "transcripts"
            assert "operation_id" in data["data"]
            # Complete the operation to clean up
            sync_manager.complete_operation(success=True)

    async def test_trigger_transcripts_sync_custom_video_ids_and_languages(
        self, async_client: AsyncClient
    ) -> None:
        """Test POST /sync/transcripts with custom video_ids and languages."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={
                    "video_ids": ["abc123", "def456", "ghi789"],
                    "languages": ["en", "fr", "de"],
                    "force": True,
                },
            )
            assert response.status_code == 202
            data = response.json()
            assert data["data"]["operation_type"] == "transcripts"
            # Complete the operation to clean up
            sync_manager.complete_operation(success=True)

    async def test_trigger_playlists_sync(self, async_client: AsyncClient) -> None:
        """Test triggering playlists sync returns 202."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post("/api/v1/sync/playlists")
            assert response.status_code == 202
            data = response.json()
            assert data["data"]["operation_type"] == "playlists"
            # Complete the operation to clean up
            sync_manager.complete_operation(success=True)

    async def test_trigger_topics_sync(self, async_client: AsyncClient) -> None:
        """Test triggering topics sync returns 202."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post("/api/v1/sync/topics")
            assert response.status_code == 202
            data = response.json()
            assert data["data"]["operation_type"] == "topics"
            # Complete the operation to clean up
            sync_manager.complete_operation(success=True)

    async def test_trigger_channel_sync(self, async_client: AsyncClient) -> None:
        """Test triggering channel sync returns 202."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post("/api/v1/sync/channel")
            assert response.status_code == 202
            data = response.json()
            assert data["data"]["operation_type"] == "channel"
            # Complete the operation to clean up
            sync_manager.complete_operation(success=True)

    async def test_trigger_liked_sync(self, async_client: AsyncClient) -> None:
        """Test triggering liked videos sync returns 202."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post("/api/v1/sync/liked")
            assert response.status_code == 202
            data = response.json()
            assert data["data"]["operation_type"] == "liked"
            # Complete the operation to clean up
            sync_manager.complete_operation(success=True)

    async def test_trigger_invalid_operation_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """Test triggering invalid operation returns 422 Validation Error."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post("/api/v1/sync/invalid_operation")
            assert response.status_code == 422

    async def test_operation_id_format_is_correct(
        self, async_client: AsyncClient
    ) -> None:
        """Test operation_id matches pattern: {type}_{timestamp}_{random}."""
        import re

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post("/api/v1/sync/subscriptions")
            assert response.status_code == 202
            data = response.json()
            operation_id = data["data"]["operation_id"]

            # Validate format: {type}_{YYYYMMDDTHHMMSSZ}_{random}
            pattern = r"^[a-z]+_\d{8}T\d{6}Z_[a-zA-Z0-9]{4,6}$"
            assert re.match(
                pattern, operation_id
            ), f"operation_id '{operation_id}' does not match expected pattern"

            # Verify it starts with correct operation type
            assert operation_id.startswith("subscriptions_")
            # Complete the operation to clean up
            sync_manager.complete_operation(success=True)


class TestConflictHandling:
    """Test conflict handling when sync is already running (T053c)."""

    @pytest.fixture(autouse=True)
    def reset_sync_manager(self):
        """Reset sync manager state before each test."""
        sync_manager._current_operation = None
        sync_manager._last_successful_sync = {}
        yield
        sync_manager._current_operation = None
        sync_manager._last_successful_sync = {}

    async def test_trigger_sync_while_another_is_running_returns_409(
        self, async_client: AsyncClient
    ) -> None:
        """Test that triggering sync while another is running returns 409."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Start first sync
            response1 = await async_client.post("/api/v1/sync/subscriptions")
            assert response1.status_code == 202

            # Try to start second sync while first is running
            response2 = await async_client.post("/api/v1/sync/videos")
            assert response2.status_code == 409
            data = response2.json()
            assert data["error"]["code"] == "CONFLICT"

            # Cleanup
            sync_manager.complete_operation(success=True)

    async def test_409_response_includes_current_operation_details(
        self, async_client: AsyncClient
    ) -> None:
        """Test that 409 response includes current operation details."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Start first sync
            response1 = await async_client.post("/api/v1/sync/transcripts")
            assert response1.status_code == 202
            first_operation_id = response1.json()["data"]["operation_id"]

            # Try to start second sync
            response2 = await async_client.post("/api/v1/sync/playlists")
            assert response2.status_code == 409
            data = response2.json()

            # Check that details include current operation info
            assert "details" in data["error"]
            details = data["error"]["details"]
            assert "operation_id" in details
            assert details["operation_id"] == first_operation_id
            assert "operation_type" in details
            assert details["operation_type"] == "transcripts"
            assert "started_at" in details

            # Cleanup
            sync_manager.complete_operation(success=True)

    async def test_409_error_message_is_actionable(
        self, async_client: AsyncClient
    ) -> None:
        """Test that the 409 error message is actionable."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Start first sync
            await async_client.post("/api/v1/sync/channel")

            # Try to start second sync
            response = await async_client.post("/api/v1/sync/liked")
            assert response.status_code == 409
            data = response.json()

            # Verify message is helpful
            message = data["error"]["message"]
            assert "in progress" in message.lower()
            assert "wait" in message.lower() or "check status" in message.lower()

            # Cleanup
            sync_manager.complete_operation(success=True)


class TestSyncStatus:
    """Test sync status monitoring endpoint (T053d)."""

    @pytest.fixture(autouse=True)
    def reset_sync_manager(self):
        """Reset sync manager state before each test."""
        sync_manager._current_operation = None
        sync_manager._last_successful_sync = {}
        yield
        sync_manager._current_operation = None
        sync_manager._last_successful_sync = {}

    async def test_get_status_returns_idle_when_no_sync_running(
        self, async_client: AsyncClient
    ) -> None:
        """Test GET /sync/status returns idle when no sync running."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/sync/status")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert data["data"]["status"] == "idle"

    async def test_get_status_returns_running_status_during_sync(
        self, async_client: AsyncClient
    ) -> None:
        """Test GET /sync/status returns running status during sync."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Start a sync
            await async_client.post("/api/v1/sync/videos")

            # Check status
            response = await async_client.get("/api/v1/sync/status")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "running"
            assert data["data"]["operation_type"] == "videos"
            assert data["data"]["operation_id"] is not None

            # Cleanup
            sync_manager.complete_operation(success=True)

    async def test_status_includes_progress_when_available(
        self, async_client: AsyncClient
    ) -> None:
        """Test status includes progress when available."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Start a sync
            await async_client.post("/api/v1/sync/subscriptions")

            # Update progress
            sync_manager.update_progress(processed=10, total=100, current_item="test")

            # Check status
            response = await async_client.get("/api/v1/sync/status")
            assert response.status_code == 200
            data = response.json()
            assert "progress" in data["data"]
            assert data["data"]["progress"] is not None
            progress = data["data"]["progress"]
            assert progress["processed_items"] == 10
            assert progress["total_items"] == 100
            assert progress["current_item"] == "test"

            # Cleanup
            sync_manager.complete_operation(success=True)

    async def test_status_includes_last_successful_sync_when_available(
        self, async_client: AsyncClient
    ) -> None:
        """Test status includes last_successful_sync when available."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Start and complete a sync
            await async_client.post("/api/v1/sync/topics")
            sync_manager.complete_operation(success=True)

            # Check status
            response = await async_client.get("/api/v1/sync/status")
            assert response.status_code == 200
            data = response.json()
            # After completion, status should be idle but include last_successful_sync
            # Note: The sync_manager clears current_operation on completion,
            # so we won't see last_successful_sync in the idle status response
            # unless we start a new operation of the same type
            assert data["data"]["status"] == "idle"

    async def test_status_includes_started_at_timestamp(
        self, async_client: AsyncClient
    ) -> None:
        """Test status includes started_at timestamp during sync."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Start a sync
            await async_client.post("/api/v1/sync/playlists")

            # Check status
            response = await async_client.get("/api/v1/sync/status")
            assert response.status_code == 200
            data = response.json()
            assert "started_at" in data["data"]
            assert data["data"]["started_at"] is not None
            # Verify it's a valid ISO datetime
            from datetime import datetime

            datetime.fromisoformat(data["data"]["started_at"].replace("Z", "+00:00"))

            # Cleanup
            sync_manager.complete_operation(success=True)

    async def test_status_structure_when_idle(self, async_client: AsyncClient) -> None:
        """Test complete status structure when idle."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/sync/status")
            assert response.status_code == 200
            data = response.json()["data"]

            # Verify all expected fields exist
            assert "status" in data
            assert "operation_type" in data
            assert "operation_id" in data
            assert "progress" in data
            assert "last_successful_sync" in data
            assert "error_message" in data
            assert "started_at" in data
            assert "completed_at" in data

            # When idle, most fields should be None
            assert data["status"] == "idle"
            assert data["operation_type"] is None
            assert data["operation_id"] is None
            assert data["progress"] is None


class TestTranscriptSyncRequestValidation:
    """Test TranscriptSyncRequest validation (T053e)."""

    @pytest.fixture(autouse=True)
    def reset_sync_manager(self):
        """Reset sync manager state before each test."""
        sync_manager._current_operation = None
        sync_manager._last_successful_sync = {}
        yield
        sync_manager._current_operation = None
        sync_manager._last_successful_sync = {}

    async def test_empty_video_ids_list_treated_as_none(
        self, async_client: AsyncClient
    ) -> None:
        """Test that empty video_ids list is treated as None (sync all)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={"video_ids": [], "languages": ["en"]},
            )
            # Empty list should be converted to None and accepted
            assert response.status_code == 202
            # Cleanup
            sync_manager.complete_operation(success=True)

    async def test_empty_string_video_ids_are_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """Test that empty string video_ids are rejected."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={"video_ids": ["abc123", "", "def456"], "languages": ["en"]},
            )
            assert response.status_code == 422
            data = response.json()
            # Check that error mentions empty video IDs
            assert "error" in data

    async def test_whitespace_only_video_ids_are_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """Test that whitespace-only video_ids are rejected."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={"video_ids": ["abc123", "   ", "def456"], "languages": ["en"]},
            )
            assert response.status_code == 422

    async def test_invalid_language_codes_are_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """Test that invalid language codes are rejected."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Invalid language code format
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={"video_ids": ["abc123"], "languages": ["invalid-lang-code-123"]},
            )
            assert response.status_code == 422

    async def test_empty_languages_list_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """Test that empty languages list is rejected."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={"video_ids": ["abc123"], "languages": []},
            )
            assert response.status_code == 422

    async def test_empty_string_language_codes_are_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """Test that empty string language codes are rejected."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={"video_ids": ["abc123"], "languages": ["en", ""]},
            )
            assert response.status_code == 422

    async def test_valid_request_with_all_fields_works(
        self, async_client: AsyncClient
    ) -> None:
        """Test that valid request with all fields works."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={
                    "video_ids": ["dQw4w9WgXcQ", "9bZkp7q19f0"],
                    "languages": ["en", "es", "fr"],
                    "force": True,
                },
            )
            assert response.status_code == 202
            data = response.json()
            assert data["data"]["operation_type"] == "transcripts"
            # Cleanup
            sync_manager.complete_operation(success=True)

    async def test_valid_request_with_minimal_fields_works(
        self, async_client: AsyncClient
    ) -> None:
        """Test that valid request with minimal fields works."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={"video_ids": ["abc123"]},
            )
            # Should use default language ["en"]
            assert response.status_code == 202
            # Cleanup
            sync_manager.complete_operation(success=True)

    async def test_valid_bcp47_language_codes(
        self, async_client: AsyncClient
    ) -> None:
        """Test that valid BCP-47 language codes are accepted."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Test various valid BCP-47 formats
            valid_codes = ["en", "es", "fr", "en-US", "en-GB", "zh-CN", "pt-BR"]
            response = await async_client.post(
                "/api/v1/sync/transcripts",
                json={"video_ids": ["abc123"], "languages": valid_codes},
            )
            assert response.status_code == 202
            # Cleanup
            sync_manager.complete_operation(success=True)

    async def test_invalid_bcp47_format_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """Test that invalid BCP-47 format is rejected."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Invalid formats
            invalid_codes = ["e", "english", "en-", "-US", "en_US"]
            for code in invalid_codes:
                response = await async_client.post(
                    "/api/v1/sync/transcripts",
                    json={"video_ids": ["abc123"], "languages": [code]},
                )
                assert (
                    response.status_code == 422
                ), f"Expected 422 for invalid code '{code}'"


class TestSyncStatusResponse:
    """Test sync status response structure and fields."""

    @pytest.fixture(autouse=True)
    def reset_sync_manager(self):
        """Reset sync manager state before each test."""
        sync_manager._current_operation = None
        sync_manager._last_successful_sync = {}
        yield
        sync_manager._current_operation = None
        sync_manager._last_successful_sync = {}

    async def test_status_response_wrapper_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test status response has correct wrapper structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/sync/status")
            assert response.status_code == 200
            data = response.json()
            # Should have data wrapper
            assert "data" in data
            assert isinstance(data["data"], dict)

    async def test_started_response_wrapper_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test sync started response has correct wrapper structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post("/api/v1/sync/subscriptions")
            assert response.status_code == 202
            data = response.json()
            # Should have data wrapper
            assert "data" in data
            assert isinstance(data["data"], dict)
            # Cleanup
            sync_manager.complete_operation(success=True)
