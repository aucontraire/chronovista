"""Canonical tag list, detail, and video endpoints.

This module provides API endpoints for accessing canonical tag data from
the tag normalization system (ADR-003). Canonical tags group raw tag
variants (aliases) under a single normalized form with aggregated counts.

Route Order: The videos endpoint MUST be defined before the detail endpoint
to ensure correct URL matching, following the same pattern as tags router.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, List, Tuple

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import GET_ITEM_ERRORS, LIST_ERRORS
from chronovista.api.schemas.canonical_tags import (
    CanonicalTagDetail,
    CanonicalTagDetailResponse,
    CanonicalTagListItem,
    CanonicalTagListResponse,
    CanonicalTagSuggestion,
    TagAliasItem,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.videos import TranscriptSummary, VideoListItem, VideoListResponse
from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.exceptions import NotFoundError
from chronovista.repositories.canonical_tag_repository import CanonicalTagRepository
from chronovista.utils.fuzzy import find_similar

logger = logging.getLogger(__name__)

# Query timeout (NFR-006: 10s timeout for video queries)
QUERY_TIMEOUT_SECONDS = 10

# Rate limiting configuration for autocomplete (T016)
# In-memory rate limiter - 50 requests per minute per client
RATE_LIMIT_REQUESTS = 50  # requests per minute
RATE_LIMIT_WINDOW_SECONDS = 60

# Fuzzy suggestion pool size (T015)
FUZZY_CANDIDATE_POOL_SIZE = 5000

# Storage for rate limit tracking
_request_counts: Dict[str, List[float]] = defaultdict(list)


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

# Module-level repository instance (stateless, safe to share)
_repository = CanonicalTagRepository()


@router.get(
    "/canonical-tags/{normalized_form}/videos",
    response_model=VideoListResponse,
    responses={
        **GET_ITEM_ERRORS,
        504: {"description": "Query timeout exceeded"},
    },
)
async def get_canonical_tag_videos(
    normalized_form: str = Path(
        ..., description="Normalized form of the canonical tag"
    ),
    limit: int = Query(
        20, ge=1, le=100, description="Maximum number of items to return"
    ),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    include_unavailable: bool = Query(
        False, description="Include unavailable records in results"
    ),
    session: AsyncSession = Depends(get_db),
) -> VideoListResponse | JSONResponse:
    """
    List videos associated with a canonical tag.

    Returns videos whose raw tags map to the given canonical tag's
    normalized form, ordered by upload date descending.

    Parameters
    ----------
    normalized_form : str
        Normalized form of the canonical tag.
    limit : int
        Maximum number of items to return (1-100, default 20).
    offset : int
        Number of items to skip (default 0).
    include_unavailable : bool
        Include unavailable records in results (default False).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    VideoListResponse
        Paginated list of videos associated with the canonical tag.

    Raises
    ------
    NotFoundError
        404 if canonical tag not found.
    JSONResponse (504)
        Query timeout exceeded per NFR-006.
    """
    start = time.monotonic()

    # Verify canonical tag exists
    tag = await _repository.get_by_normalized_form(session, normalized_form)
    if tag is None:
        raise NotFoundError(
            resource_type="Canonical Tag",
            identifier=normalized_form,
            hint="Verify the normalized form or check available canonical tags.",
        )

    # Execute video query with timeout (NFR-006)
    try:
        videos, total = await asyncio.wait_for(
            _repository.get_videos_by_normalized_form(
                session,
                normalized_form,
                include_unavailable=include_unavailable,
                skip=offset,
                limit=limit,
            ),
            timeout=QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            "[canonical-tags] Query timeout exceeded (%ds) for normalized_form=%s",
            QUERY_TIMEOUT_SECONDS,
            normalized_form,
        )
        return JSONResponse(
            status_code=504,
            content={
                "detail": (
                    f"Query timeout exceeded. Maximum query time is "
                    f"{QUERY_TIMEOUT_SECONDS} seconds."
                ),
                "retry_after": 5,
            },
            headers={"Retry-After": "5"},
        )

    # Build response items following the same pattern as tags.py / videos.py
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

        # Extract category info
        category_id_val = (
            video.category_id if hasattr(video, "category_id") else None
        )
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
                tags=[],  # Not loading raw tags in canonical tag videos endpoint
                category_id=category_id_val,
                category_name=category_name,
                topics=[],  # Not loading topics in this endpoint
                availability_status=video.availability_status,
            )
        )

    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    elapsed = time.monotonic() - start
    logger.info(
        "Canonical tag videos query took %.3fs (normalized_form=%s, total=%d)",
        elapsed,
        normalized_form,
        total,
    )

    return VideoListResponse(data=items, pagination=pagination)


@router.get(
    "/canonical-tags/{normalized_form}",
    response_model=CanonicalTagDetailResponse,
    responses=GET_ITEM_ERRORS,
)
async def get_canonical_tag_detail(
    normalized_form: str = Path(
        ..., description="Normalized form of the canonical tag"
    ),
    alias_limit: int = Query(
        5, ge=1, le=50, description="Maximum number of top aliases to return"
    ),
    session: AsyncSession = Depends(get_db),
) -> CanonicalTagDetailResponse:
    """
    Get detail for a single canonical tag by its normalized form.

    Returns the canonical tag with its display form, alias count,
    video count, top aliases, and timestamps.

    Parameters
    ----------
    normalized_form : str
        Normalized form of the canonical tag.
    alias_limit : int
        Maximum number of top aliases to return (1-50, default 5).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    CanonicalTagDetailResponse
        Full canonical tag detail with top aliases.

    Raises
    ------
    NotFoundError
        404 if canonical tag not found.
    """
    start = time.monotonic()

    # Look up canonical tag
    tag = await _repository.get_by_normalized_form(session, normalized_form)
    if tag is None:
        raise NotFoundError(
            resource_type="Canonical Tag",
            identifier=normalized_form,
            hint="Verify the normalized form or check available canonical tags.",
        )

    # Get top aliases
    aliases = await _repository.get_top_aliases(
        session, tag.id, limit=alias_limit
    )

    # Build alias items
    alias_items: List[TagAliasItem] = [
        TagAliasItem(
            raw_form=alias.raw_form,
            occurrence_count=alias.occurrence_count,
        )
        for alias in aliases
    ]

    detail = CanonicalTagDetail(
        canonical_form=tag.canonical_form,
        normalized_form=tag.normalized_form,
        alias_count=tag.alias_count,
        video_count=tag.video_count,
        top_aliases=alias_items,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
    )

    elapsed = time.monotonic() - start
    logger.info(
        "Canonical tag detail query took %.3fs (normalized_form=%s)",
        elapsed,
        normalized_form,
    )

    return CanonicalTagDetailResponse(data=detail)


@router.get(
    "/canonical-tags",
    response_model=CanonicalTagListResponse,
    responses={
        **LIST_ERRORS,
        429: {"description": "Rate limit exceeded"},
    },
)
async def list_canonical_tags(
    request: Request,
    q: str | None = Query(
        None,
        min_length=1,
        max_length=500,
        description="Search/autocomplete query for canonical tag names",
    ),
    limit: int = Query(
        20, ge=1, le=100, description="Maximum number of items to return"
    ),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    session: AsyncSession = Depends(get_db),
) -> CanonicalTagListResponse | JSONResponse:
    """
    List all canonical tags with pagination.

    Returns canonical tags ordered by video count descending, with
    pagination metadata. Supports prefix search via the `q` parameter.
    When ``q`` is provided and prefix search returns zero results,
    fuzzy suggestions are computed using Levenshtein distance.

    Parameters
    ----------
    request : Request
        FastAPI request object (for rate limiting).
    q : str | None, optional
        Search query for prefix matching on canonical/normalized forms.
    limit : int
        Maximum number of items to return (1-100, default 20).
    offset : int
        Number of items to skip (default 0).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    CanonicalTagListResponse
        Paginated list of canonical tags with video counts.

    Raises
    ------
    JSONResponse (429)
        Rate limit exceeded (50 req/min for autocomplete queries).
    """
    # T016: Rate limiting for autocomplete queries (50 req/min)
    # Only apply rate limiting when q parameter is provided (autocomplete mode)
    if q is not None:
        client_id = _get_client_id(request)
        is_allowed, retry_after = _check_rate_limit(
            client_id, _request_counts, RATE_LIMIT_REQUESTS
        )
        if not is_allowed:
            logger.warning(
                "[canonical-tags] Autocomplete rate limit exceeded for client %s, retry_after=%ds",
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

    start = time.monotonic()

    items_orm, total = await _repository.search(
        session, q=q, skip=offset, limit=limit
    )

    items: List[CanonicalTagListItem] = [
        CanonicalTagListItem(
            canonical_form=tag.canonical_form,
            normalized_form=tag.normalized_form,
            alias_count=tag.alias_count,
            video_count=tag.video_count,
        )
        for tag in items_orm
    ]

    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    # T015: Fuzzy suggestions when no prefix matches found
    suggestions: List[CanonicalTagSuggestion] | None = None
    if q is not None and len(items) == 0 and len(q) >= 2:
        try:
            # Load top N active canonical tags ordered by video_count DESC
            pool_query = (
                select(CanonicalTagDB)
                .where(CanonicalTagDB.status == "active")
                .order_by(desc(CanonicalTagDB.video_count))
                .limit(FUZZY_CANDIDATE_POOL_SIZE)
            )
            pool_result = await session.execute(pool_query)
            pool_tags = list(pool_result.scalars().all())

            # Extract canonical_form values as candidates
            candidates = [tag.canonical_form for tag in pool_tags]

            # Build a lookup from canonical_form -> normalized_form
            form_to_normalized = {
                tag.canonical_form: tag.normalized_form for tag in pool_tags
            }

            logger.debug(
                "[canonical-tags] Fuzzy search for '%s': %d candidates from pool",
                q,
                len(candidates),
            )

            # Find similar canonical forms using Levenshtein distance
            similar_forms = find_similar(
                q,
                candidates,
                max_distance=2,
                limit=10,
            )

            if similar_forms:
                suggestions = [
                    CanonicalTagSuggestion(
                        canonical_form=form,
                        normalized_form=form_to_normalized[form],
                    )
                    for form in similar_forms
                ]
                logger.info(
                    "[canonical-tags] No exact matches for '%s', suggesting: %s",
                    q,
                    [s.canonical_form for s in suggestions],
                )
        except Exception as e:
            logger.warning(
                "[canonical-tags] Failed to compute fuzzy suggestions: %s", e
            )
            suggestions = None

    elapsed = time.monotonic() - start
    logger.info(
        "Canonical tag list query took %.3fs (q=%s, total=%d)",
        elapsed,
        q,
        total,
    )

    return CanonicalTagListResponse(
        data=items, pagination=pagination, suggestions=suggestions
    )
