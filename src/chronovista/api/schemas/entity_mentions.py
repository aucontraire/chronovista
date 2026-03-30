"""Entity mention API response schemas.

Defines Pydantic models for entity mention endpoints including
video entity summaries and entity-to-videos lookups.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    first_mention_time: float | None = Field(
        ...,
        description="Start time (seconds) of the earliest segment with a mention",
    )
    sources: list[str] = Field(
        ...,
        description="Detection method categories (transcript, manual, user_correction)",
    )
    has_manual: bool = Field(
        ..., description="Whether a manual association exists for this entity"
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
        Number of transcript-derived mentions (excludes manual).
    mentions : list[MentionPreview]
        Preview of first 5 transcript mentions ordered by start_time ASC.
    sources : list[str]
        Detection method categories present (e.g. ["transcript", "manual"]).
    has_manual : bool
        Whether a manual association exists for this entity on this video.
    first_mention_time : float | None
        Earliest transcript mention timestamp; null for manual-only videos.
    upload_date : str | None
        Video upload date (ISO 8601) used for sort ordering.
    """

    model_config = ConfigDict(strict=True)

    video_id: str = Field(..., description="YouTube video ID")
    video_title: str = Field(..., description="Video title")
    channel_name: str = Field(..., description="Channel name")
    mention_count: int = Field(
        ...,
        description="Number of transcript-derived mentions (excludes manual)",
    )
    mentions: list[MentionPreview] = Field(
        ..., description="Preview of first 5 transcript mentions"
    )
    sources: list[str] = Field(
        ...,
        description="Detection method categories (transcript, manual, user_correction)",
    )
    has_manual: bool = Field(
        ..., description="Whether a manual association exists"
    )
    first_mention_time: float | None = Field(
        None,
        description="Earliest transcript mention timestamp; null for manual-only",
    )
    upload_date: str | None = Field(
        None, description="Video upload date (ISO 8601)"
    )
    description_context: str | None = Field(
        None,
        description=(
            "Context snippet (~150 chars) around the description match; "
            "only present when 'description' is in sources."
        ),
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


class EntitySearchResult(BaseModel):
    """Result from entity autocomplete search.

    Attributes
    ----------
    entity_id : str
        Named entity UUID.
    canonical_name : str
        Display name.
    entity_type : str
        Entity type.
    description : str | None
        Entity description.
    status : str
        Entity status (active/deprecated).
    matched_alias : str | None
        Alias that matched, if any.
    is_linked : bool | None
        Whether linked to the video (only when video_id provided).
    link_sources : list[str] | None
        Detection methods for existing links.
    """

    model_config = ConfigDict(strict=True)

    entity_id: str = Field(..., description="Named entity UUID")
    canonical_name: str = Field(..., description="Display name")
    entity_type: str = Field(..., description="Entity type")
    description: str | None = Field(None, description="Entity description")
    status: str = Field(..., description="Entity status (active/deprecated)")
    matched_alias: str | None = Field(
        None, description="Alias that matched, if any"
    )
    is_linked: bool | None = Field(
        None,
        description="Whether linked to the video (only when video_id provided)",
    )
    link_sources: list[str] | None = Field(
        None, description="Detection methods for existing links"
    )


class ManualAssociationResponse(BaseModel):
    """Response for manual entity-video association creation.

    Attributes
    ----------
    id : str
        Entity mention UUID.
    entity_id : str
        Named entity UUID.
    video_id : str
        YouTube video ID.
    detection_method : str
        Detection method (manual).
    mention_text : str
        Entity canonical name.
    created_at : str
        ISO 8601 creation timestamp.
    """

    model_config = ConfigDict(strict=True)

    id: str = Field(..., description="Entity mention UUID")
    entity_id: str = Field(..., description="Named entity UUID")
    video_id: str = Field(..., description="YouTube video ID")
    detection_method: str = Field(..., description="Detection method (manual)")
    mention_text: str = Field(..., description="Entity canonical name")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


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


# ---------------------------------------------------------------------------
# Entity creation & duplicate-check schemas (Feature 051)
# ---------------------------------------------------------------------------

_ENTITY_PRODUCING_TYPES = {
    "person",
    "organization",
    "place",
    "event",
    "work",
    "technical_term",
    "concept",
    "other",
}


class ExistingEntityInfo(BaseModel):
    """Summary of an existing entity for duplicate detection.

    Attributes
    ----------
    entity_id : str
        Named entity UUID.
    canonical_name : str
        Display name of the entity.
    entity_type : str
        Entity type.
    description : str | None
        Entity description.
    """

    model_config = ConfigDict(strict=True)

    entity_id: str = Field(..., description="Named entity UUID")
    canonical_name: str = Field(..., description="Display name of the entity")
    entity_type: str = Field(..., description="Entity type")
    description: str | None = Field(None, description="Entity description")


class DuplicateCheckResponse(BaseModel):
    """Response for duplicate entity check.

    Attributes
    ----------
    is_duplicate : bool
        Whether a duplicate entity was found.
    existing_entity : ExistingEntityInfo | None
        Details of the existing entity, if found.
    """

    model_config = ConfigDict(strict=True)

    is_duplicate: bool = Field(
        ..., description="Whether a duplicate entity was found"
    )
    existing_entity: ExistingEntityInfo | None = Field(
        default=None, description="Details of the existing entity, if found"
    )


class CreateEntityRequest(BaseModel):
    """Request body for standalone entity creation.

    Attributes
    ----------
    name : str
        Entity display name (1-500 chars).
    entity_type : str
        Must be one of the entity-producing types.
    description : str | None
        Optional entity description (max 5000 chars).
    aliases : list[str]
        Optional list of alias strings (max 20).
    """

    model_config = ConfigDict(strict=True)

    name: str = Field(
        ..., min_length=1, max_length=500, description="Entity display name"
    )
    entity_type: str = Field(
        ..., min_length=1, description="Entity type"
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional entity description",
    )
    aliases: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Optional alias strings",
    )

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        """Ensure entity_type is a valid entity-producing type."""
        if v not in _ENTITY_PRODUCING_TYPES:
            raise ValueError(
                f"entity_type must be one of: "
                f"{', '.join(sorted(_ENTITY_PRODUCING_TYPES))}"
            )
        return v

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, v: list[str]) -> list[str]:
        """Strip whitespace from aliases and filter out empty strings."""
        return [a.strip() for a in v if a.strip()]


