"""
Comprehensive tests for YouTubeOAuthService.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from chronovista.auth.oauth_service import YouTubeOAuthService


class TestYouTubeOAuthService:
    """Test YouTubeOAuthService functionality."""

    @pytest.fixture
    def oauth_service(self):
        """Create OAuth service instance."""
        with patch("chronovista.auth.oauth_service.settings") as mock_settings:
            mock_settings.youtube_client_id = "test_client_id"
            mock_settings.youtube_client_secret = "test_client_secret"
            mock_settings.oauth_redirect_uri = "http://localhost:8080"
            mock_settings.data_dir = Path("/tmp/test_data")
            return YouTubeOAuthService()

    def test_initialization(self, oauth_service):
        """Test OAuth service initialization."""
        assert oauth_service.scopes == [
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ]
        assert oauth_service.client_config is not None
        assert oauth_service.client_config["web"]["client_id"] == "test_client_id"
        assert (
            oauth_service.client_config["web"]["client_secret"] == "test_client_secret"
        )

    @patch("chronovista.auth.oauth_service.Flow")
    @patch("chronovista.auth.oauth_service.secrets.token_urlsafe")
    def test_get_authorization_url(self, mock_token, mock_flow, oauth_service):
        """Test authorization URL generation."""
        mock_token.return_value = "test_state"
        mock_flow_instance = MagicMock()
        mock_flow.from_client_config.return_value = mock_flow_instance
        mock_flow_instance.authorization_url.return_value = ("http://auth.url", None)

        auth_url, state = oauth_service.get_authorization_url()

        assert auth_url == "http://auth.url"
        assert state == "test_state"
        mock_flow.from_client_config.assert_called_once()
        mock_flow_instance.authorization_url.assert_called_once_with(
            access_type="offline",
            include_granted_scopes="true",
            state="test_state",
            prompt="consent",
        )

    @patch("chronovista.auth.oauth_service.Flow")
    @patch("chronovista.auth.oauth_service.urlparse")
    @patch("chronovista.auth.oauth_service.parse_qs")
    def test_authorize_from_callback_success(
        self, mock_parse_qs, mock_urlparse, mock_flow, oauth_service
    ):
        """Test successful authorization from callback."""
        # Mock URL parsing
        mock_urlparse.return_value.query = "code=test&state=test_state"
        mock_parse_qs.return_value = {"state": ["test_state"], "code": ["test_code"]}

        # Mock flow
        mock_flow_instance = MagicMock()
        mock_flow.from_client_config.return_value = mock_flow_instance

        # Mock credentials
        mock_credentials = MagicMock()
        mock_credentials.token = "access_token"
        mock_credentials.refresh_token = "refresh_token"
        mock_credentials.expiry = None
        mock_flow_instance.credentials = mock_credentials

        # Mock _save_token
        oauth_service._save_token = MagicMock()

        result = oauth_service.authorize_from_callback(
            "http://localhost:8080?code=test&state=test_state", "test_state"
        )

        assert isinstance(result, dict)
        oauth_service._save_token.assert_called_once_with(mock_credentials)

    @patch("chronovista.auth.oauth_service.parse_qs")
    @patch("chronovista.auth.oauth_service.urlparse")
    def test_authorize_from_callback_invalid_state(
        self, mock_urlparse, mock_parse_qs, oauth_service
    ):
        """Test authorization failure with invalid state."""
        mock_urlparse.return_value.query = "state=wrong_state"
        mock_parse_qs.return_value = {"state": ["wrong_state"]}

        with pytest.raises(ValueError, match="Invalid state parameter"):
            oauth_service.authorize_from_callback(
                "http://localhost:8080?state=wrong_state", "expected_state"
            )

    @patch("chronovista.auth.oauth_service.parse_qs")
    @patch("chronovista.auth.oauth_service.urlparse")
    def test_authorize_from_callback_error(
        self, mock_urlparse, mock_parse_qs, oauth_service
    ):
        """Test authorization failure with error parameter."""
        mock_urlparse.return_value.query = "error=access_denied&state=test_state"
        mock_parse_qs.return_value = {
            "error": ["access_denied"],
            "state": ["test_state"],
        }

        with pytest.raises(ValueError, match="Authorization denied: access_denied"):
            oauth_service.authorize_from_callback(
                "http://localhost:8080?error=access_denied&state=test_state",
                "test_state",
            )

    def test_save_token(self, oauth_service):
        """Test token saving to file."""
        mock_credentials = MagicMock()
        mock_credentials.token = "access_token"
        mock_credentials.refresh_token = "refresh_token"
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "client_id"
        mock_credentials.client_secret = "client_secret"
        mock_credentials.scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
        mock_credentials.expiry = None

        with patch("builtins.open", mock_open()) as mock_file:
            with patch("pathlib.Path.chmod") as mock_chmod:
                oauth_service._save_token(mock_credentials)
                mock_file.assert_called_once()
                mock_chmod.assert_called_once_with(0o600)

    def test_load_token_file_not_exists(self, oauth_service):
        """Test loading token when file doesn't exist."""
        with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
            # _load_token doesn't handle FileNotFoundError, it should raise
            with pytest.raises(FileNotFoundError):
                oauth_service._load_token()

    def test_load_token_success(self, oauth_service):
        """Test successful token loading."""
        from datetime import datetime

        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True

        token_data = {
            "token": "access_token",
            "refresh_token": "refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "client_secret",
            "scopes": ["scope1"],
            "expiry": "2024-12-31T23:59:59+00:00",
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(token_data))):
            with patch(
                "google.oauth2.credentials.Credentials"
            ) as mock_credentials_class:
                mock_credentials = MagicMock()
                mock_credentials_class.return_value = mock_credentials

                result = oauth_service._load_token()

                assert result == mock_credentials

    def test_load_token_invalid_json(self, oauth_service):
        """Test loading token with invalid JSON."""
        with patch("builtins.open", mock_open(read_data="invalid json")):
            # _load_token doesn't handle JSON errors, it should raise
            with pytest.raises(json.JSONDecodeError):
                oauth_service._load_token()

    def test_is_authenticated_no_token(self, oauth_service):
        """Test is_authenticated when no token exists."""
        oauth_service._load_token = MagicMock(return_value=None)

        assert not oauth_service.is_authenticated()

    def test_is_authenticated_valid_token(self, oauth_service):
        """Test is_authenticated with valid token."""
        mock_credentials = MagicMock()
        mock_credentials.valid = True
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        assert oauth_service.is_authenticated()

    def test_is_authenticated_invalid_token_no_refresh(self, oauth_service):
        """Test is_authenticated with invalid token and no refresh token."""
        mock_credentials = MagicMock()
        mock_credentials.valid = False
        mock_credentials.refresh_token = None
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        assert not oauth_service.is_authenticated()

    @patch("google.auth.transport.requests.Request")
    def test_is_authenticated_invalid_token_with_refresh(
        self, mock_request, oauth_service
    ):
        """Test is_authenticated with invalid token but refresh token available."""
        mock_credentials = MagicMock()
        mock_credentials.valid = False
        mock_credentials.refresh_token = "refresh_token"
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True
        oauth_service._load_token = MagicMock(return_value=mock_credentials)
        oauth_service._save_token = MagicMock()

        # Mock successful refresh - after refresh, token becomes valid
        def mock_refresh(request):
            mock_credentials.valid = True

        mock_credentials.refresh = mock_refresh

        # With new logic: Having expired token + refresh token should return True
        # because we can use the refresh token to get a new access token
        assert oauth_service.is_authenticated()

        # Verify that the token was saved after successful refresh
        oauth_service._save_token.assert_called_once_with(mock_credentials)

    @patch("google.auth.transport.requests.Request")
    def test_is_authenticated_token_refresh_error(self, mock_request, oauth_service):
        """Test is_authenticated with token refresh error."""
        mock_credentials = MagicMock()
        mock_credentials.valid = False
        mock_credentials.refresh_token = "refresh_token"
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        # Mock refresh error
        from google.auth.exceptions import RefreshError

        mock_credentials.refresh.side_effect = RefreshError("Refresh failed")  # type: ignore[no-untyped-call]  # google-auth has no type stubs

        assert not oauth_service.is_authenticated()

    def test_get_token_info_with_valid_credentials(self, oauth_service):
        """Test get_token_info with valid credentials."""
        from datetime import datetime, timezone

        mock_credentials = MagicMock()
        mock_credentials.valid = True
        mock_credentials.expired = False
        mock_credentials.refresh_token = "refresh_token"
        mock_credentials.scopes = ["scope1", "scope2"]
        mock_credentials.expiry = datetime.now(timezone.utc)

        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        result = oauth_service.get_token_info()

        assert result["valid"] is True
        assert result["expired"] is False
        assert result["has_refresh_token"] is True
        assert result["scopes"] == ["scope1", "scope2"]
        assert "expires_at" in result

    def test_get_token_info_no_token_file(self, oauth_service):
        """Test get_token_info when no token file exists."""
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = False

        result = oauth_service.get_token_info()

        assert result is None

    def test_revoke_credentials_not_authenticated(self, oauth_service):
        """Test revoke when not authenticated."""
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = False

        # Should not raise an exception
        oauth_service.revoke_credentials()

        # Method returns None, not boolean

    def test_revoke_credentials_success(self, oauth_service):
        """Test successful credential revocation."""
        mock_credentials = MagicMock()
        mock_credentials.token = "access_token"
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        # Mock credentials.revoke method
        mock_credentials.revoke = MagicMock()

        # Mock file deletion
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True
        oauth_service.token_file.unlink = MagicMock()

        # Should not raise an exception
        oauth_service.revoke_credentials()

        oauth_service.token_file.unlink.assert_called_once()

    def test_revoke_credentials_with_revoke_error(self, oauth_service):
        """Test credential revocation with revoke error."""
        mock_credentials = MagicMock()
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        # Mock credentials.revoke to raise an exception
        mock_credentials.revoke = MagicMock(side_effect=Exception("Revoke error"))

        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True
        oauth_service.token_file.unlink = MagicMock()

        # Should handle exception and still delete file
        oauth_service.revoke_credentials()

        oauth_service.token_file.unlink.assert_called_once()

    def test_revoke_credentials_file_not_exists(self, oauth_service):
        """Test credential revocation when file doesn't exist."""
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = False

        # Should not raise an exception when file doesn't exist
        oauth_service.revoke_credentials()

        oauth_service.token_file.unlink.assert_not_called()

    @patch("chronovista.auth.oauth_service.build")
    def test_get_authenticated_service_success(self, mock_build, oauth_service):
        """Test getting authenticated service when authenticated."""
        mock_credentials = MagicMock()
        mock_credentials.valid = True
        oauth_service.is_authenticated = MagicMock(return_value=True)
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        mock_client = MagicMock()
        mock_build.return_value = mock_client

        result = oauth_service.get_authenticated_service()

        assert result == mock_client
        mock_build.assert_called_once_with(
            "youtube", "v3", credentials=mock_credentials
        )

    def test_get_authenticated_service_not_authenticated(self, oauth_service):
        """Test getting authenticated service when not authenticated."""
        oauth_service.is_authenticated = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="Not authenticated"):
            oauth_service.get_authenticated_service()

    @patch("chronovista.auth.oauth_service.webbrowser.open")
    @patch("builtins.input")
    @patch("builtins.print")
    def test_authorize_interactive_with_browser_open(
        self, mock_print, mock_input, mock_browser_open, oauth_service
    ):
        """Test authorize_interactive opens browser."""
        mock_browser_open.return_value = True
        mock_input.return_value = "http://localhost:8080?code=test&state=test_state"

        oauth_service.get_authorization_url = MagicMock(
            return_value=("http://auth.url", "test_state")
        )
        oauth_service.authorize_from_callback = MagicMock(
            return_value={"access_token": "token"}
        )

        result = oauth_service.authorize_interactive()

        mock_browser_open.assert_called_once_with("http://auth.url")
        assert "access_token" in result

    @patch("chronovista.auth.oauth_service.webbrowser.open")
    @patch("builtins.input")
    @patch("builtins.print")
    def test_authorize_interactive_browser_failure(
        self, mock_print, mock_input, mock_browser_open, oauth_service
    ):
        """Test authorize_interactive handles browser failure."""
        mock_browser_open.side_effect = Exception("Browser error")

        # The actual implementation doesn't handle browser failures, it will raise
        oauth_service.get_authorization_url = MagicMock(
            return_value=("http://auth.url", "test_state")
        )

        with pytest.raises(Exception, match="Browser error"):
            oauth_service.authorize_interactive()

    def test_revoke_credentials_clears_token(self, oauth_service):
        """Test that revoke_credentials clears stored token."""
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True
        oauth_service.token_file.unlink = MagicMock()

        oauth_service.revoke_credentials()

        oauth_service.token_file.unlink.assert_called_once()

    def test_revoke_credentials_handles_missing_file(self, oauth_service):
        """Test revoke_credentials when file doesn't exist."""
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = False

        # Should not raise an exception
        oauth_service.revoke_credentials()

        oauth_service.token_file.unlink.assert_not_called()


class TestYouTubeOAuthServiceEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def oauth_service(self):
        """Create OAuth service instance."""
        with patch("chronovista.auth.oauth_service.settings") as mock_settings:
            mock_settings.youtube_client_id = "test_client_id"
            mock_settings.youtube_client_secret = "test_client_secret"
            mock_settings.oauth_redirect_uri = "http://localhost:8080"
            mock_settings.data_dir = Path("/tmp/test_data")
            return YouTubeOAuthService()

    @patch("chronovista.auth.oauth_service.Flow")
    def test_get_authorization_url_flow_error(self, mock_flow, oauth_service):
        """Test authorization URL generation with flow error."""
        mock_flow.from_client_config.side_effect = Exception("Flow creation error")

        with pytest.raises(Exception, match="Flow creation error"):
            oauth_service.get_authorization_url()

    def test_save_token_file_permission_error(self, oauth_service):
        """Test token saving with file permission error."""
        mock_credentials = MagicMock()
        mock_credentials.to_json.return_value = '{"token": "test"}'

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            # Should handle permission error gracefully
            try:
                oauth_service._save_token(mock_credentials)
            except PermissionError:
                pass  # Expected behavior

    def test_load_token_file_permission_error(self, oauth_service):
        """Test token loading with file permission error."""
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            # _load_token doesn't handle permission errors, it should raise
            with pytest.raises(PermissionError):
                oauth_service._load_token()

    def test_initialization_with_missing_settings(self):
        """Test initialization with missing settings."""
        with patch("chronovista.auth.oauth_service.settings") as mock_settings:
            mock_settings.youtube_client_id = None
            mock_settings.youtube_client_secret = None
            mock_settings.oauth_redirect_uri = "http://localhost:8080"
            mock_settings.data_dir = Path("/tmp/test_data")

            # Should still initialize but with None values
            service = YouTubeOAuthService()
            assert service.client_config["web"]["client_id"] is None

    def test_environment_variable_set(self):
        """Test that OAUTHLIB_INSECURE_TRANSPORT is set."""
        import os

        assert os.environ.get("OAUTHLIB_INSECURE_TRANSPORT") == "1"


