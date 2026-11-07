"""
Novel-relationship candidate models (Feature 107).

A relationship candidate is one undirected pair of existing library entities that
co-occur strongly on the title+description channel (lift >= 5 and support >= 5)
with no typed Wikidata tie between them. It is a read-only measurement surface: a
row asserts nothing beyond "candidate." Pairs are stored canonically ordered
(entity_a_id < entity_b_id) so the undirected pair has exactly one representation.

The verdict columns (review_status / review_taxonomy_version /
review_pass_logged_rejections) are forward-compatibility only: the MVP writes no
verdicts. ``review_status`` is a *versioned category*, not a boolean — the concrete
taxonomy (e.g. related-only vs related-or-about) is decided at the confirm/reject
stage and recorded per-row in ``review_taxonomy_version`` — so the field is typed
``str | None`` rather than a hard enum, to keep later taxonomy versions valid
without a migration. The concrete verdict categories are deferred to the
confirm/reject stage (spec §Out of Scope); the MVP emits none, so no enum is
defined here yet.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RelationshipCandidateBase(BaseModel):
    """Shared fields of a novel-relationship candidate (the measured evidence)."""

    entity_a_id: uuid.UUID = Field(
        ..., description="Canonically the smaller of the two entity ids"
    )
    entity_b_id: uuid.UUID = Field(
        ..., description="Canonically the larger of the two entity ids"
    )
    channel: str = Field(
        default="title_description",
        max_length=30,
        description="Co-occurrence channel the pair was measured on",
    )
    shared_video_count: int = Field(
        ..., ge=5, description="Videos where both entities co-occur on the channel (s)"
    )
    lift: float = Field(..., ge=5.0, description="s*N/(A*B) — the ranking key")
    entity_a_video_count: int = Field(
        ..., ge=0, description="A — entity_a's channel video count (provenance)"
    )
    entity_b_video_count: int = Field(
        ..., ge=0, description="B — entity_b's channel video count (provenance)"
    )
    channel_video_universe: int = Field(
        ..., ge=0, description="N — videos with >=1 channel mention at generation time"
    )
    both_typed_eligible: bool = Field(
        default=False,
        description="Both entities carry >=1 tie/attribute property (measured-precision population)",
    )
    kb_corroboration_count: int = Field(
        default=0,
        ge=0,
        description="Count of shared captured properties (excl. P5008/P1343)",
    )
    kb_corroboration_detail: dict[str, Any] = Field(
        default_factory=dict,
        description="Contributing shared property keys, for display",
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="channel, N, corpus_size, generator_version, generated_run_id",
    )

    @model_validator(mode="after")
    def _canonical_order(self) -> RelationshipCandidateBase:
        """Enforce the undirected-pair invariant (mirrors the DB CHECK constraints)."""
        if self.entity_a_id == self.entity_b_id:
            raise ValueError(
                "a relationship candidate cannot pair an entity with itself"
            )
        if self.entity_a_id >= self.entity_b_id:
            raise ValueError(
                "entity_a_id must be < entity_b_id (canonical order); "
                "order the pair before constructing the candidate"
            )
        return self


class RelationshipCandidateCreate(RelationshipCandidateBase):
    """What the generator upserts. Carries no verdict — the generator never judges."""


class RelationshipCandidateUpdate(BaseModel):
    """Refreshable metric fields updated in place on regeneration (never verdicts)."""

    shared_video_count: int | None = Field(default=None, ge=5)
    lift: float | None = Field(default=None, ge=5.0)
    entity_a_video_count: int | None = Field(default=None, ge=0)
    entity_b_video_count: int | None = Field(default=None, ge=0)
    channel_video_universe: int | None = Field(default=None, ge=0)
    both_typed_eligible: bool | None = None
    kb_corroboration_count: int | None = Field(default=None, ge=0)
    kb_corroboration_detail: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None


class RelationshipCandidateRead(RelationshipCandidateBase):
    """A persisted candidate row, including identity, verdict slot, and timestamps."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    review_status: str | None = None
    review_taxonomy_version: str | None = None
    review_pass_logged_rejections: bool | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    last_generated_at: datetime
    created_at: datetime
    updated_at: datetime
