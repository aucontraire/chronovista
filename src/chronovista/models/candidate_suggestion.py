"""
Candidate suggestion models for seed-and-grow entity discovery (Feature 096).

A candidate suggestion is a proposed, not-yet-created entity discovered by
following a grounded entity's stored relationship targets, grounded against the
local corpus, scored, and queued for human review. Approving one creates a
grounded named entity through the existing creation path.

The store is channel-agnostic: ``source_channel`` discriminates how a candidate
was discovered (only the relationship channel is implemented) and ``provenance``
holds the channel-specific detail, so future producers (tag-seed cold-start,
shared-category) reuse the same store and review machinery.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import EntityType, ReviewStatus, SourceChannel, TriageCategory

_QID_RE = re.compile(r"^Q\d+$")


class RelationCandidateRow(BaseModel):
    """One emitted relation-channel candidate before grounding/scoring (Feature 096).

    The raw output of the emit query: a distinct Wikidata target not yet in the
    library, aggregated across the seeds that point at it. Grounding, scoring, and
    triage are applied by the service to turn this into a ``CandidateSuggestionCreate``.
    """

    wikidata_qid: str = Field(
        ..., description="Target Wikidata QID (not yet a library entity)"
    )
    label: str = Field(..., description="Target label from the stored relation values")
    corroboration_count: int = Field(
        ..., ge=1, description="Distinct seeds pointing at it"
    )
    dangling_edge_count: int = Field(
        ..., ge=1, description="Relation edges its creation resolves"
    )
    relations: list[str] = Field(
        ..., description="Relation field names that produced it"
    )
    seed_entity_ids: list[uuid.UUID] = Field(
        ..., description="Distinct seed entities pointing at it"
    )

    model_config = ConfigDict(frozen=True)


class CandidateSuggestionBase(BaseModel):
    """Base model for a candidate suggestion."""

    source_channel: SourceChannel = Field(
        default=SourceChannel.RELATION,
        description="Discovery channel that produced this candidate",
    )
    wikidata_qid: str = Field(
        ...,
        min_length=2,
        max_length=32,
        description="Candidate's external (Wikidata) identity",
    )
    label: str = Field(
        ..., min_length=1, max_length=500, description="Display label of the candidate"
    )
    label_normalized: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Normalized label (collision + grouping key)",
    )
    type_hint: EntityType = Field(
        ...,
        description="Coarse type derived from the relationship (advisory; OTHER when ambiguous)",
    )
    token_count: int = Field(
        ..., ge=1, description="Whitespace-separated tokens in the normalized label"
    )
    corroboration_count: int = Field(
        ..., ge=1, description="Distinct seeds pointing at this candidate"
    )
    dangling_edge_count: int = Field(
        ..., ge=0, description="Dangling relationship edges creating it would resolve"
    )
    salience: int = Field(
        ...,
        ge=0,
        description="Distinct corpus videos (title+description) matching the name",
    )
    score: float = Field(
        ..., ge=0, allow_inf_nan=False, description="Plausibility score (ranking only)"
    )
    triage: TriageCategory = Field(..., description="Advisory triage bucket")
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="Channel-specific provenance (relation channel: seed ids + relation names)",
    )
    possible_duplicate_of_id: uuid.UUID | None = Field(
        default=None,
        description="Ungrounded entity whose name collides with this candidate (FR-011a)",
    )
    review_status: ReviewStatus = Field(
        default=ReviewStatus.PENDING, description="Review lifecycle state"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )

    @model_validator(mode="after")
    def type_hint_must_be_entity_valid(self) -> CandidateSuggestionBase:
        """Reject tag-only types for ``type_hint`` (FR-009 flows it to entity_type).

        ``topic`` and ``descriptor`` are tag-only types that ``named_entities``'
        ``chk_entity_type_valid`` forbids; since approval copies ``type_hint`` into
        the created entity's ``entity_type``, a candidate must never carry them.
        """
        if self.type_hint in (EntityType.TOPIC, EntityType.DESCRIPTOR):
            raise ValueError(
                "type_hint must be an entity-valid type (not topic/descriptor)"
            )
        return self


class CandidateSuggestionCreate(CandidateSuggestionBase):
    """Model for creating (or upserting) a candidate suggestion."""

    @model_validator(mode="after")
    def validate_qid_provenance_and_status(self) -> CandidateSuggestionCreate:
        """Validate QID shape, relation-channel provenance, and pending-on-create."""
        if not _QID_RE.match(self.wikidata_qid):
            raise ValueError("wikidata_qid must match '^Q\\d+$'")
        if self.source_channel == SourceChannel.RELATION and not self.provenance.get(
            "seed_entity_ids"
        ):
            raise ValueError(
                "relation-channel candidates require at least one seed in provenance"
            )
        if self.review_status != ReviewStatus.PENDING:
            raise ValueError("a newly created candidate must be pending")
        return self


class CandidateSuggestionUpdate(BaseModel):
    """Model for updating a candidate suggestion (PATCH-style, all optional)."""

    # Refreshable generation signals (FR-014)
    label: str | None = Field(default=None, min_length=1, max_length=500)
    label_normalized: str | None = Field(default=None, min_length=1, max_length=500)
    type_hint: EntityType | None = None
    token_count: int | None = Field(default=None, ge=1)
    corroboration_count: int | None = Field(default=None, ge=1)
    dangling_edge_count: int | None = Field(default=None, ge=0)
    salience: int | None = Field(default=None, ge=0)
    score: float | None = Field(default=None, ge=0)
    triage: TriageCategory | None = None
    provenance: dict[str, Any] | None = None
    possible_duplicate_of_id: uuid.UUID | None = None
    last_generated_at: datetime | None = None
    # Verdict fields
    review_status: ReviewStatus | None = None
    reviewed_by: str | None = Field(default=None, max_length=255)
    reviewed_at: datetime | None = None
    created_entity_id: uuid.UUID | None = None

    model_config = ConfigDict(
        validate_assignment=True,
    )


class CandidateSuggestion(CandidateSuggestionBase):
    """Full candidate suggestion model with identifiers, verdict, and timestamps."""

    id: uuid.UUID = Field(..., description="Candidate suggestion UUID (UUIDv7)")
    reviewed_by: str | None = Field(
        default=None,
        max_length=255,
        description="Operator identity that set the verdict",
    )
    reviewed_at: datetime | None = Field(
        default=None, description="When the verdict was set"
    )
    created_entity_id: uuid.UUID | None = Field(
        default=None, description="Entity created on approval"
    )
    last_generated_at: datetime = Field(
        ..., description="When a generation run last refreshed this candidate"
    )
    created_at: datetime = Field(..., description="When the record was created")
    updated_at: datetime = Field(..., description="When the record was last updated")

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )
