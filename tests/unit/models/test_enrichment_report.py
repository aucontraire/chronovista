"""
Tests for enrichment report Pydantic models.

Tests validation, serialization, and JSON compatibility for
metadata enrichment reporting models.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.enrichment_report import (
    EnrichmentDetail,
    EnrichmentReport,
    EnrichmentSummary,
)


class TestEnrichmentSummary:
    """Test EnrichmentSummary model validation."""

    def test_create_valid_enrichment_summary(self):
        """Test creating valid EnrichmentSummary with all fields."""
        summary = EnrichmentSummary(
            videos_processed=100,
            videos_updated=85,
            videos_deleted=10,
            channels_created=5,
            tags_created=250,
            topic_associations=180,
            categories_assigned=90,
            errors=5,
            quota_used=1500,
        )

        assert summary.videos_processed == 100
        assert summary.videos_updated == 85
        assert summary.videos_deleted == 10
        assert summary.channels_created == 5
        assert summary.tags_created == 250
        assert summary.topic_associations == 180
        assert summary.categories_assigned == 90
        assert summary.errors == 5
        assert summary.quota_used == 1500

    def test_create_enrichment_summary_minimal(self):
        """Test creating EnrichmentSummary with minimal values."""
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

        assert summary.videos_processed == 0
        assert summary.videos_updated == 0
        assert summary.videos_deleted == 0
        assert summary.channels_created == 0
        assert summary.tags_created == 0
        assert summary.topic_associations == 0
        assert summary.categories_assigned == 0
        assert summary.errors == 0
        assert summary.quota_used == 0

    def test_all_fields_required(self):
        """Test that all fields are required."""
        # Missing videos_processed
        with pytest.raises(ValidationError):
            EnrichmentSummary(
                videos_updated=10,
                videos_deleted=0,
                channels_created=0,
                tags_created=0,
                topic_associations=0,
                categories_assigned=0,
                errors=0,
                quota_used=0,
            )

    def test_negative_values_rejected(self):
        """Test that negative values are rejected."""
        fields = [
            "videos_processed",
            "videos_updated",
            "videos_deleted",
            "channels_created",
            "tags_created",
            "topic_associations",
            "categories_assigned",
            "errors",
            "quota_used",
        ]

        for field in fields:
            kwargs = {f: 0 for f in fields}
            kwargs[field] = -1

            with pytest.raises(ValidationError) as exc_info:
                EnrichmentSummary(**kwargs)
            assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_model_dump_functionality(self):
        """Test model_dump() method for serialization."""
        summary = EnrichmentSummary(
            videos_processed=50,
            videos_updated=45,
            videos_deleted=2,
            channels_created=3,
            tags_created=120,
            topic_associations=90,
            categories_assigned=48,
            errors=1,
            quota_used=750,
        )

        data = summary.model_dump()
        expected = {
            "videos_processed": 50,
            "videos_updated": 45,
            "videos_deleted": 2,
            "channels_created": 3,
            "tags_created": 120,
            "topic_associations": 90,
            "categories_assigned": 48,
            "errors": 1,
            "quota_used": 750,
            # Playlist enrichment fields (defaults to 0)
            "playlists_processed": 0,
            "playlists_updated": 0,
            "playlists_deleted": 0,
        }

        assert data == expected

    def test_model_validate_functionality(self):
        """Test model_validate() method for deserialization."""
        data = {
            "videos_processed": 100,
            "videos_updated": 95,
            "videos_deleted": 3,
            "channels_created": 2,
            "tags_created": 200,
            "topic_associations": 150,
            "categories_assigned": 97,
            "errors": 2,
            "quota_used": 1000,
        }

        summary = EnrichmentSummary.model_validate(data)

        assert summary.videos_processed == 100
        assert summary.videos_updated == 95
        assert summary.videos_deleted == 3
        assert summary.channels_created == 2
        assert summary.tags_created == 200
        assert summary.topic_associations == 150
        assert summary.categories_assigned == 97
        assert summary.errors == 2
        assert summary.quota_used == 1000


class TestEnrichmentDetail:
    """Test EnrichmentDetail model validation."""

    def test_create_valid_enrichment_detail_updated(self):
        """Test creating valid EnrichmentDetail for updated video."""
        detail = EnrichmentDetail(
            video_id="dQw4w9WgXcQ",
            status="updated",
            old_title="Old Title",
            new_title="New Title",
            old_channel="UCOldChannel123",
            new_channel="UCNewChannel456",
            tags_count=15,
            topics_count=3,
            category_id="10",
        )

        assert detail.video_id == "dQw4w9WgXcQ"
        assert detail.status == "updated"
        assert detail.old_title == "Old Title"
        assert detail.new_title == "New Title"
        assert detail.old_channel == "UCOldChannel123"
        assert detail.new_channel == "UCNewChannel456"
        assert detail.tags_count == 15
        assert detail.topics_count == 3
        assert detail.category_id == "10"
        assert detail.error is None

    def test_create_enrichment_detail_deleted(self):
        """Test creating EnrichmentDetail for deleted video."""
        detail = EnrichmentDetail(
            video_id="dQw4w9WgXcQ",
            status="deleted",
        )

        assert detail.video_id == "dQw4w9WgXcQ"
        assert detail.status == "deleted"
        assert detail.old_title is None
        assert detail.new_title is None
        assert detail.old_channel is None
        assert detail.new_channel is None
        assert detail.tags_count is None
        assert detail.topics_count is None
        assert detail.category_id is None
        assert detail.error is None

    def test_create_enrichment_detail_error(self):
        """Test creating EnrichmentDetail for error status."""
        detail = EnrichmentDetail(
            video_id="dQw4w9WgXcQ",
            status="error",
            error="Video not found in YouTube API",
        )

        assert detail.video_id == "dQw4w9WgXcQ"
        assert detail.status == "error"
        assert detail.error == "Video not found in YouTube API"

    def test_create_enrichment_detail_skipped(self):
        """Test creating EnrichmentDetail for skipped video."""
        detail = EnrichmentDetail(
            video_id="dQw4w9WgXcQ",
            status="skipped",
        )

        assert detail.video_id == "dQw4w9WgXcQ"
        assert detail.status == "skipped"

    def test_status_literal_validation(self):
        """Test status field accepts only valid Literal values."""
        valid_statuses = ["updated", "deleted", "error", "skipped"]

        for status in valid_statuses:
            detail = EnrichmentDetail(video_id="test123", status=status)
            assert detail.status == status

        # Invalid status
        with pytest.raises(ValidationError) as exc_info:
            EnrichmentDetail(video_id="test123", status="invalid")
        assert "Input should be 'updated', 'deleted', 'error' or 'skipped'" in str(
            exc_info.value
        )

    def test_video_id_required(self):
        """Test video_id is required."""
        with pytest.raises(ValidationError):
            EnrichmentDetail(status="updated")

    def test_video_id_min_length(self):
        """Test video_id has minimum length of 1."""
        with pytest.raises(ValidationError):
            EnrichmentDetail(video_id="", status="updated")

    def test_tags_count_validation(self):
        """Test tags_count validation (non-negative)."""
        # Valid tags_count
        detail = EnrichmentDetail(video_id="test", status="updated", tags_count=0)
        assert detail.tags_count == 0

        detail = EnrichmentDetail(video_id="test", status="updated", tags_count=100)
        assert detail.tags_count == 100

        # Negative tags_count rejected
        with pytest.raises(ValidationError):
            EnrichmentDetail(video_id="test", status="updated", tags_count=-1)

    def test_topics_count_validation(self):
        """Test topics_count validation (non-negative)."""
        # Valid topics_count
        detail = EnrichmentDetail(video_id="test", status="updated", topics_count=0)
        assert detail.topics_count == 0

        detail = EnrichmentDetail(video_id="test", status="updated", topics_count=50)
        assert detail.topics_count == 50

        # Negative topics_count rejected
        with pytest.raises(ValidationError):
            EnrichmentDetail(video_id="test", status="updated", topics_count=-1)

    def test_category_id_max_length(self):
        """Test category_id max length of 10 characters."""
        # Valid length
        detail = EnrichmentDetail(
            video_id="test", status="updated", category_id="1234567890"
        )
        assert detail.category_id == "1234567890"

        # Too long
        with pytest.raises(ValidationError):
            EnrichmentDetail(
                video_id="test", status="updated", category_id="12345678901"
            )

    def test_optional_fields_default_to_none(self):
        """Test optional fields default to None."""
        detail = EnrichmentDetail(video_id="test", status="updated")

        assert detail.old_title is None
        assert detail.new_title is None
        assert detail.old_channel is None
        assert detail.new_channel is None
        assert detail.tags_count is None
        assert detail.topics_count is None
        assert detail.category_id is None
        assert detail.error is None

    def test_model_dump_functionality(self):
        """Test model_dump() method for serialization."""
        detail = EnrichmentDetail(
            video_id="dQw4w9WgXcQ",
            status="updated",
            new_title="New Title",
            tags_count=10,
        )

        data = detail.model_dump()

        assert data["video_id"] == "dQw4w9WgXcQ"
        assert data["status"] == "updated"
        assert data["new_title"] == "New Title"
        assert data["tags_count"] == 10
        assert data["old_title"] is None

    def test_model_dump_excludes_none(self):
        """Test model_dump() can exclude None values."""
        detail = EnrichmentDetail(
            video_id="dQw4w9WgXcQ",
            status="updated",
            tags_count=10,
        )

        data = detail.model_dump(exclude_none=True)

        assert data == {
            "video_id": "dQw4w9WgXcQ",
            "status": "updated",
            "tags_count": 10,
        }
        assert "old_title" not in data
        assert "new_title" not in data


class TestEnrichmentReport:
    """Test EnrichmentReport model validation and JSON serialization."""

    def test_create_valid_enrichment_report(self):
        """Test creating valid EnrichmentReport with all fields."""
        timestamp = datetime.now(timezone.utc)
        summary = EnrichmentSummary(
            videos_processed=10,
            videos_updated=8,
            videos_deleted=1,
            channels_created=2,
            tags_created=40,
            topic_associations=25,
            categories_assigned=9,
            errors=1,
            quota_used=150,
        )
        details = [
            EnrichmentDetail(video_id="vid1", status="updated", tags_count=5),
            EnrichmentDetail(video_id="vid2", status="deleted"),
        ]

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
            details=details,
        )

        assert report.timestamp == timestamp
        assert report.priority == "high"
        assert report.summary == summary
        assert len(report.details) == 2
        assert report.details[0].video_id == "vid1"
        assert report.details[1].video_id == "vid2"

    def test_create_enrichment_report_minimal(self):
        """Test creating EnrichmentReport with minimal fields."""
        timestamp = datetime.now(timezone.utc)
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

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="low",
            summary=summary,
        )

        assert report.timestamp == timestamp
        assert report.priority == "low"
        assert report.summary == summary
        assert report.details == []

    def test_timestamp_required(self):
        """Test timestamp is required."""
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

        with pytest.raises(ValidationError):
            EnrichmentReport(priority="high", summary=summary)

    def test_priority_required(self):
        """Test priority is required."""
        timestamp = datetime.now(timezone.utc)
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

        with pytest.raises(ValidationError):
            EnrichmentReport(timestamp=timestamp, summary=summary)

    def test_priority_min_length(self):
        """Test priority has minimum length of 1."""
        timestamp = datetime.now(timezone.utc)
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

        with pytest.raises(ValidationError):
            EnrichmentReport(timestamp=timestamp, priority="", summary=summary)

    def test_summary_required(self):
        """Test summary is required."""
        timestamp = datetime.now(timezone.utc)

        with pytest.raises(ValidationError):
            EnrichmentReport(timestamp=timestamp, priority="high")

    def test_details_defaults_to_empty_list(self):
        """Test details defaults to empty list."""
        timestamp = datetime.now(timezone.utc)
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

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
        )

        assert report.details == []
        assert isinstance(report.details, list)

    def test_json_serialization(self):
        """Test EnrichmentReport can be serialized to JSON."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        summary = EnrichmentSummary(
            videos_processed=5,
            videos_updated=4,
            videos_deleted=1,
            channels_created=1,
            tags_created=20,
            topic_associations=15,
            categories_assigned=4,
            errors=0,
            quota_used=75,
        )
        details = [
            EnrichmentDetail(
                video_id="vid1",
                status="updated",
                new_title="New Title",
                tags_count=5,
            ),
            EnrichmentDetail(video_id="vid2", status="deleted"),
        ]

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
            details=details,
        )

        # Serialize to JSON
        json_str = report.model_dump_json()
        assert isinstance(json_str, str)

        # Parse JSON
        parsed_data = json.loads(json_str)

        assert parsed_data["priority"] == "high"
        assert parsed_data["summary"]["videos_processed"] == 5
        assert len(parsed_data["details"]) == 2
        assert parsed_data["details"][0]["video_id"] == "vid1"

    def test_json_deserialization(self):
        """Test EnrichmentReport can be deserialized from JSON."""
        json_data = {
            "timestamp": "2024-01-15T10:30:00Z",
            "priority": "high",
            "summary": {
                "videos_processed": 5,
                "videos_updated": 4,
                "videos_deleted": 1,
                "channels_created": 1,
                "tags_created": 20,
                "topic_associations": 15,
                "categories_assigned": 4,
                "errors": 0,
                "quota_used": 75,
            },
            "details": [
                {
                    "video_id": "vid1",
                    "status": "updated",
                    "new_title": "New Title",
                    "tags_count": 5,
                },
                {"video_id": "vid2", "status": "deleted"},
            ],
        }

        report = EnrichmentReport.model_validate(json_data)

        assert report.priority == "high"
        assert report.summary.videos_processed == 5
        assert len(report.details) == 2
        assert report.details[0].video_id == "vid1"
        assert report.details[1].status == "deleted"

    def test_iso_8601_timestamp_format(self):
        """Test timestamp uses ISO 8601 format in JSON."""
        timestamp = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
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

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
        )

        json_str = report.model_dump_json()
        parsed = json.loads(json_str)

        # ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ
        assert "2024-01-15T10:30:45" in parsed["timestamp"]

    def test_roundtrip_json_serialization(self):
        """Test that report can be serialized and deserialized without data loss."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        summary = EnrichmentSummary(
            videos_processed=10,
            videos_updated=9,
            videos_deleted=1,
            channels_created=2,
            tags_created=45,
            topic_associations=30,
            categories_assigned=10,
            errors=0,
            quota_used=150,
        )
        details = [
            EnrichmentDetail(
                video_id="vid1",
                status="updated",
                old_title="Old",
                new_title="New",
                tags_count=5,
                topics_count=2,
                category_id="10",
            ),
            EnrichmentDetail(video_id="vid2", status="error", error="API error"),
        ]

        original_report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
            details=details,
        )

        # Serialize to JSON
        json_str = original_report.model_dump_json()

        # Deserialize from JSON
        deserialized_report = EnrichmentReport.model_validate_json(json_str)

        # Verify data integrity
        assert deserialized_report.priority == original_report.priority
        assert (
            deserialized_report.summary.videos_processed
            == original_report.summary.videos_processed
        )
        assert len(deserialized_report.details) == len(original_report.details)
        assert deserialized_report.details[0].video_id == "vid1"
        assert deserialized_report.details[0].old_title == "Old"
        assert deserialized_report.details[1].error == "API error"

    def test_model_dump_functionality(self):
        """Test model_dump() method for serialization."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        summary = EnrichmentSummary(
            videos_processed=3,
            videos_updated=2,
            videos_deleted=1,
            channels_created=1,
            tags_created=10,
            topic_associations=8,
            categories_assigned=3,
            errors=0,
            quota_used=50,
        )

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="medium",
            summary=summary,
        )

        data = report.model_dump()

        assert data["timestamp"] == timestamp
        assert data["priority"] == "medium"
        assert data["summary"]["videos_processed"] == 3
        assert data["details"] == []


