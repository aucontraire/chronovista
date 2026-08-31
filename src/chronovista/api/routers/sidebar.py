"""Sidebar navigation endpoints.

This module provides API endpoints for sidebar navigation elements
such as category navigation with video counts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, get_video_category_repository, require_auth
from chronovista.api.routers.responses import LIST_ERRORS
from chronovista.api.schemas.sidebar import SidebarCategory, SidebarCategoryResponse
from chronovista.repositories.video_category_repository import VideoCategoryRepository

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get(
    "/sidebar/categories",
    response_model=SidebarCategoryResponse,
    responses=LIST_ERRORS,
)
async def get_sidebar_categories(
    repo: VideoCategoryRepository = Depends(get_video_category_repository),
    session: AsyncSession = Depends(get_db),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
) -> SidebarCategoryResponse:
    """
    Get categories for sidebar navigation.

    Returns categories formatted for sidebar navigation display.
    Includes pre-built navigation URLs and video counts.
    Ordered by video_count descending (most popular first).
    Only includes categories with at least one video.

    Parameters
    ----------
    repo : VideoCategoryRepository
        Video category repository injected via the DI container.
    session : AsyncSession
        Database session from dependency.
    include_unavailable : bool
        Include unavailable videos in the per-category counts.

    Returns
    -------
    SidebarCategoryResponse
        Categories ordered by video_count descending.
    """
    rows = await repo.get_with_video_counts(
        session,
        include_unavailable=include_unavailable,
        only_with_videos=True,
    )

    items = [
        SidebarCategory(
            category_id=row.category_id,
            name=row.name,
            video_count=row.video_count,
            href=f"/videos?category={row.category_id}",
        )
        for row in rows
    ]

    return SidebarCategoryResponse(data=items)
