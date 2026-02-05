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
from chronovista.api.schemas.categories import (
    CategoryDetail,
    CategoryDetailResponse,
    CategoryListItem,
    CategoryListResponse,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.videos import VideoListItem, VideoListResponse, TranscriptSummary
from chronovista.db.models import Video, VideoCategory
from chronovista.exceptions import NotFoundError


router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories(
    session: AsyncSession = Depends(get_db),
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
    # Subquery for video count (excluding deleted videos)
    video_count_subq = (
        select(func.count(Video.video_id))
        .where(Video.category_id == VideoCategory.category_id)
        .where(Video.deleted_flag.is_(False))
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
@router.get("/categories/{category_id}/videos", response_model=VideoListResponse)
async def get_category_videos(
    category_id: str = Path(
        ...,
        description="YouTube category ID",
        examples=["10", "22"],
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

    # Build query for videos in this category (excluding deleted)
    query = (
        select(Video)
        .where(Video.category_id == category_id)
        .where(Video.deleted_flag.is_(False))
        .options(selectinload(Video.transcripts))
        .options(selectinload(Video.channel))
    )

    # Get total count (before pagination)
    count_query = (
        select(func.count(Video.video_id))
        .where(Video.category_id == category_id)
        .where(Video.deleted_flag.is_(False))
    )
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


@router.get("/categories/{category_id}", response_model=CategoryDetailResponse)
async def get_category(
    category_id: str = Path(
        ...,
        description="YouTube category ID",
        examples=["10", "22"],
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
    # Subquery for video count (excluding deleted videos)
    video_count_subq = (
        select(func.count(Video.video_id))
        .where(Video.category_id == VideoCategory.category_id)
        .where(Video.deleted_flag.is_(False))
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
