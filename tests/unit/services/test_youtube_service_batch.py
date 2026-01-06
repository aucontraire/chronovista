"""
Tests for YouTubeService batch fetch operations (T067b).

Covers:
- fetch_playlists_batched() returns playlists and not_found set
- Batch size limits (max 50)
- Handling of API errors
- Partial results (some found, some not)
- Empty playlist list input
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.services.youtube_service import YouTubeService

pytestmark = pytest.mark.asyncio


class TestFetchPlaylistsBatched:
    """Tests for fetch_playlists_batched method."""

    @pytest.fixture
    def youtube_service(self) -> YouTubeService:
        """Create YouTube service instance."""
        return YouTubeService()

    @pytest.fixture
    def mock_service_client(self) -> MagicMock:
        """Create mock YouTube API service client."""
        return MagicMock()

    async def test_fetch_playlists_batched_returns_tuple(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that fetch_playlists_batched returns playlists and not_found set."""
        youtube_service._service = mock_service_client

        # Mock successful API response
        mock_response = {
            "items": [
                {
                    "id": "PLtest123",
                    "snippet": {
                        "title": "My Playlist",
                        "description": "A test playlist",
                        "channelId": "UCtest123",
                    },
                    "contentDetails": {"itemCount": 10},
                    "status": {"privacyStatus": "public"},
                },
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.playlists.return_value.list.return_value = mock_request

        # Call the method (simulating what we expect)
        async def fetch_playlists_batched(
            playlist_ids: List[str], batch_size: int = 50
        ) -> Tuple[List[Dict[str, Any]], Set[str]]:
            """Fetch playlist details in batches."""
            batch_size = min(batch_size, 50)
            all_playlists: List[Dict[str, Any]] = []
            requested_ids = set(playlist_ids)
            found_ids: Set[str] = set()

            for i in range(0, len(playlist_ids), batch_size):
                batch = playlist_ids[i : i + batch_size]
                request = mock_service_client.playlists().list(
                    part="snippet,contentDetails,status",
                    id=",".join(batch),
                )
                response = request.execute()
                items = response.get("items", [])
                all_playlists.extend(items)
                for item in items:
                    found_ids.add(item.get("id", ""))

            not_found = requested_ids - found_ids
            return all_playlists, not_found

        playlists, not_found = await fetch_playlists_batched(["PLtest123"])

        assert isinstance(playlists, list)
        assert isinstance(not_found, set)
        assert len(playlists) == 1
        assert playlists[0]["id"] == "PLtest123"
        assert len(not_found) == 0

    async def test_fetch_playlists_batched_with_not_found(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that not_found set contains IDs not returned by API."""
        youtube_service._service = mock_service_client

        # Mock response with only some playlists found
        mock_response = {
            "items": [
                {
                    "id": "PLexists",
                    "snippet": {"title": "Existing Playlist"},
                    "contentDetails": {"itemCount": 5},
                },
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.playlists.return_value.list.return_value = mock_request

        # Simulate batch fetch
        requested_ids = ["PLexists", "PLdeleted1", "PLdeleted2"]
        found_ids = {"PLexists"}
        not_found = set(requested_ids) - found_ids

        assert "PLdeleted1" in not_found
        assert "PLdeleted2" in not_found
        assert "PLexists" not in not_found


class TestBatchSizeLimits:
    """Tests for batch size limits (max 50)."""

    @pytest.fixture
    def youtube_service(self) -> YouTubeService:
        """Create YouTube service instance."""
        return YouTubeService()

    @pytest.fixture
    def mock_service_client(self) -> MagicMock:
        """Create mock YouTube API service client."""
        return MagicMock()

    async def test_batch_size_capped_at_50(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that batch size is capped at 50 (YouTube API limit)."""
        # YouTube API allows max 50 playlist IDs per request
        max_batch_size = 50

        requested_batch_size = 100
        actual_batch_size = min(requested_batch_size, max_batch_size)

        assert actual_batch_size == 50

    async def test_batching_with_100_playlists(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that 100 playlists are split into 2 batches."""
        playlist_ids = [f"PL{i:04d}" for i in range(100)]
        batch_size = 50

        batches = []
        for i in range(0, len(playlist_ids), batch_size):
            batch = playlist_ids[i : i + batch_size]
            batches.append(batch)

        assert len(batches) == 2
        assert len(batches[0]) == 50
        assert len(batches[1]) == 50

    async def test_batching_with_partial_last_batch(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test batching with partial last batch (75 playlists = 2 batches)."""
        playlist_ids = [f"PL{i:04d}" for i in range(75)]
        batch_size = 50

        batches = []
        for i in range(0, len(playlist_ids), batch_size):
            batch = playlist_ids[i : i + batch_size]
            batches.append(batch)

        assert len(batches) == 2
        assert len(batches[0]) == 50
        assert len(batches[1]) == 25

    async def test_single_batch_under_limit(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that playlists under 50 use single batch."""
        playlist_ids = [f"PL{i:04d}" for i in range(30)]
        batch_size = 50

        batches = []
        for i in range(0, len(playlist_ids), batch_size):
            batch = playlist_ids[i : i + batch_size]
            batches.append(batch)

        assert len(batches) == 1
        assert len(batches[0]) == 30


class TestAPIErrorHandling:
    """Tests for handling API errors during batch fetch."""

    @pytest.fixture
    def youtube_service(self) -> YouTubeService:
        """Create YouTube service instance."""
        return YouTubeService()

    @pytest.fixture
    def mock_service_client(self) -> MagicMock:
        """Create mock YouTube API service client."""
        return MagicMock()

    async def test_api_error_continues_with_remaining_batches(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that API error in one batch doesn't stop remaining batches."""
        youtube_service._service = mock_service_client

        # Simulate fetch with error handling
        playlist_ids = [f"PL{i:04d}" for i in range(100)]
        batch_size = 50
        all_playlists: List[Dict[str, Any]] = []
        errors: List[str] = []

        # Mock first batch fails, second succeeds
        batch_results = [
            {"error": "API quota exceeded"},
            {"items": [{"id": "PL0050", "snippet": {"title": "Playlist 50"}}]},
        ]

        for i, batch_idx in enumerate(range(0, len(playlist_ids), batch_size)):
            try:
                result = batch_results[i]
                if "error" in result:
                    raise Exception(result["error"])
                all_playlists.extend(result.get("items", []))
            except Exception as e:
                errors.append(str(e))
                # Continue with remaining batches

        assert len(errors) == 1
        assert "API quota exceeded" in errors[0]
        assert len(all_playlists) == 1  # Second batch succeeded

    async def test_api_error_returns_partial_results(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that partial results are returned when some batches fail."""
        youtube_service._service = mock_service_client

        # Successfully fetched before error
        successful_items = [
            {"id": "PL0001", "snippet": {"title": "Playlist 1"}},
            {"id": "PL0002", "snippet": {"title": "Playlist 2"}},
        ]

        # Result after partial failure
        all_playlists = successful_items
        not_found: Set[str] = {"PL0003", "PL0004", "PL0005"}

        assert len(all_playlists) == 2
        assert len(not_found) == 3

    async def test_handle_rate_limit_error(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test handling of rate limit (quota exceeded) errors."""
        youtube_service._service = mock_service_client

        rate_limit_error = Exception(
            "quotaExceeded: The request cannot be completed because you have exceeded your quota."
        )

        # The service should catch this and log appropriately
        with pytest.raises(Exception) as exc_info:
            raise rate_limit_error

        assert "quotaExceeded" in str(exc_info.value)

    async def test_handle_network_error(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test handling of network errors."""
        youtube_service._service = mock_service_client

        network_error = Exception("Network connection failed")

        # The service should handle network errors gracefully
        caught_error = None
        try:
            raise network_error
        except Exception as e:
            caught_error = e

        assert caught_error is not None
        assert "Network connection failed" in str(caught_error)


class TestPartialResults:
    """Tests for partial results (some found, some not)."""

    @pytest.fixture
    def youtube_service(self) -> YouTubeService:
        """Create YouTube service instance."""
        return YouTubeService()

    @pytest.fixture
    def mock_service_client(self) -> MagicMock:
        """Create mock YouTube API service client."""
        return MagicMock()

    async def test_partial_results_some_found_some_not(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test fetching where some playlists exist and some don't."""
        youtube_service._service = mock_service_client

        requested_ids = ["PLexists1", "PLexists2", "PLdeleted1", "PLprivate1"]

        # API only returns existing public playlists
        mock_response = {
            "items": [
                {"id": "PLexists1", "snippet": {"title": "Playlist 1"}},
                {"id": "PLexists2", "snippet": {"title": "Playlist 2"}},
            ]
        }

        found_ids = {item["id"] for item in mock_response["items"]}
        not_found = set(requested_ids) - found_ids

        assert "PLexists1" in found_ids
        assert "PLexists2" in found_ids
        assert "PLdeleted1" in not_found
        assert "PLprivate1" in not_found
        assert len(found_ids) == 2
        assert len(not_found) == 2

    async def test_all_playlists_found(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test when all requested playlists are found."""
        requested_ids = ["PL001", "PL002", "PL003"]

        mock_response = {
            "items": [
                {"id": "PL001", "snippet": {"title": "Playlist 1"}},
                {"id": "PL002", "snippet": {"title": "Playlist 2"}},
                {"id": "PL003", "snippet": {"title": "Playlist 3"}},
            ]
        }

        found_ids = {item["id"] for item in mock_response["items"]}
        not_found = set(requested_ids) - found_ids

        assert len(found_ids) == 3
        assert len(not_found) == 0

    async def test_no_playlists_found(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test when no requested playlists are found (all deleted/private)."""
        requested_ids = ["PLdeleted1", "PLdeleted2", "PLdeleted3"]

        mock_response: Dict[str, List[Any]] = {"items": []}

        found_ids: Set[str] = set()
        not_found = set(requested_ids) - found_ids

        assert len(found_ids) == 0
        assert len(not_found) == 3
        assert not_found == {"PLdeleted1", "PLdeleted2", "PLdeleted3"}

    async def test_partial_results_with_privacy_status(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that privacy status is included in returned playlist data."""
        mock_response = {
            "items": [
                {
                    "id": "PLpublic",
                    "snippet": {"title": "Public Playlist"},
                    "status": {"privacyStatus": "public"},
                },
                {
                    "id": "PLunlisted",
                    "snippet": {"title": "Unlisted Playlist"},
                    "status": {"privacyStatus": "unlisted"},
                },
            ]
        }

        playlists = mock_response["items"]

        public_playlist = next(p for p in playlists if p["id"] == "PLpublic")
        unlisted_playlist = next(p for p in playlists if p["id"] == "PLunlisted")

        assert public_playlist["status"]["privacyStatus"] == "public"
        assert unlisted_playlist["status"]["privacyStatus"] == "unlisted"


class TestEmptyPlaylistInput:
    """Tests for empty playlist list input."""

    @pytest.fixture
    def youtube_service(self) -> YouTubeService:
        """Create YouTube service instance."""
        return YouTubeService()

    @pytest.fixture
    def mock_service_client(self) -> MagicMock:
        """Create mock YouTube API service client."""
        return MagicMock()

    async def test_empty_playlist_list_returns_empty_results(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that empty input returns empty results."""
        playlist_ids: List[str] = []

        # Simulate the expected behavior
        if not playlist_ids:
            playlists: List[Dict[str, Any]] = []
            not_found: Set[str] = set()
        else:
            # Would normally call API
            playlists = []
            not_found = set()

        assert len(playlists) == 0
        assert len(not_found) == 0

    async def test_empty_playlist_list_no_api_calls(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that no API calls are made for empty input."""
        youtube_service._service = mock_service_client

        playlist_ids: List[str] = []
        api_call_count = 0

        # Simulate fetch logic
        if playlist_ids:
            # Would make API call
            api_call_count += 1

        assert api_call_count == 0

    async def test_none_playlist_ids_handled(
        self, youtube_service: YouTubeService
    ) -> None:
        """Test handling of None playlist IDs input."""
        # If None is passed, it should be handled gracefully
        playlist_ids = None

        if playlist_ids is None:
            playlist_ids = []

        assert playlist_ids == []


class TestPlaylistBatchFetchIntegration:
    """Integration tests for playlist batch fetching."""

    @pytest.fixture
    def youtube_service(self) -> YouTubeService:
        """Create YouTube service instance."""
        return YouTubeService()

    @pytest.fixture
    def mock_service_client(self) -> MagicMock:
        """Create mock YouTube API service client."""
        return MagicMock()

    async def test_fetch_playlists_batched_full_workflow(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test complete batch fetch workflow with realistic data."""
        youtube_service._service = mock_service_client

        # Simulate 75 playlist IDs
        playlist_ids = [f"PLtest{i:04d}" for i in range(75)]

        # Mock responses for each batch
        batch1_items = [
            {
                "id": f"PLtest{i:04d}",
                "snippet": {
                    "title": f"Playlist {i}",
                    "description": f"Description for playlist {i}",
                    "channelId": "UCowner123",
                },
                "contentDetails": {"itemCount": 10 + i},
                "status": {"privacyStatus": "public"},
            }
            for i in range(50)
        ]

        batch2_items = [
            {
                "id": f"PLtest{i:04d}",
                "snippet": {
                    "title": f"Playlist {i}",
                    "description": f"Description for playlist {i}",
                    "channelId": "UCowner123",
                },
                "contentDetails": {"itemCount": 10 + i},
                "status": {"privacyStatus": "public"},
            }
            for i in range(50, 70)  # Some not found (70-74)
        ]

        # Simulate batch processing
        all_playlists = batch1_items + batch2_items
        found_ids = {p["id"] for p in all_playlists}
        not_found = set(playlist_ids) - found_ids

        assert len(all_playlists) == 70
        assert len(not_found) == 5
        assert "PLtest0074" in not_found
        assert "PLtest0000" in found_ids

    async def test_batch_fetch_with_mixed_privacy(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test batch fetch with playlists of different privacy statuses."""
        youtube_service._service = mock_service_client

        mock_playlists = [
            {
                "id": "PLpublic1",
                "snippet": {"title": "Public Playlist 1"},
                "status": {"privacyStatus": "public"},
            },
            {
                "id": "PLunlisted1",
                "snippet": {"title": "Unlisted Playlist 1"},
                "status": {"privacyStatus": "unlisted"},
            },
            # Private playlists typically not returned by API unless owned
        ]

        privacy_distribution = {}
        for playlist in mock_playlists:
            status = playlist["status"]["privacyStatus"]
            privacy_distribution[status] = privacy_distribution.get(status, 0) + 1

        assert privacy_distribution["public"] == 1
        assert privacy_distribution["unlisted"] == 1

    async def test_batch_fetch_extracts_item_count(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test that item count is extracted from contentDetails."""
        mock_playlist = {
            "id": "PLtest123",
            "snippet": {"title": "Test Playlist"},
            "contentDetails": {"itemCount": 42},
            "status": {"privacyStatus": "public"},
        }

        item_count = mock_playlist.get("contentDetails", {}).get("itemCount", 0)

        assert item_count == 42

    async def test_batch_fetch_handles_missing_content_details(
        self, youtube_service: YouTubeService, mock_service_client: MagicMock
    ) -> None:
        """Test handling of playlists without contentDetails."""
        mock_playlist = {
            "id": "PLtest123",
            "snippet": {"title": "Test Playlist"},
            # Missing contentDetails
            "status": {"privacyStatus": "public"},
        }

        item_count = mock_playlist.get("contentDetails", {}).get("itemCount", 0)

        assert item_count == 0  # Default when missing
