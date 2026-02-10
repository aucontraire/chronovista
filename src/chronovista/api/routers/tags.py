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
from typing import Dict, List, Tuple

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import GET_ITEM_ERRORS, LIST_ERRORS
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
from chronovista.utils.fuzzy import find_similar

logger = logging.getLogger(__name__)

# Rate limiting configuration for autocomplete (T098)
# In-memory rate limiter - 50 requests per minute per client
RATE_LIMIT_AUTOCOMPLETE = 50  # requests per minute
RATE_LIMIT_WINDOW_SECONDS = 60

# Storage for rate limit tracking
_autocomplete_request_counts: Dict[str, List[float]] = defaultdict(list)


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
    request_counts: Dict[str, List[float]],
    rate_limit: int,
) -> Tuple[bool, int]:
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
        ts for ts in request_counts[client_id]
        if ts > window_start
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
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> TagListResponse | JSONResponse:
    """
    List tags with pagination and video counts.

    Returns tags sorted by video_count in descending order by default.
    Tags are aggregated from the video_tags junction table, excluding
    videos with deleted_flag=true.

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

    # Apply autocomplete filter if q parameter is provided
    if q is not None:
        # Use ILIKE for case-insensitive prefix matching
        query = query.where(VideoTag.tag.ilike(f"{q}%"))

    # Total count of unique tags (with optional filter)
    count_base = (
        select(func.count(func.distinct(VideoTag.tag)))
        .select_from(VideoTag)
        .join(Video, VideoTag.video_id == Video.video_id)
        .where(Video.deleted_flag.is_(False))
    )
    if q is not None:
        count_base = count_base.where(VideoTag.tag.ilike(f"{q}%"))
    total_result = await session.execute(count_base)
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

    # T049b: Fuzzy suggestions when no prefix matches found
    suggestions: List[str] | None = None
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

            candidate_tags_query = (
                select(VideoTag.tag)
                .where(func.length(VideoTag.tag) >= min_len)
                .where(func.length(VideoTag.tag) <= max_len)
                .where(
                    # Match tags starting with similar prefix OR containing query
                    (func.lower(VideoTag.tag).like(f"{prefix}%")) |
                    (func.lower(VideoTag.tag).like(f"%{q.lower()}%"))
                )
                .distinct()
                .limit(500)
            )
            candidate_result = await session.execute(candidate_tags_query)
            candidate_tags = [row[0] for row in candidate_result.all()]

            logger.debug(
                "[tags] Fuzzy search for '%s': %d candidates (prefix='%s', len %d-%d)",
                q, len(candidate_tags), prefix, min_len, max_len
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
@router.get("/tags/{tag}/videos", response_model=VideoListResponse, responses=GET_ITEM_ERRORS)
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

        # Extract category info
        category_id_val = video.category_id if hasattr(video, "category_id") else None
        category_name = video.category.name if hasattr(video, "category") and video.category else None

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
