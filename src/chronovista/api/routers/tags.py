"""Tag list and detail endpoints.

This module provides API endpoints for accessing tag data aggregated from
the video_tags junction table with video counts. Unlike topics which have a
dedicated table, tags are queried via GROUP BY aggregation on video_tags.

Route Order: The videos endpoint MUST be defined before the detail endpoint
to ensure correct URL matching, following the same pattern as topics router.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.tags import (
    TagDetail,
    TagDetailResponse,
    TagListItem,
    TagListResponse,
)
from chronovista.api.schemas.videos import VideoListItem, VideoListResponse
from chronovista.db.models import Video, VideoTag
from chronovista.exceptions import NotFoundError


router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/tags", response_model=TagListResponse)
async def list_tags(
    session: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> TagListResponse:
    """
    List tags with pagination and video counts.

    Returns tags sorted by video_count in descending order by default.
    Tags are aggregated from the video_tags junction table, excluding
    videos with deleted_flag=true.

    Parameters
    ----------
    session : AsyncSession
        Database session from dependency.
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).

    Returns
    -------
    TagListResponse
        Paginated list of tags with video counts.
    """
    # Query unique tags with counts (excluding deleted videos)
    query = (
        select(
            VideoTag.tag,
            func.count(VideoTag.video_id).label("video_count"),
        )
        .join(Video, VideoTag.video_id == Video.video_id)
        .where(Video.deleted_flag.is_(False))
        .group_by(VideoTag.tag)
    )

    # Total count of unique tags
    count_subq = (
        select(func.count(func.distinct(VideoTag.tag)))
        .select_from(VideoTag)
        .join(Video, VideoTag.video_id == Video.video_id)
        .where(Video.deleted_flag.is_(False))
    )
    total_result = await session.execute(count_subq)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    query = query.order_by(func.count(VideoTag.video_id).desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    rows = result.all()

    items: List[TagListItem] = [
        TagListItem(tag=row.tag, video_count=row.video_count)
        for row in rows
    ]

    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return TagListResponse(data=items, pagination=pagination)


# IMPORTANT: This endpoint MUST be defined before the detail endpoint below
# to ensure correct URL matching, following the same pattern as topics router.
@router.get("/tags/{tag}/videos", response_model=VideoListResponse)
async def get_tag_videos(
    tag: str = Path(
        ...,
        description="Tag name (URL-encoded if contains special characters like #, /, etc.)",
        examples=["music", "gaming", "%23tutorial"],
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> VideoListResponse:
    """
    Get videos with a specific tag.

    Returns videos that have been tagged with the specified tag,
    ordered by upload date descending. Excludes deleted videos.

    Parameters
    ----------
    tag : str
        Tag name (URL-encoded if contains special characters).
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    VideoListResponse
        Paginated list of videos with the tag.

    Raises
    ------
    NotFoundError
        404 if tag not found.
    """
    # Verify tag exists (check if any videos have this tag)
    tag_result = await session.execute(
        select(VideoTag.tag)
        .join(Video, VideoTag.video_id == Video.video_id)
        .where(VideoTag.tag == tag)
        .where(Video.deleted_flag.is_(False))
        .limit(1)
    )
    if not tag_result.scalar_one_or_none():
        raise NotFoundError(
            resource_type="Tag",
            identifier=tag,
            hint="Verify the tag name or check available tags.",
        )

    # Query videos with this tag
    query = (
        select(Video)
        .join(VideoTag, Video.video_id == VideoTag.video_id)
        .where(VideoTag.tag == tag)
        .where(Video.deleted_flag.is_(False))
        .options(selectinload(Video.transcripts))
        .options(selectinload(Video.channel))
    )

    # Total count
    count_query = (
        select(func.count(Video.video_id))
        .select_from(Video)
        .join(VideoTag, Video.video_id == VideoTag.video_id)
        .where(VideoTag.tag == tag)
        .where(Video.deleted_flag.is_(False))
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    query = query.order_by(Video.upload_date.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    videos = result.scalars().all()

    # Transform to response (reuse pattern from topics router)
    items: List[VideoListItem] = []
    for video in videos:
        # Build transcript summary
        transcripts = list(video.transcripts) if video.transcripts else []
        transcript_count = len(transcripts)
        languages = list({t.language_code for t in transcripts})
        has_manual = any(
            t.is_cc or t.transcript_type == "MANUAL" for t in transcripts
        )

        from chronovista.api.schemas.videos import TranscriptSummary

        transcript_summary = TranscriptSummary(
            count=transcript_count,
            languages=sorted(languages),
            has_manual=has_manual,
        )

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


@router.get("/tags/{tag}", response_model=TagDetailResponse)
async def get_tag(
    tag: str = Path(
        ...,
        description="Tag name (URL-encoded if contains special characters like #, /, etc.)",
        examples=["music", "gaming", "%23tutorial"],
    ),
    session: AsyncSession = Depends(get_db),
) -> TagDetailResponse:
    """
    Get tag details by name.

    Returns tag metadata with aggregated video count.
    Excludes deleted videos from the count.

    Parameters
    ----------
    tag : str
        Tag name (URL-encoded if contains special characters).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    TagDetailResponse
        Full tag details with video count.

    Raises
    ------
    NotFoundError
        404 if tag not found.
    """
    # Query tag with video count (excluding deleted videos)
    query = (
        select(
            VideoTag.tag,
            func.count(VideoTag.video_id).label("video_count"),
        )
        .join(Video, VideoTag.video_id == Video.video_id)
        .where(VideoTag.tag == tag)
        .where(Video.deleted_flag.is_(False))
        .group_by(VideoTag.tag)
    )

    result = await session.execute(query)
    row = result.one_or_none()

    if not row:
        raise NotFoundError(
            resource_type="Tag",
            identifier=tag,
            hint="Verify the tag name or check available tags.",
        )

    detail = TagDetail(tag=row.tag, video_count=row.video_count)

    return TagDetailResponse(data=detail)
