"""Settings API schemas for the settings and preferences page.

This module defines Pydantic models for the settings endpoints,
including supported languages, cache management, app info, and
multi-language transcript downloads.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SupportedLanguage(BaseModel):
    """A supported language with its BCP-47 code and display name."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    display_name: str


class CacheStatusResponse(BaseModel):
    """Image cache statistics."""

    model_config = ConfigDict(from_attributes=True)

    channel_count: int
    video_count: int
    total_count: int
    total_size_bytes: int
    total_size_display: str
    oldest_file: datetime | None = None
    newest_file: datetime | None = None


class CachePurgeResponse(BaseModel):
    """Result of a cache purge operation."""

    model_config = ConfigDict(from_attributes=True)

    purged: bool
    message: str


class DatabaseStats(BaseModel):
    """Aggregate database record counts."""

    model_config = ConfigDict(from_attributes=True)

    videos: int
    channels: int
    playlists: int
    transcripts: int
    corrections: int
    canonical_tags: int


class AppInfoResponse(BaseModel):
    """Application version, database stats, and sync timestamps."""

    model_config = ConfigDict(from_attributes=True)

    backend_version: str
    frontend_version: str
    database_stats: DatabaseStats
    sync_timestamps: dict[str, datetime | None]


class TranscriptDownloadResult(BaseModel):
    """Result of downloading a single language transcript."""

    model_config = ConfigDict(from_attributes=True)

    language_code: str
    language_name: str
    transcript_type: str
    segment_count: int
    downloaded_at: datetime


class MultiTranscriptDownloadResponse(BaseModel):
    """Response for multi-language transcript download."""

    model_config = ConfigDict(from_attributes=True)

    video_id: str
    downloaded: list[TranscriptDownloadResult]
    skipped: list[str]
    failed: list[str]
    attempted_languages: list[str]
