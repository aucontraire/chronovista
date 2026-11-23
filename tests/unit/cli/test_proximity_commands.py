"""CLI contract tests for ``chronovista proximity`` (Feature 117, T040).

The service behavior is integration-tested in ``tests/integration/test_proximity_service.py``;
these pin what the CLI owns, per ``contracts/cli.md``: the output fields and the exit
codes (0 all current / completed, 1 error or rebuild lock held, 75 work remains;
not 2, which Click reserves for usage errors).
"""

from __future__ import annotations

import datetime
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.proximity_commands import proximity_app
from chronovista.models.entity_pair_proximity import (
    DryRunReport,
    DryRunScope,
    FailingScope,
    ProcessSummary,
    ProximityStatusReport,
    RebuildOutcome,
)

runner = CliRunner()
_MODULE = "chronovista.cli.proximity_commands"


def _summary(
    *,
    processed: int = 3,
    remaining: int = 0,
    failing: int = 0,
    deferred: int = 0,
    locked_elsewhere: int = 0,
    waiting: int = 0,
) -> ProcessSummary:
    return ProcessSummary(
        processed=processed,
        failed=1 if failing else 0,
        deferred=deferred,
        records_written=7,
        locked_elsewhere=locked_elsewhere,
        failing=failing,
        waiting_to_retry=waiting,
        remaining=remaining,
        complete=remaining == 0,
    )


_BREAKDOWN_FIELDS = (
    "This run",
    "scopes recomputed",
    "records written",
    "errors",
    "skipped (database busy)",
    "Left at the end",
    "held by another worker",
    "waiting to retry",
    "failing (3+ attempts)",
    "not current",
)


class TestRebuild:
    def test_all_current_exits_zero_and_reports_the_breakdown(self) -> None:
        outcome = RebuildOutcome(status="completed", summary=_summary())
        with patch(f"{_MODULE}.rebuild_proximity", AsyncMock(return_value=outcome)):
            result = runner.invoke(proximity_app, ["rebuild"])

        assert result.exit_code == 0, result.output
        for field in _BREAKDOWN_FIELDS:
            assert field in result.output

    def test_work_remaining_exits_two_and_says_incomplete(self) -> None:
        outcome = RebuildOutcome(
            status="incomplete", summary=_summary(remaining=2, failing=1)
        )
        with patch(f"{_MODULE}.rebuild_proximity", AsyncMock(return_value=outcome)):
            result = runner.invoke(proximity_app, ["rebuild"])

        assert result.exit_code == 75, result.output
        assert "Rebuild stopped: work remains" in result.output
        assert "2 scope(s) are not current" in result.output

    @pytest.mark.parametrize(
        ("summary", "advice"),
        [
            (_summary(remaining=1, failing=1), "retry-failed"),
            (_summary(remaining=1, waiting=1), "retry-failed"),
            (_summary(remaining=1, deferred=1), "The database was busy"),
            (_summary(remaining=1, locked_elsewhere=1), "Another worker"),
            (_summary(remaining=1), "Re-run the command; it resumes"),
        ],
        ids=["failing", "waiting", "busy", "held-elsewhere", "other"],
    )
    def test_an_incomplete_run_says_what_to_do_for_its_cause(
        self, summary: ProcessSummary, advice: str
    ) -> None:
        outcome = RebuildOutcome(status="incomplete", summary=summary)
        with patch(f"{_MODULE}.rebuild_proximity", AsyncMock(return_value=outcome)):
            result = runner.invoke(proximity_app, ["rebuild"])

        assert result.exit_code == 75
        assert advice in result.output

    def test_a_held_rebuild_lock_is_refused_with_exit_one(self) -> None:
        outcome = RebuildOutcome(status="locked")
        with patch(f"{_MODULE}.rebuild_proximity", AsyncMock(return_value=outcome)):
            result = runner.invoke(proximity_app, ["rebuild"])

        assert result.exit_code == 1
        assert "Another rebuild is running" in result.output

    def test_an_error_exits_one(self) -> None:
        failing = AsyncMock(side_effect=RuntimeError("database unavailable"))
        with patch(f"{_MODULE}.rebuild_proximity", failing):
            result = runner.invoke(proximity_app, ["rebuild"])

        assert result.exit_code == 1
        assert "database unavailable" in result.output

    def test_options_are_passed_through(self) -> None:
        entity = uuid.uuid4()
        service = AsyncMock(
            return_value=RebuildOutcome(status="completed", summary=_summary())
        )
        with patch(f"{_MODULE}.rebuild_proximity", service):
            result = runner.invoke(
                proximity_app,
                ["rebuild", "--force", "--video-id", "v1", "--entity-id", str(entity)],
            )

        assert result.exit_code == 0, result.output
        kwargs = service.await_args.kwargs
        assert kwargs["force"] is True
        assert kwargs["video_ids"] == ["v1"]
        assert kwargs["entity_ids"] == [entity]

    def test_an_invalid_entity_id_exits_one_without_running(self) -> None:
        service = AsyncMock()
        with patch(f"{_MODULE}.rebuild_proximity", service):
            result = runner.invoke(proximity_app, ["rebuild", "--entity-id", "nope"])

        assert result.exit_code == 1
        assert "Invalid entity id" in result.output
        service.assert_not_awaited()

    def test_an_error_containing_brackets_is_shown_verbatim(self) -> None:
        failing = AsyncMock(side_effect=RuntimeError("bad parameters [1, 2]"))
        with patch(f"{_MODULE}.rebuild_proximity", failing):
            result = runner.invoke(proximity_app, ["rebuild"])

        assert result.exit_code == 1
        assert "bad parameters [1, 2]" in result.output


