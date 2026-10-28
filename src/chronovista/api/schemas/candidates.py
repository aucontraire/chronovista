"""Schemas for the candidate-suggestion queue (Features 096, 097).

The queue is addressed by candidate id; labels are shown but kept out of URLs.
Feature 096 added the read schemas; Feature 097 adds the write/action schemas
(verdicts, background generation runs, and the tag footprint).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from chronovista.api.schemas.responses import PaginationMeta


class CandidateDetail(BaseModel):
    """One candidate suggestion with its signals, provenance, and review state."""

    model_config = ConfigDict(strict=True)

    id: UUID
    source_channel: str
    wikidata_qid: str
    label: str
    label_normalized: str
    type_hint: str
    token_count: int
    corroboration_count: int
    dangling_edge_count: int
    salience: int
    score: float
    triage: str
    provenance: dict[str, object]
    possible_duplicate_of_id: UUID | None
    review_status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_entity_id: UUID | None
    last_generated_at: datetime
    created_at: datetime
    updated_at: datetime


class CandidateListResponse(BaseModel):
    """Paginated response envelope for the pending-candidate queue."""

    model_config = ConfigDict(strict=True)

    data: list[CandidateDetail]
    pagination: PaginationMeta


class CandidateSummary(BaseModel):
    """Queue counts by review status, plus the pending triage distribution (FR-016)."""

    model_config = ConfigDict(strict=True)

    source_channel: str
    pending: int
    approved: int
    rejected: int
    superseded: int
    worth_review: int
    likely_eliminable: int
    grounds_nowhere: int


class CandidateSummaryResponse(BaseModel):
    """Response envelope for the queue summary."""

    model_config = ConfigDict(strict=True)

    data: CandidateSummary


class GenerationRunResponse(BaseModel):
    """Status + determinate progress of a candidate generation run (Feature 097)."""

    model_config = ConfigDict(strict=True)

    id: UUID
    source_channel: str
    status: str
    progress_percent: int
    seeds_grounded: int
    candidates_discovered: int
    candidates_upserted: int
    superseded: int
    pending_total: int
    by_triage: dict[str, int]
    empty_reason: str | None
    error: str | None
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class GenerationStatusResponse(BaseModel):
    """Envelope for the generation status read; ``run`` is null when none exists.

    A null ``run`` is the defined "no run has ever occurred" state, distinct from
    a completed empty-result run (which carries an ``empty_reason``) — FR-023.
    """

    model_config = ConfigDict(strict=True)

    run: GenerationRunResponse | None


class TagFootprintMatch(BaseModel):
    """A name-matching canonical tag and the videos a link would newly associate."""

    model_config = ConfigDict(strict=True)

    normalized_form: str
    would_newly_associate: int
    owned_by_entity_id: UUID | None


class TagFootprintResponse(BaseModel):
    """Footprint of claimable canonical tags for a candidate/entity (Feature 097)."""

    model_config = ConfigDict(strict=True)

    matches: list[TagFootprintMatch]


class TagLinkRequest(BaseModel):
    """Request to link an entity to a canonical tag (Feature 097)."""

    model_config = ConfigDict(strict=True)

    normalized_form: str
    entity_type: str


class TagLinkResponse(BaseModel):
    """Outcome of linking an entity to a canonical tag (Feature 097).

    Linking claims an unclaimed tag; a tag already linked to another entity is
    refused (409), so there is no ownership-reassignment field — moving a tag
    between entities is out of scope (see the feature spec).
    """

    model_config = ConfigDict(strict=True)

    normalized_form: str
    linked_entity_id: UUID


class CandidateVerdictResponse(BaseModel):
    """Outcome of an approve/reject action on a candidate (Feature 097).

    ``outcome`` is one of ``approved`` / ``rejected`` / ``superseded`` / ``failed``
    (the service's ``not_found`` outcome is surfaced as HTTP 404 instead, so it
    never appears here). ``created_entity_id`` is set only when an approval
    created a grounded entity.
    """

    model_config = ConfigDict(strict=True)

    outcome: str
    candidate_id: UUID
    created_entity_id: UUID | None = None
    detail: str | None = None
