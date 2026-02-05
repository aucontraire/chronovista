"""Category API schemas for list and detail endpoints.

This module defines Pydantic models for the Category API endpoints following
the established patterns from topics.py with List/Detail separation and
response wrappers.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field

from chronovista.api.schemas.responses import PaginationMeta


class CategoryListItem(BaseModel):
    """Category summary for list responses.

    Maps from VideoCategory database model with aggregated counts.

    Field Mapping:
        category_id: Direct from category_id
        name: Direct from name
        assignable: Direct from assignable
        video_count: Aggregated from videos (excluding deleted)
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    category_id: str = Field(..., description="YouTube category ID")
    name: str = Field(..., description="Category name")
    assignable: bool = Field(..., description="Whether creators can select this category")
    video_count: int = Field(0, description="Number of videos in this category")


class CategoryDetail(CategoryListItem):
    """Full category details for single resource response.

    Extends CategoryListItem with additional metadata fields.
    """

    created_at: datetime = Field(..., description="Record creation timestamp")


class CategoryListResponse(BaseModel):
    """Response wrapper for category list endpoint.

    Follows standard API response format with data and pagination.
    """

    model_config = ConfigDict(strict=True)

    data: List[CategoryListItem]
    pagination: PaginationMeta


class CategoryDetailResponse(BaseModel):
    """Response wrapper for single category endpoint.

    Follows standard API response format with data.
    """

    model_config = ConfigDict(strict=True)

    data: CategoryDetail
