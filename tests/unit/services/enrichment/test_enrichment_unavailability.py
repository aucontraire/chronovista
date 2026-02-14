"""
Unit tests for multi-cycle unavailability confirmation (Feature 023).

Tests the two-cycle confirmation logic for both videos and channels:
- FR-016: Channel unavailability detection
- FR-017: Channel multi-cycle confirmation
- FR-018: Restoration of previously unavailable content
- FR-023: Channel restoration with recovery metadata
- FR-024: Video multi-cycle confirmation
- FR-026: Video transient error recovery

Coverage:
- T025: Multi-cycle confirmation unit tests for videos and channels

The multi-cycle confirmation pattern prevents false positives from transient
API errors. First empty API response sets unavailability_first_detected; second
consecutive empty response confirms by setting availability_status=UNAVAILABLE.
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.models.enums import AvailabilityStatus
from chronovista.services.enrichment.enrichment_service import EnrichmentService

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


class TestVideoMultiCycleConfirmation:
    """Tests for video multi-cycle unavailability confirmation (FR-024, FR-026)."""

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
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_youtube_service: AsyncMock) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=AsyncMock(),
            channel_repository=AsyncMock(),
            video_tag_repository=AsyncMock(),
            video_topic_repository=AsyncMock(),
            video_category_repository=AsyncMock(),
            topic_category_repository=AsyncMock(),
            youtube_service=mock_youtube_service,
        )

    async def test_first_empty_api_response_sets_unavailability_first_detected(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test first empty API response sets unavailability_first_detected.

        FR-024: First cycle of multi-cycle confirmation should:
        - Set unavailability_first_detected timestamp
        - NOT change availability_status (remains AVAILABLE)
        - Return False (not confirmed)
        """
        # Create a video with no prior unavailability flag
        mock_video = MagicMock()
        mock_video.video_id = "firstCycle123"
        mock_video.availability_status = AvailabilityStatus.AVAILABLE
        mock_video.unavailability_first_detected = None

        # Call _mark_video_deleted (first cycle)
        confirmed = await service._mark_video_deleted(
            mock_session, mock_video, dry_run=False
        )

        # Verify first cycle behavior
        assert confirmed is False, "First cycle should return False (not confirmed)"
        assert mock_video.unavailability_first_detected is not None, (
            "First cycle should set unavailability_first_detected timestamp"
        )
        assert mock_video.availability_status == AvailabilityStatus.AVAILABLE, (
            "First cycle should NOT change availability_status"
        )

    async def test_second_consecutive_empty_response_confirms_unavailable(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test second consecutive empty response confirms as UNAVAILABLE.

        FR-024: Second cycle of multi-cycle confirmation should:
        - Change availability_status to UNAVAILABLE
        - Clear unavailability_first_detected (reset for next cycle)
        - Return True (confirmed)
        """
        # Create a video with unavailability_first_detected already set
        # (simulating first cycle already occurred)
        first_detection_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        mock_video = MagicMock()
        mock_video.video_id = "secondCycle456"
        mock_video.availability_status = AvailabilityStatus.AVAILABLE
        mock_video.unavailability_first_detected = first_detection_time

        # Call _mark_video_deleted (second cycle)
        confirmed = await service._mark_video_deleted(
            mock_session, mock_video, dry_run=False
        )

        # Verify second cycle behavior
        assert confirmed is True, "Second cycle should return True (confirmed)"
        assert mock_video.availability_status == AvailabilityStatus.UNAVAILABLE, (
            "Second cycle should change availability_status to UNAVAILABLE"
        )
        assert mock_video.unavailability_first_detected is None, (
            "Second cycle should clear unavailability_first_detected"
        )

    async def test_successful_api_response_after_first_empty_clears_flag(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test successful API response after first empty clears transient flag.

        FR-026: Transient error recovery should:
        - Clear unavailability_first_detected when API returns data
        - Keep availability_status as AVAILABLE
        - NOT mark the video as unavailable

        This simulates a scenario where the first sync had a transient API error,
        but the second sync succeeds.
        """
        from chronovista.models.api_responses import (
            YouTubeVideoResponse,
            VideoSnippet,
            VideoContentDetails,
        )

        # Create a video with unavailability_first_detected set (first cycle occurred)
        first_detection_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        mock_video = MagicMock()
        mock_video.video_id = "transientError789"
        mock_video.title = "[Placeholder] Video transientError789"
        mock_video.channel_id = "UCplaceholder"
        mock_video.availability_status = AvailabilityStatus.AVAILABLE
        mock_video.unavailability_first_detected = first_detection_time

        # Create API response (video is now found)
        api_response = YouTubeVideoResponse(
            kind="youtube#video",
            etag="test_etag",
            id="transientError789",
            snippet=VideoSnippet(
                publishedAt=datetime.now(timezone.utc),
                channelId="UCuAXFkgsw1L7xaCfnd5JJOw",
                title="Recovered Video",
                description="This video is back",
                channelTitle="Test Channel",
                categoryId="10",
                tags=[],
                thumbnails={},
            ),
            contentDetails=VideoContentDetails(duration="PT5M"),
        )

        # Mock the enrichment flow
        with patch.object(
            service, "_get_videos_for_enrichment", new_callable=AsyncMock
        ) as mock_get, patch.object(
            service.youtube_service,
            "fetch_videos_batched",
            new=AsyncMock(return_value=([api_response], set())),
        ), patch.object(
            service.video_repository,
            "get",
            new=AsyncMock(return_value=mock_video),
        ), patch.object(
            service.channel_repository, "get", new=AsyncMock(return_value=None)
        ), patch.object(
            service.channel_repository, "create", new=AsyncMock()
        ):
            mock_get.return_value = [mock_video]

            # Enrich videos (should clear the flag)
            report = await service.enrich_videos(
                mock_session, check_prerequisites=False
            )

            # Verify transient error recovery
            assert mock_video.unavailability_first_detected is None, (
                "Successful API response should clear unavailability_first_detected"
            )
            assert mock_video.availability_status == AvailabilityStatus.AVAILABLE, (
                "Transient error should not change availability_status"
            )
            assert report.summary.videos_updated == 1, "Video should be updated"
            assert report.summary.videos_deleted == 0, "Video should NOT be deleted"

    async def test_successful_api_response_does_not_set_unavailability_flag(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test successful API response does NOT set unavailability_first_detected.

        FR-024: Normal video enrichment (video found on API) should:
        - NOT set unavailability_first_detected
        - Keep availability_status as AVAILABLE
        - Update video metadata normally

        This is the happy path baseline test.
        """
        from chronovista.models.api_responses import (
            YouTubeVideoResponse,
            VideoSnippet,
            VideoContentDetails,
        )

        # Create a normal video with no unavailability flags
        mock_video = MagicMock()
        mock_video.video_id = "normalVideo123"
        mock_video.title = "[Placeholder] Video normalVideo123"
        mock_video.channel_id = "UCplaceholder"
        mock_video.availability_status = AvailabilityStatus.AVAILABLE
        mock_video.unavailability_first_detected = None

        # Create API response (video found normally)
        api_response = YouTubeVideoResponse(
            kind="youtube#video",
            etag="test_etag",
            id="normalVideo123",
            snippet=VideoSnippet(
                publishedAt=datetime.now(timezone.utc),
                channelId="UCuAXFkgsw1L7xaCfnd5JJOw",
                title="Normal Video",
                description="Normal video metadata",
                channelTitle="Normal Channel",
                categoryId="10",
                tags=[],
                thumbnails={},
            ),
            contentDetails=VideoContentDetails(duration="PT3M"),
        )

        # Mock the enrichment flow
        with patch.object(
            service, "_get_videos_for_enrichment", new_callable=AsyncMock
        ) as mock_get, patch.object(
            service.youtube_service,
            "fetch_videos_batched",
            new=AsyncMock(return_value=([api_response], set())),
        ), patch.object(
            service.video_repository,
            "get",
            new=AsyncMock(return_value=mock_video),
        ), patch.object(
            service.channel_repository, "get", new=AsyncMock(return_value=None)
        ), patch.object(
            service.channel_repository, "create", new=AsyncMock()
        ):
            mock_get.return_value = [mock_video]

            # Enrich videos
            report = await service.enrich_videos(
                mock_session, check_prerequisites=False
            )

            # Verify normal enrichment behavior
            assert mock_video.unavailability_first_detected is None, (
                "Normal enrichment should NOT set unavailability_first_detected"
            )
            assert mock_video.availability_status == AvailabilityStatus.AVAILABLE, (
                "Normal enrichment should keep availability_status as AVAILABLE"
            )
            assert report.summary.videos_updated == 1, "Video should be updated"
            assert report.summary.videos_deleted == 0, "Video should NOT be deleted"


class TestChannelMultiCycleConfirmation:
    """Tests for channel multi-cycle unavailability confirmation (FR-016, FR-017)."""

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
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_youtube_service: AsyncMock) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=AsyncMock(),
            channel_repository=AsyncMock(),
            video_tag_repository=AsyncMock(),
            video_topic_repository=AsyncMock(),
            video_category_repository=AsyncMock(),
            topic_category_repository=AsyncMock(),
            youtube_service=mock_youtube_service,
        )

    async def test_first_empty_api_response_sets_channel_unavailability_flag(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test first empty API response for channel sets unavailability_first_detected.

        FR-016/FR-017: First cycle of channel multi-cycle confirmation should:
        - Set unavailability_first_detected timestamp
        - NOT change availability_status (remains AVAILABLE)
        - Increment channels_skipped counter
        """
        from chronovista.models.api_responses import YouTubeChannelResponse

        # Create a channel with no prior unavailability flag
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCfirstChannel"
        mock_channel.availability_status = AvailabilityStatus.AVAILABLE
        mock_channel.unavailability_first_detected = None

        # Mock the channel enrichment flow (channel not found on API)
        with patch.object(
            service.youtube_service,
            "get_channel_details",
            new=AsyncMock(return_value=[]),  # Empty list = channel not found
        ), patch.object(
            service.channel_repository,
            "get_channels_needing_enrichment",
            new=AsyncMock(return_value=[mock_channel]),
        ), patch.object(
            service.channel_repository,
            "get",
            new=AsyncMock(return_value=mock_channel),
        ):
            # Enrich channels (first cycle)
            result = await service.enrich_channels(mock_session, verbose=True)

            # Verify first cycle behavior
            assert mock_channel.unavailability_first_detected is not None, (
                "First cycle should set unavailability_first_detected timestamp"
            )
            assert mock_channel.availability_status == AvailabilityStatus.AVAILABLE, (
                "First cycle should NOT change availability_status"
            )
            assert result.channels_skipped == 1, (
                "Channel should be skipped in first cycle"
            )

    async def test_second_consecutive_empty_response_confirms_channel_unavailable(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test second consecutive empty response confirms channel as UNAVAILABLE.

        FR-016/FR-017: Second cycle of channel multi-cycle confirmation should:
        - Change availability_status to UNAVAILABLE
        - Clear unavailability_first_detected (reset for next cycle)
        - Increment channels_skipped counter
        """
        from chronovista.models.api_responses import YouTubeChannelResponse

        # Create a channel with unavailability_first_detected already set
        first_detection_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCsecondChannel"
        mock_channel.availability_status = AvailabilityStatus.AVAILABLE
        mock_channel.unavailability_first_detected = first_detection_time

        # Mock the channel enrichment flow (channel still not found on API)
        with patch.object(
            service.youtube_service,
            "get_channel_details",
            new=AsyncMock(return_value=[]),  # Empty list = channel not found again
        ), patch.object(
            service.channel_repository,
            "get_channels_needing_enrichment",
            new=AsyncMock(return_value=[mock_channel]),
        ), patch.object(
            service.channel_repository,
            "get",
            new=AsyncMock(return_value=mock_channel),
        ):
            # Enrich channels (second cycle)
            result = await service.enrich_channels(mock_session, verbose=True)

            # Verify second cycle behavior
            assert mock_channel.availability_status == AvailabilityStatus.UNAVAILABLE, (
                "Second cycle should change availability_status to UNAVAILABLE"
            )
            assert mock_channel.unavailability_first_detected is None, (
                "Second cycle should clear unavailability_first_detected"
            )
            assert result.channels_skipped == 1, (
                "Channel should be skipped in second cycle"
            )

    async def test_successful_api_response_clears_channel_flag(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test successful API response for channel clears transient flag.

        FR-016: Transient error recovery for channels should:
        - Clear unavailability_first_detected when API returns data
        - Keep availability_status as AVAILABLE
        - Update channel metadata normally

        This simulates a scenario where the first sync had a transient API error,
        but the second sync succeeds.
        """
        from chronovista.models.api_responses import (
            YouTubeChannelResponse,
            ChannelSnippet,
            ChannelStatisticsResponse,
        )

        # Create a channel with unavailability_first_detected set (first cycle occurred)
        first_detection_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCtransientChannel"
        mock_channel.title = "Transient Channel"
        mock_channel.availability_status = AvailabilityStatus.AVAILABLE
        mock_channel.unavailability_first_detected = first_detection_time

        # Create API response (channel is now found)
        api_response = YouTubeChannelResponse(
            kind="youtube#channel",
            etag="test_etag",
            id="UCtransientChannel",
            snippet=ChannelSnippet(
                title="Recovered Channel",
                description="Channel description",
                publishedAt=datetime.now(timezone.utc),
                thumbnails={},
            ),
            statistics=ChannelStatisticsResponse(
                viewCount=1000,
                subscriberCount=500,
            ),
        )

        # Mock the channel enrichment flow (channel found)
        with patch.object(
            service.youtube_service,
            "get_channel_details",
            new=AsyncMock(return_value=[api_response]),
        ), patch.object(
            service.channel_repository,
            "get_channels_needing_enrichment",
            new=AsyncMock(return_value=[mock_channel]),
        ), patch.object(
            service.channel_repository,
            "get",
            new=AsyncMock(return_value=mock_channel),
        ):
            # Enrich channels (should clear the flag)
            result = await service.enrich_channels(mock_session, verbose=True)

            # Verify transient error recovery
            assert mock_channel.unavailability_first_detected is None, (
                "Successful API response should clear unavailability_first_detected"
            )
            assert mock_channel.availability_status == AvailabilityStatus.AVAILABLE, (
                "Transient error should not change availability_status"
            )
            assert result.channels_enriched == 1, "Channel should be enriched"


class TestRestorationBehavior:
    """Tests for restoration of previously unavailable content (FR-018, FR-023)."""

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
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_youtube_service: AsyncMock) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=AsyncMock(),
            channel_repository=AsyncMock(),
            video_tag_repository=AsyncMock(),
            video_topic_repository=AsyncMock(),
            video_category_repository=AsyncMock(),
            topic_category_repository=AsyncMock(),
            youtube_service=mock_youtube_service,
        )

    async def test_video_restoration_sets_recovered_metadata(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test video restoration sets recovery metadata.

        FR-018/FR-023: Previously unavailable video restored via API should:
        - Change availability_status from UNAVAILABLE to AVAILABLE
        - Set recovered_at timestamp
        - Set recovery_source to 'sync'
        - Clear unavailability_first_detected
        - Update video metadata normally
        """
        from chronovista.models.api_responses import (
            YouTubeVideoResponse,
            VideoSnippet,
            VideoContentDetails,
        )

        # Create a previously unavailable video
        mock_video = MagicMock()
        mock_video.video_id = "restoredVideo123"
        mock_video.title = "[Placeholder] Video restoredVideo123"
        mock_video.channel_id = "UCplaceholder"
        mock_video.availability_status = AvailabilityStatus.UNAVAILABLE
        mock_video.unavailability_first_detected = None  # Already confirmed unavailable
        mock_video.recovered_at = None
        mock_video.recovery_source = None

        # Create API response (video is now available)
        api_response = YouTubeVideoResponse(
            kind="youtube#video",
            etag="test_etag",
            id="restoredVideo123",
            snippet=VideoSnippet(
                publishedAt=datetime.now(timezone.utc),
                channelId="UCuAXFkgsw1L7xaCfnd5JJOw",
                title="Restored Video",
                description="This video has been restored",
                channelTitle="Restored Channel",
                categoryId="10",
                tags=[],
                thumbnails={},
            ),
            contentDetails=VideoContentDetails(duration="PT4M"),
        )

        # Mock the enrichment flow
        with patch.object(
            service, "_get_videos_for_enrichment", new_callable=AsyncMock
        ) as mock_get, patch.object(
            service.youtube_service,
            "fetch_videos_batched",
            new=AsyncMock(return_value=([api_response], set())),
        ), patch.object(
            service.video_repository,
            "get",
            new=AsyncMock(return_value=mock_video),
        ), patch.object(
            service.channel_repository, "get", new=AsyncMock(return_value=None)
        ), patch.object(
            service.channel_repository, "create", new=AsyncMock()
        ):
            mock_get.return_value = [mock_video]

            # Enrich videos with include_deleted=True (to process unavailable videos)
            report = await service.enrich_videos(
                mock_session, include_deleted=True, check_prerequisites=False
            )

            # Verify restoration behavior
            assert mock_video.availability_status == AvailabilityStatus.AVAILABLE, (
                "Restored video should have availability_status=AVAILABLE"
            )
            assert mock_video.recovered_at is not None, (
                "Restored video should have recovered_at timestamp set"
            )
            assert mock_video.recovery_source == "sync", (
                "Restored video should have recovery_source='sync'"
            )
            assert mock_video.unavailability_first_detected is None, (
                "Restored video should have unavailability_first_detected cleared"
            )
            assert mock_video.title == "Restored Video", (
                "Restored video should have updated metadata"
            )
            assert report.summary.videos_updated == 1, "Video should be updated"
            assert report.summary.videos_deleted == 0, "Video should NOT be deleted"

    async def test_channel_restoration_sets_recovered_metadata(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test channel restoration sets recovery metadata.

        FR-018/FR-023: Previously unavailable channel restored via API should:
        - Change availability_status from UNAVAILABLE to AVAILABLE
        - Set recovered_at timestamp
        - Set recovery_source to 'sync'
        - Clear unavailability_first_detected
        - Update channel metadata normally
        """
        from chronovista.models.api_responses import (
            YouTubeChannelResponse,
            ChannelSnippet,
            ChannelStatisticsResponse,
        )

        # Create a previously unavailable channel
        mock_channel = MagicMock()
        mock_channel.channel_id = "UCrestoredChannel"
        mock_channel.title = "Old Channel Title"
        mock_channel.availability_status = AvailabilityStatus.UNAVAILABLE
        mock_channel.unavailability_first_detected = None  # Already confirmed unavailable
        mock_channel.recovered_at = None
        mock_channel.recovery_source = None

        # Create API response (channel is now available)
        api_response = YouTubeChannelResponse(
            kind="youtube#channel",
            etag="test_etag",
            id="UCrestoredChannel",
            snippet=ChannelSnippet(
                title="Restored Channel Title",
                description="Channel has been restored",
                publishedAt=datetime.now(timezone.utc),
                thumbnails={},
            ),
            statistics=ChannelStatisticsResponse(
                viewCount=5000,
                subscriberCount=1000,
            ),
        )

        # Mock the channel enrichment flow
        with patch.object(
            service.youtube_service,
            "get_channel_details",
            new=AsyncMock(return_value=[api_response]),
        ), patch.object(
            service.channel_repository,
            "get_channels_needing_enrichment",
            new=AsyncMock(return_value=[mock_channel]),
        ), patch.object(
            service.channel_repository,
            "get",
            new=AsyncMock(return_value=mock_channel),
        ):
            # Enrich channels
            result = await service.enrich_channels(mock_session, verbose=True)

            # Verify restoration behavior
            assert mock_channel.availability_status == AvailabilityStatus.AVAILABLE, (
                "Restored channel should have availability_status=AVAILABLE"
            )
            assert mock_channel.recovered_at is not None, (
                "Restored channel should have recovered_at timestamp set"
            )
            assert mock_channel.recovery_source == "sync", (
                "Restored channel should have recovery_source='sync'"
            )
            assert mock_channel.unavailability_first_detected is None, (
                "Restored channel should have unavailability_first_detected cleared"
            )
            assert mock_channel.title == "Restored Channel Title", (
                "Restored channel should have updated metadata"
            )
            assert result.channels_enriched == 1, "Channel should be enriched"

    async def test_restoration_clears_unavailability_first_detected(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test restoration clears unavailability_first_detected if it was set.

        FR-018/FR-023: Edge case where a video was:
        1. Flagged in first cycle (unavailability_first_detected set)
        2. Manually marked as UNAVAILABLE by admin
        3. Now becomes available again

        The restoration should clear the flag regardless of how it got there.
        """
        from chronovista.models.api_responses import (
            YouTubeVideoResponse,
            VideoSnippet,
            VideoContentDetails,
        )

        # Create a video with both UNAVAILABLE status AND a pending flag
        # (edge case - shouldn't happen normally, but test robustness)
        first_detection_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        mock_video = MagicMock()
        mock_video.video_id = "edgeCaseVideo"
        mock_video.title = "[Placeholder] Video edgeCaseVideo"
        mock_video.channel_id = "UCplaceholder"
        mock_video.availability_status = AvailabilityStatus.UNAVAILABLE
        mock_video.unavailability_first_detected = first_detection_time
        mock_video.recovered_at = None
        mock_video.recovery_source = None

        # Create API response (video is now available)
        api_response = YouTubeVideoResponse(
            kind="youtube#video",
            etag="test_etag",
            id="edgeCaseVideo",
            snippet=VideoSnippet(
                publishedAt=datetime.now(timezone.utc),
                channelId="UCuAXFkgsw1L7xaCfnd5JJOw",
                title="Edge Case Video",
                description="Testing edge case",
                channelTitle="Test Channel",
                categoryId="10",
                tags=[],
                thumbnails={},
            ),
            contentDetails=VideoContentDetails(duration="PT2M"),
        )

        # Mock the enrichment flow
        with patch.object(
            service, "_get_videos_for_enrichment", new_callable=AsyncMock
        ) as mock_get, patch.object(
            service.youtube_service,
            "fetch_videos_batched",
            new=AsyncMock(return_value=([api_response], set())),
        ), patch.object(
            service.video_repository,
            "get",
            new=AsyncMock(return_value=mock_video),
        ), patch.object(
            service.channel_repository, "get", new=AsyncMock(return_value=None)
        ), patch.object(
            service.channel_repository, "create", new=AsyncMock()
        ):
            mock_get.return_value = [mock_video]

            # Enrich videos
            report = await service.enrich_videos(
                mock_session, include_deleted=True, check_prerequisites=False
            )

            # Verify that BOTH restoration AND flag clearing happened
            assert mock_video.availability_status == AvailabilityStatus.AVAILABLE, (
                "Restoration should set availability_status=AVAILABLE"
            )
            assert mock_video.unavailability_first_detected is None, (
                "Restoration should clear unavailability_first_detected flag"
            )
            assert mock_video.recovered_at is not None, (
                "Restoration should set recovered_at"
            )
            assert mock_video.recovery_source == "sync", (
                "Restoration should set recovery_source='sync'"
            )


class TestDryRunBehavior:
    """Tests for dry_run mode behavior in multi-cycle confirmation."""

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
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_youtube_service: AsyncMock) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=AsyncMock(),
            channel_repository=AsyncMock(),
            video_tag_repository=AsyncMock(),
            video_topic_repository=AsyncMock(),
            video_category_repository=AsyncMock(),
            topic_category_repository=AsyncMock(),
            youtube_service=mock_youtube_service,
        )

    async def test_dry_run_does_not_set_unavailability_flag(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test dry_run mode does not set unavailability_first_detected.

        Dry run should:
        - NOT modify any video attributes
        - Return False (not confirmed)
        - Allow inspection of what would happen without side effects
        """
        # Create a video with no unavailability flag
        mock_video = MagicMock()
        mock_video.video_id = "dryRunVideo123"
        mock_video.availability_status = AvailabilityStatus.AVAILABLE
        mock_video.unavailability_first_detected = None

        # Call _mark_video_deleted in dry_run mode
        confirmed = await service._mark_video_deleted(
            mock_session, mock_video, dry_run=True
        )

        # Verify dry run behavior (no changes)
        assert confirmed is False, "Dry run should return False"
        assert mock_video.unavailability_first_detected is None, (
            "Dry run should NOT set unavailability_first_detected"
        )
        assert mock_video.availability_status == AvailabilityStatus.AVAILABLE, (
            "Dry run should NOT change availability_status"
        )

    async def test_dry_run_does_not_confirm_unavailable(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """
        Test dry_run mode does not confirm unavailable (second cycle).

        Dry run should:
        - NOT change availability_status to UNAVAILABLE
        - NOT clear unavailability_first_detected
        - Return False (not confirmed)
        """
        # Create a video with unavailability_first_detected set (ready for second cycle)
        first_detection_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        mock_video = MagicMock()
        mock_video.video_id = "dryRunVideo456"
        mock_video.availability_status = AvailabilityStatus.AVAILABLE
        mock_video.unavailability_first_detected = first_detection_time

        # Call _mark_video_deleted in dry_run mode (would be second cycle)
        confirmed = await service._mark_video_deleted(
            mock_session, mock_video, dry_run=True
        )

        # Verify dry run behavior (no changes, even in second cycle)
        assert confirmed is False, "Dry run should return False"
        assert mock_video.availability_status == AvailabilityStatus.AVAILABLE, (
            "Dry run should NOT change availability_status"
        )
        assert mock_video.unavailability_first_detected == first_detection_time, (
            "Dry run should NOT clear unavailability_first_detected"
        )
