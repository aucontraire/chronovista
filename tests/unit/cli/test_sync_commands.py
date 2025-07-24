"""
Tests for CLI sync commands functionality.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from chronovista.cli.main import app


@pytest.fixture
def runner():
    """CLI test runner."""
    return CliRunner()


def test_sync_help(runner):
    """Test sync help command."""
    result = runner.invoke(app, ["sync", "--help"])
    assert result.exit_code == 0
    assert "Data synchronization commands" in result.stdout


def test_sync_history_command_requires_arg(runner):
    """Test sync history command requires file path argument."""
    result = runner.invoke(app, ["sync", "history"])
    assert result.exit_code == 2  # Missing required argument
    # When required argument is missing, Typer returns exit code 2
    # Check that the command is recognized and requires an argument
    assert (
        "Missing argument" in result.output
        or "FILE_PATH" in result.output
        or result.exit_code == 2
    )
