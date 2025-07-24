"""
Quick coverage boost for oauth_service.py edge cases.

Targets specific uncovered lines: 188-189, 212-216, 219, 265-266, 302-303
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from chronovista.auth.oauth_service import YouTubeOAuthService


class TestOAuthServiceCoverageBoost:
    """Test OAuth service edge cases for coverage."""

    @pytest.fixture
    def oauth_service(self):
        """Create OAuth service instance."""
        service = YouTubeOAuthService()
        # Mock the token file path
        service.token_file = Path("/tmp/test_token.json")
        return service

    def test_revoke_credentials_no_token_file(self, oauth_service):
        """Test revoke_credentials when token file doesn't exist."""
        # Mock file doesn't exist
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = False

        # Should handle gracefully
        oauth_service.revoke_credentials()

        # Should check if file exists
        oauth_service.token_file.exists.assert_called_once()

    def test_revoke_credentials_invalid_token(self, oauth_service):
        """Test revoke_credentials with invalid/expired token."""
        # Mock file exists but token is invalid
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True

        # Mock load_token to raise exception
        oauth_service._load_token = MagicMock(side_effect=Exception("Invalid token"))

        # Should handle exception gracefully
        oauth_service.revoke_credentials()

        oauth_service.token_file.unlink.assert_called_once()

    def test_revoke_credentials_revoke_fails(self, oauth_service):
        """Test revoke_credentials when revoke API call fails."""
        # Mock file exists
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True

        # Mock credentials that fail to revoke
        mock_credentials = MagicMock()
        mock_credentials.valid = True
        mock_credentials.revoke.side_effect = Exception("Revoke failed")

        oauth_service._load_token = MagicMock(return_value=mock_credentials)

        # Should handle revoke failure gracefully
        oauth_service.revoke_credentials()

        # Should still delete the file
        oauth_service.token_file.unlink.assert_called_once()

    @patch("chronovista.auth.oauth_service.webbrowser")
    @patch("chronovista.auth.oauth_service.Flow")
    def test_authorize_interactive_flow_error(
        self, mock_flow_class, mock_webbrowser, oauth_service
    ):
        """Test authorize_interactive when flow creation fails."""
        # Mock flow creation to raise exception
        mock_flow_class.from_client_config.side_effect = Exception("Flow error")

        with pytest.raises(Exception, match="Flow error"):
            oauth_service.authorize_interactive()

    def test_get_token_info_no_credentials(self, oauth_service):
        """Test get_token_info when no credentials exist."""
        oauth_service._load_token = MagicMock(
            side_effect=FileNotFoundError("No token file")
        )

        result = oauth_service.get_token_info()

        assert result is None

    def test_get_token_info_exception_handling(self, oauth_service):
        """Test get_token_info with exception during loading."""
        # Mock token file exists but _load_token raises exception
        oauth_service.token_file = MagicMock()
        oauth_service.token_file.exists.return_value = True
        oauth_service._load_token = MagicMock(side_effect=Exception("Load error"))

        result = oauth_service.get_token_info()

        # Should return None on exception
        assert result is None

    def test_load_token_file_not_found(self, oauth_service):
        """Test _load_token when file doesn't exist."""
        oauth_service.token_file = Path("/nonexistent/token.json")

        with pytest.raises(FileNotFoundError):
            oauth_service._load_token()

    def test_load_token_invalid_json(self, oauth_service):
        """Test _load_token with invalid JSON."""
        with patch("builtins.open", mock_open(read_data="invalid json")):
            with pytest.raises(Exception):  # JSON decode error
                oauth_service._load_token()

    def test_save_token_file_operations(self, oauth_service):
        """Test _save_token file operations."""
        mock_credentials = MagicMock()
        mock_credentials.token = "test_token"
        mock_credentials.refresh_token = "refresh_token"
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "client_id"
        mock_credentials.client_secret = "client_secret"
        mock_credentials.scopes = ["scope1", "scope2"]
        mock_credentials.expiry = None

        # Mock the file operations
        oauth_service.token_file = MagicMock()

        with patch("builtins.open", mock_open()) as mock_file:
            oauth_service._save_token(mock_credentials)

            # Should call open and chmod
            mock_file.assert_called_once()
            oauth_service.token_file.chmod.assert_called_once_with(0o600)

    def test_is_authenticated_exception_handling(self, oauth_service):
        """Test is_authenticated handles exceptions gracefully."""
        oauth_service._load_token = MagicMock(side_effect=Exception("Load error"))

        result = oauth_service.is_authenticated()

        assert result is False  # Should return False on error


class TestOAuthServicePropertyAccess:
    """Test property access for coverage."""

    def test_property_access(self):
        """Test accessing properties for coverage."""
        service = YouTubeOAuthService()

        # Access properties to ensure they're covered
        assert "web" in service.client_config
        assert "client_id" in service.client_config["web"]
        assert service.token_file.name == "youtube_token.json"
        assert "youtube.readonly" in service.scopes[0]
