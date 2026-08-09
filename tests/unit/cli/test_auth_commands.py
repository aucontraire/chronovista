"""
Tests for CLI auth commands functionality.
"""

from __future__ import annotations

from unittest.mock import patch

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


@patch("chronovista.cli.auth_commands.youtube_oauth")
def test_auth_login_command_when_already_authenticated(mock_oauth, runner):
    """Login reports existing credentials and succeeds."""
    mock_oauth.is_authenticated.return_value = True

    result = runner.invoke(app, ["auth", "login"])

    assert result.exit_code == 0
    assert "Already authenticated" in result.stdout


@patch("chronovista.cli.auth_commands.youtube_oauth")
def test_auth_login_command_starts_oauth_when_unauthenticated(mock_oauth, runner):
    """Login begins the OAuth flow when there are no credentials.

    Previously this and the case above were one test asserting
    `exit_code == 0` and *either* message, with nothing mocked. It therefore
    reported whichever branch the machine running it happened to be in: it
    passed locally, where credentials exist, and failed in CI, where they do
    not. Splitting it pins both branches.
    """
    mock_oauth.is_authenticated.return_value = False
    mock_oauth.authorize_interactive.side_effect = RuntimeError("no browser in CI")

    result = runner.invoke(app, ["auth", "login"])

    assert "Starting YouTube OAuth authentication" in result.stdout
    # The flow could not complete, so the command reports failure (#198)
    assert result.exit_code == 1
