"""Sidebar API schemas for navigation endpoints.

This module defines Pydantic models for sidebar navigation elements
such as category navigation with video counts.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class SidebarCategory(BaseModel):
    """Category formatted for sidebar navigation.

    Provides category information with pre-built navigation URL
    for frontend sidebar display.

    Attributes
    ----------
    category_id : str
        YouTube category ID.
    name : str
        Human-readable category name.
    video_count : int
        Number of videos in this category.
    href : str
        Navigation URL (e.g., '/videos?category=10').
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    category_id: str = Field(..., description="YouTube category ID")
    name: str = Field(..., description="Human-readable category name")
    video_count: int = Field(0, description="Number of videos in this category")
    href: str = Field(..., description="Navigation URL (e.g., '/videos?category=10')")


class SidebarCategoryResponse(BaseModel):
    """Response wrapper for sidebar categories endpoint.

    Returns categories ordered by video_count descending,
    including only categories with at least one video by default.
    """

    model_config = ConfigDict(strict=True)

    data: List[SidebarCategory]
