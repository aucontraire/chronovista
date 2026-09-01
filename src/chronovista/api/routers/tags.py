"""Tag list and detail endpoints.

This module provides API endpoints for accessing tag data aggregated from
the video_tags junction table with video counts. Unlike topics which have a
dedicated table, tags are queried via GROUP BY aggregation on video_tags.

Route Order: The videos endpoint MUST be defined before the detail endpoint
to ensure correct URL matching, following the same pattern as topics router.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_db,
    get_video_repository,
    get_video_tag_repository,
    require_auth,
)
from chronovista.api.routers.responses import GET_ITEM_ERRORS, LIST_ERRORS
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.tags import (
    TagDetail,
    TagDetailResponse,
    TagListItem,
    TagListResponse,
)
from chronovista.api.schemas.videos import VideoListItem, VideoListResponse
from chronovista.exceptions import NotFoundError
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_tag_repository import VideoTagRepository
from chronovista.utils.fuzzy import find_similar

logger = logging.getLogger(__name__)

# Rate limiting configuration for autocomplete (T098)
# In-memory rate limiter - 50 requests per minute per client
RATE_LIMIT_AUTOCOMPLETE = 50  # requests per minute
RATE_LIMIT_WINDOW_SECONDS = 60

# Storage for rate limit tracking
_autocomplete_request_counts: dict[str, list[float]] = defaultdict(list)


def _get_client_id(request: Request) -> str:
    """
    Get client identifier from request.

    Uses X-Forwarded-For header for proxied requests, falls back to client host.

    Parameters
    ----------
    request : Request
        FastAPI request object.

    Returns
    -------
    str
        Client identifier (IP address or "unknown").
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(
    client_id: str,
    request_counts: dict[str, list[float]],
    rate_limit: int,
) -> tuple[bool, int]:
    """
    Check if client has exceeded rate limit.

    Cleans up old entries and checks if current request should be allowed.

    Parameters
    ----------
    client_id : str
        Client identifier.
    request_counts : Dict[str, List[float]]
        Storage for request timestamps per client.
    rate_limit : int
        Maximum requests allowed per minute.

    Returns
    -------
    Tuple[bool, int]
        Tuple of (is_allowed, retry_after_seconds).
        If is_allowed is True, retry_after is 0.
        If is_allowed is False, retry_after indicates seconds until a slot opens.
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    # Clean old entries (older than window)
    request_counts[client_id] = [
        ts for ts in request_counts[client_id] if ts > window_start
    ]

    # Check if limit exceeded
    if len(request_counts[client_id]) >= rate_limit:
        # Find when the oldest request in window will expire
        oldest = min(request_counts[client_id])
        retry_after = int(oldest + RATE_LIMIT_WINDOW_SECONDS - now) + 1
        return False, max(1, retry_after)

    # Add current request timestamp
    request_counts[client_id].append(now)
    return True, 0


router = APIRouter(dependencies=[Depends(require_auth)])


@router.get(
    "/tags",
    response_model=TagListResponse,
    responses={
        **LIST_ERRORS,
        429: {"description": "Rate limit exceeded"},
    },
)
async def list_tags(
    request: Request,
    session: AsyncSession = Depends(get_db),
    q: str = Query(
        None,
        min_length=1,
        max_length=100,
        description="Search/autocomplete query for tag names",
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    tag_repo: VideoTagRepository = Depends(get_video_tag_repository),
) -> TagListResponse | JSONResponse:
    """
    List tags with pagination and video counts.

    Returns tags sorted by video_count in descending order by default.
    Tags are aggregated from the video_tags junction table, excluding
    videos with availability_status != 'available'.

    Supports autocomplete via the `q` query parameter for filtering tags.

    Parameters
    ----------
    request : Request
        FastAPI request object (for rate limiting).
    session : AsyncSession
        Database session from dependency.
    q : str, optional
        Search query for autocomplete (filters tags by prefix).
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).

    Returns
    -------
    TagListResponse
        Paginated list of tags with video counts.

    Raises
    ------
    JSONResponse (429)
        Rate limit exceeded (50 req/min for autocomplete queries).
    """
    # T098: Rate limiting for autocomplete queries (50 req/min)
    # Only apply rate limiting when q parameter is provided (autocomplete mode)
    if q is not None:
        client_id = _get_client_id(request)
        is_allowed, retry_after = _check_rate_limit(
            client_id, _autocomplete_request_counts, RATE_LIMIT_AUTOCOMPLETE
        )
        if not is_allowed:
            logger.warning(
                "[tags] Autocomplete rate limit exceeded for client %s, retry_after=%ds",
                client_id,
                retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Maximum 50 autocomplete requests per minute.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

    # Tags with video counts (availability-filtered, optional autocomplete
    # prefix), ordered by count desc; total is the distinct-tag count.
    total, rows = await tag_repo.list_tags_with_counts(
        session,
        include_unavailable=include_unavailable,
        query=q,
        offset=offset,
        limit=limit,
    )

    items: list[TagListItem] = [
        TagListItem(tag=tag, video_count=video_count) for tag, video_count in rows
    ]

    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    # T049b: Fuzzy suggestions when no prefix matches found
    suggestions: list[str] | None = None
    if q is not None and len(items) == 0 and len(q) >= 2:
        try:
            # Optimization: Only consider tags with similar length
            # Levenshtein distance can't be ≤2 if lengths differ by >2
            min_len = max(1, len(q) - 2)
            max_len = len(q) + 2

            # Query tags that are likely matches:
            # 1. Similar length AND start with first 2 chars (handles typos at end)
            # 2. Similar length AND contain the query substring
            prefix = q[:2].lower() if len(q) >= 2 else q.lower()

            candidate_tags = await tag_repo.find_fuzzy_candidates(
                session,
                prefix=prefix,
                substring=q.lower(),
                min_len=min_len,
                max_len=max_len,
                limit=500,
            )

            logger.debug(
                "[tags] Fuzzy search for '%s': %d candidates (prefix='%s', len %d-%d)",
                q,
                len(candidate_tags),
                prefix,
                min_len,
                max_len,
            )

            # Find similar tags using Levenshtein distance
            # Return more than needed so frontend can filter out already-selected
            suggestions = find_similar(
                q,
                candidate_tags,
                max_distance=2,
                limit=10,  # Frontend will filter and show first 3 unselected
                case_sensitive=False,
            )

            if suggestions:
                logger.info(
                    "[tags] No exact matches for '%s', suggesting: %s",
                    q,
                    suggestions,
                )
        except Exception as e:
            logger.warning("[tags] Failed to compute fuzzy suggestions: %s", e)
            suggestions = None

    return TagListResponse(data=items, pagination=pagination, suggestions=suggestions)


# IMPORTANT: This endpoint MUST be defined before the detail endpoint below
# to ensure correct URL matching, following the same pattern as topics router.
@router.get(
    "/tags/{tag}/videos", response_model=VideoListResponse, responses=GET_ITEM_ERRORS
)
async def get_tag_videos(
    tag: str = Path(
        ...,
        description="Tag name (URL-encoded if contains special characters like #, /, etc.)",
        examples=["music", "gaming", "%23tutorial"],
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
    tag_repo: VideoTagRepository = Depends(get_video_tag_repository),
    video_repo: VideoRepository = Depends(get_video_repository),
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
    # Verify tag exists (any matching video under the availability filter)
    if not await tag_repo.tag_exists(
        session, tag, include_unavailable=include_unavailable
    ):
        raise NotFoundError(
            resource_type="Tag",
            identifier=tag,
            hint="Verify the tag name or check available tags.",
        )

    total, videos = await video_repo.list_by_tag(
        session,
        tag,
        include_unavailable=include_unavailable,
        offset=offset,
        limit=limit,
    )

    # Transform to response (reuse pattern from topics router)
    items: list[VideoListItem] = []
    for video in videos:
        # Build transcript summary
        transcripts = list(video.transcripts) if video.transcripts else []
        transcript_count = len(transcripts)
        languages = list({t.language_code for t in transcripts})
        has_manual = any(t.is_cc or t.transcript_type == "MANUAL" for t in transcripts)

        from chronovista.api.schemas.videos import TranscriptSummary

        transcript_summary = TranscriptSummary(
            count=transcript_count,
            languages=sorted(languages),
            has_manual=has_manual,
        )

        channel_title = video.channel.title if video.channel else None

        # Extract category info
        category_id_val = video.category_id if hasattr(video, "category_id") else None
        category_name = (
            video.category.name
            if hasattr(video, "category") and video.category
            else None
        )

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
                tags=[],  # Not loading tags in tag videos endpoint
                category_id=category_id_val,
                category_name=category_name,
                topics=[],  # Not loading topics in this endpoint
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


@router.get("/tags/{tag}", response_model=TagDetailResponse, responses=GET_ITEM_ERRORS)
async def get_tag(
    tag: str = Path(
        ...,
        description="Tag name (URL-encoded if contains special characters like #, /, etc.)",
        examples=["music", "gaming", "%23tutorial"],
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    session: AsyncSession = Depends(get_db),
    tag_repo: VideoTagRepository = Depends(get_video_tag_repository),
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
    result = await tag_repo.get_tag_with_count(
        session, tag, include_unavailable=include_unavailable
    )

    if result is None:
        raise NotFoundError(
            resource_type="Tag",
            identifier=tag,
            hint="Verify the tag name or check available tags.",
        )

    tag_name, video_count = result
    detail = TagDetail(tag=tag_name, video_count=video_count)

    return TagDetailResponse(data=detail)