class TestEnrichmentReportModelInteractions:
    """Test interactions between enrichment report models."""

    def test_complete_enrichment_workflow(self):
        """Test complete workflow of creating enrichment report."""
        # Simulate enrichment operation
        timestamp = datetime.now(timezone.utc)

        # Create summary
        summary = EnrichmentSummary(
            videos_processed=100,
            videos_updated=85,
            videos_deleted=10,
            channels_created=5,
            tags_created=250,
            topic_associations=200,
            categories_assigned=90,
            errors=5,
            quota_used=1500,
        )

        # Create details
        details = []
        for i in range(10):
            detail = EnrichmentDetail(
                video_id=f"vid{i}",
                status="updated" if i < 8 else "deleted",
                tags_count=i * 2 if i < 8 else None,
            )
            details.append(detail)

        # Create report
        report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
            details=details,
        )

        # Verify report structure
        assert report.summary.videos_processed == 100
        assert len(report.details) == 10
        assert report.details[0].status == "updated"
        assert report.details[9].status == "deleted"

    def test_error_handling_in_enrichment_report(self):
        """Test enrichment report with error details."""
        timestamp = datetime.now(timezone.utc)
        summary = EnrichmentSummary(
            videos_processed=5,
            videos_updated=3,
            videos_deleted=0,
            channels_created=0,
            tags_created=15,
            topic_associations=10,
            categories_assigned=3,
            errors=2,
            quota_used=75,
        )

        details = [
            EnrichmentDetail(video_id="vid1", status="updated", tags_count=5),
            EnrichmentDetail(
                video_id="vid2",
                status="error",
                error="Video not found",
            ),
            EnrichmentDetail(
                video_id="vid3",
                status="error",
                error="API quota exceeded",
            ),
        ]

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
            details=details,
        )

        # Count errors
        error_details = [d for d in report.details if d.status == "error"]
        assert len(error_details) == 2
        assert report.summary.errors == 2

    def test_priority_levels(self):
        """Test different priority levels in enrichment reports."""
        timestamp = datetime.now(timezone.utc)
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

        priorities = ["high", "medium", "low", "critical", "routine"]

        for priority in priorities:
            report = EnrichmentReport(
                timestamp=timestamp,
                priority=priority,
                summary=summary,
            )
            assert report.priority == priority

    def test_empty_enrichment_report(self):
        """Test enrichment report with no processed videos."""
        timestamp = datetime.now(timezone.utc)
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

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="low",
            summary=summary,
            details=[],
        )

        assert report.summary.videos_processed == 0
        assert len(report.details) == 0

    def test_large_enrichment_report(self):
        """Test enrichment report with many details."""
        timestamp = datetime.now(timezone.utc)
        summary = EnrichmentSummary(
            videos_processed=1000,
            videos_updated=900,
            videos_deleted=50,
            channels_created=20,
            tags_created=5000,
            topic_associations=4000,
            categories_assigned=950,
            errors=50,
            quota_used=15000,
        )

        # Create large number of details
        details = [
            EnrichmentDetail(video_id=f"vid{i}", status="updated", tags_count=i % 20)
            for i in range(1000)
        ]

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
            details=details,
        )

        assert len(report.details) == 1000
        assert report.summary.videos_processed == 1000


