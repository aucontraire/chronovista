"""
Services module for chronovista.

Contains business logic services for authentication, YouTube API interaction,
transcript processing, and data export functionality.
"""

from __future__ import annotations

from chronovista.services.youtube_service import YouTubeService, youtube_service

__all__: list[str] = ["YouTubeService", "youtube_service", "get_service_count"]


def get_service_count() -> int:
    """Get number of available services."""
    return 1
