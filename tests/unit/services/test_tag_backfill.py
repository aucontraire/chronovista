"""
Tests for Tag Backfill Service.

Comprehensive unit tests for the ``TagBackfillService`` orchestrator that
manages the tag normalization backfill pipeline.  All database operations
are mocked — these are unit tests, not integration tests.

References
----------
- T009: Unit test task for tag backfill service
- TagBackfillService implementation in src/chronovista/services/tag_backfill.py
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from chronovista.services.tag_backfill import (
    KNOWN_FALSE_MERGE_PATTERNS,
    TagBackfillService,
)
from chronovista.services.tag_normalization import TagNormalizationService


@pytest.fixture
def normalization_service() -> TagNormalizationService:
    """Use the REAL normalization service (it's pure, no I/O)."""
    return TagNormalizationService()


@pytest.fixture
def service(normalization_service: TagNormalizationService) -> TagBackfillService:
    """Provide a fresh ``TagBackfillService`` instance."""
    return TagBackfillService(normalization_service)


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide a mock async database session."""
    return AsyncMock()


# =========================================================================
# TestNormalizeAndGroupCore — core normalization and grouping
# =========================================================================


class TestNormalizeAndGroupCore:
    """Tests for ``_normalize_and_group_core`` method."""

    @pytest.mark.asyncio
    async def test_groups_by_normalized_form(
        self, service: TagBackfillService
    ) -> None:
        """Pass multiple raw forms that normalize to the same form — verify single group."""
        distinct_tags = {"Python": 10, "python": 5, "#Python": 3}
        groups, skip_list = service._normalize_and_group_core(distinct_tags)

        # All three should normalize to "python"
        assert "python" in groups
        assert len(groups) == 1
        assert len(groups["python"]) == 3

        # Verify the raw forms and counts are preserved
        raw_forms = {form for form, count in groups["python"]}
        assert raw_forms == {"Python", "python", "#Python"}

        # Verify counts
        counts_by_form = {form: count for form, count in groups["python"]}
        assert counts_by_form["Python"] == 10
        assert counts_by_form["python"] == 5
        assert counts_by_form["#Python"] == 3

        # No skips
        assert len(skip_list) == 0

    @pytest.mark.asyncio
    async def test_skips_empty_normalizing_tags(
        self, service: TagBackfillService
    ) -> None:
        """Pass tags that normalize to empty (None) — verify skip_list."""
        distinct_tags = {"#": 3, "": 0, "  ": 5}
        groups, skip_list = service._normalize_and_group_core(distinct_tags)

        # No groups should be created
        assert len(groups) == 0

        # All should be skipped
        assert len(skip_list) == 3
        skipped_forms = {form for form, count in skip_list}
        assert skipped_forms == {"#", "", "  "}

        # Verify counts
        counts_by_form = {form: count for form, count in skip_list}
        assert counts_by_form["#"] == 3
        assert counts_by_form[""] == 0
        assert counts_by_form["  "] == 5

    @pytest.mark.asyncio
    async def test_mixed_tags(self, service: TagBackfillService) -> None:
        """Mix of normalizable and non-normalizable tags — verify partition."""
        distinct_tags = {
            "Python": 10,
            "python": 5,
            "#": 3,
            "Java": 8,
            "": 0,
        }
        groups, skip_list = service._normalize_and_group_core(distinct_tags)

        # Two groups: "python" and "java"
        assert len(groups) == 2
        assert "python" in groups
        assert "java" in groups

        # Python group has 2 aliases
        assert len(groups["python"]) == 2
        python_forms = {form for form, count in groups["python"]}
        assert python_forms == {"Python", "python"}

        # Java group has 1 alias
        assert len(groups["java"]) == 1
        assert groups["java"][0] == ("Java", 8)

        # Two skipped
        assert len(skip_list) == 2
        skipped_forms = {form for form, count in skip_list}
        assert skipped_forms == {"#", ""}

    @pytest.mark.asyncio
    async def test_empty_input(self, service: TagBackfillService) -> None:
        """Empty dict returns empty groups and empty skip_list."""
        distinct_tags: dict[str, int] = {}
        groups, skip_list = service._normalize_and_group_core(distinct_tags)

        assert len(groups) == 0
        assert len(skip_list) == 0

    @pytest.mark.asyncio
    async def test_diacritic_grouping(self, service: TagBackfillService) -> None:
        """Tags with Tier 1 diacritics normalize to same form."""
        distinct_tags = {"café": 80, "cafe": 45, "CAFE": 20}
        groups, skip_list = service._normalize_and_group_core(distinct_tags)

        # All normalize to "cafe" (Tier 1 acute accent stripped)
        assert len(groups) == 1
        assert "cafe" in groups
        assert len(groups["cafe"]) == 3

        # Verify all raw forms are present
        raw_forms = {form for form, count in groups["cafe"]}
        assert raw_forms == {"café", "cafe", "CAFE"}

        # Verify counts
        counts_by_form = {form: count for form, count in groups["cafe"]}
        assert counts_by_form["café"] == 80
        assert counts_by_form["cafe"] == 45
        assert counts_by_form["CAFE"] == 20

        # No skips
        assert len(skip_list) == 0


# =========================================================================
# TestNormalizeAndGroup — full method with UUID generation
# =========================================================================


class TestNormalizeAndGroup:
    """Tests for ``_normalize_and_group`` method (with UUID generation)."""

    @pytest.mark.asyncio
    async def test_generates_uuid7_ids(self, service: TagBackfillService) -> None:
        """Verify all IDs in batch records are valid UUIDs."""
        distinct_tags = {"Python": 10, "Java": 5}
        execution_timestamp = datetime.now(UTC)

        ct_records, ta_records, skip_list = service._normalize_and_group(
            distinct_tags, execution_timestamp
        )

        # Verify canonical tag IDs are UUIDs
        for record in ct_records:
            assert isinstance(record["id"], uuid.UUID)

        # Verify tag alias IDs are UUIDs
        for record in ta_records:
            assert isinstance(record["id"], uuid.UUID)
            assert isinstance(record["canonical_tag_id"], uuid.UUID)

    @pytest.mark.asyncio
    async def test_canonical_form_selection(self, service: TagBackfillService) -> None:
        """Verify select_canonical_form is called with correct aliases list."""
        distinct_tags = {"Python": 100, "python": 50, "PYTHON": 25}
        execution_timestamp = datetime.now(UTC)

        ct_records, ta_records, skip_list = service._normalize_and_group(
            distinct_tags, execution_timestamp
        )

        # Should be 1 canonical tag
        assert len(ct_records) == 1

        # Canonical form should be "Python" (title case with highest count)
        assert ct_records[0]["canonical_form"] == "Python"
        assert ct_records[0]["normalized_form"] == "python"

    @pytest.mark.asyncio
    async def test_batch_record_fields(self, service: TagBackfillService) -> None:
        """Verify canonical_tags records have correct keys and types."""
        distinct_tags = {"Python": 10}
        execution_timestamp = datetime.now(UTC)

        ct_records, ta_records, skip_list = service._normalize_and_group(
            distinct_tags, execution_timestamp
        )

        assert len(ct_records) == 1
        record = ct_records[0]

        # Verify all required keys are present
        assert set(record.keys()) == {
            "id",
            "canonical_form",
            "normalized_form",
            "alias_count",
            "video_count",
            "status",
        }

        # Verify types
        assert isinstance(record["id"], uuid.UUID)
        assert isinstance(record["canonical_form"], str)
        assert isinstance(record["normalized_form"], str)
        assert isinstance(record["alias_count"], int)
        assert isinstance(record["video_count"], int)
        assert isinstance(record["status"], str)

        # Verify values
        assert record["canonical_form"] == "Python"
        assert record["normalized_form"] == "python"
        assert record["alias_count"] == 1
        assert record["video_count"] == 0
        assert record["status"] == "active"

    @pytest.mark.asyncio
    async def test_alias_record_fields(self, service: TagBackfillService) -> None:
        """Verify tag_aliases records have correct keys and types."""
        distinct_tags = {"Python": 10}
        execution_timestamp = datetime.now(UTC)

        ct_records, ta_records, skip_list = service._normalize_and_group(
            distinct_tags, execution_timestamp
        )

        assert len(ta_records) == 1
        record = ta_records[0]

        # Verify all required keys are present
        assert set(record.keys()) == {
            "id",
            "raw_form",
            "normalized_form",
            "canonical_tag_id",
            "creation_method",
            "normalization_version",
            "occurrence_count",
            "first_seen_at",
            "last_seen_at",
        }

        # Verify types
        assert isinstance(record["id"], uuid.UUID)
        assert isinstance(record["raw_form"], str)
        assert isinstance(record["normalized_form"], str)
        assert isinstance(record["canonical_tag_id"], uuid.UUID)
        assert isinstance(record["creation_method"], str)
        assert isinstance(record["normalization_version"], int)
        assert isinstance(record["occurrence_count"], int)
        assert isinstance(record["first_seen_at"], datetime)
        assert isinstance(record["last_seen_at"], datetime)

        # Verify values
        assert record["raw_form"] == "Python"
        assert record["normalized_form"] == "python"
        assert record["creation_method"] == "backfill"
        assert record["normalization_version"] == 1
        assert record["occurrence_count"] == 10

    @pytest.mark.asyncio
    async def test_execution_timestamp_used(self, service: TagBackfillService) -> None:
        """Verify first_seen_at and last_seen_at both match execution_timestamp."""
        distinct_tags = {"Python": 10}
        execution_timestamp = datetime(2023, 5, 15, 10, 30, 45, tzinfo=UTC)

        ct_records, ta_records, skip_list = service._normalize_and_group(
            distinct_tags, execution_timestamp
        )

        assert len(ta_records) == 1
        record = ta_records[0]

        assert record["first_seen_at"] == execution_timestamp
        assert record["last_seen_at"] == execution_timestamp

    @pytest.mark.asyncio
    async def test_alias_count_matches_group_size(
        self, service: TagBackfillService
    ) -> None:
        """Verify alias_count on canonical tag equals number of aliases."""
        distinct_tags = {"Python": 100, "python": 50, "PYTHON": 25}
        execution_timestamp = datetime.now(UTC)

        ct_records, ta_records, skip_list = service._normalize_and_group(
            distinct_tags, execution_timestamp
        )

        # Should be 1 canonical tag with 3 aliases
        assert len(ct_records) == 1
        assert ct_records[0]["alias_count"] == 3

        # Should be 3 tag aliases
        assert len(ta_records) == 3

    @pytest.mark.asyncio
    async def test_varchar_500_boundary_casefold(
        self, service: TagBackfillService
    ) -> None:
        """Test a tag at VARCHAR(500) boundary where casefold expansion increases length."""
        # Create a string at the boundary with German ß (expands to ss)
        # 499 chars + ß (1 char) = 500 chars, but casefold → 501 chars
        base_str = "a" * 499
        tag_with_eszett = base_str + "ß"  # 500 chars

        distinct_tags = {tag_with_eszett: 1}
        execution_timestamp = datetime.now(UTC)

        # This should NOT raise an exception in the service
        # (the DB will enforce the length constraint)
        ct_records, ta_records, skip_list = service._normalize_and_group(
            distinct_tags, execution_timestamp
        )

        # Verify the normalization happened
        assert len(ta_records) == 1
        assert ta_records[0]["raw_form"] == tag_with_eszett

        # The normalized form will be 501 chars (499 a's + ss)
        normalized = ta_records[0]["normalized_form"]
        assert normalized == base_str + "ss"
        assert len(normalized) == 501


# =========================================================================
# TestBatchSizeValidation — batch_size validation in run_backfill
# =========================================================================


class TestBatchSizeValidation:
    """Tests for batch_size validation in ``run_backfill``."""

    @pytest.mark.asyncio
    async def test_batch_size_zero_raises_system_exit_2(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """batch_size=0 raises SystemExit with code 2."""
        with pytest.raises(SystemExit) as exc_info:
            await service.run_backfill(mock_session, batch_size=0)
        assert exc_info.value.code == 2

    @pytest.mark.asyncio
    async def test_batch_size_negative_raises_system_exit_2(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """batch_size=-1 raises SystemExit with code 2."""
        with pytest.raises(SystemExit) as exc_info:
            await service.run_backfill(mock_session, batch_size=-1)
        assert exc_info.value.code == 2

    @pytest.mark.asyncio
    async def test_batch_size_one_succeeds(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """batch_size=1 does NOT raise (mock the rest of the pipeline)."""
        # Mock table existence check
        mock_conn = AsyncMock()
        mock_session.connection.return_value = mock_conn
        mock_conn.run_sync.return_value = []  # no missing tables

        # Mock repository get_distinct_tags_with_counts
        with patch(
            "chronovista.services.tag_backfill.VideoTagRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_distinct_tags_with_counts.return_value = []

            # Mock session.execute for batch inserts
            mock_result = MagicMock()
            mock_result.rowcount = 0
            mock_session.execute.return_value = mock_result

            # Should NOT raise
            await service.run_backfill(mock_session, batch_size=1)


# =========================================================================
# TestCheckTablesExist — table existence validation
# =========================================================================


class TestCheckTablesExist:
    """Tests for ``_check_tables_exist`` method."""

    @pytest.mark.asyncio
    async def test_both_tables_present_succeeds(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """No exception when both tables exist."""
        mock_conn = AsyncMock()
        mock_session.connection.return_value = mock_conn
        mock_conn.run_sync.return_value = []  # no missing tables

        # Should not raise
        await service._check_tables_exist(mock_session)

    @pytest.mark.asyncio
    async def test_missing_canonical_tags_raises(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """SystemExit when canonical_tags missing."""
        mock_conn = AsyncMock()
        mock_session.connection.return_value = mock_conn
        mock_conn.run_sync.return_value = ["canonical_tags"]

        with pytest.raises(SystemExit) as exc_info:
            await service._check_tables_exist(mock_session)

        # Verify error message
        assert "canonical_tags" in str(exc_info.value)
        assert "alembic upgrade head" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_tag_aliases_raises(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """SystemExit when tag_aliases missing."""
        mock_conn = AsyncMock()
        mock_session.connection.return_value = mock_conn
        mock_conn.run_sync.return_value = ["tag_aliases"]

        with pytest.raises(SystemExit) as exc_info:
            await service._check_tables_exist(mock_session)

        # Verify error message
        assert "tag_aliases" in str(exc_info.value)
        assert "alembic upgrade head" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_both_missing_raises(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """SystemExit when both missing, message includes both names."""
        mock_conn = AsyncMock()
        mock_session.connection.return_value = mock_conn
        mock_conn.run_sync.return_value = ["canonical_tags", "tag_aliases"]

        with pytest.raises(SystemExit) as exc_info:
            await service._check_tables_exist(mock_session)

        # Verify both table names are in the error message
        error_msg = str(exc_info.value)
        assert "canonical_tags" in error_msg
        assert "tag_aliases" in error_msg
        assert "alembic upgrade head" in error_msg


# =========================================================================
# TestKnownFalseMergePatterns — verify constant
# =========================================================================


class TestKnownFalseMergePatterns:
    """Tests for KNOWN_FALSE_MERGE_PATTERNS constant."""

    def test_has_exactly_five_entries(self) -> None:
        """Verify KNOWN_FALSE_MERGE_PATTERNS has exactly 5 entries."""
        assert len(KNOWN_FALSE_MERGE_PATTERNS) == 5

    def test_contains_expected_patterns(self) -> None:
        """Verify the expected false-merge patterns are present."""
        expected = {"cafe", "resume", "cliche", "naive", "rape"}
        assert KNOWN_FALSE_MERGE_PATTERNS == expected

    def test_is_frozenset(self) -> None:
        """Verify KNOWN_FALSE_MERGE_PATTERNS is immutable (frozenset)."""
        assert isinstance(KNOWN_FALSE_MERGE_PATTERNS, frozenset)


# =========================================================================
# TestDetectCollisions — collision detection (T012)
# =========================================================================


class TestDetectCollisions:
    """Tests for ``_detect_collisions`` method."""

    def test_cafe_collision(self, service: TagBackfillService) -> None:
        """Diacritic collision: cafe/cafe → detected, is_known_false_merge=True."""
        groups = {"cafe": [("cafe", 89), ("cafe", 45)]}
        # Actually use distinct diacritic forms
        groups = {"cafe": [("cafe\u0301", 89), ("cafe", 45)]}
        result = service._detect_collisions(groups)

        assert len(result) == 1
        assert result[0]["normalized_form"] == "cafe"
        assert result[0]["is_known_false_merge"] is True
        assert len(result[0]["aliases"]) == 2

    def test_case_hashtag_not_collision(self, service: TagBackfillService) -> None:
        """Case and hashtag variations are NOT collisions (casefold collapses them)."""
        groups = {
            "mexico": [
                ("Mexico", 50),
                ("MEXICO", 30),
                ("#mexico", 10),
            ]
        }
        result = service._detect_collisions(groups)

        # After strip #, strip whitespace, casefold: all become "mexico"
        assert len(result) == 0

    def test_empty_groups(self, service: TagBackfillService) -> None:
        """Empty groups dict returns empty collision list."""
        result = service._detect_collisions({})
        assert result == []

    def test_single_alias_no_collision(self, service: TagBackfillService) -> None:
        """Groups with only 1 alias cannot be collisions."""
        groups = {
            "python": [("Python", 100)],
            "java": [("Java", 80)],
        }
        result = service._detect_collisions(groups)
        assert result == []

    def test_known_false_merge_flag(self, service: TagBackfillService) -> None:
        """Verify each of the 5 known patterns gets flagged."""
        groups = {
            "cafe": [("cafe", 10), ("\u0063\u0061\u0066\u00e9", 5)],  # cafe vs cafe
            "resume": [("resume", 10), ("r\u00e9sum\u00e9", 5)],  # resume vs resume
            "cliche": [("cliche", 10), ("clich\u00e9", 5)],  # cliche vs cliche
            "naive": [("naive", 10), ("na\u00efve", 5)],  # naive vs naive
            "rape": [("rape", 10), ("Rap\u00e9", 5)],  # rape vs Rapé
        }
        result = service._detect_collisions(groups)

        # All 5 should be detected and flagged as known false-merges
        assert len(result) == 5
        for collision in result:
            assert collision["is_known_false_merge"] is True

    def test_sort_by_occurrence_descending(self, service: TagBackfillService) -> None:
        """Multiple collisions sorted by total occurrence count descending."""
        groups = {
            "cafe": [("cafe", 10), ("caf\u00e9", 5)],  # total 15
            "resume": [("resume", 100), ("r\u00e9sum\u00e9", 50)],  # total 150
            "naive": [("naive", 30), ("na\u00efve", 20)],  # total 50
        }
        result = service._detect_collisions(groups)

        assert len(result) == 3
        # Should be sorted: resume (150) > naive (50) > cafe (15)
        assert result[0]["normalized_form"] == "resume"
        assert result[1]["normalized_form"] == "naive"
        assert result[2]["normalized_form"] == "cafe"


# =========================================================================
# TestRunAnalysis — analysis output (T013)
# =========================================================================


class TestRunAnalysis:
    """Tests for ``run_analysis`` method."""

    @pytest.mark.asyncio
    async def test_json_output_schema(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """Verify JSON output has all required keys."""
        # Mock table existence check
        mock_conn = AsyncMock()
        mock_session.connection.return_value = mock_conn
        mock_conn.run_sync.return_value = []  # no missing tables

        # Mock repository
        with patch(
            "chronovista.services.tag_backfill.VideoTagRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_distinct_tags_with_counts.return_value = [
                ("Python", 100),
                ("python", 50),
                ("#Python", 25),
                ("Java", 80),
                ("#", 3),
            ]

            mock_console = MagicMock()
            result = await service.run_analysis(
                mock_session, output_format="json", console=mock_console
            )

        # Verify result is a dict with correct keys
        assert result is not None
        assert isinstance(result, dict)
        required_keys = {
            "total_distinct_tags",
            "estimated_canonical_tags",
            "skip_count",
            "top_canonical_tags",
            "collision_candidates",
            "skipped_tags",
        }
        assert set(result.keys()) == required_keys

        # Verify types
        assert isinstance(result["total_distinct_tags"], int)
        assert isinstance(result["estimated_canonical_tags"], int)
        assert isinstance(result["skip_count"], int)
        assert isinstance(result["top_canonical_tags"], list)
        assert isinstance(result["collision_candidates"], list)
        assert isinstance(result["skipped_tags"], list)

        # Verify values
        assert result["total_distinct_tags"] == 5
        assert result["estimated_canonical_tags"] == 2  # python, java
        assert result["skip_count"] == 1  # "#"

        # Verify top canonical tags schema
        for entry in result["top_canonical_tags"]:
            assert "canonical_form" in entry
            assert "normalized_form" in entry
            assert "alias_count" in entry
            assert "aliases" in entry

        # Verify skipped tags schema
        assert len(result["skipped_tags"]) == 1
        assert result["skipped_tags"][0]["raw_form"] == "#"
        assert result["skipped_tags"][0]["occurrence_count"] == 3

    @pytest.mark.asyncio
    async def test_top_20_with_fewer_groups(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """When <20 groups exist, return all of them."""
        mock_conn = AsyncMock()
        mock_session.connection.return_value = mock_conn
        mock_conn.run_sync.return_value = []

        with patch(
            "chronovista.services.tag_backfill.VideoTagRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            # Only 3 distinct tags → 3 groups
            mock_repo.get_distinct_tags_with_counts.return_value = [
                ("Python", 100),
                ("Java", 80),
                ("Go", 60),
            ]

            mock_console = MagicMock()
            result = await service.run_analysis(
                mock_session, output_format="json", console=mock_console
            )

        assert result is not None
        assert len(result["top_canonical_tags"]) == 3

    @pytest.mark.asyncio
    async def test_deterministic_output(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """Run twice with same data, verify identical results."""
        mock_conn = AsyncMock()
        mock_session.connection.return_value = mock_conn
        mock_conn.run_sync.return_value = []

        tag_data = [
            ("Python", 100),
            ("python", 50),
            ("Java", 80),
            ("java", 40),
            ("Go", 60),
        ]

        results = []
        for _ in range(2):
            with patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_class:
                mock_repo = AsyncMock()
                mock_repo_class.return_value = mock_repo
                mock_repo.get_distinct_tags_with_counts.return_value = tag_data

                mock_console = MagicMock()
                result = await service.run_analysis(
                    mock_session, output_format="json", console=mock_console
                )
                results.append(result)

        # Both runs should produce identical results
        assert results[0] == results[1]

    @pytest.mark.asyncio
    async def test_table_format_output(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """Verify table format renders output and returns None."""
        import io
        from rich.console import Console

        # Mock table existence check
        mock_conn = AsyncMock()
        mock_session.connection.return_value = mock_conn
        mock_conn.run_sync.return_value = []  # no missing tables

        # Mock repository with test data
        with patch(
            "chronovista.services.tag_backfill.VideoTagRepository"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            # Include collision candidate and skip list items
            mock_repo.get_distinct_tags_with_counts.return_value = [
                ("Python", 100),
                ("python", 50),
                ("#Python", 25),
                ("Java", 80),
                ("café", 80),
                ("cafe", 45),
                ("CAFE", 20),
                ("#", 3),
            ]

            # Capture console output
            output = io.StringIO()
            test_console = Console(file=output, width=120)
            result = await service.run_analysis(
                mock_session, output_format="table", console=test_console
            )

        # Verify table format returns None (unlike JSON which returns dict)
        assert result is None

        # Verify output contains expected sections
        printed = output.getvalue()

        # Check for summary section
        assert "Analysis Summary" in printed or "distinct" in printed.lower()

        # Check for top canonical tags section
        assert "Top 20" in printed or "Canonical Tags" in printed

        # Check for collision candidates section (should have cafe/café collision)
        assert "Collision Candidates" in printed or "collision" in printed.lower()

        # Check for expected tag names in output
        assert "Python" in printed or "python" in printed
        assert "Java" in printed or "java" in printed

        # Check that skipped tags section is present (for "#")
        assert "Skipped" in printed or "skipped" in printed.lower()


# =========================================================================
# TestRunRecount — recount utility (T017)
# =========================================================================


class TestRunRecount:
    """Tests for ``run_recount`` method."""

    def _mock_tables_exist(self, mock_session: AsyncMock) -> None:
        """Set up mock so _check_tables_exist succeeds."""
        mock_conn = AsyncMock()
        mock_session.connection.return_value = mock_conn
        mock_conn.run_sync.return_value = []  # no missing tables

    @pytest.mark.asyncio
    async def test_recount_with_correct_counts(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """When counts are already correct, no updates needed."""
        self._mock_tables_exist(mock_session)

        ct_id_1 = uuid.uuid4()
        ct_id_2 = uuid.uuid4()

        # Mock alias count query results
        alias_row_1 = MagicMock()
        alias_row_1.canonical_tag_id = ct_id_1
        alias_row_1.new_alias_count = 3

        alias_row_2 = MagicMock()
        alias_row_2.canonical_tag_id = ct_id_2
        alias_row_2.new_alias_count = 2

        # Mock video count query results
        video_row_1 = MagicMock()
        video_row_1.canonical_tag_id = ct_id_1
        video_row_1.new_video_count = 10

        video_row_2 = MagicMock()
        video_row_2.canonical_tag_id = ct_id_2
        video_row_2.new_video_count = 5

        # Current counts match new counts exactly
        current_row_1 = MagicMock()
        current_row_1.id = ct_id_1
        current_row_1.alias_count = 3
        current_row_1.video_count = 10

        current_row_2 = MagicMock()
        current_row_2.id = ct_id_2
        current_row_2.alias_count = 2
        current_row_2.video_count = 5

        alias_result = MagicMock()
        alias_result.all.return_value = [alias_row_1, alias_row_2]

        video_result = MagicMock()
        video_result.all.return_value = [video_row_1, video_row_2]

        current_result = MagicMock()
        current_result.all.return_value = [current_row_1, current_row_2]

        # UPDATE statements still execute even if no rows change
        update_result = MagicMock()
        update_result.rowcount = 0

        mock_session.execute = AsyncMock(
            side_effect=[
                alias_result,
                video_result,
                current_result,
                update_result,  # alias_count UPDATE
                update_result,  # video_count UPDATE
            ]
        )

        mock_console = MagicMock()
        await service.run_recount(mock_session, dry_run=False, console=mock_console)

        # With no deltas, "Total updated: 0" should be printed
        print_calls = [str(c) for c in mock_console.print.call_args_list]
        output = " ".join(print_calls)
        assert "Total updated: 0" in output

        # commit is always called in non-dry-run mode
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_recount_with_stale_counts(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """When counts are stale, deltas are detected and updates written."""
        self._mock_tables_exist(mock_session)

        ct_id_1 = uuid.uuid4()

        # New alias count = 5, but current = 3 (stale)
        alias_row = MagicMock()
        alias_row.canonical_tag_id = ct_id_1
        alias_row.new_alias_count = 5

        # New video count = 15, but current = 10 (stale)
        video_row = MagicMock()
        video_row.canonical_tag_id = ct_id_1
        video_row.new_video_count = 15

        current_row = MagicMock()
        current_row.id = ct_id_1
        current_row.alias_count = 3
        current_row.video_count = 10

        alias_result = MagicMock()
        alias_result.all.return_value = [alias_row]

        video_result = MagicMock()
        video_result.all.return_value = [video_row]

        current_result = MagicMock()
        current_result.all.return_value = [current_row]

        # UPDATE alias_count, UPDATE video_count each return a result
        update_result = MagicMock()
        update_result.rowcount = 1

        mock_session.execute = AsyncMock(
            side_effect=[
                alias_result,
                video_result,
                current_result,
                update_result,  # alias_count UPDATE
                update_result,  # video_count UPDATE
            ]
        )

        mock_console = MagicMock()
        await service.run_recount(mock_session, dry_run=False, console=mock_console)

        # Should report 1 updated
        print_calls = [str(c) for c in mock_console.print.call_args_list]
        output = " ".join(print_calls)
        assert "Total updated: 1" in output

        # commit should have been called
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_dry_run_shows_deltas(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """dry_run=True shows delta table without writing to database."""
        self._mock_tables_exist(mock_session)

        ct_id_1 = uuid.uuid4()

        # Stale alias count
        alias_row = MagicMock()
        alias_row.canonical_tag_id = ct_id_1
        alias_row.new_alias_count = 7

        video_row = MagicMock()
        video_row.canonical_tag_id = ct_id_1
        video_row.new_video_count = 20

        current_row = MagicMock()
        current_row.id = ct_id_1
        current_row.alias_count = 3
        current_row.video_count = 10

        alias_result = MagicMock()
        alias_result.all.return_value = [alias_row]

        video_result = MagicMock()
        video_result.all.return_value = [video_row]

        current_result = MagicMock()
        current_result.all.return_value = [current_row]

        mock_session.execute = AsyncMock(
            side_effect=[alias_result, video_result, current_result]
        )

        mock_console = MagicMock()
        await service.run_recount(mock_session, dry_run=True, console=mock_console)

        # Should NOT have called commit (dry run)
        mock_session.commit.assert_not_called()

        # Should have printed the delta table and total
        print_calls = [str(c) for c in mock_console.print.call_args_list]
        output = " ".join(print_calls)
        assert "Total with deltas: 1" in output

        # Only 3 execute calls (read queries), no UPDATE executes
        assert mock_session.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_canonical_tags(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """Empty canonical_tags table returns 0 updated with no error."""
        self._mock_tables_exist(mock_session)

        # All queries return empty results
        empty_result = MagicMock()
        empty_result.all.return_value = []

        # UPDATE statements also return a result
        update_result = MagicMock()
        update_result.rowcount = 0

        mock_session.execute = AsyncMock(
            side_effect=[
                empty_result,   # alias count query
                empty_result,   # video count query
                empty_result,   # current counts query
                update_result,  # alias_count UPDATE
                update_result,  # video_count UPDATE
            ]
        )

        mock_console = MagicMock()
        await service.run_recount(mock_session, dry_run=False, console=mock_console)

        # Should report 0 updated
        print_calls = [str(c) for c in mock_console.print.call_args_list]
        output = " ".join(print_calls)
        assert "Total updated: 0" in output

    @pytest.mark.asyncio
    async def test_dry_run_correct_counts_message(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """dry_run=True with correct counts prints 'All counts are correct.'."""
        self._mock_tables_exist(mock_session)

        ct_id_1 = uuid.uuid4()

        alias_row = MagicMock()
        alias_row.canonical_tag_id = ct_id_1
        alias_row.new_alias_count = 3

        video_row = MagicMock()
        video_row.canonical_tag_id = ct_id_1
        video_row.new_video_count = 10

        current_row = MagicMock()
        current_row.id = ct_id_1
        current_row.alias_count = 3
        current_row.video_count = 10

        alias_result = MagicMock()
        alias_result.all.return_value = [alias_row]

        video_result = MagicMock()
        video_result.all.return_value = [video_row]

        current_result = MagicMock()
        current_result.all.return_value = [current_row]

        mock_session.execute = AsyncMock(
            side_effect=[alias_result, video_result, current_result]
        )

        mock_console = MagicMock()
        await service.run_recount(mock_session, dry_run=True, console=mock_console)

        # Should print "All counts are correct."
        print_calls = [str(c) for c in mock_console.print.call_args_list]
        output = " ".join(print_calls)
        assert "All counts are correct." in output

        # No writes at all
        mock_session.commit.assert_not_called()
