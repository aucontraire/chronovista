"""
Tests for EnrichmentReport JSON file generation (T061b - Phase 8, User Story 6).

Covers:
- Report file is created at specified path
- Report contains valid JSON
- Report matches EnrichmentReport schema
- Default path generation (./exports/enrichment-{timestamp}.json)
- Exports directory is created if missing
- Report includes all enrichment details
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from chronovista.models.enrichment_report import (
    EnrichmentDetail,
    EnrichmentReport,
    EnrichmentSummary,
)


def create_sample_report(
    priority: str = "high",
    num_details: int = 3,
) -> EnrichmentReport:
    """Create a sample EnrichmentReport for testing."""
    timestamp = datetime.now(timezone.utc)
    summary = EnrichmentSummary(
        videos_processed=num_details,
        videos_updated=num_details - 1 if num_details > 0 else 0,
        videos_deleted=1 if num_details > 1 else 0,
        channels_created=1,
        tags_created=num_details * 5,
        topic_associations=num_details * 3,
        categories_assigned=num_details - 1 if num_details > 0 else 0,
        errors=0,
        quota_used=(num_details + 49) // 50 if num_details > 0 else 0,
    )

    details = []
    for i in range(num_details):
        if i == 0:
            details.append(
                EnrichmentDetail(
                    video_id=f"vid_{i:03d}",
                    status="deleted",
                    old_title=f"Old Title {i}",
                )
            )
        else:
            details.append(
                EnrichmentDetail(
                    video_id=f"vid_{i:03d}",
                    status="updated",
                    old_title=f"Old Title {i}",
                    new_title=f"New Title {i}",
                    tags_count=5,
                    topics_count=3,
                    category_id="10",
                )
            )

    return EnrichmentReport(
        timestamp=timestamp,
        priority=priority,
        summary=summary,
        details=details,
    )


def generate_default_report_path(
    base_dir: Path,
    timestamp: datetime | None = None,
) -> Path:
    """
    Generate a default report path with timestamp.

    This simulates the expected behavior of the enrichment CLI when
    no --output path is provided.

    Parameters
    ----------
    base_dir : Path
        Base directory for exports
    timestamp : datetime | None
        Timestamp to use; defaults to current time

    Returns
    -------
    Path
        Full path to the report file
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Format: enrichment-YYYYMMDD-HHMMSS.json
    timestamp_str = timestamp.strftime("%Y%m%d-%H%M%S")
    return base_dir / "exports" / f"enrichment-{timestamp_str}.json"


