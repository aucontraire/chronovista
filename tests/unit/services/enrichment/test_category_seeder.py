"""
Unit tests for CategorySeeder - YouTube video category seeding.

Tests cover:
- Default regions list (7 regions: US, GB, JP, DE, BR, IN, MX)
- API response transformation
- Quota tracking (1 unit per region)
- Multi-region merging (deduplication)
- Idempotent seeding behavior
- Force mode (delete and re-seed)
- Graceful degradation on regional failures
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.models.video_category import VideoCategoryCreate
from chronovista.repositories.video_category_repository import VideoCategoryRepository
from chronovista.services.enrichment.seeders import CategorySeeder, CategorySeedResult
from chronovista.services.youtube_service import YouTubeService

pytestmark = pytest.mark.asyncio


class TestCategorySeederConstants:
    """Test CategorySeeder constants and class methods."""

    def test_default_regions_count(self) -> None:
        """Test that there are 7 default regions."""
        assert len(CategorySeeder.DEFAULT_REGIONS) == 7

    def test_default_regions_list(self) -> None:
        """Test default regions match expected list."""
        expected_regions = ["US", "GB", "JP", "DE", "BR", "IN", "MX"]
        assert CategorySeeder.DEFAULT_REGIONS == expected_regions

    def test_get_default_region_count(self) -> None:
        """Test class method for getting default region count."""
        assert CategorySeeder.get_default_region_count() == 7

    def test_get_expected_quota_cost_default(self) -> None:
        """Test expected quota cost for default regions (1 per region)."""
        quota_cost = CategorySeeder.get_expected_quota_cost()
        assert quota_cost == 7, "Should be 1 quota unit per region"

    def test_get_expected_quota_cost_custom_regions(self) -> None:
        """Test expected quota cost for custom regions."""
        custom_regions = ["US", "GB", "FR"]
        quota_cost = CategorySeeder.get_expected_quota_cost(custom_regions)
        assert quota_cost == 3


class TestCategorySeederInitialization:
    """Test CategorySeeder initialization."""

    def test_seeder_initialization(self) -> None:
        """Test CategorySeeder can be initialized with dependencies."""
        mock_repo = MagicMock(spec=VideoCategoryRepository)
        mock_youtube = MagicMock(spec=YouTubeService)

        seeder = CategorySeeder(
            category_repository=mock_repo,
            youtube_service=mock_youtube
        )

        assert seeder.category_repository == mock_repo
        assert seeder.youtube_service == mock_youtube


class TestCategorySeederAPITransformation:
    """Test API response transformation."""

    def test_transform_valid_api_response(self) -> None:
        """Test transforming valid API response to VideoCategoryCreate."""
        mock_repo = MagicMock(spec=VideoCategoryRepository)
        mock_youtube = MagicMock(spec=YouTubeService)
        seeder = CategorySeeder(mock_repo, mock_youtube)

        api_item = {
            "id": "10",
            "snippet": {
                "title": "Music",
                "assignable": True
            }
        }

        category = seeder._transform_api_response_to_category(api_item)

        assert category is not None
        assert category.category_id == "10"
        assert category.name == "Music"
        assert category.assignable is True

    def test_transform_api_response_non_assignable(self) -> None:
        """Test transforming API response with assignable=False."""
        mock_repo = MagicMock(spec=VideoCategoryRepository)
        mock_youtube = MagicMock(spec=YouTubeService)
        seeder = CategorySeeder(mock_repo, mock_youtube)

        api_item = {
            "id": "29",
            "snippet": {
                "title": "Nonprofits & Activism",
                "assignable": False
            }
        }

        category = seeder._transform_api_response_to_category(api_item)

        assert category is not None
        assert category.assignable is False

    def test_transform_api_response_default_assignable(self) -> None:
        """Test that assignable defaults to True if not provided."""
        mock_repo = MagicMock(spec=VideoCategoryRepository)
        mock_youtube = MagicMock(spec=YouTubeService)
        seeder = CategorySeeder(mock_repo, mock_youtube)

        api_item = {
            "id": "10",
            "snippet": {
                "title": "Music"
                # No assignable field
            }
        }

        category = seeder._transform_api_response_to_category(api_item)

        assert category is not None
        assert category.assignable is True

    def test_transform_api_response_missing_id(self) -> None:
        """Test that transformation returns None for missing ID."""
        mock_repo = MagicMock(spec=VideoCategoryRepository)
        mock_youtube = MagicMock(spec=YouTubeService)
        seeder = CategorySeeder(mock_repo, mock_youtube)

        api_item = {
            "snippet": {
                "title": "Music",
                "assignable": True
            }
        }

        category = seeder._transform_api_response_to_category(api_item)
        assert category is None

    def test_transform_api_response_missing_title(self) -> None:
        """Test that transformation returns None for missing title."""
        mock_repo = MagicMock(spec=VideoCategoryRepository)
        mock_youtube = MagicMock(spec=YouTubeService)
        seeder = CategorySeeder(mock_repo, mock_youtube)

        api_item = {
            "id": "10",
            "snippet": {
                "assignable": True
            }
        }

        category = seeder._transform_api_response_to_category(api_item)
        assert category is None

    def test_transform_api_response_malformed_data(self) -> None:
        """Test that transformation handles malformed data gracefully."""
        mock_repo = MagicMock(spec=VideoCategoryRepository)
        mock_youtube = MagicMock(spec=YouTubeService)
        seeder = CategorySeeder(mock_repo, mock_youtube)

        api_item = {"invalid": "structure"}

        category = seeder._transform_api_response_to_category(api_item)
        assert category is None


class TestCategorySeederSeeding:
    """Test CategorySeeder seeding operations."""

    async def test_seed_fetches_from_all_default_regions(self) -> None:
        """Test that seeding fetches categories from all 7 default regions."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # Mock API to return empty list
        mock_youtube.get_video_categories = AsyncMock(return_value=[])
        mock_repo.exists = AsyncMock(return_value=False)

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session)

        # Verify API was called 7 times (once per default region)
        assert mock_youtube.get_video_categories.call_count == 7

        # Verify quota tracking
        assert result.quota_used == 7

    async def test_seed_custom_regions(self) -> None:
        """Test seeding with custom regions list."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        custom_regions = ["US", "GB", "FR"]
        mock_youtube.get_video_categories = AsyncMock(return_value=[])
        mock_repo.exists = AsyncMock(return_value=False)

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=custom_regions)

        # Verify API was called 3 times
        assert mock_youtube.get_video_categories.call_count == 3
        assert result.quota_used == 3

    async def test_seed_merges_categories_from_multiple_regions(self) -> None:
        """Test that categories are merged across regions (deduplication)."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # Mock API to return overlapping categories
        us_categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
            {"id": "20", "snippet": {"title": "Gaming", "assignable": True}},
        ]
        gb_categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},  # Duplicate
            {"id": "24", "snippet": {"title": "Entertainment", "assignable": True}},
        ]

        async def get_categories_side_effect(region_code: str):
            if region_code == "US":
                return us_categories
            elif region_code == "GB":
                return gb_categories
            return []

        mock_youtube.get_video_categories = AsyncMock(side_effect=get_categories_side_effect)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US", "GB"])

        # Should create only 3 unique categories (10, 20, 24)
        assert result.created == 3
        assert mock_repo.create_or_update.call_count == 3

    async def test_seed_idempotent_skips_existing(self) -> None:
        """Test idempotent seeding skips existing categories."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)

        # Mock all categories as existing
        mock_repo.exists = AsyncMock(return_value=True)

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"])

        assert result.created == 0
        assert result.skipped == 1

    async def test_seed_force_mode_deletes_all(self) -> None:
        """Test force mode deletes all categories before re-seeding."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # Mock existing categories
        existing_cat1 = MagicMock(category_id="10")
        existing_cat2 = MagicMock(category_id="20")
        mock_repo.get_all = AsyncMock(return_value=[existing_cat1, existing_cat2])
        mock_repo.delete_by_category_id = AsyncMock()

        # Mock API response
        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"], force=True)

        # Verify deletion
        assert result.deleted == 2
        assert mock_repo.delete_by_category_id.call_count == 2

        # Verify re-creation
        assert result.created == 1

    async def test_seed_graceful_degradation_on_regional_failure(self) -> None:
        """Test that regional API failures don't stop entire seeding (FR-052)."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # Mock API to fail for one region
        async def get_categories_side_effect(region_code: str):
            if region_code == "US":
                return [{"id": "10", "snippet": {"title": "Music", "assignable": True}}]
            elif region_code == "GB":
                raise ValueError("API error for GB")
            return []

        mock_youtube.get_video_categories = AsyncMock(side_effect=get_categories_side_effect)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US", "GB"])

        # Should still create categories from successful region
        assert result.created == 1
        assert len(result.errors) == 1
        assert "GB" in result.errors[0]

    async def test_seed_handles_creation_errors(self) -> None:
        """Test that individual category creation errors are tracked."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
            {"id": "20", "snippet": {"title": "Gaming", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)
        mock_repo.exists = AsyncMock(return_value=False)

        # Mock create to fail for second category
        call_count = 0
        async def create_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Database error")

        mock_repo.create_or_update = AsyncMock(side_effect=create_side_effect)

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"])

        assert result.created == 1
        assert result.failed == 1
        assert len(result.errors) == 1

    async def test_seed_rollback_on_exception(self) -> None:
        """Test that session rollback occurs on catastrophic failure."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # Mock commit to fail
        mock_session.commit = AsyncMock(side_effect=Exception("Commit failed"))
        mock_youtube.get_video_categories = AsyncMock(return_value=[])

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session)

        # Verify rollback was called
        mock_session.rollback.assert_called_once()
        assert result.failed > 0


class TestCategorySeederQuotaTracking:
    """Test quota tracking functionality."""

    async def test_quota_tracking_increments_per_region(self) -> None:
        """Test that quota is incremented once per region API call."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        mock_youtube.get_video_categories = AsyncMock(return_value=[])
        mock_repo.exists = AsyncMock(return_value=False)

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US", "GB", "JP"])

        assert result.quota_used == 3

    async def test_quota_not_incremented_on_api_failure(self) -> None:
        """Test quota tracking when API calls fail."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # Mock API to fail for one region
        async def get_categories_side_effect(region_code: str):
            if region_code == "US":
                return []
            raise ValueError("API error")

        mock_youtube.get_video_categories = AsyncMock(side_effect=get_categories_side_effect)
        mock_repo.exists = AsyncMock(return_value=False)

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US", "GB"])

        # Only successful API call should count
        assert result.quota_used == 1


class TestCategorySeederUtilityMethods:
    """Test utility methods."""

    async def test_get_category_count(self) -> None:
        """Test retrieving current category count from database."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # Mock get_all to return 30 categories
        mock_categories = [MagicMock() for _ in range(30)]
        mock_repo.get_all = AsyncMock(return_value=mock_categories)

        seeder = CategorySeeder(mock_repo, mock_youtube)
        count = await seeder.get_category_count(mock_session)

        assert count == 30


class TestCategorySeedResult:
    """Test CategorySeedResult model."""

    def test_seed_result_creation(self) -> None:
        """Test basic CategorySeedResult creation."""
        result = CategorySeedResult(
            created=25,
            skipped=5,
            deleted=0,
            failed=0,
            duration_seconds=10.5,
            quota_used=7
        )

        assert result.created == 25
        assert result.skipped == 5
        assert result.deleted == 0
        assert result.failed == 0
        assert result.duration_seconds == 10.5
        assert result.quota_used == 7
        assert result.errors == []

    def test_seed_result_total_processed(self) -> None:
        """Test total_processed property calculation."""
        result = CategorySeedResult(created=25, skipped=5, failed=0)
        assert result.total_processed == 30

    def test_seed_result_success_rate_perfect(self) -> None:
        """Test success rate with 100% success."""
        result = CategorySeedResult(created=25, skipped=5, failed=0)
        assert result.success_rate == 100.0

    def test_seed_result_success_rate_partial(self) -> None:
        """Test success rate with failures."""
        result = CategorySeedResult(created=25, skipped=3, failed=2)
        # (25 + 3) / (25 + 3 + 2) = 28/30 ≈ 93.33%
        assert abs(result.success_rate - 93.33) < 0.01

    def test_seed_result_with_errors(self) -> None:
        """Test CategorySeedResult with error messages."""
        errors = ["Region US failed", "Region GB failed"]
        result = CategorySeedResult(created=20, failed=2, quota_used=5, errors=errors)

        assert result.errors == errors
        assert len(result.errors) == 2
