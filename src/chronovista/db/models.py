"""
Database models for chronovista.

This module contains SQLAlchemy models for the enhanced multi-language
YouTube analytics database schema.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class Channel(Base):
    """YouTube channel model with subscription tracking."""

    __tablename__ = "channels"

    # Primary key
    channel_id: Mapped[str] = mapped_column(String(24), primary_key=True)

    # Channel metadata
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    subscriber_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    video_count: Mapped[Optional[int]] = mapped_column(Integer)
    default_language: Mapped[Optional[str]] = mapped_column(
        String(10)
    )  # LanguageCode enum value
    country: Mapped[Optional[str]] = mapped_column(String(2))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Subscription status
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    videos: Mapped[list["Video"]] = relationship("Video", back_populates="channel")
    keywords: Mapped[list["ChannelKeyword"]] = relationship(
        "ChannelKeyword", back_populates="channel"
    )
    channel_topics: Mapped[list["ChannelTopic"]] = relationship(
        "ChannelTopic", back_populates="channel"
    )


class VideoCategory(Base):
    """YouTube video category model."""

    __tablename__ = "video_categories"

    # Primary key
    category_id: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
        comment="YouTube category ID",
    )

    # Category metadata
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Category name",
    )
    assignable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether creators can select this category",
    )

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Record creation timestamp",
    )

    # Relationship to videos
    videos: Mapped[list["Video"]] = relationship("Video", back_populates="category")


class Video(Base):
    """Enhanced video model with language support and content restrictions."""

    __tablename__ = "videos"

    # Primary key
    video_id: Mapped[str] = mapped_column(String(20), primary_key=True)

    # Foreign keys
    channel_id: Mapped[Optional[str]] = mapped_column(
        String(24), ForeignKey("channels.channel_id"), nullable=True
    )
    channel_name_hint: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Original channel name when channel_id is NULL"
    )
    category_id: Mapped[Optional[str]] = mapped_column(
        String(10),
        ForeignKey("video_categories.category_id"),
        nullable=True,
        comment="YouTube video category ID",
    )

    # Video metadata
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    upload_date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # Duration in seconds

    # Content restrictions
    made_for_kids: Mapped[bool] = mapped_column(Boolean, default=False)
    self_declared_made_for_kids: Mapped[bool] = mapped_column(Boolean, default=False)

    # Language support (LanguageCode enum values stored as strings)
    default_language: Mapped[Optional[str]] = mapped_column(
        String(10)
    )  # LanguageCode enum value
    default_audio_language: Mapped[Optional[str]] = mapped_column(
        String(10)
    )  # LanguageCode enum value
    available_languages: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB
    )  # JSONB array of BCP-47 codes

    # Regional and content restrictions
    region_restriction: Mapped[Optional[Dict[str, Union[List[str], str]]]] = (
        mapped_column(JSONB)
    )
    content_rating: Mapped[Optional[Dict[str, str]]] = mapped_column(JSONB)

    # Engagement metrics
    like_count: Mapped[Optional[int]] = mapped_column(Integer)
    view_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    comment_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Status tracking
    deleted_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    channel: Mapped[Optional["Channel"]] = relationship("Channel", back_populates="videos")
    category: Mapped[Optional["VideoCategory"]] = relationship(
        "VideoCategory", back_populates="videos"
    )
    transcripts: Mapped[list["VideoTranscript"]] = relationship(
        "VideoTranscript", back_populates="video"
    )
    tags: Mapped[list["VideoTag"]] = relationship("VideoTag", back_populates="video")
    localizations: Mapped[list["VideoLocalization"]] = relationship(
        "VideoLocalization", back_populates="video"
    )
    user_videos: Mapped[list["UserVideo"]] = relationship(
        "UserVideo", back_populates="video"
    )
    video_topics: Mapped[list["VideoTopic"]] = relationship(
        "VideoTopic", back_populates="video"
    )
    playlist_memberships: Mapped[list["PlaylistMembership"]] = relationship(
        "PlaylistMembership", back_populates="video"
    )


class UserLanguagePreference(Base):
    """User language preferences for content consumption and learning."""

    __tablename__ = "user_language_preferences"

    # Composite primary key
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    language_code: Mapped[str] = mapped_column(
        String(10), primary_key=True
    )  # LanguageCode enum value

    # Preference details
    preference_type: Mapped[str] = mapped_column(
        String(20)
    )  # FLUENT, LEARNING, INTERESTED
    priority: Mapped[int] = mapped_column(Integer)
    auto_download_transcripts: Mapped[bool] = mapped_column(Boolean, default=False)
    learning_goal: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VideoTranscript(Base):
    """Multi-language video transcripts with quality indicators."""

    __tablename__ = "video_transcripts"

    # Composite primary key
    video_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("videos.video_id"), primary_key=True
    )
    language_code: Mapped[str] = mapped_column(
        String(10), primary_key=True
    )  # LanguageCode enum value

    # Transcript content
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Transcript metadata
    transcript_type: Mapped[str] = mapped_column(String(20))  # AUTO, MANUAL, TRANSLATED
    download_reason: Mapped[str] = mapped_column(
        String(30)
    )  # USER_REQUEST, AUTO_PREFERRED, LEARNING_LANGUAGE
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)

    # Quality indicators
    is_cc: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # Closed captions (higher quality)
    is_auto_synced: Mapped[bool] = mapped_column(
        Boolean, default=True
    )  # Auto-generated flag
    track_kind: Mapped[str] = mapped_column(
        String(20), default="standard"
    )  # standard, ASR, forced
    caption_name: Mapped[Optional[str]] = mapped_column(
        String(255)
    )  # Caption track name/description

    # Timestamps
    downloaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    video: Mapped["Video"] = relationship("Video", back_populates="transcripts")


class VideoTag(Base):
    """Video-level tags for content analysis."""

    __tablename__ = "video_tags"

    # Composite primary key
    video_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("videos.video_id"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(500), primary_key=True)

    # Tag metadata
    tag_order: Mapped[Optional[int]] = mapped_column(Integer)  # Order from YouTube API

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    video: Mapped["Video"] = relationship("Video", back_populates="tags")


class VideoLocalization(Base):
    """Multi-language video content variants."""

    __tablename__ = "video_localizations"

    # Composite primary key
    video_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("videos.video_id"), primary_key=True
    )
    language_code: Mapped[str] = mapped_column(
        String(10), primary_key=True
    )  # LanguageCode enum value

    # Localized content
    localized_title: Mapped[str] = mapped_column(Text, nullable=False)
    localized_description: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    video: Mapped["Video"] = relationship("Video", back_populates="localizations")


class ChannelKeyword(Base):
    """Channel keywords for topic analysis."""

    __tablename__ = "channel_keywords"

    # Composite primary key
    channel_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("channels.channel_id"), primary_key=True
    )
    keyword: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Keyword metadata
    keyword_order: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # Order from channel branding

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel", back_populates="keywords")


class TopicCategory(Base):
    """YouTube topic classification system with dynamic resolution support."""

    __tablename__ = "topic_categories"

    # Primary key
    topic_id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Topic metadata
    category_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_topic_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("topic_categories.topic_id")
    )
    topic_type: Mapped[str] = mapped_column(
        String(20), default="youtube"
    )  # youtube, custom

    # Dynamic topic resolution fields (Option 4 implementation)
    wikipedia_url: Mapped[Optional[str]] = mapped_column(
        String(500), unique=True, nullable=True
    )  # Full Wikipedia URL from YouTube API
    normalized_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # Lowercase, no underscores for matching
    source: Mapped[str] = mapped_column(
        String(20), default="seeded", nullable=False
    )  # 'seeded' or 'dynamic'
    last_seen_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Last time seen in API response
    occurrence_count: Mapped[int] = mapped_column(
        Integer, default=1
    )  # How many times seen

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Self-referential relationship for hierarchical topics
    children: Mapped[list["TopicCategory"]] = relationship(
        "TopicCategory", back_populates="parent"
    )
    parent: Mapped[Optional["TopicCategory"]] = relationship(
        "TopicCategory", back_populates="children", remote_side="TopicCategory.topic_id"
    )

    # Junction table relationships
    video_topics: Mapped[list["VideoTopic"]] = relationship(
        "VideoTopic", back_populates="topic_category"
    )
    channel_topics: Mapped[list["ChannelTopic"]] = relationship(
        "ChannelTopic", back_populates="topic_category"
    )
    aliases: Mapped[list["TopicAlias"]] = relationship(
        "TopicAlias", back_populates="topic_category", cascade="all, delete-orphan"
    )


class TopicAlias(Base):
    """Alias mappings for topic name variations (spelling, redirects, synonyms)."""

    __tablename__ = "topic_aliases"

    # Primary key - the alias itself (e.g., "humour")
    alias: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Foreign key to the canonical topic
    topic_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("topic_categories.topic_id", ondelete="CASCADE"),
        nullable=False
    )

    # Alias type for categorization
    alias_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'spelling', 'redirect', 'synonym'

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationship back to topic
    topic_category: Mapped["TopicCategory"] = relationship(
        "TopicCategory", back_populates="aliases"
    )


class VideoTopic(Base):
    """Video-topic relationships for content classification."""

    __tablename__ = "video_topics"

    # Composite primary key
    video_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("videos.video_id"), primary_key=True
    )
    topic_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("topic_categories.topic_id"), primary_key=True
    )

    # Relationship metadata
    relevance_type: Mapped[str] = mapped_column(
        String(20), default="primary"
    )  # primary, relevant, suggested

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    video: Mapped["Video"] = relationship("Video", back_populates="video_topics")
    topic_category: Mapped["TopicCategory"] = relationship(
        "TopicCategory", back_populates="video_topics"
    )


class ChannelTopic(Base):
    """Channel-topic relationships for channel classification."""

    __tablename__ = "channel_topics"

    # Composite primary key
    channel_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("channels.channel_id"), primary_key=True
    )
    topic_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("topic_categories.topic_id"), primary_key=True
    )

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    channel: Mapped["Channel"] = relationship(
        "Channel", back_populates="channel_topics"
    )
    topic_category: Mapped["TopicCategory"] = relationship(
        "TopicCategory", back_populates="channel_topics"
    )


class UserVideo(Base):
    """User interaction tracking with videos."""

    __tablename__ = "user_videos"

    # Composite primary key
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    video_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("videos.video_id"), primary_key=True
    )

    # Interaction metadata
    watched_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    rewatch_count: Mapped[int] = mapped_column(Integer, default=0)

    # User actions
    liked: Mapped[bool] = mapped_column(Boolean, default=False)
    saved_to_playlist: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    video: Mapped["Video"] = relationship("Video", back_populates="user_videos")


class Playlist(Base):
    """Enhanced playlists with language support."""

    __tablename__ = "playlists"

    # Primary key
    playlist_id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # YouTube ID linking (for real YouTube playlists)
    youtube_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
        comment="Real YouTube playlist ID for linking (PL prefix, 30-50 chars)",
    )

    # Playlist metadata
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Language and privacy (LanguageCode enum values stored as strings)
    default_language: Mapped[Optional[str]] = mapped_column(
        String(10)
    )  # LanguageCode enum value
    privacy_status: Mapped[str] = mapped_column(
        String(20), default="private"
    )  # private, public, unlisted

    # Channel association
    channel_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("channels.channel_id")
    )

    # Metadata
    video_count: Mapped[int] = mapped_column(Integer, default=0)

    # Playlist creation date from YouTube API
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Status tracking (similar to Video model)
    deleted_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel")
    memberships: Mapped[list["PlaylistMembership"]] = relationship(
        "PlaylistMembership",
        back_populates="playlist",
        order_by="PlaylistMembership.position",
    )


class PlaylistMembership(Base):
    """Playlist-video relationships with position tracking."""

    __tablename__ = "playlist_memberships"

    # Composite primary key
    playlist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("playlists.playlist_id", ondelete="CASCADE"), primary_key=True
    )
    video_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("videos.video_id", ondelete="CASCADE"), primary_key=True
    )

    # Position in playlist (critical for playlist ordering)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Metadata from takeout
    added_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    playlist: Mapped["Playlist"] = relationship(
        "Playlist", back_populates="memberships"
    )
    video: Mapped["Video"] = relationship(
        "Video", back_populates="playlist_memberships"
    )


# Export all models
__all__ = [
    "Base",
    "Channel",
    "VideoCategory",
    "Video",
    "UserLanguagePreference",
    "VideoTranscript",
    "VideoTag",
    "VideoLocalization",
    "ChannelKeyword",
    "TopicCategory",
    "VideoTopic",
    "ChannelTopic",
    "UserVideo",
    "Playlist",
    "PlaylistMembership",
]
