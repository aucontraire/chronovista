"""
Tests for user video models using factory pattern.

Comprehensive tests for UserVideo Pydantic models with validation,
serialization, and business logic testing using factory-boy for DRY principles.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.user_video import (
    GoogleTakeoutWatchHistoryItem,
    UserVideo,
    UserVideoBase,
    UserVideoCreate,
    UserVideoSearchFilters,
    UserVideoStatistics,
    UserVideoUpdate,
)
from tests.factories.user_video_factory import (
    GoogleTakeoutWatchHistoryItemFactory,
    UserVideoBaseFactory,
    UserVideoCreateFactory,
    UserVideoFactory,
    UserVideoSearchFiltersFactory,
    UserVideoStatisticsFactory,
    UserVideoTestData,
    UserVideoUpdateFactory,
    create_batch_user_videos,
    create_google_takeout_item,
    create_user_video,
    create_user_video_base,
    create_user_video_create,
    create_user_video_search_filters,
    create_user_video_statistics,
    create_user_video_update,
)


class TestUserVideoBaseFactory:
    """Test UserVideoBase model with factory pattern."""

    def test_user_video_base_creation(self):
        """Test basic UserVideoBase creation from factory."""
        user_video = UserVideoBaseFactory.build()

        assert isinstance(user_video, UserVideoBase)
        assert user_video.user_id == "test_user_123"
        assert user_video.video_id == "dQw4w9WgXcQ"
        assert user_video.completion_percentage == 85.5
        assert user_video.rewatch_count == 1
        assert user_video.liked is True
        assert user_video.disliked is False
        assert user_video.saved_to_playlist is True

    def test_user_video_base_custom_values(self):
        """Test UserVideoBase with custom values."""
        custom_user_video = UserVideoBaseFactory.build(
            user_id="custom_user",
            video_id="9bZkp7q19f0",
            completion_percentage=50.0,
            liked=False,
        )

        assert custom_user_video.user_id == "custom_user"
        assert custom_user_video.video_id == "9bZkp7q19f0"
        assert custom_user_video.completion_percentage == 50.0
        assert custom_user_video.liked is False

    @pytest.mark.parametrize("valid_user_id", UserVideoTestData.VALID_USER_IDS)
    def test_user_video_base_valid_user_ids(self, valid_user_id):
        """Test UserVideoBase with valid user IDs."""
        user_video = UserVideoBaseFactory.build(user_id=valid_user_id)
        assert user_video.user_id == valid_user_id.strip()

    @pytest.mark.parametrize("invalid_user_id", UserVideoTestData.INVALID_USER_IDS)
    def test_user_video_base_invalid_user_ids(self, invalid_user_id):
        """Test UserVideoBase validation with invalid user IDs."""
        with pytest.raises(ValidationError):
            UserVideoBaseFactory.build(user_id=invalid_user_id)

    @pytest.mark.parametrize("valid_video_id", UserVideoTestData.VALID_VIDEO_IDS)
    def test_user_video_base_valid_video_ids(self, valid_video_id):
        """Test UserVideoBase with valid video IDs."""
        user_video = UserVideoBaseFactory.build(video_id=valid_video_id)
        assert user_video.video_id == valid_video_id.strip()

    @pytest.mark.parametrize("invalid_video_id", UserVideoTestData.INVALID_VIDEO_IDS)
    def test_user_video_base_invalid_video_ids(self, invalid_video_id):
        """Test UserVideoBase validation with invalid video IDs."""
        with pytest.raises(ValidationError):
            UserVideoBaseFactory.build(video_id=invalid_video_id)

    @pytest.mark.parametrize(
        "valid_percentage", UserVideoTestData.VALID_COMPLETION_PERCENTAGES
    )
    def test_user_video_base_valid_completion_percentages(self, valid_percentage):
        """Test UserVideoBase with valid completion percentages."""
        user_video = UserVideoBaseFactory.build(completion_percentage=valid_percentage)
        assert user_video.completion_percentage == valid_percentage

    @pytest.mark.parametrize(
        "invalid_percentage", UserVideoTestData.INVALID_COMPLETION_PERCENTAGES
    )
    def test_user_video_base_invalid_completion_percentages(self, invalid_percentage):
        """Test UserVideoBase validation with invalid completion percentages."""
        with pytest.raises(ValidationError):
            UserVideoBaseFactory.build(completion_percentage=invalid_percentage)

    def test_user_video_base_model_dump(self):
        """Test UserVideoBase model_dump functionality."""
        user_video = UserVideoBaseFactory.build()
        data = user_video.model_dump()

        assert isinstance(data, dict)
        assert data["user_id"] == "test_user_123"
        assert data["video_id"] == "dQw4w9WgXcQ"
        assert data["completion_percentage"] == 85.5

    def test_user_video_base_model_validate(self):
        """Test UserVideoBase model_validate functionality."""
        data = {
            "user_id": "validate_user",
            "video_id": "3tmd-ClpJxA",
            "watched_at": datetime(2023, 12, 1, 10, 30, 0, tzinfo=timezone.utc),
            "completion_percentage": 95.0,
            "rewatch_count": 2,
            "liked": True,
            "disliked": False,
            "saved_to_playlist": True,
        }

        user_video = UserVideoBase.model_validate(data)
        assert user_video.user_id == "validate_user"
        assert user_video.video_id == "3tmd-ClpJxA"
        assert user_video.completion_percentage == 95.0


class TestUserVideoCreateFactory:
    """Test UserVideoCreate model with factory pattern."""

    def test_user_video_create_creation(self):
        """Test basic UserVideoCreate creation from factory."""
        user_video = UserVideoCreateFactory.build()

        assert isinstance(user_video, UserVideoCreate)
        assert user_video.user_id == "test_user_456"
        assert user_video.video_id == "9bZkp7q19f0"
        assert user_video.completion_percentage == 75.0

    def test_user_video_create_convenience_function(self):
        """Test convenience function for UserVideoCreate."""
        user_video = create_user_video_create(
            user_id="convenience_user", completion_percentage=60.0
        )

        assert user_video.user_id == "convenience_user"
        assert user_video.completion_percentage == 60.0


class TestUserVideoUpdateFactory:
    """Test UserVideoUpdate model with factory pattern."""

    def test_user_video_update_creation(self):
        """Test basic UserVideoUpdate creation from factory with explicit values."""
        user_video_update = UserVideoUpdateFactory.build(
            completion_percentage=90.0, rewatch_count=2, liked=True
        )

        assert isinstance(user_video_update, UserVideoUpdate)
        assert user_video_update.completion_percentage == 90.0
        assert user_video_update.rewatch_count == 2
        assert user_video_update.liked is True

    def test_user_video_update_partial_data(self):
        """Test UserVideoUpdate with partial data."""
        update = UserVideoUpdateFactory.build(
            completion_percentage=80.0,
            liked=None,  # Only update some fields
            disliked=None,
        )

        assert update.completion_percentage == 80.0
        assert update.liked is None
        assert update.disliked is None

    def test_user_video_update_convenience_function(self):
        """Test convenience function for UserVideoUpdate."""
        update = create_user_video_update(rewatch_count=5)
        assert update.rewatch_count == 5


class TestUserVideoFactory:
    """Test UserVideo model with factory pattern."""

    def test_user_video_creation(self):
        """Test basic UserVideo creation from factory."""
        user_video = UserVideoFactory.build()

        assert isinstance(user_video, UserVideo)
        assert user_video.user_id == "test_user_789"
        assert user_video.video_id == "3tmd-ClpJxA"
        assert user_video.completion_percentage == 95.0
        assert hasattr(user_video, "created_at")
        assert hasattr(user_video, "updated_at")

    def test_user_video_timestamps(self):
        """Test UserVideo with custom timestamps."""
        created_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        updated_time = datetime(2023, 12, 1, tzinfo=timezone.utc)

        user_video = UserVideoFactory.build(
            created_at=created_time, updated_at=updated_time
        )

        assert user_video.created_at == created_time
        assert user_video.updated_at == updated_time

    def test_user_video_convenience_function(self):
        """Test convenience function for UserVideo."""
        user_video = create_user_video(rewatch_count=10)
        assert user_video.rewatch_count == 10


class TestGoogleTakeoutWatchHistoryItemFactory:
    """Test GoogleTakeoutWatchHistoryItem model with factory pattern."""

    def test_google_takeout_item_creation(self):
        """Test basic GoogleTakeoutWatchHistoryItem creation from factory."""
        takeout_item = GoogleTakeoutWatchHistoryItemFactory.build()

        assert isinstance(takeout_item, GoogleTakeoutWatchHistoryItem)
        assert takeout_item.header == "YouTube"
        assert "Rick Astley" in takeout_item.title
        assert "youtube.com" in takeout_item.titleUrl
        assert len(takeout_item.subtitles) > 0

    @pytest.mark.parametrize("valid_url", UserVideoTestData.VALID_YOUTUBE_URLS)
    def test_google_takeout_item_valid_urls(self, valid_url):
        """Test GoogleTakeoutWatchHistoryItem with valid YouTube URLs."""
        takeout_item = GoogleTakeoutWatchHistoryItemFactory.build(titleUrl=valid_url)
        assert takeout_item.titleUrl == valid_url

    @pytest.mark.parametrize("invalid_url", UserVideoTestData.INVALID_YOUTUBE_URLS)
    def test_google_takeout_item_invalid_urls(self, invalid_url):
        """Test GoogleTakeoutWatchHistoryItem validation with invalid URLs."""
        with pytest.raises(ValidationError):
            GoogleTakeoutWatchHistoryItemFactory.build(titleUrl=invalid_url)

    @pytest.mark.parametrize("valid_title", UserVideoTestData.VALID_TAKEOUT_TITLES)
    def test_google_takeout_item_valid_titles(self, valid_title):
        """Test GoogleTakeoutWatchHistoryItem with valid titles."""
        takeout_item = GoogleTakeoutWatchHistoryItemFactory.build(title=valid_title)
        assert takeout_item.title == valid_title.strip()

    @pytest.mark.parametrize("invalid_title", UserVideoTestData.INVALID_TAKEOUT_TITLES)
    def test_google_takeout_item_invalid_titles(self, invalid_title):
        """Test GoogleTakeoutWatchHistoryItem validation with invalid titles."""
        with pytest.raises(ValidationError, match="Title cannot be empty"):
            GoogleTakeoutWatchHistoryItemFactory.build(title=invalid_title)

    def test_google_takeout_item_extract_video_id(self):
        """Test video ID extraction from different URL formats."""
        # Test youtube.com/watch format
        item1 = GoogleTakeoutWatchHistoryItemFactory.build(
            titleUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        assert item1.extract_video_id() == "dQw4w9WgXcQ"

        # Test youtu.be format
        item2 = GoogleTakeoutWatchHistoryItemFactory.build(
            titleUrl="https://youtu.be/9bZkp7q19f0"
        )
        assert item2.extract_video_id() == "9bZkp7q19f0"

        # Test embed format
        item3 = GoogleTakeoutWatchHistoryItemFactory.build(
            titleUrl="https://www.youtube.com/embed/3tmd-ClpJxA"
        )
        assert item3.extract_video_id() == "3tmd-ClpJxA"

    def test_google_takeout_item_extract_video_id_edge_cases(self):
        """Test video ID extraction edge cases and invalid URLs."""
        # Test URL with no query parameters (should return None)
        item1 = GoogleTakeoutWatchHistoryItemFactory.build(
            titleUrl="https://www.youtube.com/invalid"
        )
        assert item1.extract_video_id() is None

        # Test playlist URL (passes validation but no video ID)
        item2 = GoogleTakeoutWatchHistoryItemFactory.build(
            titleUrl="https://www.youtube.com/playlist?list=PLtest"
        )
        assert item2.extract_video_id() is None

        # Test channel URL (passes validation but no video ID)
        item3 = GoogleTakeoutWatchHistoryItemFactory.build(
            titleUrl="https://www.youtube.com/channel/UCtest"
        )
        assert item3.extract_video_id() is None

        # Test malformed URL that causes exception
        item4 = GoogleTakeoutWatchHistoryItemFactory.build(
            titleUrl="https://youtube.com/watch?v="  # Empty video ID
        )
        result = item4.extract_video_id()
        assert result in [None, ""]  # Could be None or empty string

    def test_google_takeout_item_extract_channel_info(self):
        """Test channel info extraction."""
        takeout_item = GoogleTakeoutWatchHistoryItemFactory.build()
        channel_info = takeout_item.extract_channel_info()

        assert channel_info is not None
        assert "name" in channel_info
        assert "url" in channel_info
        assert channel_info["name"] == "Rick Astley"

    def test_google_takeout_item_extract_channel_info_edge_cases(self):
        """Test channel info extraction with edge cases."""
        # Test with empty subtitles list
        item1 = GoogleTakeoutWatchHistoryItemFactory.build(subtitles=[])
        assert item1.extract_channel_info() is None

        # Test with malformed subtitle data
        item2 = GoogleTakeoutWatchHistoryItemFactory.build(
            subtitles=[{"invalid": "data"}]
        )
        channel_info = item2.extract_channel_info()
        assert channel_info is not None
        assert channel_info["name"] is None
        assert channel_info["url"] is None

    def test_google_takeout_item_extract_channel_id(self):
        """Test channel ID extraction from channel URLs."""
        # Test with valid channel URL
        item1 = GoogleTakeoutWatchHistoryItemFactory.build(
            subtitles=[
                {
                    "name": "Test Channel",
                    "url": "https://www.youtube.com/channel/UC123456789",
                }
            ]
        )
        assert item1.extract_channel_id() == "UC123456789"

        # Test with no subtitles
        item2 = GoogleTakeoutWatchHistoryItemFactory.build(subtitles=[])
        assert item2.extract_channel_id() is None

        # Test with invalid channel URL
        item3 = GoogleTakeoutWatchHistoryItemFactory.build(
            subtitles=[
                {"name": "Test Channel", "url": "https://www.youtube.com/user/testuser"}
            ]
        )
        assert item3.extract_channel_id() is None

    def test_google_takeout_item_get_watch_action(self):
        """Test watch action extraction."""
        # Test "watched" action
        item1 = GoogleTakeoutWatchHistoryItemFactory.build(title="Watched Test Video")
        assert item1.get_watch_action() == "watched"

        # Test "viewed" action
        item2 = GoogleTakeoutWatchHistoryItemFactory.build(
            title="Viewed Python Tutorial"
        )
        assert item2.get_watch_action() == "viewed"

        # Test "visited" action
        item3 = GoogleTakeoutWatchHistoryItemFactory.build(title="Visited Channel Page")
        assert item3.get_watch_action() == "visited"

        # Test unknown action
        item4 = GoogleTakeoutWatchHistoryItemFactory.build(title="Some Random Title")
        assert item4.get_watch_action() == "unknown"

    def test_google_takeout_item_get_video_title(self):
        """Test clean video title extraction."""
        # Test "Watched" prefix removal
        item1 = GoogleTakeoutWatchHistoryItemFactory.build(
            title="Watched Amazing Python Tutorial"
        )
        assert item1.get_video_title() == "Amazing Python Tutorial"

        # Test "Viewed" prefix removal
        item2 = GoogleTakeoutWatchHistoryItemFactory.build(
            title="Viewed Machine Learning Course"
        )
        assert item2.get_video_title() == "Machine Learning Course"

        # Test "Visited" prefix removal
        item3 = GoogleTakeoutWatchHistoryItemFactory.build(title="Visited Tech Channel")
        assert item3.get_video_title() == "Tech Channel"

        # Test title with no prefix
        item4 = GoogleTakeoutWatchHistoryItemFactory.build(title="Regular Video Title")
        assert item4.get_video_title() == "Regular Video Title"

    def test_google_takeout_item_to_user_video_create(self):
        """Test conversion to UserVideoCreate."""
        takeout_item = GoogleTakeoutWatchHistoryItemFactory.build()
        user_video = takeout_item.to_user_video_create("test_user")

        assert user_video is not None
        assert user_video.user_id == "test_user"
        assert user_video.video_id == "dQw4w9WgXcQ"
        assert user_video.watched_at is not None

    def test_google_takeout_item_to_user_video_create_edge_cases(self):
        """Test conversion to UserVideoCreate with edge cases."""
        # Test with invalid video URL (should return None)
        item1 = GoogleTakeoutWatchHistoryItemFactory.build(
            titleUrl="https://www.youtube.com/playlist?list=PLtest"
        )
        result1 = item1.to_user_video_create("test_user")
        assert result1 is None

        # Test with malformed timestamp
        item2 = GoogleTakeoutWatchHistoryItemFactory.build(time="invalid-timestamp")
        result2 = item2.to_user_video_create("test_user")
        if result2 is not None:  # Might still create if video ID is valid
            assert result2.watched_at is None  # But timestamp should be None

        # Test with valid timestamp parsing
        item3 = GoogleTakeoutWatchHistoryItemFactory.build(time="2023-12-01T15:30:45Z")
        result3 = item3.to_user_video_create("test_user")
        assert result3 is not None
        assert result3.watched_at is not None

    def test_google_takeout_item_convenience_function(self):
        """Test convenience function for GoogleTakeoutWatchHistoryItem."""
        item = create_google_takeout_item(title="Custom Video Title")
        assert "Custom Video Title" in item.title


class TestUserVideoSearchFiltersFactory:
    """Test UserVideoSearchFilters model with factory pattern."""

    def test_user_video_search_filters_creation(self):
        """Test basic UserVideoSearchFilters creation from factory."""
        filters = UserVideoSearchFiltersFactory.build()

        assert isinstance(filters, UserVideoSearchFilters)
        assert filters.user_ids == ["user1", "user2", "user3"]
        assert filters.video_ids == ["dQw4w9WgXcQ", "9bZkp7q19f0", "3tmd-ClpJxA"]
        assert filters.min_completion_percentage == 50.0
        assert filters.liked_only is True

    def test_user_video_search_filters_partial(self):
        """Test UserVideoSearchFilters with partial data."""
        filters = UserVideoSearchFilters(user_ids=["single_user"])

        assert filters.user_ids == ["single_user"]
        assert filters.liked_only is None
        assert filters.disliked_only is None

    def test_user_video_search_filters_convenience_function(self):
        """Test convenience function for UserVideoSearchFilters."""
        filters = create_user_video_search_filters(min_completion_percentage=75.0)
        assert filters.min_completion_percentage == 75.0


class TestUserVideoStatisticsFactory:
    """Test UserVideoStatistics model with factory pattern."""

    def test_user_video_statistics_creation(self):
        """Test basic UserVideoStatistics creation from factory."""
        stats = UserVideoStatisticsFactory.build()

        assert isinstance(stats, UserVideoStatistics)
        assert stats.total_videos == 150
        assert stats.total_watch_time == 18000
        assert stats.average_completion == 78.5
        assert stats.liked_count == 45
        assert stats.watch_streak_days == 14

    def test_user_video_statistics_custom_values(self):
        """Test UserVideoStatistics with custom values."""
        stats = UserVideoStatisticsFactory.build(
            total_videos=200, liked_count=60, watch_streak_days=30
        )

        assert stats.total_videos == 200
        assert stats.liked_count == 60
        assert stats.watch_streak_days == 30

    def test_user_video_statistics_convenience_function(self):
        """Test convenience function for UserVideoStatistics."""
        stats = create_user_video_statistics(total_videos=500)
        assert stats.total_videos == 500


class TestBatchOperations:
    """Test batch operations and advanced factory usage."""

    def test_create_batch_user_videos(self):
        """Test creating multiple UserVideo instances."""
        videos = create_batch_user_videos(count=3)

        assert len(videos) == 3
        assert all(isinstance(video, UserVideo) for video in videos)

        # Check that different values are generated
        user_ids = [video.user_id for video in videos]
        video_ids = [video.video_id for video in videos]

        assert len(set(user_ids)) > 1  # Should have different user IDs
        assert len(set(video_ids)) > 1  # Should have different video IDs

    def test_model_serialization_round_trip(self):
        """Test model serialization and deserialization."""
        original = UserVideoFactory.build()

        # Serialize to dict
        data = original.model_dump()

        # Deserialize back to model
        restored = UserVideo.model_validate(data)

        assert original.user_id == restored.user_id
        assert original.video_id == restored.video_id
        assert original.completion_percentage == restored.completion_percentage
        assert original.created_at == restored.created_at

    def test_factory_inheritance_behavior(self):
        """Test that factories properly handle model inheritance."""
        base_video = UserVideoBaseFactory.build()
        create_video = UserVideoCreateFactory.build()
        full_video = UserVideoFactory.build()

        # All should have the core attributes
        for video in [base_video, create_video, full_video]:
            assert hasattr(video, "user_id")
            assert hasattr(video, "video_id")
            assert hasattr(video, "completion_percentage")

        # Only full video should have timestamps
        assert hasattr(full_video, "created_at")
        assert hasattr(full_video, "updated_at")
        assert not hasattr(base_video, "created_at")
        assert not hasattr(create_video, "created_at")


class TestValidationEdgeCases:
    """Test edge cases and validation scenarios."""

    def test_none_values_handling(self):
        """Test handling of None values in optional fields."""
        user_video = UserVideoBaseFactory.build(
            watched_at=None, watch_duration=None, completion_percentage=None
        )

        assert user_video.watched_at is None
        assert user_video.watch_duration is None
        assert user_video.completion_percentage is None

    def test_boundary_values(self):
        """Test boundary values for validation."""
        # Test minimum valid values
        min_video = UserVideoBaseFactory.build(
            completion_percentage=0.0, rewatch_count=0, watch_duration=0
        )
        assert min_video.completion_percentage == 0.0
        assert min_video.rewatch_count == 0
        assert min_video.watch_duration == 0

        # Test maximum valid values
        max_video = UserVideoBaseFactory.build(
            completion_percentage=100.0, video_id="abcdefghijk"  # Valid 11-char length
        )
        assert max_video.completion_percentage == 100.0
        assert len(max_video.video_id) == 11

    def test_model_config_validation(self):
        """Test model configuration validation behaviors."""
        user_video = UserVideoFactory.build()

        # Test validate_assignment works
        user_video.completion_percentage = 50.0
        assert user_video.completion_percentage == 50.0

        # Test that invalid assignment raises validation error
        with pytest.raises(ValidationError):
            user_video.completion_percentage = 150.0  # Invalid value


class TestAdditionalValidationEdgeCases:
    """Test additional validation edge cases and model configuration."""

    def test_user_video_from_attributes_config(self):
        """Test from_attributes configuration for ORM compatibility."""
        # Test that UserVideo can be created from ORM-like attributes
        video_data = {
            "user_id": "orm_user",
            "video_id": "dQw4w9WgXcQ",
            "watched_at": datetime(2023, 12, 1, 10, 30, 0, tzinfo=timezone.utc),
            "completion_percentage": 85.0,
            "rewatch_count": 2,
            "liked": True,
            "disliked": False,
            "saved_to_playlist": True,
            "created_at": datetime(2023, 12, 1, 10, 35, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2023, 12, 1, 11, 30, 0, tzinfo=timezone.utc),
        }

        user_video = UserVideo.model_validate(video_data)
        assert user_video.user_id == "orm_user"
        assert user_video.completion_percentage == 85.0
        assert user_video.created_at is not None
        assert user_video.updated_at is not None

    def test_user_video_update_none_validation(self):
        """Test UserVideoUpdate handles None values correctly."""
        # Test all None values (should be valid)
        update = UserVideoUpdate(
            watched_at=None,
            watch_duration=None,
            completion_percentage=None,
            rewatch_count=None,
            liked=None,
            disliked=None,
            saved_to_playlist=None,
        )

        assert update.watched_at is None
        assert update.completion_percentage is None
        assert update.liked is None

    def test_user_video_update_selective_fields(self):
        """Test UserVideoUpdate with only some fields set."""
        update = UserVideoUpdateFactory.build(completion_percentage=75.0, liked=True)

        assert update.completion_percentage == 75.0
        assert update.liked is True
        assert update.watched_at is None  # Default None
        assert update.disliked is None  # Default None

    @pytest.mark.parametrize(
        "invalid_completion", [-0.1, -50.0, 100.1, 150.0, float("inf")]
    )
    def test_completion_percentage_comprehensive_validation(self, invalid_completion):
        """Test comprehensive completion percentage validation."""
        # Test in UserVideoBase/Create
        with pytest.raises(ValidationError):
            UserVideoCreateFactory.build(completion_percentage=invalid_completion)

        # Test in UserVideoUpdate
        with pytest.raises(ValidationError):
            UserVideoUpdateFactory.build(completion_percentage=invalid_completion)

    def test_user_video_search_filters_comprehensive(self):
        """Test UserVideoSearchFilters with all fields."""
        filters = UserVideoSearchFiltersFactory.build(
            user_ids=["user1", "user2", "user3"],
            video_ids=["dQw4w9WgXcQ", "9bZkp7q19f0"],
            watched_after=datetime(2023, 1, 1, tzinfo=timezone.utc),
            watched_before=datetime(2023, 12, 31, tzinfo=timezone.utc),
            min_watch_duration=300,
            min_completion_percentage=50.0,
            liked_only=True,
            disliked_only=False,
            playlist_saved_only=True,
            min_rewatch_count=2,
            created_after=datetime(2023, 6, 1, tzinfo=timezone.utc),
            created_before=datetime(2023, 11, 30, tzinfo=timezone.utc),
        )

        assert len(filters.user_ids) == 3
        assert len(filters.video_ids) == 2
        assert filters.min_completion_percentage == 50.0
        assert filters.liked_only is True
        assert filters.disliked_only is False
        assert filters.playlist_saved_only is True
        assert filters.min_rewatch_count == 2

    def test_user_video_statistics_comprehensive(self):
        """Test UserVideoStatistics with all fields."""
        stats = UserVideoStatisticsFactory.build(
            total_videos=500,
            total_watch_time=36000,  # 10 hours
            average_completion=82.5,
            liked_count=150,
            disliked_count=25,
            playlist_saved_count=75,
            rewatch_count=100,
            unique_videos=450,
            most_watched_date=datetime(2023, 11, 15, tzinfo=timezone.utc),
            watch_streak_days=21,
        )

        assert stats.total_videos == 500
        assert stats.total_watch_time == 36000
        assert stats.average_completion == 82.5
        assert stats.liked_count == 150
        assert stats.disliked_count == 25
        assert stats.playlist_saved_count == 75
        assert stats.rewatch_count == 100
        assert stats.unique_videos == 450
        assert stats.most_watched_date is not None
        assert stats.watch_streak_days == 21

    def test_google_takeout_comprehensive_url_validation(self):
        """Test comprehensive URL validation for GoogleTakeoutWatchHistoryItem."""
        # Test valid YouTube URLs that should pass
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/9bZkp7q19f0",
            "https://www.youtube.com/embed/3tmd-ClpJxA",
            "https://youtube.com/watch?v=test123",
            "https://m.youtube.com/watch?v=mobile123",
        ]

        for url in valid_urls:
            item = GoogleTakeoutWatchHistoryItemFactory.build(titleUrl=url)
            assert item.titleUrl == url

    def test_model_serialization_comprehensive(self):
        """Test comprehensive model serialization scenarios."""
        # Test UserVideo with all fields
        original = UserVideoFactory.build(
            user_id="serialize_test",
            video_id="dQw4w9WgXcQ",  # Valid 11-character video ID
            watched_at=datetime(2023, 12, 1, 15, 30, tzinfo=timezone.utc),
            watch_duration=450,
            completion_percentage=87.5,
            rewatch_count=3,
            liked=True,
            disliked=False,
            saved_to_playlist=True,
        )

        # Test model_dump
        data = original.model_dump()
        assert data["user_id"] == "serialize_test"
        assert data["completion_percentage"] == 87.5
        assert data["rewatch_count"] == 3

        # Test round-trip serialization
        restored = UserVideo.model_validate(data)
        assert restored.user_id == original.user_id
        assert restored.video_id == original.video_id
        assert restored.completion_percentage == original.completion_percentage
        assert restored.liked == original.liked
