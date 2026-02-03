"""Video list and detail endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.videos import (
    TranscriptSummary,
    VideoListItem,
    VideoListResponse,
)
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript


router = APIRouter(dependencies=[Depends(require_auth)])


def build_transcript_summary(transcripts: List[VideoTranscript]) -> TranscriptSummary:
    """
    Build transcript summary from transcript list.

    Parameters
    ----------
    transcripts : List[VideoTranscript]
        List of transcript database models.

    Returns
    -------
    TranscriptSummary
        Summary containing count, languages, and manual indicator.
    """
    if not transcripts:
        return TranscriptSummary(count=0, languages=[], has_manual=False)

    languages = list({t.language_code for t in transcripts})
    has_manual = any(t.is_cc or t.transcript_type == "MANUAL" for t in transcripts)

    return TranscriptSummary(
        count=len(transcripts),
        languages=sorted(languages),
        has_manual=has_manual,
    )


@router.get("/videos", response_model=VideoListResponse)
async def list_videos(
    session: AsyncSession = Depends(get_db),
    channel_id: Optional[str] = Query(
        None,
        min_length=24,
        max_length=24,
        description="Filter by channel ID",
    ),
    has_transcript: Optional[bool] = Query(
        None,
        description="Filter by transcript availability",
    ),
    uploaded_after: Optional[datetime] = Query(
        None,
        description="Filter by upload date (ISO 8601)",
    ),
    uploaded_before: Optional[datetime] = Query(
        None,
        description="Filter by upload date (ISO 8601)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> VideoListResponse:
    """
    List videos with pagination and filtering.

    Supports filtering by channel, transcript availability, and date range.

    Parameters
    ----------
    session : AsyncSession
        Database session from dependency.
    channel_id : Optional[str]
        Filter by channel ID (24 characters).
    has_transcript : Optional[bool]
        Filter by transcript availability.
    uploaded_after : Optional[datetime]
        Filter videos uploaded after this date.
    uploaded_before : Optional[datetime]
        Filter videos uploaded before this date.
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).

    Returns
    -------
    VideoListResponse
        Paginated list of videos with metadata.
    """
    # Build base query
    query = (
        select(VideoDB)
        .where(VideoDB.deleted_flag.is_(False))
        .options(selectinload(VideoDB.transcripts))
        .options(selectinload(VideoDB.channel))
    )

    # Apply filters
    if channel_id:
        query = query.where(VideoDB.channel_id == channel_id)

    if uploaded_after:
        query = query.where(VideoDB.upload_date >= uploaded_after)

    if uploaded_before:
        query = query.where(VideoDB.upload_date <= uploaded_before)

    if has_transcript is not None:
        # Subquery for videos with transcripts
        transcript_subquery = (
            select(VideoTranscript.video_id).distinct().scalar_subquery()
        )
        if has_transcript:
            query = query.where(VideoDB.video_id.in_(transcript_subquery))
        else:
            query = query.where(VideoDB.video_id.notin_(transcript_subquery))

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(VideoDB.upload_date.desc()).offset(offset).limit(limit)

    # Execute query
    result = await session.execute(query)
    videos = result.scalars().all()

    # Transform to response items
    items: List[VideoListItem] = []
    for video in videos:
        transcript_summary = build_transcript_summary(list(video.transcripts))
        channel_title = video.channel.title if video.channel else None

        items.append(
            VideoListItem(
                video_id=video.video_id,
                title=video.title,
                channel_id=video.channel_id,
                channel_title=channel_title,
                upload_date=video.upload_date,
                duration=video.duration,
                view_count=video.view_count,
                transcript_summary=transcript_summary,
            )
        )

    # Build pagination
    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return VideoListResponse(data=items, pagination=pagination)