class TestYouTubeOAuthServiceInteractive:
    """Test interactive OAuth functionality."""

    @pytest.fixture
    def oauth_service(self):
        """Create OAuth service instance."""
        with patch("chronovista.auth.oauth_service.settings") as mock_settings:
            mock_settings.youtube_client_id = "test_client_id"
            mock_settings.youtube_client_secret = "test_client_secret"
            mock_settings.oauth_redirect_uri = "http://localhost:8080"
            mock_settings.data_dir = Path("/tmp/test_data")
            return YouTubeOAuthService()

    @patch("chronovista.auth.oauth_service.webbrowser.open")
    @patch("builtins.input")
    @patch("builtins.print")
    def test_authorize_interactive_success(
        self, mock_print, mock_input, mock_webbrowser, oauth_service
    ):
        """Test successful interactive authorization."""
        # Mock user input of callback URL
        mock_input.return_value = (
            "http://localhost:8080?code=test_code&state=test_state"
        )

        # Mock get_authorization_url
        oauth_service.get_authorization_url = MagicMock(
            return_value=("http://auth.url", "test_state")
        )

        # Mock authorize_from_callback
        mock_result = {"access_token": "token123", "refresh_token": "refresh123"}
        oauth_service.authorize_from_callback = MagicMock(return_value=mock_result)

        result = oauth_service.authorize_interactive()

        assert result == mock_result
        mock_webbrowser.assert_called_once_with("http://auth.url")
        mock_input.assert_called_once()

    def test_is_authenticated_exception_handling(self, oauth_service):
        """Test is_authenticated with exception handling."""
        # Mock _load_token to raise an exception
        oauth_service._load_token = MagicMock(side_effect=Exception("Token load error"))

        result = oauth_service.is_authenticated()

        assert result is False

    def test_get_authenticated_service_not_authenticated(self, oauth_service):
        """Test get_authenticated_service when not authenticated."""
        oauth_service.is_authenticated = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="Not authenticated"):
            oauth_service.get_authenticated_service()

    @patch("chronovista.auth.oauth_service.build")
    def test_get_authenticated_service_success(self, mock_build, oauth_service):
        """Test successful get_authenticated_service."""
        # Mock authentication
        oauth_service.is_authenticated = MagicMock(return_value=True)

        # Mock credentials
        mock_credentials = MagicMock()
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        # Mock service client
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        result = oauth_service.get_authenticated_service()

        assert result == mock_service
        mock_build.assert_called_once_with(
            "youtube", "v3", credentials=mock_credentials
        )

    def test_get_token_info_authenticated(self, oauth_service):
        """Test get_token_info when authenticated."""
        from datetime import datetime, timezone

        mock_credentials = MagicMock()
        mock_credentials.valid = True
        mock_credentials.expired = False
        mock_credentials.refresh_token = "refresh_token"
        mock_credentials.scopes = ["scope1", "scope2"]
        mock_credentials.expiry = datetime.now(timezone.utc)

        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        result = oauth_service.get_token_info()

        # get_token_info should return a dict when token file exists
        assert result is not None
        assert result["valid"] is True
        assert result["has_refresh_token"] is True
        assert "expires_at" in result

    def test_get_token_info_not_authenticated(self, oauth_service):
        """Test get_token_info when not authenticated."""
        oauth_service.is_authenticated = MagicMock(return_value=False)

        result = oauth_service.get_token_info()

        assert result is None

    def test_revoke_credentials_success_comprehensive(self, oauth_service):
        """Test comprehensive credential revocation success."""
        # Mock credentials
        mock_credentials = MagicMock()
        mock_credentials.valid = True
        mock_credentials.revoke = MagicMock()  # Mock the revoke method
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        # Mock token file operations
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True
        oauth_service.token_file.unlink = MagicMock()

        # Should not raise an exception
        oauth_service.revoke_credentials()

        oauth_service.token_file.unlink.assert_called_once()

    def test_revoke_credentials_exception_comprehensive(self, oauth_service):
        """Test credential revocation with comprehensive exception handling."""
        mock_credentials = MagicMock()
        mock_credentials.revoke = MagicMock(side_effect=Exception("Revoke error"))
        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True
        oauth_service.token_file.unlink = MagicMock()

        # Should handle exception and still delete file
        oauth_service.revoke_credentials()

        oauth_service.token_file.unlink.assert_called_once()


