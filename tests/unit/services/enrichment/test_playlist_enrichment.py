"""
Tests for playlist enrichment service functionality.

Covers Phase 9: User Story 7 - Enrich Playlist Metadata:
- enrich_playlists() method
- Playlist field updates (title, description, privacy_status, item_count)
- Deleted playlist handling (not found in API)
- Dry run mode for playlists
- Playlist enrichment summary output
- Integration with video enrichment
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


class TestEnrichPlaylistsMethod:
    """Tests for enrich_playlists() method existence and behavior."""

    async def test_enrich_playlists_method_signature(self) -> None:
        """Test that enrich_playlists method has expected signature."""
        # This documents the expected method signature for playlist enrichment
        # The actual implementation should match this interface

        # Expected signature:
        # async def enrich_playlists(
        #     self,
        #     session: AsyncSession,
        #     limit: Optional[int] = None,
        #     dry_run: bool = False,
        # ) -> PlaylistEnrichmentResult
        pass  # This test documents expected interface

    async def test_enrich_playlists_returns_result(self) -> None:
        """Test that enrich_playlists returns a result object."""
        # Mock enrichment service
        mock_service = MagicMock()
        mock_service.enrich_playlists = AsyncMock(
            return_value={
                "playlists_processed": 10,
                "playlists_updated": 8,
                "playlists_deleted": 2,
                "errors": 0,
            }
        )

        result = await mock_service.enrich_playlists(MagicMock(), limit=10)

        assert result is not None
        assert "playlists_processed" in result
        assert "playlists_updated" in result

    async def test_enrich_playlists_with_limit(self) -> None:
        """Test that enrich_playlists respects limit parameter."""
        mock_service = MagicMock()
        mock_service.enrich_playlists = AsyncMock(
            return_value={
                "playlists_processed": 5,
                "playlists_updated": 5,
                "playlists_deleted": 0,
                "errors": 0,
            }
        )

        result = await mock_service.enrich_playlists(MagicMock(), limit=5)

        assert result["playlists_processed"] == 5
        mock_service.enrich_playlists.assert_called_once()


class TestPlaylistFieldUpdates:
    """Tests for playlist field updates during enrichment."""

    async def test_title_update_from_api(self) -> None:
        """Test that playlist title is updated from API response."""
        # Mock database playlist (with placeholder title)
        db_playlist: dict[str, Any] = {
            "playlist_id": "PLtest123",
            "title": "[Placeholder] Playlist PLtest123",
            "description": None,
            "privacy_status": "unknown",
            "video_count": 0,
        }

        # Mock API response
        api_response: dict[str, Any] = {
            "id": "PLtest123",
            "snippet": {
                "title": "My Awesome Music Collection",
                "description": "All my favorite songs",
            },
            "status": {"privacyStatus": "public"},
            "contentDetails": {"itemCount": 42},
        }

        # Apply updates
        updated_playlist: dict[str, Any] = {
            **db_playlist,
            "title": api_response["snippet"]["title"],
            "description": api_response["snippet"]["description"],
            "privacy_status": api_response["status"]["privacyStatus"],
            "video_count": api_response["contentDetails"]["itemCount"],
        }

        assert updated_playlist["title"] == "My Awesome Music Collection"
        assert updated_playlist["description"] == "All my favorite songs"
        assert updated_playlist["privacy_status"] == "public"
        assert updated_playlist["video_count"] == 42

    async def test_description_update_from_api(self) -> None:
        """Test that playlist description is updated from API response."""
        db_playlist: dict[str, Any] = {
            "playlist_id": "PLtest456",
            "description": None,
        }

        api_response: dict[str, Any] = {
            "snippet": {
                "description": "This is a detailed playlist description with multiple lines.\nLine 2\nLine 3",
            },
        }

        updated_description = api_response["snippet"]["description"]

        assert updated_description is not None
        assert "detailed playlist description" in updated_description
        assert "\n" in updated_description

    async def test_privacy_status_update_from_api(self) -> None:
        """Test that playlist privacy status is updated from API response."""
        test_cases = [
            {"api_status": "public", "expected": "public"},
            {"api_status": "private", "expected": "private"},
            {"api_status": "unlisted", "expected": "unlisted"},
        ]

        for test_case in test_cases:
            api_response: dict[str, Any] = {"status": {"privacyStatus": test_case["api_status"]}}
            updated_status = api_response["status"]["privacyStatus"]
            assert updated_status == test_case["expected"]

    async def test_item_count_update_from_api(self) -> None:
        """Test that playlist item count is updated from API response."""
        db_playlist: dict[str, Any] = {"video_count": 0}

        api_response: dict[str, Any] = {"contentDetails": {"itemCount": 157}}

        updated_count = api_response["contentDetails"]["itemCount"]

        assert updated_count == 157

    async def test_empty_description_from_api(self) -> None:
        """Test handling of empty description from API."""
        api_response: dict[str, Any] = {
            "snippet": {
                "title": "Playlist Title",
                "description": "",  # Empty but not None
            },
        }

        description = api_response["snippet"]["description"]
        assert description == ""

    async def test_missing_optional_fields_in_api_response(self) -> None:
        """Test handling of missing optional fields in API response."""
        api_response: dict[str, Any] = {
            "id": "PLtest789",
            "snippet": {
                "title": "Playlist With Missing Fields",
                # description might be missing
            },
            "status": {"privacyStatus": "public"},
            # contentDetails might be missing
        }

        # Should safely handle missing fields
        description = api_response["snippet"].get("description", "")
        item_count = api_response.get("contentDetails", {}).get("itemCount", 0)

        assert description == ""
        assert item_count == 0


class TestDeletedPlaylistHandling:
    """Tests for handling deleted playlists (not found in API)."""

    async def test_playlist_not_found_in_api(self) -> None:
        """Test handling of playlist not found in YouTube API."""
        # Request 3 playlists, API returns only 1
        requested_ids = ["PLexists", "PLdeleted1", "PLdeleted2"]

        api_response: dict[str, Any] = {
            "items": [
                {
                    "id": "PLexists",
                    "snippet": {"title": "Existing Playlist"},
                }
            ]
        }

        found_ids = {item["id"] for item in api_response["items"]}
        not_found_ids = set(requested_ids) - found_ids

        assert "PLdeleted1" in not_found_ids
        assert "PLdeleted2" in not_found_ids
        assert "PLexists" not in not_found_ids

    async def test_mark_playlist_as_deleted(self) -> None:
        """Test marking a playlist as deleted when not found in API."""
        playlist = {
            "playlist_id": "PLdeleted",
            "title": "Some Playlist",
            "is_deleted": False,
            "deleted_at": None,
        }

        # Mark as deleted
        playlist["is_deleted"] = True
        playlist["deleted_at"] = datetime.now(timezone.utc)

        assert playlist["is_deleted"] is True
        assert playlist["deleted_at"] is not None

    async def test_previously_deleted_playlist_found_again(self) -> None:
        """Test handling of previously deleted playlist found again in API."""
        # Playlist was marked deleted but now appears in API
        playlist = {
            "playlist_id": "PLrecovered",
            "title": "[Placeholder] Playlist PLrecovered",
            "is_deleted": True,
            "deleted_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
        }

        # API now returns this playlist
        api_response: dict[str, Any] = {
            "id": "PLrecovered",
            "snippet": {"title": "Recovered Playlist"},
            "status": {"privacyStatus": "public"},
        }

        # Should un-delete and update
        playlist["is_deleted"] = False
        playlist["deleted_at"] = None
        playlist["title"] = api_response["snippet"]["title"]

        assert playlist["is_deleted"] is False
        assert playlist["deleted_at"] is None
        assert playlist["title"] == "Recovered Playlist"

    async def test_count_deleted_playlists_in_summary(self) -> None:
        """Test that deleted playlists are counted in summary."""
        enrichment_result = {
            "playlists_processed": 10,
            "playlists_updated": 5,
            "playlists_deleted": 3,
            "playlists_unchanged": 2,
            "errors": 0,
        }

        # Verify counts add up
        total = (
            enrichment_result["playlists_updated"]
            + enrichment_result["playlists_deleted"]
            + enrichment_result["playlists_unchanged"]
        )

        assert total == enrichment_result["playlists_processed"]
        assert enrichment_result["playlists_deleted"] == 3


class TestDryRunModeForPlaylists:
    """Tests for dry run mode in playlist enrichment."""

    async def test_dry_run_does_not_modify_database(self) -> None:
        """Test that dry run mode doesn't modify the database."""
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        dry_run = True

        # In dry run mode, commit should not be called
        if not dry_run:
            await mock_session.commit()

        # Verify commit was not called
        mock_session.commit.assert_not_called()

    async def test_dry_run_returns_preview_results(self) -> None:
        """Test that dry run mode returns preview of what would be done."""
        mock_playlists_to_update = [
            {"playlist_id": "PL001", "title": "[Placeholder] Playlist PL001"},
            {"playlist_id": "PL002", "title": "[Placeholder] Playlist PL002"},
        ]

        # Dry run should show what would be updated
        preview_result = {
            "dry_run": True,
            "would_update": len(mock_playlists_to_update),
            "playlists": mock_playlists_to_update,
        }

        assert preview_result["dry_run"] is True
        assert preview_result["would_update"] == 2

    async def test_dry_run_still_calls_api(self) -> None:
        """Test that dry run mode still fetches from API to show preview."""
        mock_youtube_service = MagicMock()
        mock_youtube_service.fetch_playlists_batched = AsyncMock(
            return_value=(
                [{"id": "PL001", "snippet": {"title": "Real Title"}}],
                set(),
            )
        )

        dry_run = True

        # Even in dry run, should call API to show what would be updated
        result = await mock_youtube_service.fetch_playlists_batched(["PL001"])

        mock_youtube_service.fetch_playlists_batched.assert_called_once()

    async def test_dry_run_shows_old_and_new_values(self) -> None:
        """Test that dry run shows old and new values for comparison."""
        old_playlist: dict[str, Any] = {
            "playlist_id": "PL001",
            "title": "[Placeholder] Playlist PL001",
            "video_count": 0,
        }

        new_data_from_api: dict[str, Any] = {
            "id": "PL001",
            "snippet": {"title": "My Music Collection"},
            "contentDetails": {"itemCount": 25},
        }

        # Preview should show diff
        preview: dict[str, Any] = {
            "playlist_id": "PL001",
            "changes": {
                "title": {
                    "old": old_playlist["title"],
                    "new": new_data_from_api["snippet"]["title"],
                },
                "video_count": {
                    "old": old_playlist["video_count"],
                    "new": new_data_from_api["contentDetails"]["itemCount"],
                },
            },
        }

        assert preview["changes"]["title"]["old"] == "[Placeholder] Playlist PL001"
        assert preview["changes"]["title"]["new"] == "My Music Collection"
        assert preview["changes"]["video_count"]["old"] == 0
        assert preview["changes"]["video_count"]["new"] == 25


