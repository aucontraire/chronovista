"""
Tests for video models using factory pattern.

Comprehensive tests for Video Pydantic models with validation,
serialization, and business logic testing using factory-boy for DRY principles.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.video import (
    Video,
    VideoBase,
    VideoCreate,
    VideoSearchFilters,
    VideoStatistics,
    VideoUpdate,
    VideoWithChannel,
)
from tests.factories.video_factory import (
    VideoBaseFactory,
    VideoCreateFactory,
    VideoFactory,
    VideoSearchFiltersFactory,
    VideoStatisticsFactory,
    VideoTestData,
    VideoUpdateFactory,
    VideoWithChannelFactory,
    create_batch_videos,
    create_video,
    create_video_base,
    create_video_create,
    create_video_search_filters,
    create_video_statistics,
    create_video_update,
    create_video_with_channel,
)


class TestVideoBaseFactory:
    """Test VideoBase model with factory pattern."""

    def test_video_base_creation(self):
        """Test basic VideoBase creation from factory."""
        video = VideoBaseFactory.build()

        assert isinstance(video, VideoBase)
        assert video.video_id == "dQw4w9WgXcQ"
        assert video.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert video.title == "Rick Astley - Never Gonna Give You Up (Official Video)"
        assert video.duration == 213
        assert video.default_language == "en"
        assert video.made_for_kids is False
        assert video.deleted_flag is False

    def test_video_base_custom_values(self):
        """Test VideoBase with custom values."""
        custom_video = VideoBaseFactory.build(
            video_id="9bZkp7q19f0",  # Valid 11-char video ID
            title="Custom Test Video",
            duration=600,
            made_for_kids=True,
            view_count=50000,
        )

        assert custom_video.video_id == "9bZkp7q19f0"
        assert custom_video.title == "Custom Test Video"
        assert custom_video.duration == 600
        assert custom_video.made_for_kids is True
        assert custom_video.view_count == 50000

    @pytest.mark.parametrize("valid_video_id", VideoTestData.VALID_VIDEO_IDS)
    def test_video_base_valid_video_ids(self, valid_video_id):
        """Test VideoBase with valid video IDs."""
        video = VideoBaseFactory.build(video_id=valid_video_id)
        assert video.video_id == valid_video_id.strip()

    @pytest.mark.parametrize("invalid_video_id", VideoTestData.INVALID_VIDEO_IDS)
    def test_video_base_invalid_video_ids(self, invalid_video_id):
        """Test VideoBase validation with invalid video IDs."""
        with pytest.raises(ValidationError):
            VideoBaseFactory.build(video_id=invalid_video_id)

    @pytest.mark.parametrize("valid_channel_id", VideoTestData.VALID_CHANNEL_IDS)
    def test_video_base_valid_channel_ids(self, valid_channel_id):
        """Test VideoBase with valid channel IDs."""
        video = VideoBaseFactory.build(channel_id=valid_channel_id)
        assert video.channel_id == valid_channel_id.strip()

    @pytest.mark.parametrize("invalid_channel_id", VideoTestData.INVALID_CHANNEL_IDS)
    def test_video_base_invalid_channel_ids(self, invalid_channel_id):
        """Test VideoBase validation with invalid channel IDs."""
        with pytest.raises(ValidationError):
            VideoBaseFactory.build(channel_id=invalid_channel_id)

    @pytest.mark.parametrize("valid_title", VideoTestData.VALID_TITLES)
    def test_video_base_valid_titles(self, valid_title):
        """Test VideoBase with valid titles."""
        video = VideoBaseFactory.build(title=valid_title)
        assert video.title == valid_title.strip()

    @pytest.mark.parametrize("invalid_title", VideoTestData.INVALID_TITLES)
    def test_video_base_invalid_titles(self, invalid_title):
        """Test VideoBase validation with invalid titles."""
        with pytest.raises(ValidationError):
            VideoBaseFactory.build(title=invalid_title)

    @pytest.mark.parametrize("valid_language", VideoTestData.VALID_LANGUAGES)
    def test_video_base_valid_languages(self, valid_language):
        """Test VideoBase with valid language codes."""
        video = VideoBaseFactory.build(default_language=valid_language)
        assert video.default_language is not None
        assert video.default_language.value == valid_language.value

    @pytest.mark.parametrize("invalid_language", VideoTestData.INVALID_LANGUAGES)
    def test_video_base_invalid_languages(self, invalid_language):
        """Test VideoBase validation with invalid language codes."""
        with pytest.raises(ValidationError):
            VideoBaseFactory.build(default_language=invalid_language)

    @pytest.mark.parametrize("valid_duration", VideoTestData.VALID_DURATIONS)
    def test_video_base_valid_durations(self, valid_duration):
        """Test VideoBase with valid durations."""
        video = VideoBaseFactory.build(duration=valid_duration)
        assert video.duration == valid_duration

    @pytest.mark.parametrize("invalid_duration", VideoTestData.INVALID_DURATIONS)
    def test_video_base_invalid_durations(self, invalid_duration):
        """Test VideoBase validation with invalid durations."""
        with pytest.raises(ValidationError):
            VideoBaseFactory.build(duration=invalid_duration)

    @pytest.mark.parametrize("valid_count", VideoTestData.VALID_COUNTS)
    def test_video_base_valid_view_counts(self, valid_count):
        """Test VideoBase with valid view counts."""
        video = VideoBaseFactory.build(view_count=valid_count)
        assert video.view_count == valid_count

    @pytest.mark.parametrize("invalid_count", VideoTestData.INVALID_COUNTS)
    def test_video_base_invalid_view_counts(self, invalid_count):
        """Test VideoBase validation with invalid view counts."""
        with pytest.raises(ValidationError):
            VideoBaseFactory.build(view_count=invalid_count)

    def test_video_base_model_dump(self):
        """Test VideoBase model_dump functionality."""
        video = VideoBaseFactory.build()
        data = video.model_dump()

        assert isinstance(data, dict)
        assert data["video_id"] == "dQw4w9WgXcQ"
        assert data["title"] == "Rick Astley - Never Gonna Give You Up (Official Video)"
        assert data["duration"] == 213

    def test_video_base_model_validate(self):
        """Test VideoBase model_validate functionality."""
        data = {
            "video_id": "dQw4w9WgXcQ",  # Valid 11-char video ID
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",  # Valid 24-char channel ID
            "title": "Validation Test Video",
            "description": "Test video for validation",
            "upload_date": datetime(2023, 12, 1, 10, 30, 0, tzinfo=timezone.utc),
            "duration": 300,
            "made_for_kids": False,
            "self_declared_made_for_kids": False,
            "default_language": "en-US",
            "view_count": 100000,
            "like_count": 5000,
            "deleted_flag": False,
        }

        video = VideoBase.model_validate(data)
        assert video.video_id == "dQw4w9WgXcQ"
        assert video.title == "Validation Test Video"
        assert video.duration == 300
        assert video.default_language == "en-US"  # LanguageCode enum preserves case

    def test_video_base_convenience_function(self):
        """Test convenience function for VideoBase."""
        video = create_video_base(
            title="Convenience Test Video", duration=450, view_count=75000
        )

        assert video.title == "Convenience Test Video"
        assert video.duration == 450
        assert video.view_count == 75000


class TestVideoCreateFactory:
    """Test VideoCreate model with factory pattern."""

    def test_video_create_creation(self):
        """Test basic VideoCreate creation from factory."""
        video = VideoCreateFactory.build()

        assert isinstance(video, VideoCreate)
        assert video.video_id == "9bZkp7q19f0"
        assert video.channel_id == "UC_x5XG1OV2P6uZZ5FSM9Ttw"
        assert "Google I/O" in video.title
        assert video.duration == 2760

    def test_video_create_convenience_function(self):
        """Test convenience function for VideoCreate."""
        video = create_video_create(video_id="CreateTest1", title="Create Test Video")

        assert video.video_id == "CreateTest1"
        assert video.title == "Create Test Video"


class TestVideoUpdateFactory:
    """Test VideoUpdate model with factory pattern."""

    def test_video_update_creation(self):
        """Test basic VideoUpdate creation from factory."""
        update = VideoUpdateFactory.build()

        assert isinstance(update, VideoUpdate)
        assert update.title is not None
        assert "Updated:" in update.title
        assert update.duration == 1800
        assert update.made_for_kids is False

    def test_video_update_partial_data(self):
        """Test VideoUpdate with partial data."""
        update = VideoUpdateFactory.build(
            title="Only Title Update",
            description=None,  # Only update some fields
            duration=None,
        )

        assert update.title == "Only Title Update"
        assert update.description is None
        assert update.duration is None

    def test_video_update_none_values(self):
        """Test VideoUpdate with all None values."""
        update = VideoUpdateFactory.build(
            title=None,
            description=None,
            duration=None,
            made_for_kids=None,
            default_language=None,
            like_count=None,
            view_count=None,
            deleted_flag=None,
        )

        assert update.title is None
        assert update.description is None
        assert update.duration is None

    def test_video_update_convenience_function(self):
        """Test convenience function for VideoUpdate."""
        update = create_video_update(title="Convenience Update", view_count=150000)

        assert update.title == "Convenience Update"
        assert update.view_count == 150000


class TestVideoFactory:
    """Test Video model with factory pattern."""

    def test_video_creation(self):
        """Test basic Video creation from factory."""
        video = VideoFactory.build()

        assert isinstance(video, Video)
        assert video.video_id == "3tmd-ClpJxA"
        assert video.channel_id == "UCMtFAi84ehTSYSE9XoHefig"
        assert "Stephen Colbert" in video.title
        assert hasattr(video, "created_at")
        assert hasattr(video, "updated_at")

    def test_video_timestamps(self):
        """Test Video with custom timestamps."""
        created_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        updated_time = datetime(2023, 12, 1, tzinfo=timezone.utc)

        video = VideoFactory.build(created_at=created_time, updated_at=updated_time)

        assert video.created_at == created_time
        assert video.updated_at == updated_time

    def test_video_from_attributes_config(self):
        """Test Video from_attributes configuration for ORM compatibility."""
        video_data = {
            "video_id": "dQw4w9WgXcQ",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "title": "ORM Test Video",
            "description": "Testing ORM compatibility",
            "upload_date": datetime(2023, 6, 15, 10, 30, tzinfo=timezone.utc),
            "duration": 600,
            "made_for_kids": False,
            "self_declared_made_for_kids": False,
            "default_language": "en",
            "view_count": 25000,
            "like_count": 1500,
            "deleted_flag": False,
            "created_at": datetime(2023, 6, 15, 10, 30, tzinfo=timezone.utc),
            "updated_at": datetime(2023, 6, 15, 12, 45, tzinfo=timezone.utc),
        }

        video = Video.model_validate(video_data)
        assert video.video_id == "dQw4w9WgXcQ"
        assert video.title == "ORM Test Video"
        assert video.duration == 600
        assert video.created_at is not None
        assert video.updated_at is not None

    def test_video_convenience_function(self):
        """Test convenience function for Video."""
        video = create_video(title="Convenience Test Video", duration=900)

        assert video.title == "Convenience Test Video"
        assert video.duration == 900


class TestVideoSearchFiltersFactory:
    """Test VideoSearchFilters model with factory pattern."""

    def test_video_search_filters_creation(self):
        """Test basic VideoSearchFilters creation from factory."""
        filters = VideoSearchFiltersFactory.build()

        assert isinstance(filters, VideoSearchFilters)
        assert filters.channel_ids is not None
        assert len(filters.channel_ids) == 2
        assert filters.title_query == "python tutorial"
        assert filters.description_query == "programming"
        assert filters.min_duration == 300
        assert filters.exclude_deleted is True

    def test_video_search_filters_partial(self):
        """Test VideoSearchFilters with partial data."""
        filters = VideoSearchFilters(
            title_query="machine learning",
        )

        assert filters.title_query == "machine learning"
        assert filters.description_query is None
        assert filters.min_duration is None
        assert filters.kids_friendly_only is None

    def test_video_search_filters_comprehensive(self):
        """Test VideoSearchFilters with all fields."""
        upload_after = datetime(2023, 1, 1, tzinfo=timezone.utc)
        upload_before = datetime(2023, 12, 31, tzinfo=timezone.utc)

        filters = VideoSearchFiltersFactory.build(
            channel_ids=[
                "UCuAXFkgsw1L7xaCfnd5JJOw",
                "UC_x5XG1OV2P6uZZ5FSM9Ttw",
                "UCMtFAi84ehTSYSE9XoHefig",
            ],
            title_query="artificial intelligence",
            description_query="deep learning",
            language_codes=["en", "es", "fr"],
            upload_after=upload_after,
            upload_before=upload_before,
            min_duration=600,
            max_duration=7200,
            min_view_count=5000,
            max_view_count=1000000,
            min_like_count=100,
            kids_friendly_only=True,
            exclude_deleted=False,
            has_transcripts=True,
        )

        assert filters.channel_ids is not None
        assert len(filters.channel_ids) == 3
        assert filters.title_query == "artificial intelligence"
        assert filters.upload_after == upload_after
        assert filters.upload_before == upload_before
        assert filters.kids_friendly_only is True
        assert filters.exclude_deleted is False

    def test_video_search_filters_convenience_function(self):
        """Test convenience function for VideoSearchFilters."""
        filters = create_video_search_filters(
            title_query="cooking", min_view_count=10000
        )

        assert filters.title_query == "cooking"
        assert filters.min_view_count == 10000


class TestVideoStatisticsFactory:
    """Test VideoStatistics model with factory pattern."""

    def test_video_statistics_creation(self):
        """Test basic VideoStatistics creation from factory."""
        stats = VideoStatisticsFactory.build()

        assert isinstance(stats, VideoStatistics)
        assert stats.total_videos == 1250
        assert stats.total_duration == 2250000
        assert stats.avg_duration == 1800.0
        assert stats.total_views == 50000000
        assert len(stats.top_languages) == 4
        assert isinstance(stats.upload_trend, dict)

    def test_video_statistics_custom_values(self):
        """Test VideoStatistics with custom values."""
        custom_languages = [("en", 500), ("ja", 200), ("ko", 150)]
        custom_trend = {"2023-06": 120, "2023-07": 135, "2023-08": 110}

        stats = VideoStatisticsFactory.build(
            total_videos=800,
            total_views=25000000,
            avg_views_per_video=31250.0,
            top_languages=custom_languages,
            upload_trend=custom_trend,
        )

        assert stats.total_videos == 800
        assert stats.total_views == 25000000
        assert stats.avg_views_per_video == 31250.0
        assert stats.top_languages == custom_languages
        assert stats.upload_trend == custom_trend

    def test_video_statistics_comprehensive(self):
        """Test VideoStatistics with comprehensive data."""
        stats = VideoStatisticsFactory.build(
            total_videos=2000,
            total_duration=3600000,  # 1000 hours total
            avg_duration=1800.0,  # 30 minutes average
            total_views=100000000,
            total_likes=5000000,
            total_comments=250000,
            avg_views_per_video=50000.0,
            avg_likes_per_video=2500.0,
            deleted_video_count=50,
            kids_friendly_count=300,
        )

        assert stats.total_videos == 2000
        assert stats.total_duration == 3600000
        assert stats.total_views == 100000000
        assert stats.deleted_video_count == 50
        assert stats.kids_friendly_count == 300

    def test_video_statistics_convenience_function(self):
        """Test convenience function for VideoStatistics."""
        stats = create_video_statistics(total_videos=5000, total_views=200000000)

        assert stats.total_videos == 5000
        assert stats.total_views == 200000000


class TestVideoWithChannelFactory:
    """Test VideoWithChannel model with factory pattern."""

    def test_video_with_channel_creation(self):
        """Test basic VideoWithChannel creation from factory."""
        video = VideoWithChannelFactory.build()

        assert isinstance(video, VideoWithChannel)
        assert video.video_id == "jNQXAC9IVRw"
        assert video.channel_id == "UCBJycsmduvYEL83R_U4JriQ"
        assert "iPhone" in video.title
        assert video.channel_title == "Marques Brownlee"
        assert video.channel_subscriber_count == 17800000

    def test_video_with_channel_custom_values(self):
        """Test VideoWithChannel with custom values."""
        video = VideoWithChannelFactory.build(
            channel_title="Custom Tech Channel",
            channel_subscriber_count=5000000,
            view_count=2000000,
        )

        assert video.channel_title == "Custom Tech Channel"
        assert video.channel_subscriber_count == 5000000
        assert video.view_count == 2000000

    def test_video_with_channel_convenience_function(self):
        """Test convenience function for VideoWithChannel."""
        video = create_video_with_channel(
            title="Custom Review Video", channel_title="Custom Channel"
        )

        assert video.title == "Custom Review Video"
        assert video.channel_title == "Custom Channel"


class TestBatchOperations:
    """Test batch operations and advanced factory usage."""

    def test_create_batch_videos(self):
        """Test creating multiple Video instances."""
        videos = create_batch_videos(count=3)

        assert len(videos) == 3
        assert all(isinstance(video, Video) for video in videos)

        # Check that different values are generated
        video_ids = [video.video_id for video in videos]
        channel_ids = [video.channel_id for video in videos]

        assert len(set(video_ids)) > 1  # Should have different video IDs
        assert len(set(channel_ids)) > 1  # Should have different channel IDs

    def test_model_serialization_round_trip(self):
        """Test model serialization and deserialization."""
        original = VideoFactory.build(
            video_id="dQw4w9WgXcQ",
            title="Serialization Test Video",
            duration=720,
            view_count=80000,
        )

        # Serialize to dict
        data = original.model_dump()

        # Deserialize back to model
        restored = Video.model_validate(data)

        assert original.video_id == restored.video_id
        assert original.title == restored.title
        assert original.duration == restored.duration
        assert original.created_at == restored.created_at

    def test_factory_inheritance_behavior(self):
        """Test that factories properly handle model inheritance."""
        base_video = VideoBaseFactory.build()
        create_video = VideoCreateFactory.build()
        full_video = VideoFactory.build()
        video_with_channel = VideoWithChannelFactory.build()

        # All should have the core attributes
        for video in [base_video, create_video, full_video, video_with_channel]:
            assert hasattr(video, "video_id")
            assert hasattr(video, "channel_id")
            assert hasattr(video, "title")
            assert hasattr(video, "duration")

        # Only full video and video_with_channel should have timestamps
        assert hasattr(full_video, "created_at")
        assert hasattr(full_video, "updated_at")
        assert hasattr(video_with_channel, "created_at")
        assert hasattr(video_with_channel, "updated_at")
        assert not hasattr(base_video, "created_at")
        assert not hasattr(create_video, "created_at")

        # Only video_with_channel should have channel info
        assert hasattr(video_with_channel, "channel_title")
        assert hasattr(video_with_channel, "channel_subscriber_count")
        assert not hasattr(full_video, "channel_title")


class TestValidationEdgeCases:
    """Test edge cases and validation scenarios."""

    def test_none_values_handling(self):
        """Test handling of None values in optional fields."""
        video = VideoBaseFactory.build(
            description=None,
            default_language=None,
            default_audio_language=None,
            available_languages=None,
            region_restriction=None,
            content_rating=None,
            like_count=None,
            view_count=None,
            comment_count=None,
        )

        assert video.description is None
        assert video.default_language is None
        assert video.like_count is None
        assert video.view_count is None

    def test_boundary_values(self):
        """Test boundary values for validation."""
        # Test minimum valid values with proper YouTube ID formats
        min_video = VideoBaseFactory.build(
            video_id="dQw4w9WgXcQ",  # Valid 11-char video ID
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",  # Valid 24-char channel ID
            title="C",  # Min length (1 char)
            duration=0,  # Min duration (0 seconds)
            like_count=0,
            view_count=0,
            comment_count=0,
        )
        assert len(min_video.video_id) == 11
        assert min_video.channel_id is not None
        assert len(min_video.channel_id) == 24
        assert min_video.duration == 0
        assert min_video.like_count == 0

        # Test maximum valid values with proper formats
        max_video = VideoBaseFactory.build(
            video_id="abcdefghijk",  # Valid 11-char video ID
            channel_id="UC123456789012345678901z",  # Valid 24-char channel ID
            duration=86400,  # 24 hours in seconds
            view_count=2147483647,  # Large number
        )
        assert len(max_video.video_id) == 11
        assert max_video.channel_id is not None
        assert len(max_video.channel_id) == 24
        assert max_video.duration == 86400

    def test_model_config_validation(self):
        """Test model configuration validation behaviors."""
        video = VideoFactory.build()

        # Test validate_assignment works
        video.view_count = 500000
        assert video.view_count == 500000

        # Test that invalid assignment raises validation error
        with pytest.raises(ValidationError):
            video.duration = -100  # Invalid negative duration

    def test_field_validator_edge_cases(self):
        """Test field validator edge cases."""
        # Test video_id validator - VideoId type enforces exact format, no trimming
        video1 = VideoBaseFactory.build(video_id="dQw4w9WgXcQ")
        assert video1.video_id == "dQw4w9WgXcQ"  # VideoId type validates exact format

        # Test title validator with whitespace
        video2 = VideoBaseFactory.build(title="  Test Video Title  ")
        assert video2.title == "Test Video Title"  # Should be trimmed

        # Test language validator - enum requires exact case
        video3 = VideoBaseFactory.build(default_language="en-US")
        assert video3.default_language == "en-US"  # LanguageCode enum preserves case

        # Test audio language validator
        video4 = VideoBaseFactory.build(default_audio_language="es-MX")
        assert (
            video4.default_audio_language == "es-MX"
        )  # LanguageCode enum preserves case

    @pytest.mark.parametrize("valid_languages", VideoTestData.VALID_AVAILABLE_LANGUAGES)
    def test_valid_available_languages(self, valid_languages):
        """Test VideoBase with valid available languages."""
        video = VideoBaseFactory.build(available_languages=valid_languages)
        assert video.available_languages == valid_languages

    @pytest.mark.parametrize(
        "valid_restriction", VideoTestData.VALID_REGION_RESTRICTIONS
    )
    def test_valid_region_restrictions(self, valid_restriction):
        """Test VideoBase with valid region restrictions."""
        video = VideoBaseFactory.build(region_restriction=valid_restriction)
        assert video.region_restriction == valid_restriction

    @pytest.mark.parametrize("valid_rating", VideoTestData.VALID_CONTENT_RATINGS)
    def test_valid_content_ratings(self, valid_rating):
        """Test VideoBase with valid content ratings."""
        video = VideoBaseFactory.build(content_rating=valid_rating)
        assert video.content_rating == valid_rating

    def test_complex_data_structures(self):
        """Test complex data structures in video models."""
        # Test with comprehensive available languages
        languages = {
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "ja": "Japanese",
        }

        # Test with detailed region restrictions
        restrictions = {
            "blocked": ["CN", "KP", "IR"],
            "allowed": ["US", "CA", "GB", "AU", "NZ", "DE", "FR", "ES"],
        }

        # Test with comprehensive content rating
        rating = {
            "ytRating": "ytAgeRestricted",
            "mpaaRating": "PG-13",
            "fskRating": "12",
            "bbfcRating": "12A",
        }

        video = VideoBaseFactory.build(
            available_languages=languages,
            region_restriction=restrictions,
            content_rating=rating,
        )

        assert video.available_languages is not None
        assert len(video.available_languages) == 5
        assert video.region_restriction is not None
        assert len(video.region_restriction["blocked"]) == 3
        assert len(video.region_restriction["allowed"]) == 8
        assert video.content_rating is not None
        assert video.content_rating["ytRating"] == "ytAgeRestricted"

    def test_kids_content_validation(self):
        """Test kids content related validation."""
        # Test kids-friendly video
        kids_video = VideoBaseFactory.build(
            made_for_kids=True,
            self_declared_made_for_kids=True,
            content_rating={"ytRating": "ytAgeAppropriate"},
        )

        assert kids_video.made_for_kids is True
        assert kids_video.self_declared_made_for_kids is True

        # Test age-restricted video
        adult_video = VideoBaseFactory.build(
            made_for_kids=False,
            self_declared_made_for_kids=False,
            content_rating={"ytRating": "ytAgeRestricted"},
        )

        assert adult_video.made_for_kids is False
        assert adult_video.self_declared_made_for_kids is False
