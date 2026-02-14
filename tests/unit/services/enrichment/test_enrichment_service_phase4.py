"""
Tests for EnrichmentService Phase 4 (API Enrichment).

Covers T035a-g: batch video fetch, video field updates, channel creation,
quota estimation, and enrichment flow.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.models.enums import AvailabilityStatus
from chronovista.models.api_responses import YouTubeVideoResponse
from chronovista.models.enrichment_report import EnrichmentReport, EnrichmentSummary
from chronovista.services.enrichment.enrichment_service import (
    BATCH_SIZE,
    EnrichmentService,
    estimate_quota_cost,
    is_placeholder_channel_name,
    is_placeholder_video_title,
    parse_iso8601_duration,
)


def make_video_response(video_id: str, **kwargs: Any) -> YouTubeVideoResponse:
    """
    Create a YouTubeVideoResponse from a video ID and optional kwargs.

    This helper ensures tests return proper Pydantic objects instead of dicts.
    The snippet field requires publishedAt and channelId, so we provide defaults.
    """
    data: Dict[str, Any] = {"id": video_id, **kwargs}

    # If snippet is provided, ensure required fields are present
    if "snippet" in data:
        snippet = data["snippet"]
        if isinstance(snippet, dict):
            if "publishedAt" not in snippet:
                snippet["publishedAt"] = datetime.now(timezone.utc).isoformat()
            if "channelId" not in snippet:
                snippet["channelId"] = "UC_test_channel"

    return YouTubeVideoResponse.model_validate(data)

pytestmark = pytest.mark.asyncio


class TestParseISO8601Duration:
    """Tests for parse_iso8601_duration helper function (T035c)."""

    def test_parse_hours_minutes_seconds(self) -> None:
        """Test parsing PT1H2M3S format."""
        assert parse_iso8601_duration("PT1H2M3S") == 3723

    def test_parse_minutes_seconds(self) -> None:
        """Test parsing PT5M30S format."""
        assert parse_iso8601_duration("PT5M30S") == 330

    def test_parse_seconds_only(self) -> None:
        """Test parsing PT45S format."""
        assert parse_iso8601_duration("PT45S") == 45

    def test_parse_hours_only(self) -> None:
        """Test parsing PT2H format."""
        assert parse_iso8601_duration("PT2H") == 7200

    def test_parse_days_hours(self) -> None:
        """Test parsing P1DT2H format (1 day + 2 hours)."""
        assert parse_iso8601_duration("P1DT2H") == 86400 + 7200

    def test_parse_zero_duration(self) -> None:
        """Test parsing zero duration."""
        assert parse_iso8601_duration("P0D") == 0
        assert parse_iso8601_duration("PT0S") == 0

    def test_parse_empty_string(self) -> None:
        """Test parsing empty string."""
        assert parse_iso8601_duration("") == 0

    def test_parse_invalid_format(self) -> None:
        """Test parsing invalid format returns 0."""
        assert parse_iso8601_duration("invalid") == 0
        assert parse_iso8601_duration("1:30:45") == 0


class TestEstimateQuotaCost:
    """Tests for estimate_quota_cost helper function (T035e)."""

    def test_zero_videos(self) -> None:
        """Test quota cost for zero videos."""
        assert estimate_quota_cost(0) == 0

    def test_single_video(self) -> None:
        """Test quota cost for single video."""
        assert estimate_quota_cost(1) == 1

    def test_batch_size_videos(self) -> None:
        """Test quota cost for exactly one batch."""
        assert estimate_quota_cost(50) == 1

    def test_multiple_batches(self) -> None:
        """Test quota cost for multiple batches."""
        assert estimate_quota_cost(100) == 2
        assert estimate_quota_cost(150) == 3

    def test_partial_batch(self) -> None:
        """Test quota cost with partial last batch."""
        assert estimate_quota_cost(51) == 2
        assert estimate_quota_cost(99) == 2

    def test_large_video_count(self) -> None:
        """Test quota cost for large video count."""
        assert estimate_quota_cost(1000) == 20


class TestPlaceholderDetection:
    """Tests for placeholder detection functions (T035c)."""

    def test_is_placeholder_video_title_true(self) -> None:
        """Test detecting placeholder video titles."""
        assert is_placeholder_video_title("[Placeholder] Video dQw4w9WgXcQ") is True
        assert is_placeholder_video_title("[Placeholder] Video abc123XYZ_-") is True

    def test_is_placeholder_video_title_false(self) -> None:
        """Test detecting non-placeholder video titles."""
        assert is_placeholder_video_title("Never Gonna Give You Up") is False
        assert is_placeholder_video_title("[Other] Video Title") is False
        assert is_placeholder_video_title("") is False

    def test_is_placeholder_channel_name_true(self) -> None:
        """Test detecting placeholder channel names."""
        assert is_placeholder_channel_name("[Placeholder] Unknown Channel") is True
        assert is_placeholder_channel_name("[Unknown Channel] UCtest123") is True

    def test_is_placeholder_channel_name_false(self) -> None:
        """Test detecting non-placeholder channel names."""
        assert is_placeholder_channel_name("RickAstleyVEVO") is False
        assert is_placeholder_channel_name("My Cool Channel") is False


class TestEnrichmentServiceInit:
    """Tests for EnrichmentService initialization."""

    def test_init_with_all_dependencies(self) -> None:
        """Test initialization with all required dependencies."""
        service = EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=MagicMock(),
        )
        assert service is not None
        assert service.lock is not None


class TestExtractVideoUpdate:
    """Tests for _extract_video_update method (T035c)."""

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
        """Test extracting title and description."""
        api_data = {
            "snippet": {
                "title": "Test Video Title",
                "description": "Test description",
            }
        }
        update = service._extract_video_update_from_dict(api_data)
        assert update["title"] == "Test Video Title"
        assert update["description"] == "Test description"

    def test_extract_duration(self, service: EnrichmentService) -> None:
        """Test extracting duration."""
        api_data = {
            "snippet": {},
            "contentDetails": {"duration": "PT10M30S"},
        }
        update = service._extract_video_update_from_dict(api_data)
        assert update["duration"] == 630

    def test_extract_upload_date(self, service: EnrichmentService) -> None:
        """Test extracting upload date."""
        api_data = {
            "snippet": {"publishedAt": "2024-01-15T14:30:00Z"},
        }
        update = service._extract_video_update_from_dict(api_data)
        assert update["upload_date"] == datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)

    def test_extract_statistics(self, service: EnrichmentService) -> None:
        """Test extracting view/like/comment counts."""
        api_data = {
            "snippet": {},
            "statistics": {
                "viewCount": "1000000",
                "likeCount": "50000",
                "commentCount": "2500",
            },
        }
        update = service._extract_video_update_from_dict(api_data)
        assert update["view_count"] == 1000000
        assert update["like_count"] == 50000
        assert update["comment_count"] == 2500

    def test_extract_category_id(self, service: EnrichmentService) -> None:
        """Test extracting category ID."""
        api_data = {
            "snippet": {"categoryId": "10"},
        }
        update = service._extract_video_update_from_dict(api_data)
        assert update["category_id"] == "10"

    def test_extract_content_restrictions(self, service: EnrichmentService) -> None:
        """Test extracting content restrictions."""
        api_data = {
            "snippet": {},
            "status": {
                "madeForKids": True,
                "selfDeclaredMadeForKids": True,
            },
        }
        update = service._extract_video_update_from_dict(api_data)
        assert update["made_for_kids"] is True
        assert update["self_declared_made_for_kids"] is True

    def test_extract_languages(self, service: EnrichmentService) -> None:
        """Test extracting language settings."""
        api_data = {
            "snippet": {
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en-US",
            },
        }
        update = service._extract_video_update_from_dict(api_data)
        assert update["default_language"] == "en"
        assert update["default_audio_language"] == "en-US"

    def test_extract_empty_api_data(self, service: EnrichmentService) -> None:
        """Test extracting from empty API data."""
        api_data: dict[str, Any] = {}
        update = service._extract_video_update_from_dict(api_data)
        assert len(update) == 0


@pytest.mark.asyncio
class TestEnrichVideos:
    """Tests for enrich_videos method (T035b)."""

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
        service.fetch_videos_batched = AsyncMock(return_value=([], set()))
        return service

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

    async def test_enrich_no_videos_found(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test enrichment when no videos need enrichment."""
        with patch.object(
            service, "_get_videos_for_enrichment", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = []

            report = await service.enrich_videos(mock_session, check_prerequisites=False)

            assert report.summary.videos_processed == 0
            assert report.summary.videos_updated == 0
            assert len(report.details) == 0

    async def test_enrich_dry_run(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test enrichment in dry run mode."""
        mock_video = MagicMock()
        mock_video.video_id = "dQw4w9WgXcQ"
        mock_video.title = "[Placeholder] Video dQw4w9WgXcQ"

        with patch.object(
            service, "_get_videos_for_enrichment", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = [mock_video]

            report = await service.enrich_videos(mock_session, dry_run=True)

            assert report.summary.videos_processed == 1
            assert report.summary.videos_updated == 0
            assert report.summary.quota_used == 0
            assert len(report.details) == 1
            assert report.details[0].status == "skipped"

    async def test_enrich_deleted_video(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test enrichment marks video as deleted when API returns 404."""
        mock_video = MagicMock()
        mock_video.video_id = "deleted123"
        mock_video.title = "[Placeholder] Video deleted123"
        mock_video.availability_status = AvailabilityStatus.AVAILABLE

        with patch.object(
            service, "_get_videos_for_enrichment", new_callable=AsyncMock
        ) as mock_get, patch.object(
            service.youtube_service, "fetch_videos_batched", new=AsyncMock(return_value=([], {"deleted123"}))
        ), patch.object(
            service.video_repository, "get", new=AsyncMock(return_value=mock_video)
        ):
            mock_get.return_value = [mock_video]

            report = await service.enrich_videos(mock_session, check_prerequisites=False)

            assert report.summary.videos_deleted == 1
            assert mock_video.availability_status == AvailabilityStatus.UNAVAILABLE

    async def test_enrich_updates_video(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test enrichment updates video with API data."""
        mock_video = MagicMock()
        mock_video.video_id = "dQw4w9WgXcQ"
        mock_video.title = "[Placeholder] Video dQw4w9WgXcQ"
        mock_video.channel_id = "UCplaceholder"

        api_response = make_video_response(
            "dQw4w9WgXcQ",
            snippet={
                "title": "Never Gonna Give You Up",
                "description": "Music video",
                "channelId": "UCuAXFkgsw1L7xaCfnd5JJOw",
                "channelTitle": "RickAstleyVEVO",
                "categoryId": "10",
            },
            contentDetails={"duration": "PT3M33S"},
            statistics={
                "viewCount": "1500000000",
                "likeCount": "15000000",
            },
        )

        with patch.object(
            service, "_get_videos_for_enrichment", new_callable=AsyncMock
        ) as mock_get, patch.object(
            service.youtube_service, "fetch_videos_batched", new=AsyncMock(return_value=([api_response], set()))
        ), patch.object(
            service.channel_repository, "get", new=AsyncMock(return_value=None)
        ), patch.object(
            service.channel_repository, "create", new=AsyncMock()
        ), patch.object(
            service.video_repository, "get", new=AsyncMock(return_value=mock_video)
        ):
            mock_get.return_value = [mock_video]

            report = await service.enrich_videos(mock_session, check_prerequisites=False)

            assert report.summary.videos_updated == 1
            assert mock_video.title == "Never Gonna Give You Up"

    async def test_enrich_respects_limit(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test that enrichment respects the limit parameter."""
        with patch.object(
            service, "_get_videos_for_enrichment", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = []

            await service.enrich_videos(mock_session, limit=10)

            # Verify limit was passed
            call_args = mock_get.call_args
            assert call_args[0][2] == 10  # limit is third argument


@pytest.mark.asyncio
class TestEnsureChannelExists:
    """Tests for _ensure_channel_exists method (T035d)."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        return AsyncMock()

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

    async def test_creates_new_channel(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test creating a new channel when it doesn't exist."""
        with patch.object(
            service.channel_repository, "get", new=AsyncMock(return_value=None)
        ), patch.object(
            service.channel_repository, "create", new=AsyncMock()
        ) as mock_create:
            created = await service._ensure_channel_exists(
                mock_session,
                "UCuAXFkgsw1L7xaCfnd5JJOw",
                "RickAstleyVEVO",
            )

            assert created is True
            mock_create.assert_called_once()

    async def test_updates_placeholder_channel(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test updating a placeholder channel with real name."""
        mock_existing = MagicMock()
        mock_existing.title = "[Placeholder] Unknown Channel"

        with patch.object(
            service.channel_repository, "get", new=AsyncMock(return_value=mock_existing)
        ):
            created = await service._ensure_channel_exists(
                mock_session,
                "UCuAXFkgsw1L7xaCfnd5JJOw",
                "RickAstleyVEVO",
            )

            assert created is False
            assert mock_existing.title == "RickAstleyVEVO"

    async def test_skips_existing_real_channel(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test skipping update when channel already has real name."""
        mock_existing = MagicMock()
        mock_existing.title = "RickAstleyVEVO"

        with patch.object(
            service.channel_repository, "get", new=AsyncMock(return_value=mock_existing)
        ):
            created = await service._ensure_channel_exists(
                mock_session,
                "UCuAXFkgsw1L7xaCfnd5JJOw",
                "RickAstleyVEVO",
            )

            assert created is False
            # Title should not have been changed
            assert mock_existing.title == "RickAstleyVEVO"


class TestBatchSize:
    """Tests for batch size constant."""

    def test_batch_size_is_50(self) -> None:
        """Test that BATCH_SIZE is 50 (YouTube API limit)."""
        assert BATCH_SIZE == 50
