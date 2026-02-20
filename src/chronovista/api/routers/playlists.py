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
from chronovista.api.schemas.sorting import SortOrder
from chronovista.api.schemas.videos import TranscriptSummary
from chronovista.db.models import Playlist as PlaylistDB
from chronovista.db.models import PlaylistMembership, UserVideo, Video as VideoDB, VideoTranscript
from chronovista.exceptions import BadRequestError, NotFoundError
from chronovista.models.enums import AvailabilityStatus


router = APIRouter(dependencies=[Depends(require_auth)])


class PlaylistSortField(str, Enum):
    """Valid fields for sorting playlists."""

    TITLE = "title"
    CREATED_AT = "created_at"
    VIDEO_COUNT = "video_count"


class PlaylistVideoSortField(str, Enum):
    """Valid fields for sorting videos within a playlist."""

    POSITION = "position"
    UPLOAD_DATE = "upload_date"
    TITLE = "title"


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

    # Apply ordering and pagination (secondary sort by playlist_id for determinism)
    query = query.order_by(order_clause, PlaylistDB.playlist_id.asc()).offset(offset).limit(limit)

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
    include_unavailable: bool = Query(
        True,
        description="Include unavailable videos in results",
    ),
    sort_by: PlaylistVideoSortField = Query(
        PlaylistVideoSortField.POSITION,
        description="Field to sort by (position, upload_date, title)",
    ),
    sort_order: SortOrder = Query(
        SortOrder.ASC,
        description="Sort order (asc or desc)",
    ),
    liked_only: bool = Query(
        False,
        description="Filter to show only liked videos",
    ),
    has_transcript: bool = Query(
        False,
        description="Filter to show only videos with transcripts",
    ),
    unavailable_only: bool = Query(
        False,
        description="Filter to show only unavailable videos",
    ),
    session: AsyncSession = Depends(get_db),
) -> PlaylistVideoListResponse:
    """Get videos in a playlist with sorting and filtering.

    Returns videos with configurable sort order (default: position ASC).
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
    include_unavailable : bool
        If True (default), include unavailable videos in results.
        If False, only return available videos.
    sort_by : PlaylistVideoSortField
        Field to sort by: position, upload_date, or title (default: position).
    sort_order : SortOrder
        Sort direction: asc or desc (default: asc).
    liked_only : bool
        If True, only return videos the user has liked (default: False).
    has_transcript : bool
        If True, only return videos with transcripts (default: False).
    unavailable_only : bool
        If True, only return unavailable videos (default: False).
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

    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        query = query.where(VideoDB.availability_status == AvailabilityStatus.AVAILABLE)

    # Apply unavailable_only filter
    if unavailable_only:
        query = query.where(VideoDB.availability_status != AvailabilityStatus.AVAILABLE)

    # Apply liked_only filter (EXISTS subquery on user_videos)
    if liked_only:
        liked_subquery = (
            select(UserVideo.video_id)
            .where(UserVideo.liked.is_(True))
            .distinct()
            .scalar_subquery()
        )
        query = query.where(VideoDB.video_id.in_(liked_subquery))

    # Apply has_transcript filter (EXISTS subquery on video_transcripts)
    if has_transcript:
        transcript_subquery = (
            select(VideoTranscript.video_id).distinct().scalar_subquery()
        )
        query = query.where(VideoDB.video_id.in_(transcript_subquery))

    # Build count query with the same filters
    count_base_query = (
        select(PlaylistMembership)
        .join(VideoDB, PlaylistMembership.video_id == VideoDB.video_id)
        .where(PlaylistMembership.playlist_id == playlist_id)
    )
    if not include_unavailable:
        count_base_query = count_base_query.where(
            VideoDB.availability_status == AvailabilityStatus.AVAILABLE
        )
    if unavailable_only:
        count_base_query = count_base_query.where(
            VideoDB.availability_status != AvailabilityStatus.AVAILABLE
        )
    if liked_only:
        liked_count_subquery = (
            select(UserVideo.video_id)
            .where(UserVideo.liked.is_(True))
            .distinct()
            .scalar_subquery()
        )
        count_base_query = count_base_query.where(
            VideoDB.video_id.in_(liked_count_subquery)
        )
    if has_transcript:
        transcript_count_subquery = (
            select(VideoTranscript.video_id).distinct().scalar_subquery()
        )
        count_base_query = count_base_query.where(
            VideoDB.video_id.in_(transcript_count_subquery)
        )

    count_query = select(func.count()).select_from(count_base_query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Map sort field to database column
    sort_column_map = {
        PlaylistVideoSortField.POSITION: PlaylistMembership.position,
        PlaylistVideoSortField.UPLOAD_DATE: VideoDB.upload_date,
        PlaylistVideoSortField.TITLE: VideoDB.title,
    }
    sort_column = sort_column_map[sort_by]

    # Apply sort order with deterministic secondary sort by video_id (FR-029)
    if sort_order == SortOrder.ASC:
        order_clause = sort_column.asc()
    else:
        order_clause = sort_column.desc()

    query = (
        query.order_by(order_clause, VideoDB.video_id.asc())
        .offset(offset)
        .limit(limit)
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

    return PlaylistVideoListResponse(data=items, pagination=pagination)
