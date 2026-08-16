"""
Database models for chronovista.

This module contains SQLAlchemy models for the enhanced multi-language
YouTube analytics database schema.
"""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)

# First ARRAY columns in this schema (ADR-011 fields_written). JSONB is the
# house pattern for structured columns, but a flat list of column names is
# what a Postgres array is for, and it queries with = ANY(...) directly.
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text
from uuid_utils import uuid7

from chronovista.models.enums import TagOperationType

# `TranscriptSegment` declares a column named `text`, which shadows the imported
# `text()` inside that class body. This alias is how its `__table_args__` reach
# the SQL construct; everywhere else `text` is unambiguous.
sql_text = text


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# The GIN trigram indexes declared below use the `gin_trgm_ops` operator class,
# which only exists once `pg_trgm` is installed. Migrations create the extension
# (052, 056), but `create_all()` does not run migrations — so without this hook a
# schema built straight from the ORM fails with:
#
#     operator class "gin_trgm_ops" does not exist for access method "gin"
#
# Registered on the metadata rather than at each call site: `create_all()` is
# invoked from the app, the integration conftests and the model unit tests, and
# any future caller would hit the same wall. Guarded on the dialect so the
# SQLite path used by some model tests is untouched.
@event.listens_for(Base.metadata, "before_create")
def _ensure_pg_trgm(target: Any, connection: Any, **kwargs: Any) -> None:
    """Install `pg_trgm` before `create_all()` builds the GIN trigram indexes."""
    if connection.dialect.name == "postgresql":
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))


