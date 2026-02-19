"""
Tests for Recovery Service Models.

Comprehensive unit tests for Pydantic models in chronovista.services.recovery.models.
Covers CdxSnapshot, RecoveredVideoData, RecoveryResult, and CdxCacheEntry models
with validation, computed properties, and edge cases.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from chronovista.services.recovery.models import (
    CdxCacheEntry,
    CdxSnapshot,
    ChannelRecoveryResult,
    RecoveredChannelData,
    RecoveredVideoData,
    RecoveryResult,
)


class TestCdxSnapshot:
    """Tests for CdxSnapshot Pydantic model (T006)."""

    def test_valid_snapshot(self) -> None:
        """Test creating CdxSnapshot with valid data."""
        snapshot = CdxSnapshot(
            timestamp="20220106075526",
            original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mimetype="text/html",
            statuscode=200,
            digest="ABC123",
            length=50000,
        )

        assert snapshot.timestamp == "20220106075526"
        assert snapshot.original == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert snapshot.mimetype == "text/html"
        assert snapshot.statuscode == 200
        assert snapshot.digest == "ABC123"
        assert snapshot.length == 50000

    def test_timestamp_must_be_14_digits(self) -> None:
        """Test that timestamps must be exactly 14 digits."""
        # Too short
        with pytest.raises(ValidationError) as exc_info:
            CdxSnapshot(
                timestamp="2022010607",  # Only 10 digits
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="ABC123",
                length=50000,
            )
        assert "timestamp" in str(exc_info.value).lower()

        # Too long
        with pytest.raises(ValidationError) as exc_info:
            CdxSnapshot(
                timestamp="123456789012345",  # 15 digits
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="ABC123",
                length=50000,
            )
        assert "timestamp" in str(exc_info.value).lower()

        # Non-digits
        with pytest.raises(ValidationError) as exc_info:
            CdxSnapshot(
                timestamp="abcdefghijklmn",  # 14 characters but not digits
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="ABC123",
                length=50000,
            )
        assert "timestamp" in str(exc_info.value).lower()

    def test_statuscode_must_be_200(self) -> None:
        """Test that statuscode field accepts 200."""
        snapshot = CdxSnapshot(
            timestamp="20220106075526",
            original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mimetype="text/html",
            statuscode=200,
            digest="ABC123",
            length=50000,
        )
        assert snapshot.statuscode == 200

    def test_length_must_be_positive(self) -> None:
        """Test that length must be positive (>0)."""
        # Length = 0 should fail
        with pytest.raises(ValidationError) as exc_info:
            CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="ABC123",
                length=0,
            )
        assert "length" in str(exc_info.value).lower()

        # Negative length should fail
        with pytest.raises(ValidationError) as exc_info:
            CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="ABC123",
                length=-1000,
            )
        assert "length" in str(exc_info.value).lower()

    def test_wayback_url_property(self) -> None:
        """Test wayback_url computed property returns correct URL."""
        snapshot = CdxSnapshot(
            timestamp="20220106075526",
            original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mimetype="text/html",
            statuscode=200,
            digest="ABC123",
            length=50000,
        )

        expected_url = "https://web.archive.org/web/20220106075526id_/https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert snapshot.wayback_url == expected_url

    def test_wayback_url_rendered_property(self) -> None:
        """Test wayback_url_rendered property returns if_ format URL."""
        snapshot = CdxSnapshot(
            timestamp="20220106075526",
            original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mimetype="text/html",
            statuscode=200,
            digest="ABC123",
            length=50000,
        )

        expected_url = "https://web.archive.org/web/20220106075526if_/https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert snapshot.wayback_url_rendered == expected_url

    def test_datetime_property(self) -> None:
        """Test datetime property parses timestamp into datetime object."""
        snapshot = CdxSnapshot(
            timestamp="20220106075526",
            original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mimetype="text/html",
            statuscode=200,
            digest="ABC123",
            length=50000,
        )

        expected_datetime = datetime(2022, 1, 6, 7, 55, 26, tzinfo=timezone.utc)
        assert snapshot.datetime == expected_datetime


class TestRecoveredVideoData:
    """Tests for RecoveredVideoData Pydantic model (T007)."""

    def test_minimal_valid(self) -> None:
        """Test creating RecoveredVideoData with only required field."""
        recovered = RecoveredVideoData(snapshot_timestamp="20220106075526")

        assert recovered.snapshot_timestamp == "20220106075526"
        assert recovered.title is None
        assert recovered.description is None
        assert recovered.channel_id is None
        assert recovered.channel_name_hint is None
        assert recovered.view_count is None
        assert recovered.like_count is None
        assert recovered.tags == []  # Default empty list

    def test_full_valid(self) -> None:
        """Test creating RecoveredVideoData with all fields populated."""
        recovered = RecoveredVideoData(
            snapshot_timestamp="20220106075526",
            title="Never Gonna Give You Up",
            description="The official video for Rick Astley",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            channel_name_hint="Rick Astley",
            view_count=1000000000,
            like_count=5000000,
            tags=["music", "80s", "pop"],
        )

        assert recovered.snapshot_timestamp == "20220106075526"
        assert recovered.title == "Never Gonna Give You Up"
        assert recovered.description == "The official video for Rick Astley"
        assert recovered.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert recovered.channel_name_hint == "Rick Astley"
        assert recovered.view_count == 1000000000
        assert recovered.like_count == 5000000
        assert recovered.tags == ["music", "80s", "pop"]

    def test_channel_id_regex_validation(self) -> None:
        """Test channel_id must match UC[A-Za-z0-9_-]{22} pattern."""
        # Invalid: not a channel ID format
        with pytest.raises(ValidationError) as exc_info:
            RecoveredVideoData(
                snapshot_timestamp="20220106075526",
                channel_id="not_a_channel",
            )
        assert "channel_id" in str(exc_info.value).lower()

        # Invalid: UC but too short
        with pytest.raises(ValidationError) as exc_info:
            RecoveredVideoData(
                snapshot_timestamp="20220106075526",
                channel_id="UC_too_short",
            )
        assert "channel_id" in str(exc_info.value).lower()

        # Valid: proper channel ID format
        recovered = RecoveredVideoData(
            snapshot_timestamp="20220106075526",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
        )
        assert recovered.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"

    def test_view_count_non_negative(self) -> None:
        """Test view_count must be non-negative."""
        # Negative should fail
        with pytest.raises(ValidationError) as exc_info:
            RecoveredVideoData(
                snapshot_timestamp="20220106075526",
                view_count=-1,
            )
        assert "view_count" in str(exc_info.value).lower()

        # Zero should pass
        recovered = RecoveredVideoData(
            snapshot_timestamp="20220106075526",
            view_count=0,
        )
        assert recovered.view_count == 0

    def test_like_count_non_negative(self) -> None:
        """Test like_count must be non-negative."""
        # Negative should fail
        with pytest.raises(ValidationError) as exc_info:
            RecoveredVideoData(
                snapshot_timestamp="20220106075526",
                like_count=-1,
            )
        assert "like_count" in str(exc_info.value).lower()

        # Zero should pass
        recovered = RecoveredVideoData(
            snapshot_timestamp="20220106075526",
            like_count=0,
        )
        assert recovered.like_count == 0

    def test_snapshot_timestamp_14_digits(self) -> None:
        """Test snapshot_timestamp must be exactly 14 digits."""
        # Too short
        with pytest.raises(ValidationError) as exc_info:
            RecoveredVideoData(snapshot_timestamp="202201")
        assert "snapshot_timestamp" in str(exc_info.value).lower()

        # Non-digits
        with pytest.raises(ValidationError) as exc_info:
            RecoveredVideoData(snapshot_timestamp="abcd1234567890")
        assert "snapshot_timestamp" in str(exc_info.value).lower()

        # Valid 14 digits
        recovered = RecoveredVideoData(snapshot_timestamp="20220106075526")
        assert recovered.snapshot_timestamp == "20220106075526"

    def test_recovery_source_property(self) -> None:
        """Test recovery_source computed property returns wayback:{timestamp}."""
        recovered = RecoveredVideoData(snapshot_timestamp="20220106075526")

        expected_source = "wayback:20220106075526"
        assert recovered.recovery_source == expected_source

    def test_recovered_fields_property(self) -> None:
        """Test recovered_fields returns list of non-None field names."""
        # Only snapshot_timestamp set
        recovered_minimal = RecoveredVideoData(snapshot_timestamp="20220106075526")
        assert recovered_minimal.recovered_fields == ["snapshot_timestamp"]

        # Multiple fields set
        recovered_multi = RecoveredVideoData(
            snapshot_timestamp="20220106075526",
            title="Test Video",
            view_count=1000,
        )
        fields = recovered_multi.recovered_fields
        assert "snapshot_timestamp" in fields
        assert "title" in fields
        assert "view_count" in fields
        assert len(fields) == 3

        # Check that None fields are not included
        assert "description" not in fields
        assert "channel_id" not in fields

    def test_has_data_property(self) -> None:
        """Test has_data returns True if metadata fields are set."""
        # Only snapshot_timestamp (no metadata)
        recovered_no_data = RecoveredVideoData(snapshot_timestamp="20220106075526")
        assert recovered_no_data.has_data is False

        # With title (has metadata)
        recovered_with_title = RecoveredVideoData(
            snapshot_timestamp="20220106075526",
            title="Test Video",
        )
        assert recovered_with_title.has_data is True

        # With view_count (has metadata)
        recovered_with_views = RecoveredVideoData(
            snapshot_timestamp="20220106075526",
            view_count=100,
        )
        assert recovered_with_views.has_data is True

    def test_tags_default_empty_list(self) -> None:
        """Test tags field defaults to empty list."""
        recovered = RecoveredVideoData(snapshot_timestamp="20220106075526")
        assert recovered.tags == []
        assert isinstance(recovered.tags, list)

    def test_channel_id_none_is_valid(self) -> None:
        """Test channel_id=None is valid (optional field)."""
        recovered = RecoveredVideoData(
            snapshot_timestamp="20220106075526",
            channel_id=None,
        )
        assert recovered.channel_id is None


class TestRecoveredChannelData:
    """Tests for RecoveredChannelData Pydantic model (T003)."""

    def test_minimal_valid(self) -> None:
        """Test creating RecoveredChannelData with only required field."""
        recovered = RecoveredChannelData(snapshot_timestamp="20220106075526")

        assert recovered.snapshot_timestamp == "20220106075526"
        assert recovered.title is None
        assert recovered.description is None
        assert recovered.subscriber_count is None
        assert recovered.video_count is None
        assert recovered.thumbnail_url is None
        assert recovered.country is None
        assert recovered.default_language is None

    def test_full_valid(self) -> None:
        """Test creating RecoveredChannelData with all fields populated."""
        recovered = RecoveredChannelData(
            snapshot_timestamp="20220106075526",
            title="Rick Astley",
            description="Official Rick Astley YouTube Channel",
            subscriber_count=3000000,
            video_count=150,
            thumbnail_url="https://yt3.ggpht.com/ytc/channel_avatar.jpg",
            country="US",
            default_language="en",
        )

        assert recovered.snapshot_timestamp == "20220106075526"
        assert recovered.title == "Rick Astley"
        assert recovered.description == "Official Rick Astley YouTube Channel"
        assert recovered.subscriber_count == 3000000
        assert recovered.video_count == 150
        assert recovered.thumbnail_url == "https://yt3.ggpht.com/ytc/channel_avatar.jpg"
        assert recovered.country == "US"
        assert recovered.default_language == "en"

    def test_snapshot_timestamp_14_digits(self) -> None:
        """Test snapshot_timestamp must be exactly 14 digits."""
        # Too short
        with pytest.raises(ValidationError) as exc_info:
            RecoveredChannelData(snapshot_timestamp="202201")
        assert "snapshot_timestamp" in str(exc_info.value).lower()

        # Too long
        with pytest.raises(ValidationError) as exc_info:
            RecoveredChannelData(snapshot_timestamp="202201061234567")
        assert "snapshot_timestamp" in str(exc_info.value).lower()

        # Non-digits
        with pytest.raises(ValidationError) as exc_info:
            RecoveredChannelData(snapshot_timestamp="abcd1234567890")
        assert "snapshot_timestamp" in str(exc_info.value).lower()

        # Valid 14 digits
        recovered = RecoveredChannelData(snapshot_timestamp="20220106075526")
        assert recovered.snapshot_timestamp == "20220106075526"

    def test_subscriber_count_non_negative(self) -> None:
        """Test subscriber_count must be non-negative."""
        # Negative should fail
        with pytest.raises(ValidationError) as exc_info:
            RecoveredChannelData(
                snapshot_timestamp="20220106075526",
                subscriber_count=-1,
            )
        assert "subscriber_count" in str(exc_info.value).lower()

        # Zero should pass
        recovered = RecoveredChannelData(
            snapshot_timestamp="20220106075526",
            subscriber_count=0,
        )
        assert recovered.subscriber_count == 0

    def test_video_count_non_negative(self) -> None:
        """Test video_count must be non-negative."""
        # Negative should fail
        with pytest.raises(ValidationError) as exc_info:
            RecoveredChannelData(
                snapshot_timestamp="20220106075526",
                video_count=-1,
            )
        assert "video_count" in str(exc_info.value).lower()

        # Zero should pass
        recovered = RecoveredChannelData(
            snapshot_timestamp="20220106075526",
            video_count=0,
        )
        assert recovered.video_count == 0

    def test_country_must_be_2_char_uppercase_iso(self) -> None:
        """Test country must be 2-character uppercase ISO code if provided."""
        # Valid: 2-char uppercase
        recovered_valid = RecoveredChannelData(
            snapshot_timestamp="20220106075526",
            country="US",
        )
        assert recovered_valid.country == "US"

        # Invalid: lowercase
        with pytest.raises(ValidationError) as exc_info:
            RecoveredChannelData(
                snapshot_timestamp="20220106075526",
                country="us",
            )
        assert "country" in str(exc_info.value).lower()

        # Invalid: full country name
        with pytest.raises(ValidationError) as exc_info:
            RecoveredChannelData(
                snapshot_timestamp="20220106075526",
                country="United States",
            )
        assert "country" in str(exc_info.value).lower()

        # Invalid: too short
        with pytest.raises(ValidationError) as exc_info:
            RecoveredChannelData(
                snapshot_timestamp="20220106075526",
                country="U",
            )
        assert "country" in str(exc_info.value).lower()

        # Invalid: too long
        with pytest.raises(ValidationError) as exc_info:
            RecoveredChannelData(
                snapshot_timestamp="20220106075526",
                country="USA",
            )
        assert "country" in str(exc_info.value).lower()

    def test_recovery_source_property(self) -> None:
        """Test recovery_source computed property returns wayback:{timestamp}."""
        recovered = RecoveredChannelData(snapshot_timestamp="20220106075526")

        expected_source = "wayback:20220106075526"
        assert recovered.recovery_source == expected_source

    def test_recovered_fields_property(self) -> None:
        """Test recovered_fields returns list of non-None metadata field names."""
        # Only snapshot_timestamp set (no metadata)
        recovered_minimal = RecoveredChannelData(snapshot_timestamp="20220106075526")
        assert recovered_minimal.recovered_fields == []

        # Multiple fields set
        recovered_multi = RecoveredChannelData(
            snapshot_timestamp="20220106075526",
            title="Test Channel",
            subscriber_count=1000,
            country="US",
        )
        fields = recovered_multi.recovered_fields
        assert "title" in fields
        assert "subscriber_count" in fields
        assert "country" in fields
        assert len(fields) == 3

        # Check that None fields are not included
        assert "description" not in fields
        assert "video_count" not in fields
        # snapshot_timestamp is infrastructure, not metadata
        assert "snapshot_timestamp" not in fields

    def test_has_data_property(self) -> None:
        """Test has_data returns True if metadata fields are set."""
        # Only snapshot_timestamp (no metadata)
        recovered_no_data = RecoveredChannelData(snapshot_timestamp="20220106075526")
        assert recovered_no_data.has_data is False

        # With title (has metadata)
        recovered_with_title = RecoveredChannelData(
            snapshot_timestamp="20220106075526",
            title="Test Channel",
        )
        assert recovered_with_title.has_data is True

        # With subscriber_count (has metadata)
        recovered_with_subs = RecoveredChannelData(
            snapshot_timestamp="20220106075526",
            subscriber_count=100,
        )
        assert recovered_with_subs.has_data is True

        # With country (has metadata)
        recovered_with_country = RecoveredChannelData(
            snapshot_timestamp="20220106075526",
            country="GB",
        )
        assert recovered_with_country.has_data is True


class TestChannelRecoveryResult:
    """Tests for ChannelRecoveryResult Pydantic model (T003)."""

    def test_required_fields(self) -> None:
        """Test channel_id and success are required fields."""
        # Missing channel_id
        with pytest.raises(ValidationError) as exc_info:
            ChannelRecoveryResult(success=True)  # type: ignore[call-arg]
        assert "channel_id" in str(exc_info.value).lower()

        # Missing success
        with pytest.raises(ValidationError) as exc_info:
            ChannelRecoveryResult(channel_id="UCuAXFkgsw1L7xaCfnd5JJOw")  # type: ignore[call-arg]
        assert "success" in str(exc_info.value).lower()

        # Both provided
        result = ChannelRecoveryResult(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            success=True,
        )
        assert result.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert result.success is True

    def test_default_values(self) -> None:
        """Test default values for optional fields."""
        result = ChannelRecoveryResult(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            success=True,
        )

        assert result.success is True
        assert result.snapshot_used is None
        assert result.fields_recovered == []
        assert result.fields_skipped == []
        assert result.snapshots_available == 0
        assert result.snapshots_tried == 0
        assert result.failure_reason is None
        assert result.duration_seconds == 0.0

    def test_full_success_result(self) -> None:
        """Test creating a full success result with all fields."""
        result = ChannelRecoveryResult(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title", "description", "subscriber_count"],
            fields_skipped=["country", "default_language"],
            snapshots_available=10,
            snapshots_tried=2,
            duration_seconds=3.5,
        )

        assert result.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert result.success is True
        assert result.snapshot_used == "20220106075526"
        assert result.fields_recovered == ["title", "description", "subscriber_count"]
        assert result.fields_skipped == ["country", "default_language"]
        assert result.snapshots_available == 10
        assert result.snapshots_tried == 2
        assert result.failure_reason is None
        assert result.duration_seconds == 3.5

    def test_failure_result(self) -> None:
        """Test creating a failure result with failure_reason."""
        result = ChannelRecoveryResult(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            success=False,
            failure_reason="no_archive_found",
            snapshots_available=0,
            snapshots_tried=0,
            duration_seconds=1.2,
        )

        assert result.success is False
        assert result.failure_reason == "no_archive_found"
        assert result.snapshot_used is None
        assert result.fields_recovered == []

    def test_serialization_round_trip(self) -> None:
        """Test serialization and deserialization round-trip."""
        original = ChannelRecoveryResult(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title", "description"],
            snapshots_available=5,
            snapshots_tried=1,
            duration_seconds=2.3,
        )

        # Serialize to dict
        data = original.model_dump()

        # Deserialize back to model
        restored = ChannelRecoveryResult(**data)

        # Verify all fields match
        assert restored.channel_id == original.channel_id
        assert restored.success == original.success
        assert restored.snapshot_used == original.snapshot_used
        assert restored.fields_recovered == original.fields_recovered
        assert restored.fields_skipped == original.fields_skipped
        assert restored.snapshots_available == original.snapshots_available
        assert restored.snapshots_tried == original.snapshots_tried
        assert restored.failure_reason == original.failure_reason
        assert restored.duration_seconds == original.duration_seconds


class TestRecoveryResult:
    """Tests for RecoveryResult Pydantic model (T008)."""

    def test_required_fields(self) -> None:
        """Test video_id and success are required fields."""
        # Missing video_id
        with pytest.raises(ValidationError) as exc_info:
            RecoveryResult(success=True)  # type: ignore[call-arg]
        assert "video_id" in str(exc_info.value).lower()

        # Missing success
        with pytest.raises(ValidationError) as exc_info:
            RecoveryResult(video_id="dQw4w9WgXcQ")  # type: ignore[call-arg]
        assert "success" in str(exc_info.value).lower()

        # Both provided
        result = RecoveryResult(video_id="dQw4w9WgXcQ", success=True)
        assert result.video_id == "dQw4w9WgXcQ"
        assert result.success is True

    def test_success_result_defaults(self) -> None:
        """Test default values for successful recovery result."""
        result = RecoveryResult(video_id="dQw4w9WgXcQ", success=True)

        assert result.success is True
        assert result.fields_recovered == []
        assert result.snapshots_available == 0
        assert result.failure_reason is None
        assert result.snapshot_used is None
        assert result.channel_recovery_candidates == []

    def test_channel_field_defaults(self) -> None:
        """Test default values for channel recovery fields (T003)."""
        result = RecoveryResult(video_id="dQw4w9WgXcQ", success=True)

        assert result.channel_recovered is False
        assert result.channel_fields_recovered == []
        assert result.channel_fields_skipped == []
        assert result.channel_failure_reason is None

    def test_backward_compatibility_without_channel_fields(self) -> None:
        """Test existing RecoveryResult construction still works (T003)."""
        # This should work without providing any channel-specific fields
        result = RecoveryResult(
            video_id="dQw4w9WgXcQ",
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title", "description"],
            snapshots_available=5,
            snapshots_tried=2,
        )

        assert result.video_id == "dQw4w9WgXcQ"
        assert result.success is True
        assert result.snapshot_used == "20220106075526"
        assert result.fields_recovered == ["title", "description"]
        # Channel fields should have defaults
        assert result.channel_recovered is False
        assert result.channel_fields_recovered == []

    def test_construction_with_channel_fields(self) -> None:
        """Test RecoveryResult construction with channel recovery fields (T003)."""
        result = RecoveryResult(
            video_id="dQw4w9WgXcQ",
            success=True,
            snapshot_used="20220106075526",
            fields_recovered=["title", "description"],
            snapshots_available=5,
            snapshots_tried=2,
            channel_recovered=True,
            channel_fields_recovered=["title", "subscriber_count"],
            channel_fields_skipped=["country"],
            channel_failure_reason=None,
        )

        assert result.video_id == "dQw4w9WgXcQ"
        assert result.success is True
        # Channel fields are populated
        assert result.channel_recovered is True
        assert result.channel_fields_recovered == ["title", "subscriber_count"]
        assert result.channel_fields_skipped == ["country"]
        assert result.channel_failure_reason is None

    def test_failure_result(self) -> None:
        """Test creating a failure result with failure_reason."""
        result = RecoveryResult(
            video_id="dQw4w9WgXcQ",
            success=False,
            failure_reason="no_archive_found",
        )

        assert result.success is False
        assert result.failure_reason == "no_archive_found"

    def test_all_failure_reasons(self) -> None:
        """Test all 10 valid failure_reason values."""
        failure_reasons = [
            "no_archive_found",
            "all_snapshots_too_small",
            "all_removal_notices",
            "no_extractable_metadata",
            "extraction_failed",
            "timeout",
            "cdx_error",
            "dependency_missing",
            "video_not_found",
            "video_available",
        ]

        for reason in failure_reasons:
            result = RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=False,
                failure_reason=reason,
            )
            assert result.failure_reason == reason

    def test_video_id_validation(self) -> None:
        """Test video_id must be valid VideoId (11 chars alphanumeric)."""
        # Valid video ID
        result = RecoveryResult(video_id="dQw4w9WgXcQ", success=True)
        assert result.video_id == "dQw4w9WgXcQ"

        # Invalid: too short
        with pytest.raises(ValidationError) as exc_info:
            RecoveryResult(video_id="short", success=True)
        assert "video_id" in str(exc_info.value).lower()

        # Invalid: too long
        with pytest.raises(ValidationError) as exc_info:
            RecoveryResult(video_id="dQw4w9WgXcQTooLong", success=True)
        assert "video_id" in str(exc_info.value).lower()

    def test_channel_recovery_candidates_default(self) -> None:
        """Test channel_recovery_candidates defaults to empty list."""
        result = RecoveryResult(video_id="dQw4w9WgXcQ", success=True)
        assert result.channel_recovery_candidates == []
        assert isinstance(result.channel_recovery_candidates, list)


class TestCdxCacheEntry:
    """Tests for CdxCacheEntry Pydantic model (T009)."""

    def test_valid_cache_entry(self) -> None:
        """Test creating valid CdxCacheEntry."""
        now = datetime.now(timezone.utc)
        snapshots = [
            CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="ABC123",
                length=50000,
            )
        ]

        cache_entry = CdxCacheEntry(
            video_id="dQw4w9WgXcQ",
            fetched_at=now,
            snapshots=snapshots,
            raw_count=5,
        )

        assert cache_entry.video_id == "dQw4w9WgXcQ"
        assert cache_entry.fetched_at == now
        assert len(cache_entry.snapshots) == 1
        assert cache_entry.snapshots[0].timestamp == "20220106075526"
        assert cache_entry.raw_count == 5

    def test_fetched_at_must_be_timezone_aware(self) -> None:
        """Test fetched_at must be timezone-aware datetime."""
        snapshots = [
            CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="ABC123",
                length=50000,
            )
        ]

        # Naive datetime should fail
        naive_datetime = datetime(2022, 1, 6, 7, 55, 26)
        with pytest.raises(ValidationError) as exc_info:
            CdxCacheEntry(
                video_id="dQw4w9WgXcQ",
                fetched_at=naive_datetime,
                snapshots=snapshots,
                raw_count=1,
            )
        assert "fetched_at" in str(exc_info.value).lower()

        # UTC datetime should pass
        utc_datetime = datetime(2022, 1, 6, 7, 55, 26, tzinfo=timezone.utc)
        cache_entry = CdxCacheEntry(
            video_id="dQw4w9WgXcQ",
            fetched_at=utc_datetime,
            snapshots=snapshots,
            raw_count=1,
        )
        assert cache_entry.fetched_at.tzinfo == timezone.utc

    def test_cache_validity_check(self) -> None:
        """Test is_valid method checks cache age against TTL."""
        snapshots = [
            CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="ABC123",
                length=50000,
            )
        ]

        # Recent cache (1 hour ago) - should be valid with 24hr TTL
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        cache_entry_recent = CdxCacheEntry(
            video_id="dQw4w9WgXcQ",
            fetched_at=recent,
            snapshots=snapshots,
            raw_count=1,
        )
        assert cache_entry_recent.is_valid(ttl_hours=24) is True

        # Old cache (25 hours ago) - should be expired with 24hr TTL
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        cache_entry_old = CdxCacheEntry(
            video_id="dQw4w9WgXcQ",
            fetched_at=old,
            snapshots=snapshots,
            raw_count=1,
        )
        assert cache_entry_old.is_valid(ttl_hours=24) is False

        # Edge case: exactly 24 hours ago
        exactly_24h = datetime.now(timezone.utc) - timedelta(hours=24, seconds=1)
        cache_entry_edge = CdxCacheEntry(
            video_id="dQw4w9WgXcQ",
            fetched_at=exactly_24h,
            snapshots=snapshots,
            raw_count=1,
        )
        assert cache_entry_edge.is_valid(ttl_hours=24) is False

    def test_snapshots_list(self) -> None:
        """Test snapshots field accepts list of CdxSnapshot objects."""
        now = datetime.now(timezone.utc)
        snapshots = [
            CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="ABC123",
                length=50000,
            ),
            CdxSnapshot(
                timestamp="20210106075526",
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="DEF456",
                length=48000,
            ),
        ]

        cache_entry = CdxCacheEntry(
            video_id="dQw4w9WgXcQ",
            fetched_at=now,
            snapshots=snapshots,
            raw_count=2,
        )

        assert len(cache_entry.snapshots) == 2
        assert cache_entry.snapshots[0].digest == "ABC123"
        assert cache_entry.snapshots[1].digest == "DEF456"

    def test_raw_count_field(self) -> None:
        """Test raw_count field stores CDX entry count before filtering."""
        now = datetime.now(timezone.utc)
        snapshots = [
            CdxSnapshot(
                timestamp="20220106075526",
                original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mimetype="text/html",
                statuscode=200,
                digest="ABC123",
                length=50000,
            )
        ]

        # raw_count can be different from len(snapshots) due to filtering
        cache_entry = CdxCacheEntry(
            video_id="dQw4w9WgXcQ",
            fetched_at=now,
            snapshots=snapshots,
            raw_count=10,  # 10 raw entries, but only 1 after filtering
        )

        assert cache_entry.raw_count == 10
        assert len(cache_entry.snapshots) == 1
