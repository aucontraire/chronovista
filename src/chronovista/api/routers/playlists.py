"""Playlist list and detail endpoints.

This module provides API endpoints for playlist management,
including list with linked/unlinked filters, detail view,
and video listing with position ordering.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import GET_ITEM_ERRORS, LIST_ERRORS
from chronovista.api.schemas.playlists import (
    PlaylistDetail,
    PlaylistDetailResponse,
    PlaylistListItem,
    PlaylistListResponse,
    PlaylistVideoListItem,
    PlaylistVideoListResponse,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.videos import TranscriptSummary
from chronovista.db.models import Playlist as PlaylistDB
from chronovista.db.models import PlaylistMembership, Video as VideoDB, VideoTranscript
from chronovista.exceptions import BadRequestError, NotFoundError


router = APIRouter(dependencies=[Depends(require_auth)])


class PlaylistSortField(str, Enum):
    """Valid fields for sorting playlists."""

    TITLE = "title"
    CREATED_AT = "created_at"
    VIDEO_COUNT = "video_count"


class SortOrder(str, Enum):
    """Sort order direction."""

    ASC = "asc"
    DESC = "desc"


def build_transcript_summary(transcripts: List[VideoTranscript]) -> TranscriptSummary:
    """Build transcript summary from transcript list.

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


