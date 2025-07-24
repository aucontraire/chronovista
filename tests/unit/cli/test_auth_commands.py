"""
Tests for CLI auth commands functionality.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from chronovista.cli.main import app


@pytest.fixture
def runner():
    """CLI test runner."""
    return CliRunner()


def test_auth_help(runner):
    """Test auth help command."""
    result = runner.invoke(app, ["auth", "--help"])
    assert result.exit_code == 0
    assert "Authentication commands" in result.stdout


def test_auth_login_command(runner):
    """Test auth login command (either shows already authenticated or starts OAuth)."""
    result = runner.invoke(app, ["auth", "login"])
    assert result.exit_code == 0
    # Should either show already authenticated or start OAuth flow
    assert (
        "Already authenticated" in result.stdout
        or "Starting YouTube OAuth authentication" in result.stdout
    )