class Channel(Base):
    """YouTube channel model with subscription tracking."""

    __tablename__ = "channels"

    # Primary key
    channel_id: Mapped[str] = mapped_column(String(24), primary_key=True)

    # Channel metadata
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    subscriber_count: Mapped[int | None] = mapped_column(BigInteger)
    video_count: Mapped[int | None] = mapped_column(Integer)
    default_language: Mapped[str | None] = mapped_column(
        String(10)
    )  # LanguageCode enum value
    country: Mapped[str | None] = mapped_column(String(2))
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))

    # Subscription status
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Status tracking
    availability_status: Mapped[str] = mapped_column(String(20), default="available")
    recovered_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    recovery_source: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    unavailability_first_detected: Mapped[datetime.datetime | None] = mapped_column(
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
    videos: Mapped[list[Video]] = relationship("Video", back_populates="channel")
    keywords: Mapped[list[ChannelKeyword]] = relationship(
        "ChannelKeyword", back_populates="channel"
    )
    channel_topics: Mapped[list[ChannelTopic]] = relationship(
        "ChannelTopic", back_populates="channel"
    )

    # Table indexes (declared so autogenerate round-trips them)
    __table_args__ = (
        Index("idx_channels_availability_status", "availability_status"),
        Index(
            "idx_channels_needs_enrichment",
            "channel_id",
            postgresql_where=text("subscriber_count IS NULL"),
        ),
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
    videos: Mapped[list[Video]] = relationship("Video", back_populates="category")


class Video(Base):
    """Enhanced video model with language support and content restrictions."""

    __tablename__ = "videos"

    # Primary key
    video_id: Mapped[str] = mapped_column(String(20), primary_key=True)

    # Foreign keys
    channel_id: Mapped[str | None] = mapped_column(
        String(24), ForeignKey("channels.channel_id"), nullable=True
    )
    channel_name_hint: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Original channel name when channel_id is NULL",
    )
    category_id: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey("video_categories.category_id"),
        nullable=True,
        comment="YouTube video category ID",
    )

    # Video metadata
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
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
    default_language: Mapped[str | None] = mapped_column(
        String(10)
    )  # LanguageCode enum value
    default_audio_language: Mapped[str | None] = mapped_column(
        String(10)
    )  # LanguageCode enum value
    available_languages: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB
    )  # JSONB array of BCP-47 codes

    # Regional and content restrictions
    region_restriction: Mapped[dict[str, list[str] | str] | None] = mapped_column(JSONB)
    content_rating: Mapped[dict[str, str] | None] = mapped_column(JSONB)

    # Engagement metrics
    like_count: Mapped[int | None] = mapped_column(Integer)
    view_count: Mapped[int | None] = mapped_column(BigInteger)
    comment_count: Mapped[int | None] = mapped_column(Integer)

    # Status tracking
    availability_status: Mapped[str] = mapped_column(String(20), default="available")
    alternative_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, default=None
    )
    recovered_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    recovery_source: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    unavailability_first_detected: Mapped[datetime.datetime | None] = mapped_column(
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
    channel: Mapped[Channel | None] = relationship("Channel", back_populates="videos")
    category: Mapped[VideoCategory | None] = relationship(
        "VideoCategory", back_populates="videos"
    )
    transcripts: Mapped[list[VideoTranscript]] = relationship(
        "VideoTranscript", back_populates="video"
    )
    tags: Mapped[list[VideoTag]] = relationship("VideoTag", back_populates="video")
    localizations: Mapped[list[VideoLocalization]] = relationship(
        "VideoLocalization", back_populates="video"
    )
    user_videos: Mapped[list[UserVideo]] = relationship(
        "UserVideo", back_populates="video"
    )
    video_topics: Mapped[list[VideoTopic]] = relationship(
        "VideoTopic", back_populates="video"
    )
    playlist_memberships: Mapped[list[PlaylistMembership]] = relationship(
        "PlaylistMembership", back_populates="video"
    )

    # Table indexes (declared so autogenerate round-trips them)
    __table_args__ = (
        Index("idx_videos_availability_status", "availability_status"),
        Index("idx_videos_category_id", "category_id"),
        Index(
            "idx_videos_channel_hint",
            "channel_name_hint",
            postgresql_where=text(
                "channel_id IS NULL AND channel_name_hint IS NOT NULL"
            ),
        ),
        Index(
            "idx_videos_null_channel",
            "video_id",
            postgresql_where=text("channel_id IS NULL"),
        ),
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
    learning_goal: Mapped[str | None] = mapped_column(Text)

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
    confidence_score: Mapped[float | None] = mapped_column(Float)

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
    caption_name: Mapped[str | None] = mapped_column(
        String(255)
    )  # Caption track name/description

    # Timestamps
    downloaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Raw transcript data with timestamps (Feature 007)
    raw_transcript_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="Complete raw API response with timestamps"
    )
    has_timestamps: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether raw data includes timing information",
    )
    segment_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Number of transcript segments"
    )
    total_duration: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Total transcript duration in seconds"
    )
    source: Mapped[str] = mapped_column(
        String(50),
        default="youtube_transcript_api",
        nullable=False,
        comment="Source: youtube_transcript_api, youtube_data_api_v3, manual_upload, unknown",
    )

    # Correction metadata (Feature 033)
    has_corrections: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default=text("false"),
        comment="Whether any segment has active corrections",
    )
    last_corrected_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent correction",
    )
    correction_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        server_default=text("0"),
        comment="Count of active (non-reverted) corrections",
    )

    # Relationships
    video: Mapped[Video] = relationship("Video", back_populates="transcripts")
    segments: Mapped[list[TranscriptSegment]] = relationship(
        "TranscriptSegment",
        back_populates="transcript",
        order_by="TranscriptSegment.sequence_number",
        cascade="all, delete-orphan",
    )
    corrections: Mapped[list[TranscriptCorrection]] = relationship(
        "TranscriptCorrection",
        back_populates="transcript",
        order_by="TranscriptCorrection.corrected_at.desc()",
    )

    # Table indexes (declared so autogenerate round-trips them)
    __table_args__ = (
        Index(
            "ix_video_transcripts_has_timestamps_true",
            "has_timestamps",
            postgresql_where=text("has_timestamps = true"),
        ),
        Index("ix_video_transcripts_segment_count", "segment_count"),
        Index("ix_video_transcripts_source", "source"),
        Index("ix_video_transcripts_total_duration", "total_duration"),
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
    corrected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        CheckConstraint(
            "sequence_number >= 0", name="chk_segment_sequence_non_negative"
        ),
        Index(
            "idx_segments_corrected_text_trgm",
            "corrected_text",
            postgresql_using="gin",
            postgresql_ops={"corrected_text": "gin_trgm_ops"},
            postgresql_where=sql_text("corrected_text IS NOT NULL"),
        ),
        Index(
            "idx_segments_text_trgm",
            "text",
            postgresql_using="gin",
            postgresql_ops={"text": "gin_trgm_ops"},
        ),
        Index(
            "idx_transcript_segments_corrected",
            "video_id",
            "language_code",
            "has_correction",
        ),
        Index(
            "idx_transcript_segments_lookup", "video_id", "language_code", "start_time"
        ),
        Index(
            "idx_transcript_segments_time_range",
            "video_id",
            "language_code",
            "start_time",
            "end_time",
        ),
    )

    # Relationships
    transcript: Mapped[VideoTranscript] = relationship(
        "VideoTranscript", back_populates="segments"
    )
    entity_mentions: Mapped[list[EntityMention]] = relationship(
        "EntityMention", back_populates="segment", lazy="select"
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
    tag_order: Mapped[int | None] = mapped_column(Integer)  # Order from YouTube API

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    video: Mapped[Video] = relationship("Video", back_populates="tags")

    # Table indexes (declared so autogenerate round-trips them)
    __table_args__ = (Index("idx_video_tags_tag", "tag"),)


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
    localized_description: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    video: Mapped[Video] = relationship("Video", back_populates="localizations")


class ChannelKeyword(Base):
    """Channel keywords for topic analysis."""

    __tablename__ = "channel_keywords"

    # Composite primary key
    channel_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("channels.channel_id"), primary_key=True
    )
    keyword: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Keyword metadata
    keyword_order: Mapped[int | None] = mapped_column(
        Integer
    )  # Order from channel branding

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    channel: Mapped[Channel] = relationship("Channel", back_populates="keywords")


