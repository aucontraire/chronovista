"""Transcript correction endpoints for submitting and managing corrections.

This module handles the REST API endpoints for transcript correction
operations, including submitting new corrections, reviewing pending
corrections, and applying or reverting corrections. Endpoints will
be added incrementally as Feature 034 tasks are implemented.
"""

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.responses import ApiResponse, PaginationMeta
from chronovista.api.schemas.transcript_corrections import (
    CorrectionAuditRecord,
    CorrectionRevertResponse,
    CorrectionSubmitRequest,
    CorrectionSubmitResponse,
    SegmentCorrectionState,
)
from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import TranscriptSegment as SegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.exceptions import APIValidationError, NotFoundError
from chronovista.models.correction_actors import ACTOR_USER_LOCAL
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)
from chronovista.services.transcript_correction_service import (
    TranscriptCorrectionService,
)

router = APIRouter(dependencies=[Depends(require_auth)])

# Module-level service instantiation (singleton pattern)
_correction_repo = TranscriptCorrectionRepository()
_segment_repo = TranscriptSegmentRepository()
_transcript_repo = VideoTranscriptRepository()
_correction_service = TranscriptCorrectionService(
    correction_repo=_correction_repo,
    segment_repo=_segment_repo,
    transcript_repo=_transcript_repo,
)


def _map_correction_error(error: ValueError) -> APIValidationError:
    """Map a ValueError from the correction service to an APIValidationError.

    Parameters
    ----------
    error : ValueError
        The ValueError raised by the correction service.

    Returns
    -------
    APIValidationError
        An API validation error with the appropriate error code.
    """
    msg = str(error)
    exc = APIValidationError(message=msg)
    if "not found" in msg.lower() or "does not exist" in msg.lower():
        exc._error_code_value = "SEGMENT_NOT_FOUND"
    elif "identical" in msg.lower() or "no change" in msg.lower():
        exc._error_code_value = "NO_CHANGE_DETECTED"
    elif "no active correction" in msg.lower():
        exc._error_code_value = "NO_ACTIVE_CORRECTION"
    return exc


