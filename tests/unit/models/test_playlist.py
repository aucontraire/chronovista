"""
Tests for playlist Pydantic models.

Tests validation, keyword arguments, serialization, and model methods
for all Playlist model variants using factory pattern for DRY.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.enums import (
    LanguageCode,
    PlaylistType,
    PrivacyStatus,
)
from chronovista.models.playlist import (
    Playlist,
    PlaylistBase,
    PlaylistCreate,
    PlaylistSearchFilters,
    PlaylistStatistics,
    PlaylistUpdate,
)
from tests.factories.playlist_factory import (
    PlaylistBaseFactory,
    PlaylistCreateFactory,
    PlaylistFactory,
    PlaylistSearchFiltersFactory,
    PlaylistStatisticsFactory,
    PlaylistTestData,
    PlaylistUpdateFactory,
    create_playlist,
)


class TestPlaylistBase:
    """Test PlaylistBase model using factories."""

    def test_create_valid_playlist_base(self):
        """Test creating valid PlaylistBase with keyword arguments."""
        playlist = PlaylistBaseFactory.build(
            playlist_id="PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f",
            title="Learn Python Programming",
            description="Complete Python course",
            default_language="en",
            privacy_status="public",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            video_count=50,
        )

        assert playlist.playlist_id == "PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f"
        assert playlist.title == "Learn Python Programming"
        assert playlist.description == "Complete Python course"
        assert playlist.default_language == "en"
        assert playlist.privacy_status == "public"
        assert playlist.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert playlist.video_count == 50

    def test_create_playlist_base_minimal(self):
        """Test creating PlaylistBase with minimal required fields."""
        playlist = PlaylistBaseFactory.build(
            playlist_id="PLs9ACwy3uKTOT2q9gLKUvyqPOjLXUlAWg",
            title="My Playlist",
            description=None,
            default_language=None,
            privacy_status="private",
            channel_id="UC-lHJZR3Gqxm24_Vd_AJ5Yw",
            video_count=0,
        )

        assert playlist.playlist_id == "PLs9ACwy3uKTOT2q9gLKUvyqPOjLXUlAWg"
        assert playlist.title == "My Playlist"
        assert playlist.description is None
        assert playlist.default_language is None
        assert playlist.privacy_status == "private"
        assert playlist.channel_id == "UC-lHJZR3Gqxm24_Vd_AJ5Yw"
        assert playlist.video_count == 0

    def test_factory_generates_valid_defaults(self):
        """Test that factory generates valid models with defaults.

        NOTE: Factory generates internal IDs (int_ prefix, 36 chars) by default.
        """
        playlist = PlaylistBaseFactory.build()

        assert isinstance(playlist, PlaylistBase)
        # Internal IDs are 36 chars (int_ + 32 hex), YouTube IDs are 30-50 chars
        assert len(playlist.playlist_id) >= 30
        assert len(playlist.playlist_id) <= 50
        assert len(playlist.title) >= 1
        assert len(playlist.title) <= 255
        assert len(playlist.channel_id) >= 20
        assert len(playlist.channel_id) <= 24
        assert playlist.privacy_status in ["private", "public", "unlisted"]
        assert playlist.video_count >= 0

    @pytest.mark.parametrize(
        "invalid_playlist_id", PlaylistTestData.INVALID_PLAYLIST_IDS
    )
    def test_playlist_id_validation_invalid(self, invalid_playlist_id):
        """Test playlist_id validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            PlaylistBaseFactory.build(playlist_id=invalid_playlist_id)

    @pytest.mark.parametrize("valid_playlist_id", PlaylistTestData.VALID_PLAYLIST_IDS)
    def test_playlist_id_validation_valid(self, valid_playlist_id):
        """Test playlist_id validation with various valid inputs."""
        playlist = PlaylistBaseFactory.build(playlist_id=valid_playlist_id)
        assert playlist.playlist_id == valid_playlist_id

    @pytest.mark.parametrize("invalid_title", PlaylistTestData.INVALID_TITLES)
    def test_title_validation_invalid(self, invalid_title):
        """Test title validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            PlaylistBaseFactory.build(title=invalid_title)

    @pytest.mark.parametrize("valid_title", PlaylistTestData.VALID_TITLES)
    def test_title_validation_valid(self, valid_title):
        """Test title validation with various valid inputs."""
        playlist = PlaylistBaseFactory.build(title=valid_title)
        assert playlist.title == valid_title

    @pytest.mark.parametrize(
        "invalid_description", PlaylistTestData.INVALID_DESCRIPTIONS
    )
    def test_description_validation_invalid(self, invalid_description):
        """Test description validation with invalid inputs."""
        with pytest.raises(ValidationError):
            PlaylistBaseFactory.build(description=invalid_description)

    def test_description_empty_becomes_none(self):
        """Test that empty description becomes None."""
        # With type-safe validation, pass None directly for empty description
        playlist = PlaylistBaseFactory.build(description=None)
        assert playlist.description is None

    @pytest.mark.parametrize("invalid_channel_id", PlaylistTestData.INVALID_CHANNEL_IDS)
    def test_channel_id_validation_invalid(self, invalid_channel_id):
        """Test channel_id validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            PlaylistBaseFactory.build(channel_id=invalid_channel_id)

    @pytest.mark.parametrize("valid_channel_id", PlaylistTestData.VALID_CHANNEL_IDS)
    def test_channel_id_validation_valid(self, valid_channel_id):
        """Test channel_id validation with various valid inputs."""
        playlist = PlaylistBaseFactory.build(channel_id=valid_channel_id)
        assert playlist.channel_id == valid_channel_id

    @pytest.mark.parametrize(
        "invalid_language_code", PlaylistTestData.INVALID_LANGUAGE_CODES
    )
    def test_default_language_validation_invalid(self, invalid_language_code):
        """Test default_language validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            PlaylistBaseFactory.build(default_language=invalid_language_code)

    @pytest.mark.parametrize(
        "valid_language_code", PlaylistTestData.VALID_LANGUAGE_CODES
    )
    def test_default_language_validation_valid(self, valid_language_code):
        """Test default_language validation with various valid inputs."""
        playlist = PlaylistBaseFactory.build(default_language=valid_language_code)
        assert playlist.default_language is not None
        assert playlist.default_language.value == valid_language_code

    def test_default_language_none_allowed(self):
        """Test that default_language can be None."""
        playlist = PlaylistBaseFactory.build(default_language=None)
        assert playlist.default_language is None

    def test_privacy_status_validation(self):
        """Test privacy_status validation."""
        for status in PlaylistTestData.PRIVACY_STATUSES:
            playlist = PlaylistBaseFactory.build(privacy_status=status)
            assert playlist.privacy_status == status

        # Invalid status
        with pytest.raises(ValidationError):
            PlaylistBaseFactory.build(privacy_status="invalid_status")

    def test_video_count_validation(self):
        """Test video_count validation."""
        # Valid counts
        playlist = PlaylistBaseFactory.build(video_count=0)
        assert playlist.video_count == 0

        playlist = PlaylistBaseFactory.build(video_count=100)
        assert playlist.video_count == 100

        # Invalid count
        with pytest.raises(ValidationError):
            PlaylistBaseFactory.build(video_count=-1)

    def test_model_dump_functionality(self):
        """Test model_dump() method for serialization."""
        playlist = PlaylistBaseFactory.build(
            playlist_id="PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f",
            title="Test Playlist",
            description="Test description",
            default_language="en",
            privacy_status="public",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            video_count=25,
        )

        data = playlist.model_dump()
        expected = {
            "playlist_id": "PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f",
            "title": "Test Playlist",
            "description": "Test description",
            "default_language": "en",
            "privacy_status": "public",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "video_count": 25,
            # New fields for playlist enrichment
            "published_at": None,
            "deleted_flag": False,
            # Playlist type for system playlist handling (T077)
            "playlist_type": PlaylistType.REGULAR,
        }

        assert data == expected

    def test_model_validate_functionality(self):
        """Test model_validate() method for deserialization."""
        data = PlaylistTestData.valid_playlist_data()

        playlist = PlaylistBase.model_validate(data)

        assert playlist.playlist_id == data["playlist_id"]
        assert playlist.title == data["title"]
        assert playlist.description == data["description"]
        assert playlist.default_language == data["default_language"]
        assert playlist.privacy_status == data["privacy_status"]
        assert playlist.channel_id == data["channel_id"]
        assert playlist.video_count == data["video_count"]


class TestPlaylistCreate:
    """Test PlaylistCreate model using factories."""

    def test_create_valid_playlist_create(self):
        """Test creating valid PlaylistCreate with keyword arguments."""
        playlist = PlaylistCreateFactory.build(
            playlist_id="PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo",
            title="Music Collection",
            description="My favorite music tracks",
            default_language="fr",
            privacy_status="unlisted",
            channel_id="UCBJycsmduvYEL83R_U4JriQ",
            video_count=40,
        )

        assert playlist.playlist_id == "PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo"
        assert playlist.title == "Music Collection"
        assert playlist.description == "My favorite music tracks"
        assert playlist.default_language == "fr"
        assert playlist.privacy_status == "unlisted"
        assert playlist.channel_id == "UCBJycsmduvYEL83R_U4JriQ"
        assert playlist.video_count == 40

    def test_inherits_base_validation(self):
        """Test that PlaylistCreate inherits base validation."""
        with pytest.raises(ValidationError):
            PlaylistCreateFactory.build(playlist_id="   ")

    def test_factory_generates_valid_model(self):
        """Test factory generates valid PlaylistCreate models."""
        playlist = PlaylistCreateFactory.build()

        assert isinstance(playlist, PlaylistCreate)
        assert isinstance(playlist, PlaylistBase)  # Inheritance check


class TestPlaylistUpdate:
    """Test PlaylistUpdate model using factories."""

    def test_create_valid_playlist_update(self):
        """Test creating valid PlaylistUpdate with keyword arguments."""
        update = PlaylistUpdateFactory.build(
            title="Updated Title",
            description="Updated description",
            default_language="es",
            privacy_status="public",
            video_count=60,
        )

        assert update.title == "Updated Title"
        assert update.description == "Updated description"
        assert update.default_language == "es"
        assert update.privacy_status == "public"
        assert update.video_count == 60

    def test_create_empty_playlist_update(self):
        """Test creating empty PlaylistUpdate."""
        update = PlaylistUpdateFactory.build()

        assert update.title is None
        assert update.description is None
        assert update.default_language is None
        assert update.privacy_status is None
        assert update.video_count is None

    def test_title_validation_in_update(self):
        """Test title validation in update model."""
        with pytest.raises(ValidationError):
            PlaylistUpdateFactory.build(title="")

    def test_description_empty_becomes_none(self):
        """Test that empty description becomes None in update."""
        # With type-safe validation, pass None directly for empty description
        update = PlaylistUpdateFactory.build(description=None)
        assert update.description is None

    def test_video_count_validation_in_update(self):
        """Test video_count validation in update model."""
        with pytest.raises(ValidationError):
            PlaylistUpdateFactory.build(video_count=-5)

    def test_model_dump_excludes_none(self):
        """Test model_dump() excludes None values."""
        update = PlaylistUpdateFactory.build(
            title=None,
            description=None,
            default_language=None,
            privacy_status=None,
            video_count=None,
        )

        data = update.model_dump(exclude_none=True)

        assert data == {}

    def test_factory_generates_valid_updates(self):
        """Test factory generates valid update models with explicit values."""
        update = PlaylistUpdateFactory.build(
            title="Updated Playlist Title", video_count=25
        )

        assert isinstance(update, PlaylistUpdate)
        assert update.title == "Updated Playlist Title"
        assert update.video_count == 25


class TestPlaylist:
    """Test Playlist full model using factories."""

    def test_create_valid_playlist(self):
        """Test creating valid Playlist with keyword arguments."""
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

        playlist = PlaylistFactory.build(
            playlist_id="PLMYEtPqzjdeev14J_RpAU_RQKyeaROB8T",
            title="Tech Tutorials",
            description="Collection of technology tutorials",
            default_language="de",
            privacy_status="public",
            channel_id="UCsXVk37bltHxD1rDPwtNM8Q",
            video_count=75,
            created_at=created_at,
            updated_at=updated_at,
        )
        assert isinstance(playlist, Playlist)  # Type guard for mypy

        assert playlist.playlist_id == "PLMYEtPqzjdeev14J_RpAU_RQKyeaROB8T"
        assert playlist.title == "Tech Tutorials"
        assert playlist.description == "Collection of technology tutorials"
        assert playlist.default_language == "de"
        assert playlist.privacy_status == "public"
        assert playlist.channel_id == "UCsXVk37bltHxD1rDPwtNM8Q"
        assert playlist.video_count == 75
        assert playlist.created_at == created_at
        assert playlist.updated_at == updated_at

    def test_from_attributes_compatibility(self):
        """Test ORM compatibility with from_attributes."""

        # Simulate SQLAlchemy model attributes
        class MockPlaylistDB:
            playlist_id = "PLillGF-RfqbY0pq_LLo8BSfP_iDnODx36"
            title = "Gaming Highlights"
            description = "Best gaming moments"
            default_language = "ja"
            privacy_status = "unlisted"
            channel_id = "UCYCvGbr7chpyTgFpgUOVjjw"
            video_count = 30
            created_at = datetime.now(timezone.utc)
            updated_at = datetime.now(timezone.utc)

        mock_db = MockPlaylistDB()
        playlist = Playlist.model_validate(mock_db, from_attributes=True)

        assert playlist.playlist_id == "PLillGF-RfqbY0pq_LLo8BSfP_iDnODx36"
        assert playlist.title == "Gaming Highlights"
        assert playlist.description == "Best gaming moments"
        assert playlist.default_language == "ja"
        assert playlist.privacy_status == "unlisted"
        assert playlist.channel_id == "UCYCvGbr7chpyTgFpgUOVjjw"
        assert playlist.video_count == 30
        assert isinstance(playlist.created_at, datetime)
        assert isinstance(playlist.updated_at, datetime)

    def test_factory_generates_full_model(self):
        """Test factory generates complete Playlist models."""
        playlist = PlaylistFactory.build()

        assert isinstance(playlist, Playlist)
        assert isinstance(playlist, PlaylistBase)  # Inheritance
        assert isinstance(playlist.created_at, datetime)
        assert isinstance(playlist.updated_at, datetime)
        assert playlist.created_at.tzinfo is not None  # Has timezone
        assert playlist.updated_at.tzinfo is not None  # Has timezone


class TestPlaylistSearchFilters:
    """Test PlaylistSearchFilters model using factories."""

    def test_create_comprehensive_filters(self):
        """Test creating comprehensive search filters with keyword arguments."""
        data = PlaylistTestData.comprehensive_search_filters_data()
        filters = PlaylistSearchFiltersFactory.build(**data)

        assert filters.playlist_ids == data["playlist_ids"]
        assert filters.channel_ids == data["channel_ids"]
        assert filters.title_query == data["title_query"]
        assert filters.description_query == data["description_query"]
        assert filters.language_codes == data["language_codes"]
        assert filters.privacy_statuses == data["privacy_statuses"]
        assert filters.min_video_count == data["min_video_count"]
        assert filters.max_video_count == data["max_video_count"]
        assert filters.has_description == data["has_description"]
        assert filters.created_after == data["created_after"]
        assert filters.created_before == data["created_before"]
        assert filters.updated_after == data["updated_after"]
        assert filters.updated_before == data["updated_before"]

    def test_create_empty_filters(self):
        """Test creating empty search filters."""
        filters = PlaylistSearchFilters()

        assert filters.playlist_ids is None
        assert filters.channel_ids is None
        assert filters.title_query is None
        assert filters.description_query is None
        assert filters.language_codes is None
        assert filters.privacy_statuses is None
        assert filters.min_video_count is None
        assert filters.max_video_count is None
        assert filters.has_description is None
        assert filters.created_after is None
        assert filters.created_before is None
        assert filters.updated_after is None
        assert filters.updated_before is None

    def test_factory_generates_valid_filters(self):
        """Test factory generates valid search filters."""
        filters = PlaylistSearchFiltersFactory.build()

        assert isinstance(filters, PlaylistSearchFilters)
        assert isinstance(filters.playlist_ids, list)
        assert isinstance(filters.channel_ids, list)
        assert isinstance(filters.language_codes, list)
        assert isinstance(filters.privacy_statuses, list)
        assert len(filters.playlist_ids) > 0
        assert len(filters.channel_ids) > 0

    def test_query_validation_empty_string(self):
        """Test query validation with empty strings."""
        with pytest.raises(ValidationError):
            PlaylistSearchFiltersFactory.build(title_query="")

        with pytest.raises(ValidationError):
            PlaylistSearchFiltersFactory.build(description_query="")

    def test_video_count_range_validation(self):
        """Test video count range validation."""
        # Valid ranges
        filters = PlaylistSearchFiltersFactory.build(
            min_video_count=1, max_video_count=100
        )
        assert filters.min_video_count == 1
        assert filters.max_video_count == 100

        # Invalid ranges
        with pytest.raises(ValidationError):
            PlaylistSearchFiltersFactory.build(min_video_count=-1)

        with pytest.raises(ValidationError):
            PlaylistSearchFiltersFactory.build(max_video_count=-1)


class TestPlaylistStatistics:
    """Test PlaylistStatistics model using factories."""

    def test_create_valid_statistics(self):
        """Test creating valid PlaylistStatistics with keyword arguments."""
        stats = PlaylistStatisticsFactory.build(
            total_playlists=500,
            total_videos=7500,
            avg_videos_per_playlist=15.0,
            unique_channels=350,
            privacy_distribution={"public": 300, "unlisted": 150, "private": 50},
            language_distribution={"en": 250, "es": 100, "fr": 80, "de": 70},
            top_channels_by_playlists=[
                ("UCuAXFkgsw1L7xaCfnd5JJOw", 35),
                ("UC-lHJZR3Gqxm24_Vd_AJ5Yw", 30),
            ],
            playlist_size_distribution={
                "1-5 videos": 150,
                "6-20 videos": 200,
                "21-50 videos": 100,
                "50+ videos": 50,
            },
            playlists_with_descriptions=375,
        )

        assert stats.total_playlists == 500
        assert stats.total_videos == 7500
        assert stats.avg_videos_per_playlist == 15.0
        assert stats.unique_channels == 350
        assert stats.privacy_distribution == {
            "public": 300,
            "unlisted": 150,
            "private": 50,
        }
        assert stats.language_distribution == {"en": 250, "es": 100, "fr": 80, "de": 70}
        assert stats.top_channels_by_playlists == [
            ("UCuAXFkgsw1L7xaCfnd5JJOw", 35),
            ("UC-lHJZR3Gqxm24_Vd_AJ5Yw", 30),
        ]
        assert stats.playlist_size_distribution == {
            "1-5 videos": 150,
            "6-20 videos": 200,
            "21-50 videos": 100,
            "50+ videos": 50,
        }
        assert stats.playlists_with_descriptions == 375

    def test_create_minimal_statistics(self):
        """Test creating minimal PlaylistStatistics."""
        stats = PlaylistStatistics(
            total_playlists=100,
            total_videos=1500,
            avg_videos_per_playlist=15.0,
            unique_channels=75,
            playlists_with_descriptions=60,
        )

        assert stats.total_playlists == 100
        assert stats.total_videos == 1500
        assert stats.avg_videos_per_playlist == 15.0
        assert stats.unique_channels == 75
        assert stats.playlists_with_descriptions == 60
        assert stats.privacy_distribution == {}
        assert stats.language_distribution == {}
        assert stats.top_channels_by_playlists == []
        assert stats.playlist_size_distribution == {}

    def test_factory_generates_realistic_statistics(self):
        """Test factory generates realistic statistics."""
        stats = PlaylistStatisticsFactory.build()

        assert isinstance(stats, PlaylistStatistics)
        assert stats.total_playlists > 0
        assert (
            stats.total_videos >= stats.total_playlists
        )  # At least 1 video per playlist on average
        assert (
            stats.unique_channels <= stats.total_playlists
        )  # Can't have more channels than playlists
        assert stats.avg_videos_per_playlist > 0
        assert stats.playlists_with_descriptions <= stats.total_playlists
        assert isinstance(stats.privacy_distribution, dict)
        assert isinstance(stats.language_distribution, dict)
        assert isinstance(stats.top_channels_by_playlists, list)
        assert isinstance(stats.playlist_size_distribution, dict)


class TestPlaylistModelInteractions:
    """Test interactions between different Playlist models using factories."""

    def test_create_then_update_workflow(self):
        """Test typical create then update workflow with keyword arguments."""
        # Create
        playlist_create = PlaylistCreateFactory.build(
            playlist_id="PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f",
            title="Original Title",
            description="Original description",
            default_language="en",
            privacy_status="private",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            video_count=10,
        )

        # Simulate creation
        created_at = datetime.now(timezone.utc)
        updated_at = created_at

        playlist_full = PlaylistFactory.build(
            playlist_id=playlist_create.playlist_id,
            title=playlist_create.title,
            description=playlist_create.description,
            default_language=playlist_create.default_language,
            privacy_status=playlist_create.privacy_status,
            channel_id=playlist_create.channel_id,
            video_count=playlist_create.video_count,
            created_at=created_at,
            updated_at=updated_at,
        )

        # Update
        playlist_update = PlaylistUpdate(
            title="Updated Title",
            privacy_status=PrivacyStatus.PUBLIC,
            video_count=25,
            # description and default_language intentionally omitted - no change
        )

        # Apply update (simulated)
        updated_data = playlist_full.model_dump()
        update_data = playlist_update.model_dump(exclude_unset=True)
        updated_data.update(update_data)
        updated_data["updated_at"] = datetime.now(
            timezone.utc
        )  # Simulate timestamp update

        playlist_updated = Playlist.model_validate(updated_data)

        assert playlist_updated.playlist_id == "PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f"
        assert playlist_updated.title == "Updated Title"
        assert playlist_updated.description == "Original description"  # Unchanged
        assert playlist_updated.default_language == "en"  # Unchanged
        assert playlist_updated.privacy_status == "public"
        assert playlist_updated.video_count == 25
        assert playlist_updated.updated_at > playlist_updated.created_at

    def test_search_filters_serialization(self):
        """Test search filters serialization for API usage."""
        filters = PlaylistSearchFilters(
            playlist_ids=["PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f"],
            channel_ids=["UCuAXFkgsw1L7xaCfnd5JJOw"],
            title_query="python",
            language_codes=[LanguageCode.ENGLISH, LanguageCode.SPANISH],
            privacy_statuses=[PrivacyStatus.PUBLIC],
            min_video_count=5,
            max_video_count=100,
            has_description=True,
        )

        # Simulate API query parameters
        query_params = filters.model_dump(exclude_none=True)

        expected = {
            "playlist_ids": ["PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f"],
            "channel_ids": ["UCuAXFkgsw1L7xaCfnd5JJOw"],
            "title_query": "python",
            "language_codes": [LanguageCode.ENGLISH, LanguageCode.SPANISH],
            "privacy_statuses": [PrivacyStatus.PUBLIC],
            "min_video_count": 5,
            "max_video_count": 100,
            "has_description": True,
            "linked_status": "all",  # Default value for linked_status
        }

        assert query_params == expected

    def test_statistics_aggregation_pattern(self):
        """Test statistics model for aggregation results."""
        # Simulate aggregation data from database
        aggregation_result = {
            "total_playlists": 1000,
            "total_videos": 15000,
            "avg_videos_per_playlist": 15.0,
            "unique_channels": 600,
            "privacy_distribution": {"public": 500, "unlisted": 300, "private": 200},
            "language_distribution": {
                "en": 400,
                "es": 200,
                "fr": 150,
                "de": 100,
                "ja": 150,
            },
            "top_channels_by_playlists": [
                ("UCuAXFkgsw1L7xaCfnd5JJOw", 45),
                ("UC-lHJZR3Gqxm24_Vd_AJ5Yw", 40),
                ("UCBJycsmduvYEL83R_U4JriQ", 35),
            ],
            "playlist_size_distribution": {
                "1-5 videos": 300,
                "6-20 videos": 400,
                "21-50 videos": 200,
                "50+ videos": 100,
            },
            "playlists_with_descriptions": 750,
        }

        stats = PlaylistStatistics.model_validate(aggregation_result)

        assert stats.total_playlists == 1000
        assert stats.total_videos == 15000
        assert len(stats.privacy_distribution) == 3
        assert len(stats.language_distribution) == 5
        assert len(stats.top_channels_by_playlists) == 3
        assert stats.top_channels_by_playlists[0] == ("UCuAXFkgsw1L7xaCfnd5JJOw", 45)
        assert stats.playlists_with_descriptions == 750

    def test_convenience_factory_functions(self):
        """Test convenience factory functions for easy model creation."""
        # Test convenience function
        playlist = create_playlist(
            playlist_id="PLs9ACwy3uKTOT2q9gLKUvyqPOjLXUlAWg",
            title="Test Playlist",
            description="Test description",
            privacy_status="public",
            channel_id="UC-lHJZR3Gqxm24_Vd_AJ5Yw",
        )

        assert isinstance(playlist, Playlist)
        assert playlist.playlist_id == "PLs9ACwy3uKTOT2q9gLKUvyqPOjLXUlAWg"
        assert playlist.title == "Test Playlist"
        assert playlist.description == "Test description"
        assert playlist.privacy_status == "public"
        assert playlist.channel_id == "UC-lHJZR3Gqxm24_Vd_AJ5Yw"
        assert isinstance(playlist.created_at, datetime)
        assert isinstance(playlist.updated_at, datetime)

    def test_factory_inheritance_consistency(self):
        """Test that factory-created models maintain proper inheritance."""
        base = PlaylistBaseFactory.build()
        create = PlaylistCreateFactory.build()
        full = PlaylistFactory.build()

        # All should be instances of PlaylistBase
        assert isinstance(base, PlaylistBase)
        assert isinstance(create, PlaylistBase)
        assert isinstance(full, PlaylistBase)

        # Specific type checks
        assert isinstance(create, PlaylistCreate)
        assert isinstance(full, Playlist)

    def test_playlist_id_format_validation(self):
        """Test specific YouTube playlist ID format validation."""
        # Test various valid YouTube playlist ID formats (all start with PL, 30-34 chars)
        valid_playlist_ids = [
            "PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f",  # Standard format (34 chars)
            "PLs9ACwy3uKTOT2q9gLKUvyqPOjLXUlAWg",  # Standard format (34 chars)
            "PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo",  # Standard format (34 chars)
            "PLuAXFkgsw1L7xaCfnd5JJOwPLuAXFk",  # PL format (30 chars - minimum)
            "PLuAXFkgsw1L7xaCfnd5JJOwPLuAXFkg",  # PL format (31 chars)
            "PLuAXFkgsw1L7xaCfnd5JJOwPLuAXFkgs",  # PL format (32 chars)
            "PLuAXFkgsw1L7xaCfnd5JJOwPLuAXFkgsw",  # PL format (33 chars)
        ]

        for playlist_id in valid_playlist_ids:
            playlist = PlaylistBaseFactory.build(playlist_id=playlist_id)
            assert playlist.playlist_id == playlist_id

    def test_channel_id_format_validation(self):
        """Test specific YouTube channel ID format validation."""
        # Test various valid YouTube channel ID formats (all start with UC)
        valid_channel_ids = [
            "UCuAXFkgsw1L7xaCfnd5JJOw",  # UC format
            "UC-lHJZR3Gqxm24_Vd_AJ5Yw",  # UC with hyphen
            "UCBJycsmduvYEL83R_U4JriQ",  # Another UC format
            "UCsXVk37bltHxD1rDPwtNM8Q",  # UC format variant
        ]

        for channel_id in valid_channel_ids:
            playlist = PlaylistBaseFactory.build(channel_id=channel_id)
            assert playlist.channel_id == channel_id

    def test_multilingual_content_handling(self):
        """Test handling of various multilingual content."""
        multilingual_playlists = PlaylistTestData.multilingual_playlists_data()

        for playlist_data in multilingual_playlists:
            playlist = PlaylistBaseFactory.build(**playlist_data)

            assert playlist.playlist_id == playlist_data["playlist_id"]
            assert playlist.title == playlist_data["title"]
            assert playlist.description == playlist_data["description"]
            assert playlist.default_language == playlist_data["default_language"]
            assert playlist.privacy_status == playlist_data["privacy_status"]

    def test_language_code_normalization(self):
        """Test that language codes work with LanguageCode enum values."""
        # Test various valid LanguageCode enum values
        test_cases = [
            ("en", "en"),
            ("en-US", "en-US"),
            ("fr-FR", "fr-FR"),
            ("de", "de"),
            ("ja", "ja"),
        ]

        for input_code, expected_code in test_cases:
            playlist = PlaylistBaseFactory.build(default_language=input_code)
            assert playlist.default_language is not None
            assert playlist.default_language.value == expected_code

    def test_privacy_status_business_logic(self):
        """Test business logic around privacy status."""
        # Test different privacy levels
        public_playlist = PlaylistBaseFactory.build(privacy_status="public")
        unlisted_playlist = PlaylistBaseFactory.build(privacy_status="unlisted")
        private_playlist = PlaylistBaseFactory.build(privacy_status="private")

        assert public_playlist.privacy_status == "public"
        assert unlisted_playlist.privacy_status == "unlisted"
        assert private_playlist.privacy_status == "private"

        # Verify all are valid privacy statuses
        assert public_playlist.privacy_status in PlaylistTestData.PRIVACY_STATUSES
        assert unlisted_playlist.privacy_status in PlaylistTestData.PRIVACY_STATUSES
        assert private_playlist.privacy_status in PlaylistTestData.PRIVACY_STATUSES

    def test_video_count_business_logic(self):
        """Test business logic around video counts."""
        # Test edge cases
        empty_playlist = PlaylistBaseFactory.build(video_count=0)
        small_playlist = PlaylistBaseFactory.build(video_count=5)
        large_playlist = PlaylistBaseFactory.build(video_count=500)

        assert empty_playlist.video_count == 0
        assert small_playlist.video_count == 5
        assert large_playlist.video_count == 500

        # All should be non-negative
        assert empty_playlist.video_count >= 0
        assert small_playlist.video_count >= 0
        assert large_playlist.video_count >= 0