@router.get("/playlists", response_model=PlaylistListResponse, responses=LIST_ERRORS)
async def list_playlists(
    session: AsyncSession = Depends(get_db),
    linked: Optional[bool] = Query(
        None,
        description="Filter for YouTube-linked playlists (PL/LL/WL/HL prefix)",
    ),
    unlinked: Optional[bool] = Query(
        None,
        description="Filter for internal playlists (int_ prefix)",
    ),
    sort_by: PlaylistSortField = Query(
        PlaylistSortField.CREATED_AT,
        description="Field to sort by (title, created_at, video_count)",
    ),
    sort_order: SortOrder = Query(
        SortOrder.DESC,
        description="Sort order (asc or desc)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> PlaylistListResponse:
    """List playlists with pagination, filters, and sorting.

    Supports filtering by linked/unlinked status. These filters are
    mutually exclusive - if both are set to True, a 400 error is returned.

    Parameters
    ----------
    session : AsyncSession
        Database session from dependency.
    linked : Optional[bool]
        Filter for YouTube-linked playlists (PL/LL/WL/HL prefix).
    unlinked : Optional[bool]
        Filter for internal playlists (int_ prefix).
    sort_by : PlaylistSortField
        Field to sort by: title, created_at, or video_count (default: created_at).
    sort_order : SortOrder
        Sort direction: asc or desc (default: desc).
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).

    Returns
    -------
    PlaylistListResponse
        Paginated list of playlists with metadata.

    Raises
    ------
    BadRequestError
        If both linked=true and unlinked=true are specified.
    """
    # Validate mutually exclusive filters
    if linked is True and unlinked is True:
        raise BadRequestError(
            message="Cannot specify both 'linked=true' and 'unlinked=true'. "
            "These filters are mutually exclusive.",
            details={"field": "linked,unlinked", "constraint": "mutually_exclusive"},
            mutually_exclusive=True,
        )

    # Build base query
    query = select(PlaylistDB).where(PlaylistDB.deleted_flag.is_(False))

    # Apply linked/unlinked filters
    if linked is True:
        # YouTube-linked playlists start with PL, LL, WL, or HL
        query = query.where(
            (PlaylistDB.playlist_id.like("PL%"))
            | (PlaylistDB.playlist_id.like("LL%"))
            | (PlaylistDB.playlist_id.like("WL%"))
            | (PlaylistDB.playlist_id.like("HL%"))
        )
    elif unlinked is True:
        # Internal playlists start with int_
        query = query.where(PlaylistDB.playlist_id.like("int_%"))
    elif linked is False:
        # linked=false means unlinked playlists
        query = query.where(PlaylistDB.playlist_id.like("int_%"))
    elif unlinked is False:
        # unlinked=false means linked playlists
        query = query.where(
            (PlaylistDB.playlist_id.like("PL%"))
            | (PlaylistDB.playlist_id.like("LL%"))
            | (PlaylistDB.playlist_id.like("WL%"))
            | (PlaylistDB.playlist_id.like("HL%"))
        )

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Map sort field to database column
    sort_column_map = {
        PlaylistSortField.TITLE: PlaylistDB.title,
        PlaylistSortField.CREATED_AT: PlaylistDB.created_at,
        PlaylistSortField.VIDEO_COUNT: PlaylistDB.video_count,
    }
    sort_column = sort_column_map[sort_by]

    # Apply sort order
    if sort_order == SortOrder.ASC:
        order_clause = sort_column.asc()
    else:
        order_clause = sort_column.desc()

    # Apply ordering and pagination
    query = query.order_by(order_clause).offset(offset).limit(limit)

    # Execute query
    result = await session.execute(query)
    playlists = result.scalars().all()

    # Transform to response items
    items = [PlaylistListItem.model_validate(p) for p in playlists]

    # Build pagination
    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return PlaylistListResponse(data=items, pagination=pagination)


@router.get("/playlists/{playlist_id}", response_model=PlaylistDetailResponse, responses=GET_ITEM_ERRORS)
async def get_playlist(
    playlist_id: str = Path(
        ...,
        min_length=2,
        max_length=50,
        description="Playlist ID (YouTube or internal)",
    ),
    session: AsyncSession = Depends(get_db),
) -> PlaylistDetailResponse:
    """Get playlist details by ID.

    Accepts both YouTube IDs (PL prefix) and internal IDs (int_ prefix).

    Parameters
    ----------
    playlist_id : str
        Playlist ID (YouTube: PL prefix, 30-50 chars; System: LL/WL/HL;
        Internal: int_ prefix, 36 chars total).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    PlaylistDetailResponse
        Full playlist details.

    Raises
    ------
    NotFoundError
        If playlist not found.
    """
    # Query playlist
    query = (
        select(PlaylistDB)
        .where(PlaylistDB.playlist_id == playlist_id)
        .where(PlaylistDB.deleted_flag.is_(False))
    )

    result = await session.execute(query)
    playlist = result.scalar_one_or_none()

    if not playlist:
        raise NotFoundError(
            resource_type="Playlist",
            identifier=playlist_id,
            hint="Verify the playlist ID or run a sync.",
        )

    return PlaylistDetailResponse(data=PlaylistDetail.model_validate(playlist))


@router.get(
    "/playlists/{playlist_id}/videos",
    response_model=PlaylistVideoListResponse,
    responses=GET_ITEM_ERRORS,
)
async def get_playlist_videos(
    playlist_id: str = Path(
        ...,
        min_length=2,
        max_length=50,
        description="Playlist ID (YouTube or internal)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> PlaylistVideoListResponse:
    """Get videos in a playlist with position ordering.

    Returns videos ordered by their position in the playlist (ASC).
    Includes deleted_flag to preserve position integrity even for
    videos that have been deleted from YouTube.

    Parameters
    ----------
    playlist_id : str
        Playlist ID (YouTube or internal).
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    PlaylistVideoListResponse
        Paginated list of videos in playlist order.

    Raises
    ------
    NotFoundError
        If playlist not found.
    """
    # First verify playlist exists
    playlist_query = select(PlaylistDB.playlist_id).where(
        PlaylistDB.playlist_id == playlist_id
    )
    playlist_result = await session.execute(playlist_query)
    if not playlist_result.scalar_one_or_none():
        raise NotFoundError(
            resource_type="Playlist",
            identifier=playlist_id,
        )

    # Build query for membership with video data
    # Join PlaylistMembership with Video to get all video details
    query = (
        select(PlaylistMembership, VideoDB)
        .join(VideoDB, PlaylistMembership.video_id == VideoDB.video_id)
        .where(PlaylistMembership.playlist_id == playlist_id)
        .options(selectinload(VideoDB.transcripts))
        .options(selectinload(VideoDB.channel))
    )

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(
        select(PlaylistMembership)
        .where(PlaylistMembership.playlist_id == playlist_id)
        .subquery()
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering (position ASC) and pagination
    query = (
        query.order_by(PlaylistMembership.position.asc()).offset(offset).limit(limit)
    )

    # Execute query
    result = await session.execute(query)
    rows = result.all()

    # Transform to response items
    items: List[PlaylistVideoListItem] = []
    for membership, video in rows:
        transcript_summary = build_transcript_summary(list(video.transcripts))
        channel_title = video.channel.title if video.channel else None

        items.append(
            PlaylistVideoListItem(
                video_id=video.video_id,
                title=video.title,
                channel_id=video.channel_id,
                channel_title=channel_title,
                upload_date=video.upload_date,
                duration=video.duration,
                view_count=video.view_count,
                transcript_summary=transcript_summary,
                position=membership.position,
                deleted_flag=video.deleted_flag,
            )
        )

    # Build pagination
    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return PlaylistVideoListResponse(data=items, pagination=pagination)