class TopicCategory(Base):
    """YouTube topic classification system with dynamic resolution support."""

    __tablename__ = "topic_categories"

    # Primary key
    topic_id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Topic metadata
    category_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_topic_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("topic_categories.topic_id")
    )
    topic_type: Mapped[str] = mapped_column(
        String(20), default="youtube"
    )  # youtube, custom

    # Dynamic topic resolution fields (Option 4 implementation)
    # Uniqueness comes from the partial unique index in __table_args__
    # (idx_topic_categories_wikipedia_url, WHERE wikipedia_url IS NOT NULL),
    # which is what the migrations actually build. `unique=True` here would
    # additionally declare a UNIQUE *constraint* that no migration created.
    wikipedia_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Full Wikipedia URL (e.g., https://en.wikipedia.org/wiki/Music)",
    )
    normalized_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Lowercase category name with no underscores for lookups",
    )
    source: Mapped[str] = mapped_column(
        String(20),
        default="seeded",
        nullable=False,
        comment="Origin of topic: 'seeded' or 'dynamic'",
    )
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time this topic was seen in API response",
    )
    occurrence_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        comment="Number of times this topic has been encountered",
    )

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Self-referential relationship for hierarchical topics
    children: Mapped[list[TopicCategory]] = relationship(
        "TopicCategory", back_populates="parent"
    )
    parent: Mapped[TopicCategory | None] = relationship(
        "TopicCategory", back_populates="children", remote_side="TopicCategory.topic_id"
    )

    # Junction table relationships
    video_topics: Mapped[list[VideoTopic]] = relationship(
        "VideoTopic", back_populates="topic_category"
    )
    channel_topics: Mapped[list[ChannelTopic]] = relationship(
        "ChannelTopic", back_populates="topic_category"
    )
    aliases: Mapped[list[TopicAlias]] = relationship(
        "TopicAlias", back_populates="topic_category", cascade="all, delete-orphan"
    )

    # Table indexes (declared so autogenerate round-trips them)
    __table_args__ = (
        Index("idx_topic_categories_normalized_name", "normalized_name"),
        Index("idx_topic_categories_source", "source"),
        Index(
            "idx_topic_categories_wikipedia_url",
            "wikipedia_url",
            unique=True,
            postgresql_where=text("wikipedia_url IS NOT NULL"),
        ),
    )


