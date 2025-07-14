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


def test_sync_history_placeholder(runner):
    """Test sync history placeholder."""
    result = runner.invoke(app, ["sync", "history"])
    assert result.exit_code == 0
    assert "Watch history sync not yet implemented" in result.stdout
