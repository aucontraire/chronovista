"""
Authentication module for chronovista.

Handles Google OAuth 2.0 flow, token management, and credential storage
for accessing YouTube Data API.
"""

from __future__ import annotations

__all__: list[str] = ["get_auth_status"]


def get_auth_status() -> str:
    """Get current authentication status."""
    return "not_authenticated"
