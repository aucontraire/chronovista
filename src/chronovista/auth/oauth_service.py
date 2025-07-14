"""
YouTube OAuth 2.0 authentication service.

Handles the complete OAuth flow including authorization URL generation,
token exchange, token storage and refresh, and credential management.
"""

from __future__ import annotations

import json
import secrets
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import os

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from chronovista.config.settings import settings

# Allow insecure transport for localhost development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


class YouTubeOAuthService:
    """
    YouTube OAuth 2.0 authentication service.
    
    Provides methods for authenticating with YouTube API using OAuth 2.0,
    managing tokens, and building authenticated API clients.
    """

    def __init__(self) -> None:
        """Initialize the OAuth service."""
        self.scopes = [
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ]
        
        # Create OAuth client configuration from environment variables
        self.client_config = {
            "web": {
                "client_id": settings.youtube_client_id,
                "client_secret": settings.youtube_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": [settings.oauth_redirect_uri],
            }
        }
        
        # Ensure data directory exists for token storage
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.token_file = settings.data_dir / "youtube_token.json"

    def get_authorization_url(self) -> tuple[str, str]:
        """
        Generate authorization URL for OAuth flow.
        
        Returns
        -------
        tuple[str, str]
            A tuple containing (authorization_url, state) where state
            should be stored for verification during callback.
        """
        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.scopes,
            redirect_uri=settings.oauth_redirect_uri,
        )
        
        # Generate a secure random state parameter
        state = secrets.token_urlsafe(32)
        
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state,
            prompt="consent",  # Force consent screen to ensure refresh token
        )
        
        return authorization_url, state

    def authorize_from_callback(self, authorization_response: str, expected_state: str) -> dict[str, Any]:
        """
        Complete OAuth flow using authorization callback response.
        
        Parameters
        ----------
        authorization_response : str
            The full callback URL received from OAuth provider
        expected_state : str
            The state parameter that was sent in authorization request
            
        Returns
        -------
        dict[str, Any]
            Token information including access_token, refresh_token, etc.
            
        Raises
        ------
        ValueError
            If state parameter doesn't match or authorization was denied
        """
        # Parse the callback URL
        parsed_url = urlparse(authorization_response)
        query_params = parse_qs(parsed_url.query)
        
        # Verify state parameter
        received_state = query_params.get("state", [None])[0]
        if received_state != expected_state:
            raise ValueError("Invalid state parameter. Possible CSRF attack.")
        
        # Check for authorization denial
        if "error" in query_params:
            error = query_params.get("error", ["unknown"])[0]
            raise ValueError(f"Authorization denied: {error}")
        
        # Create flow and fetch token
        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.scopes,
            redirect_uri=settings.oauth_redirect_uri,
            state=expected_state,
        )
        
        flow.fetch_token(authorization_response=authorization_response)
        
        # Save credentials to file
        credentials = flow.credentials
        self._save_token(credentials)
        
        return {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expires_in": credentials.expiry.timestamp() if credentials.expiry else None,
            "scope": " ".join(credentials.scopes) if credentials.scopes else "",
        }

    def authorize_interactive(self) -> dict[str, Any]:
        """
        Perform interactive OAuth authorization.
        
        Opens browser for user authorization and waits for manual callback entry.
        
        Returns
        -------
        dict[str, Any]
            Token information including access_token, refresh_token, etc.
        """
        authorization_url, state = self.get_authorization_url()
        
        print("🔐 Opening browser for YouTube authorization...")
        print(f"If browser doesn't open, visit: {authorization_url}")
        
        # Open browser
        webbrowser.open(authorization_url)
        
        # Wait for user to complete authorization and paste callback URL
        print("\n📋 After authorizing, copy the full callback URL and paste it here:")
        callback_url = input("Callback URL: ").strip()
        
        return self.authorize_from_callback(callback_url, state)

    def is_authenticated(self) -> bool:
        """
        Check if user is currently authenticated.
        
        Returns
        -------
        bool
            True if valid credentials exist, False otherwise
        """
        if not self.token_file.exists():
            return False
        
        try:
            credentials = self._load_token()
            return credentials.valid or credentials.refresh_token is not None
        except Exception:
            return False

    def get_authenticated_service(self):
        """
        Get authenticated YouTube API service client.
        
        Returns
        -------
        googleapiclient.discovery.Resource
            Authenticated YouTube Data API v3 service client
            
        Raises
        ------
        ValueError
            If no valid credentials are available
        """
        if not self.is_authenticated():
            raise ValueError("Not authenticated. Run authentication flow first.")
        
        credentials = self._load_token()
        
        # Refresh token if needed
        if not credentials.valid and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self._save_token(credentials)
            except RefreshError as e:
                raise ValueError(f"Failed to refresh credentials: {e}")
        
        if not credentials.valid:
            raise ValueError("Credentials are invalid and cannot be refreshed.")
        
        return build("youtube", "v3", credentials=credentials)

    def revoke_credentials(self) -> None:
        """
        Revoke stored credentials and delete token file.
        
        This will require re-authentication for future API calls.
        """
        if self.token_file.exists():
            try:
                credentials = self._load_token()
                if credentials.valid:
                    # Attempt to revoke the token
                    credentials.revoke(Request())
            except Exception:
                # Continue with deletion even if revocation fails
                pass
            
            # Delete the token file
            self.token_file.unlink()

    def get_token_info(self) -> dict[str, Any] | None:
        """
        Get information about stored token.
        
        Returns
        -------
        dict[str, Any] | None
            Token information or None if no token exists
        """
        if not self.token_file.exists():
            return None
        
        try:
            credentials = self._load_token()
            return {
                "valid": credentials.valid,
                "expired": credentials.expired,
                "has_refresh_token": credentials.refresh_token is not None,
                "scopes": list(credentials.scopes) if credentials.scopes else [],
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
            }
        except Exception:
            return None

    def _save_token(self, credentials) -> None:
        """Save credentials to token file."""
        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes) if credentials.scopes else [],
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }
        
        with open(self.token_file, "w") as f:
            json.dump(token_data, f, indent=2)
        
        # Set restrictive permissions on token file
        self.token_file.chmod(0o600)

    def _load_token(self):
        """Load credentials from token file."""
        from google.oauth2.credentials import Credentials
        from datetime import datetime
        
        with open(self.token_file) as f:
            token_data = json.load(f)
        
        # Parse expiry time if available
        expiry = None
        if token_data.get("expiry"):
            try:
                expiry = datetime.fromisoformat(token_data["expiry"].replace('Z', '+00:00'))
            except (ValueError, TypeError):
                pass
        
        return Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
            expiry=expiry,
        )


# Global OAuth service instance
youtube_oauth = YouTubeOAuthService()