@router.post(
    "/videos/{video_id}/transcript/segments/{segment_id}/corrections",
    response_model=ApiResponse[CorrectionSubmitResponse],
    status_code=201,
    summary="Submit a transcript correction",
)
async def submit_correction(
    video_id: str = Path(..., description="YouTube video ID"),
    segment_id: int = Path(..., description="Transcript segment primary key"),
    language_code: str = Query(..., description="BCP-47 language code"),
    body: CorrectionSubmitRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[CorrectionSubmitResponse]:
    """Submit a correction for a transcript segment.

    Creates an append-only audit record and updates the segment's corrected
    text. The segment's effective text becomes the ``corrected_text`` value
    from the request body.

    Parameters
    ----------
    video_id : str
        YouTube video ID.
    segment_id : int
        Primary key of the transcript segment to correct.
    language_code : str
        BCP-47 language code (required query parameter).
    body : CorrectionSubmitRequest
        Correction details including corrected text and type.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[CorrectionSubmitResponse]
        The created audit record and resulting segment state.

    Raises
    ------
    NotFoundError
        If the video does not exist (404).
    APIValidationError
        If the segment is not found, the corrected text is identical
        to the current effective text, or the correction type is invalid (422).
    """
    # Check video existence
    video_query = select(VideoDB.video_id).where(VideoDB.video_id == video_id)
    video_result = await session.execute(video_query)
    if not video_result.scalar_one_or_none():
        raise NotFoundError(resource_type="Video", identifier=video_id)

    # Apply correction via service
    try:
        correction_db = await _correction_service.apply_correction(
            session,
            video_id=video_id,
            language_code=language_code,
            segment_id=segment_id,
            corrected_text=body.corrected_text,
            correction_type=body.correction_type,
            correction_note=body.correction_note,
            corrected_by_user_id=body.corrected_by_user_id or ACTOR_USER_LOCAL,
        )
    except ValueError as e:
        raise _map_correction_error(e) from e

    # Get updated segment state
    segment_query = select(SegmentDB).where(SegmentDB.id == segment_id)
    segment_result = await session.execute(segment_query)
    segment = segment_result.scalar_one()

    effective_text = (
        segment.corrected_text if segment.has_correction else segment.text
    ) or segment.text

    # Build response
    audit_record = CorrectionAuditRecord.model_validate(correction_db)
    segment_state = SegmentCorrectionState(
        has_correction=segment.has_correction,
        effective_text=effective_text,
    )
    response_data = CorrectionSubmitResponse(
        correction=audit_record,
        segment_state=segment_state,
    )
    return ApiResponse[CorrectionSubmitResponse](data=response_data)


@router.post(
    "/videos/{video_id}/transcript/segments/{segment_id}/corrections/revert",
    response_model=ApiResponse[CorrectionRevertResponse],
    status_code=200,
    summary="Revert the latest transcript correction",
)
async def revert_correction(
    video_id: str = Path(..., description="YouTube video ID"),
    segment_id: int = Path(..., description="Transcript segment primary key"),
    language_code: str = Query(..., description="BCP-47 language code"),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[CorrectionRevertResponse]:
    """Revert the most recent correction for a transcript segment.

    Creates an append-only revert audit record and restores the segment's
    text to its previous state.

    Parameters
    ----------
    video_id : str
        YouTube video ID.
    segment_id : int
        Primary key of the transcript segment.
    language_code : str
        BCP-47 language code (required query parameter).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[CorrectionRevertResponse]
        The revert audit record and resulting segment state.

    Raises
    ------
    NotFoundError
        If the video does not exist (404).
    APIValidationError
        If no active correction exists to revert (422).
    """
    # Check video existence
    video_query = select(VideoDB.video_id).where(VideoDB.video_id == video_id)
    video_result = await session.execute(video_query)
    if not video_result.scalar_one_or_none():
        raise NotFoundError(resource_type="Video", identifier=video_id)

    # Revert correction via service
    try:
        correction_db = await _correction_service.revert_correction(
            session, segment_id=segment_id
        )
    except ValueError as e:
        raise _map_correction_error(e) from e

    # Get updated segment state
    segment_query = select(SegmentDB).where(SegmentDB.id == segment_id)
    segment_result = await session.execute(segment_query)
    segment = segment_result.scalar_one()

    effective_text = (
        segment.corrected_text if segment.has_correction else segment.text
    ) or segment.text

    # Build response
    audit_record = CorrectionAuditRecord.model_validate(correction_db)
    segment_state = SegmentCorrectionState(
        has_correction=segment.has_correction,
        effective_text=effective_text,
    )
    response_data = CorrectionRevertResponse(
        correction=audit_record,
        segment_state=segment_state,
    )
    return ApiResponse[CorrectionRevertResponse](data=response_data)


@router.get(
    "/videos/{video_id}/transcript/segments/{segment_id}/corrections",
    response_model=ApiResponse[list[CorrectionAuditRecord]],
    status_code=200,
    summary="Get correction history for a segment",
)
async def get_correction_history(
    video_id: str = Path(..., description="YouTube video ID"),
    segment_id: int = Path(..., description="Transcript segment primary key"),
    language_code: str = Query(..., description="BCP-47 language code"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[CorrectionAuditRecord]]:
    """Get the correction history for a transcript segment.

    Returns an ordered list of all correction audit records for the
    specified segment, newest first. Returns an empty list if no
    corrections exist (no 404 for missing segments per FR-013).

    Parameters
    ----------
    video_id : str
        YouTube video ID.
    segment_id : int
        Primary key of the transcript segment.
    language_code : str
        BCP-47 language code (required query parameter).
    limit : int
        Maximum number of items to return (1--100, default 50).
    offset : int
        Number of items to skip (default 0).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[list[CorrectionAuditRecord]]
        Paginated list of correction audit records with pagination metadata.

    Raises
    ------
    NotFoundError
        If the video does not exist (404).
    """
    # Check video existence
    video_query = select(VideoDB.video_id).where(VideoDB.video_id == video_id)
    video_result = await session.execute(video_query)
    if not video_result.scalar_one_or_none():
        raise NotFoundError(resource_type="Video", identifier=video_id)

    # Fetch corrections for segment
    corrections = await _correction_repo.get_by_segment(
        session,
        video_id=video_id,
        language_code=language_code,
        segment_id=segment_id,
        skip=offset,
        limit=limit,
    )

    # Count total corrections for pagination
    count_query = (
        select(func.count())
        .select_from(TranscriptCorrectionDB)
        .where(
            TranscriptCorrectionDB.video_id == video_id,
            TranscriptCorrectionDB.language_code == language_code,
            TranscriptCorrectionDB.segment_id == segment_id,
        )
    )
    total = (await session.execute(count_query)).scalar() or 0

    # Map to response models
    records = [CorrectionAuditRecord.model_validate(r) for r in corrections]

    return ApiResponse[list[CorrectionAuditRecord]](
        data=records,
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + limit < total,
        ),
    )
