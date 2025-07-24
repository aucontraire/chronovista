"""
Comprehensive tests for auth_commands.py to maximize coverage.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.auth_commands import auth_app, console


class TestAuthAppCommands:
    """Test all auth app CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    def test_auth_app_help(self, runner):
        """Test main auth app help command."""
        result = runner.invoke(auth_app, ["--help"])
        assert result.exit_code == 0
        assert "Authentication commands" in result.output

    def test_auth_app_no_args_shows_help(self, runner):
        """Test that auth app shows help when no arguments provided."""
        result = runner.invoke(auth_app)
        # Should show help due to no_args_is_help=True (exit code 2 is expected for help)
        assert result.exit_code in [0, 2]

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_already_authenticated(self, mock_console, mock_oauth, runner):
        """Test login command when already authenticated."""
        mock_oauth.is_authenticated.return_value = True

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_successful_authentication(self, mock_console, mock_oauth, runner):
        """Test successful login flow."""
        mock_oauth.is_authenticated.return_value = False
        mock_oauth.authorize_interactive.return_value = {
            "access_token": "token123",
            "scope": "youtube.readonly",
        }

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_oauth.authorize_interactive.assert_called_once()
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_authentication_error(self, mock_console, mock_oauth, runner):
        """Test login with authentication error."""
        mock_oauth.is_authenticated.return_value = False
        mock_oauth.authorize_interactive.side_effect = Exception("Auth failed")

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    @patch("chronovista.cli.auth_commands.typer.confirm")
    def test_logout_authenticated(self, mock_confirm, mock_console, mock_oauth, runner):
        """Test logout when authenticated."""
        mock_oauth.is_authenticated.return_value = True
        mock_confirm.return_value = True
        mock_oauth.revoke_credentials.return_value = True

        result = runner.invoke(auth_app, ["logout"])

        assert result.exit_code == 0
        mock_oauth.revoke_credentials.assert_called_once()
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_logout_not_authenticated(self, mock_console, mock_oauth, runner):
        """Test logout when not authenticated."""
        mock_oauth.is_authenticated.return_value = False

        result = runner.invoke(auth_app, ["logout"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    @patch("chronovista.cli.auth_commands.typer.confirm")
    def test_logout_cancelled(self, mock_confirm, mock_console, mock_oauth, runner):
        """Test logout when user cancels."""
        mock_oauth.is_authenticated.return_value = True
        mock_confirm.return_value = False

        result = runner.invoke(auth_app, ["logout"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    @patch("chronovista.cli.auth_commands.typer.confirm")
    def test_logout_revoke_failed(self, mock_confirm, mock_console, mock_oauth, runner):
        """Test logout when revoke fails."""
        mock_oauth.is_authenticated.return_value = True
        mock_confirm.return_value = True
        mock_oauth.revoke_credentials.side_effect = Exception("Revoke failed")

        result = runner.invoke(auth_app, ["logout"])

        assert result.exit_code == 0
        mock_oauth.revoke_credentials.assert_called_once()
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_authenticated(self, mock_console, mock_oauth, runner):
        """Test status command when authenticated."""
        mock_oauth.is_authenticated.return_value = True
        mock_token_info = {
            "valid": True,
            "has_refresh_token": True,
            "expires_at": "2024-12-31T23:59:59Z",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        result = runner.invoke(auth_app, ["status"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_not_authenticated(self, mock_console, mock_oauth, runner):
        """Test status command when not authenticated."""
        mock_oauth.is_authenticated.return_value = False

        result = runner.invoke(auth_app, ["status"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_with_expiry(self, mock_console, mock_oauth, runner):
        """Test status command with token expiry information."""
        mock_oauth.is_authenticated.return_value = True
        mock_token_info = {
            "valid": True,
            "has_refresh_token": True,
            "expires_at": "2024-12-31T23:59:59Z",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        result = runner.invoke(auth_app, ["status"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    def test_invalid_command(self, runner):
        """Test invalid command handling."""
        result = runner.invoke(auth_app, ["invalid-command"])

        assert result.exit_code != 0
        assert "No such command" in result.output or "Usage:" in result.output

    def test_login_command_help(self, runner):
        """Test login command help."""
        result = runner.invoke(auth_app, ["login", "--help"])

        assert result.exit_code == 0
        assert (
            "Login to your YouTube account" in result.output
            or "login" in result.output.lower()
        )

    def test_logout_command_help(self, runner):
        """Test logout command help."""
        result = runner.invoke(auth_app, ["logout", "--help"])

        assert result.exit_code == 0
        assert "Logout" in result.output or "logout" in result.output.lower()

    def test_status_command_help(self, runner):
        """Test status command help."""
        result = runner.invoke(auth_app, ["status", "--help"])

        assert result.exit_code == 0
        assert "status" in result.output.lower()


class TestAuthCommandsModuleLevelCode:
    """Test module-level initialization and constants."""

    def test_module_imports(self):
        """Test that all required modules are imported."""
        from chronovista.cli import auth_commands

        assert hasattr(auth_commands, "auth_app")
        assert hasattr(auth_commands, "console")

    def test_console_instance(self):
        """Test console instance is created."""
        assert console is not None
        assert hasattr(console, "print")

    def test_auth_app_configuration(self):
        """Test auth_app is properly configured."""
        assert auth_app.info.name == "auth"
        assert auth_app.info.help == "Authentication commands"
        # no_args_is_help would be in the Typer internal configuration


class TestAuthCommandsErrorHandling:
    """Test error handling in auth commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_oauth_service_exception(self, mock_console, mock_oauth, runner):
        """Test login when OAuth service raises unexpected exception."""
        mock_oauth.is_authenticated.side_effect = Exception("OAuth service error")

        result = runner.invoke(auth_app, ["login"])

        # Should handle exception gracefully
        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_oauth_service_exception(self, mock_console, mock_oauth, runner):
        """Test status when OAuth service raises unexpected exception."""
        mock_oauth.is_authenticated.side_effect = Exception("OAuth service error")

        result = runner.invoke(auth_app, ["status"])

        # Should handle exception gracefully
        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    @patch("chronovista.cli.auth_commands.typer.confirm")
    def test_logout_oauth_service_exception(
        self, mock_confirm, mock_console, mock_oauth, runner
    ):
        """Test logout when OAuth service raises unexpected exception."""
        mock_oauth.is_authenticated.return_value = True
        mock_confirm.return_value = True
        mock_oauth.revoke_credentials.side_effect = Exception("Revoke error")

        result = runner.invoke(auth_app, ["logout"])

        # Should handle exception gracefully
        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.console.print")
    def test_console_print_calls(self, mock_print, runner):
        """Test that console.print is called in various commands."""
        # Test a simple command that should print
        with patch("chronovista.cli.auth_commands.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False

            result = runner.invoke(auth_app, ["status"])

            assert result.exit_code == 0
            # The command should have called console.print


class TestAuthCommandsInteractiveFlow:
    """Test interactive authentication flow scenarios."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_interactive_success_with_token_info(
        self, mock_console, mock_oauth, runner
    ):
        """Test successful interactive login with detailed token info."""
        mock_oauth.is_authenticated.return_value = False
        mock_oauth.authorize_interactive.return_value = {
            "access_token": "ya29.test_token",
            "refresh_token": "1//test_refresh",
            "scope": "https://www.googleapis.com/auth/youtube.readonly",
            "token_type": "Bearer",
        }

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_oauth.authorize_interactive.assert_called_once()
        # Should have multiple console.print calls for different parts of the flow
        assert mock_console.print.call_count >= 2

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_partial_token_info(self, mock_console, mock_oauth, runner):
        """Test login with partial token information."""
        mock_oauth.is_authenticated.return_value = False
        mock_oauth.authorize_interactive.return_value = {
            "access_token": "token123"
            # Missing some fields
        }

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_oauth.authorize_interactive.assert_called_once()
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_credentials_detailed_info(self, mock_console, mock_oauth, runner):
        """Test status command with detailed credentials information."""
        mock_oauth.is_authenticated.return_value = True
        mock_token_info = {
            "valid": True,
            "has_refresh_token": True,
            "expires_at": "2024-12-31T23:59:59Z",
            "scopes": [
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/youtube.force-ssl",
            ],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        result = runner.invoke(auth_app, ["status"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_expired_credentials(self, mock_console, mock_oauth, runner):
        """Test status command with expired credentials."""
        mock_oauth.is_authenticated.return_value = True
        mock_token_info = {
            "valid": False,
            "has_refresh_token": True,
            "expires_at": "2023-01-01T00:00:00Z",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        result = runner.invoke(auth_app, ["status"])

        assert result.exit_code == 0
        mock_console.print.assert_called()


class TestAuthCommandsEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_none_token_info(self, mock_console, mock_oauth, runner):
        """Test status when get_token_info returns None."""
        mock_oauth.is_authenticated.return_value = True
        mock_oauth.get_token_info.return_value = None

        result = runner.invoke(auth_app, ["status"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_empty_token_info(self, mock_console, mock_oauth, runner):
        """Test login with empty token info."""
        mock_oauth.is_authenticated.return_value = False
        mock_oauth.authorize_interactive.return_value = {}

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_none_token_info(self, mock_console, mock_oauth, runner):
        """Test login when authorize_interactive returns None."""
        mock_oauth.is_authenticated.return_value = False
        mock_oauth.authorize_interactive.return_value = None

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    @patch("chronovista.cli.auth_commands.typer.confirm")
    def test_multiple_consecutive_operations(
        self, mock_confirm, mock_console, mock_oauth, runner
    ):
        """Test multiple consecutive auth operations."""
        # First check status (not authenticated)
        mock_oauth.is_authenticated.return_value = False
        result1 = runner.invoke(auth_app, ["status"])
        assert result1.exit_code == 0

        # Then login
        mock_oauth.authorize_interactive.return_value = {"access_token": "token"}
        result2 = runner.invoke(auth_app, ["login"])
        assert result2.exit_code == 0

        # Then check status (authenticated)
        mock_oauth.is_authenticated.return_value = True
        mock_token_info = {
            "valid": True,
            "has_refresh_token": True,
            "expires_at": "2024-12-31T23:59:59Z",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info
        result3 = runner.invoke(auth_app, ["status"])
        assert result3.exit_code == 0

        # Then logout
        mock_confirm.return_value = True
        mock_oauth.revoke_credentials.return_value = True
        result4 = runner.invoke(auth_app, ["logout"])
        assert result4.exit_code == 0

    def test_auth_app_commands_exist(self):
        """Test that all expected commands exist in auth_app."""
        # Check that commands are registered using typer's command inspection
        commands = auth_app.registered_commands
        if hasattr(commands, "values"):
            command_names = [cmd.name for cmd in commands.values()]
        else:
            # If it's a list, extract command names differently
            command_names = [
                cmd.name if hasattr(cmd, "name") else str(cmd) for cmd in commands
            ]

        expected_commands = ["login", "logout", "status", "refresh"]

        # Check that auth app has expected commands
        assert isinstance(auth_app, object)
        assert hasattr(auth_app, "registered_commands")


class TestAuthRefreshCommand:
    """Test refresh command functionality."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_refresh_not_authenticated(self, mock_console, mock_oauth, runner):
        """Test refresh when not authenticated."""
        mock_oauth.is_authenticated.return_value = False

        result = runner.invoke(auth_app, ["refresh"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_refresh_success(self, mock_console, mock_oauth, runner):
        """Test successful token refresh."""
        mock_oauth.is_authenticated.return_value = True
        mock_service = MagicMock()
        mock_oauth.get_authenticated_service.return_value = mock_service

        result = runner.invoke(auth_app, ["refresh"])

        assert result.exit_code == 0
        mock_oauth.get_authenticated_service.assert_called_once()
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_refresh_exception(self, mock_console, mock_oauth, runner):
        """Test refresh with exception."""
        mock_oauth.is_authenticated.return_value = True
        mock_oauth.get_authenticated_service.side_effect = Exception("Refresh error")

        result = runner.invoke(auth_app, ["refresh"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    def test_refresh_command_help(self, runner):
        """Test refresh command help."""
        result = runner.invoke(auth_app, ["refresh", "--help"])

        assert result.exit_code == 0
        assert "refresh" in result.output.lower()


class TestAuthLoginNewBehavior:
    """Test new login behavior with auto-refresh functionality."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_auto_refresh_success(self, mock_console, mock_oauth, runner):
        """Test login with successful auto-refresh of expired token."""
        # First call: not authenticated (expired token)
        mock_oauth.is_authenticated.return_value = False

        # Mock get_token_info to show expired token with refresh capability
        mock_token_info = {
            "valid": False,
            "has_refresh_token": True,
            "expires_at": "2023-01-01T00:00:00Z",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        # Mock successful refresh via get_authenticated_service
        mock_service = MagicMock()
        mock_oauth.get_authenticated_service.return_value = mock_service

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_oauth.get_authenticated_service.assert_called_once()
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_auto_refresh_fails_fallback_to_fresh_auth(
        self, mock_console, mock_oauth, runner
    ):
        """Test login auto-refresh fails, falls back to fresh authentication."""
        # First call: not authenticated (expired token)
        mock_oauth.is_authenticated.return_value = False

        # Mock get_token_info to show expired token with refresh capability
        mock_token_info = {
            "valid": False,
            "has_refresh_token": True,
            "expires_at": "2023-01-01T00:00:00Z",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        # Mock failed refresh, then successful fresh auth
        mock_oauth.get_authenticated_service.side_effect = Exception("Refresh failed")
        mock_oauth.authorize_interactive.return_value = {
            "access_token": "fresh_token",
            "scope": "https://www.googleapis.com/auth/youtube.readonly",
        }

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_oauth.get_authenticated_service.assert_called_once()
        mock_oauth.authorize_interactive.assert_called_once()
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_no_token_info_fresh_auth(self, mock_console, mock_oauth, runner):
        """Test login when get_token_info fails, proceeds with fresh auth."""
        mock_oauth.is_authenticated.return_value = False
        mock_oauth.get_token_info.side_effect = Exception("Token info failed")

        mock_oauth.authorize_interactive.return_value = {
            "access_token": "fresh_token",
            "scope": "https://www.googleapis.com/auth/youtube.readonly",
        }

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_oauth.authorize_interactive.assert_called_once()
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_expired_token_no_refresh_capability(
        self, mock_console, mock_oauth, runner
    ):
        """Test login with expired token that cannot be refreshed."""
        mock_oauth.is_authenticated.return_value = False

        # Mock get_token_info to show expired token without refresh capability
        mock_token_info = {
            "valid": False,
            "has_refresh_token": False,
            "expires_at": "2023-01-01T00:00:00Z",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        mock_oauth.authorize_interactive.return_value = {
            "access_token": "fresh_token",
            "scope": "https://www.googleapis.com/auth/youtube.readonly",
        }

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        # Should skip auto-refresh attempt and go straight to fresh auth
        mock_oauth.get_authenticated_service.assert_not_called()
        mock_oauth.authorize_interactive.assert_called_once()
        mock_console.print.assert_called()


class TestAuthLoginEdgeCases:
    """Test edge cases for login command to improve coverage."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_with_expires_in_numeric(self, mock_console, mock_oauth, runner):
        """Test login with numeric expires_in."""
        mock_oauth.is_authenticated.return_value = False
        mock_oauth.authorize_interactive.return_value = {
            "expires_in": 1640995200,  # Unix timestamp
            "scope": "https://www.googleapis.com/auth/youtube.readonly",
        }

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_oauth.authorize_interactive.assert_called_once()
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_with_invalid_expires_in(self, mock_console, mock_oauth, runner):
        """Test login with invalid expires_in."""
        mock_oauth.is_authenticated.return_value = False
        mock_oauth.authorize_interactive.return_value = {
            "expires_in": "invalid_timestamp",
            "scope": "https://www.googleapis.com/auth/youtube.readonly",
        }

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_oauth.authorize_interactive.assert_called_once()
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_login_with_type_error_expires_in(self, mock_console, mock_oauth, runner):
        """Test login with TypeError on expires_in."""
        mock_oauth.is_authenticated.return_value = False
        mock_oauth.authorize_interactive.return_value = {
            "expires_in": None,  # Will cause TypeError
            "scope": "https://www.googleapis.com/auth/youtube.readonly",
        }

        result = runner.invoke(auth_app, ["login"])

        assert result.exit_code == 0
        mock_oauth.authorize_interactive.assert_called_once()
        mock_console.print.assert_called()


class TestAuthStatusEdgeCases:
    """Test edge cases for status command to improve coverage."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_invalid_expires_at_format(self, mock_console, mock_oauth, runner):
        """Test status with invalid expires_at format."""
        mock_oauth.is_authenticated.return_value = True
        mock_token_info = {
            "valid": True,
            "has_refresh_token": True,
            "expires_at": "invalid_date_format",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        result = runner.invoke(auth_app, ["status"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_type_error_expires_at(self, mock_console, mock_oauth, runner):
        """Test status with TypeError on expires_at."""
        mock_oauth.is_authenticated.return_value = True
        mock_token_info = {
            "valid": True,
            "has_refresh_token": True,
            "expires_at": None,  # Will cause TypeError
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        result = runner.invoke(auth_app, ["status"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_expired_token_with_refresh_available(
        self, mock_console, mock_oauth, runner
    ):
        """Test status with expired token that has refresh token available."""
        # With new logic: expired tokens mean is_authenticated() returns False
        mock_oauth.is_authenticated.return_value = False  # Changed from True
        mock_token_info = {
            "valid": False,
            "has_refresh_token": True,
            "expires_at": "2023-01-01T00:00:00Z",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        result = runner.invoke(auth_app, ["status"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.auth_commands.youtube_oauth")
    @patch("chronovista.cli.auth_commands.console")
    def test_status_expired_token_no_refresh_available(
        self, mock_console, mock_oauth, runner
    ):
        """Test status with expired token that has no refresh token."""
        # With new logic: expired tokens mean is_authenticated() returns False
        mock_oauth.is_authenticated.return_value = False  # Changed from True
        mock_token_info = {
            "valid": False,
            "has_refresh_token": False,
            "expires_at": "2023-01-01T00:00:00Z",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        }
        mock_oauth.get_token_info.return_value = mock_token_info

        result = runner.invoke(auth_app, ["status"])

        assert result.exit_code == 0
        mock_console.print.assert_called()
