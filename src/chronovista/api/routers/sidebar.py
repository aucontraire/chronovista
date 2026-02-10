"""Sidebar navigation endpoints.

This module provides API endpoints for sidebar navigation elements
such as category navigation with video counts.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import LIST_ERRORS
from chronovista.api.schemas.sidebar import SidebarCategory, SidebarCategoryResponse
from chronovista.db.models import Video, VideoCategory


router = APIRouter(dependencies=[Depends(require_auth)])


@router.get(
    "/sidebar/categories",
    response_model=SidebarCategoryResponse,
    responses=LIST_ERRORS,
)
async def get_sidebar_categories(
    session: AsyncSession = Depends(get_db),
) -> SidebarCategoryResponse:
    """
    Get categories for sidebar navigation.

    Returns categories formatted for sidebar navigation display.
    Includes pre-built navigation URLs and video counts.
    Ordered by video_count descending (most popular first).
    Only includes categories with at least one video.

    Parameters
    ----------
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    SidebarCategoryResponse
        Categories ordered by video_count descending.
    """
    # Subquery for video count per category (only non-deleted videos)
    video_count_subq = (
        select(func.count(Video.video_id))
        .where(Video.category_id == VideoCategory.category_id)
        .where(Video.deleted_flag.is_(False))
        .correlate(VideoCategory)
        .scalar_subquery()
    )

    # Query categories with video counts
    query = select(
        VideoCategory.category_id,
        VideoCategory.name,
        video_count_subq.label("video_count"),
    ).where(video_count_subq > 0)  # Only include categories with videos

    # Order by video count descending
    query = query.order_by(video_count_subq.desc())

    # Execute query
    result = await session.execute(query)
    rows = result.all()

    # Transform to response items with href
    items: List[SidebarCategory] = []
    for row in rows:
        items.append(
            SidebarCategory(
                category_id=row.category_id,
                name=row.name,
                video_count=row.video_count or 0,
                href=f"/videos?category={row.category_id}",
            )
        )

    return SidebarCategoryResponse(data=items)
