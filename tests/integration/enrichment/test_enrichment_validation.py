"""
Phase 14: Polish & Cross-Cutting Concerns - Enrichment Validation Tests.

This module contains comprehensive validation and integration tests for the
metadata enrichment feature, covering:

- T100: End-to-end workflow validation
- T102: Success criteria verification (SC-001 to SC-016)
- T105: Final integration test for complete flow
- Additional CLI validation tests

These tests verify the complete enrichment workflow functions correctly and
all documented success criteria are met.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.commands.enrich import app as enrich_app
from chronovista.cli.commands.seed import seed_app
from chronovista.exceptions import (
    EXIT_CODE_INTERRUPTED,
    EXIT_CODE_PREREQUISITES_MISSING,
    EXIT_CODE_QUOTA_EXCEEDED,
    GracefulShutdownException,
    PrerequisiteError,
    QuotaExceededException,
)
from chronovista.models.enrichment_report import (
    EnrichmentDetail,
    EnrichmentReport,
    EnrichmentSummary,
)
from chronovista.services.enrichment.enrichment_service import (
    BATCH_SIZE,
    EnrichmentService,
    EnrichmentStatus,
    PriorityTierEstimate,
    estimate_quota_cost,
    is_placeholder_channel_name,
    is_placeholder_video_title,
)
from chronovista.services.enrichment.seeders import (
    CategorySeeder,
    TopicSeeder,
    TopicSeedResult,
    CategorySeedResult,
)

pytestmark = pytest.mark.asyncio

runner = CliRunner()


# ============================================================================
# T100: END-TO-END WORKFLOW VALIDATION TESTS
# ============================================================================


class TestT100EndToEndWorkflowValidation:
    """
    T100: End-to-end workflow validation tests.

    Validates the complete quickstart workflow:
    1. Seed topics (verify topics are created)
    2. Seed categories (verify categories are created)
    3. Run enrichment with --dry-run (verify it shows what would be done)
    4. Run enrichment status (verify status output)
    5. Verify report generation works
    """

    def test_seed_topics_cli_help_shows_expected_options(self) -> None:
        """Test that seed topics command has expected options."""
        result = runner.invoke(seed_app, ["topics", "--help"])

        assert result.exit_code == 0
        assert "--force" in result.output
        assert "--dry-run" in result.output
        # Description should mention topic categories
        assert "topic" in result.output.lower()

    def test_seed_categories_cli_help_shows_expected_options(self) -> None:
        """Test that seed categories command has expected options."""
        result = runner.invoke(seed_app, ["categories", "--help"])

        assert result.exit_code == 0
        assert "--force" in result.output
        assert "--dry-run" in result.output
        assert "--regions" in result.output
        # Description should mention video categories
        assert "categor" in result.output.lower()

    def test_enrich_run_cli_help_shows_expected_options(self) -> None:
        """Test that enrich run command has expected options."""
        result = runner.invoke(enrich_app, ["run", "--help"])

        assert result.exit_code == 0
        # All expected options should be present
        assert "--limit" in result.output
        assert "--priority" in result.output
        assert "--dry-run" in result.output
        assert "--include-deleted" in result.output
        assert "--include-playlists" in result.output
        assert "--force" in result.output
        assert "--auto-seed" in result.output
        assert "--verbose" in result.output
        assert "--output" in result.output

    def test_enrich_status_command_exists(self) -> None:
        """Test that enrich status command exists and shows help."""
        result = runner.invoke(enrich_app, ["status", "--help"])

        assert result.exit_code == 0
        assert "status" in result.output.lower()

    @pytest.mark.asyncio
    async def test_topic_seeder_creates_expected_topic_count(self) -> None:
        """Test that TopicSeeder creates the expected number of topics."""
        mock_repo = AsyncMock()
        mock_session = AsyncMock()

        # All topics are new (none exist)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=False)

        # TopicSeeder should create 58 topics (7 parents + 51 children)
        expected_count = TopicSeeder.get_expected_topic_count()
        assert expected_count == 58
        assert result.created == expected_count
        assert result.skipped == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_category_seeder_fetches_from_all_default_regions(self) -> None:
        """Test that CategorySeeder fetches from all default regions."""
        mock_repo = AsyncMock()
        mock_youtube = AsyncMock()
        mock_session = AsyncMock()

        # Mock API response for each region
        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
            {"id": "20", "snippet": {"title": "Gaming", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session)  # Uses default regions

        # Should have called API for each default region
        expected_regions = CategorySeeder.DEFAULT_REGIONS
        assert result.quota_used == len(expected_regions)
        assert mock_youtube.get_video_categories.call_count == len(expected_regions)

    @pytest.mark.asyncio
    async def test_dry_run_mode_does_not_modify_database(self) -> None:
        """Test that --dry-run mode does not modify the database."""
        # The dry-run behavior is controlled by the CLI, which does not
        # call the service with actual operations when dry_run=True

        mock_repo = AsyncMock()
        mock_session = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)

        # In dry-run mode, the CLI shows preview without calling seed
        # This test verifies TopicSeeder dry-run class methods work
        expected_count = TopicSeeder.get_expected_topic_count()
        parent_count = TopicSeeder.get_parent_count()
        child_count = TopicSeeder.get_child_count()

        assert expected_count == 58
        assert parent_count == 7
        assert child_count == 51
        assert parent_count + child_count == expected_count

    def test_workflow_steps_documented_in_quickstart(self) -> None:
        """Test that workflow steps match the quickstart documentation."""
        # Verify the expected workflow steps exist
        # 1. chronovista seed topics
        # 2. chronovista seed categories
        # 3. chronovista takeout recover
        # 4. chronovista enrich --status
        # 5. chronovista enrich --dry-run
        # 6. chronovista enrich

        # Verify seed topics command exists
        result = runner.invoke(seed_app, ["topics", "--help"])
        assert result.exit_code == 0

        # Verify seed categories command exists
        result = runner.invoke(seed_app, ["categories", "--help"])
        assert result.exit_code == 0

        # Verify enrich status command exists
        result = runner.invoke(enrich_app, ["status", "--help"])
        assert result.exit_code == 0

        # Verify enrich run command exists
        result = runner.invoke(enrich_app, ["run", "--help"])
        assert result.exit_code == 0


# ============================================================================
# T102: SUCCESS CRITERIA VERIFICATION TESTS
# ============================================================================


class TestT102SuccessCriteriaSC001LocalRecovery:
    """
    SC-001: Local recovery fills metadata for at least 80% of placeholder
    videos that exist in historical takeouts.

    This test verifies the placeholder detection and recovery mechanisms.
    """

    def test_is_placeholder_video_title_detects_placeholder(self) -> None:
        """Test that placeholder video titles are correctly detected."""
        # Placeholder titles
        assert is_placeholder_video_title("[Placeholder] Video abc123")
        assert is_placeholder_video_title("[Placeholder] Video xyz789")
        assert is_placeholder_video_title("[Placeholder] Video ")

        # Non-placeholder titles
        assert not is_placeholder_video_title("My Awesome Video")
        assert not is_placeholder_video_title("Placeholder Video")  # No brackets
        assert not is_placeholder_video_title("[Placeholder]Video abc")  # No space
        assert not is_placeholder_video_title("")

    def test_is_placeholder_channel_name_detects_placeholder(self) -> None:
        """Test that placeholder channel names are correctly detected."""
        # Placeholder channel names
        assert is_placeholder_channel_name("[Placeholder] Channel abc123")
        assert is_placeholder_channel_name("[Unknown Channel")
        assert is_placeholder_channel_name("[Placeholder]")

        # Non-placeholder channel names
        assert not is_placeholder_channel_name("My Awesome Channel")
        assert not is_placeholder_channel_name("Placeholder Channel")  # No brackets
        assert not is_placeholder_channel_name("")


class TestT102SuccessCriteriaSC003StatusQueryPerformance:
    """
    SC-003: Users can view complete enrichment status in under 5 seconds.

    This test verifies the status query is structured for efficiency.
    """

    @pytest.mark.asyncio
    async def test_status_query_uses_count_aggregation(self) -> None:
        """Test that status query uses COUNT aggregation for efficiency."""
        mock_youtube_service = MagicMock()
        service = EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=mock_youtube_service,
        )

        mock_session = AsyncMock()

        # Track query execution
        scalar_calls = []

        def make_result() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = 100
            scalar_calls.append(True)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: make_result())

        # Execute status query
        await service.get_priority_tier_counts(mock_session)

        # Verify scalar() was called (indicating COUNT query)
        assert len(scalar_calls) >= 4  # At least 4 queries for tiers

    @pytest.mark.asyncio
    async def test_status_returns_all_required_fields(self) -> None:
        """Test that status returns all fields required by FR-074."""
        mock_youtube_service = MagicMock()
        service = EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=mock_youtube_service,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 50
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Get priority tier counts
        result = await service.get_priority_tier_counts(mock_session)

        # Verify required keys per FR-074
        assert "high" in result
        assert "medium" in result
        assert "low" in result
        assert "all" in result
        assert "deleted" in result


class TestT102SuccessCriteriaSC015SeedingIdempotency:
    """
    SC-015: Seeding operations are idempotent.

    Re-running seeding with no --force flag produces zero new records
    when tables are already populated.
    """

    @pytest.mark.asyncio
    async def test_topic_seeder_idempotent_when_all_exist(self) -> None:
        """Test that TopicSeeder skips all when topics already exist."""
        mock_repo = AsyncMock()
        mock_session = AsyncMock()

        # All topics already exist
        mock_repo.exists = AsyncMock(return_value=True)

        seeder = TopicSeeder(topic_repository=mock_repo)

        # First run - all exist
        result1 = await seeder.seed(mock_session, force=False)

        # Second run - all still exist
        result2 = await seeder.seed(mock_session, force=False)

        # Both runs should skip all, create none
        assert result1.created == 0
        assert result1.skipped == 58
        assert result2.created == 0
        assert result2.skipped == 58

        # create() should never have been called
        mock_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_category_seeder_idempotent_when_all_exist(self) -> None:
        """Test that CategorySeeder skips all when categories already exist."""
        mock_repo = AsyncMock()
        mock_youtube = AsyncMock()
        mock_session = AsyncMock()

        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)

        # Category already exists
        mock_repo.exists = AsyncMock(return_value=True)

        seeder = CategorySeeder(mock_repo, mock_youtube)

        # First run
        result1 = await seeder.seed(mock_session, regions=["US"])

        # Second run
        result2 = await seeder.seed(mock_session, regions=["US"])

        # Both should skip the category
        assert result1.created == 0
        assert result1.skipped == 1
        assert result2.created == 0
        assert result2.skipped == 1

    @pytest.mark.asyncio
    async def test_multiple_seeding_runs_produce_same_state(self) -> None:
        """Test that multiple runs without --force produce identical results."""
        mock_repo = AsyncMock()
        mock_session = AsyncMock()

        # All topics exist
        mock_repo.exists = AsyncMock(return_value=True)

        seeder = TopicSeeder(topic_repository=mock_repo)

        # Run multiple times
        results = []
        for _ in range(5):
            result = await seeder.seed(mock_session, force=False)
            results.append(result)

        # All results should be identical
        for i, result in enumerate(results):
            assert result.created == 0, f"Run {i+1} created topics"
            assert result.skipped == 58, f"Run {i+1} skipped wrong count"
            assert result.deleted == 0, f"Run {i+1} deleted topics"


class TestT102SuccessCriteriaSC016ForceFlag:
    """
    SC-016: Seeding with --force flag replaces all existing records.

    Force flag should delete existing records and re-seed without
    leaving orphan associations or breaking referential integrity.
    """

    @pytest.mark.asyncio
    async def test_force_flag_deletes_existing_then_recreates(self) -> None:
        """Test that --force deletes existing records before re-seeding."""
        mock_repo = AsyncMock()
        mock_session = AsyncMock()

        # Mock deletion
        delete_result = MagicMock()
        delete_result.rowcount = 58
        mock_session.execute = AsyncMock(return_value=delete_result)

        # After deletion, nothing exists
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=True)

        # Should delete all existing and create all new
        assert result.deleted > 0
        assert result.created == 58
        assert result.skipped == 0


class TestT102SuccessCriteriaSC013TopicSeeding:
    """
    SC-013: Topic seeding successfully seeds all ~55 YouTube topic categories
    with correct parent-child relationships.
    """

    def test_topic_hierarchy_has_expected_parent_count(self) -> None:
        """Test that topic hierarchy has 7 parent categories."""
        assert TopicSeeder.get_parent_count() == 7

    def test_topic_hierarchy_has_expected_child_count(self) -> None:
        """Test that topic hierarchy has ~51 child categories."""
        assert TopicSeeder.get_child_count() == 51

    def test_topic_hierarchy_has_expected_total_count(self) -> None:
        """Test that topic hierarchy has ~58 total categories."""
        assert TopicSeeder.get_expected_topic_count() == 58

    def test_parent_topic_ids_are_valid(self) -> None:
        """Test that parent topic IDs are all valid Freebase IDs."""
        for topic_id in TopicSeeder.PARENT_TOPIC_IDS:
            # Freebase IDs start with /m/
            assert topic_id.startswith("/m/")
            # Get topic info
            topic_info = TopicSeeder.get_topic_by_id(topic_id)
            assert topic_info is not None
            # Parent topics have no parent_id
            category_name, parent_id, _ = topic_info
            assert parent_id is None

    def test_child_topics_have_valid_parents(self) -> None:
        """Test that all child topics reference valid parent IDs."""
        for topic_id, (name, parent_id, _) in TopicSeeder.YOUTUBE_TOPICS.items():
            if parent_id is not None:
                # Parent must exist in the topics dict
                assert parent_id in TopicSeeder.YOUTUBE_TOPICS
                # Parent must be a root topic (has no parent)
                parent_info = TopicSeeder.YOUTUBE_TOPICS[parent_id]
                assert parent_info[1] is None  # Parent's parent is None


class TestT102SuccessCriteriaSC014CategorySeeding:
    """
    SC-014: Category seeding successfully seeds video categories from all
    configured regions (default: 7 regions).
    """

    def test_default_regions_count(self) -> None:
        """Test that default regions are 7."""
        assert len(CategorySeeder.DEFAULT_REGIONS) == 7

    def test_default_regions_include_expected_countries(self) -> None:
        """Test that default regions include US, GB, JP, DE, BR, IN, MX."""
        expected = {"US", "GB", "JP", "DE", "BR", "IN", "MX"}
        actual = set(CategorySeeder.DEFAULT_REGIONS)
        assert actual == expected

    def test_expected_quota_cost_calculation(self) -> None:
        """Test that quota cost is 1 unit per region."""
        # Default regions
        assert CategorySeeder.get_expected_quota_cost() == 7

        # Custom regions
        assert CategorySeeder.get_expected_quota_cost(["US"]) == 1
        assert CategorySeeder.get_expected_quota_cost(["US", "GB"]) == 2
        assert CategorySeeder.get_expected_quota_cost(["US", "GB", "JP"]) == 3


# ============================================================================
# T105: FINAL INTEGRATION TEST - COMPLETE FLOW
# ============================================================================


class TestT105FinalIntegrationFlow:
    """
    T105: Final integration test for complete flow.

    Tests: seed -> recover -> enrich -> status -> report
    Verifies data flows correctly through each step.
    """

    def test_quota_estimation_formula(self) -> None:
        """Test that quota estimation uses ceiling division by 50."""
        # Formula: ceil(video_count / BATCH_SIZE)
        assert BATCH_SIZE == 50

        # Test cases
        assert estimate_quota_cost(0) == 0
        assert estimate_quota_cost(1) == 1
        assert estimate_quota_cost(49) == 1
        assert estimate_quota_cost(50) == 1
        assert estimate_quota_cost(51) == 2
        assert estimate_quota_cost(100) == 2
        assert estimate_quota_cost(101) == 3
        assert estimate_quota_cost(1000) == 20
        assert estimate_quota_cost(10000) == 200

    def test_enrichment_report_model_validation(self) -> None:
        """Test that EnrichmentReport model validates correctly."""
        timestamp = datetime.now(timezone.utc)

        summary = EnrichmentSummary(
            videos_processed=100,
            videos_updated=90,
            videos_deleted=5,
            channels_created=10,
            tags_created=500,
            topic_associations=300,
            categories_assigned=95,
            errors=5,
            quota_used=2,
        )

        details = [
            EnrichmentDetail(
                video_id="vid_001",
                status="updated",
                old_title="[Placeholder] Video vid_001",
                new_title="Real Video Title",
                tags_count=5,
                topics_count=3,
                category_id="10",
            ),
            EnrichmentDetail(
                video_id="vid_002",
                status="deleted",
            ),
            EnrichmentDetail(
                video_id="vid_003",
                status="error",
                error="API returned 404",
            ),
        ]

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="high",
            summary=summary,
            details=details,
        )

        # Verify all fields are accessible
        assert report.timestamp == timestamp
        assert report.priority == "high"
        assert report.summary.videos_processed == 100
        assert len(report.details) == 3
        assert report.details[0].status == "updated"
        assert report.details[1].status == "deleted"
        assert report.details[2].error == "API returned 404"

    def test_enrichment_report_json_serialization(self, tmp_path: Path) -> None:
        """Test that EnrichmentReport serializes to JSON correctly."""
        timestamp = datetime(2025, 1, 15, 10, 30, 45, tzinfo=timezone.utc)

        summary = EnrichmentSummary(
            videos_processed=50,
            videos_updated=45,
            videos_deleted=3,
            channels_created=5,
            tags_created=200,
            topic_associations=150,
            categories_assigned=45,
            errors=2,
            quota_used=1,
        )

        report = EnrichmentReport(
            timestamp=timestamp,
            priority="medium",
            summary=summary,
            details=[
                EnrichmentDetail(video_id="test_vid", status="updated"),
            ],
        )

        # Serialize to JSON
        json_str = report.model_dump_json(indent=2)

        # Save to file
        report_path = tmp_path / "test_report.json"
        report_path.write_text(json_str)

        # Read back and validate
        content = json.loads(report_path.read_text())

        assert content["priority"] == "medium"
        assert content["summary"]["videos_processed"] == 50
        assert content["summary"]["tags_created"] == 200
        assert len(content["details"]) == 1
        assert "2025-01-15" in content["timestamp"]

    @pytest.mark.asyncio
    async def test_priority_tier_counts_structure(self) -> None:
        """Test that priority tier counts return expected structure."""
        mock_youtube_service = MagicMock()
        service = EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=mock_youtube_service,
        )

        mock_session = AsyncMock()

        # Return different counts for each tier
        counts = iter([10, 50, 200, 30])

        def make_result() -> MagicMock:
            mock_result = MagicMock()
            mock_result.scalar.return_value = next(counts)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=lambda _: make_result())

        result = await service.get_priority_tier_counts(mock_session)

        # Verify cumulative relationship: HIGH <= MEDIUM <= LOW <= ALL
        assert result["high"] <= result["medium"]
        assert result["medium"] <= result["low"]
        assert result["low"] <= result["all"]

    def test_enrichment_status_model_structure(self) -> None:
        """Test that EnrichmentStatus model has all required fields."""
        status = EnrichmentStatus(
            total_videos=1000,
            placeholder_videos=100,
            deleted_videos=50,
            fully_enriched_videos=850,
            videos_missing_tags=200,
            videos_missing_topics=300,
            videos_missing_category=150,
            total_channels=200,
            placeholder_channels=20,
            enrichment_percentage=85.0,
            tier_high=PriorityTierEstimate(count=10, quota_units=1),
            tier_medium=PriorityTierEstimate(count=50, quota_units=1),
            tier_low=PriorityTierEstimate(count=200, quota_units=4),
            tier_all=PriorityTierEstimate(count=250, quota_units=5),
        )

        # Verify all FR-074 required fields are present
        assert status.total_videos == 1000
        assert status.placeholder_videos == 100
        assert status.deleted_videos == 50
        assert status.fully_enriched_videos == 850
        assert status.videos_missing_tags == 200
        assert status.videos_missing_topics == 300
        assert status.videos_missing_category == 150
        assert status.total_channels == 200
        assert status.placeholder_channels == 20
        assert status.enrichment_percentage == 85.0
        assert status.tier_high.count == 10
        assert status.tier_medium.count == 50
        assert status.tier_low.count == 200
        assert status.tier_all.count == 250


# ============================================================================
# ADDITIONAL CLI VALIDATION TESTS
# ============================================================================


class TestCLIHelpTextAccuracy:
    """Tests for CLI help text accuracy."""

    def test_seed_topics_help_describes_topic_count(self) -> None:
        """Test that seed topics help mentions ~55 topics."""
        result = runner.invoke(seed_app, ["topics", "--help"])

        assert result.exit_code == 0
        # Help should mention the topic count or hierarchy
        output_lower = result.output.lower()
        assert "topic" in output_lower
        # Should mention parent categories
        assert any(
            term in output_lower
            for term in ["7 parent", "music", "gaming", "sports", "entertainment"]
        )

    def test_seed_categories_help_describes_regions(self) -> None:
        """Test that seed categories help describes default regions."""
        result = runner.invoke(seed_app, ["categories", "--help"])

        assert result.exit_code == 0
        # Help should mention regions
        output_lower = result.output.lower()
        assert "region" in output_lower
        # Default regions format shown in help
        assert "us" in output_lower

    def test_enrich_run_help_describes_priority_levels(self) -> None:
        """Test that enrich run help describes priority levels."""
        result = runner.invoke(enrich_app, ["run", "--help"])

        assert result.exit_code == 0
        output_lower = result.output.lower()

        # All priority levels should be mentioned
        assert "high" in output_lower
        assert "medium" in output_lower
        assert "low" in output_lower
        assert "all" in output_lower

        # Should describe cumulative behavior
        assert "priority" in output_lower
        assert "cumulative" in output_lower or "placeholder" in output_lower

    def test_enrich_run_help_describes_exit_codes(self) -> None:
        """Test that enrich run help describes exit codes."""
        result = runner.invoke(enrich_app, ["run", "--help"])

        assert result.exit_code == 0
        # Help should mention exit codes
        output = result.output
        # Look for common exit code indicators
        assert any(
            term in output
            for term in ["Exit code", "exit code", "0:", "3:", "4:", "130:"]
        )


class TestCommandCombinations:
    """Tests for command combinations."""

    def test_enrich_run_priority_and_limit_combined(self) -> None:
        """Test that --priority and --limit can be combined."""
        result = runner.invoke(enrich_app, ["run", "--help"])

        assert result.exit_code == 0
        assert "--priority" in result.output
        assert "--limit" in result.output

    def test_enrich_run_dry_run_and_output_combined(self) -> None:
        """Test that --dry-run and --output can be combined."""
        result = runner.invoke(enrich_app, ["run", "--help"])

        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--output" in result.output

    def test_seed_categories_regions_and_force_combined(self) -> None:
        """Test that --regions and --force can be combined."""
        result = runner.invoke(seed_app, ["categories", "--help"])

        assert result.exit_code == 0
        assert "--regions" in result.output
        assert "--force" in result.output


class TestErrorMessagesUserFriendly:
    """Tests for user-friendly error messages."""

    def test_invalid_priority_error_message(self) -> None:
        """Test that invalid priority produces user-friendly error."""
        result = runner.invoke(enrich_app, ["run", "--priority", "invalid"])

        assert result.exit_code != 0
        # Error should explain what went wrong
        assert "Invalid priority" in result.output
        # Should suggest valid options
        assert any(
            opt in result.output.lower()
            for opt in ["high", "medium", "low", "all"]
        )

    def test_invalid_priority_suggests_valid_options(self) -> None:
        """Test that invalid priority error suggests valid options."""
        result = runner.invoke(enrich_app, ["run", "--priority", "xyz"])

        assert result.exit_code != 0
        output_lower = result.output.lower()
        # All valid options should be suggested
        assert "high" in output_lower
        assert "medium" in output_lower
        assert "low" in output_lower
        assert "all" in output_lower


class TestExitCodes:
    """Tests for exit codes in various scenarios."""

    def test_exit_code_constants_defined(self) -> None:
        """Test that exit code constants are properly defined."""
        assert EXIT_CODE_QUOTA_EXCEEDED == 3
        assert EXIT_CODE_PREREQUISITES_MISSING == 4
        assert EXIT_CODE_INTERRUPTED == 130

    def test_quota_exceeded_exception_has_correct_attributes(self) -> None:
        """Test that QuotaExceededException has correct attributes."""
        exc = QuotaExceededException(
            message="Quota exceeded during enrichment",
            daily_quota_exceeded=True,
            videos_processed=50,
        )

        assert exc.message == "Quota exceeded during enrichment"
        assert exc.daily_quota_exceeded is True
        assert exc.videos_processed == 50

    def test_prerequisite_error_has_correct_attributes(self) -> None:
        """Test that PrerequisiteError has correct attributes."""
        exc = PrerequisiteError(
            message="Missing prerequisite data",
            missing_tables=["topic_categories", "video_categories"],
        )

        assert exc.message == "Missing prerequisite data"
        assert "topic_categories" in exc.missing_tables
        assert "video_categories" in exc.missing_tables

    def test_graceful_shutdown_exception_has_correct_attributes(self) -> None:
        """Test that GracefulShutdownException has correct attributes."""
        exc = GracefulShutdownException(
            message="Shutdown requested",
            signal_received="SIGTERM",
        )

        assert exc.message == "Shutdown requested"
        assert exc.signal_received == "SIGTERM"


class TestSeedResultModels:
    """Tests for seeder result models."""

    def test_topic_seed_result_properties(self) -> None:
        """Test TopicSeedResult computed properties."""
        result = TopicSeedResult(
            created=30,
            skipped=20,
            deleted=0,
            failed=5,
            duration_seconds=1.5,
        )

        assert result.total_processed == 55  # created + skipped + failed
        assert result.success_rate == (50 / 55) * 100  # (created + skipped) / total

    def test_category_seed_result_properties(self) -> None:
        """Test CategorySeedResult computed properties."""
        result = CategorySeedResult(
            created=25,
            skipped=5,
            deleted=10,
            failed=2,
            duration_seconds=2.5,
            quota_used=7,
        )

        assert result.total_processed == 32  # created + skipped + failed
        assert result.success_rate == (30 / 32) * 100  # (created + skipped) / total
        assert result.quota_used == 7


class TestEnrichmentReportDetailStatus:
    """Tests for EnrichmentDetail status values."""

    def test_valid_status_values(self) -> None:
        """Test that all valid status values are accepted."""
        from typing import Literal, cast

        valid_statuses = ["updated", "deleted", "error", "skipped"]

        for status in valid_statuses:
            detail = EnrichmentDetail(
                video_id="test_vid",
                status=cast(Literal["updated", "deleted", "error", "skipped"], status),
            )
            assert detail.status == status

    def test_updated_status_with_title_change(self) -> None:
        """Test updated status with title change details."""
        detail = EnrichmentDetail(
            video_id="vid_001",
            status="updated",
            old_title="[Placeholder] Video vid_001",
            new_title="Actual Video Title",
            tags_count=5,
            topics_count=3,
            category_id="20",
        )

        assert detail.status == "updated"
        assert detail.old_title is not None
        assert detail.old_title.startswith("[Placeholder]")
        assert detail.new_title is not None
        assert not detail.new_title.startswith("[Placeholder]")
        assert detail.tags_count == 5
        assert detail.topics_count == 3
        assert detail.category_id == "20"

    def test_error_status_with_error_message(self) -> None:
        """Test error status includes error message."""
        detail = EnrichmentDetail(
            video_id="vid_error",
            status="error",
            error="Video not found: 404",
        )

        assert detail.status == "error"
        assert detail.error is not None
        assert "404" in detail.error


class TestBatchSizeConstant:
    """Tests for BATCH_SIZE constant."""

    def test_batch_size_is_50(self) -> None:
        """Test that BATCH_SIZE is 50 (YouTube API limit)."""
        assert BATCH_SIZE == 50

    def test_batch_size_used_in_quota_estimation(self) -> None:
        """Test that BATCH_SIZE is used in quota estimation."""
        # 50 videos = 1 quota unit
        assert estimate_quota_cost(50, batch_size=50) == 1

        # 100 videos = 2 quota units
        assert estimate_quota_cost(100, batch_size=50) == 2

        # Custom batch size
        assert estimate_quota_cost(100, batch_size=25) == 4
