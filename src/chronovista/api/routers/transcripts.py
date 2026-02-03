"""Transcript endpoints for viewing and retrieving transcript data."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.transcripts import (
    SegmentListResponse,
    TranscriptFull,
    TranscriptLanguage,
    TranscriptLanguagesResponse,
    TranscriptResponse,
    TranscriptSegment,
)
from chronovista.db.models import TranscriptSegment as SegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as TranscriptDB


router = APIRouter(dependencies=[Depends(require_auth)])


def get_language_name(code: str) -> str:
    """
    Get human-readable language name from code.

    Parameters
    ----------
    code : str
        BCP-47 language code.

    Returns
    -------
    str
        Human-readable language name, or the code itself if unknown.
    """
    names = {
        "en": "English",
        "en-US": "English (US)",
        "en-GB": "English (UK)",
        "es": "Spanish",
        "es-ES": "Spanish (Spain)",
        "es-MX": "Spanish (Mexico)",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "pt-BR": "Portuguese (Brazil)",
        "zh-CN": "Chinese (Simplified)",
        "zh-TW": "Chinese (Traditional)",
        "ja": "Japanese",
        "ko": "Korean",
        "ru": "Russian",
        "ar": "Arabic",
        "hi": "Hindi",
    }
    return names.get(code, code)


@router.get(
    "/videos/{video_id}/transcript/languages",
    response_model=TranscriptLanguagesResponse,
)
async def get_transcript_languages(
    video_id: str = Path(..., min_length=11, max_length=11),
    session: AsyncSession = Depends(get_db),
) -> TranscriptLanguagesResponse:
    """
    Get available transcript languages for a video.

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    TranscriptLanguagesResponse
        List of available transcript languages.

    Raises
    ------
    HTTPException
        404 if video not found.
    """
    # Check video exists
    video_result = await session.execute(
        select(VideoDB)
        .where(VideoDB.video_id == video_id)
        .where(VideoDB.deleted_flag.is_(False))
    )
    if not video_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": f"Video '{video_id}' not found.",
            },
        )

    # Get transcripts
    result = await session.execute(
        select(TranscriptDB)
        .where(TranscriptDB.video_id == video_id)
        .order_by(TranscriptDB.is_cc.desc(), TranscriptDB.downloaded_at.desc())
    )
    transcripts = result.scalars().all()

    languages = [
        TranscriptLanguage(
            language_code=t.language_code,
            language_name=get_language_name(t.language_code),
            transcript_type=(
                "manual" if t.is_cc or t.transcript_type == "MANUAL" else "auto_generated"
            ),
            is_translatable=True,  # Default - could check from API
            downloaded_at=t.downloaded_at,
        )
        for t in transcripts
    ]

    return TranscriptLanguagesResponse(data=languages)


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    video_id: str = Path(..., min_length=11, max_length=11),
    language: Optional[str] = Query(
        None, description="Language code (default: first available)"
    ),
    session: AsyncSession = Depends(get_db),
) -> TranscriptResponse:
    """
    Get full transcript for a video.

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    language : Optional[str]
        Language code to retrieve (default: first available, preferring manual).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    TranscriptResponse
        Full transcript content with metadata.

    Raises
    ------
    HTTPException
        404 if transcript not found.
    """
    # Build query
    query = select(TranscriptDB).where(TranscriptDB.video_id == video_id)

    if language:
        query = query.where(TranscriptDB.language_code == language)
    else:
        # Default selection: prefer manual/CC, then by download date
        query = query.order_by(
            TranscriptDB.is_cc.desc(), TranscriptDB.downloaded_at.desc()
        )

    result = await session.execute(query)
    transcript = result.scalars().first()

    if not transcript:
        if language:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "NOT_FOUND",
                    "message": (
                        f"No transcript found for video '{video_id}' "
                        f"in language '{language}'."
                    ),
                },
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": f"No transcripts available for video '{video_id}'.",
            },
        )

    return TranscriptResponse(
        data=TranscriptFull(
            video_id=transcript.video_id,
            language_code=transcript.language_code,
            transcript_type="manual" if transcript.is_cc else "auto_generated",
            full_text=transcript.transcript_text,
            segment_count=transcript.segment_count or 0,
            downloaded_at=transcript.downloaded_at,
        )
    )


@router.get(
    "/videos/{video_id}/transcript/segments", response_model=SegmentListResponse
)
async def get_transcript_segments(
    video_id: str = Path(..., min_length=11, max_length=11),
    language: Optional[str] = Query(
        None, description="Language code (default: first available)"
    ),
    start_time: Optional[float] = Query(
        None, ge=0, description="Filter segments starting at or after (seconds)"
    ),
    end_time: Optional[float] = Query(
        None, ge=0, description="Filter segments ending before (seconds)"
    ),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> SegmentListResponse:
    """
    Get paginated transcript segments for a video.

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    language : Optional[str]
        Language code to retrieve (default: first available, preferring manual).
    start_time : Optional[float]
        Filter segments starting at or after this time (seconds).
    end_time : Optional[float]
        Filter segments ending before this time (seconds).
    limit : int
        Items per page (1-200, default 50).
    offset : int
        Pagination offset (default 0).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    SegmentListResponse
        Paginated list of transcript segments.
    """
    # First, determine the language code to use
    if not language:
        # Get default transcript
        transcript_query = (
            select(TranscriptDB)
            .where(TranscriptDB.video_id == video_id)
            .order_by(TranscriptDB.is_cc.desc(), TranscriptDB.downloaded_at.desc())
        )
        result = await session.execute(transcript_query)
        transcript = result.scalars().first()
        if not transcript:
            return SegmentListResponse(
                data=[],
                pagination=PaginationMeta(
                    total=0, limit=limit, offset=offset, has_more=False
                ),
            )
        language = transcript.language_code

    # Build segments query
    query = (
        select(SegmentDB)
        .where(SegmentDB.video_id == video_id)
        .where(SegmentDB.language_code == language)
    )

    # Apply time filters
    if start_time is not None:
        query = query.where(SegmentDB.start_time >= start_time)
    if end_time is not None:
        query = query.where(SegmentDB.end_time <= end_time)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(SegmentDB.start_time.asc()).offset(offset).limit(limit)

    segment_result = await session.execute(query)
    segments: list[SegmentDB] = list(segment_result.scalars().all())

    items = [
        TranscriptSegment(
            id=seg.id,
            text=seg.text,
            start_time=seg.start_time,
            end_time=seg.end_time,
            duration=seg.duration,
        )
        for seg in segments
    ]

    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return SegmentListResponse(data=items, pagination=pagination)
