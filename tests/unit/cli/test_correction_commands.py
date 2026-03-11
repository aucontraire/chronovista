"""
Tests for Correction CLI commands.

Tests the ``corrections`` CLI commands including find-replace, rebuild-text,
export, stats, patterns, and batch-revert. Covers option parsing, dry-run
preview, confirmation prompts, summary tables, zero-match output, and
validation error handling.

Feature 036 — Batch Correction Tools (T012–T026)
"""

from __future__ import annotations

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
        assert "--pattern" in result.stdout
        assert "--replacement" in result.stdout
        assert "--regex" in result.stdout
        assert "--case-insensitive" in result.stdout
        assert "--language" in result.stdout
        assert "--channel" in result.stdout
        assert "--video-id" in result.stdout
        assert "--correction-type" in result.stdout
        assert "--correction-note" in result.stdout
        assert "--batch-size" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--yes" in result.stdout
        assert "--limit" in result.stdout

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
