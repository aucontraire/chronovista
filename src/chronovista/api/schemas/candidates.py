"""Response schemas for the read-only candidate-suggestion queue (Feature 096).

The queue is addressed by candidate id; labels are shown but kept out of URLs. This
surface is read-only — approve/reject are CLI-only (FR-016).
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