class TopicAlias(Base):
    """Alias mappings for topic name variations (spelling, redirects, synonyms)."""

    __tablename__ = "topic_aliases"

    # Primary key - the alias itself (e.g., "humour")
    alias: Mapped[str] = mapped_column(
        String(255), primary_key=True, comment="Alias name (e.g., 'humour')"
    )

    # Foreign key to the canonical topic
    topic_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("topic_categories.topic_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to canonical topic",
    )

    # Alias type for categorization
    alias_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type: 'spelling', 'redirect', or 'synonym'",
    )

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="When this alias was created",
    )

    # Relationship back to topic
    topic_category: Mapped[TopicCategory] = relationship(
        "TopicCategory", back_populates="aliases"
    )

    # Table indexes (declared so autogenerate round-trips them)
    __table_args__ = (Index("idx_topic_aliases_topic_id", "topic_id"),)


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
    video: Mapped[Video] = relationship("Video", back_populates="video_topics")
    topic_category: Mapped[TopicCategory] = relationship(
        "TopicCategory", back_populates="video_topics"
    )

    # Table indexes (declared so autogenerate round-trips them)
    __table_args__ = (Index("idx_video_topics_topic_id", "topic_id"),)


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
    channel: Mapped[Channel] = relationship("Channel", back_populates="channel_topics")
    topic_category: Mapped[TopicCategory] = relationship(
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
    watched_at: Mapped[datetime.datetime | None] = mapped_column(
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
    video: Mapped[Video] = relationship("Video", back_populates="user_videos")

    __table_args__ = (
        # The primary key is (user_id, video_id), so a lookup keyed on
        # video_id alone cannot use it — the leading column is absent from the
        # predicate. The playlist detail page batch-loads the watched flag for
        # its current page with `WHERE video_id IN (...)`, which therefore
        # seq-scanned the whole table to resolve at most 100 ids.
        #
        # Feature 060 sharpened this: it collapsed watch history to a single
        # identity, so `user_id` now has cardinality 1 and the primary key
        # discriminates nothing at all.
        Index("ix_user_videos_video_id", "video_id"),
    )


class AppIdentity(Base):
    """Singleton row holding the canonical local-user identity (Feature 060).

    Only one row ever exists (enforced by ``CHECK (id = 1)``). It records the
    resolved ``user_id`` and how it was resolved (``source``), so every writer
    and reader of user-scoped data can obtain a single, persisted identity
    instead of deriving one from ambient auth state.
    """

    __tablename__ = "app_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Explicit, named constraint so create_all() (test schema) and the Alembic
    # migration produce the same constraint name (uq_app_identities_user_id).
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_app_identities_user_id"),
        CheckConstraint("id = 1", name="chk_app_identities_singleton"),
    )


class Playlist(Base):
    """Enhanced playlists with language support."""

    __tablename__ = "playlists"

    # Primary key - either YouTube ID (PL prefix, 30-50 chars) or internal (int_ prefix, 36 chars)
    playlist_id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Playlist metadata
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Language and privacy (LanguageCode enum values stored as strings)
    default_language: Mapped[str | None] = mapped_column(
        String(10)
    )  # LanguageCode enum value
    privacy_status: Mapped[str] = mapped_column(
        String(20), default="private"
    )  # private, public, unlisted

    # Channel association (nullable to support system playlists)
    channel_id: Mapped[str | None] = mapped_column(
        String(24), ForeignKey("channels.channel_id"), nullable=True
    )

    # Metadata
    video_count: Mapped[int] = mapped_column(Integer, default=0)

    # Playlist creation date from YouTube API
    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Status tracking (similar to Video model)
    deleted_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    # Set when an enrichment run first fails to find this playlist; a second
    # consecutive miss is what actually sets deleted_flag. Videos have carried
    # the identically named column since the availability_status migration;
    # playlists were left without it, which is why one bad run could hide the
    # whole library (#149).
    unavailability_first_detected: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Playlist type (for system playlist handling)
    playlist_type: Mapped[str] = mapped_column(
        String(20),
        default="regular",
        comment="PlaylistType enum: regular, liked, watch_later, history, favorites",
    )

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    channel: Mapped[Channel | None] = relationship("Channel")
    memberships: Mapped[list[PlaylistMembership]] = relationship(
        "PlaylistMembership",
        back_populates="playlist",
        order_by="PlaylistMembership.position",
    )


class PlaylistMembership(Base):
    """Playlist-video relationships with position tracking."""

    __tablename__ = "playlist_memberships"

    # Composite primary key
    playlist_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("playlists.playlist_id", ondelete="CASCADE"),
        primary_key=True,
    )
    video_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("videos.video_id", ondelete="CASCADE"), primary_key=True
    )

    # Position in playlist (critical for playlist ordering)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Metadata from takeout
    added_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    playlist: Mapped[Playlist] = relationship("Playlist", back_populates="memberships")
    video: Mapped[Video] = relationship("Video", back_populates="playlist_memberships")


