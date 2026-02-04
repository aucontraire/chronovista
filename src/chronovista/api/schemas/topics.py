"""Topic API schemas for list and detail endpoints.

This module defines Pydantic models for the Topic API endpoints following
the established patterns from videos.py with List/Detail separation and
response wrappers. The database entity is TopicCategory, but the API
exposes it as "Topic" for simplicity.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from chronovista.api.schemas.responses import PaginationMeta


class TopicListItem(BaseModel):
    """Topic summary for list responses.

    Maps from TopicCategory database model with aggregated counts.

    Field Mapping:
        topic_id: Direct from topic_id
        name: Renamed from category_name
        video_count: Aggregated from video_topics
        channel_count: Aggregated from channel_topics
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    topic_id: str = Field(..., description="Topic ID (e.g., /m/019_rr)")
    name: str = Field(..., description="Topic name")
    video_count: int = Field(0, description="Number of videos with this topic")
    channel_count: int = Field(0, description="Number of channels with this topic")


class TopicDetail(TopicListItem):
    """Full topic details for single resource response.

    Extends TopicListItem with additional metadata fields.
    """

    parent_topic_id: Optional[str] = Field(None, description="Parent topic ID")
    topic_type: str = Field("youtube", description="Topic type: youtube or custom")
    wikipedia_url: Optional[str] = Field(None, description="Wikipedia URL for topic")
    normalized_name: Optional[str] = Field(None, description="Normalized topic name")
    source: str = Field("seeded", description="Topic source: seeded or dynamic")
    created_at: datetime = Field(..., description="Record creation timestamp")


class TopicListResponse(BaseModel):
    """Response wrapper for topic list endpoint.

    Follows standard API response format with data and pagination.
    """

    model_config = ConfigDict(strict=True)

    data: List[TopicListItem]
    pagination: PaginationMeta


class TopicDetailResponse(BaseModel):
    """Response wrapper for single topic endpoint.

    Follows standard API response format with data.
    """

    model_config = ConfigDict(strict=True)

    data: TopicDetail
