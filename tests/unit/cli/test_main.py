"""
Tests for CLI main functionality.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from chronovista import __version__
from chronovista.cli.main import app


@pytest.fixture
def runner():
    """CLI test runner."""
    return CliRunner()


def test_cli_version(runner):
    """Test version command."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"chronovista v{__version__}" in result.stdout


def test_cli_help(runner):
    """Test help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Personal YouTube data analytics tool" in result.stdout


def test_cli_status(runner):
    """Test status command."""
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "chronovista is ready to use" in result.stdout


def test_cli_version_command(runner):
    """Test explicit version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "chronovista" in result.stdout
    assert "Version" in result.stdout


def test_cli_no_subcommand_shows_help(runner):
    """Test that no args shows help due to no_args_is_help=True."""
    result = runner.invoke(app, [])
    # With no_args_is_help=True, this shows help instead of calling callback
    # The exit code varies by typer version, but we expect help content
    assert "Personal YouTube data analytics tool" in result.stdout


def test_cli_callback_with_invalid_subcommand(runner):
    """Test CLI callback when an invalid subcommand is used."""
    # This will trigger the callback since it's not no-args
    result = runner.invoke(app, ["invalid-command"])
    assert result.exit_code == 2  # Typer error for invalid command
    # The output should contain error about unknown command
    output = result.stdout + result.stderr
    assert "No such command" in output or "invalid-command" in output


def test_main_callback_directly():
    """Test the main callback function directly to cover unreachable lines."""
    from unittest.mock import MagicMock

    import typer

    from chronovista.cli.main import main

    # Create a mock context that simulates no invoked subcommand
    ctx = MagicMock()
    ctx.invoked_subcommand = None

    # This should trigger the lines 77-80
    with pytest.raises(typer.Exit) as exc_info:
        main(ctx, version=False)

    assert exc_info.value.exit_code == 1
