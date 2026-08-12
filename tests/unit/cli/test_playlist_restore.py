"""Guard rails on `chronovista playlist restore` (#149).

The command un-hides playlists, and ``--all`` un-hides every one of them. The
argument checks run before any database work, so they are testable on their
own — and they are the part worth testing hardest, because the failure mode is
a bare ``restore`` quietly restoring the entire library.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.commands.playlist import playlist_app
from chronovista.cli.constants import EXIT_USER_ERROR


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestArgumentGuards:
    """These exit before touching the database.

    ``DatabaseManager`` is patched anyway: if a guard regressed, the command
    would fall through to real database work, and the assertion that would
    then fail should be the exit code — not a connection error that happens to
    look like a failure for the wrong reason.
    """

    def test_a_bare_restore_is_rejected(self, runner: CliRunner) -> None:
        """Without this, `restore` with no arguments could un-hide everything."""
        with patch("chronovista.cli.commands.playlist.DatabaseManager") as db:
            result = runner.invoke(playlist_app, ["restore"])

        assert result.exit_code == EXIT_USER_ERROR
        assert "Nothing to restore" in result.output
        db.assert_not_called()

    def test_all_and_id_together_are_rejected(self, runner: CliRunner) -> None:
        """They mean different things; silently preferring one would surprise."""
        with patch("chronovista.cli.commands.playlist.DatabaseManager") as db:
            result = runner.invoke(playlist_app, ["restore", "--all", "--id", "PLx"])

        assert result.exit_code == EXIT_USER_ERROR
        assert "not both" in result.output
        db.assert_not_called()

    def test_the_rejection_points_at_the_listing_command(
        self, runner: CliRunner
    ) -> None:
        """Someone who typed the wrong thing needs to know what is hidden."""
        with patch("chronovista.cli.commands.playlist.DatabaseManager"):
            result = runner.invoke(playlist_app, ["restore"])

        assert "playlist hidden" in result.output


class TestHelp:
    def test_restore_is_registered(self, runner: CliRunner) -> None:
        result = runner.invoke(playlist_app, ["--help"])

        assert result.exit_code == 0
        assert "restore" in result.output
        assert "hidden" in result.output