def save_report_to_file(report: EnrichmentReport, path: Path) -> None:
    """
    Save an EnrichmentReport to a JSON file.

    This simulates the expected behavior of the enrichment service
    report generation functionality.

    Parameters
    ----------
    report : EnrichmentReport
        The report to save
    path : Path
        Path to save the report to
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON to file
    with open(path, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))


class TestReportFileCreation:
    """Tests for report file creation at specified path."""

    def test_report_file_created_at_specified_path(self, tmp_path: Path) -> None:
        """Test that report file is created at the specified path."""
        report = create_sample_report()
        report_path = tmp_path / "test-report.json"

        save_report_to_file(report, report_path)

        assert report_path.exists()
        assert report_path.is_file()

    def test_report_file_in_subdirectory(self, tmp_path: Path) -> None:
        """Test that report file is created in a subdirectory."""
        report = create_sample_report()
        report_path = tmp_path / "subdir" / "nested" / "report.json"

        save_report_to_file(report, report_path)

        assert report_path.exists()
        assert report_path.parent.is_dir()

    def test_report_file_with_custom_name(self, tmp_path: Path) -> None:
        """Test report file with custom name."""
        report = create_sample_report()
        report_path = tmp_path / "my-custom-enrichment-report.json"

        save_report_to_file(report, report_path)

        assert report_path.exists()
        assert "my-custom-enrichment-report" in report_path.name


class TestReportContainsValidJSON:
    """Tests for report containing valid JSON."""

    def test_report_file_contains_valid_json(self, tmp_path: Path) -> None:
        """Test that the saved report contains valid JSON."""
        report = create_sample_report()
        report_path = tmp_path / "test-report.json"

        save_report_to_file(report, report_path)

        # Read and parse the file
        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        assert isinstance(parsed, dict)

    def test_report_file_is_utf8_encoded(self, tmp_path: Path) -> None:
        """Test that the report file is UTF-8 encoded."""
        # Create report with unicode characters
        report = create_sample_report()
        # Modify a detail to include unicode
        if report.details:
            report.details[0] = EnrichmentDetail(
                video_id="vid_unicode",
                status="updated",
                old_title="Title with unicode: \u00e9\u00e8\u00ea",
                new_title="Japanese: \u65e5\u672c\u8a9e",
            )

        report_path = tmp_path / "test-unicode.json"
        save_report_to_file(report, report_path)

        # Should be readable as UTF-8
        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        assert "\u00e9" in parsed["details"][0]["old_title"]
        assert "\u65e5" in parsed["details"][0]["new_title"]

    def test_report_file_is_pretty_printed(self, tmp_path: Path) -> None:
        """Test that the JSON is pretty-printed with indentation."""
        report = create_sample_report()
        report_path = tmp_path / "test-report.json"

        save_report_to_file(report, report_path)

        content = report_path.read_text(encoding="utf-8")

        # Pretty-printed JSON should have multiple lines
        lines = content.split("\n")
        assert len(lines) > 10  # A reasonably formatted report has many lines

        # Should have proper indentation (2 spaces based on our indent=2)
        assert "  " in content  # Has indentation


class TestReportMatchesSchema:
    """Tests for report matching EnrichmentReport schema."""

    def test_report_file_can_be_parsed_as_enrichment_report(
        self, tmp_path: Path
    ) -> None:
        """Test that saved report can be parsed back to EnrichmentReport."""
        original_report = create_sample_report()
        report_path = tmp_path / "test-report.json"

        save_report_to_file(original_report, report_path)

        # Read and parse back
        content = report_path.read_text(encoding="utf-8")
        restored_report = EnrichmentReport.model_validate_json(content)

        # Verify key fields match
        assert restored_report.priority == original_report.priority
        assert (
            restored_report.summary.videos_processed
            == original_report.summary.videos_processed
        )
        assert len(restored_report.details) == len(original_report.details)

    def test_report_contains_all_summary_fields(self, tmp_path: Path) -> None:
        """Test that saved report contains all EnrichmentSummary fields."""
        report = create_sample_report()
        report_path = tmp_path / "test-report.json"

        save_report_to_file(report, report_path)

        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        summary = parsed["summary"]
        required_fields = [
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

        for field in required_fields:
            assert field in summary, f"Missing field: {field}"
            assert isinstance(summary[field], int), f"Field {field} should be int"

    def test_report_contains_all_detail_fields(self, tmp_path: Path) -> None:
        """Test that saved report contains all EnrichmentDetail fields."""
        report = create_sample_report(num_details=5)
        report_path = tmp_path / "test-report.json"

        save_report_to_file(report, report_path)

        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        # Check that details exist
        assert "details" in parsed
        assert len(parsed["details"]) == 5

        # Each detail should have required fields
        for detail in parsed["details"]:
            assert "video_id" in detail
            assert "status" in detail
            assert detail["status"] in ["updated", "deleted", "error", "skipped"]


class TestDefaultPathGeneration:
    """Tests for default path generation (./exports/enrichment-{timestamp}.json)."""

    def test_default_path_format(self, tmp_path: Path) -> None:
        """Test that default path follows expected format."""
        timestamp = datetime(2024, 6, 15, 14, 30, 45, tzinfo=timezone.utc)
        path = generate_default_report_path(tmp_path, timestamp)

        # Verify path format
        assert path.parent.name == "exports"
        assert "enrichment-20240615-143045.json" == path.name

    def test_default_path_in_exports_directory(self, tmp_path: Path) -> None:
        """Test that default path is in exports directory."""
        path = generate_default_report_path(tmp_path)

        assert "exports" in str(path)
        assert path.parent.name == "exports"

    def test_default_path_includes_timestamp(self, tmp_path: Path) -> None:
        """Test that default path includes timestamp."""
        timestamp = datetime(2024, 12, 25, 8, 0, 0, tzinfo=timezone.utc)
        path = generate_default_report_path(tmp_path, timestamp)

        # Should contain date components
        assert "20241225" in path.name
        assert "080000" in path.name

    def test_default_path_has_json_extension(self, tmp_path: Path) -> None:
        """Test that default path has .json extension."""
        path = generate_default_report_path(tmp_path)

        assert path.suffix == ".json"

    def test_default_path_matches_pattern(self, tmp_path: Path) -> None:
        """Test that default path matches expected regex pattern."""
        path = generate_default_report_path(tmp_path)

        # Pattern: enrichment-YYYYMMDD-HHMMSS.json
        pattern = r"enrichment-\d{8}-\d{6}\.json"
        assert re.match(pattern, path.name), f"Path {path.name} doesn't match pattern"


class TestExportsDirectoryCreation:
    """Tests for exports directory creation if missing."""

    def test_exports_directory_created_if_missing(self, tmp_path: Path) -> None:
        """Test that exports directory is created if it doesn't exist."""
        report = create_sample_report()
        exports_dir = tmp_path / "exports"
        report_path = exports_dir / "test-report.json"

        # Verify directory doesn't exist yet
        assert not exports_dir.exists()

        save_report_to_file(report, report_path)

        # Now directory should exist
        assert exports_dir.exists()
        assert exports_dir.is_dir()

    def test_nested_exports_directory_created(self, tmp_path: Path) -> None:
        """Test that nested directory structure is created."""
        report = create_sample_report()
        report_path = tmp_path / "data" / "exports" / "2024" / "06" / "report.json"

        # None of the directories exist
        assert not (tmp_path / "data").exists()

        save_report_to_file(report, report_path)

        # All directories should now exist
        assert (tmp_path / "data").exists()
        assert (tmp_path / "data" / "exports").exists()
        assert (tmp_path / "data" / "exports" / "2024").exists()
        assert (tmp_path / "data" / "exports" / "2024" / "06").exists()

    def test_existing_exports_directory_not_affected(self, tmp_path: Path) -> None:
        """Test that existing exports directory is not affected."""
        exports_dir = tmp_path / "exports"
        exports_dir.mkdir(parents=True)

        # Create an existing file in the directory
        existing_file = exports_dir / "existing-report.json"
        existing_file.write_text('{"existing": true}')

        report = create_sample_report()
        new_report_path = exports_dir / "new-report.json"

        save_report_to_file(report, new_report_path)

        # Both files should exist
        assert existing_file.exists()
        assert new_report_path.exists()


