"""
Repository layer for data access patterns.

This module provides repository interfaces and implementations following
the Repository pattern for clean separation of domain logic and data persistence.
"""

from .base import BaseRepository, BaseSQLAlchemyRepository, IdType
from .canonical_tag_repository import CanonicalTagRepository
from .channel_repository import ChannelRepository
from .channel_topic_repository import ChannelTopicRepository
from .entity_alias_repository import EntityAliasRepository
from .named_entity_repository import NamedEntityRepository
from .playlist_membership_repository import PlaylistMembershipRepository
from .playlist_repository import PlaylistRepository
from .tag_alias_repository import TagAliasRepository
from .tag_operation_log_repository import TagOperationLogRepository
from .topic_category_repository import TopicCategoryRepository
from .transcript_segment_repository import TranscriptSegmentRepository
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
    "CanonicalTagRepository",
    "ChannelRepository",
    "ChannelTopicRepository",
    "EntityAliasRepository",
    "NamedEntityRepository",
    "PlaylistMembershipRepository",
    "PlaylistRepository",
    "TagAliasRepository",
    "TagOperationLogRepository",
    "TopicCategoryRepository",
    "TranscriptSegmentRepository",
    "UserLanguagePreferenceRepository",
    "UserVideoRepository",
    "VideoCategoryRepository",
    "VideoLocalizationRepository",
    "VideoRepository",
    "VideoTagRepository",
    "VideoTopicRepository",
    "VideoTranscriptRepository",
]