class TestEnrichmentReportJSONSerialization:
    """Tests for EnrichmentReport JSON serialization (T061a).

    Covers:
    - model_dump_json() produces valid JSON
    - datetime fields serialize as ISO 8601 strings
    - EnrichmentDetail includes all required fields
    - EnrichmentSummary serializes correctly
    - Report with empty details list
    - Report with multiple details (updated, deleted, error statuses)
    """

    def test_model_dump_json_produces_valid_json(self) -> None:
        """Test that model_dump_json() produces valid JSON."""
        timestamp = datetime(2024, 6, 15, 12, 30, 45, tzinfo=timezone.utc)
        summary = EnrichmentSummary(
            videos_processed=25,
            videos_updated=20,
            videos_deleted=3,
            channels_created=2,
            tags_created=100,
            topic_associations=75,
            categories_assigned=22,
            errors=2,
            quota_used=1,
        )
        report = EnrichmentReport(
            timestamp=timestamp,
            priority="medium",
            summary=summary,
            details=[],
        )

        json_str = report.model_dump_json()

        # Verify it's a valid JSON string
        assert isinstance(json_str, str)
        assert len(json_str) > 0

        # Verify it can be parsed as JSON
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

        # Verify structure
        assert "timestamp" in parsed
        assert "priority" in parsed
        assert "summary" in parsed
        assert "details" in parsed

    def test_datetime_fields_serialize_as_iso8601(self) -> None:
        """Test that datetime fields serialize as ISO 8601 strings."""
        # Use a specific timestamp with milliseconds
        timestamp = datetime(2024, 12, 25, 8, 30, 15, 123456, tzinfo=timezone.utc)
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
        report = EnrichmentReport(
            timestamp=timestamp,
            priority="low",
            summary=summary,
        )

        json_str = report.model_dump_json()
        parsed = json.loads(json_str)

        # Verify timestamp is ISO 8601 format
        timestamp_str = parsed["timestamp"]
        assert "2024-12-25" in timestamp_str
        assert "T" in timestamp_str  # ISO 8601 separator

        # Verify we can parse it back to a datetime
        # Handle Z suffix for UTC
        parsed_timestamp = timestamp_str.replace("Z", "+00:00")
        reconstructed = datetime.fromisoformat(parsed_timestamp)
        assert reconstructed.year == 2024
        assert reconstructed.month == 12
        assert reconstructed.day == 25

    def test_enrichment_detail_includes_all_required_fields(self) -> None:
        """Test that EnrichmentDetail includes all required fields in JSON."""
        detail = EnrichmentDetail(
            video_id="test_video_123",
            status="updated",
            old_title="Old Video Title",
            new_title="New Video Title",
            old_channel="UColdChannel123",
            new_channel="UCnewChannel456",
            tags_count=15,
            topics_count=5,
            category_id="22",
            error=None,
        )

        json_str = detail.model_dump_json()
        parsed = json.loads(json_str)

        # Verify required fields
        assert parsed["video_id"] == "test_video_123"
        assert parsed["status"] == "updated"

        # Verify optional fields are included
        assert parsed["old_title"] == "Old Video Title"
        assert parsed["new_title"] == "New Video Title"
        assert parsed["old_channel"] == "UColdChannel123"
        assert parsed["new_channel"] == "UCnewChannel456"
        assert parsed["tags_count"] == 15
        assert parsed["topics_count"] == 5
        assert parsed["category_id"] == "22"
        assert parsed["error"] is None

    def test_enrichment_summary_serializes_correctly(self) -> None:
        """Test that EnrichmentSummary serializes all fields correctly."""
        summary = EnrichmentSummary(
            videos_processed=1000,
            videos_updated=850,
            videos_deleted=100,
            channels_created=50,
            tags_created=5000,
            topic_associations=3500,
            categories_assigned=900,
            errors=50,
            quota_used=200,
        )

        json_str = summary.model_dump_json()
        parsed = json.loads(json_str)

        # Verify all fields are present with correct values
        assert parsed["videos_processed"] == 1000
        assert parsed["videos_updated"] == 850
        assert parsed["videos_deleted"] == 100
        assert parsed["channels_created"] == 50
        assert parsed["tags_created"] == 5000
        assert parsed["topic_associations"] == 3500
        assert parsed["categories_assigned"] == 900
        assert parsed["errors"] == 50
        assert parsed["quota_used"] == 200

    def test_report_with_empty_details_list(self) -> None:
        """Test that report with empty details list serializes correctly."""
        timestamp = datetime(2024, 3, 10, 15, 0, 0, tzinfo=timezone.utc)
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
        report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
            details=[],  # Explicit empty list
        )

        json_str = report.model_dump_json()
        parsed = json.loads(json_str)

        # Verify details is an empty list
        assert parsed["details"] == []
        assert isinstance(parsed["details"], list)
        assert len(parsed["details"]) == 0

    def test_report_with_multiple_status_types(self) -> None:
        """Test report with multiple details having different statuses."""
        timestamp = datetime(2024, 7, 20, 10, 15, 30, tzinfo=timezone.utc)
        summary = EnrichmentSummary(
            videos_processed=5,
            videos_updated=2,
            videos_deleted=1,
            channels_created=1,
            tags_created=20,
            topic_associations=10,
            categories_assigned=2,
            errors=2,
            quota_used=1,
        )

        details = [
            EnrichmentDetail(
                video_id="updated_vid_1",
                status="updated",
                old_title="Old Title 1",
                new_title="New Title 1",
                tags_count=10,
                topics_count=3,
                category_id="10",
            ),
            EnrichmentDetail(
                video_id="updated_vid_2",
                status="updated",
                old_title="Old Title 2",
                new_title="New Title 2",
                tags_count=5,
            ),
            EnrichmentDetail(
                video_id="deleted_vid_1",
                status="deleted",
                old_title="Deleted Video Title",
            ),
            EnrichmentDetail(
                video_id="error_vid_1",
                status="error",
                error="Video not found in API response",
            ),
            EnrichmentDetail(
                video_id="error_vid_2",
                status="error",
                error="API quota exceeded during fetch",
            ),
        ]

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="all",
            summary=summary,
            details=details,
        )

        json_str = report.model_dump_json()
        parsed = json.loads(json_str)

        # Verify structure
        assert len(parsed["details"]) == 5

        # Verify each status type is present
        statuses = [d["status"] for d in parsed["details"]]
        assert statuses.count("updated") == 2
        assert statuses.count("deleted") == 1
        assert statuses.count("error") == 2

        # Verify error messages are preserved
        error_details = [d for d in parsed["details"] if d["status"] == "error"]
        assert len(error_details) == 2
        assert error_details[0]["error"] == "Video not found in API response"
        assert error_details[1]["error"] == "API quota exceeded during fetch"

        # Verify deleted detail
        deleted_details = [d for d in parsed["details"] if d["status"] == "deleted"]
        assert len(deleted_details) == 1
        assert deleted_details[0]["video_id"] == "deleted_vid_1"

    def test_report_serialization_preserves_numeric_types(self) -> None:
        """Test that numeric fields remain as integers after serialization."""
        summary = EnrichmentSummary(
            videos_processed=999999,
            videos_updated=888888,
            videos_deleted=77777,
            channels_created=6666,
            tags_created=55555,
            topic_associations=4444,
            categories_assigned=333,
            errors=22,
            quota_used=1,
        )

        json_str = summary.model_dump_json()
        parsed = json.loads(json_str)

        # Verify all numeric fields are integers
        assert isinstance(parsed["videos_processed"], int)
        assert isinstance(parsed["videos_updated"], int)
        assert isinstance(parsed["videos_deleted"], int)
        assert isinstance(parsed["channels_created"], int)
        assert isinstance(parsed["tags_created"], int)
        assert isinstance(parsed["topic_associations"], int)
        assert isinstance(parsed["categories_assigned"], int)
        assert isinstance(parsed["errors"], int)
        assert isinstance(parsed["quota_used"], int)

    def test_detail_with_skipped_status(self) -> None:
        """Test EnrichmentDetail with 'skipped' status serializes correctly."""
        detail = EnrichmentDetail(
            video_id="skipped_vid_1",
            status="skipped",
        )

        json_str = detail.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["video_id"] == "skipped_vid_1"
        assert parsed["status"] == "skipped"
        # Optional fields should be null
        assert parsed["old_title"] is None
        assert parsed["new_title"] is None
        assert parsed["error"] is None

    def test_json_serialization_with_special_characters(self) -> None:
        """Test JSON serialization handles special characters in strings."""
        detail = EnrichmentDetail(
            video_id="vid_special_chars",
            status="updated",
            old_title='Title with "quotes" and \\backslash',
            new_title="Title with <angle> brackets & ampersand",
            error="Error: can't parse \n newline",
        )

        json_str = detail.model_dump_json()

        # Should be valid JSON despite special characters
        parsed = json.loads(json_str)

        assert parsed["old_title"] == 'Title with "quotes" and \\backslash'
        assert parsed["new_title"] == "Title with <angle> brackets & ampersand"
        assert "newline" in parsed["error"]
