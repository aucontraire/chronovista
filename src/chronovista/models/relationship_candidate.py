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
from enum import Enum
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
    lift: float | None = Field(
        default=None,
        ge=5.0,
        description=(
            "s*N/(A*B) — the title/description ranking key. None for a transcript-only "
            "parent (which ranks by support); for a dual-signal pair it holds the "
            "title/description lift. The lift↔signal coupling is enforced per-signal on "
            "the child (RelationshipCandidateSignal), not here."
        ),
    )
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


class CandidateSignal(str, Enum):
    """The co-occurrence channel a candidate's evidence came from (Feature 116).

    One pair can carry evidence from more than one signal; each signal's evidence is a
    separate child row (``relationship_candidate_signals``), so a third signal is additive —
    no migration. The values are the channel strings stored on
    ``relationship_candidates.channel`` and matched by the per-channel read funnel
    (``RelationshipCandidateRepository.list_ranked(signal=...)``).
    """

    TITLE_DESCRIPTION = "title_description"
    TRANSCRIPT = "transcript"


class RelationshipCandidateSignalBase(BaseModel):
    """One signal's evidence for a candidate pair (Option-C child, Feature 116).

    Per-signal because the two channels are not the same shape. The title/description signal
    ranks by ``lift``; the transcript signal ranks by ``support`` (close co-mention count) and
    carries no lift (``lift`` is NULL for transcript). ``support`` is the signal's native
    magnitude — a shared-video count for title/description, a 30s close-co-mention count for
    transcript. This model enforces the *structural* invariant (which fields each signal
    carries); the numeric qualifying floors (title/desc support ≥ 5 ∧ lift ≥ 5; the tuned
    transcript bar, FR-022) are DB CHECK constraints, not model validation, because the
    transcript floor is still being calibrated.
    """

    candidate_id: uuid.UUID = Field(
        ..., description="FK to the parent relationship_candidates row"
    )
    signal: CandidateSignal = Field(
        ..., description="Which channel this evidence came from"
    )
    support: int = Field(
        ...,
        ge=1,
        description="Native magnitude: shared videos (title/desc) or close-30s count (transcript)",
    )
    lift: float | None = Field(
        default=None,
        ge=5.0,
        description="title/description lift; NULL for transcript (it ranks by proximity, not lift)",
    )
    min_gap_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Transcript only — the closest co-mention gap in seconds; NULL otherwise",
    )
    entity_a_video_count: int = Field(
        ..., ge=0, description="A — provenance for this signal's denominator"
    )
    entity_b_video_count: int = Field(
        ..., ge=0, description="B — provenance for this signal's denominator"
    )
    signal_universe: int = Field(
        ...,
        ge=0,
        description="N — videos with >=1 mention on this signal at generation time",
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
        description="channel, N, generator_version, run id, outer window",
    )

    @model_validator(mode="after")
    def _lift_matches_signal(self) -> RelationshipCandidateSignalBase:
        """Encode the definitional per-signal shape: title/description has a lift, transcript
        does not (it ranks by proximity). Catches a generator that mixes the two channels'
        evidence — the structural analogue of the parent's canonical-order check."""
        if self.signal is CandidateSignal.TITLE_DESCRIPTION and self.lift is None:
            raise ValueError("a title_description signal must carry a lift (>= 5)")
        if self.signal is CandidateSignal.TRANSCRIPT and self.lift is not None:
            raise ValueError(
                "a transcript signal must not carry a lift (it ranks by proximity)"
            )
        return self


class RelationshipCandidateSignalCreate(RelationshipCandidateSignalBase):
    """What the generator upserts for one (pair, signal)."""


class RelationshipCandidateSignalRead(RelationshipCandidateSignalBase):
    """A persisted signal-evidence row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