class TestDryRun:
    def test_dry_run_with_force_is_rejected(self) -> None:
        dry, rebuild = AsyncMock(), AsyncMock()
        with (
            patch(f"{_MODULE}.dry_run_proximity", dry),
            patch(f"{_MODULE}.rebuild_proximity", rebuild),
        ):
            result = runner.invoke(proximity_app, ["rebuild", "--dry-run", "--force"])

        assert result.exit_code == 1
        assert "Conflicting options" in result.output
        dry.assert_not_awaited()
        rebuild.assert_not_awaited()

    def test_a_sample_says_how_many_and_that_it_is_not_a_corpus_validation(
        self,
    ) -> None:
        report = DryRunReport(
            scopes=[DryRunScope(video_id="v1", language_code="en", records=4)],
            sampled=True,
        )
        rebuild = AsyncMock()
        with (
            patch(f"{_MODULE}.dry_run_proximity", AsyncMock(return_value=report)),
            patch(f"{_MODULE}.rebuild_proximity", rebuild),
        ):
            result = runner.invoke(proximity_app, ["rebuild", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "A sample of 1 scope(s)" in result.output
        assert "not a validation of the whole corpus" in result.output
        assert "v1" in result.output and "4" in result.output
        assert "Nothing was written" in result.output
        rebuild.assert_not_awaited()  # the publishing path is never touched

    def test_requested_scopes_are_not_described_as_a_sample(self) -> None:
        report = DryRunReport(
            scopes=[DryRunScope(video_id="v1", language_code="en", records=0)],
            sampled=False,
        )
        with patch(f"{_MODULE}.dry_run_proximity", AsyncMock(return_value=report)):
            result = runner.invoke(
                proximity_app, ["rebuild", "--dry-run", "--video-id", "v1"]
            )

        assert result.exit_code == 0, result.output
        assert "1 requested scope(s)" in result.output
        assert "sample" not in result.output.lower()

    def test_no_matching_scopes_is_said_explicitly(self) -> None:
        report = DryRunReport(scopes=[], sampled=False)
        with patch(f"{_MODULE}.dry_run_proximity", AsyncMock(return_value=report)):
            result = runner.invoke(
                proximity_app, ["rebuild", "--dry-run", "--video-id", "typo"]
            )

        assert result.exit_code == 0, result.output
        assert "No matching scopes" in result.output


class TestDrain:
    @pytest.mark.parametrize(("remaining", "code"), [(0, 0), (4, 75)])
    def test_exit_code_reflects_whether_work_remains(
        self, remaining: int, code: int
    ) -> None:
        service = AsyncMock(return_value=_summary(remaining=remaining))
        with patch(f"{_MODULE}.drain_stale_scopes", service):
            result = runner.invoke(proximity_app, ["drain", "--limit", "5"])

        assert result.exit_code == code, result.output
        assert service.await_args.kwargs["limit"] == 5
        for field in _BREAKDOWN_FIELDS:
            assert field in result.output

    def test_a_clean_system_says_nothing_was_stale(self) -> None:
        clean = _summary(processed=0)
        with patch(f"{_MODULE}.drain_stale_scopes", AsyncMock(return_value=clean)):
            result = runner.invoke(proximity_app, ["drain"])

        assert result.exit_code == 0
        assert "Nothing was stale" in result.output

    def test_a_usage_error_exits_two_which_incomplete_never_does(self) -> None:
        """Click exits 2 on a usage error; "work remains" is 75, so a script that
        re-runs while incomplete cannot loop forever on a typo."""
        service = AsyncMock()
        with patch(f"{_MODULE}.drain_stale_scopes", service):
            result = runner.invoke(proximity_app, ["drain", "--limit", "0"])

        assert result.exit_code == 2
        service.assert_not_awaited()


class TestRetryFailed:
    def test_reports_the_scopes_reset(self) -> None:
        service = AsyncMock(return_value=3)
        with patch(f"{_MODULE}.retry_failed", service):
            result = runner.invoke(proximity_app, ["retry-failed", "--video-id", "v1"])

        assert result.exit_code == 0, result.output
        assert "scopes reset: 3" in result.output
        assert service.await_args.kwargs["video_ids"] == ["v1"]


class TestStatus:
    def test_shows_counts_failing_scopes_oldest_age_rule_and_lock(self) -> None:
        report = ProximityStatusReport(
            rule_version="117.0",
            not_computed=1,
            current=10,
            stale=2,
            failing=[
                FailingScope(
                    video_id="v9",
                    language_code="en",
                    attempts=4,
                    last_error="RuntimeError: boom",
                    next_attempt_at=None,
                )
            ],
            failing_total=1,
            oldest_not_current_at=datetime.datetime(2026, 11, 22, tzinfo=datetime.UTC),
            rebuild_lock_holder_pid=4242,
        )
        with patch(f"{_MODULE}.proximity_status", AsyncMock(return_value=report)):
            result = runner.invoke(proximity_app, ["status"])

        assert result.exit_code == 0, result.output
        for expected in (
            "117.0",
            "current:",
            "stale:",
            "not computed:",
            "failing:",
            "2026-11-22",
            "database session pid 4242",
            "Some scopes keep failing",
            "v9",
            "RuntimeError: boom",
        ):
            assert expected in result.output
