"""Tag API schemas for list and detail endpoints.

This module defines Pydantic models for the Tag API endpoints following
the established patterns from topics.py with List/Detail separation and
response wrappers. Tags are aggregated from the video_tags junction table.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field

from chronovista.api.schemas.responses import PaginationMeta


class TagListItem(BaseModel):
    """Tag summary for list responses.

    Aggregated from video_tags table with video counts.

    Field Mapping:
        tag: Direct from video_tags.tag
        video_count: Aggregated count of videos with this tag
    """

    model_config = ConfigDict(strict=True)

    tag: str = Field(..., description="Tag name")
    video_count: int = Field(0, description="Number of videos with this tag")


class TagDetail(BaseModel):
    """Full tag details for single resource response.

    Currently has same fields as TagListItem since tags are simple
    string values without additional metadata.
    """

    model_config = ConfigDict(strict=True)

    tag: str = Field(..., description="Tag name")
    video_count: int = Field(0, description="Number of videos with this tag")


class TagListResponse(BaseModel):
    """Response wrapper for tag list endpoint.

    Follows standard API response format with data and pagination.
    """

    model_config = ConfigDict(strict=True)

    data: List[TagListItem]
    pagination: PaginationMeta


class TagDetailResponse(BaseModel):
    """Response wrapper for single tag endpoint.

    Follows standard API response format with data.
    """

    model_config = ConfigDict(strict=True)

    data: TagDetail
