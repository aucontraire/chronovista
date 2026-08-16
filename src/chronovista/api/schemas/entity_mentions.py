"""Entity mention API response schemas.

Defines Pydantic models for entity mention endpoints including
video entity summaries and entity-to-videos lookups.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from chronovista.api.schemas.responses import PaginationMeta
from chronovista.models.enums import EntityType


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
        Number of detected mentions: distinct transcript segments, plus each
        title and description mention. Excludes manual associations, which are
        reported by ``has_manual``.
    first_mention_time : float | None
        Start time (seconds) of the earliest segment with a mention. None when
        the entity has no transcript mention — a title-only entity has a
        mention but no timestamp.
    sources : list[str]
        Provenance of the association: where mentions were found (transcript,
        title, description), plus "manual" if a hand-made association exists and
        "tag" if the entity is linked through a YouTube tag. A tag-only or
        manual-only entity has mention_count 0 but is still listed (US2).
    """

    model_config = ConfigDict(strict=True)

    entity_id: str = Field(..., description="Named entity UUID")
    canonical_name: str = Field(..., description="Display name of the entity")
    entity_type: str = Field(
        ..., description="Entity type (person, organization, place, etc.)"
    )
    description: str | None = Field(None, description="Entity description")
    mention_count: int = Field(
        ...,
        description=(
            "Detected mentions: distinct transcript segments plus each title "
            "and description mention; excludes manual associations"
        ),
    )
    first_mention_time: float | None = Field(
        ...,
        description="Start time (seconds) of the earliest segment with a mention",
    )
    sources: list[str] = Field(
        ...,
        description=(
            "Association provenance: where mentions were found (transcript, "
            "title, description), plus 'manual' for a hand-made association and "
            "'tag' when linked through a YouTube tag"
        ),
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
    start_time: float = Field(..., description="Start time of the segment in seconds")
    mention_text: str = Field(..., description="The alias/name text that matched")


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
        description=(
            "Where mentions were found (transcript, title, description), plus "
            "'manual' when a hand-made association exists"
        ),
    )
    has_manual: bool = Field(..., description="Whether a manual association exists")
    first_mention_time: float | None = Field(
        None,
        description="Earliest transcript mention timestamp; null for manual-only",
    )
    upload_date: str | None = Field(None, description="Video upload date (ISO 8601)")
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
    id : UUID
        Alias identifier, needed to address a single alias for update.
    alias_name : str
        The alias text as stored.
    alias_type : str
        Alias category: name_variant, abbreviation, nickname, translated_name,
        or former_name.
    occurrence_count : int
        Number of times this alias form has been observed.
    case_sensitive : bool
        Whether this alias matches only its exact casing.
    """

    model_config = ConfigDict(strict=True)

    id: UUID = Field(..., description="Alias identifier")
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
    case_sensitive: bool = Field(
        default=False,
        description=(
            "When true, this alias matches only the exact casing shown in "
            "alias_name. False (the default) matches any casing."
        ),
    )


class UpdateEntityAliasRequest(BaseModel):
    """PATCH body for a single alias.

    Only ``case_sensitive`` is settable. Renaming an alias would change what
    it matches and orphan the mentions it produced, so it is deliberately not
    offered here.
    """

    model_config = ConfigDict(strict=True)

    case_sensitive: bool = Field(
        ...,
        description=(
            "Match only the exact casing stored in alias_name. Intended for "
            "an alias that is also an ordinary word, where casing separates "
            "the name from the word — but only where that has been confirmed "
            "against real occurrences, since automatic transcription drops "
            "capitalisation often enough that the opposite can hold."
        ),
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
    matched_alias: str | None = Field(None, description="Alias that matched, if any")
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

    is_duplicate: bool = Field(..., description="Whether a duplicate entity was found")
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
    entity_type: str = Field(..., min_length=1, description="Entity type")
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
    display_name : str | None
        Optional verbatim entity display name (1-500 chars). When provided,
        the created entity's ``canonical_name`` is this value exactly (no
        auto re-casing); when omitted, the auto-derived name is used
        (Feature 057, FR-008..FR-011).
    link_entity_id : UUID | None
        Link the tag to this existing entity instead of creating one. When
        given, ``entity_type`` may be omitted and is inferred from the target
        entity, matching ``tags classify --link-entity`` (issue #183).
    """

    model_config = ConfigDict(strict=True)

    normalized_form: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Normalized form of the canonical tag",
    )
    entity_type: str | None = Field(
        default=None,
        min_length=1,
        description="Entity type; optional when link_entity_id is given",
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional entity description",
    )
    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="Optional verbatim entity display name",
    )
    link_entity_id: UUID | None = Field(
        default=None,
        # This model is strict, and strict mode refuses to build a UUID from
        # the string an HTTP client sends — FastAPI validates the parsed body
        # in python mode, where a str is just a str. Same opt-out the
        # EntityType fields use.
        strict=False,
        description="Link to this existing entity instead of creating one",
    )

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str | None) -> str | None:
        """Ensure entity_type, when given, is a valid entity-producing type."""
        if v is None:
            return v
        if v not in _ENTITY_PRODUCING_TYPES:
            raise ValueError(
                f"entity_type must be one of: "
                f"{', '.join(sorted(_ENTITY_PRODUCING_TYPES))}"
            )
        return v

    @model_validator(mode="after")
    def validate_type_or_link(self) -> ClassifyTagRequest:
        """Mirror the CLI's rules for combining these fields.

        ``entity_type`` is only optional in the linking case, where it is
        inferred from the target entity.

        ``description`` and ``display_name`` both describe an entity being
        created. Pairing either with a link is refused rather than accepted,
        because neither is inert there: the service ignores ``description``
        outright, and ``display_name`` is worse — it becomes the name of a new
        alias written onto the *target* entity, so a link request could inject
        an arbitrary alias onto a record it was only supposed to point at.
        """
        if self.entity_type is None and self.link_entity_id is None:
            raise ValueError(
                "entity_type is required unless link_entity_id is provided"
            )
        if self.link_entity_id is not None:
            for field in ("description", "display_name"):
                if getattr(self, field) is not None:
                    raise ValueError(
                        f"{field} and link_entity_id are mutually exclusive; "
                        f"{field} applies only when creating a new entity"
                    )
        return self


