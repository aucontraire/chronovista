"""CLI contract for `chronovista recover filmot` (Feature 065, User Story 3).

Every test invokes the real command through Typer's runner. The recovery run
itself is stubbed, because what is under test here is the *contract* — options,
exit codes, and which counts appear on screen — not the recovery.

The exit codes carry an opinion worth stating: a run that learned nothing is
still a run that completed. An unconfigured credential, a credential the
archive rejects, and a run in which every request failed all exit 0. Only an
unusable *system* is a failure.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.commands.recover import recover_app
from chronovista.services.recovery.models import FilmotRecoveryResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke(runner: CliRunner, result: FilmotRecoveryResult, *args: str):
    """Run the command with the recovery stubbed out."""
    with (
        patch(
            "chronovista.cli.commands.recover.run_filmot_recovery",
            new_callable=AsyncMock,
        ) as run,
        patch("chronovista.cli.commands.recover.db_manager") as db,
    ):
        run.return_value = result

        async def _sessions(*_a, **_kw):
            yield AsyncMock()

        db.get_session = _sessions
        invocation = runner.invoke(recover_app, ["filmot", *args])
        invocation.run_mock = run  # type: ignore[attr-defined]
        return invocation


class TestOptions:
    def test_limit_must_be_positive(self, runner: CliRunner) -> None:
        """`--limit 0` would be a run that cannot recover anything.

        Pinned to 2 rather than "not 0". Click owns 2 for usage errors and the
        project's ``EXIT_SYSTEM_ERROR`` is also 2, so this exact collision is
        the documented behaviour — asserting only ``!= 0`` hid which of the
        two an operator would see.
        """
        result = runner.invoke(recover_app, ["filmot", "--limit", "0"])

        assert result.exit_code == 2

    def test_the_options_reach_the_service(self, runner: CliRunner) -> None:
        """Otherwise the flags are decorative.

        Every other test here stubs the run and asserts on the stub's *return*
        value, so `--dry-run` appeared to work because the canned result said
        ``dry_run=True``. Deleting the forwarding from the command left the
        whole suite green.
        """
        result = _invoke(
            runner, FilmotRecoveryResult(dry_run=True), "--dry-run", "--limit", "7"
        )

        assert result.exit_code == 0
        kwargs = result.run_mock.await_args.kwargs  # type: ignore[attr-defined]
        assert kwargs["limit"] == 7
        assert kwargs["dry_run"] is True

    def test_a_plain_run_forwards_no_limit_and_no_dry_run(
        self, runner: CliRunner
    ) -> None:
        """The defaults are part of the contract too."""
        result = _invoke(runner, FilmotRecoveryResult())

        kwargs = result.run_mock.await_args.kwargs  # type: ignore[attr-defined]
        assert kwargs["limit"] is None
        assert kwargs["dry_run"] is False

    def test_there_is_no_source_selection_option(self, runner: CliRunner) -> None:
        """FR-032: composition waits for the abstraction.

        A `--source` flag here would make the command the de-facto abstraction,
        which is the least testable place to put one.
        """
        help_text = runner.invoke(recover_app, ["filmot", "--help"]).output

        assert "--source" not in help_text

    def test_help_states_the_request_rate(self, runner: CliRunner) -> None:
        """FR-021: the limit must be discoverable, not folklore."""
        help_text = runner.invoke(recover_app, ["filmot", "--help"]).output

        assert "one per second" in help_text


class TestExitCodes:
    def test_an_unconfigured_credential_succeeds(self, runner: CliRunner) -> None:
        """FR-019/SC-009 — an optional source that is absent is not a failure."""
        result = _invoke(runner, FilmotRecoveryResult(ended_early="not_configured"))

        assert result.exit_code == 0
        assert "not configured" in result.output.lower()

    def test_a_run_that_learned_nothing_succeeds(self, runner: CliRunner) -> None:
        """SC-007 — every request failed, so nothing is known. Still exit 0."""
        result = _invoke(
            runner,
            FilmotRecoveryResult(submitted=50, unresolved=50, not_held=0),
        )

        assert result.exit_code == 0

    def test_a_run_ended_by_a_rejected_credential_succeeds(
        self, runner: CliRunner
    ) -> None:
        """FR-019a — distinct from unconfigured, still a completed run."""
        result = _invoke(
            runner,
            FilmotRecoveryResult(
                submitted=50,
                unresolved=50,
                not_attempted=100,
                ended_early="credential_rejected",
            ),
        )

        assert result.exit_code == 0
        assert "credential_rejected" in result.output


class TestSummary:
    def test_absent_and_unresolved_are_separate_lines(self, runner: CliRunner) -> None:
        """The distinction this whole feature descends from.

        Asserts both labels appear *and* both numbers do — a summary that
        rendered one label with the other's total would satisfy a weaker test.
        """
        result = _invoke(
            runner,
            FilmotRecoveryResult(
                submitted=10,
                returned=4,
                updated=3,
                held_no_write=1,
                not_held=5,
                unresolved=2,
            ),
        )

        assert "archive had no record" in result.output
        assert "not looked up" in result.output

    def test_held_with_nothing_to_write_is_reported(self, runner: CliRunner) -> None:
        """FR-022a — without it, returned-minus-updated is unexplained."""
        result = _invoke(
            runner,
            FilmotRecoveryResult(returned=4, updated=3, held_no_write=1),
        )

        assert "held, nothing to write" in result.output

    def test_a_non_reconciling_run_is_flagged(self, runner: CliRunner) -> None:
        """FR-022b — a discrepancy means something was dropped silently."""
        result = _invoke(
            runner,
            FilmotRecoveryResult(returned=10, updated=3, held_no_write=1),
        )

        assert "does not equal" in result.output.lower()

    def test_changed_titles_warn_about_stale_derived_data(
        self, runner: CliRunner
    ) -> None:
        """FR-020a — the operator decides whether to re-run those processes."""
        result = _invoke(
            runner,
            FilmotRecoveryResult(returned=3, updated=3, field_counts={"title": 3}),
        )

        assert "stale" in result.output.lower()

    def test_refusals_are_visible(self, runner: CliRunner) -> None:
        """FR-022c — the cost of the discard rules must not be assumed small."""
        result = _invoke(
            runner,
            FilmotRecoveryResult(
                returned=2,
                held_no_write=2,
                refused_values={"duration:incoming_implausible": 2},
            ),
        )

        assert "refused" in result.output.lower()

    def test_dry_run_says_so(self, runner: CliRunner) -> None:
        result = _invoke(
            runner,
            FilmotRecoveryResult(returned=1, updated=1, dry_run=True),
            "--dry-run",
        )

        assert "dry run" in result.output.lower()

    def test_a_dry_run_does_not_claim_derived_data_went_stale(
        self, runner: CliRunner
    ) -> None:
        """Nothing was written, so nothing downstream of it is stale.

        The warning fired on the same condition in both modes, so a dry run
        told the operator to go and rebuild search indexes and entity mentions
        for titles it had not touched.
        """
        result = _invoke(
            runner,
            FilmotRecoveryResult(
                returned=3, updated=3, field_counts={"title": 3}, dry_run=True
            ),
            "--dry-run",
        )

        assert "stale" not in result.output.lower()


class TestCancellation:
    def test_ctrl_c_reports_the_conventional_code(self, runner: CliRunner) -> None:
        """130, and the operator is told the run was cancelled.

        The handler used to live inside the coroutine, where it could never
        run: asyncio's Runner turns Ctrl+C into task cancellation and re-raises
        KeyboardInterrupt *outside* `asyncio.run`. The message never printed
        and the code was whatever the interpreter chose.
        """

        def _interrupt(coro: Any) -> None:
            coro.close()  # or pytest reports an un-awaited coroutine
            raise KeyboardInterrupt

        with patch(
            "chronovista.cli.commands.recover.asyncio.run", side_effect=_interrupt
        ):
            result = runner.invoke(recover_app, ["filmot"])

        assert result.exit_code == 130
        assert "cancelled" in result.output.lower()