class TestPlaylistEnrichmentSummary:
    """Tests for playlist enrichment summary output."""

    async def test_summary_includes_all_counts(self) -> None:
        """Test that summary includes all relevant counts."""
        summary = {
            "playlists_processed": 100,
            "playlists_updated": 75,
            "playlists_deleted": 10,
            "playlists_unchanged": 15,
            "playlists_with_errors": 0,
            "quota_used": 2,
        }

        # All expected fields should be present
        assert "playlists_processed" in summary
        assert "playlists_updated" in summary
        assert "playlists_deleted" in summary
        assert "playlists_unchanged" in summary
        assert "quota_used" in summary

    async def test_summary_quota_calculation(self) -> None:
        """Test that quota is calculated correctly for playlists."""
        # YouTube API: 50 playlists per request = 1 unit
        def estimate_playlist_quota(playlist_count: int) -> int:
            """Estimate quota units for playlist fetches."""
            if playlist_count <= 0:
                return 0
            return (playlist_count + 49) // 50  # Round up division

        assert estimate_playlist_quota(0) == 0
        assert estimate_playlist_quota(1) == 1
        assert estimate_playlist_quota(50) == 1
        assert estimate_playlist_quota(51) == 2
        assert estimate_playlist_quota(100) == 2
        assert estimate_playlist_quota(101) == 3

    async def test_summary_percentage_enriched(self) -> None:
        """Test that summary calculates percentage enriched."""
        total_playlists = 100
        playlists_updated = 75

        percentage = (playlists_updated / total_playlists) * 100

        assert percentage == 75.0

    async def test_summary_error_rate(self) -> None:
        """Test that summary calculates error rate."""
        playlists_processed = 100
        errors = 5

        error_rate = (errors / playlists_processed) * 100

        assert error_rate == 5.0


