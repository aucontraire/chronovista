"""Candidate-suggestion queue endpoints (Features 096, 097).

Exposes the pending queue (ranked + filterable) and a count summary (Feature 096,
read-only), plus the Feature-097 write actions: approve/reject a candidate in the
browser. Approval wraps the existing ``CandidateSuggestionService`` and schedules
enrichment as a detached task so the request is never held across its network
calls (FR-004).
"""

from __future__ import annotations

import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_candidate_generation_run_repository,
    get_candidate_suggestion_repository,
    get_candidate_suggestion_service,
    get_db,
    get_tag_management_service,
    require_auth,
    require_local_identity,
)
from chronovista.api.query_protection import run_with_timeout
from chronovista.api.routers.responses import GET_ITEM_ERRORS
from chronovista.api.schemas.candidates import (
    CandidateDetail,
    CandidateListResponse,
    CandidateSummary,
    CandidateSummaryResponse,
    CandidateVerdictResponse,
    GenerationRunResponse,
    GenerationStatusResponse,
    TagFootprintMatch,
    TagFootprintResponse,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.config.database import db_manager
from chronovista.db.models import CandidateSuggestion as CandidateSuggestionDB
from chronovista.exceptions import ConflictError, NotFoundError
from chronovista.models.candidate_generation_run import CandidateGenerationRun
from chronovista.repositories.candidate_generation_run_repository import (
    CandidateGenerationRunRepository,
)
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.candidate_suggestion_service import (
    CandidateSuggestionService,
)
from chronovista.services.entity_enrichment_service import (
    EntityEnrichmentService,
    get_enrichment_service,
)
from chronovista.services.tag_management import TagManagementService

router = APIRouter(dependencies=[Depends(require_auth)])

_CHANNEL = "relation"

# Retained handles for detached on-approval enrichment tasks (FR-004, research D1).
# A bare ``asyncio.create_task`` handle can be garbage-collected mid-flight; the set
# + done-callback keep it alive until completion (mirrors ``entity_mentions``).
_enrichment_tasks: set[asyncio.Task[None]] = set()


def _schedule_enrichment(
    service: EntityEnrichmentService, entity_id: uuid.UUID, qid: str
) -> None:
    """Schedule the on-approval property fetch as a detached, GC-safe background task.

    ``EntityEnrichmentService`` opens its own session, so the request's session is
    never held across the enrichment network calls (the held-session deadlock
    class). ``entity_id`` is normalized to a stdlib ``uuid.UUID``.
    """
    normalized_id = uuid.UUID(str(entity_id))
    task = asyncio.create_task(service.enrich_on_approval(normalized_id, qid))
    _enrichment_tasks.add(task)
    task.add_done_callback(_enrichment_tasks.discard)


# Retained handles for the detached generation sweep (FR-022), GC-safe like the
# enrichment tasks above.
_generation_tasks: set[asyncio.Task[None]] = set()

# Write a progress heartbeat at least this often even when the percent has not
# advanced, so a slow phase is not falsely reaped as stale (FR-025). Comfortably
# below the staleness cutoff.
_HEARTBEAT_SECONDS = 30.0


def _run_to_response(run: CandidateGenerationRun) -> GenerationRunResponse:
    """Map the full run model to its API response shape."""
    return GenerationRunResponse(
        id=run.id,
        source_channel=run.source_channel.value,
        status=run.status.value,
        progress_percent=run.progress_percent,
        seeds_grounded=run.seeds_grounded,
        candidates_discovered=run.candidates_discovered,
        candidates_upserted=run.candidates_upserted,
        superseded=run.superseded,
        pending_total=run.pending_total,
        by_triage=run.by_triage,
        empty_reason=run.empty_reason,
        error=run.error,
        started_at=run.started_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
    )


async def _run_generation(run_id: uuid.UUID) -> None:
    """Execute the generation sweep in its own sessions (detached task, FR-022).

    Progress heartbeats commit in short-lived sessions so a concurrent status poll
    sees the advancing percentage; the candidate upserts commit once at the end
    (FR-027). Any failure marks the run failed (FR-025 / graceful degradation).
    """
    session_factory = db_manager.get_session_factory()
    run_repo = CandidateGenerationRunRepository()
    service = CandidateSuggestionService(
        candidate_repo=CandidateSuggestionRepository(),
        entity_repo=NamedEntityRepository(),
        video_repo=VideoRepository(),
        alias_repo=EntityAliasRepository(),
        enrichment=None,
    )

    last_pct = 0
    last_write = 0.0

    async def on_progress(done: int, total: int) -> None:
        nonlocal last_pct, last_write
        pct = min(99, (done * 100) // total) if total else 0
        now = time.monotonic()
        # Write on a percent advance, or on a time heartbeat so a slow phase
        # keeps the run fresh (FR-025). `pct` is non-decreasing.
        if pct <= last_pct and (now - last_write) < _HEARTBEAT_SECONDS:
            return
        last_pct = max(last_pct, pct)
        last_write = now
        async with session_factory() as heartbeat_session:
            await run_repo.record_progress(
                heartbeat_session, run_id=run_id, progress_percent=last_pct
            )
            await heartbeat_session.commit()

    try:
        async with session_factory() as gen_session:
            summary = await service.generate(gen_session, progress=on_progress)
            await gen_session.commit()
        async with session_factory() as done_session:
            await run_repo.finish(
                done_session,
                run_id=run_id,
                candidates_discovered=summary.candidates_discovered,
                candidates_upserted=summary.candidates_upserted,
                superseded=summary.superseded,
                pending_total=summary.pending_total,
                by_triage=summary.by_triage,
                empty_reason=summary.empty_reason,
            )
            await done_session.commit()
    except Exception as exc:  # defensive: any sweep failure is surfaced as a failed run
        async with session_factory() as fail_session:
            await run_repo.fail(fail_session, run_id=run_id, error=str(exc)[:1000])
            await fail_session.commit()


def _launch_generation(run_id: uuid.UUID) -> None:
    """Schedule the generation sweep as a detached, GC-safe background task."""
    task = asyncio.create_task(_run_generation(run_id))
    _generation_tasks.add(task)
    task.add_done_callback(_generation_tasks.discard)


def _parse_candidate_id(candidate_id: str) -> uuid.UUID:
    """Parse a candidate id to UUID, raising NotFoundError on a malformed value."""
    try:
        return uuid.UUID(candidate_id)
    except ValueError as exc:
        raise NotFoundError(
            resource_type="CandidateSuggestion", identifier=candidate_id
        ) from exc


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
    parsed_id = _parse_candidate_id(candidate_id)
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


@router.post(
    "/candidates/{candidate_id}/approve",
    response_model=CandidateVerdictResponse,
    responses=GET_ITEM_ERRORS,
    summary="Approve a candidate — create a grounded entity",
)
async def approve_candidate(
    candidate_id: str = Path(..., description="Candidate suggestion UUID"),
    session: AsyncSession = Depends(get_db),
    service: CandidateSuggestionService = Depends(get_candidate_suggestion_service),
    repo: CandidateSuggestionRepository = Depends(get_candidate_suggestion_repository),
    enrichment_service: EntityEnrichmentService = Depends(get_enrichment_service),
    reviewed_by: str = Depends(require_local_identity),
) -> CandidateVerdictResponse:
    """Approve a pending candidate (FR-001/003/004/005/010).

    Wraps ``CandidateSuggestionService.approve`` (built with ``enrichment=None``),
    which commits the entity and verdict; enrichment is then scheduled as a
    detached task so the request is never held across its network calls (FR-004).
    An already-decided candidate yields ``failed`` (compare-and-set), a missing one
    a 404, an already-grounded identity/name collision ``superseded``.
    """
    parsed_id = _parse_candidate_id(candidate_id)
    result = await service.approve(
        session, candidate_id=parsed_id, reviewed_by=reviewed_by
    )
    if result.outcome == "not_found":
        raise NotFoundError(
            resource_type="CandidateSuggestion", identifier=candidate_id
        )
    if result.outcome == "approved" and result.created_entity_id is not None:
        row = await repo.get(session, parsed_id)
        if row is not None:
            _schedule_enrichment(
                enrichment_service, result.created_entity_id, row.wikidata_qid
            )
    return CandidateVerdictResponse(
        outcome=result.outcome,
        candidate_id=result.candidate_id,
        created_entity_id=result.created_entity_id,
        detail=result.detail,
    )


@router.post(
    "/candidates/generation",
    response_model=GenerationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_local_identity)],
    summary="Start a background candidate generation run",
)
async def start_generation(
    session: AsyncSession = Depends(get_db),
    run_repo: CandidateGenerationRunRepository = Depends(
        get_candidate_generation_run_repository
    ),
) -> GenerationRunResponse:
    """Start a generation sweep as a detached background task (FR-020/022/024).

    At most one run per channel: if one is active, returns 409 with the active run
    so the UI can show its progress rather than starting a second sweep. The
    running row is committed before the task launches so the detached sweep and
    concurrent status polls observe it.
    """
    run = await run_repo.start_run(session, source_channel=_CHANNEL)
    if run is None:
        active = await run_repo.get_active(session, source_channel=_CHANNEL)
        if active is not None and run_repo.is_stale(active):
            # Self-heal: reap a crashed/stale run (FR-025) so the slot is not
            # blocked forever, then retry the guarded insert once.
            await run_repo.fail(
                session, run_id=active.id, error="Run stalled (no heartbeat)."
            )
            await session.commit()
            run = await run_repo.start_run(session, source_channel=_CHANNEL)
        if run is None:
            raise ConflictError(
                message="A generation run is already in progress.",
                details={"code": "GENERATION_ALREADY_RUNNING"},
            )
    await session.commit()
    _launch_generation(run.id)
    return _run_to_response(run)


