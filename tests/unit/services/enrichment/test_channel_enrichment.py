"""
Tests for EnrichmentService channel enrichment functionality.

Covers T023-T034: Channel enrichment method, batch processing, progress tracking,
dry-run mode, limit parameter, shutdown handling, error isolation, and field extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.models.api_responses import (
    ChannelSnippet,
    ChannelStatisticsResponse,
    YouTubeChannelResponse,
)
from chronovista.services.enrichment.enrichment_service import (
    BATCH_SIZE,
    ChannelEnrichmentResult,
    EnrichmentService,
)

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


def make_channel_response(
    channel_id: str,
    title: str = "Test Channel",
    description: str = "Test description",
    country: str | None = None,
    default_language: str | None = None,
    subscriber_count: int | None = 1000,
    video_count: int | None = 100,
    view_count: int | None = 50000,
    custom_url: str | None = None,
    **kwargs: Any,
) -> YouTubeChannelResponse:
    """
    Create a YouTubeChannelResponse for testing.

    Parameters
    ----------
    channel_id : str
        YouTube channel ID.
    title : str
        Channel title.
    description : str
        Channel description.
    country : str | None
        Country code.
    default_language : str | None
        Default language code.
    subscriber_count : int | None
        Subscriber count.
    video_count : int | None
        Video count.
    view_count : int | None
        Total view count.
    custom_url : str | None
        Custom URL handle.
    **kwargs : Any
        Additional fields to pass.

    Returns
    -------
    YouTubeChannelResponse
        A valid Pydantic model instance.
    """
    snippet = ChannelSnippet(
        title=title,
        description=description,
        country=country,
        defaultLanguage=default_language,
        customUrl=custom_url,
        publishedAt=datetime.now(timezone.utc),
    )

    statistics = ChannelStatisticsResponse(
        subscriberCount=subscriber_count,
        videoCount=video_count or 0,
        viewCount=view_count or 0,
        hiddenSubscriberCount=False,
    )

    return YouTubeChannelResponse(
        kind="youtube#channel",
        etag="test_etag",
        id=channel_id,
        snippet=snippet,
        statistics=statistics,
        **kwargs,
    )


class TestChannelEnrichmentResultModel:
    """Tests for ChannelEnrichmentResult Pydantic model."""

    def test_default_values(self) -> None:
        """Test default values for ChannelEnrichmentResult."""
        result = ChannelEnrichmentResult()

        assert result.channels_processed == 0
        assert result.channels_enriched == 0
        assert result.channels_failed == 0
        assert result.channels_skipped == 0
        assert result.batches_processed == 0
        assert result.quota_used == 0
        assert result.duration_seconds == 0.0
        assert result.consecutive_failures == 0
        assert result.network_instability_warning is False
        assert result.was_interrupted is False
        assert result.enriched_channel_ids == []
        assert result.failed_channel_ids == []
        assert result.skipped_channel_ids == []

    def test_with_values(self) -> None:
        """Test ChannelEnrichmentResult with specific values."""
        result = ChannelEnrichmentResult(
            channels_processed=100,
            channels_enriched=90,
            channels_failed=5,
            channels_skipped=5,
            batches_processed=2,
            quota_used=2,
            duration_seconds=15.5,
        )

        assert result.channels_processed == 100
        assert result.channels_enriched == 90
        assert result.channels_failed == 5
        assert result.channels_skipped == 5
        assert result.batches_processed == 2
        assert result.quota_used == 2
        assert result.duration_seconds == 15.5

    def test_verbose_mode_ids(self) -> None:
        """Test ChannelEnrichmentResult with verbose mode channel IDs."""
        result = ChannelEnrichmentResult(
            enriched_channel_ids=["UC1", "UC2", "UC3"],
            failed_channel_ids=["UC4"],
            skipped_channel_ids=["UC5", "UC6"],
        )

        assert len(result.enriched_channel_ids) == 3
        assert len(result.failed_channel_ids) == 1
        assert len(result.skipped_channel_ids) == 2

    def test_timing_fields(self) -> None:
        """Test timing fields on ChannelEnrichmentResult."""
        started = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2024, 1, 15, 12, 5, 30, tzinfo=timezone.utc)

        result = ChannelEnrichmentResult(
            started_at=started,
            completed_at=completed,
            duration_seconds=330.0,
        )

        assert result.started_at == started
        assert result.completed_at == completed
        assert result.duration_seconds == 330.0


class TestExtractChannelUpdate:
    """Tests for _extract_channel_update method (T034)."""

    @pytest.fixture
    def service(self) -> EnrichmentService:
        """Create an EnrichmentService instance."""
        return EnrichmentService(
            video_repository=AsyncMock(),
            channel_repository=AsyncMock(),
            video_tag_repository=AsyncMock(),
            video_topic_repository=AsyncMock(),
            video_category_repository=AsyncMock(),
            topic_category_repository=AsyncMock(),
            youtube_service=AsyncMock(),
        )

    def test_extract_title_and_description(self, service: EnrichmentService) -> None:
        """Test extracting title and description from API response."""
        api_data = make_channel_response(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="RickAstleyVEVO",
            description="Official YouTube channel for Rick Astley",
        )

        update = service._extract_channel_update(api_data)

        assert update["title"] == "RickAstleyVEVO"
        assert "Rick Astley" in update["description"]

    def test_extract_statistics(self, service: EnrichmentService) -> None:
        """Test extracting subscriber/video counts."""
        api_data = make_channel_response(
            channel_id="UCtest",
            subscriber_count=1000000,
            video_count=500,
            view_count=2000000000,
        )

        update = service._extract_channel_update(api_data)

        assert update["subscriber_count"] == 1000000
        assert update["video_count"] == 500
        # Note: view_count is not extracted by the current implementation

    def test_extract_country(self, service: EnrichmentService) -> None:
        """Test extracting country code."""
        api_data = make_channel_response(
            channel_id="UCtest",
            country="US",
        )

        update = service._extract_channel_update(api_data)

        assert update["country"] == "US"

    def test_extract_default_language(self, service: EnrichmentService) -> None:
        """Test extracting default language."""
        api_data = make_channel_response(
            channel_id="UCtest",
            default_language="EN",
        )

        update = service._extract_channel_update(api_data)

        assert update["default_language"] == "en"  # Should be lowercased

    def test_description_truncation(self, service: EnrichmentService) -> None:
        """Test that long descriptions are truncated to 10,000 chars."""
        long_description = "A" * 15000  # Longer than 10k limit

        api_data = make_channel_response(
            channel_id="UCtest",
            description=long_description,
        )

        update = service._extract_channel_update(api_data)

        assert len(update["description"]) == 10000

    def test_missing_statistics(self, service: EnrichmentService) -> None:
        """Test extracting data when statistics is missing."""
        # Create response without statistics
        api_data = YouTubeChannelResponse(
            kind="youtube#channel",
            etag="test_etag",
            id="UCtest",
            snippet=ChannelSnippet(
                title="Test Channel",
                description="Test description",
                publishedAt=datetime.now(timezone.utc),
            ),
            statistics=None,
        )

        update = service._extract_channel_update(api_data)

        # Should still have title and description from snippet
        assert update["title"] == "Test Channel"
        assert "subscriber_count" not in update
        assert "video_count" not in update


class TestEnrichChannels:
    """Tests for enrich_channels method (T023-T033)."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def mock_youtube_service(self) -> AsyncMock:
        """Create a mock YouTube service."""
        service = AsyncMock()
        service.get_channel_details = AsyncMock(return_value=[])
        return service

    @pytest.fixture
    def mock_channel_repo(self) -> AsyncMock:
        """Create a mock channel repository."""
        repo = AsyncMock()
        repo.get_channels_needing_enrichment = AsyncMock(return_value=[])
        repo.get = AsyncMock(return_value=None)
        return repo

    @pytest.fixture
    def service(
        self, mock_youtube_service: AsyncMock, mock_channel_repo: AsyncMock
    ) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=AsyncMock(),
            channel_repository=mock_channel_repo,
            video_tag_repository=AsyncMock(),
            video_topic_repository=AsyncMock(),
            video_category_repository=AsyncMock(),
            topic_category_repository=AsyncMock(),
            youtube_service=mock_youtube_service,
        )

    async def test_no_channels_to_enrich(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test enrichment when no channels need enrichment (T023)."""
        result = await service.enrich_channels(mock_session)

        assert result.channels_processed == 0
        assert result.channels_enriched == 0
        assert result.completed_at is not None
        assert result.duration_seconds >= 0

    async def test_dry_run_mode(
        self,
        service: EnrichmentService,
        mock_session: AsyncMock,
        mock_channel_repo: AsyncMock,
    ) -> None:
        """Test dry-run mode returns count without API calls (T026)."""
        # Setup mock channels
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCtest123"
        mock_channel_repo.get_channels_needing_enrichment.return_value = [mock_channel]

        result = await service.enrich_channels(mock_session, dry_run=True)

        # Should process 1 channel but skip all (dry run)
        assert result.channels_processed == 1
        assert result.channels_skipped == 1
        assert result.channels_enriched == 0
        assert result.quota_used == 0  # No API calls in dry run

    async def test_dry_run_with_verbose(
        self,
        service: EnrichmentService,
        mock_session: AsyncMock,
        mock_channel_repo: AsyncMock,
    ) -> None:
        """Test dry-run mode with verbose tracking (T026)."""
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCtest456"
        mock_channel_repo.get_channels_needing_enrichment.return_value = [mock_channel]

        result = await service.enrich_channels(mock_session, dry_run=True, verbose=True)

        assert result.channels_skipped == 1
        assert "UCtest456" in result.skipped_channel_ids

    async def test_limit_parameter(
        self,
        service: EnrichmentService,
        mock_session: AsyncMock,
        mock_channel_repo: AsyncMock,
    ) -> None:
        """Test that limit parameter is passed to repository (T027)."""
        await service.enrich_channels(mock_session, limit=10)

        # Verify limit was passed to repository
        mock_channel_repo.get_channels_needing_enrichment.assert_called_once()
        call_kwargs = mock_channel_repo.get_channels_needing_enrichment.call_args.kwargs
        assert call_kwargs.get("limit") == 10

    async def test_successful_enrichment(
        self,
        service: EnrichmentService,
        mock_session: AsyncMock,
        mock_channel_repo: AsyncMock,
        mock_youtube_service: AsyncMock,
    ) -> None:
        """Test successful channel enrichment updates database (T023)."""
        # Setup mock channel in database
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"
        mock_channel.title = "[Placeholder] Channel"
        mock_channel_repo.get_channels_needing_enrichment.return_value = [mock_channel]
        mock_channel_repo.get.return_value = mock_channel

        # Setup mock API response
        api_response = make_channel_response(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="RickAstleyVEVO",
            description="Official channel",
        )
        mock_youtube_service.get_channel_details.return_value = [api_response]

        result = await service.enrich_channels(mock_session)

        assert result.channels_processed == 1
        assert result.channels_enriched == 1
        assert result.quota_used == 1  # 1 API call
        assert mock_channel.title == "RickAstleyVEVO"

    async def test_channel_not_found_on_api(
        self,
        service: EnrichmentService,
        mock_session: AsyncMock,
        mock_channel_repo: AsyncMock,
        mock_youtube_service: AsyncMock,
    ) -> None:
        """Test handling when channel is not found on YouTube API."""
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCdeleted123"
        mock_channel_repo.get_channels_needing_enrichment.return_value = [mock_channel]

        # API returns empty list (channel not found)
        mock_youtube_service.get_channel_details.return_value = []

        result = await service.enrich_channels(mock_session)

        assert result.channels_processed == 1
        assert result.channels_skipped == 1
        assert result.channels_enriched == 0

    async def test_batch_processing(
        self,
        service: EnrichmentService,
        mock_session: AsyncMock,
        mock_channel_repo: AsyncMock,
        mock_youtube_service: AsyncMock,
    ) -> None:
        """Test that channels are processed in batches of 50 (T024)."""
        # Create 75 mock channels to test batching
        mock_channels = [
            MagicMock(channel_id=f"UC{i:022d}") for i in range(75)
        ]
        mock_channel_repo.get_channels_needing_enrichment.return_value = mock_channels
        mock_channel_repo.get.return_value = MagicMock()

        # API returns all channels
        mock_youtube_service.get_channel_details.return_value = [
            make_channel_response(f"UC{i:022d}") for i in range(75)
        ]

        result = await service.enrich_channels(mock_session)

        # Should have 2 batches (50 + 25)
        assert result.batches_processed == 2
        assert result.quota_used == 2  # 1 quota per batch

    async def test_per_batch_commits(
        self,
        service: EnrichmentService,
        mock_session: AsyncMock,
        mock_channel_repo: AsyncMock,
        mock_youtube_service: AsyncMock,
    ) -> None:
        """Test per-batch database commits per FR-025 (T031)."""
        # Create 75 mock channels for 2 batches
        mock_channels = [
            MagicMock(channel_id=f"UC{i:022d}") for i in range(75)
        ]
        mock_channel_repo.get_channels_needing_enrichment.return_value = mock_channels
        mock_channel_repo.get.return_value = MagicMock()
        mock_youtube_service.get_channel_details.return_value = [
            make_channel_response(f"UC{i:022d}") for i in range(75)
        ]

        await service.enrich_channels(mock_session)

        # Should commit after each batch
        assert mock_session.commit.call_count >= 2

    async def test_verbose_tracking(
        self,
        service: EnrichmentService,
        mock_session: AsyncMock,
        mock_channel_repo: AsyncMock,
        mock_youtube_service: AsyncMock,
    ) -> None:
        """Test verbose mode tracks channel IDs (T025)."""
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCtest789"
        mock_channel_repo.get_channels_needing_enrichment.return_value = [mock_channel]
        mock_channel_repo.get.return_value = mock_channel

        api_response = make_channel_response(channel_id="UCtest789")
        mock_youtube_service.get_channel_details.return_value = [api_response]

        result = await service.enrich_channels(mock_session, verbose=True)

        assert "UCtest789" in result.enriched_channel_ids


class TestBatchSizeConstant:
    """Tests for BATCH_SIZE constant."""

    def test_batch_size_is_50(self) -> None:
        """Test that BATCH_SIZE is 50 (YouTube API limit)."""
        assert BATCH_SIZE == 50


class TestChannelEnrichmentErrorHandling:
    """Tests for error handling during channel enrichment (T029)."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def mock_channel_repo(self) -> AsyncMock:
        """Create a mock channel repository."""
        repo = AsyncMock()
        repo.get_channels_needing_enrichment = AsyncMock(return_value=[])
        repo.get = AsyncMock(return_value=None)
        return repo

    @pytest.fixture
    def service(self, mock_channel_repo: AsyncMock) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=AsyncMock(),
            channel_repository=mock_channel_repo,
            video_tag_repository=AsyncMock(),
            video_topic_repository=AsyncMock(),
            video_category_repository=AsyncMock(),
            topic_category_repository=AsyncMock(),
            youtube_service=AsyncMock(),
        )

    async def test_channel_not_in_database(
        self,
        service: EnrichmentService,
        mock_session: AsyncMock,
        mock_channel_repo: AsyncMock,
    ) -> None:
        """Test handling when channel exists on API but not in database."""
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCghost123"
        mock_channel_repo.get_channels_needing_enrichment.return_value = [mock_channel]
        mock_channel_repo.get.return_value = None  # Channel deleted from DB

        mock_youtube = cast(AsyncMock, service.youtube_service)
        mock_youtube.get_channel_details.return_value = [
            make_channel_response("UCghost123")
        ]

        result = await service.enrich_channels(mock_session, verbose=True)

        assert result.channels_failed == 1
        assert "UCghost123" in result.failed_channel_ids

    async def test_individual_channel_error_isolation(
        self,
        service: EnrichmentService,
        mock_session: AsyncMock,
        mock_channel_repo: AsyncMock,
    ) -> None:
        """Test that individual channel errors don't stop batch processing."""
        # Two channels, first will fail, second should succeed
        mock_channels = [
            MagicMock(channel_id="UCfail123"),
            MagicMock(channel_id="UCsuccess456"),
        ]
        mock_channel_repo.get_channels_needing_enrichment.return_value = mock_channels

        # First channel returns None (deleted), second works
        def get_channel(session: Any, channel_id: str) -> MagicMock | None:
            if channel_id == "UCfail123":
                return None  # Simulates database issue
            return MagicMock()

        mock_channel_repo.get.side_effect = get_channel

        # Both channels found on API
        mock_youtube = cast(AsyncMock, service.youtube_service)
        mock_youtube.get_channel_details.return_value = [
            make_channel_response("UCfail123"),
            make_channel_response("UCsuccess456"),
        ]

        result = await service.enrich_channels(mock_session)

        # Both should be processed despite first failing
        assert result.channels_processed == 2
        assert result.channels_failed == 1
        assert result.channels_enriched == 1
