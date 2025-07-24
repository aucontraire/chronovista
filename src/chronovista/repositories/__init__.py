"""
Repository layer for data access patterns.

This module provides repository interfaces and implementations following
the Repository pattern for clean separation of domain logic and data persistence.
"""

from .base import BaseRepository, BaseSQLAlchemyRepository
from .channel_repository import ChannelRepository
from .playlist_repository import PlaylistRepository
from .topic_category_repository import TopicCategoryRepository
from .user_language_preference_repository import UserLanguagePreferenceRepository
from .user_video_repository import UserVideoRepository
from .video_localization_repository import VideoLocalizationRepository
from .video_repository import VideoRepository
from .video_tag_repository import VideoTagRepository
from .video_transcript_repository import VideoTranscriptRepository

__all__ = [
    "BaseRepository",
    "BaseSQLAlchemyRepository",
    "ChannelRepository",
    "PlaylistRepository",
    "TopicCategoryRepository",
    "UserLanguagePreferenceRepository",
    "UserVideoRepository",
    "VideoLocalizationRepository",
    "VideoRepository",
    "VideoTagRepository",
    "VideoTranscriptRepository",
]