@router.get(
    "/candidates/generation/status",
    response_model=GenerationStatusResponse,
    summary="Current or latest generation run status",
)
async def generation_status(
    session: AsyncSession = Depends(get_db),
    run_repo: CandidateGenerationRunRepository = Depends(
        get_candidate_generation_run_repository
    ),
) -> GenerationStatusResponse:
    """Return the active run, else the latest (FR-023).

    A running run whose heartbeat is stale is reaped to ``failed`` on read
    (FR-025); a null ``run`` is the defined "no run yet" state.
    """
    active = await run_repo.get_active(session, source_channel=_CHANNEL)
    if active is not None and run_repo.is_stale(active):
        await run_repo.fail(
            session, run_id=active.id, error="Run stalled (no heartbeat)."
        )
        await session.commit()
        active = None
    run = active or await run_repo.get_latest(session, source_channel=_CHANNEL)
    return GenerationStatusResponse(
        run=_run_to_response(run) if run is not None else None
    )


@router.post(
    "/candidates/{candidate_id}/reject",
    response_model=CandidateVerdictResponse,
    responses=GET_ITEM_ERRORS,
    summary="Reject a candidate",
)
async def reject_candidate(
    candidate_id: str = Path(..., description="Candidate suggestion UUID"),
    session: AsyncSession = Depends(get_db),
    service: CandidateSuggestionService = Depends(get_candidate_suggestion_service),
    reviewed_by: str = Depends(require_local_identity),
) -> CandidateVerdictResponse:
    """Reject a pending candidate (FR-002/003/010).

    An already-decided candidate yields ``failed``; a missing one a 404.
    """
    parsed_id = _parse_candidate_id(candidate_id)
    result = await service.reject(
        session, candidate_id=parsed_id, reviewed_by=reviewed_by
    )
    if result.outcome == "not_found":
        raise NotFoundError(
            resource_type="CandidateSuggestion", identifier=candidate_id
        )
    return CandidateVerdictResponse(
        outcome=result.outcome,
        candidate_id=result.candidate_id,
        created_entity_id=result.created_entity_id,
        detail=result.detail,
    )