class ClassifyTagRequest(BaseModel):
    """Request body for tag-backed entity creation.

    Attributes
    ----------
    normalized_form : str
        Normalized form of the canonical tag (1-500 chars).
    entity_type : str
        Must be one of the entity-producing types.
    description : str | None
        Optional entity description (max 5000 chars).
    """

    model_config = ConfigDict(strict=True)

    normalized_form: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Normalized form of the canonical tag",
    )
    entity_type: str = Field(
        ..., min_length=1, description="Entity type"
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional entity description",
    )

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        """Ensure entity_type is a valid entity-producing type."""
        if v not in _ENTITY_PRODUCING_TYPES:
            raise ValueError(
                f"entity_type must be one of: "
                f"{', '.join(sorted(_ENTITY_PRODUCING_TYPES))}"
            )
        return v


# ---------------------------------------------------------------------------
# Scan request / response schemas (Feature 038 API)
# ---------------------------------------------------------------------------

_VALID_ENTITY_TYPES = {
    "person",
    "organization",
    "place",
    "event",
    "work",
    "technical_term",
    "topic",
    "descriptor",
    "concept",
    "other",
}


_VALID_SCAN_SOURCES = {"transcript", "title", "description"}


class ScanRequest(BaseModel):
    """Request body for triggering an entity mention scan.

    All fields are optional.  An empty body ``{}`` runs a default
    incremental scan across all entities and languages.

    Attributes
    ----------
    language_code : str | None
        Restrict scanning to transcript segments in this language.
    entity_type : str | None
        Restrict scanning to entities of this type.  Must be a valid
        ``EntityType`` enum value.
    dry_run : bool
        If ``True``, collect preview data without writing to the database.
    full_rescan : bool
        If ``True``, delete existing ``rule_match`` mentions in scope
        before scanning.
    sources : list[str] | None
        Text sources to scan.  Valid values: ``transcript``, ``title``,
        ``description``.  Defaults to ``["transcript"]`` for backward
        compatibility.
    """

    model_config = ConfigDict(strict=True)

    language_code: str | None = Field(
        default=None,
        description="Restrict scanning to segments in this language",
    )
    entity_type: str | None = Field(
        default=None,
        description="Restrict scanning to entities of this type",
    )
    dry_run: bool = Field(
        default=False,
        description="Preview matches without writing to the database",
    )
    full_rescan: bool = Field(
        default=False,
        description="Delete existing rule_match mentions before scanning",
    )
    sources: list[str] | None = Field(
        default=None,
        description=(
            "Text sources to scan: transcript, title, description. "
            "Defaults to ['transcript'] when omitted."
        ),
    )

    @field_validator("entity_type")
    @classmethod
    def validate_scan_entity_type(cls, v: str | None) -> str | None:
        """Ensure entity_type is a valid EntityType enum value when provided."""
        if v is not None and v not in _VALID_ENTITY_TYPES:
            raise ValueError(
                f"entity_type must be one of: "
                f"{', '.join(sorted(_VALID_ENTITY_TYPES))}"
            )
        return v

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, v: list[str] | None) -> list[str] | None:
        """Ensure each source value is valid (transcript, title, description).

        Rejects ``tag`` with a helpful message explaining that tag
        associations are query-time (Feature 053), not scan-persisted.
        """
        if v is None:
            return v
        for source in v:
            if source not in _VALID_SCAN_SOURCES:
                if source == "tag":
                    raise ValueError(
                        f"Invalid source value '{source}'. Tag associations "
                        f"are query-time (not scan-persisted). "
                        f"Valid values: {', '.join(sorted(_VALID_SCAN_SOURCES))}."
                    )
                raise ValueError(
                    f"Invalid source value '{source}'. "
                    f"Valid values: {', '.join(sorted(_VALID_SCAN_SOURCES))}."
                )
        return v


