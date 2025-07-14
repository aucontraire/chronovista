"""
Authentication module for chronovista.

Handles Google OAuth 2.0 flow, token management, and credential storage
for accessing YouTube Data API.
"""

from __future__ import annotations

from chronovista.auth.oauth_service import YouTubeOAuthService, youtube_oauth

__all__: list[str] = ["YouTubeOAuthService", "youtube_oauth", "get_auth_status"]


def get_auth_status() -> str:
    """Get current authentication status."""
    if youtube_oauth.is_authenticated():
        return "authenticated"
    return "not_authenticated"
