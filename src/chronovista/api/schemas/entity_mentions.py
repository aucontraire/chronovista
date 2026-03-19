"""Entity mention API response schemas.

Defines Pydantic models for entity mention endpoints including
video entity summaries and entity-to-videos lookups.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from chronovista.api.schemas.responses import PaginationMeta


class VideoEntitySummary(BaseModel):
    """Summary of a named entity's mentions within a single video.

    Attributes
    ----------
    entity_id : str
        UUID of the named entity (serialized as string in JSON).
    canonical_name : str
        Display name of the entity.
    entity_type : str
        Entity type (person, organization, place, etc.).
    description : str | None
        Entity description.
    mention_count : int
        Number of distinct segments mentioning this entity.
    first_mention_time : float
        Start time (seconds) of the earliest segment with a mention.
    """

    model_config = ConfigDict(strict=True)

    entity_id: str = Field(..., description="Named entity UUID")
    canonical_name: str = Field(..., description="Display name of the entity")
    entity_type: str = Field(
        ..., description="Entity type (person, organization, place, etc.)"
    )
    description: str | None = Field(None, description="Entity description")
    mention_count: int = Field(
        ..., description="Number of distinct segments mentioning this entity"
    )
    first_mention_time: float = Field(
        ...,
        description="Start time (seconds) of the earliest segment with a mention",
    )


class VideoEntitiesResponse(BaseModel):
    """Response envelope for the video entity summary endpoint.

    Attributes
    ----------
    data : list[VideoEntitySummary]
        List of entity summaries for the video, sorted by mention_count DESC.
    """

    model_config = ConfigDict(strict=True)

    data: list[VideoEntitySummary]


class MentionPreview(BaseModel):
    """Preview of a single mention occurrence in a transcript segment.

    Attributes
    ----------
    segment_id : int
        Transcript segment ID.
    start_time : float
        Start time of the segment in seconds.
    mention_text : str
        The alias/name text that matched.
    """

    model_config = ConfigDict(strict=True)

    segment_id: int = Field(..., description="Transcript segment ID")
    start_time: float = Field(
        ..., description="Start time of the segment in seconds"
    )
    mention_text: str = Field(
        ..., description="The alias/name text that matched"
    )


class EntityVideoResult(BaseModel):
    """A single video result in the entity-to-videos lookup.

    Attributes
    ----------
    video_id : str
        YouTube video ID.
    video_title : str
        Video title.
    channel_name : str
        Channel name.
    mention_count : int
        Number of distinct segments mentioning this entity in this video.
    mentions : list[MentionPreview]
        Preview of first 5 mentions ordered by start_time ASC.
    """

    model_config = ConfigDict(strict=True)

    video_id: str = Field(..., description="YouTube video ID")
    video_title: str = Field(..., description="Video title")
    channel_name: str = Field(..., description="Channel name")
    mention_count: int = Field(
        ..., description="Number of distinct segments mentioning this entity"
    )
    mentions: list[MentionPreview] = Field(
        ..., description="Preview of first 5 mentions"
    )


class EntityVideoResponse(BaseModel):
    """Paginated response envelope for the entity-to-videos endpoint.

    Attributes
    ----------
    data : list[EntityVideoResult]
        List of video results with mention previews.
    pagination : PaginationMeta
        Pagination metadata (total, limit, offset, has_more).
    """

    model_config = ConfigDict(strict=True)

    data: list[EntityVideoResult]
    pagination: PaginationMeta


class EntityAliasSummary(BaseModel):
    """Summary of a single alias for a named entity.

    Only genuine aliases are included in responses (asr_error aliases are
    filtered out at the endpoint level as they are considered internal noise).

    Attributes
    ----------
    alias_name : str
        The alias text as stored.
    alias_type : str
        Alias category: name_variant, abbreviation, nickname, translated_name,
        or former_name.
    occurrence_count : int
        Number of times this alias form has been observed.
    """

    model_config = ConfigDict(strict=True)

    alias_name: str = Field(..., description="Alias text")
    alias_type: str = Field(
        ...,
        description=(
            "Alias category (name_variant, abbreviation, nickname, "
            "translated_name, former_name)"
        ),
    )
    occurrence_count: int = Field(
        ..., description="Number of observed occurrences of this alias form"
    )


# Allowed alias types for user-facing creation (asr_error is system-only).
_ALLOWED_ALIAS_TYPES = Literal[
    "name_variant",
    "abbreviation",
    "nickname",
    "translated_name",
    "former_name",
]


class PhoneticMatchResponse(BaseModel):
    """A suspected phonetic ASR variant of an entity name.

    Attributes
    ----------
    original_text : str
        The N-gram text from the transcript segment.
    proposed_correction : str
        The entity name (or alias) that the N-gram likely represents.
    confidence : float
        Weighted confidence score in [0.0, 1.0].
    evidence_description : str
        Human-readable description of the evidence supporting this match.
    video_id : str
        YouTube video ID where the match was found.
    segment_id : int
        Transcript segment primary key.
    video_title : str | None
        Title of the video (enriched from the videos table).
    """

    model_config = ConfigDict(from_attributes=True)

    original_text: str
    proposed_correction: str
    confidence: float
    evidence_description: str
    video_id: str
    segment_id: int
    video_title: str | None = None


class CreateEntityAliasRequest(BaseModel):
    """Request body for creating a new alias on a named entity.

    Attributes
    ----------
    alias_name : str
        The alias text to add.
    alias_type : str
        Alias category. Must be one of: name_variant, abbreviation,
        nickname, translated_name, former_name.
    """

    model_config = ConfigDict(strict=True)

    alias_name: str = Field(
        ..., min_length=1, max_length=500, description="Alias text to add"
    )
    alias_type: _ALLOWED_ALIAS_TYPES = Field(
        default="name_variant",
        description=(
            "Alias type (name_variant, abbreviation, nickname, "
            "translated_name, former_name)"
        ),
    )


class ExclusionPatternRequest(BaseModel):
    """Request body for adding or removing an exclusion pattern.

    Attributes
    ----------
    pattern : str
        The exclusion pattern string. Must be non-empty and at most
        500 characters.
    """

    model_config = ConfigDict(strict=True)

    pattern: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Exclusion pattern to add or remove",
    )
