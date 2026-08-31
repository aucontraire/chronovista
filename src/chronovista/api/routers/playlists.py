"""Playlist list and detail endpoints.

This module provides API endpoints for playlist management,
including list with linked/unlinked filters, detail view,
and video listing with position ordering.
"""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_db,
    get_playlist_repository,
    get_transcript_segment_repository,
    get_user_video_repository,
    require_auth,
)
from chronovista.api.routers.responses import GET_ITEM_ERRORS, LIST_ERRORS
from chronovista.api.schemas.playlists import (
    HiddenPlaylistItem,
    HiddenPlaylistListResponse,
    PlaylistDetail,
    PlaylistDetailResponse,
    PlaylistListItem,
    PlaylistListResponse,
    PlaylistRestoreRequest,
    PlaylistRestoreResponse,
    PlaylistVideoListItem,
    PlaylistVideoListResponse,
    PlaylistWatchStats,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.sorting import SortOrder
from chronovista.api.schemas.videos import TranscriptSummary
from chronovista.db.models import VideoTranscript
from chronovista.exceptions import BadRequestError, NotFoundError
from chronovista.models.enums import PlaylistType, WatchedStatus
from chronovista.repositories.playlist_repository import PlaylistRepository
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.user_video_repository import UserVideoRepository

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


def build_transcript_summary(
    transcripts: list[VideoTranscript],
    has_corrections: bool = False,
) -> TranscriptSummary:
    """Build transcript summary from transcript list.

    Parameters
    ----------
    transcripts : List[VideoTranscript]
        List of transcript database models.
    has_corrections : bool
        Whether any segment for this video has a user correction.

    Returns
    -------
    TranscriptSummary
        Summary containing count, languages, manual indicator, and corrections flag.
    """
    if not transcripts:
        return TranscriptSummary(
            count=0,
            languages=[],
            has_manual=False,
            has_corrections=has_corrections,
        )

    languages = list({t.language_code for t in transcripts})
    has_manual = any(t.is_cc or t.transcript_type == "MANUAL" for t in transcripts)

    return TranscriptSummary(
        count=len(transcripts),
        languages=sorted(languages),
        has_manual=has_manual,
        has_corrections=has_corrections,
    )


@router.get("/playlists", response_model=PlaylistListResponse, responses=LIST_ERRORS)
async def list_playlists(
    session: AsyncSession = Depends(get_db),
    playlist_repo: PlaylistRepository = Depends(get_playlist_repository),
    linked: bool | None = Query(
        None,
        description="Filter for YouTube-linked playlists (PL/LL/WL/HL prefix)",
    ),
    unlinked: bool | None = Query(
        None,
        description="Filter for internal playlists (int_ prefix)",
    ),
    playlist_type: PlaylistType | None = Query(
        None,
        description="Filter by playlist type (regular, liked, watch_later, "
        "history, favorites)",
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

    playlists, total = await playlist_repo.list_filtered(
        session,
        linked=linked,
        unlinked=unlinked,
        playlist_type=playlist_type,
        sort_by=sort_by.value,
        descending=(sort_order == SortOrder.DESC),
        skip=offset,
        limit=limit,
    )

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


@router.get(
    "/playlists/hidden",
    response_model=HiddenPlaylistListResponse,
    responses=LIST_ERRORS,
)
async def list_hidden_playlists(
    session: AsyncSession = Depends(get_db),
    playlist_repo: PlaylistRepository = Depends(get_playlist_repository),
) -> HiddenPlaylistListResponse:
    """List playlists hidden from every other view by ``deleted_flag``.

    Declared before ``/playlists/{playlist_id}`` deliberately: FastAPI matches
    routes in definition order, and "hidden" is a valid playlist-id shape, so
    the reverse order would send every request here to the detail handler and
    return a 404.

    Parameters
    ----------
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    HiddenPlaylistListResponse
        Hidden playlists, most recently hidden first.
    """
    playlists = await playlist_repo.get_hidden_playlists(session)
    return HiddenPlaylistListResponse(
        data=[HiddenPlaylistItem.model_validate(p) for p in playlists],
        total=len(playlists),
    )


@router.post(
    "/playlists/restore",
    response_model=PlaylistRestoreResponse,
    responses=LIST_ERRORS,
)
async def restore_playlists(
    request: PlaylistRestoreRequest,
    session: AsyncSession = Depends(get_db),
    playlist_repo: PlaylistRepository = Depends(get_playlist_repository),
) -> PlaylistRestoreResponse:
    """Un-hide playlists that were marked deleted.

    A hidden playlist never returns on its own — enrichment selects only live
    rows, so it leaves the population permanently. Until this endpoint the only
    route back was a hand-written UPDATE (#149).

    IDs that are not currently hidden are reported in ``skipped`` rather than
    raising: a partial restore is a useful outcome, and failing the whole
    request because one id was already visible would be worse than saying so.

    Parameters
    ----------
    request : PlaylistRestoreRequest
        Playlist IDs to restore (non-empty).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    PlaylistRestoreResponse
        Count restored, plus any requested IDs that were not hidden.
    """
    hidden_ids = {
        p.playlist_id for p in await playlist_repo.get_hidden_playlists(session)
    }

    targets = [pid for pid in request.playlist_ids if pid in hidden_ids]
    skipped = [pid for pid in request.playlist_ids if pid not in hidden_ids]

    restored = await playlist_repo.restore_playlists(session, targets)
    await session.commit()

    return PlaylistRestoreResponse(restored=restored, skipped=skipped)


@router.get(
    "/playlists/{playlist_id}",
    response_model=PlaylistDetailResponse,
    responses=GET_ITEM_ERRORS,
)
async def get_playlist(
    playlist_id: str = Path(
        ...,
        min_length=2,
        max_length=50,
        description="Playlist ID (YouTube or internal)",
    ),
    session: AsyncSession = Depends(get_db),
    playlist_repo: PlaylistRepository = Depends(get_playlist_repository),
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
    playlist = await playlist_repo.get_active_by_playlist_id(session, playlist_id)

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
    watched_status: WatchedStatus = Query(
        WatchedStatus.ALL,
        description=(
            "Filter by watched status (all, watched, unwatched). Watched-status "
            "comes from watch history, never from playlist membership."
        ),
    ),
    session: AsyncSession = Depends(get_db),
    playlist_repo: PlaylistRepository = Depends(get_playlist_repository),
    segment_repo: TranscriptSegmentRepository = Depends(
        get_transcript_segment_repository
    ),
    user_video_repo: UserVideoRepository = Depends(get_user_video_repository),
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
    watched_status : WatchedStatus
        Restrict results to watched or unwatched videos (default: all). Watched
        means a watch-history record exists; it is never inferred from playlist
        membership. Narrows ``pagination.total`` but deliberately not ``stats``,
        which always describes the whole playlist.
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
    # First verify playlist exists. Unlike get_playlist, this does NOT filter
    # deleted_flag — a hidden playlist still lists its videos.
    if not await playlist_repo.exists_by_playlist_id(session, playlist_id):
        raise NotFoundError(
            resource_type="Playlist",
            identifier=playlist_id,
        )

    rows, total, stats_total, stats_watched = (
        await playlist_repo.list_playlist_videos_page(
            session,
            playlist_id=playlist_id,
            include_unavailable=include_unavailable,
            unavailable_only=unavailable_only,
            liked_only=liked_only,
            has_transcript=has_transcript,
            watched_status=watched_status,
            sort_by=sort_by.value,
            descending=(sort_order == SortOrder.DESC),
            skip=offset,
            limit=limit,
        )
    )
    stats = PlaylistWatchStats(
        playlist_total=stats_total,
        watched=stats_watched,
        unwatched=stats_total - stats_watched,
    )

    # Batch lookups for the page (one query each, never per-row).
    video_ids = [video.video_id for _membership, video in rows]
    videos_with_corrections = await segment_repo.get_video_ids_with_corrections(
        session, video_ids
    )

    # Which videos on this page have been watched (FR-010). Under a watched filter
    # the page's WHERE clause already settled it — every row passed (WATCHED) or
    # failed (UNWATCHED) the membership test — so only the unfiltered case needs a
    # lookup. That lookup is one query per page, never per row.
    watched_ids: set[str] = set()
    if watched_status is WatchedStatus.WATCHED:
        watched_ids = set(video_ids)
    elif watched_status is WatchedStatus.UNWATCHED:
        watched_ids = set()
    else:
        watched_ids = await user_video_repo.get_watched_video_ids_in(session, video_ids)

    # Transform to response items
    items: list[PlaylistVideoListItem] = []
    for membership, video in rows:
        transcript_summary = build_transcript_summary(
            list(video.transcripts),
            has_corrections=video.video_id in videos_with_corrections,
        )
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
                watched=video.video_id in watched_ids,
            )
        )

    # Build pagination
    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return PlaylistVideoListResponse(data=items, pagination=pagination, stats=stats)