class NamedEntity(Base):
    """Named entities extracted from video tags (people, places, organizations, etc.)."""

    __tablename__ = "named_entities"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )

    # Entity identification
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_name_normalized: Mapped[str] = mapped_column(String(500), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_subtype: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # External references (JSONB for flexibility)
    external_ids: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Exclusion patterns for entity mention detection
    exclusion_patterns: Mapped[list[Any]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), nullable=False
    )

    # Statistics
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Discovery and quality
    discovery_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="manual"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Status and merging
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    merged_into_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("named_entities.id"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "canonical_name_normalized", "entity_type", name="uq_named_entity_canonical"
        ),
        CheckConstraint(
            "entity_type IN ('person', 'organization', 'place', 'event', 'work', 'technical_term', 'concept', 'other')",
            name="chk_entity_type_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'merged', 'deprecated')",
            name="chk_entity_status_valid",
        ),
        CheckConstraint(
            "discovery_method IN ('manual', 'spacy_ner', 'tag_bootstrap', 'llm_extraction', 'user_created')",
            name="chk_entity_discovery_method_valid",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="chk_entity_confidence_range",
        ),
        Index("idx_named_entities_normalized", "canonical_name_normalized"),
        Index("idx_named_entities_status", "status"),
        Index("idx_named_entities_type", "entity_type"),
    )

    # Relationships
    aliases: Mapped[list[EntityAlias]] = relationship(
        "EntityAlias", back_populates="entity", cascade="all, delete-orphan"
    )
    canonical_tags: Mapped[list[CanonicalTag]] = relationship(
        "CanonicalTag", back_populates="entity", foreign_keys="CanonicalTag.entity_id"
    )
    merged_into: Mapped[NamedEntity | None] = relationship(
        "NamedEntity", remote_side="NamedEntity.id"
    )
    mentions: Mapped[list[EntityMention]] = relationship(
        "EntityMention", back_populates="entity", lazy="select"
    )


class EntityAlias(Base):
    """Alternative names and variations for named entities."""

    __tablename__ = "entity_aliases"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )

    # Foreign key to parent entity
    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("named_entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Alias information
    alias_name: Mapped[str] = mapped_column(String(500), nullable=False)
    alias_name_normalized: Mapped[str] = mapped_column(String(500), nullable=False)
    alias_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="name_variant"
    )

    # Matching behaviour. False (the default, and every alias historically)
    # means case-insensitive. True restricts this one alias to the exact
    # casing in alias_name — for aliases that collide with an ordinary word.
    case_sensitive: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment=(
            "When true, this alias matches only the exact casing stored in "
            "alias_name. Defaults to false (case-insensitive), which is the "
            "historical behaviour for every alias."
        ),
    )

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
        UniqueConstraint(
            "alias_name_normalized", "entity_id", name="uq_entity_alias_name"
        ),
        CheckConstraint(
            "alias_type IN ('name_variant', 'abbreviation', 'nickname', 'asr_error', 'translated_name', 'former_name')",
            name="chk_alias_type_valid",
        ),
        Index("idx_entity_aliases_entity_id", "entity_id"),
        Index("idx_entity_aliases_normalized", "alias_name_normalized"),
        Index("idx_entity_aliases_type", "alias_type"),
    )

    # Relationships
    entity: Mapped[NamedEntity] = relationship("NamedEntity", back_populates="aliases")


