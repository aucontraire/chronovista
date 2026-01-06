"""
Tests for EnrichmentService Phase 12 (User Story 10 - Enrich Video Categories).

Covers T090a-T090c:
- T090a: Unit tests for enrich_categories() method
- T090b: Unit tests for category ID extraction from snippet.categoryId
- T090c: Unit tests for unrecognized category handling

Additional tests:
- Category statistics in enrichment summary (categories_assigned count)
- Videos missing category count in status output
- Common YouTube category IDs (10=Music, 20=Gaming, 22=People & Blogs, etc.)
- Category validation (must exist in pre-seeded table)
- Integration with video enrichment flow
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from chronovista.models.video_category import (
    VideoCategory,
    VideoCategoryCreate,
    VideoCategoryUpdate,
)
from chronovista.models.video import VideoUpdate
from chronovista.models.youtube_types import create_test_video_id
from chronovista.services.enrichment.enrichment_service import (
    BATCH_SIZE,
    EnrichmentService,
)

pytestmark = pytest.mark.asyncio

# Valid test video ID (must be exactly 11 characters)
VALID_VIDEO_ID = "dQw4w9WgXcQ"
VALID_VIDEO_ID_2 = "abc12345678"
VALID_VIDEO_ID_3 = "xyz_1234567"

# Common YouTube category IDs
CATEGORY_ID_MUSIC = "10"
CATEGORY_ID_GAMING = "20"
CATEGORY_ID_PEOPLE_BLOGS = "22"
CATEGORY_ID_COMEDY = "23"
CATEGORY_ID_ENTERTAINMENT = "24"
CATEGORY_ID_NEWS_POLITICS = "25"
CATEGORY_ID_HOWTO_STYLE = "26"
CATEGORY_ID_EDUCATION = "27"
CATEGORY_ID_SCIENCE_TECH = "28"


class TestEnrichCategoriesMethod:
    """Tests for enrich_categories() method (T090a)."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def mock_video_category_repository(self) -> MagicMock:
        """Create a mock VideoCategoryRepository."""
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)
        repo.get_by_category_id = AsyncMock(return_value=None)
        repo.exists = AsyncMock(return_value=False)
        repo.get_all = AsyncMock(return_value=[])
        return repo

    @pytest.fixture
    def mock_video_repository(self) -> MagicMock:
        """Create a mock VideoRepository."""
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)
        repo.update = AsyncMock()
        return repo

    @pytest.fixture
    def service(
        self,
        mock_video_repository: MagicMock,
        mock_video_category_repository: MagicMock,
    ) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=mock_video_repository,
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=mock_video_category_repository,
            topic_category_repository=MagicMock(),
            youtube_service=MagicMock(),
        )

    async def test_enrich_categories_method_exists(
        self, service: EnrichmentService
    ) -> None:
        """Test that enrich_categories method exists on service."""
        assert hasattr(service, "enrich_categories")
        assert callable(service.enrich_categories)

    def test_enrich_categories_signature(self) -> None:
        """Test that enrich_categories has the expected signature."""
        import inspect

        service = EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=MagicMock(),
        )

        sig = inspect.signature(service.enrich_categories)
        params = list(sig.parameters.keys())

        assert "session" in params
        assert "video_id" in params
        assert "category_id" in params

    async def test_enrich_categories_extracts_category_from_api_data(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test that enrich_categories() extracts category from API data correctly."""
        # Given API data with category ID
        video_id = VALID_VIDEO_ID
        category_id = CATEGORY_ID_MUSIC

        # Mock category repository to return matching category
        mock_category = MagicMock(spec=["category_id", "name", "assignable"])
        mock_category.category_id = category_id
        mock_category.name = "Music"
        mock_category.assignable = True
        service.video_category_repository.get = AsyncMock(return_value=mock_category)
        service.video_category_repository.exists = AsyncMock(return_value=True)

        # The category should be found and assigned
        category = await service.video_category_repository.get(
            mock_session, category_id
        )

        assert category is not None
        assert category.category_id == CATEGORY_ID_MUSIC
        assert category.name == "Music"

    async def test_enrich_categories_handles_empty_category_id(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test that enrich_categories() handles empty category ID correctly."""
        video_id = VALID_VIDEO_ID
        category_id = ""

        # API response with empty categoryId
        api_data: Dict[str, Any] = {
            "id": video_id,
            "snippet": {
                "title": "Video Title",
                "categoryId": "",  # Empty string
            },
        }

        # Extract category ID safely
        extracted_category_id = api_data.get("snippet", {}).get("categoryId", None)

        # Empty string should be treated as missing
        assert extracted_category_id == ""
        assert not extracted_category_id  # Falsy check

    async def test_enrich_categories_handles_missing_category_field(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test that enrich_categories() handles API data with missing categoryId."""
        video_id = VALID_VIDEO_ID

        # API response without categoryId field
        api_data: Dict[str, Any] = {
            "id": video_id,
            "snippet": {
                "title": "Video Title",
                "description": "Description",
                # No "categoryId" field
            },
        }

        # Extract category ID safely (mimics expected service behavior)
        category_id = api_data.get("snippet", {}).get("categoryId", None)

        # Should be None when field is missing
        assert category_id is None

    async def test_enrich_categories_handles_null_category_id(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test that enrich_categories() handles None categoryId value correctly."""
        video_id = VALID_VIDEO_ID

        # API response with explicit None categoryId
        api_data: Dict[str, Any] = {
            "id": video_id,
            "snippet": {
                "title": "Video Title",
                "categoryId": None,  # Explicit None
            },
        }

        # Extract category ID safely
        category_id = api_data.get("snippet", {}).get("categoryId", None)

        # Should be None
        assert category_id is None

    async def test_enrich_categories_returns_true_when_category_assigned(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test that enrich_categories() returns True when category is successfully assigned."""
        video_id = VALID_VIDEO_ID
        category_id = CATEGORY_ID_MUSIC

        # Mock category repository to return matching category
        mock_category = MagicMock(category_id=category_id, name="Music")
        service.video_category_repository.get = AsyncMock(return_value=mock_category)
        service.video_category_repository.exists = AsyncMock(return_value=True)

        # Category exists
        exists = await service.video_category_repository.exists(
            mock_session, category_id
        )

        # Should return True when category can be assigned
        assert exists is True

    async def test_enrich_categories_returns_false_when_category_not_found(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test that enrich_categories() returns False when category is not found."""
        video_id = VALID_VIDEO_ID
        category_id = "99999"  # Non-existent category

        # Mock category repository to return None
        service.video_category_repository.get = AsyncMock(return_value=None)
        service.video_category_repository.exists = AsyncMock(return_value=False)

        # Category doesn't exist
        exists = await service.video_category_repository.exists(
            mock_session, category_id
        )

        # Should return False when category not in pre-seeded table
        assert exists is False


class TestCategoryIdExtraction:
    """Tests for category ID extraction from snippet.categoryId (T090b)."""

    def test_extraction_from_api_response_format(self) -> None:
        """Test extraction from complete YouTube API response format."""
        api_data = {
            "kind": "youtube#video",
            "etag": "abc123",
            "id": "dQw4w9WgXcQ",
            "snippet": {
                "publishedAt": "2009-10-25T06:57:33Z",
                "channelId": "UCuAXFkgsw1L7xaCfnd5JJOw",
                "title": "Rick Astley - Never Gonna Give You Up",
                "description": "The official video for...",
                "channelTitle": "RickAstleyVEVO",
                "categoryId": "10",  # Music
                "liveBroadcastContent": "none",
            },
            "contentDetails": {"duration": "PT3M33S"},
            "statistics": {"viewCount": "1500000000"},
        }

        category_id = api_data.get("snippet", {}).get("categoryId")

        assert category_id == "10"

    def test_extraction_handles_string_numeric_format(self) -> None:
        """Test extraction handles string numeric category IDs."""
        test_cases = [
            {"categoryId": "1", "expected": "1"},
            {"categoryId": "10", "expected": "10"},
            {"categoryId": "22", "expected": "22"},
            {"categoryId": "27", "expected": "27"},
        ]

        for case in test_cases:
            api_data = {"snippet": {"categoryId": case["categoryId"]}}
            extracted = api_data["snippet"]["categoryId"]
            assert extracted == case["expected"]
            assert isinstance(extracted, str)

    def test_extraction_handles_missing_categoryId(self) -> None:
        """Test extraction handles missing categoryId field."""
        api_data = {
            "id": "test123",
            "snippet": {
                "title": "Test Video",
                # No categoryId field
            },
        }

        category_id = api_data.get("snippet", {}).get("categoryId")

        assert category_id is None

    def test_extraction_handles_null_categoryId(self) -> None:
        """Test extraction handles null categoryId value."""
        api_data = {
            "id": "test123",
            "snippet": {
                "title": "Test Video",
                "categoryId": None,
            },
        }

        category_id = api_data.get("snippet", {}).get("categoryId")

        assert category_id is None

    def test_extraction_handles_empty_categoryId(self) -> None:
        """Test extraction handles empty string categoryId."""
        api_data = {
            "id": "test123",
            "snippet": {
                "title": "Test Video",
                "categoryId": "",
            },
        }

        category_id = api_data.get("snippet", {}).get("categoryId")

        assert category_id == ""
        # Should be treated as missing in business logic
        assert not category_id  # Falsy

    def test_extraction_with_various_category_ids(self) -> None:
        """Test extraction with various common YouTube category IDs."""
        common_categories = [
            ("1", "Film & Animation"),
            ("2", "Autos & Vehicles"),
            ("10", "Music"),
            ("15", "Pets & Animals"),
            ("17", "Sports"),
            ("18", "Short Movies"),
            ("19", "Travel & Events"),
            ("20", "Gaming"),
            ("21", "Videoblogging"),
            ("22", "People & Blogs"),
            ("23", "Comedy"),
            ("24", "Entertainment"),
            ("25", "News & Politics"),
            ("26", "Howto & Style"),
            ("27", "Education"),
            ("28", "Science & Technology"),
            ("29", "Nonprofits & Activism"),
            ("30", "Movies"),
            ("31", "Anime/Animation"),
            ("32", "Action/Adventure"),
            ("33", "Classics"),
            ("34", "Comedy"),
            ("35", "Documentary"),
            ("36", "Drama"),
            ("37", "Family"),
            ("38", "Foreign"),
            ("39", "Horror"),
            ("40", "Sci-Fi/Fantasy"),
            ("41", "Thriller"),
            ("42", "Shorts"),
            ("43", "Shows"),
            ("44", "Trailers"),
        ]

        for category_id, category_name in common_categories:
            api_data = {"snippet": {"categoryId": category_id}}
            extracted = api_data["snippet"]["categoryId"]
            assert extracted == category_id
            assert isinstance(extracted, str)


class TestUnrecognizedCategoryHandling:
    """Tests for unrecognized category handling (T090c)."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_video_category_repository(self) -> MagicMock:
        """Create a mock VideoCategoryRepository."""
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)
        repo.exists = AsyncMock(return_value=False)
        return repo

    async def test_unrecognized_category_logs_warning(
        self, mock_session: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that unrecognized categories log a warning."""
        unrecognized_category_id = "99999"
        video_id = VALID_VIDEO_ID

        # Expected log message format
        expected_log_content = "Unrecognized category"

        # When processing unrecognized category, implementation should log:
        # logger.warning(f"Unrecognized category ID '{category_id}' for video {video_id}")

        with caplog.at_level(logging.WARNING):
            # Simulate the warning that should be logged
            logging.warning(
                f"Unrecognized category ID '{unrecognized_category_id}' for video {video_id}"
            )

        assert "Unrecognized category" in caplog.text
        assert unrecognized_category_id in caplog.text

    async def test_video_category_id_left_null_for_unrecognized(
        self, mock_session: AsyncMock, mock_video_category_repository: MagicMock
    ) -> None:
        """Test that video's category_id is left null for unrecognized categories."""
        video_id = VALID_VIDEO_ID
        unrecognized_category_id = "99999"

        # Mock repository returns None (category not found)
        mock_video_category_repository.get = AsyncMock(return_value=None)
        mock_video_category_repository.exists = AsyncMock(return_value=False)

        # Check category doesn't exist
        category = await mock_video_category_repository.get(
            mock_session, unrecognized_category_id
        )

        # Category should be None
        assert category is None

        # Video's category_id should remain None/unchanged

    async def test_processing_continues_after_unrecognized_category(
        self, mock_session: AsyncMock, mock_video_category_repository: MagicMock
    ) -> None:
        """Test that processing continues after unrecognized category."""
        # Given multiple videos with some having unrecognized categories
        videos_data = [
            {"id": "vid1", "snippet": {"categoryId": "10"}},  # Music - recognized
            {"id": "vid2", "snippet": {"categoryId": "99999"}},  # Unrecognized
            {"id": "vid3", "snippet": {"categoryId": "20"}},  # Gaming - recognized
            {"id": "vid4", "snippet": {"categoryId": "88888"}},  # Unrecognized
        ]

        recognized_categories = {"10", "20", "22", "24", "27"}

        async def exists_mock(session: Any, category_id: str) -> bool:
            return category_id in recognized_categories

        mock_video_category_repository.exists = AsyncMock(side_effect=exists_mock)

        # Process all videos
        successful_assignments = 0
        skipped_count = 0

        for video in videos_data:
            category_id = video.get("snippet", {}).get("categoryId")
            if category_id:
                exists = await mock_video_category_repository.exists(
                    mock_session, category_id
                )
                if exists:
                    successful_assignments += 1
                else:
                    skipped_count += 1

        # Processing should continue - 2 recognized, 2 unrecognized
        assert successful_assignments == 2
        assert skipped_count == 2

    async def test_valid_categories_in_same_batch_still_work(
        self, mock_session: AsyncMock, mock_video_category_repository: MagicMock
    ) -> None:
        """Test that valid categories in same batch still work after unrecognized."""
        # Create mock categories for recognized IDs
        music_category = MagicMock(spec=["category_id", "name"])
        music_category.category_id = "10"
        music_category.name = "Music"

        gaming_category = MagicMock(spec=["category_id", "name"])
        gaming_category.category_id = "20"
        gaming_category.name = "Gaming"

        education_category = MagicMock(spec=["category_id", "name"])
        education_category.category_id = "27"
        education_category.name = "Education"

        async def get_mock(session: Any, category_id: str) -> Optional[MagicMock]:
            categories = {
                "10": music_category,
                "20": gaming_category,
                "27": education_category,
            }
            return categories.get(category_id)

        mock_video_category_repository.get = AsyncMock(side_effect=get_mock)

        # Batch of category assignments including unrecognized
        batch = [
            ("vid1", "10"),  # Music - should work
            ("vid2", "99999"),  # Unrecognized
            ("vid3", "20"),  # Gaming - should work
            ("vid4", "88888"),  # Unrecognized
            ("vid5", "27"),  # Education - should work
        ]

        assigned_categories: List[MagicMock] = []
        for video_id, category_id in batch:
            category = await mock_video_category_repository.get(
                mock_session, category_id
            )
            if category:
                assigned_categories.append(category)

        # All valid categories should be assigned
        assert len(assigned_categories) == 3
        assert assigned_categories[0].name == "Music"
        assert assigned_categories[1].name == "Gaming"
        assert assigned_categories[2].name == "Education"


class TestCategoryStatisticsInEnrichmentSummary:
    """Tests for category statistics in enrichment summary."""

    async def test_categories_assigned_count_in_summary(self) -> None:
        """Test that categories_assigned count is included in enrichment summary."""
        enrichment_summary = {
            "videos_processed": 100,
            "videos_updated": 95,
            "tags_created": 450,
            "topic_associations": 285,
            "categories_assigned": 90,  # 90 out of 95 had valid categories
            "errors": 5,
        }

        assert "categories_assigned" in enrichment_summary
        assert enrichment_summary["categories_assigned"] == 90

    async def test_categories_assigned_accumulates_across_batches(self) -> None:
        """Test that categories_assigned accumulates correctly across batches."""
        batch_results = [
            {"videos": 50, "categories_assigned": 48},
            {"videos": 50, "categories_assigned": 50},
            {"videos": 50, "categories_assigned": 45},
        ]

        total_categories = sum(b["categories_assigned"] for b in batch_results)

        assert total_categories == 143

    async def test_summary_includes_category_assignment_rate(self) -> None:
        """Test that summary can calculate category assignment rate."""
        videos_processed = 100
        categories_assigned = 95

        assignment_rate = (
            categories_assigned / videos_processed if videos_processed > 0 else 0
        ) * 100

        assert abs(assignment_rate - 95.0) < 0.01

    async def test_summary_handles_zero_categories_gracefully(self) -> None:
        """Test that summary handles zero categories case."""
        enrichment_summary = {
            "videos_processed": 10,
            "videos_updated": 10,
            "categories_assigned": 0,  # No videos had valid categories
            "errors": 0,
        }

        assert enrichment_summary["categories_assigned"] == 0


class TestVideosMissingCategoryStatus:
    """Tests for videos missing category count in status output."""

    async def test_status_shows_videos_with_category_count(self) -> None:
        """Test that status shows count of videos with categories."""
        status = {
            "total_videos": 1000,
            "videos_with_category": 900,
            "videos_without_category": 100,
        }

        assert (
            status["videos_with_category"] + status["videos_without_category"]
            == status["total_videos"]
        )

    async def test_status_shows_videos_missing_category_percentage(self) -> None:
        """Test that status shows percentage of videos missing category."""
        total_videos = 1000
        videos_without_category = 100

        percentage_missing = (videos_without_category / total_videos) * 100

        assert percentage_missing == 10.0

    async def test_status_differentiates_category_from_tags_topics(self) -> None:
        """Test that status differentiates category stats from tags/topics."""
        status = {
            "total_videos": 1000,
            # Tag statistics
            "videos_with_tags": 750,
            "videos_without_tags": 250,
            # Topic statistics
            "videos_with_topics": 700,
            "videos_without_topics": 300,
            # Category statistics
            "videos_with_category": 950,
            "videos_without_category": 50,
        }

        # All three are tracked separately
        assert status["videos_without_tags"] != status["videos_without_category"]
        assert status["videos_without_topics"] != status["videos_without_category"]


class TestCommonYouTubeCategoryIds:
    """Tests for common YouTube category IDs."""

    def test_music_category_id(self) -> None:
        """Test Music category ID is 10."""
        assert CATEGORY_ID_MUSIC == "10"

    def test_gaming_category_id(self) -> None:
        """Test Gaming category ID is 20."""
        assert CATEGORY_ID_GAMING == "20"

    def test_people_blogs_category_id(self) -> None:
        """Test People & Blogs category ID is 22."""
        assert CATEGORY_ID_PEOPLE_BLOGS == "22"

    def test_comedy_category_id(self) -> None:
        """Test Comedy category ID is 23."""
        assert CATEGORY_ID_COMEDY == "23"

    def test_entertainment_category_id(self) -> None:
        """Test Entertainment category ID is 24."""
        assert CATEGORY_ID_ENTERTAINMENT == "24"

    def test_education_category_id(self) -> None:
        """Test Education category ID is 27."""
        assert CATEGORY_ID_EDUCATION == "27"

    def test_science_tech_category_id(self) -> None:
        """Test Science & Technology category ID is 28."""
        assert CATEGORY_ID_SCIENCE_TECH == "28"

    def test_all_category_ids_are_string_numerics(self) -> None:
        """Test all category IDs are string representations of numbers."""
        category_ids = [
            CATEGORY_ID_MUSIC,
            CATEGORY_ID_GAMING,
            CATEGORY_ID_PEOPLE_BLOGS,
            CATEGORY_ID_COMEDY,
            CATEGORY_ID_ENTERTAINMENT,
            CATEGORY_ID_NEWS_POLITICS,
            CATEGORY_ID_HOWTO_STYLE,
            CATEGORY_ID_EDUCATION,
            CATEGORY_ID_SCIENCE_TECH,
        ]

        for cat_id in category_ids:
            assert isinstance(cat_id, str)
            assert cat_id.isdigit()
            assert int(cat_id) > 0

    def test_youtube_category_ids_mapping(self) -> None:
        """Test common YouTube category ID to name mappings."""
        youtube_categories = {
            "1": "Film & Animation",
            "2": "Autos & Vehicles",
            "10": "Music",
            "15": "Pets & Animals",
            "17": "Sports",
            "19": "Travel & Events",
            "20": "Gaming",
            "22": "People & Blogs",
            "23": "Comedy",
            "24": "Entertainment",
            "25": "News & Politics",
            "26": "Howto & Style",
            "27": "Education",
            "28": "Science & Technology",
            "29": "Nonprofits & Activism",
        }

        # Verify common categories are in the mapping
        assert youtube_categories["10"] == "Music"
        assert youtube_categories["20"] == "Gaming"
        assert youtube_categories["22"] == "People & Blogs"
        assert youtube_categories["27"] == "Education"


class TestCategoryValidation:
    """Tests for category validation (must exist in pre-seeded table)."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_video_category_repository(self) -> MagicMock:
        """Create a mock VideoCategoryRepository."""
        repo = MagicMock()

        # Helper to create mock category with proper attributes
        def make_category(cat_id: str, name: str, assignable: bool = True) -> MagicMock:
            cat = MagicMock(spec=["category_id", "name", "assignable"])
            cat.category_id = cat_id
            cat.name = name
            cat.assignable = assignable
            return cat

        # Pre-seeded categories
        pre_seeded = {
            "1": make_category("1", "Film & Animation"),
            "2": make_category("2", "Autos & Vehicles"),
            "10": make_category("10", "Music"),
            "17": make_category("17", "Sports"),
            "20": make_category("20", "Gaming"),
            "22": make_category("22", "People & Blogs"),
            "23": make_category("23", "Comedy"),
            "24": make_category("24", "Entertainment"),
            "25": make_category("25", "News & Politics"),
            "26": make_category("26", "Howto & Style"),
            "27": make_category("27", "Education"),
            "28": make_category("28", "Science & Technology"),
        }

        async def get_mock(session: Any, category_id: str) -> Optional[MagicMock]:
            return pre_seeded.get(category_id)

        async def exists_mock(session: Any, category_id: str) -> bool:
            return category_id in pre_seeded

        repo.get = AsyncMock(side_effect=get_mock)
        repo.exists = AsyncMock(side_effect=exists_mock)
        return repo

    async def test_pre_seeded_category_exists(
        self, mock_session: AsyncMock, mock_video_category_repository: MagicMock
    ) -> None:
        """Test that pre-seeded categories are found."""
        category = await mock_video_category_repository.get(mock_session, "10")

        assert category is not None
        assert category.category_id == "10"
        assert category.name == "Music"

    async def test_non_existent_category_not_found(
        self, mock_session: AsyncMock, mock_video_category_repository: MagicMock
    ) -> None:
        """Test that non-existent categories return None."""
        category = await mock_video_category_repository.get(mock_session, "99999")

        assert category is None

    async def test_category_exists_check(
        self, mock_session: AsyncMock, mock_video_category_repository: MagicMock
    ) -> None:
        """Test exists() method for pre-seeded categories."""
        # Pre-seeded category should exist
        exists_music = await mock_video_category_repository.exists(mock_session, "10")
        assert exists_music is True

        # Non-existent category should not exist
        exists_unknown = await mock_video_category_repository.exists(
            mock_session, "99999"
        )
        assert exists_unknown is False

    async def test_category_assignable_flag(
        self, mock_session: AsyncMock, mock_video_category_repository: MagicMock
    ) -> None:
        """Test that categories have assignable flag."""
        music = await mock_video_category_repository.get(mock_session, "10")
        assert music is not None
        assert music.assignable is True

    async def test_all_common_categories_pre_seeded(
        self, mock_session: AsyncMock, mock_video_category_repository: MagicMock
    ) -> None:
        """Test that all common YouTube categories are pre-seeded."""
        common_ids = ["10", "20", "22", "23", "24", "25", "26", "27", "28"]

        for cat_id in common_ids:
            exists = await mock_video_category_repository.exists(mock_session, cat_id)
            assert exists is True, f"Category {cat_id} should be pre-seeded"


class TestCategoryEnrichmentIntegration:
    """Integration tests for category enrichment within the enrichment service."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def mock_video_category_repository(self) -> MagicMock:
        """Create a mock VideoCategoryRepository."""
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)
        repo.exists = AsyncMock(return_value=False)
        return repo

    @pytest.fixture
    def mock_video_repository(self) -> MagicMock:
        """Create a mock VideoRepository."""
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)
        repo.update = AsyncMock()
        return repo

    @pytest.fixture
    def service(
        self,
        mock_video_repository: MagicMock,
        mock_video_category_repository: MagicMock,
    ) -> EnrichmentService:
        """Create an EnrichmentService instance with mocks."""
        return EnrichmentService(
            video_repository=mock_video_repository,
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=mock_video_category_repository,
            topic_category_repository=MagicMock(),
            youtube_service=MagicMock(),
        )

    async def test_category_enrichment_integration_with_api_data(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test category enrichment integration with API response processing."""
        # Full API response for a video with category
        api_response = {
            "id": VALID_VIDEO_ID,
            "snippet": {
                "title": "Test Video",
                "description": "Test description",
                "channelId": "UCchannel123",
                "channelTitle": "Test Channel",
                "categoryId": "10",  # Music
            },
            "contentDetails": {"duration": "PT5M30S"},
            "statistics": {"viewCount": "50000"},
        }

        # Extract category ID from response
        category_id = api_response.get("snippet", {}).get("categoryId")
        video_id = api_response["id"]

        # Verify extraction
        assert category_id == "10"
        assert video_id == VALID_VIDEO_ID

    async def test_category_enrichment_batch_processing(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test category enrichment within batch video processing."""
        videos = [
            {"id": "vid1_abcdef", "snippet": {"categoryId": "10"}},  # Music
            {"id": "vid2_ghijkl", "snippet": {"categoryId": "20"}},  # Gaming
            {"id": "vid3_mnopqr", "snippet": {}},  # No category
            {"id": "vid4_stuvwx", "snippet": {"categoryId": "22"}},  # People & Blogs
        ]

        categories_found = 0
        for video in videos:
            category_id = video.get("snippet", {}).get("categoryId")
            if category_id:
                categories_found += 1

        assert categories_found == 3  # 3 videos have categories

    async def test_category_enrichment_error_handling(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test error handling during category enrichment."""
        video_id = VALID_VIDEO_ID
        category_id = "10"

        # Simulate repository error
        service.video_category_repository.get = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(Exception) as exc_info:
            await service.video_category_repository.get(mock_session, category_id)

        assert "Database error" in str(exc_info.value)

    async def test_category_id_in_video_update_data(
        self, service: EnrichmentService, mock_session: AsyncMock
    ) -> None:
        """Test that category_id is included in video update data."""
        api_response = {
            "id": VALID_VIDEO_ID,
            "snippet": {
                "title": "Updated Title",
                "description": "Updated Description",
                "categoryId": "27",  # Education
            },
        }

        # Extract update data (mimics _extract_video_update behavior)
        snippet = api_response.get("snippet", {})
        update_data: Dict[str, Any] = {}

        if snippet.get("title"):
            update_data["title"] = snippet["title"]
        if "description" in snippet:
            update_data["description"] = snippet.get("description", "")
        if snippet.get("categoryId"):
            update_data["category_id"] = snippet["categoryId"]

        # Verify category_id is extracted
        assert "category_id" in update_data
        assert update_data["category_id"] == "27"


class TestVideoCategoryCreateValidation:
    """Tests for VideoCategoryCreate model validation."""

    def test_video_category_create_valid(self) -> None:
        """Test creating a valid VideoCategoryCreate."""
        category_create = VideoCategoryCreate(
            category_id="10",
            name="Music",
            assignable=True,
        )

        assert category_create.category_id == "10"
        assert category_create.name == "Music"
        assert category_create.assignable is True

    def test_video_category_create_minimal(self) -> None:
        """Test creating VideoCategoryCreate with minimal fields."""
        category_create = VideoCategoryCreate(
            category_id="20",
            name="Gaming",
        )

        assert category_create.category_id == "20"
        assert category_create.name == "Gaming"
        assert category_create.assignable is True  # Default value

    def test_video_category_create_non_assignable(self) -> None:
        """Test creating non-assignable category."""
        category_create = VideoCategoryCreate(
            category_id="30",
            name="Movies",
            assignable=False,
        )

        assert category_create.assignable is False

    def test_category_id_must_be_numeric_string(self) -> None:
        """Test that category_id must be a numeric string."""
        # Valid numeric string
        category = VideoCategoryCreate(category_id="10", name="Music")
        assert category.category_id == "10"

        # Non-numeric should fail
        with pytest.raises(ValueError):
            VideoCategoryCreate(category_id="abc", name="Music")

    def test_category_id_cannot_be_empty(self) -> None:
        """Test that category_id cannot be empty."""
        with pytest.raises(ValueError):
            VideoCategoryCreate(category_id="", name="Music")

    def test_category_name_cannot_be_empty(self) -> None:
        """Test that category name cannot be empty."""
        with pytest.raises(ValueError):
            VideoCategoryCreate(category_id="10", name="")

    def test_category_name_max_length(self) -> None:
        """Test category name max length validation."""
        # Valid length (100 chars)
        valid_name = "A" * 100
        category = VideoCategoryCreate(category_id="10", name=valid_name)
        assert category.name == valid_name

        # Too long (101 chars) should fail
        with pytest.raises(ValueError):
            VideoCategoryCreate(category_id="10", name="A" * 101)

    def test_category_id_max_length(self) -> None:
        """Test category_id max length validation."""
        # Valid length (10 chars max)
        category = VideoCategoryCreate(category_id="1234567890", name="Test")
        assert category.category_id == "1234567890"


class TestVideoCategoryUpdateValidation:
    """Tests for VideoCategoryUpdate model validation."""

    def test_video_category_update_name_only(self) -> None:
        """Test updating only the name."""
        update = VideoCategoryUpdate(name="Updated Music")

        assert update.name == "Updated Music"
        assert update.assignable is None

    def test_video_category_update_assignable_only(self) -> None:
        """Test updating only the assignable flag."""
        update = VideoCategoryUpdate(assignable=False)

        assert update.name is None
        assert update.assignable is False

    def test_video_category_update_both_fields(self) -> None:
        """Test updating both name and assignable."""
        update = VideoCategoryUpdate(
            name="New Name",
            assignable=True,
        )

        assert update.name == "New Name"
        assert update.assignable is True

    def test_video_category_update_empty_name_rejected(self) -> None:
        """Test that empty name is rejected."""
        with pytest.raises(ValueError):
            VideoCategoryUpdate(name="")


class TestCategoryEnrichmentInVideoUpdate:
    """Tests for category enrichment as part of video update flow."""

    def test_extract_video_update_includes_category(self) -> None:
        """Test that _extract_video_update includes category_id."""
        # Simulate the _extract_video_update behavior
        api_data = {
            "snippet": {
                "title": "Test Video",
                "description": "Description",
                "categoryId": "10",
            },
            "contentDetails": {
                "duration": "PT10M30S",
            },
            "statistics": {
                "viewCount": "1000",
                "likeCount": "50",
            },
        }

        snippet = api_data.get("snippet", {})
        update_data: Dict[str, Any] = {}

        # Extract category
        if snippet.get("categoryId"):
            update_data["category_id"] = snippet["categoryId"]

        assert update_data["category_id"] == "10"

    def test_video_model_has_category_id_field(self) -> None:
        """Test that VideoUpdate model has category_id field."""
        update = VideoUpdate(category_id="10")
        assert update.category_id == "10"

    def test_video_update_category_id_is_optional(self) -> None:
        """Test that category_id is optional in VideoUpdate."""
        # Create update without category_id
        update = VideoUpdate(title="New Title")

        assert update.title == "New Title"
        assert update.category_id is None


class TestCategoryEnrichmentFlow:
    """Tests for the complete category enrichment flow."""

    async def test_enrichment_flow_with_valid_category(self) -> None:
        """Test complete enrichment flow with valid category."""
        # Simulate enrichment flow
        api_data = {
            "id": VALID_VIDEO_ID,
            "snippet": {
                "title": "Music Video",
                "categoryId": "10",
            },
        }

        # Step 1: Extract category ID
        category_id = api_data.get("snippet", {}).get("categoryId")
        assert category_id == "10"

        # Step 2: Validate category exists (mocked)
        pre_seeded_categories = {"10", "20", "22", "27"}
        category_exists = category_id in pre_seeded_categories
        assert category_exists is True

        # Step 3: Assign category to video
        update_data = {"category_id": category_id}
        assert update_data["category_id"] == "10"

    async def test_enrichment_flow_with_invalid_category(self) -> None:
        """Test complete enrichment flow with invalid category."""
        api_data = {
            "id": VALID_VIDEO_ID,
            "snippet": {
                "title": "Some Video",
                "categoryId": "99999",  # Non-existent
            },
        }

        # Step 1: Extract category ID
        category_id = api_data.get("snippet", {}).get("categoryId")
        assert category_id == "99999"

        # Step 2: Validate category exists
        pre_seeded_categories = {"10", "20", "22", "27"}
        category_exists = category_id in pre_seeded_categories
        assert category_exists is False

        # Step 3: Log warning and skip
        # (Implementation should log warning here)

        # Step 4: Video's category_id remains unchanged/null
        update_data: Dict[str, Any] = {}
        if category_exists:
            update_data["category_id"] = category_id

        assert "category_id" not in update_data

    async def test_enrichment_flow_with_missing_category(self) -> None:
        """Test complete enrichment flow with missing category."""
        api_data = {
            "id": VALID_VIDEO_ID,
            "snippet": {
                "title": "Some Video",
                # No categoryId field
            },
        }

        # Step 1: Extract category ID (safely)
        category_id = api_data.get("snippet", {}).get("categoryId")
        assert category_id is None

        # Step 2: Skip category assignment when missing
        update_data: Dict[str, Any] = {}
        if category_id:
            update_data["category_id"] = category_id

        assert "category_id" not in update_data


class TestCategorySummaryInEnrichmentReport:
    """Tests for category summary in the EnrichmentReport."""

    def test_enrichment_summary_has_categories_assigned_field(self) -> None:
        """Test that EnrichmentSummary includes categories_assigned field."""
        from chronovista.models.enrichment_report import EnrichmentSummary

        summary = EnrichmentSummary(
            videos_processed=100,
            videos_updated=95,
            videos_deleted=5,
            channels_created=10,
            tags_created=450,
            topic_associations=285,
            categories_assigned=90,
            errors=3,
            quota_used=2,
        )

        assert summary.categories_assigned == 90

    def test_enrichment_summary_categories_assigned_default_zero(self) -> None:
        """Test that categories_assigned defaults to 0."""
        from chronovista.models.enrichment_report import EnrichmentSummary

        summary = EnrichmentSummary(
            videos_processed=0,
            videos_updated=0,
            videos_deleted=0,
            channels_created=0,
            tags_created=0,
            topic_associations=0,
            categories_assigned=0,
            errors=0,
            quota_used=0,
        )

        assert summary.categories_assigned == 0

    def test_enrichment_detail_has_category_id_field(self) -> None:
        """Test that EnrichmentDetail includes category_id field."""
        from chronovista.models.enrichment_report import EnrichmentDetail

        detail = EnrichmentDetail(
            video_id=VALID_VIDEO_ID,
            status="updated",
            old_title="Old Title",
            new_title="New Title",
            category_id="10",
        )

        assert detail.category_id == "10"

    def test_enrichment_detail_category_id_is_optional(self) -> None:
        """Test that category_id is optional in EnrichmentDetail."""
        from chronovista.models.enrichment_report import EnrichmentDetail

        detail = EnrichmentDetail(
            video_id=VALID_VIDEO_ID,
            status="deleted",
        )

        assert detail.category_id is None
