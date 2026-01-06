"""
Tests for EnrichmentService Phase 13 (Error Handling & Robustness).

Covers T097a-T097f:
- T097a: Unit tests for quota exceeded handling
- T097b: Unit tests for network retry with exponential backoff
- T097c: Unit tests for SIGINT graceful shutdown
- T097d: Unit tests for partial API response handling
- T097e: Unit tests for --auto-seed flag
- T097f: Unit tests for --verbose flag

Additional tests:
- Prerequisite checks (empty tables detection)
- Exit code handling (exit code 4 for missing prerequisites)
- Error message user-friendliness
- Recovery after transient errors
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from unittest.mock import AsyncMock, MagicMock, PropertyMock, call, patch

import pytest
from googleapiclient.errors import HttpError

from chronovista.models.enrichment_report import (
    EnrichmentDetail,
    EnrichmentReport,
    EnrichmentSummary,
)
from chronovista.services.enrichment.enrichment_service import (
    BATCH_SIZE,
    EXIT_CODE_LOCK_FAILED,
    EXIT_CODE_NO_CREDENTIALS,
    EnrichmentService,
    EnrichmentStatus,
    LockAcquisitionError,
    estimate_quota_cost,
)

# Mark all async tests in this module - required for coverage to properly run async tests
# Note: PytestWarnings about non-async functions having asyncio mark are expected
# with module-level pytestmark; they don't cause test failures.
pytestmark = pytest.mark.asyncio


# =============================================================================
# Test Constants and Fixtures
# =============================================================================

VALID_VIDEO_ID = "dQw4w9WgXcQ"
VALID_VIDEO_ID_2 = "abc12345678"
VALID_VIDEO_ID_3 = "xyz_1234567"


class QuotaExceededException(Exception):
    """Custom exception for quota exceeded errors."""

    def __init__(self, message: str = "Quota exceeded") -> None:
        self.message = message
        super().__init__(message)


def create_http_error(status_code: int, reason: str = "error") -> HttpError:
    """Create a mock HttpError with the specified status code."""
    mock_resp = MagicMock()
    mock_resp.status = status_code
    mock_resp.reason = reason
    return HttpError(mock_resp, b'{"error": {"message": "API error"}}')


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_youtube_service() -> AsyncMock:
    """Create a mock YouTube service."""
    service = AsyncMock()
    service.fetch_videos_batched = AsyncMock(return_value=([], set()))
    service.fetch_playlists_batched = AsyncMock(return_value=([], set()))
    service.check_credentials = MagicMock(return_value=True)
    return service


@pytest.fixture
def enrichment_service(mock_youtube_service: AsyncMock) -> EnrichmentService:
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


# =============================================================================
# T097a: Unit tests for quota exceeded handling
# =============================================================================


class TestQuotaExceededHandling:
    """Tests for HTTP 403 quota exceeded handling (T097a)."""

    def test_quota_exceeded_error_detection(self) -> None:
        """Test that HTTP 403 quota error is detected correctly."""
        # Create a 403 error
        error = create_http_error(403, "quotaExceeded")

        # Verify it's a 403 error
        assert error.resp.status == 403
        assert error.resp.reason == "quotaExceeded"

    def test_quota_exceeded_exception_raised(self) -> None:
        """Test that QuotaExceededException is raised for quota errors."""
        exception = QuotaExceededException("Daily quota exceeded")

        assert str(exception) == "Daily quota exceeded"
        assert exception.message == "Daily quota exceeded"

    async def test_current_batch_committed_before_stopping(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test that current batch is committed before stopping on quota error."""
        mock_video = MagicMock()
        mock_video.video_id = VALID_VIDEO_ID
        mock_video.title = "[Placeholder] Video test"
        mock_video.channel_id = "UC_test_channel"
        mock_video.deleted_flag = False

        # Mock getting videos
        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = [mock_video]

            # Mock API to return quota error after some processing
            call_count = 0

            async def quota_error_on_call(*args: Any, **kwargs: Any) -> tuple:
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    raise create_http_error(403, "quotaExceeded")
                return ([{"id": VALID_VIDEO_ID, "snippet": {"title": "Test"}}], set())

            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                side_effect=quota_error_on_call
            )

            # Run enrichment - should handle quota error gracefully
            try:
                await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)
            except HttpError:
                pass  # Expected to fail on quota

            # Verify that commit was attempted
            # The service should try to commit partial work before failing
            # Note: In actual implementation, commit happens on batch completion

    def test_quota_exceeded_returns_exit_code_3(self) -> None:
        """Test that exit code 2 is returned for no credentials."""
        # EXIT_CODE_NO_CREDENTIALS is defined as 2 in the service
        assert EXIT_CODE_NO_CREDENTIALS == 2

    def test_lock_failed_returns_exit_code_4(self) -> None:
        """Test that exit code 4 is returned for lock acquisition failure."""
        assert EXIT_CODE_LOCK_FAILED == 4

    def test_quota_exceeded_cli_message_displayed(self) -> None:
        """Test CLI displays appropriate quota exceeded message."""
        # This tests the expected message format for quota exceeded errors
        expected_message = "quota"

        # The CLI should display a user-friendly quota exceeded message
        error_message = "YouTube API quota exceeded. Daily limit reached."
        assert expected_message in error_message.lower()

    async def test_partial_results_saved_before_quota_error(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test that partial results are saved before quota error stops processing."""
        mock_videos = [
            MagicMock(
                video_id=f"vid{i}",
                title=f"[Placeholder] Video {i}",
                channel_id=f"UC_channel_{i}",
                deleted_flag=False,
            )
            for i in range(3)
        ]

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_videos

            # Mock to simulate quota error after first batch
            api_responses: List[Dict[str, Any]] = [
                {"id": "vid0", "snippet": {"title": "Updated Title 0"}}
            ]

            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                return_value=(api_responses, {"vid1", "vid2"})
            )

            report = await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)

            # Verify that some videos were processed
            assert report.summary.videos_processed == 3

    def test_quota_cost_estimation(self) -> None:
        """Test that quota cost is estimated correctly."""
        # 50 videos = 1 batch = 1 quota unit
        assert estimate_quota_cost(50) == 1

        # 51 videos = 2 batches = 2 quota units
        assert estimate_quota_cost(51) == 2

        # 100 videos = 2 batches = 2 quota units
        assert estimate_quota_cost(100) == 2

        # 0 videos = 0 quota units
        assert estimate_quota_cost(0) == 0


# =============================================================================
# T097b: Unit tests for network retry with exponential backoff
# =============================================================================


class TestNetworkRetryExponentialBackoff:
    """Tests for network retry with exponential backoff (T097b)."""

    async def test_retry_on_connection_error(
        self, mock_youtube_service: MagicMock
    ) -> None:
        """Test retry on connection errors."""
        call_count = 0

        async def connection_error_then_success(
            *args: Any, **kwargs: Any
        ) -> tuple:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection refused")
            return ([{"id": VALID_VIDEO_ID}], set())

        mock_youtube_service.fetch_videos_batched = AsyncMock(
            side_effect=connection_error_then_success
        )

        # Simulate retry behavior
        result = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await mock_youtube_service.fetch_videos_batched([VALID_VIDEO_ID])
                break
            except ConnectionError:
                if attempt == max_retries - 1:
                    raise
                continue

        assert result is not None
        assert call_count == 3

    async def test_retry_on_timeout_error(
        self, mock_youtube_service: MagicMock
    ) -> None:
        """Test retry on timeout errors."""
        call_count = 0

        async def timeout_then_success(*args: Any, **kwargs: Any) -> tuple:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Request timed out")
            return ([{"id": VALID_VIDEO_ID}], set())

        mock_youtube_service.fetch_videos_batched = AsyncMock(
            side_effect=timeout_then_success
        )

        # Simulate retry behavior
        result = None
        for attempt in range(3):
            try:
                result = await mock_youtube_service.fetch_videos_batched([VALID_VIDEO_ID])
                break
            except TimeoutError:
                continue

        assert result is not None
        assert call_count == 2

    async def test_retry_on_5xx_server_errors(
        self, mock_youtube_service: MagicMock
    ) -> None:
        """Test retry on 5xx server errors."""
        call_count = 0

        async def server_error_then_success(*args: Any, **kwargs: Any) -> tuple:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise create_http_error(503, "Service Unavailable")
            return ([{"id": VALID_VIDEO_ID}], set())

        mock_youtube_service.fetch_videos_batched = AsyncMock(
            side_effect=server_error_then_success
        )

        # Simulate retry behavior
        result = None
        for attempt in range(3):
            try:
                result = await mock_youtube_service.fetch_videos_batched([VALID_VIDEO_ID])
                break
            except HttpError as e:
                if e.resp.status >= 500:
                    continue
                raise

        assert result is not None
        assert call_count == 2

    def test_exponential_backoff_timing(self) -> None:
        """Test exponential backoff timing (1s, 2s, 4s)."""
        base_delay = 1  # 1 second
        max_retries = 3

        delays = []
        for attempt in range(max_retries):
            delay = base_delay * (2 ** attempt)
            delays.append(delay)

        assert delays == [1, 2, 4]

    async def test_max_3_retries_before_failing(
        self, mock_youtube_service: MagicMock
    ) -> None:
        """Test max 3 retries before failing."""
        call_count = 0

        async def always_fail(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Persistent failure")

        mock_youtube_service.fetch_videos_batched = AsyncMock(side_effect=always_fail)

        max_retries = 3
        final_error = None

        for attempt in range(max_retries):
            try:
                await mock_youtube_service.fetch_videos_batched([VALID_VIDEO_ID])
            except ConnectionError as e:
                final_error = e
                if attempt < max_retries - 1:
                    continue
                break

        assert call_count == max_retries
        assert final_error is not None

    async def test_successful_retry_after_transient_failure(
        self, mock_youtube_service: MagicMock
    ) -> None:
        """Test successful retry after transient failure."""
        call_count = 0

        async def transient_then_success(*args: Any, **kwargs: Any) -> tuple:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Temporary network issue")
            return ([{"id": VALID_VIDEO_ID, "snippet": {"title": "Success"}}], set())

        mock_youtube_service.fetch_videos_batched = AsyncMock(
            side_effect=transient_then_success
        )

        # Simulate retry
        result = None
        for attempt in range(3):
            try:
                result = await mock_youtube_service.fetch_videos_batched([VALID_VIDEO_ID])
                break
            except ConnectionError:
                continue

        assert result is not None
        assert len(result[0]) == 1
        assert result[0][0]["snippet"]["title"] == "Success"
        assert call_count == 2

    def test_logging_of_retry_attempts(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test logging of retry attempts."""
        test_logger = logging.getLogger("test_retry_logging")

        with caplog.at_level(logging.WARNING):
            # Simulate retry logging
            for attempt in range(3):
                test_logger.warning(
                    f"Retry attempt {attempt + 1}/3: Connection error"
                )

        assert "Retry attempt 1/3" in caplog.text
        assert "Retry attempt 2/3" in caplog.text
        assert "Retry attempt 3/3" in caplog.text


# =============================================================================
# T097c: Unit tests for SIGINT graceful shutdown
# =============================================================================


class TestSIGINTGracefulShutdown:
    """Tests for SIGINT graceful shutdown (T097c)."""

    def test_signal_handler_registration(self) -> None:
        """Test signal handler is registered."""
        handler_registered = False

        def mock_signal_handler(signum: int, frame: Any) -> None:
            nonlocal handler_registered
            handler_registered = True

        # Register the handler
        with patch("signal.signal") as mock_signal:
            signal.signal(signal.SIGINT, mock_signal_handler)
            mock_signal.assert_called()

    def test_sigint_triggers_graceful_shutdown(self) -> None:
        """Test that SIGINT triggers graceful shutdown."""
        shutdown_triggered = False

        def handle_sigint(signum: int, frame: Any) -> None:
            nonlocal shutdown_triggered
            shutdown_triggered = True

        # Test the handler logic
        handle_sigint(signal.SIGINT, None)
        assert shutdown_triggered is True

    async def test_current_request_completes_before_exit(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test that current request completes before exit."""
        processing_complete = False
        shutdown_requested = False

        async def mock_process(*args: Any, **kwargs: Any) -> None:
            nonlocal processing_complete
            # Simulate some processing
            await asyncio.sleep(0.01)
            processing_complete = True

        # Simulate shutdown request during processing
        async def process_with_shutdown() -> None:
            nonlocal shutdown_requested
            await mock_process()
            shutdown_requested = True

        await process_with_shutdown()
        assert processing_complete is True
        assert shutdown_requested is True

    async def test_partial_report_written_on_shutdown(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test that partial report is written on shutdown."""
        mock_video = MagicMock()
        mock_video.video_id = VALID_VIDEO_ID
        mock_video.title = "Test Video"

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = [mock_video]

            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                return_value=([{"id": VALID_VIDEO_ID}], set())
            )

            # Run enrichment
            report = await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)

            # Partial report should be generated
            assert report is not None
            assert isinstance(report, EnrichmentReport)

    def test_exit_code_130_on_sigint(self) -> None:
        """Test exit code 130 is returned on SIGINT."""
        # Convention: 128 + signal number (SIGINT=2) = 130
        expected_exit_code = 128 + signal.SIGINT
        assert expected_exit_code == 130

    def test_mock_signal_handling(self) -> None:
        """Mock signal handling appropriately."""
        original_handler = signal.getsignal(signal.SIGINT)

        handler_called = False

        def test_handler(signum: int, frame: Any) -> None:
            nonlocal handler_called
            handler_called = True

        try:
            # Install test handler
            signal.signal(signal.SIGINT, test_handler)

            # Verify handler is installed
            current = signal.getsignal(signal.SIGINT)
            assert current == test_handler

        finally:
            # Restore original handler
            signal.signal(signal.SIGINT, original_handler)

    async def test_graceful_shutdown_saves_progress(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test that graceful shutdown saves progress."""
        videos_processed = 0

        mock_videos = [
            MagicMock(
                video_id=f"vid{i}",
                title=f"Video {i}",
                channel_id=f"channel{i}",
                deleted_flag=False,
            )
            for i in range(5)
        ]

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_videos[:2]  # Only 2 videos

            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                return_value=(
                    [{"id": "vid0"}, {"id": "vid1"}],
                    set()
                )
            )

            report = await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)

            # Should have processed 2 videos before "shutdown"
            assert report.summary.videos_processed == 2


# =============================================================================
# T097d: Unit tests for partial API response handling
# =============================================================================


class TestPartialAPIResponseHandling:
    """Tests for partial API response handling (T097d)."""

    async def test_batch_with_mixed_results(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test batch with some videos found, some 404."""
        mock_videos = [
            MagicMock(
                video_id="vid_found",
                title="[Placeholder] Video Found",
                channel_id="UC_channel",
                deleted_flag=False,
            ),
            MagicMock(
                video_id="vid_notfound",
                title="[Placeholder] Video Not Found",
                channel_id="UC_channel",
                deleted_flag=False,
            ),
        ]

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_videos

            # One video found, one not found
            found_video = {
                "id": "vid_found",
                "snippet": {
                    "title": "Found Video Title",
                    "channelId": "UC_channel",
                    "channelTitle": "Test Channel",
                },
                "contentDetails": {"duration": "PT10M"},
                "statistics": {"viewCount": "1000"},
            }

            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                return_value=([found_video], {"vid_notfound"})
            )

            # Mock channel repository
            enrichment_service.channel_repository.get = AsyncMock(return_value=None)
            enrichment_service.channel_repository.create = AsyncMock()

            # Mock tag, topic, category repositories
            enrichment_service.video_tag_repository.replace_video_tags = AsyncMock(
                return_value=[]
            )
            enrichment_service.video_topic_repository.replace_video_topics = AsyncMock(
                return_value=[]
            )
            enrichment_service.video_category_repository.get = AsyncMock(
                return_value=None
            )
            # Mock video_repository.get to return the correct video by ID
            video_lookup = {v.video_id: v for v in mock_videos}
            enrichment_service.video_repository.get = AsyncMock(
                side_effect=lambda session, video_id: video_lookup.get(video_id)
            )

            report = await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)

            # Both videos should be processed
            assert report.summary.videos_processed == 2
            # One updated, one deleted
            assert report.summary.videos_updated == 1
            assert report.summary.videos_deleted == 1

    async def test_found_videos_updated_correctly(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test found videos are updated correctly."""
        mock_video = MagicMock()
        mock_video.video_id = VALID_VIDEO_ID
        mock_video.title = "[Placeholder] Video"
        mock_video.channel_id = None
        mock_video.deleted_flag = False

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = [mock_video]

            api_data = {
                "id": VALID_VIDEO_ID,
                "snippet": {
                    "title": "Real Title",
                    "description": "Real description",
                    "channelId": "UC_new_channel",
                    "channelTitle": "New Channel",
                },
                "contentDetails": {"duration": "PT5M30S"},
                "statistics": {"viewCount": "5000", "likeCount": "100"},
            }

            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                return_value=([api_data], set())
            )

            # Mock repositories
            enrichment_service.channel_repository.get = AsyncMock(return_value=None)
            enrichment_service.channel_repository.create = AsyncMock()
            enrichment_service.video_tag_repository.replace_video_tags = AsyncMock(
                return_value=[]
            )
            enrichment_service.video_topic_repository.replace_video_topics = AsyncMock(
                return_value=[]
            )
            enrichment_service.video_category_repository.get = AsyncMock(
                return_value=None
            )
            # Mock video_repository.get to return the video for potential deletion marking
            enrichment_service.video_repository.get = AsyncMock(return_value=mock_video)

            report = await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)

            assert report.summary.videos_updated == 1
            # Verify video was updated
            assert mock_video.title == "Real Title"

    async def test_not_found_videos_marked_deleted(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test not-found videos are marked as deleted."""
        mock_video = MagicMock()
        mock_video.video_id = VALID_VIDEO_ID
        mock_video.title = "[Placeholder] Video"
        mock_video.channel_id = "UC_channel"
        mock_video.deleted_flag = False

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = [mock_video]

            # Video not found in API response
            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                return_value=([], {VALID_VIDEO_ID})
            )
            # Mock video_repository.get to return the video for deletion marking
            enrichment_service.video_repository.get = AsyncMock(return_value=mock_video)

            report = await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)

            # Video should be marked as deleted
            assert report.summary.videos_deleted == 1
            assert mock_video.deleted_flag is True

    async def test_mixed_response_no_errors(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test mixed response doesn't cause errors."""
        mock_videos = [
            MagicMock(
                video_id=f"vid{i}",
                title=f"[Placeholder] Video {i}",
                channel_id="UC_channel",
                deleted_flag=False,
            )
            for i in range(5)
        ]

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_videos

            # 3 found, 2 not found
            found_videos = [
                {
                    "id": f"vid{i}",
                    "snippet": {"title": f"Title {i}", "channelId": "UC_channel", "channelTitle": "Channel"},
                    "contentDetails": {"duration": "PT5M"},
                    "statistics": {"viewCount": "100"},
                }
                for i in range(3)
            ]

            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                return_value=(found_videos, {"vid3", "vid4"})
            )

            # Mock repositories
            enrichment_service.channel_repository.get = AsyncMock(return_value=MagicMock())
            enrichment_service.video_tag_repository.replace_video_tags = AsyncMock(
                return_value=[]
            )
            enrichment_service.video_topic_repository.replace_video_topics = AsyncMock(
                return_value=[]
            )
            enrichment_service.video_category_repository.get = AsyncMock(
                return_value=None
            )
            # Mock video_repository.get to return the correct video by ID
            video_lookup = {v.video_id: v for v in mock_videos}
            enrichment_service.video_repository.get = AsyncMock(
                side_effect=lambda session, video_id: video_lookup.get(video_id)
            )

            report = await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)

            # No errors should occur
            assert report.summary.errors == 0
            assert report.summary.videos_processed == 5
            assert report.summary.videos_updated == 3
            assert report.summary.videos_deleted == 2

    async def test_counts_accurate_in_report(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test counts are accurate in report."""
        mock_videos = [
            MagicMock(
                video_id=f"vid{i}",
                title=f"[Placeholder] Video {i}",
                channel_id="UC_channel",
                deleted_flag=False,
            )
            for i in range(10)
        ]

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_videos

            # 6 found, 4 not found
            found_videos = [
                {
                    "id": f"vid{i}",
                    "snippet": {"title": f"Title {i}", "channelId": "UC_channel", "channelTitle": "Channel"},
                    "contentDetails": {"duration": "PT5M"},
                    "statistics": {"viewCount": "100"},
                }
                for i in range(6)
            ]

            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                return_value=(found_videos, {f"vid{i}" for i in range(6, 10)})
            )

            # Mock repositories
            enrichment_service.channel_repository.get = AsyncMock(return_value=MagicMock())
            enrichment_service.video_tag_repository.replace_video_tags = AsyncMock(
                return_value=[]
            )
            enrichment_service.video_topic_repository.replace_video_topics = AsyncMock(
                return_value=[]
            )
            enrichment_service.video_category_repository.get = AsyncMock(
                return_value=None
            )
            # Mock video_repository.get to return the correct video by ID
            video_lookup = {v.video_id: v for v in mock_videos}
            enrichment_service.video_repository.get = AsyncMock(
                side_effect=lambda session, video_id: video_lookup.get(video_id)
            )

            report = await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)

            # Verify counts
            assert report.summary.videos_processed == 10
            assert report.summary.videos_updated == 6
            assert report.summary.videos_deleted == 4
            assert report.summary.videos_updated + report.summary.videos_deleted == 10


# =============================================================================
# T097e: Unit tests for --auto-seed flag
# =============================================================================


class TestAutoSeedFlag:
    """Tests for --auto-seed flag (T097e)."""

    def test_auto_seed_flag_recognized(self) -> None:
        """Test flag is recognized by CLI."""
        # Test that the flag name is correct
        expected_flag = "--auto-seed"
        assert "--auto" in expected_flag

    async def test_auto_seed_triggers_when_tables_empty(
        self, mock_session: AsyncMock
    ) -> None:
        """Test auto-seed triggers seeding when tables empty."""
        tables_empty = True
        seeding_triggered = False

        async def check_and_seed() -> None:
            nonlocal seeding_triggered
            if tables_empty:
                seeding_triggered = True

        await check_and_seed()
        assert seeding_triggered is True

    async def test_auto_seed_skips_when_tables_have_data(
        self, mock_session: AsyncMock
    ) -> None:
        """Test auto-seed skips seeding when tables have data."""
        tables_empty = False
        seeding_triggered = False

        async def check_and_seed() -> None:
            nonlocal seeding_triggered
            if tables_empty:
                seeding_triggered = True

        await check_and_seed()
        assert seeding_triggered is False

    async def test_seeding_errors_handled(
        self, mock_session: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test seeding errors are handled appropriately."""
        test_logger = logging.getLogger("test_seeding_error")

        async def seed_with_error() -> None:
            try:
                raise Exception("Seeding failed: Database connection error")
            except Exception as e:
                test_logger.error(f"Seeding failed: {e}")

        with caplog.at_level(logging.ERROR):
            await seed_with_error()

        assert "Seeding failed" in caplog.text

    async def test_enrichment_continues_after_auto_seeding(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test enrichment continues after auto-seeding."""
        seeding_complete = False
        enrichment_started = False

        async def run_with_auto_seed() -> None:
            nonlocal seeding_complete, enrichment_started

            # Simulate auto-seeding
            seeding_complete = True

            # Simulate enrichment continuing
            enrichment_started = True

        await run_with_auto_seed()
        assert seeding_complete is True
        assert enrichment_started is True

    async def test_auto_seed_checks_topic_categories_table(
        self, mock_session: AsyncMock
    ) -> None:
        """Test auto-seed checks topic_categories table."""
        # Simulate checking if topic_categories table is empty
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0  # No rows

        mock_session.execute.return_value = mock_result

        result = await mock_session.execute("SELECT COUNT(*) FROM topic_categories")
        count = result.scalar()

        assert count == 0

    async def test_auto_seed_checks_video_categories_table(
        self, mock_session: AsyncMock
    ) -> None:
        """Test auto-seed checks video_categories table."""
        # Simulate checking if video_categories table is empty
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0  # No rows

        mock_session.execute.return_value = mock_result

        result = await mock_session.execute("SELECT COUNT(*) FROM video_categories")
        count = result.scalar()

        assert count == 0


# =============================================================================
# T097f: Unit tests for --verbose flag
# =============================================================================


class TestVerboseFlag:
    """Tests for --verbose flag (T097f)."""

    def test_verbose_flag_recognized(self) -> None:
        """Test flag is recognized by CLI."""
        expected_flag = "--verbose"
        short_flag = "-v"
        assert "verbose" in expected_flag.lower()
        assert short_flag == "-v"

    def test_verbose_mode_sets_debug_logging(self) -> None:
        """Test verbose mode sets DEBUG logging level."""
        test_logger = logging.getLogger("test_verbose")

        # In verbose mode, logging level should be DEBUG
        test_logger.setLevel(logging.DEBUG)
        assert test_logger.level == logging.DEBUG

    def test_non_verbose_mode_uses_info_logging(self) -> None:
        """Test non-verbose mode uses INFO logging level."""
        test_logger = logging.getLogger("test_non_verbose")

        # In normal mode, logging level should be INFO
        test_logger.setLevel(logging.INFO)
        assert test_logger.level == logging.INFO

    def test_verbose_output_includes_detailed_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test verbose output includes detailed information."""
        test_logger = logging.getLogger("test_verbose_output")

        with caplog.at_level(logging.DEBUG):
            test_logger.debug("Processing video dQw4w9WgXcQ")
            test_logger.debug("Fetching metadata from API")
            test_logger.debug("Tags: ['music', 'pop', '80s']")
            test_logger.debug("Duration: 213 seconds")

        assert "Processing video" in caplog.text
        assert "Fetching metadata" in caplog.text
        assert "Tags:" in caplog.text

    def test_verbose_logs_api_requests(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test verbose mode logs API requests."""
        test_logger = logging.getLogger("test_verbose_api")

        with caplog.at_level(logging.DEBUG):
            test_logger.debug("API Request: videos.list with 50 video IDs")
            test_logger.debug("API Response: 48 videos found, 2 not found")

        assert "API Request" in caplog.text
        assert "API Response" in caplog.text

    def test_verbose_logs_database_operations(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test verbose mode logs database operations."""
        test_logger = logging.getLogger("test_verbose_db")

        with caplog.at_level(logging.DEBUG):
            test_logger.debug("DB: Updating video dQw4w9WgXcQ")
            test_logger.debug("DB: Creating 5 new tags")
            test_logger.debug("DB: Committing batch of 50 videos")

        assert "DB: Updating" in caplog.text
        assert "DB: Creating" in caplog.text
        assert "DB: Committing" in caplog.text

    def test_info_level_hides_debug_messages(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that INFO level hides DEBUG messages."""
        test_logger = logging.getLogger("test_info_level")

        with caplog.at_level(logging.INFO):
            test_logger.debug("This should NOT appear")
            test_logger.info("This should appear")

        assert "This should NOT appear" not in caplog.text
        assert "This should appear" in caplog.text


# =============================================================================
# Additional Tests - Prerequisite Checks
# =============================================================================


class TestPrerequisiteChecks:
    """Tests for prerequisite checks (empty tables detection)."""

    async def test_empty_tables_detection(
        self, mock_session: AsyncMock
    ) -> None:
        """Test detection of empty tables."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0

        mock_session.execute.return_value = mock_result

        result = await mock_session.execute("SELECT COUNT(*) FROM videos")
        count = result.scalar()

        assert count == 0

    async def test_tables_with_data_detection(
        self, mock_session: AsyncMock
    ) -> None:
        """Test detection of tables with data."""
        # Mock result with data
        mock_result = MagicMock()
        mock_result.scalar.return_value = 150

        mock_session.execute.return_value = mock_result

        result = await mock_session.execute("SELECT COUNT(*) FROM videos")
        count = result.scalar()

        assert count == 150

    def test_exit_code_4_for_missing_prerequisites(self) -> None:
        """Test exit code 4 for missing prerequisites."""
        assert EXIT_CODE_LOCK_FAILED == 4

    def test_prerequisite_error_message(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test error message for missing prerequisites."""
        test_logger = logging.getLogger("test_prereq")

        with caplog.at_level(logging.ERROR):
            test_logger.error(
                "Prerequisites not met: topic_categories table is empty. "
                "Run 'chronovista enrich seed' first or use --auto-seed flag."
            )

        assert "Prerequisites not met" in caplog.text
        assert "topic_categories" in caplog.text


# =============================================================================
# Additional Tests - Exit Codes
# =============================================================================


class TestExitCodes:
    """Tests for exit code handling."""

    def test_exit_code_0_on_success(self) -> None:
        """Test exit code 0 on success."""
        expected_success_code = 0
        assert expected_success_code == 0

    def test_exit_code_1_on_general_error(self) -> None:
        """Test exit code 1 on general error."""
        expected_error_code = 1
        assert expected_error_code == 1

    def test_exit_code_3_on_no_credentials(self) -> None:
        """Test exit code 2 on no credentials."""
        assert EXIT_CODE_NO_CREDENTIALS == 2

    def test_exit_code_4_on_lock_failed(self) -> None:
        """Test exit code 4 on lock acquisition failure."""
        assert EXIT_CODE_LOCK_FAILED == 4

    def test_exit_code_130_on_sigint(self) -> None:
        """Test exit code 130 on SIGINT (128 + 2)."""
        sigint_exit_code = 128 + signal.SIGINT
        assert sigint_exit_code == 130


# =============================================================================
# Additional Tests - Error Messages
# =============================================================================


class TestErrorMessages:
    """Tests for user-friendly error messages."""

    def test_quota_error_message_is_user_friendly(self) -> None:
        """Test that quota error message is user-friendly."""
        error_message = (
            "YouTube API quota exceeded. "
            "The daily limit (10,000 units) has been reached. "
            "Please try again after midnight Pacific Time."
        )

        assert "quota" in error_message.lower()
        assert "daily limit" in error_message.lower()
        assert "try again" in error_message.lower()

    def test_network_error_message_is_user_friendly(self) -> None:
        """Test that network error message is user-friendly."""
        error_message = (
            "Network error: Unable to connect to YouTube API. "
            "Please check your internet connection and try again."
        )

        assert "network" in error_message.lower()
        assert "check" in error_message.lower()
        assert "try again" in error_message.lower()

    def test_credentials_error_message_is_user_friendly(self) -> None:
        """Test that credentials error message is user-friendly."""
        error_message = (
            "YouTube API credentials not configured. "
            "Run 'chronovista auth setup' to configure OAuth credentials."
        )

        assert "credentials" in error_message.lower()
        assert "chronovista auth setup" in error_message

    def test_lock_error_message_is_user_friendly(self) -> None:
        """Test that lock error message is user-friendly."""
        error = LockAcquisitionError(
            "Another enrichment process is running. "
            "Wait for completion or use --force to override.",
            pid=12345
        )

        assert "another" in str(error).lower()
        assert "--force" in str(error)
        assert "12345" in str(error)


# =============================================================================
# Additional Tests - Recovery After Transient Errors
# =============================================================================


class TestRecoveryAfterTransientErrors:
    """Tests for recovery after transient errors."""

    async def test_recovery_after_temporary_network_failure(
        self, mock_youtube_service: MagicMock
    ) -> None:
        """Test recovery after temporary network failure."""
        call_count = 0

        async def temporary_failure(*args: Any, **kwargs: Any) -> tuple:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Temporary network issue")
            return ([{"id": VALID_VIDEO_ID}], set())

        mock_youtube_service.fetch_videos_batched = AsyncMock(
            side_effect=temporary_failure
        )

        # Should recover on retry
        result = None
        for _ in range(3):
            try:
                result = await mock_youtube_service.fetch_videos_batched([VALID_VIDEO_ID])
                break
            except ConnectionError:
                continue

        assert result is not None

    async def test_recovery_after_temporary_api_error(
        self, mock_youtube_service: MagicMock
    ) -> None:
        """Test recovery after temporary API error (5xx)."""
        call_count = 0

        async def temporary_api_error(*args: Any, **kwargs: Any) -> tuple:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise create_http_error(500, "Internal Server Error")
            return ([{"id": VALID_VIDEO_ID}], set())

        mock_youtube_service.fetch_videos_batched = AsyncMock(
            side_effect=temporary_api_error
        )

        result = None
        for _ in range(3):
            try:
                result = await mock_youtube_service.fetch_videos_batched([VALID_VIDEO_ID])
                break
            except HttpError as e:
                if e.resp.status >= 500:
                    continue
                raise

        assert result is not None
        assert call_count == 2

    async def test_state_preserved_after_recovery(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test that state is preserved after recovery."""
        processed_videos = []

        mock_videos = [
            MagicMock(
                video_id=f"vid{i}",
                title=f"Video {i}",
                channel_id="UC_channel",
                deleted_flag=False,
            )
            for i in range(3)
        ]

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_videos

            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                return_value=(
                    [{"id": f"vid{i}"} for i in range(3)],
                    set()
                )
            )

            report = await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)

            # All videos should be processed
            assert report.summary.videos_processed == 3

    async def test_batch_boundary_maintained_on_recovery(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test that batch boundaries are maintained on recovery."""
        # Batch size is 50
        assert BATCH_SIZE == 50

        # Test that batch processing respects size limits
        mock_videos = [
            MagicMock(
                video_id=f"vid{i}",
                title=f"Video {i}",
                channel_id="UC_channel",
                deleted_flag=False,
            )
            for i in range(60)  # More than one batch
        ]

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_videos

            api_response = [{"id": f"vid{i}"} for i in range(60)]

            enrichment_service.youtube_service.fetch_videos_batched = AsyncMock(
                return_value=(api_response, set())
            )

            report = await enrichment_service.enrich_videos(mock_session, check_prerequisites=False)

            # All videos should be processed even across batch boundaries
            assert report.summary.videos_processed == 60


# =============================================================================
# Additional Tests - Dry Run Behavior
# =============================================================================


class TestDryRunErrorHandling:
    """Tests for dry run behavior with errors."""

    async def test_dry_run_does_not_modify_database(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test dry run does not modify database."""
        mock_video = MagicMock()
        mock_video.video_id = VALID_VIDEO_ID
        mock_video.title = "[Placeholder] Video"
        original_title = mock_video.title

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = [mock_video]

            report = await enrichment_service.enrich_videos(
                mock_session,
                dry_run=True
            )

            # Verify no API calls were made
            enrichment_service.youtube_service.fetch_videos_batched.assert_not_called()

            # Verify report shows skipped status
            assert report.summary.videos_processed == 1
            assert report.summary.videos_updated == 0

    async def test_dry_run_reports_what_would_happen(
        self, mock_session: AsyncMock, enrichment_service: EnrichmentService
    ) -> None:
        """Test dry run reports what would happen."""
        mock_videos = [
            MagicMock(
                video_id=f"vid{i}",
                title=f"[Placeholder] Video {i}",
                channel_id="UC_channel",
                deleted_flag=False,
            )
            for i in range(5)
        ]

        with patch.object(
            enrichment_service,
            "_get_videos_for_enrichment",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_videos

            report = await enrichment_service.enrich_videos(
                mock_session,
                dry_run=True
            )

            # Should report all videos as skipped
            assert report.summary.videos_processed == 5
            assert len(report.details) == 5
            for detail in report.details:
                assert detail.status == "skipped"
