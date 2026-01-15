"""
Enrichment report models.

Defines Pydantic models for metadata enrichment reporting, including
summary statistics and detailed per-video enrichment results.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EnrichmentSummary(BaseModel):
    """Summary statistics for metadata enrichment operation."""

    videos_processed: int = Field(
        ..., ge=0, description="Total number of videos processed"
    )
    videos_updated: int = Field(
        ..., ge=0, description="Number of videos successfully updated"
    )
    videos_deleted: int = Field(
        ..., ge=0, description="Number of videos marked as deleted"
    )
    channels_created: int = Field(
        ..., ge=0, description="Number of new channels created"
    )
    channels_auto_resolved: int = Field(
        default=0, ge=0, description="Number of orphan videos linked to real channels"
    )
    tags_created: int = Field(
        ..., ge=0, description="Number of new tags created"
    )
    topic_associations: int = Field(
        ..., ge=0, description="Number of topic associations created"
    )
    categories_assigned: int = Field(
        ..., ge=0, description="Number of category assignments made"
    )
    errors: int = Field(
        ..., ge=0, description="Number of errors encountered"
    )
    quota_used: int = Field(
        ..., ge=0, description="YouTube API quota units consumed"
    )
    # Playlist enrichment statistics
    playlists_processed: int = Field(
        default=0, ge=0, description="Total number of playlists processed"
    )
    playlists_updated: int = Field(
        default=0, ge=0, description="Number of playlists successfully updated"
    )
    playlists_deleted: int = Field(
        default=0, ge=0, description="Number of playlists marked as deleted/private"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class EnrichmentDetail(BaseModel):
    """Detailed enrichment result for a single video."""

    video_id: str = Field(
        ..., min_length=1, description="YouTube video ID"
    )
    status: Literal["updated", "deleted", "error", "skipped"] = Field(
        ..., description="Enrichment status for this video"
    )
    old_title: Optional[str] = Field(
        default=None, description="Previous video title (if changed)"
    )
    new_title: Optional[str] = Field(
        default=None, description="New video title (if changed)"
    )
    old_channel: Optional[str] = Field(
        default=None, description="Previous channel ID (if changed)"
    )
    new_channel: Optional[str] = Field(
        default=None, description="New channel ID (if changed)"
    )
    tags_count: Optional[int] = Field(
        default=None, ge=0, description="Number of tags associated"
    )
    topics_count: Optional[int] = Field(
        default=None, ge=0, description="Number of topics associated"
    )
    category_id: Optional[str] = Field(
        default=None, max_length=10, description="Assigned category ID"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if status is 'error'"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class EnrichmentReport(BaseModel):
    """Complete metadata enrichment report."""

    timestamp: datetime = Field(
        ..., description="When the enrichment operation was performed (ISO 8601)"
    )
    priority: str = Field(
        ..., min_length=1, description="Priority level of the enrichment batch"
    )
    summary: EnrichmentSummary = Field(
        ..., description="Summary statistics for the enrichment operation"
    )
    details: List[EnrichmentDetail] = Field(
        default_factory=list, description="Detailed results for each video"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )
