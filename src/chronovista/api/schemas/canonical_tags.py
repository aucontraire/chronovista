"""Canonical Tag API schemas for list and detail endpoints.

This module defines Pydantic models for the Canonical Tag API endpoints
(Feature 030) following established patterns from tags.py with List/Detail
separation and response wrappers.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from chronovista.api.schemas.responses import PaginationMeta


class CanonicalTagListItem(BaseModel):
    """Canonical tag summary for list responses.

    Attributes
    ----------
    canonical_form : str
        Display-ready canonical form of the tag.
    normalized_form : str
        Normalized (lowercased, accent-folded) form used for matching.
    alias_count : int
        Number of raw tag aliases mapped to this canonical tag.
    video_count : int
        Number of videos associated with this canonical tag.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    canonical_form: str = Field(..., description="Display-ready canonical form")
    normalized_form: str = Field(..., description="Normalized form for matching")
    alias_count: int = Field(0, description="Number of raw tag aliases")
    video_count: int = Field(0, description="Number of videos with this tag")


class TagAliasItem(BaseModel):
    """Individual tag alias within a canonical tag detail.

    Attributes
    ----------
    raw_form : str
        Original raw tag string as it appears on YouTube videos.
    occurrence_count : int
        Number of times this raw form appears across videos.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    raw_form: str = Field(..., description="Original raw tag string")
    occurrence_count: int = Field(0, description="Number of occurrences across videos")


class CanonicalTagDetail(BaseModel):
    """Full canonical tag details for single resource response.

    Extends the list item fields with top aliases and timestamps.

    Attributes
    ----------
    canonical_form : str
        Display-ready canonical form of the tag.
    normalized_form : str
        Normalized (lowercased, accent-folded) form used for matching.
    alias_count : int
        Number of raw tag aliases mapped to this canonical tag.
    video_count : int
        Number of videos associated with this canonical tag.
    top_aliases : list[TagAliasItem]
        Top aliases by occurrence count for this canonical tag.
    created_at : datetime
        Timestamp when the canonical tag was created.
    updated_at : datetime
        Timestamp when the canonical tag was last updated.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    canonical_form: str = Field(..., description="Display-ready canonical form")
    normalized_form: str = Field(..., description="Normalized form for matching")
    alias_count: int = Field(0, description="Number of raw tag aliases")
    video_count: int = Field(0, description="Number of videos with this tag")
    top_aliases: List[TagAliasItem] = Field(
        default_factory=list, description="Top aliases by occurrence count"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class CanonicalTagSuggestion(BaseModel):
    """Fuzzy match suggestion for canonical tag search.

    Attributes
    ----------
    canonical_form : str
        Display-ready canonical form of the suggested tag.
    normalized_form : str
        Normalized form for matching.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    canonical_form: str = Field(..., description="Suggested canonical form")
    normalized_form: str = Field(..., description="Normalized form for matching")


class CanonicalTagListResponse(BaseModel):
    """Response wrapper for canonical tag list endpoint.

    Follows standard API response format with data and pagination.
    Includes optional fuzzy suggestions when no exact matches found.
    """

    model_config = ConfigDict(strict=True)

    data: List[CanonicalTagListItem]
    pagination: PaginationMeta
    suggestions: Optional[List[CanonicalTagSuggestion]] = Field(
        None,
        description="Fuzzy match suggestions when no exact matches found",
    )


class CanonicalTagDetailResponse(BaseModel):
    """Response wrapper for single canonical tag endpoint.

    Follows standard API response format with data.
    """

    model_config = ConfigDict(strict=True)

    data: CanonicalTagDetail
