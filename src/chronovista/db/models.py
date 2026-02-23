"""
Database models for chronovista.

This module contains SQLAlchemy models for the enhanced multi-language
YouTube analytics database schema.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text
from uuid_utils import uuid7


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

    # Status tracking
    availability_status: Mapped[str] = mapped_column(String(20), default="available")
    recovered_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    recovery_source: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=None
    )
    unavailability_first_detected: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

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
    availability_status: Mapped[str] = mapped_column(String(20), default="available")
    alternative_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None
    )
    recovered_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    recovery_source: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=None
    )
    unavailability_first_detected: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

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

    # Raw transcript data with timestamps (Feature 007)
    raw_transcript_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, comment="Complete raw API response with timestamps"
    )
    has_timestamps: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Whether raw data includes timing information"
    )
    segment_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Number of transcript segments"
    )
    total_duration: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Total transcript duration in seconds"
    )
    source: Mapped[str] = mapped_column(
        String(50), default="youtube_transcript_api", nullable=False,
        comment="Source: youtube_transcript_api, youtube_data_api_v3, manual_upload, unknown"
    )

    # Relationships
    video: Mapped["Video"] = relationship("Video", back_populates="transcripts")
    segments: Mapped[list["TranscriptSegment"]] = relationship(
        "TranscriptSegment",
        back_populates="transcript",
        order_by="TranscriptSegment.sequence_number",
        cascade="all, delete-orphan",
    )


class TranscriptSegment(Base):
    """Individual timed text segment from a video transcript."""

    __tablename__ = "transcript_segments"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Composite foreign key columns
    video_id: Mapped[str] = mapped_column(String(20), nullable=False)
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)

    # Segment content
    text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_correction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timing information
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Composite foreign key constraint and CHECK constraints
    __table_args__ = (
        ForeignKeyConstraint(
            ["video_id", "language_code"],
            ["video_transcripts.video_id", "video_transcripts.language_code"],
            ondelete="CASCADE",
        ),
        CheckConstraint("start_time >= 0", name="chk_segment_start_time_non_negative"),
        CheckConstraint("duration >= 0", name="chk_segment_duration_non_negative"),
        CheckConstraint("sequence_number >= 0", name="chk_segment_sequence_non_negative"),
    )

    # Relationship
    transcript: Mapped["VideoTranscript"] = relationship(
        "VideoTranscript", back_populates="segments"
    )


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

    # Primary key - either YouTube ID (PL prefix, 30-50 chars) or internal (int_ prefix, 36 chars)
    playlist_id: Mapped[str] = mapped_column(String(50), primary_key=True)

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

    # Channel association (nullable to support system playlists)
    channel_id: Mapped[Optional[str]] = mapped_column(
        String(24), ForeignKey("channels.channel_id"), nullable=True
    )

    # Metadata
    video_count: Mapped[int] = mapped_column(Integer, default=0)

    # Playlist creation date from YouTube API
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Status tracking (similar to Video model)
    deleted_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    # Playlist type (for system playlist handling)
    playlist_type: Mapped[str] = mapped_column(
        String(20), default="regular"
    )  # PlaylistType enum value: regular, liked, watch_later, history, favorites

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    channel: Mapped[Optional["Channel"]] = relationship("Channel")
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
        String(50), ForeignKey("playlists.playlist_id", ondelete="CASCADE"), primary_key=True
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


class NamedEntity(Base):
    """Named entities extracted from video tags (people, places, organizations, etc.)."""

    __tablename__ = "named_entities"

    # Primary key
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)

    # Entity identification
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_name_normalized: Mapped[str] = mapped_column(String(500), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_subtype: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # External references (JSONB for flexibility)
    external_ids: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Statistics
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    channel_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Discovery and quality
    discovery_method: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Status and merging
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    merged_into_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("named_entities.id"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint("canonical_name_normalized", "entity_type", name="uq_named_entity_canonical"),
        CheckConstraint(
            "entity_type IN ('person', 'organization', 'place', 'event', 'work', 'technical_term')",
            name="chk_entity_type_valid"
        ),
        CheckConstraint(
            "status IN ('active', 'merged', 'deprecated')",
            name="chk_entity_status_valid"
        ),
        CheckConstraint(
            "discovery_method IN ('manual', 'spacy_ner', 'tag_bootstrap', 'llm_extraction', 'user_created')",
            name="chk_entity_discovery_method_valid"
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="chk_entity_confidence_range"
        ),
    )

    # Relationships
    aliases: Mapped[list["EntityAlias"]] = relationship(
        "EntityAlias", back_populates="entity", cascade="all, delete-orphan"
    )
    canonical_tags: Mapped[list["CanonicalTag"]] = relationship(
        "CanonicalTag", back_populates="entity", foreign_keys="CanonicalTag.entity_id"
    )
    merged_into: Mapped[Optional["NamedEntity"]] = relationship(
        "NamedEntity", remote_side="NamedEntity.id"
    )


class EntityAlias(Base):
    """Alternative names and variations for named entities."""

    __tablename__ = "entity_aliases"

    # Primary key
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)

    # Foreign key to parent entity
    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("named_entities.id", ondelete="CASCADE"), nullable=False
    )

    # Alias information
    alias_name: Mapped[str] = mapped_column(String(500), nullable=False)
    alias_name_normalized: Mapped[str] = mapped_column(String(500), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(30), nullable=False, default="name_variant")

    # Usage statistics
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint("alias_name_normalized", "entity_id", name="uq_entity_alias_name"),
        CheckConstraint(
            "alias_type IN ('name_variant', 'abbreviation', 'nickname', 'asr_error', 'translated_name', 'former_name')",
            name="chk_alias_type_valid"
        ),
    )

    # Relationships
    entity: Mapped["NamedEntity"] = relationship("NamedEntity", back_populates="aliases")


class CanonicalTag(Base):
    """Canonical tag form with normalization and entity linking."""

    __tablename__ = "canonical_tags"

    # Primary key
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)

    # Tag forms
    canonical_form: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_form: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)

    # Statistics
    alias_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Entity linking (optional)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("named_entities.id", ondelete="SET NULL"), nullable=True
    )

    # Status and merging
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    merged_into_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("canonical_tags.id"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('person', 'organization', 'place', 'event', 'work', 'technical_term', 'topic', 'descriptor') OR entity_type IS NULL",
            name="chk_canonical_tag_entity_type_valid"
        ),
        CheckConstraint(
            "status IN ('active', 'merged', 'deprecated')",
            name="chk_canonical_tag_status_valid"
        ),
        CheckConstraint(
            "alias_count >= 1",
            name="chk_canonical_tag_alias_count_positive"
        ),
        CheckConstraint(
            "video_count >= 0",
            name="chk_canonical_tag_video_count_non_negative"
        ),
        CheckConstraint(
            "canonical_form != ''",
            name="chk_canonical_tag_canonical_form_not_empty"
        ),
    )

    # Relationships
    aliases: Mapped[list["TagAlias"]] = relationship(
        "TagAlias", back_populates="canonical_tag", cascade="all, delete-orphan"
    )
    entity: Mapped[Optional["NamedEntity"]] = relationship(
        "NamedEntity", back_populates="canonical_tags", foreign_keys=[entity_id]
    )
    merged_into: Mapped[Optional["CanonicalTag"]] = relationship(
        "CanonicalTag", remote_side="CanonicalTag.id"
    )


class TagAlias(Base):
    """Raw tag forms mapped to their canonical representation."""

    __tablename__ = "tag_aliases"

    # Primary key
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)

    # Tag forms
    raw_form: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    normalized_form: Mapped[str] = mapped_column(String(500), nullable=False)

    # Foreign key to canonical tag
    canonical_tag_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("canonical_tags.id", ondelete="CASCADE"), nullable=False
    )

    # Metadata
    creation_method: Mapped[str] = mapped_column(String(30), nullable=False, default="auto_normalize")
    normalization_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Usage statistics
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Timestamps
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "creation_method IN ('auto_normalize', 'manual_merge', 'backfill', 'api_create')",
            name="chk_tag_alias_creation_method_valid"
        ),
        CheckConstraint(
            "occurrence_count >= 1",
            name="chk_tag_alias_occurrence_count_positive"
        ),
    )

    # Relationships
    canonical_tag: Mapped["CanonicalTag"] = relationship("CanonicalTag", back_populates="aliases")


class TagOperationLog(Base):
    """Audit log for tag normalization and management operations."""

    __tablename__ = "tag_operation_logs"

    # Primary key
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)

    # Operation details
    operation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_canonical_ids: Mapped[List[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    target_canonical_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    affected_alias_ids: Mapped[List[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    # Context and recovery
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    performed_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    performed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    rollback_data: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Rollback tracking
    rolled_back: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rolled_back_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('merge', 'split', 'rename', 'delete', 'create')",
            name="chk_tag_operation_type_valid"
        ),
    )


# Export all models
__all__ = [
    "Base",
    "Channel",
    "VideoCategory",
    "Video",
    "UserLanguagePreference",
    "VideoTranscript",
    "TranscriptSegment",
    "VideoTag",
    "VideoLocalization",
    "ChannelKeyword",
    "TopicCategory",
    "TopicAlias",
    "VideoTopic",
    "ChannelTopic",
    "UserVideo",
    "Playlist",
    "PlaylistMembership",
    "NamedEntity",
    "EntityAlias",
    "CanonicalTag",
    "TagAlias",
    "TagOperationLog",
]
