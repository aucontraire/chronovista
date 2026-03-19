"""Batch correction endpoints for bulk find-replace operations on transcripts.

This module handles the REST API endpoints for batch correction operations,
including previewing matches, applying corrections in bulk, rebuilding
full transcript text from corrected segments, listing batches, and
reverting entire batches.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.api.deps import get_db, require_auth
from sqlalchemy import case, func, select

from chronovista.api.schemas.batch_corrections import (
    BatchApplyRequest,
    BatchApplyResult,
    BatchListItemResponse,
    BatchPreviewRequest,
    BatchPreviewResponse,
    BatchRebuildRequest,
    BatchRebuildResult,
    BatchRevertResponse,
    CrossSegmentCandidateResponse,
    DiffErrorPatternResponse,
)
from chronovista.api.schemas.responses import ApiResponse, PaginationMeta
from chronovista.exceptions import APIValidationError, ConflictError, NotFoundError
from chronovista.models.correction_actors import ACTOR_USER_BATCH
from chronovista.models.enums import CorrectionType
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.batch_correction_models import BatchCorrectionResult
from chronovista.services.batch_correction_service import (
    BatchCorrectionService,
    word_level_diff,
)
from chronovista.services.cross_segment_discovery import CrossSegmentDiscovery
from chronovista.utils.text import strip_boundary_punctuation
from chronovista.services.transcript_correction_service import (
    TranscriptCorrectionService,
)

router = APIRouter(prefix="", tags=["batch-corrections"], dependencies=[Depends(require_auth)])

# Module-level service instantiation (singleton pattern)
_correction_repo = TranscriptCorrectionRepository()
_segment_repo = TranscriptSegmentRepository()
_transcript_repo = VideoTranscriptRepository()
_correction_service = TranscriptCorrectionService(
    correction_repo=_correction_repo,
    segment_repo=_segment_repo,
    transcript_repo=_transcript_repo,
)
_batch_service = BatchCorrectionService(
    correction_service=_correction_service,
    segment_repo=_segment_repo,
    correction_repo=_correction_repo,
)


def _map_batch_error(error: ValueError) -> APIValidationError:
    """Map a ValueError from the batch correction service to an APIValidationError.

    Parameters
    ----------
    error : ValueError
        The ValueError raised by the batch correction service.

    Returns
    -------
    APIValidationError
        An API validation error with the appropriate error code.
    """
    msg = str(error)
    exc = APIValidationError(message=msg)
    if "timeout" in msg.lower():
        exc._error_code_value = "PATTERN_TIMEOUT"
    elif "invalid" in msg.lower() or "pattern" in msg.lower():
        exc._error_code_value = "INVALID_PATTERN"
    return exc


@router.post(
    "/preview",
    response_model=ApiResponse[BatchPreviewResponse],
    status_code=200,
    summary="Preview batch find-replace matches",
)
async def preview_batch_corrections(
    request: BatchPreviewRequest,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[BatchPreviewResponse]:
    """Preview segments matching a find-replace pattern.

    Searches transcript segments for matches against the provided pattern
    and returns proposed replacements without applying any changes.
    Results are capped at 100 matches.

    Parameters
    ----------
    request : BatchPreviewRequest
        The search pattern, replacement text, and optional scope filters.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[BatchPreviewResponse]
        Matching segments with proposed replacements.

    Raises
    ------
    APIValidationError
        If the regex pattern is invalid or times out (422).
    """
    try:
        matches, total_count = await _batch_service.find_matching_segments(
            session,
            pattern=request.pattern,
            replacement=request.replacement,
            regex=request.is_regex,
            case_insensitive=request.case_insensitive,
            language=request.language,
            channel=request.channel_id,
            video_ids=request.video_ids,
            cross_segment=request.cross_segment,
            max_matches=200,
        )
    except ValueError as e:
        raise _map_batch_error(e) from e

    # Cap returned matches at 100
    capped_matches = matches[:100]

    response_data = BatchPreviewResponse(
        matches=capped_matches,
        total_count=total_count,
        pattern=request.pattern,
        replacement=request.replacement,
        is_regex=request.is_regex,
        case_insensitive=request.case_insensitive,
        cross_segment=request.cross_segment,
    )
    return ApiResponse[BatchPreviewResponse](data=response_data)


@router.post(
    "/apply",
    response_model=ApiResponse[BatchApplyResult],
    status_code=200,
    summary="Apply batch find-replace corrections",
)
async def apply_batch_corrections(
    request: BatchApplyRequest,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[BatchApplyResult]:
    """Apply find-replace corrections to a set of segment IDs.

    Applies the provided pattern/replacement to the specified segments
    previously identified through the preview endpoint.

    Parameters
    ----------
    request : BatchApplyRequest
        The pattern, replacement, segment IDs, and correction metadata.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[BatchApplyResult]
        Summary of applied, skipped, and failed corrections.

    Raises
    ------
    APIValidationError
        If the regex pattern is invalid or times out (422).
    """
    # Convert string correction_type to enum
    try:
        correction_type_enum = CorrectionType(request.correction_type)
    except ValueError:
        exc = APIValidationError(
            message=f"Invalid correction_type: {request.correction_type}"
        )
        exc._error_code_value = "VALIDATION_ERROR"
        raise exc

    # Generate a batch_id so all corrections from this API call share
    # the same provenance identifier (mirrors CLI find_and_replace behaviour).
    batch_id = uuid.UUID(bytes=uuid7().bytes)

    try:
        result = await _batch_service.apply_to_segments(
            session,
            pattern=request.pattern,
            replacement=request.replacement,
            segment_ids=request.segment_ids,
            regex=request.is_regex,
            case_insensitive=request.case_insensitive,
            cross_segment=request.cross_segment,
            correction_type=correction_type_enum,
            correction_note=request.correction_note,
            auto_rebuild=request.auto_rebuild,
            corrected_by_user_id=ACTOR_USER_BATCH,
            entity_id=request.entity_id,
            batch_id=batch_id,
        )
    except ValueError as e:
        raise _map_batch_error(e) from e

    return ApiResponse[BatchApplyResult](data=result)


@router.post(
    "/rebuild-text",
    response_model=ApiResponse[BatchRebuildResult],
    status_code=200,
    summary="Rebuild full transcript text for videos",
)
async def rebuild_text(
    request: BatchRebuildRequest,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[BatchRebuildResult]:
    """Rebuild full transcript text from corrected segments.

    Re-concatenates the effective text of all segments for each specified
    video and updates the stored transcript text.

    Parameters
    ----------
    request : BatchRebuildRequest
        The video IDs to rebuild.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[BatchRebuildResult]
        Summary of rebuilt and failed videos.
    """
    # rebuild_text returns (total_rebuilt, total_segments) when dry_run=False
    result = await _batch_service.rebuild_text(
        session,
        video_ids=request.video_ids,
    )

    # Adapt the tuple return value to BatchRebuildResult
    if isinstance(result, tuple):
        total_rebuilt, _total_segments = result
        response_data = BatchRebuildResult(
            videos_rebuilt=total_rebuilt,
            video_ids=request.video_ids,
            failed_video_ids=[],
        )
    else:
        # dry_run=True returns list[dict], but we don't use dry_run here
        response_data = BatchRebuildResult(
            videos_rebuilt=len(result),
            video_ids=[d.get("video_id", "") for d in result],
            failed_video_ids=[],
        )

    return ApiResponse[BatchRebuildResult](data=response_data)


@router.get(
    "/batches",
    response_model=ApiResponse[list[BatchListItemResponse]],
    status_code=200,
    summary="List batch correction groups",
)
async def list_batches(
    offset: int = Query(default=0, ge=0, description="Number of rows to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum rows to return"),
    corrected_by_user_id: str | None = Query(
        default=None, description="Filter batches by user/actor ID"
    ),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[BatchListItemResponse]]:
    """List batch correction groups with aggregated metadata.

    Returns a paginated list of batch correction groups, sorted by
    ``corrected_at`` descending (most recent first). Each item includes
    the batch ID, correction count, actor, pattern/replacement, and timestamp.

    Parameters
    ----------
    offset : int
        Number of rows to skip (default 0).
    limit : int
        Maximum rows to return (default 20, max 100).
    corrected_by_user_id : str or None
        If provided, restrict to batches by this user/actor.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[list[BatchListItemResponse]]
        Paginated list of batch summary items.
    """
    items = await _correction_repo.get_batch_list(
        session,
        offset=offset,
        limit=limit,
        corrected_by_user_id=corrected_by_user_id,
    )

    response_items = [
        BatchListItemResponse(
            batch_id=item.batch_id,
            correction_count=item.correction_count,
            corrected_by_user_id=item.corrected_by_user_id,
            pattern=item.pattern,
            replacement=item.replacement,
            batch_timestamp=item.batch_timestamp,
        )
        for item in items
    ]

    # Build pagination metadata — total is not provided by get_batch_list,
    # so we indicate has_more based on whether we got a full page.
    pagination = PaginationMeta(
        total=offset + len(response_items) + (1 if len(response_items) == limit else 0),
        limit=limit,
        offset=offset,
        has_more=len(response_items) == limit,
    )

    return ApiResponse[list[BatchListItemResponse]](
        data=response_items,
        pagination=pagination,
    )


@router.delete(
    "/{batch_id}",
    response_model=ApiResponse[BatchRevertResponse],
    status_code=200,
    summary="Revert all corrections in a batch",
)
async def revert_batch(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[BatchRevertResponse]:
    """Revert all corrections belonging to a specific batch.

    Atomically reverts every correction sharing the given ``batch_id``.
    Returns HTTP 404 if no corrections exist for the batch ID,
    and HTTP 409 if all corrections in the batch have already been reverted.

    Parameters
    ----------
    batch_id : uuid.UUID
        The batch identifier (UUIDv7).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[BatchRevertResponse]
        Summary of reverted and skipped corrections.

    Raises
    ------
    NotFoundError
        If no corrections exist for the given batch_id (404).
    ConflictError
        If all corrections in the batch are already reverted (409).
    """
    # Check if the batch exists at all
    corrections = await _correction_repo.get_by_batch_id(session, batch_id)
    if not corrections:
        raise NotFoundError(
            resource_type="Batch",
            identifier=str(batch_id),
        )

    # Check if all corrections are already reverted (no active corrections)
    # A correction is "active" if the segment still has has_correction=True
    # We rely on batch_revert to determine this; if total_applied == 0
    # and total_matched == 0 after the call, everything was already reverted.

    result = await _batch_service.batch_revert(
        session,
        batch_id=batch_id,
    )

    # batch_revert returns BatchCorrectionResult when dry_run=False
    if isinstance(result, BatchCorrectionResult):
        reverted_count = result.total_applied
        skipped_count = result.total_skipped + result.total_failed

        # If nothing was reverted and nothing matched, all were already reverted
        if reverted_count == 0 and result.total_matched == 0:
            raise ConflictError(
                message=f"Batch '{batch_id}' has already been fully reverted.",
                details={"batch_id": str(batch_id)},
            )

        response_data = BatchRevertResponse(
            reverted_count=reverted_count,
            skipped_count=skipped_count,
        )
        return ApiResponse[BatchRevertResponse](data=response_data)

    # Shouldn't reach here since dry_run=False, but handle gracefully
    response_data = BatchRevertResponse(
        reverted_count=0,
        skipped_count=0,
    )
    return ApiResponse[BatchRevertResponse](data=response_data)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


async def _find_entity_by_name(
    session: AsyncSession,
    name: str,
) -> tuple[uuid.UUID | None, str | None]:
    """Look up a named entity by canonical name or alias.

    Parameters
    ----------
    session : AsyncSession
        Database session.
    name : str
        The text to match against canonical_name or alias_name.

    Returns
    -------
    tuple[uuid.UUID | None, str | None]
        ``(entity_id, entity_name)`` if found, otherwise ``(None, None)``.
    """
    # Try canonical name first
    stmt = (
        select(NamedEntityDB.id, NamedEntityDB.canonical_name)
        .where(NamedEntityDB.canonical_name.ilike(name))
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is not None:
        return row.id, row.canonical_name

    # Try alias name
    alias_stmt = (
        select(EntityAliasDB.entity_id, EntityAliasDB.alias_name)
        .where(EntityAliasDB.alias_name.ilike(name))
        .limit(1)
    )
    alias_row = (await session.execute(alias_stmt)).first()
    if alias_row is not None:
        # Fetch the entity's canonical name
        entity_stmt = (
            select(NamedEntityDB.canonical_name)
            .where(NamedEntityDB.id == alias_row.entity_id)
        )
        entity_name_val = (await session.execute(entity_stmt)).scalar_one_or_none()
        return alias_row.entity_id, entity_name_val

    return None, None


# ═══════════════════════════════════════════════════════════════════════════
# GET /diff-analysis
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/diff-analysis",
    response_model=ApiResponse[list[DiffErrorPatternResponse]],
    status_code=200,
    summary="Get word-level diff error patterns with entity associations",
)
async def get_diff_analysis(
    min_occurrences: int = Query(default=2, ge=1, le=50),
    limit: int = Query(default=100, ge=1, le=500),
    show_completed: bool = Query(default=True),
    entity_name: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[DiffErrorPatternResponse]]:
    """Get recurring correction patterns enriched with entity associations.

    Wraps ``BatchCorrectionService.get_patterns()`` and enriches each
    pattern with an entity lookup based on the corrected text.

    Parameters
    ----------
    min_occurrences : int
        Minimum number of occurrences for a pattern to be included (1-50).
    limit : int
        Maximum number of patterns to return (1-500).
    show_completed : bool
        Whether to include patterns with no remaining un-corrected matches.
    entity_name : str | None
        If provided, filter results to patterns whose matched entity name
        contains this string (case-insensitive).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[list[DiffErrorPatternResponse]]
        List of error patterns with optional entity associations.
    """
    # Always fetch all patterns (including completed) so we can extract
    # word-level tokens and recompute remaining_matches at the token level.
    patterns = await _batch_service.get_patterns(
        session,
        min_occurrences=min_occurrences,
        limit=limit,
        show_completed=True,
    )

    # Aggregate word-level token pairs across all patterns.
    # Key: (error_token, canonical_form) -> frequency
    aggregated: dict[tuple[str, str], int] = {}

    for p in patterns:
        diff_result = word_level_diff(p.original_text, p.corrected_text)

        if not diff_result.changed_pairs:
            continue

        for error_frag, canon_frag in diff_result.changed_pairs:
            error_token = strip_boundary_punctuation(error_frag)
            canonical_form = strip_boundary_punctuation(canon_frag)

            # Skip empty tokens after stripping
            if not error_token and not canonical_form:
                continue

            key = (error_token, canonical_form)
            aggregated[key] = aggregated.get(key, 0) + p.occurrences

    # Recompute remaining_matches at the token level: count segments whose
    # effective text (corrected_text if corrected, else text) still contains
    # the error token.  This replaces the repository's full-segment-level
    # remaining_matches which doesn't work after word-level extraction.
    effective_text = case(
        (TranscriptSegmentDB.has_correction, TranscriptSegmentDB.corrected_text),
        else_=TranscriptSegmentDB.text,
    )

    # Build response items with entity enrichment.
    results: list[DiffErrorPatternResponse] = []
    for (error_token, canonical_form), freq in aggregated.items():
        # Token-level remaining_matches query
        remaining_stmt = (
            select(func.count())
            .select_from(TranscriptSegmentDB)
            .where(effective_text.contains(error_token))
        )
        remaining_result = await session.execute(remaining_stmt)
        remaining = remaining_result.scalar_one()

        # Apply show_completed filter at the token level
        if not show_completed and remaining == 0:
            continue

        lookup_text = canonical_form if canonical_form else error_token
        entity_id, matched_entity_name = await _find_entity_by_name(
            session, lookup_text
        )

        # If entity_name filter is set, skip non-matching entries
        if entity_name is not None:
            if matched_entity_name is None:
                continue
            if entity_name.lower() not in matched_entity_name.lower():
                continue

        results.append(
            DiffErrorPatternResponse(
                error_token=error_token,
                canonical_form=canonical_form,
                frequency=freq,
                remaining_matches=remaining,
                entity_id=entity_id,
                entity_name=matched_entity_name,
            )
        )

    # Sort by remaining_matches DESC so actionable patterns come first
    results.sort(key=lambda r: r.remaining_matches, reverse=True)

    return ApiResponse[list[DiffErrorPatternResponse]](data=results)


# ═══════════════════════════════════════════════════════════════════════════
# GET /cross-segment/candidates
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/cross-segment/candidates",
    response_model=ApiResponse[list[CrossSegmentCandidateResponse]],
    status_code=200,
    summary="Discover cross-segment ASR error candidates",
)
async def get_cross_segment_candidates(
    min_corrections: int = Query(default=3, ge=1, le=20),
    entity_name: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[CrossSegmentCandidateResponse]]:
    """Discover adjacent segment pairs where a known error is split across a boundary.

    Uses ``CrossSegmentDiscovery`` to analyse recurring correction patterns
    and find segment pairs matching prefix/suffix combinations.

    Parameters
    ----------
    min_corrections : int
        Minimum correction occurrences for a pattern to be considered (1-20).
    entity_name : str | None
        If provided, only consider patterns related to this entity name.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[list[CrossSegmentCandidateResponse]]
        List of cross-segment ASR error candidates.
    """
    discovery = CrossSegmentDiscovery(batch_service=_batch_service)
    candidates = await discovery.discover(
        session,
        min_corrections=min_corrections,
        entity_name=entity_name,
    )

    results = [
        CrossSegmentCandidateResponse(**c.model_dump()) for c in candidates
    ]

    return ApiResponse[list[CrossSegmentCandidateResponse]](data=results)
