"""Read-only candidate-suggestion queue endpoints (Feature 096).

Exposes the pending queue (ranked + filterable) and a count summary for a future
frontend or onboarding step. Read-only by design (FR-016): approve/reject are
CLI-only, so there are no POST/PATCH/DELETE routes here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_candidate_suggestion_repository,
    get_db,
    require_auth,
)
from chronovista.api.query_protection import run_with_timeout
from chronovista.api.routers.responses import GET_ITEM_ERRORS
from chronovista.api.schemas.candidates import (
    CandidateDetail,
    CandidateListResponse,
    CandidateSummary,
    CandidateSummaryResponse,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.db.models import CandidateSuggestion as CandidateSuggestionDB
from chronovista.exceptions import NotFoundError
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)

router = APIRouter(dependencies=[Depends(require_auth)])

_CHANNEL = "relation"


def _to_detail(row: CandidateSuggestionDB) -> CandidateDetail:
    """Map an ORM candidate row into the API detail schema, field by field."""
    return CandidateDetail(
        id=row.id,
        source_channel=row.source_channel,
        wikidata_qid=row.wikidata_qid,
        label=row.label,
        label_normalized=row.label_normalized,
        type_hint=row.type_hint,
        token_count=row.token_count,
        corroboration_count=row.corroboration_count,
        dangling_edge_count=row.dangling_edge_count,
        salience=row.salience,
        score=row.score,
        triage=row.triage,
        provenance=row.provenance or {},
        possible_duplicate_of_id=row.possible_duplicate_of_id,
        review_status=row.review_status,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        created_entity_id=row.created_entity_id,
        last_generated_at=row.last_generated_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/candidates",
    response_model=CandidateListResponse,
    summary="List pending candidate suggestions, ranked",
)
async def list_candidates(
    triage: str | None = Query(
        None, description="worth_review | likely_eliminable | grounds_nowhere"
    ),
    type_hint: str | None = Query(None, description="Filter by coarse type hint"),
    min_token_count: int | None = Query(
        None, ge=1, description="Hide names with fewer tokens"
    ),
    possible_duplicate: bool | None = Query(
        None, description="Only candidates flagged as a possible duplicate"
    ),
    source_channel: str = Query(_CHANNEL, description="Discovery channel"),
    sort: str = Query("score", description="score | corroboration | salience"),
    limit: int = Query(25, ge=1, le=100, description="Candidates per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
    repo: CandidateSuggestionRepository = Depends(get_candidate_suggestion_repository),
) -> CandidateListResponse:
    """Return a page of pending candidates ordered by plausibility (FR-007, FR-016)."""
    rows, total = await run_with_timeout(
        repo.list_pending(
            session,
            source_channel=source_channel,
            triage=triage,
            type_hint=type_hint,
            min_token_count=min_token_count,
            possible_duplicate=possible_duplicate,
            sort=sort,
            skip=offset,
            limit=limit,
        ),
        operation="candidate list",
        session=session,
    )
    return CandidateListResponse(
        data=[_to_detail(r) for r in rows],
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + limit < total,
        ),
    )


@router.get(
    "/candidates/summary",
    response_model=CandidateSummaryResponse,
    summary="Candidate queue counts by status and (pending) triage",
)
async def candidate_summary(
    source_channel: str = Query(_CHANNEL, description="Discovery channel"),
    session: AsyncSession = Depends(get_db),
    repo: CandidateSuggestionRepository = Depends(get_candidate_suggestion_repository),
) -> CandidateSummaryResponse:
    """Return queue counts — shaped so an onboarding step can key off a single number."""
    counts = await run_with_timeout(
        repo.counts_by_status(session, source_channel=source_channel),
        operation="candidate summary",
        session=session,
    )
    return CandidateSummaryResponse(
        data=CandidateSummary(
            source_channel=source_channel,
            pending=counts.get("pending", 0),
            approved=counts.get("approved", 0),
            rejected=counts.get("rejected", 0),
            superseded=counts.get("superseded", 0),
            worth_review=counts.get("worth_review", 0),
            likely_eliminable=counts.get("likely_eliminable", 0),
            grounds_nowhere=counts.get("grounds_nowhere", 0),
        )
    )


@router.get(
    "/candidates/{candidate_id}",
    response_model=CandidateDetail,
    responses=GET_ITEM_ERRORS,
    summary="One candidate suggestion (any status)",
)
async def get_candidate(
    candidate_id: str = Path(..., description="Candidate suggestion UUID"),
    session: AsyncSession = Depends(get_db),
    repo: CandidateSuggestionRepository = Depends(get_candidate_suggestion_repository),
) -> CandidateDetail:
    """Return one candidate by id, including provenance and verdict fields."""
    try:
        parsed_id = uuid.UUID(candidate_id)
    except ValueError as exc:
        raise NotFoundError(
            resource_type="CandidateSuggestion", identifier=candidate_id
        ) from exc
    row = await run_with_timeout(
        repo.get(session, parsed_id),
        operation="candidate detail",
        session=session,
    )
    if row is None:
        raise NotFoundError(
            resource_type="CandidateSuggestion", identifier=candidate_id
        )
    return _to_detail(row)