@router.get(
    "/candidates/{candidate_id}/tag-footprint",
    response_model=TagFootprintResponse,
    responses=GET_ITEM_ERRORS,
    summary="Canonical-tag footprint a candidate would claim if approved (preview)",
)
async def candidate_tag_footprint(
    candidate_id: str = Path(..., description="Candidate suggestion UUID"),
    session: AsyncSession = Depends(get_db),
    repo: CandidateSuggestionRepository = Depends(get_candidate_suggestion_repository),
    tag_service: TagManagementService = Depends(get_tag_management_service),
) -> TagFootprintResponse:
    """Pre-approval preview (FR-050): if this candidate were approved, how many
    videos would a canonical-tag link newly associate, beyond the derived
    alias-tag coverage its name earns for free. Read-only; mutates nothing."""
    parsed_id = _parse_candidate_id(candidate_id)
    candidate = await repo.get(session, parsed_id)
    if candidate is None:
        raise NotFoundError(
            resource_type="CandidateSuggestion", identifier=candidate_id
        )
    matches = await tag_service.tag_footprint(
        session, normalized_form=candidate.label_normalized
    )
    return TagFootprintResponse(
        matches=[
            TagFootprintMatch(
                normalized_form=m.normalized_form,
                would_newly_associate=m.would_newly_associate,
                owned_by_entity_id=m.owned_by_entity_id,
            )
            for m in matches
        ]
    )
