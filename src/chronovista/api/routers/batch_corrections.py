"""Batch correction endpoints for bulk find-replace operations on transcripts.

This module handles the REST API endpoints for batch correction operations,
including previewing matches, applying corrections in bulk, and rebuilding
full transcript text from corrected segments.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.batch_corrections import (
    BatchApplyRequest,
    BatchApplyResult,
    BatchPreviewRequest,
    BatchPreviewResponse,
    BatchRebuildRequest,
    BatchRebuildResult,
)
from chronovista.api.schemas.responses import ApiResponse
from chronovista.exceptions import APIValidationError
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
from chronovista.services.batch_correction_service import BatchCorrectionService
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
