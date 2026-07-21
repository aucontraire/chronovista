"""Canonical Tag API schemas for list and detail endpoints.

This module defines Pydantic models for the Canonical Tag API endpoints
(Feature 030) following established patterns from tags.py with List/Detail
separation and response wrappers.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from chronovista.api.schemas.responses import PaginationMeta


class MatchMode(str, Enum):
    """Search match mode for canonical tag lookup.

    ``PREFIX`` matches from the start of the value (``q%``) and is the default,
    preserving the video filter's behavior. ``CONTAINS`` matches a substring at
    any position (``%q%``) and is used by the merge UI for variant discovery.
    """

    PREFIX = "prefix"
    CONTAINS = "contains"


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
    top_aliases: list[TagAliasItem] = Field(
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

    data: list[CanonicalTagListItem]
    pagination: PaginationMeta
    suggestions: list[CanonicalTagSuggestion] | None = Field(
        None,
        description="Fuzzy match suggestions when no exact matches found",
    )


class CanonicalTagDetailResponse(BaseModel):
    """Response wrapper for single canonical tag endpoint.

    Follows standard API response format with data.
    """

    model_config = ConfigDict(strict=True)

    data: CanonicalTagDetail


# ---------------------------------------------------------------------------
# Merge / preview / undo (Feature 056)
# ---------------------------------------------------------------------------


class MergePreviewRequest(BaseModel):
    """Request body for the read-only merge preview endpoint."""

    model_config = ConfigDict(strict=True)

    source_normalized_forms: list[str] = Field(
        ..., min_length=1, description="Normalized forms of source tags"
    )
    target_normalized_form: str = Field(
        ..., description="Normalized form of the surviving target tag"
    )


class MergePreview(BaseModel):
    """Exact resulting counts for a proposed merge (no mutation)."""

    model_config = ConfigDict(strict=True, from_attributes=True)

    source_tags: list[str] = Field(..., description="Source canonical forms")
    target_tag: str = Field(..., description="Target canonical form")
    resulting_alias_count: int = Field(
        ..., description="Alias count after merge (exact)"
    )
    resulting_video_count: int = Field(
        ..., description="Distinct video count after merge (exact)"
    )
    source_alias_count: int = Field(
        ..., description="Alias count across sources only"
    )
    source_video_count: int = Field(
        ..., description="Distinct video count across sources only"
    )


class MergePreviewResponse(BaseModel):
    """Response wrapper for the merge preview endpoint."""

    model_config = ConfigDict(strict=True)

    data: MergePreview


class MergeRequest(BaseModel):
    """Request body for executing a merge."""

    model_config = ConfigDict(strict=True)

    source_normalized_forms: list[str] = Field(
        ..., min_length=1, description="Normalized forms of source tags"
    )
    target_normalized_form: str = Field(
        ..., description="Normalized form of the surviving target tag"
    )
    reason: str | None = Field(
        None, max_length=1000, description="Optional reason for the merge"
    )


class MergeResultSchema(BaseModel):
    """Result of an executed merge (maps from service MergeResult)."""

    model_config = ConfigDict(strict=True, from_attributes=True)

    source_tags: list[str] = Field(..., description="Source normalized forms")
    target_tag: str = Field(..., description="Target normalized form")
    aliases_moved: int = Field(..., description="Number of aliases reassigned")
    new_alias_count: int = Field(..., description="Target alias count after merge")
    new_video_count: int = Field(..., description="Target video count after merge")
    operation_id: str = Field(..., description="Operation ID for undo")
    entity_hint: str | None = Field(
        None, description="Hint when a source was linked to a named entity"
    )


class MergeResponse(BaseModel):
    """Response wrapper for the merge endpoint."""

    model_config = ConfigDict(strict=True)

    data: MergeResultSchema


class UndoResultSchema(BaseModel):
    """Result of an undo operation (maps from service UndoResult)."""

    model_config = ConfigDict(strict=True, from_attributes=True)

    operation_type: str = Field(..., description="Type of operation undone")
    operation_id: str = Field(..., description="Operation ID that was undone")
    details: str = Field(..., description="Human-readable undo summary")


class UndoResponse(BaseModel):
    """Response wrapper for the undo endpoint."""

    model_config = ConfigDict(strict=True)

    data: UndoResultSchema