class CanonicalTag(Base):
    """Canonical tag form with normalization and entity linking."""

    __tablename__ = "canonical_tags"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )

    # Tag forms
    canonical_form: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_form: Mapped[str] = mapped_column(
        String(500), nullable=False, unique=True
    )

    # Statistics
    alias_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Entity linking (optional)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("named_entities.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status and merging
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    merged_into_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("canonical_tags.id"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('person', 'organization', 'place', 'event', 'work', 'technical_term', 'concept', 'other', 'topic', 'descriptor') OR entity_type IS NULL",
            name="chk_canonical_tag_entity_type_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'merged', 'deprecated')",
            name="chk_canonical_tag_status_valid",
        ),
        CheckConstraint(
            "alias_count >= 0", name="chk_canonical_tag_alias_count_positive"
        ),
        CheckConstraint(
            "video_count >= 0", name="chk_canonical_tag_video_count_non_negative"
        ),
        CheckConstraint(
            "canonical_form != ''", name="chk_canonical_tag_canonical_form_not_empty"
        ),
        Index(
            "idx_canonical_tags_active_normalized",
            "normalized_form",
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "idx_canonical_tags_canonical_form_trgm",
            "canonical_form",
            postgresql_using="gin",
            postgresql_ops={"canonical_form": "gin_trgm_ops"},
        ),
        Index(
            "idx_canonical_tags_canonical_pattern",
            "canonical_form",
            postgresql_ops={"canonical_form": "varchar_pattern_ops"},
        ),
        Index(
            "idx_canonical_tags_entity_id",
            "entity_id",
            postgresql_where=text("entity_id IS NOT NULL"),
        ),
        Index(
            "idx_canonical_tags_normalized_form_trgm",
            "normalized_form",
            postgresql_using="gin",
            postgresql_ops={"normalized_form": "gin_trgm_ops"},
        ),
        Index("idx_canonical_tags_video_count_desc", text("video_count DESC")),
    )

    # Relationships
    aliases: Mapped[list[TagAlias]] = relationship(
        "TagAlias", back_populates="canonical_tag", cascade="all, delete-orphan"
    )
    entity: Mapped[NamedEntity | None] = relationship(
        "NamedEntity", back_populates="canonical_tags", foreign_keys=[entity_id]
    )
    merged_into: Mapped[CanonicalTag | None] = relationship(
        "CanonicalTag", remote_side="CanonicalTag.id"
    )


class TagAlias(Base):
    """Raw tag forms mapped to their canonical representation."""

    __tablename__ = "tag_aliases"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )

    # Tag forms
    raw_form: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    normalized_form: Mapped[str] = mapped_column(String(500), nullable=False)

    # Foreign key to canonical tag
    canonical_tag_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("canonical_tags.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Metadata
    creation_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="auto_normalize"
    )
    normalization_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

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
            name="chk_tag_alias_creation_method_valid",
        ),
        CheckConstraint(
            "occurrence_count >= 1", name="chk_tag_alias_occurrence_count_positive"
        ),
        Index("idx_tag_aliases_canonical_id", "canonical_tag_id"),
        Index("idx_tag_aliases_normalized", "normalized_form"),
        Index(
            "idx_tag_aliases_raw_form_trgm",
            "raw_form",
            postgresql_using="gin",
            postgresql_ops={"raw_form": "gin_trgm_ops"},
        ),
        Index(
            "idx_tag_aliases_raw_pattern",
            "raw_form",
            postgresql_ops={"raw_form": "varchar_pattern_ops"},
        ),
    )

    # Relationships
    canonical_tag: Mapped[CanonicalTag] = relationship(
        "CanonicalTag", back_populates="aliases"
    )


class TagOperationLog(Base):
    """Audit log for tag normalization and management operations."""

    __tablename__ = "tag_operation_logs"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )

    # Operation details
    operation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_canonical_ids: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    target_canonical_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    affected_alias_ids: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    # Context and recovery
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[str] = mapped_column(
        String(100), nullable=False, default="system"
    )
    performed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    rollback_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Rollback tracking
    rolled_back: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rolled_back_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            # Built from TagOperationType rather than restated. The same list
            # lived here, in the Pydantic validator, and in the migration DDL;
            # adding a member updated one and left writes failing at the two
            # others, each from a layer far from the change.
            "operation_type IN ("
            + ", ".join(f"'{t.value}'" for t in TagOperationType)
            + ")",
            name="chk_tag_operation_type_valid",
        ),
        Index("idx_tag_operation_logs_performed_at", "performed_at"),
    )