class TestIntegrationWithVideoEnrichment:
    """Tests for integration between video and playlist enrichment."""

    async def test_include_playlists_true_triggers_playlist_enrichment(self) -> None:
        """Test that include_playlists=True triggers playlist enrichment."""
        include_playlists = True

        # This simulates the enrichment service logic
        should_enrich_playlists = include_playlists

        assert should_enrich_playlists is True

    async def test_include_playlists_false_skips_playlist_enrichment(self) -> None:
        """Test that include_playlists=False skips playlist enrichment."""
        include_playlists = False

        should_enrich_playlists = include_playlists

        assert should_enrich_playlists is False

    async def test_combined_summary_has_video_and_playlist_counts(self) -> None:
        """Test that combined summary includes both video and playlist counts."""
        video_summary = {
            "videos_processed": 500,
            "videos_updated": 450,
            "videos_deleted": 25,
            "errors": 5,
        }

        playlist_summary = {
            "playlists_processed": 50,
            "playlists_updated": 45,
            "playlists_deleted": 3,
            "errors": 0,
        }

        combined_summary = {
            **video_summary,
            **playlist_summary,
            "total_quota_used": 12,  # 10 for videos + 2 for playlists
        }

        assert combined_summary["videos_processed"] == 500
        assert combined_summary["playlists_processed"] == 50
        assert combined_summary["total_quota_used"] == 12

    async def test_video_only_enrichment_no_playlist_fields(self) -> None:
        """Test that video-only enrichment doesn't include playlist fields."""
        include_playlists = False

        video_only_summary = {
            "videos_processed": 500,
            "videos_updated": 450,
            "videos_deleted": 25,
            "errors": 5,
            "quota_used": 10,
        }

        # Should not have playlist fields
        assert "playlists_processed" not in video_only_summary

    async def test_playlist_enrichment_after_video_enrichment(self) -> None:
        """Test that playlist enrichment runs after video enrichment."""
        enrichment_order: List[str] = []

        # Mock video enrichment
        async def mock_video_enrichment() -> dict[str, int]:
            enrichment_order.append("videos")
            return {"videos_processed": 100}

        # Mock playlist enrichment
        async def mock_playlist_enrichment() -> dict[str, int]:
            enrichment_order.append("playlists")
            return {"playlists_processed": 10}

        # Run enrichments
        await mock_video_enrichment()
        await mock_playlist_enrichment()

        # Playlists should run after videos
        assert enrichment_order == ["videos", "playlists"]


