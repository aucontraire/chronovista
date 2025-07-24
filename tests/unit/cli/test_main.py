"""
Tests for CLI main functionality.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from chronovista.cli.main import app


@pytest.fixture
def runner():
    """CLI test runner."""
    return CliRunner()


def test_cli_version(runner):
    """Test version command."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "chronovista v0.1.0" in result.stdout


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