class EntityOperationLog(Base):
    """Audit log for named-entity curation edits (name/description) — Feature 057."""

    __tablename__ = "entity_operation_logs"

    # Primary key (UUIDv7, time-ordered, application-generated)
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )

    # Edited entity (cascade delete: log rows die with their entity)
    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("named_entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Operation details
    operation_type: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'update'")
    )
    rollback_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Attribution
    performed_by: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'system'")
    )
    performed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Rollback tracking
    rolled_back: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rolled_back_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('update')",
            name="chk_entity_operation_type_valid",
        ),
        Index("idx_entity_operation_logs_entity_id", "entity_id"),
        Index("idx_entity_operation_logs_performed_at", "performed_at"),
    )


class TranscriptCorrection(Base):
    """Append-only audit record for transcript segment corrections (Feature 033).

    Records are never updated or deleted. Each row captures a single correction
    event including the before/after text, correction type, and version number
    within the segment's correction chain.
    """

    __tablename__ = "transcript_corrections"

    # Primary key (UUIDv7, time-ordered)
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )

    # Transcript linkage (composite FK to video_transcripts)
    video_id: Mapped[str] = mapped_column(String(20), nullable=False)
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)

    # Segment linkage (optional FK to transcript_segments)
    segment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("transcript_segments.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Correction content
    correction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_text: Mapped[str] = mapped_column(Text, nullable=False)
    correction_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit metadata
    corrected_by_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    corrected_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Batch grouping (Feature 045 — Correction Intelligence Pipeline)
    # Groups corrections applied together in a single batch run. NULL for
    # corrections that were not part of a batch operation.
    batch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    # Table constraints
    __table_args__ = (
        ForeignKeyConstraint(
            ["video_id", "language_code"],
            ["video_transcripts.video_id", "video_transcripts.language_code"],
            name="fk_transcript_corrections_transcript",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="chk_transcript_corrections_version_number_positive",
        ),
        Index(
            "idx_transcript_corrections_lookup",
            "video_id",
            "language_code",
            "corrected_at",
        ),
        Index("idx_transcript_corrections_segment", "segment_id", "corrected_at"),
        Index(
            "ix_transcript_corrections_batch_id",
            "batch_id",
            postgresql_where=text("batch_id IS NOT NULL"),
        ),
    )

    # Relationships
    transcript: Mapped[VideoTranscript] = relationship(
        "VideoTranscript", back_populates="corrections"
    )
    segment: Mapped[TranscriptSegment | None] = relationship("TranscriptSegment")


class EntityMention(Base):
    """Entity mention records linking named entities to transcript segments.

    Tracks every occurrence of a named entity within a transcript segment,
    including the detection method and confidence score.
    """

    __tablename__ = "entity_mentions"

    # Primary key (UUIDv7, time-ordered)
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )

    # Foreign key to named_entities
    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("named_entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Foreign key to transcript_segments (nullable for manual mentions)
    segment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("transcript_segments.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Denormalized for direct querying without segment join
    video_id: Mapped[str] = mapped_column(String(20), nullable=False)
    # nullable for manual mentions that lack a specific language context
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Mention content
    mention_text: Mapped[str] = mapped_column(String(500), nullable=False)

    # Detection metadata
    detection_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="rule_match"
    )
    # nullable for manual mentions (no statistical confidence applies)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, default=1.0)

    # Character-level position within segment text
    match_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Link to the correction that triggered this mention (if any)
    correction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transcript_corrections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Source location where the mention was found (transcript, title, description)
    mention_source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="transcript",
        server_default="transcript",
    )

    # Context snippet (~150 chars) around the match — populated for description mentions only
    mention_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Table constraints and indexes
    __table_args__ = (
        # Partial unique index for segment-bound (automated) mentions.
        # Replaces the former uq_entity_mention_entity_segment_position
        # unique constraint so that NULL segment_id rows (manual mentions)
        # are excluded from the uniqueness check.
        Index(
            "uq_entity_mentions_transcript",
            "entity_id",
            "segment_id",
            "match_start",
            unique=True,
            postgresql_where=text("segment_id IS NOT NULL"),
        ),
        # Partial unique index for manual mentions.
        # Prevents duplicate manual mentions for the same entity+video pair.
        Index(
            "uq_entity_mentions_manual",
            "entity_id",
            "video_id",
            "detection_method",
            unique=True,
            postgresql_where=text("detection_method = 'manual'"),
        ),
        # Partial unique index for title mentions: one per entity+video.
        Index(
            "uq_entity_mentions_title",
            "entity_id",
            "video_id",
            "mention_source",
            unique=True,
            postgresql_where=text("mention_source = 'title'"),
        ),
        # Partial unique index for description mentions: one per distinct text match.
        Index(
            "uq_entity_mentions_description",
            "entity_id",
            "video_id",
            "mention_source",
            "mention_text",
            unique=True,
            postgresql_where=text("mention_source = 'description'"),
        ),
        CheckConstraint(
            "detection_method IN ('rule_match', 'spacy_ner', 'llm_extraction', 'manual', 'user_correction')",
            name="chk_entity_mention_detection_method_valid",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="chk_entity_mention_confidence_range",
        ),
        CheckConstraint(
            "mention_source IN ('transcript', 'title', 'description', 'manual')",
            name="chk_entity_mention_source_valid",
        ),
        Index("ix_entity_mentions_entity_id", "entity_id"),
        Index("ix_entity_mentions_segment_id", "segment_id"),
        Index("ix_entity_mentions_video_id", "video_id"),
        Index("ix_entity_mentions_video_language", "video_id", "language_code"),
        Index("ix_entity_mentions_detection_method", "detection_method"),
        Index("ix_entity_mentions_mention_source", "mention_source"),
        # Note: correction_id index is created by index=True on the column definition
    )

    # Relationships
    entity: Mapped[NamedEntity] = relationship("NamedEntity", back_populates="mentions")
    segment: Mapped[TranscriptSegment] = relationship(
        "TranscriptSegment", back_populates="entity_mentions"
    )
    correction: Mapped[TranscriptCorrection | None] = relationship(
        "TranscriptCorrection", foreign_keys=[correction_id]
    )