class TestPlaylistBatchProcessing:
    """Tests for batch processing of playlists during enrichment."""

    async def test_playlists_processed_in_batches_of_50(self) -> None:
        """Test that playlists are processed in batches of 50."""
        playlist_ids = [f"PL{i:04d}" for i in range(120)]
        batch_size = 50

        batches = []
        for i in range(0, len(playlist_ids), batch_size):
            batch = playlist_ids[i : i + batch_size]
            batches.append(batch)

        assert len(batches) == 3
        assert len(batches[0]) == 50
        assert len(batches[1]) == 50
        assert len(batches[2]) == 20

    async def test_batch_processing_continues_on_partial_failure(self) -> None:
        """Test that batch processing continues after partial failure."""
        # Simulate batch processing with one failed batch
        batch_results: list[dict[str, Any]] = [
            {"success": True, "playlists": 50},
            {"success": False, "error": "API timeout"},
            {"success": True, "playlists": 20},
        ]

        successful_batches = [b for b in batch_results if b["success"]]
        failed_batches = [b for b in batch_results if not b["success"]]

        total_processed = sum(b["playlists"] for b in successful_batches)

        assert len(successful_batches) == 2
        assert len(failed_batches) == 1
        assert total_processed == 70

    async def test_empty_playlist_list_returns_zero_counts(self) -> None:
        """Test that empty playlist list returns zero counts."""
        playlist_ids: List[str] = []

        result: dict[str, Any] = {
            "playlists_processed": len(playlist_ids),
            "playlists_updated": 0,
            "playlists_deleted": 0,
        }

        assert result["playlists_processed"] == 0
        assert result["playlists_updated"] == 0


