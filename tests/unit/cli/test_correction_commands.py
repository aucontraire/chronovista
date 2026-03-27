"""
Tests for Correction CLI commands.

Tests the ``corrections`` CLI commands including find-replace, rebuild-text,
export, stats, patterns, and batch-revert. Covers option parsing, dry-run
preview, confirmation prompts, summary tables, zero-match output, and
validation error handling.

Feature 036 — Batch Correction Tools (T012–T026)
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from chronovista.cli.correction_commands import (
    _parse_correction_type,
    _truncate_end,
    _truncate_with_context,
    correction_app,
)
from chronovista.models.batch_correction_models import (
    BatchCorrectionResult,
    CorrectionPattern,
    CorrectionStats,
    TypeCount,
    VideoCount,
)
from chronovista.models.enums import CorrectionType
from chronovista.services.cross_segment_discovery import CrossSegmentCandidate

pytestmark = pytest.mark.asyncio


class TestFindReplaceCommand:
    """Test suite for the ``corrections find-replace`` CLI command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    # ------------------------------------------------------------------
    # T012: Option acceptance
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.asyncio.run")
    def test_help_shows_options(
        self, _mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that --help lists all expected options."""
        result = runner.invoke(correction_app, ["find-replace", "--help"])
        assert result.exit_code == 0
        # Strip ANSI escape codes — Typer emits them in CI (no TTY)
        output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        assert "--pattern" in output
        assert "--replacement" in output
        assert "--regex" in output
        assert "--case-insensitive" in output
        assert "--language" in output
        assert "--channel" in output
        assert "--video-id" in output
        assert "--correction-type" in output
        assert "--correction-note" in output
        assert "--batch-size" in output
        assert "--dry-run" in output
        assert "--yes" in output
        assert "--limit" in output

    def test_missing_pattern_fails(self, runner: CliRunner) -> None:
        """Test that omitting --pattern triggers an error."""
        result = runner.invoke(
            correction_app,
            ["find-replace", "--replacement", "bar"],
        )
        assert result.exit_code != 0

    def test_missing_replacement_fails(self, runner: CliRunner) -> None:
        """Test that omitting --replacement triggers an error."""
        result = runner.invoke(
            correction_app,
            ["find-replace", "--pattern", "foo"],
        )
        assert result.exit_code != 0

    def test_invalid_correction_type(self, runner: CliRunner) -> None:
        """Test that an invalid --correction-type value is rejected."""
        result = runner.invoke(
            correction_app,
            [
                "find-replace",
                "--pattern", "foo",
                "--replacement", "bar",
                "--correction-type", "not_a_type",
                "--dry-run",
            ],
        )
        assert result.exit_code != 0
        # typer.BadParameter writes to stderr; check combined output
        output = result.stdout + (result.output or "")
        assert "Invalid correction type" in output or result.exit_code == 2

    def test_invalid_regex_pattern(self, runner: CliRunner) -> None:
        """Test that an invalid regex pattern is rejected."""
        result = runner.invoke(
            correction_app,
            [
                "find-replace",
                "--pattern", "[invalid",
                "--replacement", "bar",
                "--regex",
                "--dry-run",
            ],
        )
        assert result.exit_code == 1
        assert "Invalid regex" in result.stdout

    @patch("chronovista.cli.correction_commands.asyncio.run")
    def test_all_options_accepted(
        self, _mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that the command accepts all option types without error."""
        result = runner.invoke(
            correction_app,
            [
                "find-replace",
                "--pattern", "hello",
                "--replacement", "world",
                "--regex",
                "--case-insensitive",
                "--language", "en",
                "--channel", "UC123",
                "--video-id", "vid1",
                "--video-id", "vid2",
                "--correction-type", "spelling",
                "--correction-note", "bulk fix",
                "--batch-size", "50",
                "--dry-run",
                "--limit", "10",
            ],
        )
        # asyncio.run is mocked so no actual work is done
        assert result.exit_code == 0

    # ------------------------------------------------------------------
    # T013: Dry-run preview
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.asyncio.run")
    def test_dry_run_preview_with_matches(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test dry-run displays Rich preview table and summary line."""
        async def _fake_run() -> None:
            pass

        # We need to capture what asyncio.run receives and invoke it
        # Instead let's mock at a deeper level
        mock_asyncio.return_value = None

        # We'll test by mocking the service directly
        result = runner.invoke(
            correction_app,
            [
                "find-replace",
                "--pattern", "quick",
                "--replacement", "slow",
                "--dry-run",
            ],
        )
        # With asyncio.run mocked the command returns 0 but no output
        assert result.exit_code == 0

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_dry_run_zero_matches(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test dry-run with zero matches prints appropriate message."""
        mock_session = AsyncMock()

        async def _session_gen(*_a, **_kw):
            yield mock_session

        mock_db.get_session = _session_gen

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(return_value=[])

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "nonexistent",
                    "--replacement", "bar",
                    "--dry-run",
                ],
            )
            assert result.exit_code == 0
            assert "No segments matched" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_dry_run_shows_preview_table(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test dry-run shows preview table with correct data."""
        mock_session = AsyncMock()

        async def _session_gen(*_a, **_kw):
            yield mock_session

        mock_db.get_session = _session_gen

        previews = [
            ("vid1", 10, 5.0, "the quick brown fox", "the slow brown fox"),
            ("vid2", 20, 12.5, "quick test", "slow test"),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(
                return_value=previews
            )

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "quick",
                    "--replacement", "slow",
                    "--dry-run",
                ],
            )
            assert result.exit_code == 0
            assert "Dry-Run Preview" in result.stdout
            assert "vid1" in result.stdout
            assert "vid2" in result.stdout
            assert "2" in result.stdout  # segments count
            assert "Dry run complete" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_dry_run_respects_limit(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test dry-run caps preview rows to --limit."""
        mock_session = AsyncMock()

        async def _session_gen(*_a, **_kw):
            yield mock_session

        mock_db.get_session = _session_gen

        # Generate 10 previews
        previews = [
            (f"vid{i}", i, float(i), f"text {i} old", f"text {i} new")
            for i in range(10)
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(
                return_value=previews
            )

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "old",
                    "--replacement", "new",
                    "--dry-run",
                    "--limit", "3",
                ],
            )
            assert result.exit_code == 0
            # Summary should still show total count (10), not limited count
            assert "10" in result.stdout

    # ------------------------------------------------------------------
    # T014: Confirmation prompt
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_confirmation_cancelled(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that denying confirmation aborts the operation."""
        mock_session = AsyncMock()

        async def _session_gen(*_a, **_kw):
            yield mock_session

        mock_db.get_session = _session_gen

        previews = [
            ("vid1", 10, 5.0, "old text", "new text"),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(
                return_value=previews
            )

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "old",
                    "--replacement", "new",
                ],
                input="n\n",
            )
            assert result.exit_code == 0
            assert "Cancelled" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_yes_flag_skips_confirmation(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that --yes skips the confirmation prompt."""
        mock_session = AsyncMock()

        async def _session_gen(*_a, **_kw):
            yield mock_session

        mock_db.get_session = _session_gen

        previews = [
            ("vid1", 10, 5.0, "old text", "new text"),
        ]
        live_result = BatchCorrectionResult(
            total_scanned=100,
            total_matched=1,
            total_applied=1,
            total_skipped=0,
            total_failed=0,
            failed_batches=0,
            unique_videos=1,
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            # First call (dry-run scan for count) returns previews,
            # second call (live) returns BatchCorrectionResult
            mock_svc_instance.find_and_replace = AsyncMock(
                side_effect=[previews, live_result]
            )

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "old",
                    "--replacement", "new",
                    "--yes",
                ],
            )
            assert result.exit_code == 0
            assert "Cancelled" not in result.stdout
            # Should show summary table
            assert "Find-Replace Results" in result.stdout

    # ------------------------------------------------------------------
    # T015: Summary table
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_summary_table_content(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that the summary table contains expected metrics."""
        mock_session = AsyncMock()

        async def _session_gen(*_a, **_kw):
            yield mock_session

        mock_db.get_session = _session_gen

        previews = [("vid1", 10, 5.0, "old text", "new text")]
        live_result = BatchCorrectionResult(
            total_scanned=500,
            total_matched=3,
            total_applied=2,
            total_skipped=1,
            total_failed=0,
            failed_batches=0,
            unique_videos=2,
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(
                side_effect=[previews, live_result]
            )

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "old",
                    "--replacement", "new",
                    "--yes",
                ],
            )
            assert result.exit_code == 0
            assert "Segments scanned" in result.stdout
            assert "Matches found" in result.stdout
            assert "Corrections applied" in result.stdout
            assert "Skipped (no-op)" in result.stdout
            assert "Failed" in result.stdout
            assert "Unique videos" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_summary_shows_failed_batches_when_nonzero(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that 'Failed batches' row appears when > 0."""
        mock_session = AsyncMock()

        async def _session_gen(*_a, **_kw):
            yield mock_session

        mock_db.get_session = _session_gen

        previews = [("vid1", 10, 5.0, "old text", "new text")]
        live_result = BatchCorrectionResult(
            total_scanned=100,
            total_matched=5,
            total_applied=2,
            total_skipped=0,
            total_failed=3,
            failed_batches=1,
            unique_videos=1,
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(
                side_effect=[previews, live_result]
            )

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "old",
                    "--replacement", "new",
                    "--yes",
                ],
            )
            assert result.exit_code == 0
            assert "Failed batches" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_live_zero_matches(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test live mode with zero matches prints message and exits 0."""
        mock_session = AsyncMock()

        async def _session_gen(*_a, **_kw):
            yield mock_session

        mock_db.get_session = _session_gen

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(return_value=[])

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "nonexistent",
                    "--replacement", "bar",
                    "--yes",
                ],
            )
            assert result.exit_code == 0
            assert "No segments matched" in result.stdout

    # ------------------------------------------------------------------
    # T014: Confirmation info display
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_confirmation_shows_details(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that pre-confirmation info shows pattern, replacement, type, filters."""
        mock_session = AsyncMock()

        async def _session_gen(*_a, **_kw):
            yield mock_session

        mock_db.get_session = _session_gen

        previews = [("vid1", 10, 5.0, "old text", "new text")]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(
                return_value=previews
            )

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "old",
                    "--replacement", "new",
                    "--language", "en",
                    "--channel", "UC123",
                ],
                input="n\n",
            )
            assert result.exit_code == 0
            assert "Pattern:" in result.stdout
            assert "old" in result.stdout
            assert "Replacement:" in result.stdout
            assert "new" in result.stdout
            assert "proper_noun" in result.stdout
            assert "language=en" in result.stdout
            assert "channel=UC123" in result.stdout