class ScanResultData(BaseModel):
    """Core scan result metrics returned inside the response envelope.

    Attributes
    ----------
    segments_scanned : int
        Total number of transcript segments examined.
    mentions_found : int
        Number of new entity mention rows inserted (or previewed).
    mentions_skipped : int
        Number of mention matches already present (incremental mode).
    unique_entities : int
        Count of distinct entities that produced at least one mention.
    unique_videos : int
        Count of distinct videos that contained at least one mention.
    duration_seconds : float
        Wall-clock time spent on the scan.
    dry_run : bool
        Whether this was a dry-run (no writes).
    """

    model_config = ConfigDict(strict=True)

    segments_scanned: int = Field(
        ..., description="Total transcript segments examined"
    )
    mentions_found: int = Field(
        ..., description="New entity mention rows inserted (or previewed)"
    )
    mentions_skipped: int = Field(
        ..., description="Mention matches already present (incremental mode)"
    )
    unique_entities: int = Field(
        ..., description="Distinct entities with at least one mention"
    )
    unique_videos: int = Field(
        ..., description="Distinct videos with at least one mention"
    )
    duration_seconds: float = Field(
        ..., description="Wall-clock time spent on the scan"
    )
    dry_run: bool = Field(
        ..., description="Whether this was a dry-run (no writes)"
    )


class ScanResultResponse(BaseModel):
    """Response envelope for the entity mention scan endpoint.

    Wraps ``ScanResultData`` inside a ``data`` key for consistent
    API response formatting.

    Attributes
    ----------
    data : ScanResultData
        Scan result metrics.
    """

    model_config = ConfigDict(strict=True)

    data: ScanResultData
