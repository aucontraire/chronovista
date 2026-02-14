"""Category list and detail endpoints.

This module provides API endpoints for accessing category (VideoCategory) data
with aggregated video counts. Categories are YouTube's built-in classification system.

Route Order: The videos endpoint MUST be defined before the detail endpoint
to avoid path matching conflicts.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import GET_ITEM_ERRORS, LIST_ERRORS
from chronovista.api.schemas.categories import (
    CategoryDetail,
    CategoryDetailResponse,
    CategoryListItem,
    CategoryListResponse,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.topics import TopicSummary
from chronovista.api.schemas.videos import VideoListItem, VideoListResponse, TranscriptSummary
from chronovista.db.models import Video, VideoCategory, VideoTag, VideoTopic, TopicCategory
from chronovista.exceptions import NotFoundError
from chronovista.models.enums import AvailabilityStatus


router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/categories", response_model=CategoryListResponse, responses=LIST_ERRORS)
async def list_categories(
    session: AsyncSession = Depends(get_db),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> CategoryListResponse:
    """
    List categories with pagination and aggregated counts.

    Returns categories sorted by video_count in descending order by default.
    Includes aggregated video_count for each category (excluding deleted videos).

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
    CategoryListResponse
        Paginated list of categories with metadata.
    """
    # Subquery for video count
    video_count_conditions = [Video.category_id == VideoCategory.category_id]
    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        video_count_conditions.append(Video.availability_status == AvailabilityStatus.AVAILABLE)

    video_count_subq = (
        select(func.count(Video.video_id))
        .where(*video_count_conditions)
        .correlate(VideoCategory)
        .scalar_subquery()
    )

    # Main query with counts - selecting specific columns for aggregation
    query = select(
        VideoCategory.category_id,
        VideoCategory.name,
        VideoCategory.assignable,
        video_count_subq.label("video_count"),
    )

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(VideoCategory)
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering (video_count DESC per spec) and pagination
    query = (
        query.order_by(video_count_subq.desc())
        .offset(offset)
        .limit(limit)
    )

    # Execute query
    result = await session.execute(query)
    rows = result.all()

    # Transform to response items
    items: List[CategoryListItem] = []
    for row in rows:
        items.append(
            CategoryListItem(
                category_id=row.category_id,
                name=row.name,
                assignable=row.assignable,
                video_count=row.video_count or 0,
            )
        )

    # Build pagination
    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return CategoryListResponse(data=items, pagination=pagination)


# IMPORTANT: This endpoint MUST be defined before the detail endpoint below
# to avoid path matching conflicts with /{category_id}.
@router.get("/categories/{category_id}/videos", response_model=VideoListResponse, responses=GET_ITEM_ERRORS)
async def get_category_videos(
    category_id: str = Path(
        ...,
        description="YouTube category ID",
        examples=["10", "22"],
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> VideoListResponse:
    """
    Get videos in a category.

    Returns videos that have been classified with the specified category,
    ordered by upload date descending. Excludes deleted videos.

    Parameters
    ----------
    category_id : str
        YouTube category ID (e.g., "10" for Music, "22" for People & Blogs).
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    VideoListResponse
        Paginated list of videos in the category.

    Raises
    ------
    NotFoundError
        404 if category not found.
    """
    # Verify category exists
    cat_result = await session.execute(
        select(VideoCategory.category_id).where(VideoCategory.category_id == category_id)
    )
    if not cat_result.scalar_one_or_none():
        raise NotFoundError(
            resource_type="Category",
            identifier=category_id,
            hint="Verify the category ID or check available categories.",
        )

    # Build query for videos in this category
    query = (
        select(Video)
        .where(Video.category_id == category_id)
        .options(selectinload(Video.transcripts))
        .options(selectinload(Video.channel))
        .options(selectinload(Video.category))
        .options(selectinload(Video.tags))
        .options(selectinload(Video.video_topics).selectinload(VideoTopic.topic_category))
    )

    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        query = query.where(Video.availability_status == AvailabilityStatus.AVAILABLE)

    # Get total count (before pagination)
    count_query = (
        select(func.count(Video.video_id))
        .where(Video.category_id == category_id)
    )
    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        count_query = count_query.where(Video.availability_status == AvailabilityStatus.AVAILABLE)
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    query = query.order_by(Video.upload_date.desc()).offset(offset).limit(limit)

    # Execute query
    result = await session.execute(query)
    videos = result.scalars().all()

    # Transform to response items (reusing pattern from topics)
    items: List[VideoListItem] = []
    for video in videos:
        # Build transcript summary
        transcripts = list(video.transcripts) if video.transcripts else []
        transcript_count = len(transcripts)
        languages = list({t.language_code for t in transcripts})
        has_manual = any(
            t.is_cc or t.transcript_type == "MANUAL" for t in transcripts
        )

        transcript_summary = TranscriptSummary(
            count=transcript_count,
            languages=sorted(languages),
            has_manual=has_manual,
        )

        channel_title = video.channel.title if video.channel else None

        # Build classification fields
        category_name = video.category.name if video.category else None
        tags = [tag.tag for tag in video.tags] if video.tags else []
        topics = [
            TopicSummary(
                topic_id=vt.topic_category.topic_id,
                name=vt.topic_category.category_name,
                parent_path=None,  # TODO: Compute hierarchy path if needed
            )
            for vt in video.video_topics
        ] if video.video_topics else []

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
                category_id=video.category_id,
                category_name=category_name,
                tags=tags,
                topics=topics,
                availability_status=video.availability_status,
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


@router.get("/categories/{category_id}", response_model=CategoryDetailResponse, responses=GET_ITEM_ERRORS)
async def get_category(
    category_id: str = Path(
        ...,
        description="YouTube category ID",
        examples=["10", "22"],
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    session: AsyncSession = Depends(get_db),
) -> CategoryDetailResponse:
    """
    Get category details by ID.

    Returns full category metadata including aggregated video count
    (excluding deleted videos).

    Parameters
    ----------
    category_id : str
        YouTube category ID (e.g., "10" for Music, "22" for People & Blogs).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    CategoryDetailResponse
        Full category details with aggregated counts.

    Raises
    ------
    NotFoundError
        404 if category not found.
    """
    # Subquery for video count
    video_count_conditions = [Video.category_id == VideoCategory.category_id]
    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        video_count_conditions.append(Video.availability_status == AvailabilityStatus.AVAILABLE)

    video_count_subq = (
        select(func.count(Video.video_id))
        .where(*video_count_conditions)
        .correlate(VideoCategory)
        .scalar_subquery()
    )

    # Query category with counts
    query = select(
        VideoCategory.category_id,
        VideoCategory.name,
        VideoCategory.assignable,
        VideoCategory.created_at,
        video_count_subq.label("video_count"),
    ).where(VideoCategory.category_id == category_id)

    result = await session.execute(query)
    row = result.one_or_none()

    if not row:
        raise NotFoundError(
            resource_type="Category",
            identifier=category_id,
            hint="Verify the category ID or check available categories.",
        )

    # Build response
    detail = CategoryDetail(
        category_id=row.category_id,
        name=row.name,
        assignable=row.assignable,
        video_count=row.video_count or 0,
        created_at=row.created_at,
    )

    return CategoryDetailResponse(data=detail)