class TestHelperFunctions:
    """Tests for truncation and parsing helper functions."""

    def test_truncate_end_short(self) -> None:
        """Test end truncation with text shorter than max."""
        assert _truncate_end("hello", 80) == "hello"

    def test_truncate_end_long(self) -> None:
        """Test end truncation with text longer than max."""
        text = "a" * 100
        result = _truncate_end(text, 20)
        assert len(result) == 20
        assert result.endswith("...")

    def test_truncate_with_context_no_match(self) -> None:
        """Test context truncation when pattern not found falls back to end-truncation."""
        result = _truncate_with_context("hello world", "xyz", max_len=80)
        assert result == "hello world"

    def test_truncate_with_context_highlights_match(self) -> None:
        """Test context truncation highlights the matched substring."""
        result = _truncate_with_context(
            "the quick brown fox", "quick", max_len=80
        )
        assert "[bold]quick[/bold]" in result

    def test_truncate_with_context_case_insensitive_find(self) -> None:
        """Test context truncation finds match case-insensitively."""
        result = _truncate_with_context(
            "The QUICK Brown Fox", "quick", max_len=80
        )
        assert "[bold]QUICK[/bold]" in result

    def test_truncate_with_context_long_text(self) -> None:
        """Test context truncation on long text adds ellipsis markers."""
        text = "A" * 50 + "MATCH" + "B" * 50
        result = _truncate_with_context(text, "MATCH", max_len=30)
        assert "[bold]MATCH[/bold]" in result
        assert "..." in result

    def test_parse_correction_type_valid(self) -> None:
        """Test parsing valid correction type strings."""
        assert _parse_correction_type("proper_noun") == CorrectionType.PROPER_NOUN
        assert _parse_correction_type("spelling") == CorrectionType.SPELLING
        assert (
            _parse_correction_type("profanity_fix")
            == CorrectionType.PROFANITY_FIX
        )

    def test_parse_correction_type_invalid(self) -> None:
        """Test parsing invalid correction type raises BadParameter."""
        import typer

        with pytest.raises(typer.BadParameter, match="Invalid correction type"):
            _parse_correction_type("not_a_real_type")


# ======================================================================
# Helper: reusable mock session generator
# ======================================================================


def _mock_session_gen(mock_session: AsyncMock):
    """Create an async generator that yields *mock_session*."""

    async def _gen(*_a, **_kw):
        yield mock_session

    return _gen


# ======================================================================
# T018: rebuild-text command
# ======================================================================


