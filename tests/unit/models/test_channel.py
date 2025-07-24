"""
Tests for channel models using factory pattern.

Comprehensive tests for Channel Pydantic models with validation,
serialization, and business logic testing using factory-boy for DRY principles.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.channel import (
    Channel,
    ChannelBase,
    ChannelCreate,
    ChannelSearchFilters,
    ChannelStatistics,
    ChannelUpdate,
)
from tests.factories.channel_factory import (
    ChannelBaseFactory,
    ChannelCreateFactory,
    ChannelFactory,
    ChannelSearchFiltersFactory,
    ChannelStatisticsFactory,
    ChannelTestData,
    ChannelUpdateFactory,
    create_batch_channels,
    create_channel,
    create_channel_base,
    create_channel_create,
    create_channel_search_filters,
    create_channel_statistics,
    create_channel_update,
)


class TestChannelBaseFactory:
    """Test ChannelBase model with factory pattern."""

    def test_channel_base_creation(self):
        """Test basic ChannelBase creation from factory."""
        channel = ChannelBaseFactory()

        assert isinstance(channel, ChannelBase)
        assert channel.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert channel.title == "Rick Astley"
        assert channel.subscriber_count == 3500000
        assert channel.video_count == 125
        assert channel.default_language == "en"
        assert channel.country == "GB"

    def test_channel_base_custom_values(self):
        """Test ChannelBase with custom values."""
        custom_channel = ChannelBaseFactory(
            channel_id="UCCustomChannel123456789",
            title="Custom Channel",
            subscriber_count=1000000,
            country="US",
        )

        assert custom_channel.channel_id == "UCCustomChannel123456789"
        assert custom_channel.title == "Custom Channel"
        assert custom_channel.subscriber_count == 1000000
        assert custom_channel.country == "US"

    @pytest.mark.parametrize("valid_channel_id", ChannelTestData.VALID_CHANNEL_IDS)
    def test_channel_base_valid_channel_ids(self, valid_channel_id):
        """Test ChannelBase with valid channel IDs."""
        channel = ChannelBaseFactory(channel_id=valid_channel_id)
        assert channel.channel_id == valid_channel_id.strip()

    @pytest.mark.parametrize("invalid_channel_id", ChannelTestData.INVALID_CHANNEL_IDS)
    def test_channel_base_invalid_channel_ids(self, invalid_channel_id):
        """Test ChannelBase validation with invalid channel IDs."""
        with pytest.raises(ValidationError):
            ChannelBaseFactory(channel_id=invalid_channel_id)

    @pytest.mark.parametrize("valid_title", ChannelTestData.VALID_TITLES)
    def test_channel_base_valid_titles(self, valid_title):
        """Test ChannelBase with valid titles."""
        channel = ChannelBaseFactory(title=valid_title)
        assert channel.title == valid_title.strip()

    @pytest.mark.parametrize("invalid_title", ChannelTestData.INVALID_TITLES)
    def test_channel_base_invalid_titles(self, invalid_title):
        """Test ChannelBase validation with invalid titles."""
        with pytest.raises(ValidationError):
            ChannelBaseFactory(title=invalid_title)

    @pytest.mark.parametrize("valid_country", ChannelTestData.VALID_COUNTRIES)
    def test_channel_base_valid_countries(self, valid_country):
        """Test ChannelBase with valid country codes."""
        channel = ChannelBaseFactory(country=valid_country)
        assert channel.country == valid_country.upper()

    @pytest.mark.parametrize("invalid_country", ChannelTestData.INVALID_COUNTRIES)
    def test_channel_base_invalid_countries(self, invalid_country):
        """Test ChannelBase validation with invalid country codes."""
        with pytest.raises(ValidationError):
            ChannelBaseFactory(country=invalid_country)

    @pytest.mark.parametrize("valid_language", ChannelTestData.VALID_LANGUAGES)
    def test_channel_base_valid_languages(self, valid_language):
        """Test ChannelBase with valid language codes."""
        channel = ChannelBaseFactory(default_language=valid_language)
        # Language codes are now LanguageCode enums, so compare the value
        assert channel.default_language.value == valid_language

    @pytest.mark.parametrize("invalid_language", ChannelTestData.INVALID_LANGUAGES)
    def test_channel_base_invalid_languages(self, invalid_language):
        """Test ChannelBase validation with invalid language codes."""
        with pytest.raises(ValidationError):
            ChannelBaseFactory(default_language=invalid_language)

    @pytest.mark.parametrize("valid_count", ChannelTestData.VALID_SUBSCRIBER_COUNTS)
    def test_channel_base_valid_subscriber_counts(self, valid_count):
        """Test ChannelBase with valid subscriber counts."""
        channel = ChannelBaseFactory(subscriber_count=valid_count)
        assert channel.subscriber_count == valid_count

    @pytest.mark.parametrize("invalid_count", ChannelTestData.INVALID_SUBSCRIBER_COUNTS)
    def test_channel_base_invalid_subscriber_counts(self, invalid_count):
        """Test ChannelBase validation with invalid subscriber counts."""
        with pytest.raises(ValidationError):
            ChannelBaseFactory(subscriber_count=invalid_count)

    @pytest.mark.parametrize("valid_count", ChannelTestData.VALID_VIDEO_COUNTS)
    def test_channel_base_valid_video_counts(self, valid_count):
        """Test ChannelBase with valid video counts."""
        channel = ChannelBaseFactory(video_count=valid_count)
        assert channel.video_count == valid_count

    @pytest.mark.parametrize("invalid_count", ChannelTestData.INVALID_VIDEO_COUNTS)
    def test_channel_base_invalid_video_counts(self, invalid_count):
        """Test ChannelBase validation with invalid video counts."""
        with pytest.raises(ValidationError):
            ChannelBaseFactory(video_count=invalid_count)

    def test_channel_base_model_dump(self):
        """Test ChannelBase model_dump functionality."""
        channel = ChannelBaseFactory()
        data = channel.model_dump()

        assert isinstance(data, dict)
        assert data["channel_id"] == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert data["title"] == "Rick Astley"
        assert data["subscriber_count"] == 3500000

    def test_channel_base_model_validate(self):
        """Test ChannelBase model_validate functionality."""
        data = {
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",  # Exactly 24 characters
            "title": "Validation Test Channel",
            "description": "Test channel for validation",
            "subscriber_count": 500000,
            "video_count": 150,
            "default_language": "en-US",
            "country": "US",
            "thumbnail_url": "https://yt3.ggpht.com/test=s240-c-k-c0x00ffffff-no-rj",
        }

        channel = ChannelBase.model_validate(data)
        assert channel.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert channel.title == "Validation Test Channel"
        assert channel.subscriber_count == 500000
        assert channel.country == "US"  # Should be uppercase
        assert channel.default_language.value == "en-US"  # LanguageCode enum value

    def test_channel_base_convenience_function(self):
        """Test convenience function for ChannelBase."""
        channel = create_channel_base(title="Convenience Test", subscriber_count=750000)

        assert channel.title == "Convenience Test"
        assert channel.subscriber_count == 750000


class TestChannelCreateFactory:
    """Test ChannelCreate model with factory pattern."""

    def test_channel_create_creation(self):
        """Test basic ChannelCreate creation from factory."""
        channel = ChannelCreateFactory()

        assert isinstance(channel, ChannelCreate)
        assert channel.channel_id == "UC_x5XG1OV2P6uZZ5FSM9Ttw"
        assert channel.title == "Google Developers"
        assert channel.subscriber_count == 2100000

    def test_channel_create_convenience_function(self):
        """Test convenience function for ChannelCreate."""
        channel = create_channel_create(
            channel_id="UCTestCreate123456789012", title="Test Create Channel"
        )

        assert channel.channel_id == "UCTestCreate123456789012"
        assert channel.title == "Test Create Channel"


class TestChannelUpdateFactory:
    """Test ChannelUpdate model with factory pattern."""

    def test_channel_update_creation(self):
        """Test basic ChannelUpdate creation from factory."""
        update = ChannelUpdateFactory()

        assert isinstance(update, ChannelUpdate)
        assert update.title == "Updated Channel Title"
        assert update.subscriber_count == 5000000
        assert update.country == "ES"

    def test_channel_update_partial_data(self):
        """Test ChannelUpdate with partial data."""
        update = ChannelUpdateFactory(
            title="Only Title Update",
            description=None,  # Only update some fields
            subscriber_count=None,
        )

        assert update.title == "Only Title Update"
        assert update.description is None
        assert update.subscriber_count is None

    def test_channel_update_none_values(self):
        """Test ChannelUpdate with all None values."""
        update = ChannelUpdate(
            title=None,
            description=None,
            subscriber_count=None,
            video_count=None,
            default_language=None,
            country=None,
            thumbnail_url=None,
        )

        assert update.title is None
        assert update.description is None
        assert update.subscriber_count is None

    def test_channel_update_convenience_function(self):
        """Test convenience function for ChannelUpdate."""
        update = create_channel_update(
            title="Convenience Update", subscriber_count=3000000
        )

        assert update.title == "Convenience Update"
        assert update.subscriber_count == 3000000


class TestChannelFactory:
    """Test Channel model with factory pattern."""

    def test_channel_creation(self):
        """Test basic Channel creation from factory."""
        channel = ChannelFactory()

        assert isinstance(channel, Channel)
        assert channel.channel_id == "UCMtFAi84ehTSYSE9XoHefig"
        assert channel.title == "The Late Show with Stephen Colbert"
        assert hasattr(channel, "created_at")
        assert hasattr(channel, "updated_at")

    def test_channel_timestamps(self):
        """Test Channel with custom timestamps."""
        created_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        updated_time = datetime(2023, 12, 1, tzinfo=timezone.utc)

        channel = ChannelFactory(created_at=created_time, updated_at=updated_time)

        assert channel.created_at == created_time
        assert channel.updated_at == updated_time

    def test_channel_from_attributes_config(self):
        """Test Channel from_attributes configuration for ORM compatibility."""
        channel_data = {
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "title": "ORM Test Channel",
            "description": "Testing ORM compatibility",
            "subscriber_count": 850000,
            "video_count": 275,
            "default_language": "en",
            "country": "CA",
            "thumbnail_url": "https://yt3.ggpht.com/orm-test=s240-c-k-c0x00ffffff-no-rj",
            "created_at": datetime(2023, 6, 15, 10, 30, tzinfo=timezone.utc),
            "updated_at": datetime(2023, 12, 1, 16, 45, tzinfo=timezone.utc),
        }

        channel = Channel.model_validate(channel_data)
        assert channel.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert channel.title == "ORM Test Channel"
        assert channel.subscriber_count == 850000
        assert channel.created_at is not None
        assert channel.updated_at is not None

    def test_channel_convenience_function(self):
        """Test convenience function for Channel."""
        channel = create_channel(title="Convenience Channel", subscriber_count=1500000)

        assert channel.title == "Convenience Channel"
        assert channel.subscriber_count == 1500000


class TestChannelSearchFiltersFactory:
    """Test ChannelSearchFilters model with factory pattern."""

    def test_channel_search_filters_creation(self):
        """Test basic ChannelSearchFilters creation from factory."""
        filters = ChannelSearchFiltersFactory()

        assert isinstance(filters, ChannelSearchFilters)
        assert filters.title_query == "programming"
        assert filters.description_query == "tutorial"
        assert filters.language_codes == ["en", "en-US", "es"]
        assert filters.countries == ["US", "GB", "CA"]
        assert filters.min_subscriber_count == 10000
        assert filters.has_keywords is True

    def test_channel_search_filters_partial(self):
        """Test ChannelSearchFilters with partial data."""
        filters = ChannelSearchFiltersFactory(
            title_query="python", description_query=None, min_subscriber_count=None
        )

        assert filters.title_query == "python"
        assert filters.description_query is None
        assert filters.min_subscriber_count is None

    def test_channel_search_filters_comprehensive(self):
        """Test ChannelSearchFilters with all fields."""
        filters = ChannelSearchFiltersFactory(
            title_query="machine learning",
            description_query="artificial intelligence",
            language_codes=["en", "es", "fr"],
            countries=["US", "ES", "FR"],
            min_subscriber_count=50000,
            max_subscriber_count=5000000,
            min_video_count=100,
            max_video_count=10000,
            has_keywords=False,
        )

        assert filters.title_query == "machine learning"
        assert filters.description_query == "artificial intelligence"
        assert len(filters.language_codes) == 3
        assert len(filters.countries) == 3
        assert filters.min_subscriber_count == 50000
        assert filters.max_subscriber_count == 5000000
        assert filters.has_keywords is False

    def test_channel_search_filters_convenience_function(self):
        """Test convenience function for ChannelSearchFilters."""
        filters = create_channel_search_filters(
            title_query="cooking", min_subscriber_count=25000
        )

        assert filters.title_query == "cooking"
        assert filters.min_subscriber_count == 25000


class TestChannelStatisticsFactory:
    """Test ChannelStatistics model with factory pattern."""

    def test_channel_statistics_creation(self):
        """Test basic ChannelStatistics creation from factory."""
        stats = ChannelStatisticsFactory()

        assert isinstance(stats, ChannelStatistics)
        assert stats.total_channels == 150
        assert stats.total_subscribers == 25000000
        assert stats.avg_subscribers_per_channel == 166666.67
        assert len(stats.top_countries) == 5
        assert len(stats.top_languages) == 5

    def test_channel_statistics_custom_values(self):
        """Test ChannelStatistics with custom values."""
        stats = ChannelStatisticsFactory(
            total_channels=500, total_subscribers=50000000, avg_videos_per_channel=120.5
        )

        assert stats.total_channels == 500
        assert stats.total_subscribers == 50000000
        assert stats.avg_videos_per_channel == 120.5

    def test_channel_statistics_comprehensive(self):
        """Test ChannelStatistics with comprehensive data."""
        custom_countries = [("US", 150), ("GB", 75), ("CA", 50)]
        custom_languages = [("en", 200), ("es", 50), ("fr", 25)]

        stats = ChannelStatisticsFactory(
            total_channels=275,
            total_subscribers=75000000,
            total_videos=22000,
            avg_subscribers_per_channel=272727.27,
            avg_videos_per_channel=80.0,
            top_countries=custom_countries,
            top_languages=custom_languages,
        )

        assert stats.total_channels == 275
        assert stats.total_subscribers == 75000000
        assert stats.total_videos == 22000
        assert stats.top_countries == custom_countries
        assert stats.top_languages == custom_languages

    def test_channel_statistics_convenience_function(self):
        """Test convenience function for ChannelStatistics."""
        stats = create_channel_statistics(
            total_channels=1000, total_subscribers=100000000
        )

        assert stats.total_channels == 1000
        assert stats.total_subscribers == 100000000


class TestBatchOperations:
    """Test batch operations and advanced factory usage."""

    def test_create_batch_channels(self):
        """Test creating multiple Channel instances."""
        channels = create_batch_channels(count=3)

        assert len(channels) == 3
        assert all(isinstance(channel, Channel) for channel in channels)

        # Check that different values are generated
        channel_ids = [channel.channel_id for channel in channels]
        titles = [channel.title for channel in channels]

        assert len(set(channel_ids)) > 1  # Should have different channel IDs
        assert len(set(titles)) > 1  # Should have different titles

    def test_model_serialization_round_trip(self):
        """Test model serialization and deserialization."""
        original = ChannelFactory(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="Serialization Test Channel",
            subscriber_count=2500000,
            video_count=450,
        )

        # Serialize to dict
        data = original.model_dump()

        # Deserialize back to model
        restored = Channel.model_validate(data)

        assert original.channel_id == restored.channel_id
        assert original.title == restored.title
        assert original.subscriber_count == restored.subscriber_count
        assert original.created_at == restored.created_at

    def test_factory_inheritance_behavior(self):
        """Test that factories properly handle model inheritance."""
        base_channel = ChannelBaseFactory()
        create_channel = ChannelCreateFactory()
        full_channel = ChannelFactory()

        # All should have the core attributes
        for channel in [base_channel, create_channel, full_channel]:
            assert hasattr(channel, "channel_id")
            assert hasattr(channel, "title")
            assert hasattr(channel, "subscriber_count")

        # Only full channel should have timestamps
        assert hasattr(full_channel, "created_at")
        assert hasattr(full_channel, "updated_at")
        assert not hasattr(base_channel, "created_at")
        assert not hasattr(create_channel, "created_at")


class TestValidationEdgeCases:
    """Test edge cases and validation scenarios."""

    def test_none_values_handling(self):
        """Test handling of None values in optional fields."""
        channel = ChannelBaseFactory(
            description=None,
            subscriber_count=None,
            video_count=None,
            default_language=None,
            country=None,
            thumbnail_url=None,
        )

        assert channel.description is None
        assert channel.subscriber_count is None
        assert channel.video_count is None
        assert channel.default_language is None
        assert channel.country is None
        assert channel.thumbnail_url is None

    def test_boundary_values(self):
        """Test boundary values for validation."""
        # Test minimum valid values (must match YouTube format requirements)
        min_channel = ChannelBaseFactory(
            channel_id="UC12345678901234567890AB",  # Min valid UC format (24 chars)
            title="B",  # Min length (1 char)
            subscriber_count=0,
            video_count=0,
        )
        assert len(min_channel.channel_id) == 24
        assert len(min_channel.title) == 1
        assert min_channel.subscriber_count == 0
        assert min_channel.video_count == 0

        # Test maximum valid values
        max_channel = ChannelBaseFactory(
            channel_id="UC123456789012345678901Z",  # Valid UC format (exactly 24 chars)
            title="B" * 255,  # Max length (255 chars)
            thumbnail_url="https://yt3.ggpht.com/"
            + "C" * 460,  # Max length (~500 chars total)
        )
        assert len(max_channel.channel_id) == 24
        assert len(max_channel.title) == 255
        assert len(max_channel.thumbnail_url) <= 500

    def test_model_config_validation(self):
        """Test model configuration validation behaviors."""
        channel = ChannelFactory()

        # Test validate_assignment works
        channel.subscriber_count = 7500000
        assert channel.subscriber_count == 7500000

        # Test that invalid assignment raises validation error
        with pytest.raises(ValidationError):
            channel.subscriber_count = -1000  # Invalid negative value

    def test_field_validator_edge_cases(self):
        """Test field validator edge cases."""
        # Test title validator with whitespace
        channel2 = ChannelBaseFactory(title="  Test Title  ")
        assert channel2.title == "Test Title"  # Should be trimmed

        # Test country validator case normalization
        channel3 = ChannelBaseFactory(country="us")
        assert channel3.country == "US"  # Should be uppercase

        # Test language validator - LanguageCode enum handles validation
        from chronovista.models.enums import LanguageCode

        channel4 = ChannelBaseFactory(default_language=LanguageCode.ENGLISH_US)
        assert channel4.default_language == LanguageCode.ENGLISH_US

    @pytest.mark.parametrize("valid_url", ChannelTestData.VALID_THUMBNAIL_URLS)
    def test_valid_thumbnail_urls(self, valid_url):
        """Test ChannelBase with valid thumbnail URLs."""
        channel = ChannelBaseFactory(thumbnail_url=valid_url)
        assert channel.thumbnail_url == valid_url

    @pytest.mark.parametrize("invalid_url", ChannelTestData.INVALID_THUMBNAIL_URLS)
    def test_invalid_thumbnail_urls(self, invalid_url):
        """Test ChannelBase validation with invalid thumbnail URLs."""
        with pytest.raises(ValidationError):
            ChannelBaseFactory(thumbnail_url=invalid_url)