class TestReportIncludesAllDetails:
    """Tests for report including all enrichment details."""

    def test_report_includes_all_enrichment_details(self, tmp_path: Path) -> None:
        """Test that report includes all enrichment details."""
        report = create_sample_report(num_details=10)
        report_path = tmp_path / "test-report.json"

        save_report_to_file(report, report_path)

        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        assert len(parsed["details"]) == 10

    def test_report_preserves_detail_order(self, tmp_path: Path) -> None:
        """Test that report preserves the order of details."""
        report = create_sample_report(num_details=5)
        report_path = tmp_path / "test-report.json"

        save_report_to_file(report, report_path)

        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        # Verify order matches
        for i, detail in enumerate(parsed["details"]):
            assert detail["video_id"] == f"vid_{i:03d}"

    def test_report_includes_error_details(self, tmp_path: Path) -> None:
        """Test that report includes error details with messages."""
        timestamp = datetime.now(timezone.utc)
        summary = EnrichmentSummary(
            videos_processed=2,
            videos_updated=0,
            videos_deleted=0,
            channels_created=0,
            tags_created=0,
            topic_associations=0,
            categories_assigned=0,
            errors=2,
            quota_used=1,
        )
        details = [
            EnrichmentDetail(
                video_id="error_vid_1",
                status="error",
                error="API quota exceeded",
            ),
            EnrichmentDetail(
                video_id="error_vid_2",
                status="error",
                error="Video not found",
            ),
        ]
        report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
            details=details,
        )

        report_path = tmp_path / "test-report.json"
        save_report_to_file(report, report_path)

        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        # Verify error details
        error_details = parsed["details"]
        assert len(error_details) == 2
        assert error_details[0]["status"] == "error"
        assert error_details[0]["error"] == "API quota exceeded"
        assert error_details[1]["status"] == "error"
        assert error_details[1]["error"] == "Video not found"

    def test_report_includes_empty_details_list(self, tmp_path: Path) -> None:
        """Test that report handles empty details list."""
        report = create_sample_report(num_details=0)
        report_path = tmp_path / "test-report.json"

        save_report_to_file(report, report_path)

        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        assert parsed["details"] == []
        assert parsed["summary"]["videos_processed"] == 0

    def test_report_includes_mixed_status_details(self, tmp_path: Path) -> None:
        """Test that report includes details with all status types."""
        timestamp = datetime.now(timezone.utc)
        summary = EnrichmentSummary(
            videos_processed=4,
            videos_updated=1,
            videos_deleted=1,
            channels_created=0,
            tags_created=5,
            topic_associations=3,
            categories_assigned=1,
            errors=1,
            quota_used=1,
        )
        details = [
            EnrichmentDetail(video_id="vid_1", status="updated", tags_count=5),
            EnrichmentDetail(video_id="vid_2", status="deleted"),
            EnrichmentDetail(video_id="vid_3", status="error", error="Not found"),
            EnrichmentDetail(video_id="vid_4", status="skipped"),
        ]
        report = EnrichmentReport(
            timestamp=timestamp,
            priority="all",
            summary=summary,
            details=details,
        )

        report_path = tmp_path / "test-report.json"
        save_report_to_file(report, report_path)

        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        statuses = [d["status"] for d in parsed["details"]]
        assert "updated" in statuses
        assert "deleted" in statuses
        assert "error" in statuses
        assert "skipped" in statuses


class TestReportTimestamp:
    """Tests for report timestamp handling."""

    def test_report_timestamp_is_iso8601(self, tmp_path: Path) -> None:
        """Test that report timestamp is in ISO 8601 format."""
        report = create_sample_report()
        report_path = tmp_path / "test-report.json"

        save_report_to_file(report, report_path)

        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        # Should be parseable as ISO 8601
        timestamp_str = parsed["timestamp"]
        # Handle Z suffix for UTC
        parsed_ts = timestamp_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(parsed_ts)
        assert isinstance(dt, datetime)

    def test_report_preserves_utc_timezone(self, tmp_path: Path) -> None:
        """Test that report preserves UTC timezone."""
        timestamp = datetime(2024, 6, 15, 12, 30, 45, tzinfo=timezone.utc)
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

        report_path = tmp_path / "test-report.json"
        save_report_to_file(report, report_path)

        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)

        # Timestamp should indicate UTC
        timestamp_str = parsed["timestamp"]
        assert "Z" in timestamp_str or "+00:00" in timestamp_str