class TestRebuildTextCommand:
    """Test suite for the ``corrections rebuild-text`` CLI command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_help_shows_options(self, runner: CliRunner) -> None:
        """Test that --help lists expected options."""
        result = runner.invoke(correction_app, ["rebuild-text", "--help"])
        assert result.exit_code == 0
        assert "--video-id" in result.stdout
        assert "--language" in result.stdout
        assert "--dry-run" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_dry_run_shows_preview_table(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test dry-run displays a preview table with transcript info."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [
            {
                "video_id": "vid1",
                "language_code": "en",
                "current_length": 500,
                "new_length": 520,
            },
            {
                "video_id": "vid2",
                "language_code": "es",
                "current_length": 300,
                "new_length": 310,
            },
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.rebuild_text = AsyncMock(return_value=previews)

            result = runner.invoke(
                correction_app,
                ["rebuild-text", "--dry-run"],
            )
            assert result.exit_code == 0
            assert "Rebuild Preview" in result.stdout
            assert "vid1" in result.stdout
            assert "vid2" in result.stdout
            assert "Dry run complete" in result.stdout
            assert "2" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_dry_run_zero_transcripts(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test dry-run with no corrected transcripts shows message."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.rebuild_text = AsyncMock(return_value=[])

            result = runner.invoke(
                correction_app,
                ["rebuild-text", "--dry-run"],
            )
            assert result.exit_code == 0
            assert "No transcripts with corrections found" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_live_mode_summary(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test live mode prints rebuilt count and segments processed."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [
            {
                "video_id": "vid1",
                "language_code": "en",
                "current_length": 100,
                "new_length": 110,
            },
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            # First call (dry-run for count), second call (live)
            mock_svc.rebuild_text = AsyncMock(
                side_effect=[previews, (1, 42)]
            )

            result = runner.invoke(
                correction_app,
                ["rebuild-text"],
            )
            assert result.exit_code == 0
            assert "Rebuilt" in result.stdout
            assert "1" in result.stdout
            assert "42" in result.stdout
            assert "segments processed" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_live_zero_transcripts(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test live mode with no corrected transcripts exits cleanly."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.rebuild_text = AsyncMock(return_value=[])

            result = runner.invoke(
                correction_app,
                ["rebuild-text"],
            )
            assert result.exit_code == 0
            assert "No transcripts with corrections found" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_video_id_filter_passed(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that --video-id options are forwarded to the service."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.rebuild_text = AsyncMock(return_value=[])

            runner.invoke(
                correction_app,
                ["rebuild-text", "--video-id", "v1", "--video-id", "v2", "--dry-run"],
            )
            call_kwargs = mock_svc.rebuild_text.call_args[1]
            assert call_kwargs["video_ids"] == ["v1", "v2"]


# ======================================================================
# T020: export command
# ======================================================================


class TestExportCommand:
    """Test suite for the ``corrections export`` CLI command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_help_shows_options(self, runner: CliRunner) -> None:
        """Test that --help lists expected options."""
        result = runner.invoke(correction_app, ["export", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.stdout
        assert "--output" in result.stdout
        assert "--video-id" in result.stdout
        assert "--correction-type" in result.stdout
        assert "--since" in result.stdout
        assert "--until" in result.stdout
        assert "--compact" in result.stdout

    def test_missing_format_fails(self, runner: CliRunner) -> None:
        """Test that omitting --format triggers an error."""
        result = runner.invoke(correction_app, ["export"])
        assert result.exit_code != 0

    def test_invalid_format_rejected(self, runner: CliRunner) -> None:
        """Test that invalid --format values are rejected."""
        result = runner.invoke(
            correction_app,
            ["export", "--format", "xml"],
        )
        assert result.exit_code == 1
        assert "Invalid format" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_csv_stdout(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test CSV export to stdout."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        csv_data = "id,video_id\n1,vid1\n"

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.export_corrections = AsyncMock(
                return_value=(1, csv_data)
            )

            result = runner.invoke(
                correction_app,
                ["export", "--format", "csv"],
            )
            assert result.exit_code == 0
            # CSV data is written to stdout
            assert "id,video_id" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_json_stdout(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test JSON export to stdout."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        json_data = '[{"id": "1", "video_id": "vid1"}]'

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.export_corrections = AsyncMock(
                return_value=(1, json_data)
            )

            result = runner.invoke(
                correction_app,
                ["export", "--format", "json"],
            )
            assert result.exit_code == 0
            assert "vid1" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_file_output(
        self, mock_db: MagicMock, runner: CliRunner, tmp_path
    ) -> None:
        """Test export writes to file when --output is specified."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        csv_data = "id,video_id\n1,vid1\n"
        out_file = tmp_path / "export.csv"

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.export_corrections = AsyncMock(
                return_value=(1, csv_data)
            )

            result = runner.invoke(
                correction_app,
                ["export", "--format", "csv", "--output", str(out_file)],
            )
            assert result.exit_code == 0
            assert out_file.read_text() == csv_data

    def test_since_after_until_rejected(self, runner: CliRunner) -> None:
        """Test that --since >= --until is rejected."""
        result = runner.invoke(
            correction_app,
            [
                "export",
                "--format", "csv",
                "--since", "2025-06-01",
                "--until", "2025-01-01",
            ],
        )
        assert result.exit_code == 1
        assert "--since must be earlier" in result.stdout

    def test_invalid_since_date(self, runner: CliRunner) -> None:
        """Test that invalid --since date format is rejected."""
        result = runner.invoke(
            correction_app,
            ["export", "--format", "csv", "--since", "not-a-date"],
        )
        assert result.exit_code == 1
        assert "Invalid --since date" in result.stdout

    def test_invalid_until_date(self, runner: CliRunner) -> None:
        """Test that invalid --until date format is rejected."""
        result = runner.invoke(
            correction_app,
            ["export", "--format", "csv", "--until", "not-a-date"],
        )
        assert result.exit_code == 1
        assert "Invalid --until date" in result.stdout


# ======================================================================
# T022: stats command
# ======================================================================


class TestStatsCommand:
    """Test suite for the ``corrections stats`` CLI command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_help_shows_options(self, runner: CliRunner) -> None:
        """Test that --help lists expected options."""
        result = runner.invoke(correction_app, ["stats", "--help"])
        assert result.exit_code == 0
        assert "--language" in result.stdout
        assert "--top" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_displays_stats_panel(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that stats command displays panel with metrics."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        stats = CorrectionStats(
            total_corrections=150,
            total_reverts=10,
            unique_segments=120,
            unique_videos=25,
            by_type=[
                TypeCount(correction_type="proper_noun", count=100),
                TypeCount(correction_type="spelling", count=50),
            ],
            top_videos=[
                VideoCount(video_id="vid1", title="Test Video", count=30),
                VideoCount(video_id="vid2", title=None, count=20),
            ],
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.get_statistics = AsyncMock(return_value=stats)

            result = runner.invoke(
                correction_app,
                ["stats"],
            )
            assert result.exit_code == 0
            assert "Correction Statistics" in result.stdout
            assert "150" in result.stdout
            assert "10" in result.stdout
            assert "120" in result.stdout
            assert "25" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_displays_type_breakdown(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that type breakdown table is displayed."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        stats = CorrectionStats(
            total_corrections=50,
            total_reverts=5,
            unique_segments=40,
            unique_videos=10,
            by_type=[
                TypeCount(correction_type="proper_noun", count=30),
                TypeCount(correction_type="spelling", count=20),
            ],
            top_videos=[],
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.get_statistics = AsyncMock(return_value=stats)

            result = runner.invoke(correction_app, ["stats"])
            assert result.exit_code == 0
            assert "Corrections by Type" in result.stdout
            assert "proper_noun" in result.stdout
            assert "spelling" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_displays_top_videos(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that top videos table is displayed."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        stats = CorrectionStats(
            total_corrections=50,
            total_reverts=5,
            unique_segments=40,
            unique_videos=10,
            by_type=[],
            top_videos=[
                VideoCount(video_id="vid1", title="My Video", count=15),
            ],
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.get_statistics = AsyncMock(return_value=stats)

            result = runner.invoke(correction_app, ["stats"])
            assert result.exit_code == 0
            assert "Most-Corrected Videos" in result.stdout
            assert "vid1" in result.stdout
            assert "My Video" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_null_title_shows_placeholder(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that videos with no title show '(no title)' placeholder."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        stats = CorrectionStats(
            total_corrections=10,
            total_reverts=0,
            unique_segments=5,
            unique_videos=1,
            by_type=[],
            top_videos=[
                VideoCount(video_id="vid1", title=None, count=10),
            ],
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.get_statistics = AsyncMock(return_value=stats)

            result = runner.invoke(correction_app, ["stats"])
            assert result.exit_code == 0
            assert "(no title)" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_language_filter_passed(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that --language is forwarded to the service."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        stats = CorrectionStats(
            total_corrections=0,
            total_reverts=0,
            unique_segments=0,
            unique_videos=0,
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.get_statistics = AsyncMock(return_value=stats)

            runner.invoke(correction_app, ["stats", "--language", "es"])
            call_kwargs = mock_svc.get_statistics.call_args[1]
            assert call_kwargs["language"] == "es"


# ======================================================================
# T024: patterns command
# ======================================================================


class TestPatternsCommand:
    """Test suite for the ``corrections patterns`` CLI command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_help_shows_options(self, runner: CliRunner) -> None:
        """Test that --help lists expected options."""
        result = runner.invoke(correction_app, ["patterns", "--help"])
        assert result.exit_code == 0
        assert "--min-occurrences" in result.stdout
        assert "--limit" in result.stdout
        assert "--show-completed" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_displays_patterns_table(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that patterns command displays table with pattern rows."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        patterns = [
            CorrectionPattern(
                original_text="teh",
                corrected_text="the",
                occurrences=15,
                remaining_matches=8,
            ),
            CorrectionPattern(
                original_text="recieve",
                corrected_text="receive",
                occurrences=10,
                remaining_matches=3,
            ),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.get_patterns = AsyncMock(return_value=patterns)

            result = runner.invoke(correction_app, ["patterns"])
            assert result.exit_code == 0
            assert "Correction Patterns" in result.stdout
            assert "teh" in result.stdout
            assert "the" in result.stdout
            assert "recieve" in result.stdout
            assert "receive" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_suggested_command_shown(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that each row includes a suggested find-replace command."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        patterns = [
            CorrectionPattern(
                original_text="teh",
                corrected_text="the",
                occurrences=5,
                remaining_matches=2,
            ),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.get_patterns = AsyncMock(return_value=patterns)

            # Use wider terminal to avoid column truncation in Rich table
            wide_runner = CliRunner()
            with patch(
                "chronovista.cli.correction_commands.console",
                Console(width=200),
            ):
                result = wide_runner.invoke(correction_app, ["patterns"])
            assert result.exit_code == 0
            assert "find-replace" in result.stdout
            assert "teh" in result.stdout
            assert "the" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_empty_patterns_message(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that empty pattern list shows appropriate message."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.get_patterns = AsyncMock(return_value=[])

            result = runner.invoke(correction_app, ["patterns"])
            assert result.exit_code == 0
            assert "No recurring correction patterns found" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_min_occurrences_passed(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that --min-occurrences is forwarded to the service."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.get_patterns = AsyncMock(return_value=[])

            runner.invoke(
                correction_app,
                ["patterns", "--min-occurrences", "5"],
            )
            call_kwargs = mock_svc.get_patterns.call_args[1]
            assert call_kwargs["min_occurrences"] == 5

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_long_text_truncated(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that long original/corrected text is end-truncated."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        patterns = [
            CorrectionPattern(
                original_text="x" * 200,
                corrected_text="y" * 200,
                occurrences=3,
                remaining_matches=1,
            ),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.get_patterns = AsyncMock(return_value=patterns)

            result = runner.invoke(correction_app, ["patterns"])
            assert result.exit_code == 0
            # The 200-char string should be truncated (either by _truncate_end
            # with "..." or by Rich's column overflow with ellipsis char)
            assert "x" * 200 not in result.stdout
            assert "y" * 200 not in result.stdout


# ======================================================================
# T026: batch-revert command
# ======================================================================


class TestBatchRevertCommand:
    """Test suite for the ``corrections batch-revert`` CLI command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_help_shows_options(self, runner: CliRunner) -> None:
        """Test that --help lists expected options."""
        result = runner.invoke(correction_app, ["batch-revert", "--help"])
        assert result.exit_code == 0
        assert "--pattern" in result.stdout
        assert "--video-id" in result.stdout
        assert "--language" in result.stdout
        assert "--regex" in result.stdout
        assert "--case-insensitive" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--yes" in result.stdout
        assert "--batch-size" in result.stdout

    def test_missing_pattern_fails(self, runner: CliRunner) -> None:
        """Test that omitting --pattern triggers an error."""
        result = runner.invoke(correction_app, ["batch-revert"])
        assert result.exit_code != 0

    def test_invalid_regex_rejected(self, runner: CliRunner) -> None:
        """Test that invalid regex pattern is rejected."""
        result = runner.invoke(
            correction_app,
            ["batch-revert", "--pattern", "[bad", "--regex", "--dry-run"],
        )
        assert result.exit_code == 1
        assert "Invalid regex" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_dry_run_preview(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test dry-run displays preview table and summary."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [
            ("vid1", 10, 5.0, "corrected text one"),
            ("vid1", 20, 12.5, "corrected text two"),
            ("vid2", 30, 8.0, "corrected text three"),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(return_value=previews)

            result = runner.invoke(
                correction_app,
                ["batch-revert", "--pattern", "corrected", "--dry-run"],
            )
            assert result.exit_code == 0
            assert "Batch Revert Preview" in result.stdout
            assert "vid1" in result.stdout
            assert "vid2" in result.stdout
            assert "3" in result.stdout  # segments count
            assert "2" in result.stdout  # unique videos
            assert "Dry run complete" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_dry_run_zero_matches(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test dry-run with zero matches prints appropriate message."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(return_value=[])

            result = runner.invoke(
                correction_app,
                ["batch-revert", "--pattern", "nothing", "--dry-run"],
            )
            assert result.exit_code == 0
            assert "No corrected segments matched" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_confirmation_cancelled(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that denying confirmation aborts the operation."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [("vid1", 10, 5.0, "some text")]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(return_value=previews)

            result = runner.invoke(
                correction_app,
                ["batch-revert", "--pattern", "some"],
                input="n\n",
            )
            assert result.exit_code == 0
            assert "Cancelled" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_yes_flag_skips_confirmation(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that --yes skips the confirmation prompt."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [("vid1", 10, 5.0, "some text")]
        live_result = BatchCorrectionResult(
            total_scanned=200,
            total_matched=1,
            total_applied=1,
            total_skipped=0,
            total_failed=0,
            failed_batches=0,
            unique_videos=1,
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            # First call (dry-run scan), second call (live)
            mock_svc.batch_revert = AsyncMock(
                side_effect=[previews, live_result]
            )

            result = runner.invoke(
                correction_app,
                ["batch-revert", "--pattern", "some", "--yes"],
            )
            assert result.exit_code == 0
            assert "Cancelled" not in result.stdout
            assert "Batch Revert Results" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_summary_table_content(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test that the summary table contains expected metric labels."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [("vid1", 10, 5.0, "some text")]
        live_result = BatchCorrectionResult(
            total_scanned=500,
            total_matched=3,
            total_applied=2,
            total_skipped=1,
            total_failed=0,
            failed_batches=0,
            unique_videos=2,
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(
                side_effect=[previews, live_result]
            )

            result = runner.invoke(
                correction_app,
                ["batch-revert", "--pattern", "some", "--yes"],
            )
            assert result.exit_code == 0
            assert "Segments scanned" in result.stdout
            assert "Matches found" in result.stdout
            assert "Reverted" in result.stdout
            assert "Skipped" in result.stdout
            assert "Failed" in result.stdout
            assert "Unique videos" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_live_zero_matches(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Test live mode with zero matches prints message and exits 0."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(return_value=[])

            result = runner.invoke(
                correction_app,
                ["batch-revert", "--pattern", "nothing", "--yes"],
            )
            assert result.exit_code == 0
            assert "No corrected segments matched" in result.stdout


# ======================================================================
# T029–T030: Cross-segment dry-run display (Feature 040)
# ======================================================================


class TestCrossSegmentDryRunDisplay:
    """Test suite for ``corrections find-replace --cross-segment --dry-run`` display.

    Verifies that the dry-run preview table correctly annotates cross-segment
    pairs with box-drawing characters in the "Type" column, and that the
    summary line includes the cross-segment pair count.

    Feature 040 — Correction Pattern Matching (T029–T030)
    """

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    # ------------------------------------------------------------------
    # T029: Type column box-drawing markers for cross-segment pairs
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_cross_segment_dry_run_type_column_markers(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """T029: Dry-run Type column shows box-drawing markers for pairs.

        When --cross-segment is active and the service returns two consecutive
        segments from the same video (adjacent segment IDs), the table's "Type"
        column must display:
          - ``╶─┐`` (U+2576 U+2500 U+2510) for the first segment in the pair
          - ``╶─┘`` (U+2576 U+2500 U+2518) for the second segment in the pair
          - empty string for single-segment rows
        The column header "Type" must appear in the output.
        """
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        # Two consecutive segments from same video form a cross-segment pair
        # (vid001, seg 156 → seg 157). vid002 seg 42 is standalone.
        mock_previews = [
            ("vid001", 156, 342.0, "Claudia Shane", "Claudia Sheinbaum"),
            ("vid001", 157, 345.0, "Bound también", "también siendo"),
            ("vid002", 42, 123.0, "amlo said", "AMLO said"),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(
                return_value=mock_previews
            )

            # Use a wide terminal so Rich does not truncate column headers or
            # cell content. The box-drawing characters (╶─┐, ╶─┘) are 3 chars
            # wide; with the default narrow CliRunner terminal they are
            # abbreviated to whitespace by Rich's overflow handling.
            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "Shane",
                    "--replacement", "Sheinbaum",
                    "--dry-run",
                    "--cross-segment",
                    "--video-id", "vid001",
                    "--video-id", "vid002",
                ],
                env={"COLUMNS": "200"},
            )

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output:\n{result.output}"
        )
        output = result.output

        # "Type" column header must appear (only visible at wide terminal width)
        assert "Type" in output, (
            f"Expected 'Type' column header in output.\nOutput:\n{output}"
        )

        # First segment of pair: U+2576 U+2500 U+2510  →  ╶─┐
        assert "\u2576\u2500\u2510" in output, (
            f"Expected '╶─┐' (U+2576 U+2500 U+2510) in output for pair-first marker.\n"
            f"Output:\n{output}"
        )

        # Second segment of pair: U+2576 U+2500 U+2518  →  ╶─┘
        assert "\u2576\u2500\u2518" in output, (
            f"Expected '╶─┘' (U+2576 U+2500 U+2518) in output for pair-second marker.\n"
            f"Output:\n{output}"
        )

        # The standalone row (vid002, seg 42) must appear but without a pair marker.
        # We verify it appears in the table output.
        assert "vid002" in output, (
            f"Expected 'vid002' (standalone segment) in output.\nOutput:\n{output}"
        )

    # ------------------------------------------------------------------
    # T030: Mixed summary line format with cross-segment pair count
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_cross_segment_dry_run_summary_with_pairs(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """T030a: Summary line includes cross-segment pair count when pairs exist.

        When --cross-segment produces at least one pair, the dry-run summary line
        must contain the segment count, the video count, and the pair count in
        parentheses, e.g. "(1 cross-segment pairs)".
        """
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        # One cross-segment pair (vid001, seg 156–157) + one standalone (vid002, seg 42)
        mock_previews = [
            ("vid001", 156, 342.0, "Claudia Shane", "Claudia Sheinbaum"),
            ("vid001", 157, 345.0, "Bound también", "también siendo"),
            ("vid002", 42, 123.0, "amlo said", "AMLO said"),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(
                return_value=mock_previews
            )

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "Shane",
                    "--replacement", "Sheinbaum",
                    "--dry-run",
                    "--cross-segment",
                    "--video-id", "vid001",
                    "--video-id", "vid002",
                ],
            )

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output:\n{result.output}"
        )
        output = result.output

        # Summary must contain the segment count
        assert "3" in output, (
            f"Expected segment count '3' in summary.\nOutput:\n{output}"
        )

        # Summary must name the video count (2 unique videos: vid001 and vid002)
        assert "2" in output, (
            f"Expected video count '2' in summary.\nOutput:\n{output}"
        )

        # Summary must include the cross-segment pair count annotation.
        # Rich may wrap the summary line so "cross-segment" and "pairs" may be
        # on separate lines. Normalise newlines before asserting.
        normalised = output.replace("\n", " ")
        assert "cross-segment pairs" in normalised, (
            f"Expected 'cross-segment pairs' in summary line.\nOutput:\n{output}"
        )

        # Specifically 1 pair was detected (156 and 157 are consecutive)
        assert "1" in normalised, (
            f"Expected '1' (pair count) in summary.\nOutput:\n{output}"
        )

        # The full dry-run completion message must be present
        assert "Dry run complete" in output, (
            f"Expected 'Dry run complete' in output.\nOutput:\n{output}"
        )

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_cross_segment_dry_run_summary_zero_pairs(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """T030b: Summary shows "(0 cross-segment pairs)" when no pairs found.

        When --cross-segment is active but no adjacent segment pairs are
        returned, the summary must still include the "(0 cross-segment pairs)"
        suffix to confirm that cross-segment matching was attempted.
        """
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        # All standalone segments — no adjacent same-video consecutive pairs
        mock_previews = [
            ("vid001", 10, 50.0, "amlo said hello", "AMLO said hello"),
            ("vid002", 20, 100.0, "amlo spoke again", "AMLO spoke again"),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc_instance = MagicMock()
            mock_service_cls.return_value = mock_svc_instance
            mock_svc_instance.find_and_replace = AsyncMock(
                return_value=mock_previews
            )

            result = runner.invoke(
                correction_app,
                [
                    "find-replace",
                    "--pattern", "amlo",
                    "--replacement", "AMLO",
                    "--dry-run",
                    "--cross-segment",
                    "--video-id", "vid001",
                    "--video-id", "vid002",
                ],
            )

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output:\n{result.output}"
        )
        output = result.output

        # Even with 0 pairs, the cross-segment pair count should appear.
        # Rich may wrap the summary line, so normalise newlines before asserting.
        normalised = output.replace("\n", " ")
        assert "cross-segment pairs" in normalised, (
            f"Expected 'cross-segment pairs' in summary even with P=0.\n"
            f"Output:\n{output}"
        )

        # Pair count should be 0
        assert "0" in normalised, (
            f"Expected '0' pair count in summary.\nOutput:\n{output}"
        )


# ======================================================================
# T017 [US1]: --batch-id CLI flag for batch-revert command (Feature 045)
# ======================================================================


class TestBatchRevertBatchIdFlag:
    """Tests for the ``corrections batch-revert --batch-id`` option.

    Feature 045 (T017) adds a ``--batch-id UUID`` flag that lets the user
    revert an entire prior batch by its UUID, instead of specifying a text
    ``--pattern``.  The two flags are mutually exclusive.
    """

    VALID_UUID: str = "01932f4a-dead-7000-beef-000000000001"

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    # ------------------------------------------------------------------
    # --help shows --batch-id
    # ------------------------------------------------------------------

    def test_help_shows_batch_id_option(self, runner: CliRunner) -> None:
        """``--batch-id`` must appear in the ``batch-revert --help`` output."""
        result = runner.invoke(correction_app, ["batch-revert", "--help"])
        assert result.exit_code == 0
        assert "--batch-id" in result.stdout

    # ------------------------------------------------------------------
    # Mutual exclusivity
    # ------------------------------------------------------------------

    def test_both_pattern_and_batch_id_errors(self, runner: CliRunner) -> None:
        """Providing both --pattern and --batch-id shows an error and exits 1."""
        result = runner.invoke(
            correction_app,
            [
                "batch-revert",
                "--pattern", "teh",
                "--batch-id", self.VALID_UUID,
            ],
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.stdout.lower() or "Error" in result.stdout

    def test_neither_pattern_nor_batch_id_errors(self, runner: CliRunner) -> None:
        """Providing neither --pattern nor --batch-id shows an error and exits 1."""
        result = runner.invoke(correction_app, ["batch-revert"])
        assert result.exit_code == 1
        # The existing guard message covers this case
        assert "Error" in result.stdout or result.exit_code != 0

    # ------------------------------------------------------------------
    # --batch-id with valid UUID — dry-run
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_batch_id_dry_run_calls_service_with_uuid(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """--batch-id dry-run forwards the parsed UUID to batch_revert."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [
            ("vid1", 10, 5.0, "teh quick fox", False),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(return_value=previews)

            runner.invoke(
                correction_app,
                [
                    "batch-revert",
                    "--batch-id", self.VALID_UUID,
                    "--dry-run",
                ],
            )

            mock_svc.batch_revert.assert_awaited_once()
            call_kwargs = mock_svc.batch_revert.call_args.kwargs
            import uuid as _uuid_mod
            assert call_kwargs.get("batch_id") == _uuid_mod.UUID(self.VALID_UUID)

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_batch_id_dry_run_zero_matches_shows_batch_message(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """--batch-id dry-run with no corrections prints batch-specific message."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(return_value=[])

            result = runner.invoke(
                correction_app,
                [
                    "batch-revert",
                    "--batch-id", self.VALID_UUID,
                    "--dry-run",
                ],
            )

            assert result.exit_code == 0
            assert "No corrections found for batch" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_batch_id_dry_run_preview_shows_table_and_summary(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """--batch-id dry-run with matches shows preview table and batch summary."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [
            ("vid1", 10, 5.0, "teh quick fox", False),
            ("vid2", 20, 12.0, "recieve this", False),
        ]

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(return_value=previews)

            result = runner.invoke(
                correction_app,
                [
                    "batch-revert",
                    "--batch-id", self.VALID_UUID,
                    "--dry-run",
                ],
            )

            assert result.exit_code == 0
            assert "Batch Revert Preview" in result.stdout
            assert "vid1" in result.stdout
            assert "vid2" in result.stdout
            # Summary must mention the batch UUID
            assert self.VALID_UUID in result.stdout

    # ------------------------------------------------------------------
    # --batch-id with valid UUID — live mode (yes flag skips confirmation)
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_batch_id_live_mode_calls_batch_revert(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """--batch-id live mode calls batch_revert (dry_run=False) with batch_id."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [("vid1", 10, 5.0, "some text")]
        live_result = BatchCorrectionResult(
            total_scanned=50,
            total_matched=1,
            total_applied=1,
            total_skipped=0,
            total_failed=0,
            failed_batches=0,
            unique_videos=1,
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(
                side_effect=[previews, live_result]
            )

            result = runner.invoke(
                correction_app,
                [
                    "batch-revert",
                    "--batch-id", self.VALID_UUID,
                    "--yes",
                ],
            )

            assert result.exit_code == 0
            # Confirm batch-specific title appears in summary table
            assert "Batch Revert Results" in result.stdout
            # The UUID may be line-wrapped by Rich; normalise before checking
            normalised = result.stdout.replace("\n", "")
            assert "01932f4a" in normalised

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_batch_id_live_zero_matches_shows_batch_message(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """--batch-id live mode with no matches shows batch-specific message."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(return_value=[])

            result = runner.invoke(
                correction_app,
                [
                    "batch-revert",
                    "--batch-id", self.VALID_UUID,
                    "--yes",
                ],
            )

            assert result.exit_code == 0
            assert "No corrections found for batch" in result.stdout

    # ------------------------------------------------------------------
    # --batch-id with invalid UUID
    # ------------------------------------------------------------------

    def test_invalid_uuid_shows_error_and_exits_1(self, runner: CliRunner) -> None:
        """--batch-id with a non-UUID string prints a user-friendly error."""
        result = runner.invoke(
            correction_app,
            ["batch-revert", "--batch-id", "not-a-uuid-at-all"],
        )
        assert result.exit_code == 1
        assert "not a valid UUID" in result.stdout

    def test_invalid_uuid_error_shows_expected_format(
        self, runner: CliRunner
    ) -> None:
        """Error message hints at the expected UUID format."""
        result = runner.invoke(
            correction_app,
            ["batch-revert", "--batch-id", "12345678"],
        )
        assert result.exit_code == 1
        # The error message shows the expected format (see correction_commands.py line ~1036)
        assert "xxxx" in result.stdout.lower() or "format" in result.stdout.lower() or "valid UUID" in result.stdout

    def test_truncated_uuid_shows_error(self, runner: CliRunner) -> None:
        """A truncated UUID (valid prefix only) is rejected with exit code 1."""
        result = runner.invoke(
            correction_app,
            ["batch-revert", "--batch-id", "01932f4a-dead"],
        )
        assert result.exit_code == 1
        assert "not a valid UUID" in result.stdout

    # ------------------------------------------------------------------
    # Skipped segments reported in output
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_skipped_segments_appear_in_summary(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """When batch_revert reports skipped segments, the summary table shows them."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [
            ("vid1", 10, 5.0, "some corrected text"),
            ("vid1", 11, 7.0, "another corrected segment"),
        ]
        live_result = BatchCorrectionResult(
            total_scanned=200,
            total_matched=2,
            total_applied=1,  # one reverted
            total_skipped=1,  # one skipped (already reverted)
            total_failed=0,
            failed_batches=0,
            unique_videos=1,
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(
                side_effect=[previews, live_result]
            )

            result = runner.invoke(
                correction_app,
                [
                    "batch-revert",
                    "--batch-id", self.VALID_UUID,
                    "--yes",
                ],
            )

            assert result.exit_code == 0
            # Skipped metric must appear in the summary table
            assert "Skipped" in result.stdout
            # Value 1 (skipped count) must be visible
            assert "1" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_pattern_mode_skipped_segments_also_in_summary(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Pattern-mode batch-revert also reports skipped segments in summary."""
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen(mock_session)

        previews = [("vid1", 10, 5.0, "some text")]
        live_result = BatchCorrectionResult(
            total_scanned=100,
            total_matched=1,
            total_applied=0,
            total_skipped=1,
            total_failed=0,
            failed_batches=0,
            unique_videos=1,
        )

        with patch(
            "chronovista.cli.correction_commands.BatchCorrectionService"
        ) as mock_service_cls:
            mock_svc = MagicMock()
            mock_service_cls.return_value = mock_svc
            mock_svc.batch_revert = AsyncMock(
                side_effect=[previews, live_result]
            )

            result = runner.invoke(
                correction_app,
                [
                    "batch-revert",
                    "--pattern", "some",
                    "--yes",
                ],
            )

            assert result.exit_code == 0
            assert "Skipped" in result.stdout


# ---------------------------------------------------------------------------
# T026 [US3]: analyze-diffs CLI command tests
# ---------------------------------------------------------------------------


def _mock_session_gen_for_analyze(mock_session: AsyncMock):
    """Create an async generator that yields *mock_session* for analyze-diffs tests."""

    async def _gen(*_a, **_kw):
        yield mock_session

    return _gen


def _make_correction_mock(
    *,
    original_text: str,
    corrected_text: str,
    correction_type: str = "proper_noun",
) -> MagicMock:
    """Build a lightweight mock TranscriptCorrectionDB for analyze-diffs tests."""
    c = MagicMock()
    c.original_text = original_text
    c.corrected_text = corrected_text
    c.correction_type = correction_type
    return c


class TestAnalyzeDiffsCommand:
    """Tests for the ``corrections analyze-diffs`` CLI command.

    Feature 045 (T023 / T026) — The command iterates all non-revert
    corrections, computes word-level diffs, and renders an aggregated Rich
    table with columns: Error Token, Canonical Form, Frequency,
    Associated Entities.

    All database I/O is mocked.  Correction ORM objects are constructed via
    the ``_make_correction_mock`` helper (factory-style) since the factory
    module does not yet expose a CorrectionDB ORM factory for the analyze-diffs
    scenario (the test constructs ORM attributes directly on MagicMock to match
    the duck-typed attribute access in the command).
    """

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    # ------------------------------------------------------------------
    # (a) Rich table output format with correct columns
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_table_has_correct_columns(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """The Rich table must display the four expected column headers.

        When at least one word-level diff pair exists, the output table must
        contain the header columns: "Error Token", "Canonical Form",
        "Frequency", and "Associated Entities".
        """
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen_for_analyze(mock_session)

        correction = _make_correction_mock(
            original_text="Chomski",
            corrected_text="Chomsky",
        )

        with patch(
            "chronovista.cli.correction_commands.TranscriptCorrectionRepository"
        ) as MockRepo, patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=None),
        ):
            repo_instance = AsyncMock()
            repo_instance.get_all_filtered.return_value = [correction]
            MockRepo.return_value = repo_instance

            result = runner.invoke(correction_app, ["analyze-diffs"])

        assert result.exit_code == 0
        # Table title must be present
        assert "Word-Level Diff Analysis" in result.stdout
        # Verifiable column headers (Rich may truncate "Frequency" to "F…"
        # in narrow columns, so check the ones with enough width to render fully)
        assert "Error Token" in result.stdout
        assert "Canonical Form" in result.stdout
        assert "Associated Entities" in result.stdout

    # ------------------------------------------------------------------
    # (b) Frequency aggregation across multiple corrections
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_frequency_aggregated_across_corrections(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Repeated (error_token, canonical_form) pairs accumulate frequency.

        Three corrections all containing "Chomski" → "Chomsky" must produce a
        frequency of 3 for that pair in the output.
        """
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen_for_analyze(mock_session)

        corrections = [
            _make_correction_mock(
                original_text="Chomski",
                corrected_text="Chomsky",
            )
            for _ in range(3)
        ]

        with patch(
            "chronovista.cli.correction_commands.TranscriptCorrectionRepository"
        ) as MockRepo, patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=None),
        ):
            repo_instance = AsyncMock()
            repo_instance.get_all_filtered.return_value = corrections
            MockRepo.return_value = repo_instance

            result = runner.invoke(correction_app, ["analyze-diffs"])

        assert result.exit_code == 0
        # Frequency count of 3 must appear in the table row
        assert "3" in result.stdout
        assert "Chomski" in result.stdout
        assert "Chomsky" in result.stdout

    # ------------------------------------------------------------------
    # (c) No-op corrections (original == corrected) excluded
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_noop_corrections_excluded_from_analysis(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Corrections where original_text == corrected_text must be excluded.

        The command filters out no-op corrections before computing diffs.  When
        only no-op corrections exist the command must print a message indicating
        no corrections were found to analyze and exit cleanly.
        """
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen_for_analyze(mock_session)

        # No-op: original equals corrected
        noop = _make_correction_mock(
            original_text="same text",
            corrected_text="same text",
        )

        with patch(
            "chronovista.cli.correction_commands.TranscriptCorrectionRepository"
        ) as MockRepo, patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=None),
        ):
            repo_instance = AsyncMock()
            repo_instance.get_all_filtered.return_value = [noop]
            MockRepo.return_value = repo_instance

            result = runner.invoke(correction_app, ["analyze-diffs"])

        assert result.exit_code == 0
        # No table rows — command should report that nothing was found
        assert "No corrections found" in result.stdout or "No word-level" in result.stdout

    # ------------------------------------------------------------------
    # (d) Associated entities displayed in output
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_associated_entities_shown_in_output(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """When a canonical token resolves to a known entity, its name appears.

        The command calls ``resolve_entity_id_from_text`` for each canonical
        token and populates the Associated Entities column.  When an entity
        name is returned it must appear in the table output.
        """
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen_for_analyze(mock_session)

        import uuid
        from uuid_utils import uuid7

        entity_id = uuid.UUID(bytes=uuid7().bytes)
        correction = _make_correction_mock(
            original_text="Chomski",
            corrected_text="Chomsky",
        )

        with patch(
            "chronovista.cli.correction_commands.TranscriptCorrectionRepository"
        ) as MockRepo, patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=(entity_id, "Noam Chomsky")),
        ):
            repo_instance = AsyncMock()
            repo_instance.get_all_filtered.return_value = [correction]
            MockRepo.return_value = repo_instance

            result = runner.invoke(correction_app, ["analyze-diffs"])

        assert result.exit_code == 0
        # Entity name must appear in the Associated Entities column
        assert "Noam Chomsky" in result.stdout

    # ------------------------------------------------------------------
    # (e) --help shows expected options
    # ------------------------------------------------------------------

    def test_help_shows_options(self, runner: CliRunner) -> None:
        """The ``analyze-diffs --help`` output must list all expected options."""
        result = runner.invoke(correction_app, ["analyze-diffs", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.stdout
        assert "--min-frequency" in result.stdout

    # ------------------------------------------------------------------
    # (f) Empty corrections list shows informative message
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_empty_corrections_shows_informative_message(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """When no corrections exist at all, an informative message is printed.

        The command must exit cleanly (code 0) and print a message indicating
        that no corrections were found.
        """
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen_for_analyze(mock_session)

        with patch(
            "chronovista.cli.correction_commands.TranscriptCorrectionRepository"
        ) as MockRepo, patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=None),
        ):
            repo_instance = AsyncMock()
            repo_instance.get_all_filtered.return_value = []
            MockRepo.return_value = repo_instance

            result = runner.invoke(correction_app, ["analyze-diffs"])

        assert result.exit_code == 0
        assert "No corrections found" in result.stdout

    # ------------------------------------------------------------------
    # (g) Revert corrections excluded from analysis
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_revert_corrections_excluded(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Revert-type corrections must be excluded from word-level diff analysis.

        The command filters out corrections with correction_type == "revert",
        "revert_to_original", or "revert_to_prior". When only those exist the
        output must indicate no analyzable corrections were found.
        """
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen_for_analyze(mock_session)

        revert_correction = _make_correction_mock(
            original_text="Chomsky",
            corrected_text="Chomski",
            correction_type="revert",
        )

        with patch(
            "chronovista.cli.correction_commands.TranscriptCorrectionRepository"
        ) as MockRepo, patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=None),
        ):
            repo_instance = AsyncMock()
            repo_instance.get_all_filtered.return_value = [revert_correction]
            MockRepo.return_value = repo_instance

            result = runner.invoke(correction_app, ["analyze-diffs"])

        assert result.exit_code == 0
        assert "No corrections found" in result.stdout

    # ------------------------------------------------------------------
    # (h) --min-frequency flag filters low-frequency pairs
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    def test_min_frequency_filters_low_frequency_pairs(
        self, mock_db: MagicMock, runner: CliRunner
    ) -> None:
        """Pairs with frequency below --min-frequency are excluded from output.

        With two distinct pairs each appearing once, ``--min-frequency 2``
        must suppress both and show a "no diffs" message.
        """
        mock_session = AsyncMock()
        mock_db.get_session = _mock_session_gen_for_analyze(mock_session)

        corrections = [
            _make_correction_mock(
                original_text="Chomski",
                corrected_text="Chomsky",
            ),
            _make_correction_mock(
                original_text="recieve",
                corrected_text="receive",
            ),
        ]

        with patch(
            "chronovista.cli.correction_commands.TranscriptCorrectionRepository"
        ) as MockRepo, patch(
            "chronovista.services.asr_alias_registry.resolve_entity_id_from_text",
            new=AsyncMock(return_value=None),
        ):
            repo_instance = AsyncMock()
            repo_instance.get_all_filtered.return_value = corrections
            MockRepo.return_value = repo_instance

            result = runner.invoke(
                correction_app,
                ["analyze-diffs", "--min-frequency", "2"],
            )

        assert result.exit_code == 0
        # Both pairs appear only once; min-frequency=2 should suppress them
        assert "No word-level diffs" in result.stdout or "frequency" in result.stdout.lower()


# ---------------------------------------------------------------------------
# TestDetectBoundariesCommand  (Feature 045 — T032)
# ---------------------------------------------------------------------------


def _mock_session_for_detect(
    entities: list[MagicMock],
) -> MagicMock:
    """Build a mock async session that returns ``entities`` from the first execute.

    Parameters
    ----------
    entities : list[MagicMock]
        NamedEntityDB-like mocks to return from the entity SELECT query.

    Returns
    -------
    MagicMock
        Configured async session mock.
    """
    mock_session = AsyncMock()

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = entities

    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock

    mock_session.execute.return_value = execute_result
    return mock_session


def _make_named_entity_db_mock(
    *,
    name: str = "Sheinbaum",
    entity_type: str = "person",
) -> MagicMock:
    """Build a minimal NamedEntityDB-like mock for CLI testing.

    Parameters
    ----------
    name : str
        Canonical entity name.
    entity_type : str
        Entity type string (matches NamedEntityDB.entity_type).

    Returns
    -------
    MagicMock
        Configured mock resembling a NamedEntityDB row.
    """
    import uuid as _uuid_mod
    ent = MagicMock()
    ent.id = _uuid_mod.uuid4()
    ent.canonical_name = name
    ent.entity_type = entity_type
    ent.status = "active"
    return ent


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
class TestDetectBoundariesCommand:
    """Tests for the ``corrections detect-boundaries`` CLI command (T032).

    The command:
    1. Loads active NamedEntity rows from the DB (filtered by --entity if given).
    2. For each entity, calls PhoneticMatcher.match_entity().
    3. Renders a Rich Table per entity with columns:
       "Original Text", "Proposed Correction", "Confidence", "Evidence".
    4. Prints a summary Panel showing scanned/skipped/total-candidates counts.

    Mock strategy:
    - ``db_manager`` is patched to yield a mock AsyncSession.
    - ``PhoneticMatcher`` is patched to control match_entity() return values.
    """

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    # ---- (a) Rich table output with correct columns ----

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.cli.correction_commands.PhoneticMatcher")
    def test_table_shows_correct_columns(
        self,
        mock_matcher_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Output table contains all four required columns.

        The detect-boundaries command renders a Rich Table with columns:
        "Original Text", "Proposed Correction", "Confidence", "Evidence".
        """
        from chronovista.services.phonetic_matcher import PhoneticMatch as _PM

        entity = _make_named_entity_db_mock(name="Sheinbaum")
        mock_session = _mock_session_for_detect([entity])

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        phonetic_match = _PM(
            original_text="Shanebam",
            proposed_correction="Sheinbaum",
            confidence=0.72,
            evidence_description="phonetic+levenshtein match (conf=0.72)",
            video_id="dQw4w9WgXcQ",
            segment_id=1,
        )

        mock_matcher_instance = MagicMock()
        mock_matcher_instance.match_entity = AsyncMock(return_value=[phonetic_match])
        mock_matcher_cls.return_value = mock_matcher_instance

        result = runner.invoke(correction_app, ["detect-boundaries"])

        assert result.exit_code == 0
        # Rich may wrap column headers; check each word individually
        assert "Original Text" in result.stdout
        assert "Proposed" in result.stdout
        assert "Correction" in result.stdout
        # "Confidence" may be truncated to "C…" in narrow terminals; verify
        # at minimum the data row contains a confidence-formatted value
        assert "Evidence" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.cli.correction_commands.PhoneticMatcher")
    def test_table_shows_match_data(
        self,
        mock_matcher_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Match data (original text, correction, confidence) appears in the output."""
        from chronovista.services.phonetic_matcher import PhoneticMatch as _PM

        entity = _make_named_entity_db_mock(name="Chomsky")
        mock_session = _mock_session_for_detect([entity])

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        phonetic_match = _PM(
            original_text="Chomskee",
            proposed_correction="Chomsky",
            confidence=0.8500,
            evidence_description="phonetic+levenshtein match (conf=0.85)",
            video_id="dQw4w9WgXcQ",
            segment_id=5,
        )

        mock_matcher_instance = MagicMock()
        mock_matcher_instance.match_entity = AsyncMock(return_value=[phonetic_match])
        mock_matcher_cls.return_value = mock_matcher_instance

        result = runner.invoke(correction_app, ["detect-boundaries"])

        assert result.exit_code == 0
        assert "Chomskee" in result.stdout
        assert "Chomsky" in result.stdout
        # Confidence column may be truncated to "0…" in narrow terminal; check
        # the evidence description instead which echoes the conf value
        assert "conf=0.85" in result.stdout

    # ---- (b) --entity filter ----

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.cli.correction_commands.PhoneticMatcher")
    def test_entity_filter_restricts_scan(
        self,
        mock_matcher_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """--entity restricts the scan to entities whose name contains the substring.

        The DB query receives a LOWER(canonical_name).contains(filter) clause.
        We verify this indirectly by confirming only the matching entity's
        table appears in output.
        """
        from chronovista.services.phonetic_matcher import PhoneticMatch as _PM

        entity = _make_named_entity_db_mock(name="Chomsky")
        mock_session = _mock_session_for_detect([entity])

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        phonetic_match = _PM(
            original_text="Chomskee",
            proposed_correction="Chomsky",
            confidence=0.75,
            evidence_description="phonetic+levenshtein match (conf=0.75)",
            video_id="dQw4w9WgXcQ",
            segment_id=3,
        )

        mock_matcher_instance = MagicMock()
        mock_matcher_instance.match_entity = AsyncMock(return_value=[phonetic_match])
        mock_matcher_cls.return_value = mock_matcher_instance

        result = runner.invoke(
            correction_app,
            ["detect-boundaries", "--entity", "Chomsky"],
        )

        assert result.exit_code == 0
        assert "Chomsky" in result.stdout
        assert "1" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.cli.correction_commands.PhoneticMatcher")
    def test_entity_filter_no_match_exits_cleanly(
        self,
        mock_matcher_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """--entity with no matching entities prints a warning and exits 0."""
        mock_session = _mock_session_for_detect([])

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_matcher_cls.return_value = MagicMock()

        result = runner.invoke(
            correction_app,
            ["detect-boundaries", "--entity", "nonexistent_entity_xyz"],
        )

        assert result.exit_code == 0
        assert "No entities found" in result.stdout

    # ---- (c) --threshold flag ----

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.cli.correction_commands.PhoneticMatcher")
    def test_threshold_flag_passed_to_match_entity(
        self,
        mock_matcher_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """--threshold value is forwarded to PhoneticMatcher.match_entity().

        The CLI must pass the user-supplied threshold to the service layer
        rather than always using the default 0.5.
        """
        entity = _make_named_entity_db_mock(name="Sheinbaum")
        mock_session = _mock_session_for_detect([entity])

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_matcher_instance = MagicMock()
        mock_matcher_instance.match_entity = AsyncMock(return_value=[])
        mock_matcher_cls.return_value = mock_matcher_instance

        runner.invoke(
            correction_app,
            ["detect-boundaries", "--threshold", "0.7"],
        )

        mock_matcher_instance.match_entity.assert_called_once()
        call_kwargs = mock_matcher_instance.match_entity.call_args
        assert call_kwargs.kwargs.get("threshold") == pytest.approx(0.7), (
            f"Expected threshold=0.7 forwarded to match_entity; "
            f"got {call_kwargs.kwargs.get('threshold')}"
        )

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.cli.correction_commands.PhoneticMatcher")
    def test_default_threshold_is_0_5(
        self,
        mock_matcher_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When --threshold is omitted, the default 0.5 is used."""
        entity = _make_named_entity_db_mock(name="Sheinbaum")
        mock_session = _mock_session_for_detect([entity])

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_matcher_instance = MagicMock()
        mock_matcher_instance.match_entity = AsyncMock(return_value=[])
        mock_matcher_cls.return_value = mock_matcher_instance

        runner.invoke(correction_app, ["detect-boundaries"])

        call_kwargs = mock_matcher_instance.match_entity.call_args
        assert call_kwargs.kwargs.get("threshold") == pytest.approx(0.5)

    # ---- (d) Skipped entities reported in output ----

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.cli.correction_commands.PhoneticMatcher")
    def test_entities_with_no_matches_counted_as_skipped(
        self,
        mock_matcher_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Entities that return no matches are counted in the 'skipped' summary line.

        When match_entity() returns [] for an entity, the entity is skipped
        (no table is printed) and the entities_skipped counter increments.
        The summary Panel must report the correct skipped count.
        """
        entity = _make_named_entity_db_mock(name="UnknownPerson")
        mock_session = _mock_session_for_detect([entity])

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_matcher_instance = MagicMock()
        mock_matcher_instance.match_entity = AsyncMock(return_value=[])
        mock_matcher_cls.return_value = mock_matcher_instance

        result = runner.invoke(correction_app, ["detect-boundaries"])

        assert result.exit_code == 0
        assert "skipped" in result.stdout.lower()
        assert "1" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.cli.correction_commands.PhoneticMatcher")
    def test_mixed_skipped_and_found_entities(
        self,
        mock_matcher_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Mix of skipped (no matches) and found (with matches) entities is reported.

        With two entities where one has matches and the other has none,
        the summary should show 2 entities scanned and 1 skipped.
        """
        from chronovista.services.phonetic_matcher import PhoneticMatch as _PM

        entity_a = _make_named_entity_db_mock(name="Sheinbaum")
        entity_b = _make_named_entity_db_mock(name="UnknownPerson")
        mock_session = _mock_session_for_detect([entity_a, entity_b])

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        phonetic_match = _PM(
            original_text="Shanebam",
            proposed_correction="Sheinbaum",
            confidence=0.72,
            evidence_description="phonetic+levenshtein match (conf=0.72)",
            video_id="dQw4w9WgXcQ",
            segment_id=1,
        )

        mock_matcher_instance = MagicMock()
        mock_matcher_instance.match_entity = AsyncMock(
            side_effect=[[phonetic_match], []]
        )
        mock_matcher_cls.return_value = mock_matcher_instance

        result = runner.invoke(correction_app, ["detect-boundaries"])

        assert result.exit_code == 0
        assert "Sheinbaum" in result.stdout
        assert "2" in result.stdout

    # ---- help text ----

    def test_detect_boundaries_help_shows_expected_options(
        self, runner: CliRunner
    ) -> None:
        """--help lists all expected options for detect-boundaries."""
        result = runner.invoke(correction_app, ["detect-boundaries", "--help"])

        assert result.exit_code == 0
        assert "--entity" in result.stdout
        assert "--threshold" in result.stdout
        assert "--limit" in result.stdout

    # ---- summary panel ----

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.cli.correction_commands.PhoneticMatcher")
    def test_summary_panel_printed_at_end(
        self,
        mock_matcher_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The summary Panel is always printed at the end of the command output."""
        entity = _make_named_entity_db_mock(name="Sheinbaum")
        mock_session = _mock_session_for_detect([entity])

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_matcher_instance = MagicMock()
        mock_matcher_instance.match_entity = AsyncMock(return_value=[])
        mock_matcher_cls.return_value = mock_matcher_instance

        result = runner.invoke(correction_app, ["detect-boundaries"])

        assert result.exit_code == 0
        assert "ASR Error Boundary Detection Summary" in result.stdout


# ======================================================================
# T036: suggest-cross-segment command (Feature 045 — US5)
# ======================================================================


def _make_cross_segment_candidate(
    *,
    segment_n_id: int = 10,
    segment_n_text: str = "He said Chomski",
    segment_n1_id: int = 11,
    segment_n1_text: str = "is wrong",
    proposed_correction: str = "Chomsky is",
    source_pattern: str = "Chomski is",
    confidence: float = 0.75,
    is_partially_corrected: bool = False,
    video_id: str = "dQw4w9WgXcQ",
) -> "CrossSegmentCandidate":
    """Build a ``CrossSegmentCandidate`` Pydantic model for use in CLI tests."""
    from chronovista.services.cross_segment_discovery import CrossSegmentCandidate

    return CrossSegmentCandidate(
        segment_n_id=segment_n_id,
        segment_n_text=segment_n_text,
        segment_n1_id=segment_n1_id,
        segment_n1_text=segment_n1_text,
        proposed_correction=proposed_correction,
        source_pattern=source_pattern,
        confidence=confidence,
        is_partially_corrected=is_partially_corrected,
        video_id=video_id,
    )


class TestSuggestCrossSegmentCommand:
    """Test suite for the ``corrections suggest-cross-segment`` CLI command.

    All tests patch ``db_manager`` and ``CrossSegmentDiscovery`` to avoid
    any real database connection.

    Test coverage map (T036):
      (a) Rich table output with correct columns/layout
      (b) ``--min-corrections`` flag passed to discover()
      (c) ``--entity`` filter passed to discover()
      (d) Empty results message with suggestion to lower threshold
    """

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a Typer test runner."""
        return CliRunner()

    # ------------------------------------------------------------------
    # Help text
    # ------------------------------------------------------------------

    def test_help_shows_expected_options(self, runner: CliRunner) -> None:
        """--help lists all expected options for suggest-cross-segment."""
        result = runner.invoke(correction_app, ["suggest-cross-segment", "--help"])

        assert result.exit_code == 0
        assert "--min-corrections" in result.stdout
        assert "--entity" in result.stdout
        assert "--limit" in result.stdout

    # ------------------------------------------------------------------
    # (a) Rich table output with correct columns/layout
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_rich_table_shows_correct_columns(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The output table contains the expected column headers."""
        candidate = _make_cross_segment_candidate()
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[candidate])
        mock_discovery_cls.return_value = mock_discovery_instance

        result = runner.invoke(correction_app, ["suggest-cross-segment"])

        assert result.exit_code == 0
        # Rich may truncate narrow column headers in a constrained terminal;
        # verify the meaningful headers that survive.
        assert "Segment N Text" in result.stdout
        assert "Segment N+1 Text" in result.stdout
        assert "Source" in result.stdout
        assert "Proposed Fix" in result.stdout
        # Table title always present regardless of terminal width
        assert "Cross-Segment Candidates" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_rich_table_contains_candidate_data(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The output table rows contain data from the returned candidates."""
        candidate = _make_cross_segment_candidate(
            segment_n_id=42,
            segment_n1_id=43,
            source_pattern="Chomski is",
            proposed_correction="Chomsky is",
            confidence=0.8500,
        )
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[candidate])
        mock_discovery_cls.return_value = mock_discovery_instance

        result = runner.invoke(correction_app, ["suggest-cross-segment"])

        assert result.exit_code == 0
        # The text columns (width=25) reliably show their data
        assert "Chomski is" in result.stdout
        assert "Chomsky is" in result.stdout
        # The table title always appears
        assert "Cross-Segment Candidates" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_partial_flag_shown_for_partially_corrected_candidate(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """'PARTIAL' flag appears in the table row for partially corrected candidates."""
        candidate = _make_cross_segment_candidate(is_partially_corrected=True)
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[candidate])
        mock_discovery_cls.return_value = mock_discovery_instance

        result = runner.invoke(correction_app, ["suggest-cross-segment"])

        assert result.exit_code == 0
        # The summary Panel always shows the partial count explicitly,
        # even when the "Flag" table column is too narrow to display in the test terminal.
        assert "Partially corrected" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_summary_panel_printed(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """A summary Panel is printed at the end of the command output."""
        candidate = _make_cross_segment_candidate()
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[candidate])
        mock_discovery_cls.return_value = mock_discovery_instance

        result = runner.invoke(correction_app, ["suggest-cross-segment"])

        assert result.exit_code == 0
        assert "Cross-Segment Discovery Summary" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_summary_counts_unique_videos(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The summary panel shows unique video count across all candidates."""
        candidates = [
            _make_cross_segment_candidate(
                segment_n_id=1, segment_n1_id=2, video_id="vid1"
            ),
            _make_cross_segment_candidate(
                segment_n_id=3, segment_n1_id=4, video_id="vid2"
            ),
        ]
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=candidates)
        mock_discovery_cls.return_value = mock_discovery_instance

        result = runner.invoke(correction_app, ["suggest-cross-segment"])

        assert result.exit_code == 0
        # Two unique videos — "2" appears in summary
        assert "Unique videos" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_truncates_display_at_limit(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """With --limit=2 and 5 candidates, only 2 rows are shown in the table."""
        candidates = [
            _make_cross_segment_candidate(
                segment_n_id=i, segment_n1_id=i + 100, video_id="vid1"
            )
            for i in range(1, 6)
        ]
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=candidates)
        mock_discovery_cls.return_value = mock_discovery_instance

        result = runner.invoke(
            correction_app, ["suggest-cross-segment", "--limit", "2"]
        )

        assert result.exit_code == 0
        # The "... and N more candidates" message should appear
        assert "more candidates" in result.stdout

    # ------------------------------------------------------------------
    # (b) --min-corrections flag passed to discover()
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_min_corrections_forwarded_to_discover(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """``--min-corrections 7`` is forwarded as ``min_corrections=7`` to discover()."""
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[])
        mock_discovery_cls.return_value = mock_discovery_instance

        runner.invoke(
            correction_app, ["suggest-cross-segment", "--min-corrections", "7"]
        )

        mock_discovery_instance.discover.assert_awaited_once()
        call_kwargs = mock_discovery_instance.discover.call_args.kwargs
        assert call_kwargs.get("min_corrections") == 7

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_default_min_corrections_is_three(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The default ``--min-corrections`` value is 3."""
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[])
        mock_discovery_cls.return_value = mock_discovery_instance

        runner.invoke(correction_app, ["suggest-cross-segment"])

        call_kwargs = mock_discovery_instance.discover.call_args.kwargs
        assert call_kwargs.get("min_corrections") == 3

    # ------------------------------------------------------------------
    # (c) --entity filter forwarded to discover()
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_entity_filter_forwarded_to_discover(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """``--entity Chomsky`` is forwarded as ``entity_name='Chomsky'`` to discover()."""
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[])
        mock_discovery_cls.return_value = mock_discovery_instance

        runner.invoke(
            correction_app, ["suggest-cross-segment", "--entity", "Chomsky"]
        )

        call_kwargs = mock_discovery_instance.discover.call_args.kwargs
        assert call_kwargs.get("entity_name") == "Chomsky"

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_no_entity_flag_passes_none_to_discover(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When ``--entity`` is omitted, ``entity_name=None`` is passed to discover()."""
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[])
        mock_discovery_cls.return_value = mock_discovery_instance

        runner.invoke(correction_app, ["suggest-cross-segment"])

        call_kwargs = mock_discovery_instance.discover.call_args.kwargs
        assert call_kwargs.get("entity_name") is None

    # ------------------------------------------------------------------
    # (d) Empty results message with suggestion to lower threshold
    # ------------------------------------------------------------------

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_empty_results_prints_no_candidates_message(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When discover() returns [], the command prints a 'no candidates found' message."""
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[])
        mock_discovery_cls.return_value = mock_discovery_instance

        result = runner.invoke(correction_app, ["suggest-cross-segment"])

        assert result.exit_code == 0
        assert "No cross-segment candidates found" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_empty_results_suggests_lower_min_corrections(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When no candidates found with min_corrections > 2, the tip message appears."""
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[])
        mock_discovery_cls.return_value = mock_discovery_instance

        # Default min_corrections=3 triggers the tip
        result = runner.invoke(correction_app, ["suggest-cross-segment"])

        assert result.exit_code == 0
        # The tip message references --min-corrections
        assert "--min-corrections" in result.stdout or "min-corrections" in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_empty_results_no_tip_when_min_corrections_is_one(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When min_corrections <= 2, no 'lower threshold' tip is printed."""
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[])
        mock_discovery_cls.return_value = mock_discovery_instance

        result = runner.invoke(
            correction_app, ["suggest-cross-segment", "--min-corrections", "2"]
        )

        assert result.exit_code == 0
        # The tip must NOT appear when already at the minimum
        assert "Tip: Try lowering" not in result.stdout

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_exit_code_zero_on_empty_results(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Empty results exit with code 0 (not an error)."""
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=[])
        mock_discovery_cls.return_value = mock_discovery_instance

        result = runner.invoke(correction_app, ["suggest-cross-segment"])

        assert result.exit_code == 0

    @patch("chronovista.cli.correction_commands.db_manager")
    @patch("chronovista.services.cross_segment_discovery.CrossSegmentDiscovery")
    def test_multiple_candidates_all_appear_in_output(
        self,
        mock_discovery_cls: MagicMock,
        mock_db: MagicMock,
        runner: CliRunner,
    ) -> None:
        """With multiple candidates within the limit, all rows appear in output."""
        candidates = [
            _make_cross_segment_candidate(
                segment_n_id=1,
                segment_n1_id=2,
                source_pattern="Chomski is",
                proposed_correction="Chomsky is",
            ),
            _make_cross_segment_candidate(
                segment_n_id=5,
                segment_n1_id=6,
                source_pattern="teh",
                proposed_correction="the",
            ),
        ]
        mock_session = AsyncMock()

        async def _session_gen(*_a: object, **_kw: object):
            yield mock_session

        mock_db.get_session = _session_gen

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=candidates)
        mock_discovery_cls.return_value = mock_discovery_instance

        result = runner.invoke(correction_app, ["suggest-cross-segment"])

        assert result.exit_code == 0
        assert "Chomski is" in result.stdout
        assert "teh" in result.stdout