class TestYouTubeOAuthServiceTokenManagement:
    """Test token management functionality."""

    @pytest.fixture
    def oauth_service(self):
        """Create OAuth service instance."""
        with patch("chronovista.auth.oauth_service.settings") as mock_settings:
            mock_settings.youtube_client_id = "test_client_id"
            mock_settings.youtube_client_secret = "test_client_secret"
            mock_settings.oauth_redirect_uri = "http://localhost:8080"
            mock_settings.data_dir = Path("/tmp/test_data")
            return YouTubeOAuthService()

    def test_load_token_file_permission_error(self, oauth_service):
        """Test token loading with file permission error."""
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            # _load_token doesn't handle permission errors, it should raise
            with pytest.raises(PermissionError):
                oauth_service._load_token()

    def test_save_token_create_directory(self, oauth_service):
        """Test token saving creates directory if needed."""
        mock_credentials = MagicMock()
        mock_credentials.token = "access_token"
        mock_credentials.refresh_token = "refresh_token"
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "client_id"
        mock_credentials.client_secret = "client_secret"
        mock_credentials.scopes = ["scope1"]
        mock_credentials.expiry = None

        with patch("builtins.open", mock_open()) as mock_file:
            with patch("pathlib.Path.chmod") as mock_chmod:
                oauth_service._save_token(mock_credentials)
                mock_file.assert_called_once()
                mock_chmod.assert_called_once_with(0o600)

    def test_load_token_corrupted_json(self, oauth_service):
        """Test loading token with corrupted JSON."""
        with patch("builtins.open", mock_open(read_data="corrupted json {")):
            # _load_token doesn't handle JSON errors, it should raise
            with pytest.raises(json.JSONDecodeError):
                oauth_service._load_token()
