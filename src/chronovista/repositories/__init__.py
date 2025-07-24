"""
Repository layer for data access patterns.

This module provides repository interfaces and implementations following
the Repository pattern for clean separation of domain logic and data persistence.
"""

from .base import BaseRepository, BaseSQLAlchemyRepository
from .channel_repository import ChannelRepository
from .user_language_preference_repository import UserLanguagePreferenceRepository
from .user_video_repository import UserVideoRepository
from .video_repository import VideoRepository
from .video_transcript_repository import VideoTranscriptRepository

__all__ = [
    "BaseRepository",
    "BaseSQLAlchemyRepository",
    "UserLanguagePreferenceRepository",
    "VideoTranscriptRepository",
    "UserVideoRepository",
    "ChannelRepository",
    "VideoRepository",
]
