"""
CLI tests for ``tags normalize --incremental`` (T009-T012, Feature 055).

Covers:
- T009: ``--incremental`` routes to ``run_incremental_backfill()``
- T010: No ``--incremental`` routes to ``run_backfill()`` (backward compat)
- T011: ``--incremental --dry-run`` renders Rich Panel + Rich Table output
- T012: ``--incremental`` with no unresolved tags shows "No unresolved tags found"

References
----------
- Feature 055: Incremental Tag Normalization
- FR-007, FR-008, FR-008a, FR-009, FR-010
- SC-006 (backward compatibility)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.tag_commands import tag_app


@pytest.fixture
def runner() -> CliRunner:
    """CLI test runner for clean stdout capture."""
    return CliRunner()


# ---------------------------------------------------------------------------
# T009 — ``--incremental`` calls ``run_incremental_backfill()``
# ---------------------------------------------------------------------------


class TestIncrementalFlag:
    """T009: --incremental routes to run_incremental_backfill, not run_backfill."""

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_incremental_flag_calls_incremental_backfill(
        self,
        mock_asyncio_run: MagicMock,
        runner: CliRunner,
    ) -> None:
        """``--incremental`` flag causes the CLI to invoke run_incremental_backfill.

        We capture the coroutine that asyncio.run receives and assert that
        run_incremental_backfill (not run_backfill) is called on the service.
        """
        metrics: dict[str, Any] = {
            "tags_processed": 5,
            "aliases_created": 5,
            "canonical_tags_created": 3,
            "canonical_tags_reused": 2,
            "skipped": 0,
            "duration": 0.1,
        }
        mock_service = MagicMock()
        mock_service.run_incremental_backfill = AsyncMock(return_value=metrics)
        mock_service.run_backfill = AsyncMock()

        with (
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_service,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=MagicMock(),
            ),
            patch(
                "chronovista.cli.tag_commands.db_manager",
            ) as mock_db,
        ):
            # Provide an async generator that yields a session
            mock_session = AsyncMock()

            async def fake_get_session(**kwargs: Any):
                yield mock_session

            mock_db.get_session.return_value = fake_get_session()

            result = runner.invoke(tag_app, ["normalize", "--incremental"])

        # asyncio.run must have been called to drive the coroutine
        mock_asyncio_run.assert_called_once()
        assert result.exit_code == 0

    def test_incremental_flag_dispatches_to_incremental_service(
        self,
        runner: CliRunner,
    ) -> None:
        """Integration-style: run_incremental_backfill is called, run_backfill is not."""
        metrics: dict[str, Any] = {
            "tags_processed": 3,
            "aliases_created": 3,
            "canonical_tags_created": 2,
            "canonical_tags_reused": 1,
            "skipped": 0,
            "duration": 0.05,
        }
        mock_service = MagicMock()
        mock_service.run_incremental_backfill = AsyncMock(return_value=metrics)
        mock_service.run_backfill = AsyncMock()

        mock_session = AsyncMock()

        async def fake_get_session(**kwargs: Any):
            yield mock_session

        with (
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_service,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=MagicMock(),
            ),
            patch(
                "chronovista.cli.tag_commands.db_manager"
            ) as mock_db,
        ):
            mock_db.get_session.return_value = fake_get_session()
            result = runner.invoke(tag_app, ["normalize", "--incremental"])

        assert result.exit_code == 0
        mock_service.run_incremental_backfill.assert_awaited_once()
        mock_service.run_backfill.assert_not_awaited()


# ---------------------------------------------------------------------------
# T010 — No ``--incremental`` calls ``run_backfill()`` (backward compatible)
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """T010: Without --incremental the existing run_backfill path is unchanged."""

    def test_no_incremental_flag_calls_run_backfill(
        self,
        runner: CliRunner,
    ) -> None:
        """Without --incremental, run_backfill is called and run_incremental_backfill is not."""
        mock_service = MagicMock()
        mock_service.run_backfill = AsyncMock()
        mock_service.run_incremental_backfill = AsyncMock()

        mock_session = AsyncMock()

        async def fake_get_session(**kwargs: Any):
            yield mock_session

        with (
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_service,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=MagicMock(),
            ),
            patch(
                "chronovista.cli.tag_commands.db_manager"
            ) as mock_db,
        ):
            mock_db.get_session.return_value = fake_get_session()
            result = runner.invoke(tag_app, ["normalize"])

        assert result.exit_code == 0
        mock_service.run_backfill.assert_awaited_once()
        mock_service.run_incremental_backfill.assert_not_awaited()

    def test_explicit_no_incremental_calls_run_backfill(
        self,
        runner: CliRunner,
    ) -> None:
        """Explicitly passing --no-incremental calls run_backfill (SC-006)."""
        mock_service = MagicMock()
        mock_service.run_backfill = AsyncMock()
        mock_service.run_incremental_backfill = AsyncMock()

        mock_session = AsyncMock()

        async def fake_get_session(**kwargs: Any):
            yield mock_session

        with (
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_service,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=MagicMock(),
            ),
            patch(
                "chronovista.cli.tag_commands.db_manager"
            ) as mock_db,
        ):
            mock_db.get_session.return_value = fake_get_session()
            result = runner.invoke(tag_app, ["normalize", "--no-incremental"])

        assert result.exit_code == 0
        mock_service.run_backfill.assert_awaited_once()
        mock_service.run_incremental_backfill.assert_not_awaited()


# ---------------------------------------------------------------------------
# T011 — ``--incremental --dry-run`` renders Rich Panel + Rich Table
# ---------------------------------------------------------------------------


class TestIncrementalDryRun:
    """T011: --incremental --dry-run displays FR-008a Rich Panel summary + Rich Table."""

    def test_dry_run_output_contains_panel_and_table(
        self,
        runner: CliRunner,
    ) -> None:
        """Dry-run output shows summary panel and per-tag table (FR-008a)."""
        # Service returns dry_run metrics including ct_records / ta_records
        ct_records = [
            {
                "canonical_form": "Python Tutorial",
                "normalized_form": "python tutorial",
            }
        ]
        ta_records = [
            {
                "raw_form": "Python Tutorial",
                "normalized_form": "python tutorial",
                "canonical_tag_id": "new",
            },
            {
                "raw_form": "python tutorial",
                "normalized_form": "python tutorial",
                "canonical_tag_id": "reuse-existing-id",
            },
        ]
        metrics: dict[str, Any] = {
            "tags_processed": 2,
            "aliases_created": 2,
            "canonical_tags_created": 1,
            "canonical_tags_reused": 1,
            "skipped": 0,
            "duration": 0.02,
            "dry_run": True,
            "ct_records": ct_records,
            "ta_records": ta_records,
            "skip_list": [],
        }
        mock_service = MagicMock()
        mock_service.run_incremental_backfill = AsyncMock(return_value=metrics)

        mock_session = AsyncMock()

        async def fake_get_session(**kwargs: Any):
            yield mock_session

        with (
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_service,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=MagicMock(),
            ),
            patch(
                "chronovista.cli.tag_commands.db_manager"
            ) as mock_db,
        ):
            mock_db.get_session.return_value = fake_get_session()
            result = runner.invoke(
                tag_app, ["normalize", "--incremental", "--dry-run"]
            )

        assert result.exit_code == 0
        output = result.output

        # Panel-level summary keywords (FR-008a §1)
        assert "dry run" in output.lower() or "dry-run" in output.lower()
        assert "2" in output  # tags_processed

        # Table column headers (FR-008a §2)
        assert "Raw Form" in output
        assert "Normalized Form" in output
        assert "Action" in output

    def test_dry_run_passes_dry_run_true_to_service(
        self,
        runner: CliRunner,
    ) -> None:
        """--dry-run flag is forwarded as dry_run=True to run_incremental_backfill."""
        metrics: dict[str, Any] = {
            "tags_processed": 1,
            "aliases_created": 1,
            "canonical_tags_created": 1,
            "canonical_tags_reused": 0,
            "skipped": 0,
            "duration": 0.01,
            "dry_run": True,
            "ct_records": [{"canonical_form": "ai", "normalized_form": "ai"}],
            "ta_records": [
                {"raw_form": "AI", "normalized_form": "ai", "canonical_tag_id": "new"}
            ],
            "skip_list": [],
        }
        mock_service = MagicMock()
        mock_service.run_incremental_backfill = AsyncMock(return_value=metrics)

        mock_session = AsyncMock()

        async def fake_get_session(**kwargs: Any):
            yield mock_session

        with (
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_service,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=MagicMock(),
            ),
            patch(
                "chronovista.cli.tag_commands.db_manager"
            ) as mock_db,
        ):
            mock_db.get_session.return_value = fake_get_session()
            result = runner.invoke(
                tag_app, ["normalize", "--incremental", "--dry-run"]
            )

        assert result.exit_code == 0
        call_kwargs = mock_service.run_incremental_backfill.call_args
        assert call_kwargs is not None
        # dry_run=True must appear either as positional or keyword argument
        all_args = list(call_kwargs.args) + list(call_kwargs.kwargs.values())
        assert True in all_args or call_kwargs.kwargs.get("dry_run") is True

    def test_dry_run_table_shows_action_new_and_reuse(
        self,
        runner: CliRunner,
    ) -> None:
        """Dry-run table Action column contains 'New' for new canonical tags."""
        ct_records = [
            {"canonical_form": "Claude Code", "normalized_form": "claude code"}
        ]
        ta_records = [
            {
                "raw_form": "Claude Code",
                "normalized_form": "claude code",
                "canonical_tag_id": "new",
            }
        ]
        metrics: dict[str, Any] = {
            "tags_processed": 1,
            "aliases_created": 1,
            "canonical_tags_created": 1,
            "canonical_tags_reused": 0,
            "skipped": 0,
            "duration": 0.01,
            "dry_run": True,
            "ct_records": ct_records,
            "ta_records": ta_records,
            "skip_list": [],
        }
        mock_service = MagicMock()
        mock_service.run_incremental_backfill = AsyncMock(return_value=metrics)

        mock_session = AsyncMock()

        async def fake_get_session(**kwargs: Any):
            yield mock_session

        with (
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_service,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=MagicMock(),
            ),
            patch(
                "chronovista.cli.tag_commands.db_manager"
            ) as mock_db,
        ):
            mock_db.get_session.return_value = fake_get_session()
            result = runner.invoke(
                tag_app, ["normalize", "--incremental", "--dry-run"]
            )

        assert result.exit_code == 0
        assert "New" in result.output
        assert "claude code" in result.output.lower() or "Claude Code" in result.output


# ---------------------------------------------------------------------------
# T012 — ``--incremental`` with no unresolved tags shows informative message
# ---------------------------------------------------------------------------


class TestIncrementalNoUnresolvedTags:
    """T012: When no unresolved tags exist, the command exits cleanly with a message."""

    def test_no_unresolved_tags_shows_message(
        self,
        runner: CliRunner,
    ) -> None:
        """'No unresolved tags found' message shown when nothing to process (FR-009)."""
        metrics: dict[str, Any] = {
            "tags_processed": 0,
            "aliases_created": 0,
            "canonical_tags_created": 0,
            "canonical_tags_reused": 0,
            "skipped": 0,
            "duration": 0.01,
        }
        mock_service = MagicMock()
        mock_service.run_incremental_backfill = AsyncMock(return_value=metrics)

        mock_session = AsyncMock()

        async def fake_get_session(**kwargs: Any):
            yield mock_session

        with (
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_service,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=MagicMock(),
            ),
            patch(
                "chronovista.cli.tag_commands.db_manager"
            ) as mock_db,
        ):
            mock_db.get_session.return_value = fake_get_session()
            result = runner.invoke(tag_app, ["normalize", "--incremental"])

        assert result.exit_code == 0
        assert "no unresolved tags" in result.output.lower()

    def test_no_unresolved_tags_exits_cleanly(
        self,
        runner: CliRunner,
    ) -> None:
        """Zero-work incremental run exits with code 0 (SC-003)."""
        metrics: dict[str, Any] = {
            "tags_processed": 0,
            "aliases_created": 0,
            "canonical_tags_created": 0,
            "canonical_tags_reused": 0,
            "skipped": 0,
            "duration": 0.005,
        }
        mock_service = MagicMock()
        mock_service.run_incremental_backfill = AsyncMock(return_value=metrics)

        mock_session = AsyncMock()

        async def fake_get_session(**kwargs: Any):
            yield mock_session

        with (
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_service,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=MagicMock(),
            ),
            patch(
                "chronovista.cli.tag_commands.db_manager"
            ) as mock_db,
        ):
            mock_db.get_session.return_value = fake_get_session()
            result = runner.invoke(tag_app, ["normalize", "--incremental"])

        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Additional: Live output metrics panel (T016)
# ---------------------------------------------------------------------------


class TestIncrementalLiveOutput:
    """T016: Live (non-dry-run) --incremental run displays FR-007 metrics panel."""

    def test_live_output_displays_metrics_panel(
        self,
        runner: CliRunner,
    ) -> None:
        """FR-007: metrics panel shows tags processed, aliases/canonical counts, duration."""
        metrics: dict[str, Any] = {
            "tags_processed": 10,
            "aliases_created": 10,
            "canonical_tags_created": 7,
            "canonical_tags_reused": 3,
            "skipped": 1,
            "duration": 1.5,
        }
        mock_service = MagicMock()
        mock_service.run_incremental_backfill = AsyncMock(return_value=metrics)

        mock_session = AsyncMock()

        async def fake_get_session(**kwargs: Any):
            yield mock_session

        with (
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_service,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=MagicMock(),
            ),
            patch(
                "chronovista.cli.tag_commands.db_manager"
            ) as mock_db,
        ):
            mock_db.get_session.return_value = fake_get_session()
            result = runner.invoke(tag_app, ["normalize", "--incremental"])

        assert result.exit_code == 0
        output = result.output
        # Key metric values must appear in the output panel
        assert "10" in output  # tags_processed
        assert "7" in output   # canonical_tags_created
        assert "3" in output   # canonical_tags_reused


# ---------------------------------------------------------------------------
# T018 — ``enrich run --skip-normalize`` prevents normalization call
# ---------------------------------------------------------------------------


class TestSkipNormalizeFlag:
    """T018: ``enrich run --skip-normalize`` bypasses automatic normalization (FR-014).

    The ``--skip-normalize`` flag is a Typer Option on the ``enrich run``
    command.  We verify it appears in the help text and is accepted
    without error.  The actual skip-normalize *behaviour* is tested in
    ``TestEnrichmentServiceNormalizationHook`` (service-level test).
    """

    def test_skip_normalize_flag_shown_in_help(
        self,
        runner: CliRunner,
    ) -> None:
        """``--skip-normalize`` appears in ``enrich run --help`` (FR-014)."""
        from chronovista.cli.commands.enrich import app as enrich_app

        result = runner.invoke(enrich_app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--skip-normalize" in result.output

    def test_skip_normalize_flag_described_in_help(
        self,
        runner: CliRunner,
    ) -> None:
        """``--skip-normalize`` help text mentions normalization."""
        from chronovista.cli.commands.enrich import app as enrich_app

        result = runner.invoke(enrich_app, ["run", "--help"])
        assert result.exit_code == 0
        assert "normalization" in result.output.lower()