class VideoRecoverySource(Base):
    """One recovery source that contributed to a video's metadata — ADR-011.

    Append-only. A video whose title came from Takeout, description from Wayback
    and duration from Filmot has three rows here, and no pass may erase
    another's.

    Replaces the single-valued ``videos.recovery_source``, which was correct
    while there was exactly one source (ADR-007 defined ``recovered_at`` as
    "when archive recovery was last attempted") and became lossy when a second
    arrived. On 2026-08-09 a Filmot pass overwrote 92 rows' earlier attribution,
    taking the Wayback snapshot timestamp with it because that timestamp was
    encoded *inside* the source string as ``wayback:20210101080938``.

    ``videos.recovery_source`` is retained as a denormalised "most recent" for
    cheap reads, and is derived from this table rather than authoritative.
    """

    __tablename__ = "video_recovery_sources"

    video_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("videos.video_id", ondelete="CASCADE"),
        primary_key=True,
    )
    # 'takeout' | 'wayback' | 'filmot' | 'sync'. Not an enum: a new source
    # should not require a migration, and the set is expected to grow.
    source: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Source-specific identifier — e.g. a Wayback snapshot timestamp. Separate
    # from `source` precisely because packing both into one string is what
    # destroyed the timestamps this table exists to preserve.
    source_detail: Mapped[str | None] = mapped_column(String(100), nullable=True)

    recovered_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Which columns this pass actually wrote. Best-effort: a pass that does not
    # populate it degrades to "this source touched this row", which is still
    # more than the previous schema could say. Consumers must treat it as a
    # hint, never a guarantee.
    fields_written: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )

    __table_args__ = (
        Index("idx_video_recovery_sources_source", "source"),
        {
            "comment": "Append-only provenance: which sources contributed to a video (ADR-011)"
        },
    )


class ChannelRecoverySource(Base):
    """One recovery source that contributed to a channel's metadata — ADR-011.

    Same shape and same rules as :class:`VideoRecoverySource`; see there for the
    reasoning. 275 channels currently exist only because a recovery pass created
    them, and that fact should survive the next pass.
    """

    __tablename__ = "channel_recovery_sources"

    channel_id: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("channels.channel_id", ondelete="CASCADE"),
        primary_key=True,
    )
    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    source_detail: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recovered_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fields_written: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )

    __table_args__ = (
        Index("idx_channel_recovery_sources_source", "source"),
        {
            "comment": "Append-only provenance: which sources contributed to a channel (ADR-011)"
        },
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
    "TranscriptCorrection",
    "EntityMention",
    "VideoRecoverySource",
    "ChannelRecoverySource",
]