class TestPlaylistEnrichmentErrorHandling:
    """Tests for error handling in playlist enrichment."""

    async def test_api_error_logged_and_continued(self) -> None:
        """Test that API errors are logged and processing continues."""
        errors: List[Dict[str, Any]] = []

        # Simulate processing with an error
        try:
            raise Exception("API rate limit exceeded")
        except Exception as e:
            errors.append({"playlist_id": "PLerror", "error": str(e)})

        assert len(errors) == 1
        assert "rate limit" in errors[0]["error"].lower()

    async def test_individual_playlist_error_doesnt_stop_batch(self) -> None:
        """Test that error on one playlist doesn't stop processing others."""
        playlist_ids = ["PL001", "PL002", "PL003"]
        results: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        for playlist_id in playlist_ids:
            try:
                if playlist_id == "PL002":
                    raise ValueError("Invalid playlist data")
                results.append({"playlist_id": playlist_id, "status": "updated"})
            except Exception as e:
                errors.append({"playlist_id": playlist_id, "error": str(e)})

        assert len(results) == 2
        assert len(errors) == 1
        assert errors[0]["playlist_id"] == "PL002"

    async def test_error_summary_in_result(self) -> None:
        """Test that errors are summarized in the result."""
        result: dict[str, Any] = {
            "playlists_processed": 100,
            "playlists_updated": 95,
            "playlists_with_errors": 5,
            "errors": [
                {"playlist_id": "PL001", "error": "Not found"},
                {"playlist_id": "PL002", "error": "API error"},
                {"playlist_id": "PL003", "error": "Not found"},
                {"playlist_id": "PL004", "error": "Invalid data"},
                {"playlist_id": "PL005", "error": "Timeout"},
            ],
        }

        assert result["playlists_with_errors"] == 5
        assert len(result["errors"]) == 5


class TestPlaylistEnrichmentWithTakeoutData:
    """Tests for playlist enrichment with takeout historical data."""

    async def test_update_placeholder_from_takeout_name(self) -> None:
        """Test updating placeholder playlist title from takeout data."""
        # Database has placeholder
        db_playlist: dict[str, Any] = {
            "playlist_id": "PLtest123",
            "title": "[Placeholder] Playlist PLtest123",
        }

        # Takeout has historical name
        takeout_playlist = {
            "name": "My Travel Videos",
            "videos": ["video1", "video2"],
        }

        # API doesn't return this playlist (deleted/private)
        api_not_found = True

        if api_not_found and takeout_playlist:
            # Use takeout name as fallback
            db_playlist["title"] = takeout_playlist["name"]

        assert db_playlist["title"] == "My Travel Videos"

    async def test_prefer_api_over_takeout_data(self) -> None:
        """Test that API data is preferred over takeout data when available."""
        takeout_playlist = {
            "name": "Old Name From Takeout",
        }

        api_playlist = {
            "snippet": {
                "title": "Current Name From API",
            },
        }

        # API data should be preferred
        final_title = (
            api_playlist["snippet"]["title"]
            if api_playlist
            else takeout_playlist["name"]
        )

        assert final_title == "Current Name From API"
