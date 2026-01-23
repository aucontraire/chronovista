"""
Repository layer for data access patterns.

This module provides repository interfaces and implementations following
the Repository pattern for clean separation of domain logic and data persistence.
"""

from .base import BaseRepository, BaseSQLAlchemyRepository, IdType
from .channel_repository import ChannelRepository
from .channel_topic_repository import ChannelTopicRepository
from .playlist_membership_repository import PlaylistMembershipRepository
from .playlist_repository import PlaylistRepository
from .topic_category_repository import TopicCategoryRepository
from .user_language_preference_repository import UserLanguagePreferenceRepository
from .user_video_repository import UserVideoRepository
from .video_category_repository import VideoCategoryRepository
from .video_localization_repository import VideoLocalizationRepository
from .video_repository import VideoRepository
from .video_tag_repository import VideoTagRepository
from .video_topic_repository import VideoTopicRepository
from .video_transcript_repository import VideoTranscriptRepository

__all__ = [
    "BaseRepository",
    "BaseSQLAlchemyRepository",
    "IdType",
    "ChannelRepository",
    "ChannelTopicRepository",
    "PlaylistMembershipRepository",
    "PlaylistRepository",
    "TopicCategoryRepository",
    "UserLanguagePreferenceRepository",
    "UserVideoRepository",
    "VideoCategoryRepository",
    "VideoLocalizationRepository",
    "VideoRepository",
    "VideoTagRepository",
    "VideoTopicRepository",
    "VideoTranscriptRepository",
]