class UnMergeRequest(BaseModel):
    """Request body for reversing a merge (Feature 064, FR-015/FR-016).

    Attributes
    ----------
    confirm_multi_source : bool
        Acknowledges that the merge being reversed folded several tags, and
        that reversing it restores all of them. Required only in that case;
        every other un-merge proceeds without confirmation (FR-006).
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    confirm_multi_source: bool = Field(
        default=False,
        description="Proceed even though other tags will also be restored",
    )


class UnMergeResult(BaseModel):
    """Which tags a reversal restored."""

    model_config = ConfigDict(strict=True)

    restored: list[str]
    operation_id: str


class UnMergeResponse(BaseModel):
    """Envelope for :class:`UnMergeResult`."""

    data: UnMergeResult


class UnlinkResult(BaseModel):
    """The tag no longer representing the entity."""

    model_config = ConfigDict(strict=True)

    unlinked: str


class UnlinkResponse(BaseModel):
    """Envelope for :class:`UnlinkResult`."""

    data: UnlinkResult


class MergedTagSummary(BaseModel):
    """A canonical tag folded into the entity's tag by a curator's merge.

    Attributes
    ----------
    canonical_form : str
        Display form of the absorbed tag.
    normalized_form : str
        Its normalized form, used to address it for un-merging.
    contributed_video_count : int
        Videos this tag held **at the moment it was merged**. A frozen figure,
        not a live count, and not additive with the parent's — the two video
        sets may overlap. Labelled accordingly wherever it is shown (FR-014).
    operation_id : str | None
        The merge that absorbed it, if a live one is recorded. ``None`` means
        the tag cannot be un-merged from the interface, rather than that it can
        be un-merged by guessing which operation to reverse.
    operation_source_count : int
        How many tags that one operation folded. Greater than 1 means reversing
        it restores others too, which requires confirmation (FR-016). Supplied
        here so the interface knows without a second request.
    """

    model_config = ConfigDict(strict=True)

    canonical_form: str
    normalized_form: str
    contributed_video_count: int
    operation_id: str | None
    operation_source_count: int


class LinkedTagSummary(BaseModel):
    """A canonical tag that represents the entity, plus what it has absorbed.

    Attributes
    ----------
    canonical_form : str
        Display form of the tag.
    normalized_form : str
        Its normalized form.
    video_count : int
        Current video count — live, unlike ``contributed_video_count`` above.
    alias_count : int
        Raw forms this tag owns, including any inherited by merging.
    merged_tags : list[MergedTagSummary]
        Tags merged into this one. Only curator merges; auto-normalized raw
        forms are excluded (FR-013).
    """

    model_config = ConfigDict(strict=True)

    canonical_form: str
    normalized_form: str
    video_count: int
    alias_count: int
    merged_tags: list[MergedTagSummary]


class EntityTagsResult(BaseModel):
    """The tags representing an entity.

    Attributes
    ----------
    linked_tags : list[LinkedTagSummary]
        Normally exactly one (FR-028 / invariant I1). Empty when no tag is
        linked, which is itself the signal that the entity is under-counted
        (FR-011). A list rather than a single value because legacy data reached
        a multi-tag state the browser can no longer create, and the page must
        render it rather than raise (FR-011a).
    needs_attention : bool
        True when more than one tag is linked.
    """

    model_config = ConfigDict(strict=True)

    linked_tags: list[LinkedTagSummary]
    needs_attention: bool


class EntityTagsResponse(BaseModel):
    """Envelope for :class:`EntityTagsResult`."""

    data: EntityTagsResult


class AddEntityTagRequest(BaseModel):
    """Request body for attaching a canonical tag to an entity (Feature 064).

    Carries only the tag. The server chooses between linking and merging from
    the entity's current state (FR-001/FR-002) — the client never decides, so
    that the rule "the entity's tag always wins" (FR-003) cannot be overridden
    from a browser.

    Deliberately has no ``entity_type``: it is inferred from the entity, and a
    value disagreeing with the target is a conflict rather than an instruction.
    No ``description`` or ``display_name`` either — those describe an entity
    being created, and neither is inert on this path (FR-004).

    Attributes
    ----------
    normalized_form : str
        Normalized form of the canonical tag to attach.
    """

    # extra="forbid" rather than the default, which silently drops unknown
    # fields. A caller sending display_name or entity_type here is working from
    # a wrong model of the endpoint, and dropping it quietly leaves them
    # believing it took effect. This feature exists because a field that looked
    # inert was not — refusing is the honest answer (FR-004).
    model_config = ConfigDict(strict=True, extra="forbid")

    normalized_form: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Normalized form of the canonical tag to attach",
    )


class AddEntityTagResult(BaseModel):
    """Outcome of attaching a tag, including which operation was chosen.

    Attributes
    ----------
    operation : Literal["link", "merge"]
        Which path the server took. Reported so the interface can word its
        confirmation truthfully rather than guessing.
    operation_id : str
        Operation log id, usable to reverse this.
    target_normalized_form : str
        The tag that now represents the entity. For a merge this is the
        pre-existing tag, not the one just supplied.
    target_canonical_form : str
        Its display form. Supplied because the normalized form is lower-cased
        and a message built from it reads as a different tag than the one shown
        immediately above it on the page.
    entity_video_count : int
        The entity's video count after the operation, so the caller can show
        the consequence without a second request.
    """

    model_config = ConfigDict(strict=True)

    operation: Literal["link", "merge"]
    operation_id: str
    target_normalized_form: str
    target_canonical_form: str
    entity_video_count: int


class AddEntityTagResponse(BaseModel):
    """Envelope for :class:`AddEntityTagResult`."""

    data: AddEntityTagResult


class UpdateEntityRequest(BaseModel):
    """Request body for editing an entity's name and/or description.

    PATCH semantics: an omitted field is left unchanged. ``description=""``
    is a valid value that clears the description (distinct from an omitted
    field). At least one of ``canonical_name`` / ``description`` must be
    provided (Feature 057, FR-001, FR-002, FR-013).

    Attributes
    ----------
    canonical_name : str | None
        New verbatim display name (1-500 chars). Omit to leave unchanged.
    description : str | None
        New description (empty string clears it). Omit to leave unchanged.
    entity_type : EntityType | None
        New entity type. Omit to leave unchanged.
    """

    model_config = ConfigDict(strict=True)

    canonical_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="New verbatim entity display name",
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="New entity description (empty string clears it)",
    )
    entity_type: EntityType | None = Field(
        default=None,
        # This model is strict, and strict mode will not coerce the JSON string
        # "place" into the enum — it demands an EntityType instance, which no
        # HTTP client can send. Same opt-out as CorrectionType uses.
        strict=False,
        description="New entity type (e.g. correcting a place filed as a person)",
    )

    @model_validator(mode="after")
    def at_least_one_field(self) -> UpdateEntityRequest:
        """Require at least one editable field to be present."""
        if (
            self.canonical_name is None
            and self.description is None
            and self.entity_type is None
        ):
            raise ValueError(
                "At least one of 'canonical_name', 'description' or "
                "'entity_type' is required"
            )
        return self


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

    segments_scanned: int = Field(..., description="Total transcript segments examined")
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
    dry_run: bool = Field(..., description="Whether this was a dry-run (no writes)")


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


class ScanJobData(BaseModel):
    """State of an asynchronous entity-mention scan job.

    Scan jobs are tracked in an in-memory registry (ephemeral — a job does
    not survive a server restart). This model is returned both when a scan is
    launched (``202``) and when its status is polled.

    Attributes
    ----------
    job_id : str
        Unique identifier for the scan job.
    kind : str
        ``"entity"`` or ``"video"`` — what the scan targets.
    target_id : str
        The entity UUID or video ID being scanned.
    status : str
        ``"running"``, ``"succeeded"``, or ``"failed"``.
    result : ScanResultData | None
        Scan metrics, populated once the job has succeeded.
    error : str | None
        Error message if the job failed.
    started_at : datetime
        When the scan started.
    finished_at : datetime | None
        When the scan reached a terminal state, if it has.
    """

    model_config = ConfigDict(strict=True)

    job_id: str = Field(..., description="Scan job identifier")
    kind: Literal["entity", "video"] = Field(
        ..., description="Whether the scan targets an entity or a video"
    )
    target_id: str = Field(..., description="Entity UUID or video ID being scanned")
    status: Literal["running", "succeeded", "failed"] = Field(
        ..., description="Current job status"
    )
    result: ScanResultData | None = Field(
        None, description="Scan metrics once the job has succeeded"
    )
    error: str | None = Field(None, description="Error message if the job failed")
    started_at: datetime = Field(..., description="When the scan started")
    finished_at: datetime | None = Field(
        None, description="When the scan reached a terminal state"
    )


class ScanJobResponse(BaseModel):
    """Response envelope for scan-job launch (202) and status endpoints.

    Wraps ``ScanJobData`` inside a ``data`` key for consistent API formatting.
    """

    model_config = ConfigDict(strict=True)

    data: ScanJobData


class CooccurringEntity(BaseModel):
    """An entity that shares videos with the subject entity (Feature 062).

    Attributes
    ----------
    entity_id : UUID
        The co-occurring partner.
    entity_type : str
        Carried so the badge renders without a second lookup (FR-031).
    canonical_name : str
        Display name.
    shared_video_count : int
        Distinct videos in which BOTH entities have a qualifying mention.

        This MUST equal the ``pagination.total`` the videos list returns when
        filtered to the same pair under the same evidence scope (FR-024b). The
        two derive from the same qualification rule, but only agree if both
        also apply the same video population -- the videos list excludes
        unavailable videos by default, so this count must too. Showing "261
        shared videos" and then landing on a page that says 258 is the same
        class of defect as two endpoints disagreeing about a video count.
    """

    model_config = ConfigDict(strict=True)

    entity_id: UUID
    entity_type: str
    canonical_name: str
    shared_video_count: int


class CooccurringEntitiesResponse(BaseModel):
    """Response envelope for the appears-with panel."""

    model_config = ConfigDict(strict=True)

    data: list[CooccurringEntity]
