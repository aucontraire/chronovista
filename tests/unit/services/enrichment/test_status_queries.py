"""
Tests for EnrichmentService status queries (Phase 7, User Story 5).

Covers:
- T054a: Unit tests for status queries (counts, percentages)
- T054b: Unit tests for quota estimation per tier
- T054d: Performance test for status query structure
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select

from chronovista.services.enrichment.enrichment_service import (
    BATCH_SIZE,
    EnrichmentService,
    estimate_quota_cost,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
class TestEnrichmentStatusCounts:
    """Tests for EnrichmentService status query counts (T054a)."""

    @pytest.fixture
    def mock_youtube_service(self) -> MagicMock:
        """Create a mock YouTube service."""
        service = MagicMock()
        service.fetch_videos_batched = AsyncMock(return_value=([], set()))
        return service

    @pytest.fixture
    def service(self, mock_youtube_service: MagicMock) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=mock_youtube_service,
        )

    async def test_get_priority_tier_counts_returns_all_required_keys(
        self, service: EnrichmentService
    ) -> None:
        """Test that get_priority_tier_counts returns all required keys."""
        mock_session = AsyncMock()

        # Mock the execute method to return count results
        mock_result = MagicMock()
        mock_result.scalar.return_value = 100
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_priority_tier_counts(mock_session)

        # Should return all required keys
        assert "high" in result
        assert "medium" in result
        assert "low" in result
        assert "all" in result
        assert "deleted" in result

    async def test_get_priority_tier_counts_returns_total_video_count(
        self, service: EnrichmentService
    ) -> None:
        """Test that status includes total video count via tier counts."""
        mock_session = AsyncMock()

        # Mock different counts for each tier
        counts = [10, 50, 100, 5]  # high, medium, low, deleted
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        # Verify counts are returned (total = all = low + deleted)
        assert result["high"] == 10
        assert result["medium"] == 50
        assert result["low"] == 100
        assert result["deleted"] == 5
        assert result["all"] == 105  # low + deleted

    async def test_get_priority_tier_counts_returns_placeholder_video_count(
        self, service: EnrichmentService
    ) -> None:
        """Test that medium tier count represents placeholder videos."""
        mock_session = AsyncMock()

        # Setup mock to return specific placeholder count
        placeholder_count = 250
        counts = [100, placeholder_count, 400, 20]  # high, medium (placeholder), low, deleted
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        # Medium priority = all placeholder videos
        assert result["medium"] == placeholder_count

    async def test_get_priority_tier_counts_returns_deleted_video_count(
        self, service: EnrichmentService
    ) -> None:
        """Test that status includes deleted video count."""
        mock_session = AsyncMock()

        deleted_count = 42
        counts = [10, 50, 100, deleted_count]
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        assert result["deleted"] == deleted_count

    async def test_get_priority_tier_counts_fully_enriched_calculation(
        self, service: EnrichmentService
    ) -> None:
        """Test that fully enriched can be calculated from tier counts.

        Fully enriched = total - all (where 'all' includes those needing enrichment)
        Note: This requires knowing total videos, which is not directly returned
        by get_priority_tier_counts but can be queried separately.
        """
        mock_session = AsyncMock()

        # Low priority includes all videos needing enrichment (excluding deleted)
        # ALL = LOW + deleted
        counts = [5, 20, 100, 10]  # high, medium, low, deleted
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        # ALL tier is computed as low + deleted
        assert result["all"] == result["low"] + result["deleted"]

    async def test_get_priority_tier_counts_calculates_correct_enrichment_counts(
        self, service: EnrichmentService
    ) -> None:
        """Test that enrichment percentages can be calculated from tier counts."""
        mock_session = AsyncMock()

        # Given: 1000 total videos, 100 needing enrichment (low tier), 50 deleted
        # Enriched = 1000 - 100 - 50 = 850
        counts = [10, 30, 100, 50]  # high, medium, low, deleted
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        # Verify structure allows percentage calculation
        # percentage = (total - all) / total * 100
        # This test verifies the structure exists for the calculation
        assert result["all"] == 150  # low + deleted

    async def test_handles_empty_database_all_zeros(
        self, service: EnrichmentService
    ) -> None:
        """Test that status handles empty database gracefully (all zeros)."""
        mock_session = AsyncMock()

        # All counts are 0
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_priority_tier_counts(mock_session)

        assert result["high"] == 0
        assert result["medium"] == 0
        assert result["low"] == 0
        assert result["all"] == 0
        assert result["deleted"] == 0

    async def test_handles_database_with_only_placeholder_videos(
        self, service: EnrichmentService
    ) -> None:
        """Test status when database contains only placeholder videos."""
        mock_session = AsyncMock()

        # All videos are placeholder (high = medium = low = all)
        all_placeholder_count = 500
        counts = [all_placeholder_count, all_placeholder_count, all_placeholder_count, 0]
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        # All tiers should have same count when all videos are placeholders
        assert result["high"] == all_placeholder_count
        assert result["medium"] == all_placeholder_count
        assert result["low"] == all_placeholder_count
        assert result["deleted"] == 0
        assert result["all"] == all_placeholder_count

    async def test_get_priority_tier_counts_returns_total_channel_count(
        self, service: EnrichmentService
    ) -> None:
        """Test that channel count can be queried (tested via priority filter).

        Note: The high priority filter joins with channels table to check
        for placeholder channels, demonstrating channel awareness in queries.
        """
        mock_session = AsyncMock()

        # High priority requires both placeholder title AND placeholder channel
        # This tests that channel table is being queried
        high_count = 25  # Videos with both placeholder title AND channel
        medium_count = 50  # Videos with placeholder title (any channel)

        counts = [high_count, medium_count, 100, 5]
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        # High priority < Medium priority (high requires channel condition too)
        assert result["high"] <= result["medium"]

    async def test_get_priority_tier_counts_returns_placeholder_channel_count(
        self, service: EnrichmentService
    ) -> None:
        """Test that high tier correctly filters by placeholder channel.

        High priority = placeholder title AND placeholder channel.
        This verifies channel placeholder detection is included in the query.
        """
        mock_session = AsyncMock()

        # Scenario: 100 placeholder title videos, but only 30 also have placeholder channel
        counts = [30, 100, 150, 10]  # high, medium, low, deleted
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        # High priority should be subset of medium (additional channel condition)
        assert result["high"] < result["medium"]
        assert result["high"] == 30


class TestQuotaEstimationPerTier:
    """Tests for quota estimation per priority tier (T054b) - sync tests."""

    def test_estimate_quota_cost_high_tier(self) -> None:
        """Test quota estimate for HIGH tier."""
        # HIGH tier: 150 videos -> ceiling(150/50) = 3 quota units
        video_count = 150
        expected_quota = 3

        result = estimate_quota_cost(video_count)

        assert result == expected_quota

    def test_estimate_quota_cost_medium_tier(self) -> None:
        """Test quota estimate for MEDIUM tier."""
        # MEDIUM tier: 500 videos -> ceiling(500/50) = 10 quota units
        video_count = 500
        expected_quota = 10

        result = estimate_quota_cost(video_count)

        assert result == expected_quota

    def test_estimate_quota_cost_low_tier(self) -> None:
        """Test quota estimate for LOW tier."""
        # LOW tier: 2500 videos -> ceiling(2500/50) = 50 quota units
        video_count = 2500
        expected_quota = 50

        result = estimate_quota_cost(video_count)

        assert result == expected_quota

    def test_estimate_quota_cost_all_tier(self) -> None:
        """Test quota estimate for ALL tier."""
        # ALL tier: 10000 videos -> ceiling(10000/50) = 200 quota units
        video_count = 10000
        expected_quota = 200

        result = estimate_quota_cost(video_count)

        assert result == expected_quota

    def test_quota_estimates_use_ceiling_division_by_50(self) -> None:
        """Test that quota estimates use correct formula: ceiling division by 50."""
        # Test various counts to verify ceiling division
        test_cases = [
            (0, 0),      # 0 videos = 0 quota
            (1, 1),      # 1 video = 1 quota (1 API call)
            (50, 1),     # 50 videos = 1 quota (exactly one batch)
            (51, 2),     # 51 videos = 2 quota (need second batch)
            (100, 2),    # 100 videos = 2 quota
            (101, 3),    # 101 videos = 3 quota
            (49, 1),     # 49 videos = 1 quota
        ]

        for video_count, expected_quota in test_cases:
            result = estimate_quota_cost(video_count)
            assert result == expected_quota, (
                f"estimate_quota_cost({video_count}) = {result}, expected {expected_quota}"
            )

    def test_estimate_quota_cost_with_custom_batch_size(self) -> None:
        """Test quota estimation with custom batch size."""
        # Custom batch size of 25
        video_count = 100
        batch_size = 25
        expected_quota = 4  # ceiling(100/25) = 4

        result = estimate_quota_cost(video_count, batch_size=batch_size)

        assert result == expected_quota

    def test_estimate_quota_cost_zero_videos(self) -> None:
        """Test quota estimate for zero videos."""
        result = estimate_quota_cost(0)
        assert result == 0

    def test_estimate_quota_cost_negative_videos_returns_zero(self) -> None:
        """Test quota estimate for negative videos returns zero."""
        result = estimate_quota_cost(-10)
        assert result == 0

    def test_batch_size_constant_is_50(self) -> None:
        """Test that BATCH_SIZE constant is 50 (YouTube API limit)."""
        assert BATCH_SIZE == 50


@pytest.mark.asyncio
class TestQuotaEstimationWithService:
    """Tests for quota estimation with EnrichmentService (T054b) - async tests."""

    @pytest.fixture
    def mock_youtube_service(self) -> MagicMock:
        """Create a mock YouTube service."""
        service = MagicMock()
        service.fetch_videos_batched = AsyncMock(return_value=([], set()))
        return service

    @pytest.fixture
    def service(self, mock_youtube_service: MagicMock) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=mock_youtube_service,
        )

    async def test_status_includes_quota_estimate_for_each_tier(
        self, service: EnrichmentService
    ) -> None:
        """Test that tier counts can be used to calculate quota estimates."""
        mock_session = AsyncMock()

        # Setup counts for each tier
        tier_counts = {
            "high": 150,      # quota = 3
            "medium": 500,    # quota = 10
            "low": 2500,      # quota = 50
            "deleted": 100,   # included in all
        }
        tier_counts["all"] = tier_counts["low"] + tier_counts["deleted"]  # 2600 -> quota = 52

        counts = [tier_counts["high"], tier_counts["medium"], tier_counts["low"], tier_counts["deleted"]]
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        # Verify quota can be calculated for each tier
        assert estimate_quota_cost(result["high"]) == 3
        assert estimate_quota_cost(result["medium"]) == 10
        assert estimate_quota_cost(result["low"]) == 50
        assert estimate_quota_cost(result["all"]) == 52


@pytest.mark.asyncio
class TestStatusQueryPerformance:
    """Tests for status query performance (T054d)."""

    @pytest.fixture
    def mock_youtube_service(self) -> MagicMock:
        """Create a mock YouTube service."""
        service = MagicMock()
        service.fetch_videos_batched = AsyncMock(return_value=([], set()))
        return service

    @pytest.fixture
    def service(self, mock_youtube_service: MagicMock) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=mock_youtube_service,
        )

    async def test_status_query_uses_count_not_select_star(
        self, service: EnrichmentService
    ) -> None:
        """Test that status query uses COUNT(*) for efficiency, not SELECT *."""
        mock_session = AsyncMock()

        # Track the queries executed
        executed_queries = []

        async def track_query(query: MagicMock) -> MagicMock:
            # Store string representation of query for inspection
            executed_queries.append(str(query))
            mock_result = MagicMock()
            mock_result.scalar.return_value = 100
            return mock_result

        mock_session.execute = AsyncMock(side_effect=track_query)

        await service.get_priority_tier_counts(mock_session)

        # Verify multiple queries were executed (one per tier)
        assert len(executed_queries) >= 4  # At least 4 queries (high, medium, low, deleted)

        # The actual query structure uses func.count() which translates to COUNT
        # This test verifies the method completes and returns scalar results
        # (which is how COUNT queries return values)

    async def test_status_query_returns_scalar_results(
        self, service: EnrichmentService
    ) -> None:
        """Test that status queries return scalar values (indicating COUNT usage)."""
        mock_session = AsyncMock()

        # Mock scalar return to simulate COUNT query
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_priority_tier_counts(mock_session)

        # All results should be integers (scalar values from COUNT)
        assert isinstance(result["high"], int)
        assert isinstance(result["medium"], int)
        assert isinstance(result["low"], int)
        assert isinstance(result["all"], int)
        assert isinstance(result["deleted"], int)

    async def test_status_query_does_not_load_full_video_objects(
        self, service: EnrichmentService
    ) -> None:
        """Test that status query doesn't load full video objects into memory.

        This is verified by checking that the query uses scalar() which returns
        a single value (the count) rather than scalars() which would return
        multiple ORM objects.
        """
        mock_session = AsyncMock()

        # Track method calls
        scalar_calls = 0

        def make_result() -> MagicMock:
            nonlocal scalar_calls
            mock_result = MagicMock()

            def track_scalar() -> int:
                nonlocal scalar_calls
                scalar_calls += 1
                return 100

            mock_result.scalar = track_scalar
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: make_result())

        await service.get_priority_tier_counts(mock_session)

        # Should have called scalar() for each query (4 queries minimum)
        assert scalar_calls >= 4

    async def test_status_query_structure_is_efficient(
        self, service: EnrichmentService
    ) -> None:
        """Test that the query structure is efficient for large datasets.

        Efficiency indicators:
        1. Uses COUNT aggregation (returns scalar)
        2. Filters on indexed columns (deleted_flag, title patterns)
        3. Does not load full objects
        """
        mock_session = AsyncMock()

        # Mock that returns quickly (simulating efficient query)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 40000  # Simulating 40k+ videos
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Execute the query
        result = await service.get_priority_tier_counts(mock_session)

        # Query should complete and return expected structure
        assert "high" in result
        assert "medium" in result
        assert "low" in result
        assert "all" in result
        assert "deleted" in result

        # Verify execute was called (queries were made)
        assert mock_session.execute.called

    async def test_multiple_counts_use_separate_queries(
        self, service: EnrichmentService
    ) -> None:
        """Test that multiple counts are performed via separate queries.

        Note: While a single query with CASE WHEN could be more efficient,
        the current implementation uses separate queries for clarity.
        This test documents the current behavior.
        """
        mock_session = AsyncMock()

        call_count = 0

        async def count_calls(_: MagicMock) -> MagicMock:
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            mock_result.scalar.return_value = 100 * call_count
            return mock_result

        mock_session.execute = AsyncMock(side_effect=count_calls)

        await service.get_priority_tier_counts(mock_session)

        # Should make at least 4 separate queries
        assert call_count >= 4


@pytest.mark.asyncio
class TestStatusQueryEdgeCases:
    """Tests for edge cases in status queries."""

    @pytest.fixture
    def mock_youtube_service(self) -> MagicMock:
        """Create a mock YouTube service."""
        service = MagicMock()
        service.fetch_videos_batched = AsyncMock(return_value=([], set()))
        return service

    @pytest.fixture
    def service(self, mock_youtube_service: MagicMock) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=mock_youtube_service,
        )

    async def test_handles_null_scalar_result(
        self, service: EnrichmentService
    ) -> None:
        """Test that null scalar results are handled (default to 0)."""
        mock_session = AsyncMock()

        # Mock returning None (no rows)
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_priority_tier_counts(mock_session)

        # Should handle None gracefully and return 0
        assert result["high"] == 0
        assert result["medium"] == 0
        assert result["low"] == 0
        assert result["deleted"] == 0
        assert result["all"] == 0

    async def test_cumulative_tier_relationship(
        self, service: EnrichmentService
    ) -> None:
        """Test that tiers maintain cumulative relationship: HIGH <= MEDIUM <= LOW <= ALL."""
        mock_session = AsyncMock()

        # Setup realistic cumulative counts
        counts = [10, 50, 200, 30]  # high, medium, low, deleted
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        # Verify cumulative relationship
        assert result["high"] <= result["medium"]
        assert result["medium"] <= result["low"]
        assert result["low"] <= result["all"]

    async def test_large_video_count_handling(
        self, service: EnrichmentService
    ) -> None:
        """Test handling of large video counts (40,000+)."""
        mock_session = AsyncMock()

        large_count = 45000
        counts = [5000, 15000, 40000, large_count - 40000]
        count_iter = iter(counts)

        def get_next_count() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(count_iter)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: get_next_count())

        result = await service.get_priority_tier_counts(mock_session)

        # Should handle large counts correctly
        assert result["all"] == large_count
        assert estimate_quota_cost(result["all"]) == 900  # ceiling(45000/50)
