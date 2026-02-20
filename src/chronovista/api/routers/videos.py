"""Video list and detail endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from fastapi import APIRouter, Body, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.api.deps import get_db, get_recovery_deps, require_auth
from chronovista.api.routers.responses import (
    CONFLICT_RESPONSE,
    GET_ITEM_ERRORS,
    LIST_ERRORS,
    NOT_FOUND_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from chronovista.api.schemas.filters import FilterType, FilterWarning, FilterWarningCode
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.sorting import SortOrder
from chronovista.api.schemas.topics import TopicSummary
from chronovista.api.schemas.videos import (
    AlternativeUrlRequest,
    TranscriptSummary,
    VideoDetail,
    VideoDetailResponse,
    VideoListItem,
    VideoListResponse,
    VideoListResponseWithWarnings,
    VideoPlaylistMembership,
    VideoPlaylistsResponse,
    VideoRecoveryResponse,
    VideoRecoveryResultData,
)
from chronovista.db.models import TopicCategory, UserVideo as UserVideoDB, Video as VideoDB, VideoCategory
from chronovista.db.models import VideoTag, VideoTopic, VideoTranscript
from chronovista.exceptions import BadRequestError, CDXError, ConflictError, NotFoundError
from chronovista.models.enums import AvailabilityStatus
from chronovista.repositories.playlist_membership_repository import (
    PlaylistMembershipRepository,
)

logger = logging.getLogger(__name__)


class VideoSortField(str, Enum):
    """Sort fields for video list endpoint.

    Values correspond to database column names used in ORDER BY clauses.
    The frontend display label "Date Added" maps to ``upload_date`` (FR-017).
    """

    UPLOAD_DATE = "upload_date"
    TITLE = "title"


# Mapping from VideoSortField enum to actual SQLAlchemy column references.
# Used by the list_videos endpoint to build ORDER BY clauses.
_VIDEO_SORT_COLUMN_MAP = {
    VideoSortField.UPLOAD_DATE: VideoDB.upload_date,
    VideoSortField.TITLE: VideoDB.title,
}

# Filter limits per FR-034
MAX_TAGS = 10
MAX_TOPICS = 10
MAX_TOTAL_FILTERS = 15

# Rate limiting configuration (T097)
# In-memory rate limiter - requests per minute per client
RATE_LIMIT_FILTER_QUERIES = 100  # requests per minute
RATE_LIMIT_WINDOW_SECONDS = 60

# Storage for rate limit tracking
_filter_request_counts: Dict[str, List[float]] = defaultdict(list)

# Query timeout per FR-036 (T099)
QUERY_TIMEOUT_SECONDS = 10

# Recovery idempotency guard (T033)
# Skip Wayback Machine requests if entity was recovered within this window
RECOVERY_IDEMPOTENCY_MINUTES = 5


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


def build_transcript_summary(transcripts: List[VideoTranscript]) -> TranscriptSummary:
    """
    Build transcript summary from transcript list.

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


def _validate_filter_limits(
    tags: List[str],
    topic_ids: List[str],
    category: Optional[str],
) -> None:
    """
    Validate filter limits per FR-034.

    Parameters
    ----------
    tags : List[str]
        List of tag filters.
    topic_ids : List[str]
        List of topic ID filters.
    category : Optional[str]
        Category filter (single value).

    Raises
    ------
    BadRequestError
        If any filter limit is exceeded.
    """
    # Check tag limit
    if len(tags) > MAX_TAGS:
        raise BadRequestError(
            message=(
                f"Maximum {MAX_TAGS} tags allowed, received {len(tags)}. "
                f"Remove {len(tags) - MAX_TAGS} tags to continue."
            ),
            details={
                "field": "tag",
                "max_allowed": MAX_TAGS,
                "received": len(tags),
                "excess": len(tags) - MAX_TAGS,
            },
        )

    # Check topic limit
    if len(topic_ids) > MAX_TOPICS:
        raise BadRequestError(
            message=(
                f"Maximum {MAX_TOPICS} topics allowed, received {len(topic_ids)}. "
                f"Remove {len(topic_ids) - MAX_TOPICS} topics to continue."
            ),
            details={
                "field": "topic_id",
                "max_allowed": MAX_TOPICS,
                "received": len(topic_ids),
                "excess": len(topic_ids) - MAX_TOPICS,
            },
        )

    # Check total filter count
    total_filters = len(tags) + len(topic_ids) + (1 if category else 0)
    if total_filters > MAX_TOTAL_FILTERS:
        raise BadRequestError(
            message=(
                f"Maximum {MAX_TOTAL_FILTERS} total filters allowed, "
                f"received {total_filters}. "
                f"Remove {total_filters - MAX_TOTAL_FILTERS} filters to continue."
            ),
            details={
                "max_allowed": MAX_TOTAL_FILTERS,
                "received": total_filters,
                "excess": total_filters - MAX_TOTAL_FILTERS,
            },
        )


def _build_parent_path(
    topic: TopicCategory,
    topic_cache: dict[str, TopicCategory],
) -> Optional[str]:
    """
    Build parent path string for a topic.

    Parameters
    ----------
    topic : TopicCategory
        The topic to build path for.
    topic_cache : dict[str, TopicCategory]
        Cache of loaded topics by ID.

    Returns
    -------
    Optional[str]
        Parent path string (e.g., 'Music > Pop music') or None for root topics.
    """
    if not topic.parent_topic_id:
        return None

    path_parts: List[str] = []
    current_id: Optional[str] = topic.parent_topic_id

    # Walk up the parent chain
    while current_id is not None and current_id in topic_cache:
        parent = topic_cache[current_id]
        path_parts.insert(0, parent.category_name)
        current_id = parent.parent_topic_id

    return " > ".join(path_parts) if path_parts else None


async def _validate_tags(
    session: AsyncSession,
    tags: List[str],
) -> Tuple[List[str], List[FilterWarning]]:
    """
    Validate tag filter values exist in the database (FR-042, FR-044, FR-045).

    Invalid or non-existent tags are silently ignored and logged at WARNING level.

    Parameters
    ----------
    session : AsyncSession
        Database session.
    tags : List[str]
        List of tag values to validate.

    Returns
    -------
    Tuple[List[str], List[FilterWarning]]
        Tuple of (valid_tags, warnings) where valid_tags are tags that exist
        in the database and warnings are for invalid tags that were ignored.
    """
    if not tags:
        return [], []

    # Query for tags that exist in the database
    existing_tags_query = (
        select(VideoTag.tag).where(VideoTag.tag.in_(tags)).distinct()
    )
    result = await session.execute(existing_tags_query)
    existing_tags = {row[0] for row in result.fetchall()}

    valid_tags: List[str] = []
    warnings: List[FilterWarning] = []

    for tag in tags:
        if tag in existing_tags:
            valid_tags.append(tag)
        else:
            # FR-045: Log warning for invalid filter parameter
            logger.warning(
                "Invalid tag filter value ignored: '%s' does not exist in database",
                tag,
            )
            # FR-042, FR-044: Silently ignore invalid tags
            warnings.append(
                FilterWarning(
                    code=FilterWarningCode.FILTER_INVALID_VALUE,
                    filter_type=FilterType.TAG,
                    message=f"Tag '{tag}' not found and was ignored",
                )
            )

    return valid_tags, warnings


async def _validate_category(
    session: AsyncSession,
    category: Optional[str],
) -> Tuple[Optional[str], List[FilterWarning]]:
    """
    Validate category filter value exists in the database (FR-042, FR-045).

    Invalid or non-existent category is silently ignored and logged at WARNING level.

    Parameters
    ----------
    session : AsyncSession
        Database session.
    category : Optional[str]
        Category ID to validate.

    Returns
    -------
    Tuple[Optional[str], List[FilterWarning]]
        Tuple of (valid_category, warnings) where valid_category is the category
        if it exists, None otherwise, and warnings for invalid category.
    """
    if not category:
        return None, []

    # Query for category that exists in the database
    existing_category_query = select(VideoCategory.category_id).where(
        VideoCategory.category_id == category
    )
    result = await session.execute(existing_category_query)
    exists = result.scalar_one_or_none() is not None

    if exists:
        return category, []

    # FR-045: Log warning for invalid filter parameter
    logger.warning(
        "Invalid category filter value ignored: '%s' does not exist in database",
        category,
    )
    # FR-042: Silently ignore invalid category
    return None, [
        FilterWarning(
            code=FilterWarningCode.FILTER_INVALID_VALUE,
            filter_type=FilterType.CATEGORY,
            message=f"Category '{category}' not found and was ignored",
        )
    ]


async def _validate_topics(
    session: AsyncSession,
    topic_ids: List[str],
) -> Tuple[List[str], List[FilterWarning]]:
    """
    Validate topic filter values exist in the database (FR-043, FR-045).

    Invalid or non-existent topics are silently ignored and logged at WARNING level.

    Parameters
    ----------
    session : AsyncSession
        Database session.
    topic_ids : List[str]
        List of topic ID values to validate.

    Returns
    -------
    Tuple[List[str], List[FilterWarning]]
        Tuple of (valid_topic_ids, warnings) where valid_topic_ids are topics
        that exist in the database and warnings for invalid topics.
    """
    if not topic_ids:
        return [], []

    # Query for topics that exist in the database
    existing_topics_query = (
        select(TopicCategory.topic_id)
        .where(TopicCategory.topic_id.in_(topic_ids))
        .distinct()
    )
    result = await session.execute(existing_topics_query)
    existing_topics = {row[0] for row in result.fetchall()}

    valid_topics: List[str] = []
    warnings: List[FilterWarning] = []

    for topic_id in topic_ids:
        if topic_id in existing_topics:
            valid_topics.append(topic_id)
        else:
            # FR-045: Log warning for invalid filter parameter
            logger.warning(
                "Invalid topic filter value ignored: '%s' does not exist in database",
                topic_id,
            )
            # FR-043: Silently ignore invalid topics
            warnings.append(
                FilterWarning(
                    code=FilterWarningCode.FILTER_INVALID_VALUE,
                    filter_type=FilterType.TOPIC,
                    message=f"Topic '{topic_id}' not found and was ignored",
                )
            )

    return valid_topics, warnings


@router.get(
    "/videos",
    response_model=Union[VideoListResponse, VideoListResponseWithWarnings],
    responses={
        **LIST_ERRORS,
        429: {"description": "Rate limit exceeded"},
        504: {"description": "Query timeout exceeded"},
    },
)
async def list_videos(
    request: Request,
    session: AsyncSession = Depends(get_db),
    channel_id: Optional[str] = Query(
        None,
        min_length=24,
        max_length=24,
        description="Filter by channel ID",
    ),
    has_transcript: Optional[bool] = Query(
        None,
        description="Filter by transcript availability",
    ),
    uploaded_after: Optional[datetime] = Query(
        None,
        description="Filter by upload date (ISO 8601)",
    ),
    uploaded_before: Optional[datetime] = Query(
        None,
        description="Filter by upload date (ISO 8601)",
    ),
    # Classification filters (Feature 020)
    tag: List[str] = Query(
        default=[],
        description="Filter by tag(s) - OR logic between multiple tags. Max 10.",
    ),
    category: Optional[str] = Query(
        None,
        description="Filter by YouTube category ID (single value)",
    ),
    topic_id: List[str] = Query(
        default=[],
        description="Filter by topic ID(s) - OR logic between multiple topics. Max 10.",
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    sort_by: VideoSortField = Query(
        VideoSortField.UPLOAD_DATE,
        description="Sort field (upload_date or title)",
    ),
    sort_order: SortOrder = Query(
        SortOrder.DESC,
        description="Sort order (asc or desc)",
    ),
    liked_only: bool = Query(
        False,
        description="Filter to only liked videos",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> Union[VideoListResponse, VideoListResponseWithWarnings, JSONResponse]:
    """
    List videos with pagination and filtering.

    Supports filtering by channel, transcript availability, date range,
    and classification filters (tags, category, topics).

    Invalid filter values are silently ignored per FR-042 through FR-044,
    with warnings logged (FR-045) and returned in the response (FR-049, FR-050).

    Parameters
    ----------
    session : AsyncSession
        Database session from dependency.
    channel_id : Optional[str]
        Filter by channel ID (24 characters).
    has_transcript : Optional[bool]
        Filter by transcript availability.
    uploaded_after : Optional[datetime]
        Filter videos uploaded after this date.
    uploaded_before : Optional[datetime]
        Filter videos uploaded before this date.
    tag : List[str]
        Filter by tag(s) - OR logic between multiple tags. Max 10.
    category : Optional[str]
        Filter by YouTube category ID (single value).
    topic_id : List[str]
        Filter by topic ID(s) - OR logic between multiple topics. Max 10.
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).

    Returns
    -------
    Union[VideoListResponse, VideoListResponseWithWarnings]
        Paginated list of videos with metadata and classification data.
        If any filter values were invalid, returns VideoListResponseWithWarnings
        with a warnings array indicating which filters were ignored.

    Raises
    ------
    JSONResponse (429)
        Rate limit exceeded - returns Retry-After header.
    JSONResponse (504)
        Query timeout exceeded per FR-036.
    """
    # T097: Rate limiting for filter queries (100 req/min)
    client_id = _get_client_id(request)
    is_allowed, retry_after = _check_rate_limit(
        client_id, _filter_request_counts, RATE_LIMIT_FILTER_QUERIES
    )
    if not is_allowed:
        logger.warning(
            "[videos] Rate limit exceeded for client %s, retry_after=%ds",
            client_id,
            retry_after,
        )
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded. Maximum 100 requests per minute.",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    # T100: Performance logging - start timing
    query_start_time = time.perf_counter()

    # Validate filter limits (FR-034)
    _validate_filter_limits(tag, topic_id, category)

    # Validate filter values and collect warnings (FR-042 through FR-045)
    all_warnings: List[FilterWarning] = []

    # Validate tags
    valid_tags, tag_warnings = await _validate_tags(session, tag)
    all_warnings.extend(tag_warnings)

    # Validate category
    valid_category, category_warnings = await _validate_category(session, category)
    all_warnings.extend(category_warnings)

    # Validate topics
    valid_topics, topic_warnings = await _validate_topics(session, topic_id)
    all_warnings.extend(topic_warnings)

    # Build base query with relationships for classification data
    query = (
        select(VideoDB)
        .options(selectinload(VideoDB.transcripts))
        .options(selectinload(VideoDB.channel))
        .options(selectinload(VideoDB.tags))
        .options(selectinload(VideoDB.category))
        .options(
            selectinload(VideoDB.video_topics).selectinload(VideoTopic.topic_category)
        )
    )

    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        query = query.where(VideoDB.availability_status == AvailabilityStatus.AVAILABLE)

    # Apply existing filters
    if channel_id:
        query = query.where(VideoDB.channel_id == channel_id)

    if uploaded_after:
        query = query.where(VideoDB.upload_date >= uploaded_after)

    if uploaded_before:
        query = query.where(VideoDB.upload_date <= uploaded_before)

    if has_transcript is not None:
        # Subquery for videos with transcripts
        transcript_subquery = (
            select(VideoTranscript.video_id).distinct().scalar_subquery()
        )
        if has_transcript:
            query = query.where(VideoDB.video_id.in_(transcript_subquery))
        else:
            query = query.where(VideoDB.video_id.notin_(transcript_subquery))

    # Apply classification filters (Feature 020)
    # Use validated filter values (invalid values have been logged and excluded)

    # Tag filter (OR logic within tags)
    if valid_tags:
        tagged_videos = (
            select(VideoTag.video_id)
            .where(VideoTag.tag.in_(valid_tags))
            .distinct()
        )
        query = query.where(VideoDB.video_id.in_(tagged_videos))

    # Category filter
    if valid_category:
        query = query.where(VideoDB.category_id == valid_category)

    # Topic filter (OR logic within topics)
    if valid_topics:
        topic_videos = (
            select(VideoTopic.video_id)
            .where(VideoTopic.topic_id.in_(valid_topics))
            .distinct()
        )
        query = query.where(VideoDB.video_id.in_(topic_videos))

    # Liked-only filter (Feature 027) — EXISTS subquery following has_transcript pattern
    if liked_only:
        liked_subquery = (
            select(UserVideoDB.video_id)
            .where(UserVideoDB.liked.is_(True))
            .distinct()
            .scalar_subquery()
        )
        query = query.where(VideoDB.video_id.in_(liked_subquery))

    # T099: Execute query with timeout (FR-036: 10s timeout)
    try:
        async def execute_queries() -> Tuple[int, List[VideoDB], Dict[str, TopicCategory]]:
            """Execute all database queries for video listing."""
            # Get total count (before pagination)
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar() or 0

            # Apply sorting (Feature 027) with deterministic secondary sort (FR-029)
            sort_column = _VIDEO_SORT_COLUMN_MAP[sort_by]
            if sort_order == SortOrder.ASC:
                order_clause = sort_column.asc()
            else:
                order_clause = sort_column.desc()
            paginated_query = (
                query
                .order_by(order_clause, VideoDB.video_id.asc())
                .offset(offset)
                .limit(limit)
            )

            # Execute query
            result = await session.execute(paginated_query)
            videos = list(result.scalars().all())

            # Collect all topic IDs to build parent paths
            all_topic_ids: set[str] = set()
            for video in videos:
                if video.video_topics:
                    for vt in video.video_topics:
                        all_topic_ids.add(vt.topic_id)
                        if vt.topic_category and vt.topic_category.parent_topic_id:
                            all_topic_ids.add(vt.topic_category.parent_topic_id)

            # Load all relevant topics for path building
            topic_cache: dict[str, TopicCategory] = {}
            if all_topic_ids:
                topic_query_inner = select(TopicCategory).where(
                    TopicCategory.topic_id.in_(all_topic_ids)
                )
                topic_result = await session.execute(topic_query_inner)
                for tc in topic_result.scalars().all():
                    topic_cache[tc.topic_id] = tc

            return total, videos, topic_cache

        total, videos, topic_cache = await asyncio.wait_for(
            execute_queries(),
            timeout=QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            "[videos] Query timeout exceeded (%ds) for client %s",
            QUERY_TIMEOUT_SECONDS,
            client_id,
        )
        return JSONResponse(
            status_code=504,
            content={
                "detail": f"Query timeout exceeded. Maximum query time is {QUERY_TIMEOUT_SECONDS} seconds.",
                "retry_after": 5,
            },
            headers={"Retry-After": "5"},
        )

    # Transform to response items with classification data
    items: List[VideoListItem] = []
    for video in videos:
        transcript_summary = build_transcript_summary(list(video.transcripts))
        channel_title = video.channel.title if video.channel else None

        # Extract tags
        video_tags = [t.tag for t in video.tags] if video.tags else []

        # Extract category info
        category_id_val = video.category_id
        category_name = video.category.name if video.category else None

        # Extract topics with parent paths
        topics_list: List[TopicSummary] = []
        if video.video_topics:
            for vt in video.video_topics:
                tc = vt.topic_category
                if tc:
                    parent_path = _build_parent_path(tc, topic_cache)
                    topics_list.append(
                        TopicSummary(
                            topic_id=tc.topic_id,
                            name=tc.category_name,
                            parent_path=parent_path,
                        )
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
                tags=video_tags,
                category_id=category_id_val,
                category_name=category_name,
                topics=topics_list,
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

    # T100: Performance logging for filter query timing
    query_elapsed_ms = (time.perf_counter() - query_start_time) * 1000
    logger.info(
        "[videos] Filter query completed in %.0fms (tags=%d, category=%s, topics=%d)",
        query_elapsed_ms,
        len(valid_tags),
        1 if valid_category else 0,
        len(valid_topics),
    )

    # Return response with warnings if any filter values were invalid (FR-049, FR-050)
    if all_warnings:
        return VideoListResponseWithWarnings(
            data=items,
            pagination=pagination,
            warnings=all_warnings,
        )

    return VideoListResponse(data=items, pagination=pagination)


@router.get("/videos/{video_id}", response_model=VideoDetailResponse, responses=GET_ITEM_ERRORS)
async def get_video(
    video_id: str = Path(
        ...,
        min_length=11,
        max_length=11,
        description="YouTube video ID (11 characters)",
        example="dQw4w9WgXcQ",
    ),
    session: AsyncSession = Depends(get_db),
) -> VideoDetailResponse:
    """
    Get video details by ID.

    Returns full video metadata including transcript summary.

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    VideoDetailResponse
        Full video details with transcript summary.

    Raises
    ------
    NotFoundError
        If video not found (404).
    """
    # Query video with relationships (including category and topics)
    # Note: No availability_status filter - return all records including unavailable
    query = (
        select(VideoDB)
        .where(VideoDB.video_id == video_id)
        .options(selectinload(VideoDB.transcripts))
        .options(selectinload(VideoDB.channel))
        .options(selectinload(VideoDB.tags))
        .options(selectinload(VideoDB.category))
        .options(
            selectinload(VideoDB.video_topics).selectinload(VideoTopic.topic_category)
        )
    )

    result = await session.execute(query)
    video = result.scalar_one_or_none()

    if not video:
        raise NotFoundError(
            resource_type="Video",
            identifier=video_id,
            hint="Verify the video ID or run: chronovista sync videos",
        )

    # Build response
    transcript_summary = build_transcript_summary(list(video.transcripts))
    channel_title = video.channel.title if video.channel else None
    tags = [tag.tag for tag in video.tags] if video.tags else []
    category_name = video.category.name if video.category else None

    # Build topics list with parent paths
    # Collect all topic IDs for parent path building
    topic_cache: dict[str, TopicCategory] = {}
    if video.video_topics:
        all_topic_ids: set[str] = set()
        for vt in video.video_topics:
            all_topic_ids.add(vt.topic_id)
            if vt.topic_category and vt.topic_category.parent_topic_id:
                all_topic_ids.add(vt.topic_category.parent_topic_id)

        # Load parent topics that might not be in video_topics
        if all_topic_ids:
            parent_query = select(TopicCategory).where(
                TopicCategory.topic_id.in_(all_topic_ids)
            )
            parent_result = await session.execute(parent_query)
            for tc in parent_result.scalars().all():
                topic_cache[tc.topic_id] = tc

    topics_list: List[TopicSummary] = []
    if video.video_topics:
        for vt in video.video_topics:
            tc = vt.topic_category
            if tc:
                parent_path = _build_parent_path(tc, topic_cache)
                topics_list.append(
                    TopicSummary(
                        topic_id=tc.topic_id,
                        name=tc.category_name,
                        parent_path=parent_path,
                    )
                )

    detail = VideoDetail(
        video_id=video.video_id,
        title=video.title,
        description=video.description,
        channel_id=video.channel_id,
        channel_title=channel_title,
        upload_date=video.upload_date,
        duration=video.duration,
        view_count=video.view_count,
        like_count=video.like_count,
        comment_count=video.comment_count,
        tags=tags,
        category_id=video.category_id,
        category_name=category_name,
        default_language=video.default_language,
        made_for_kids=video.made_for_kids,
        transcript_summary=transcript_summary,
        topics=topics_list,
        availability_status=video.availability_status,
        alternative_url=video.alternative_url,
        recovered_at=video.recovered_at,
        recovery_source=video.recovery_source,
    )

    return VideoDetailResponse(data=detail)


def _is_playlist_linked(playlist_id: str) -> bool:
    """
    Determine if a playlist is linked to YouTube.

    Parameters
    ----------
    playlist_id : str
        The playlist ID to check.

    Returns
    -------
    bool
        True if playlist is YouTube-linked, False otherwise.
    """
    return playlist_id.startswith(("PL", "LL", "WL", "HL"))


@router.get(
    "/videos/{video_id}/playlists",
    response_model=VideoPlaylistsResponse,
    responses=GET_ITEM_ERRORS,
)
async def get_video_playlists(
    video_id: str = Path(
        ...,
        min_length=11,
        max_length=11,
        description="YouTube video ID (11 characters)",
        example="dQw4w9WgXcQ",
    ),
    session: AsyncSession = Depends(get_db),
) -> VideoPlaylistsResponse:
    """
    Get all playlists containing a specific video.

    Returns a list of playlists that include this video, along with
    the video's position in each playlist.

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    VideoPlaylistsResponse
        List of playlists containing the video with position info.

    Raises
    ------
    NotFoundError
        If video not found (404).
    """
    # Verify video exists (check all records regardless of availability_status)
    video_query = select(VideoDB).where(VideoDB.video_id == video_id)
    video_result = await session.execute(video_query)
    video = video_result.scalar_one_or_none()

    if not video:
        raise NotFoundError(
            resource_type="Video",
            identifier=video_id,
            hint="Verify the video ID or run: chronovista sync videos",
        )

    # Get all playlist memberships for this video
    membership_repo = PlaylistMembershipRepository()
    memberships = await membership_repo.get_video_playlists(session, video_id)

    # Transform to response schema
    playlist_memberships: List[VideoPlaylistMembership] = []
    for membership in memberships:
        playlist = membership.playlist
        if playlist and not playlist.deleted_flag:
            playlist_memberships.append(
                VideoPlaylistMembership(
                    playlist_id=playlist.playlist_id,
                    title=playlist.title,
                    position=membership.position,
                    is_linked=_is_playlist_linked(playlist.playlist_id),
                    privacy_status=playlist.privacy_status,
                )
            )

    return VideoPlaylistsResponse(data=playlist_memberships)


@router.patch(
    "/videos/{video_id}/alternative-url",
    response_model=VideoDetailResponse,
    responses={
        **GET_ITEM_ERRORS,
        409: {"description": "Cannot set alternative URL on available video"},
        422: {"description": "Validation error (invalid URL format or length)"},
    },
)
async def update_alternative_url(
    video_id: str = Path(
        ...,
        min_length=11,
        max_length=11,
        description="YouTube video ID (11 characters)",
        example="dQw4w9WgXcQ",
    ),
    request_body: AlternativeUrlRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> VideoDetailResponse:
    """
    Set or clear an alternative URL for an unavailable video.

    This endpoint allows setting an alternative URL (e.g., a mirror on another
    platform) for videos that are no longer available on YouTube. Alternative
    URLs can only be set on videos with availability_status != 'available'.

    Per FR-027, alternative URLs are rejected for available videos.
    Per FR-029, URLs must be 500 characters or less (validated by schema).

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    request_body : AlternativeUrlRequest
        Request body containing the alternative URL (or null to clear).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    VideoDetailResponse
        Updated video details including the new alternative_url value.

    Raises
    ------
    NotFoundError
        If video not found (404).
    ConflictError
        If attempting to set alternative URL on an available video (409).
    """
    # Query video without availability filter - we need to check the status
    query = (
        select(VideoDB)
        .where(VideoDB.video_id == video_id)
        .options(selectinload(VideoDB.transcripts))
        .options(selectinload(VideoDB.channel))
        .options(selectinload(VideoDB.tags))
        .options(selectinload(VideoDB.category))
        .options(
            selectinload(VideoDB.video_topics).selectinload(VideoTopic.topic_category)
        )
    )

    result = await session.execute(query)
    video = result.scalar_one_or_none()

    if not video:
        raise NotFoundError(
            resource_type="Video",
            identifier=video_id,
            hint="Verify the video ID or run: chronovista sync videos",
        )

    # FR-027: Reject requests for videos with availability_status='available'
    if video.availability_status == AvailabilityStatus.AVAILABLE.value:
        raise ConflictError(
            message="Alternative URLs can only be set for unavailable videos",
            details={
                "video_id": video_id,
                "availability_status": video.availability_status,
                "hint": "This video is currently available on YouTube",
            },
        )

    # Validate URL format if provided
    alternative_url = request_body.alternative_url
    if alternative_url is not None:
        # Normalize empty string to None
        alternative_url = alternative_url.strip()
        if not alternative_url:
            alternative_url = None

    # URL format validation - ensure it's a valid HTTP/HTTPS URL
    if alternative_url:
        if not (alternative_url.startswith("http://") or alternative_url.startswith("https://")):
            from chronovista.exceptions import APIValidationError

            raise APIValidationError(
                message="Alternative URL must be a valid HTTP or HTTPS URL",
                details={
                    "field": "alternative_url",
                    "value": alternative_url,
                    "constraint": "must start with http:// or https://",
                },
            )

    # Update the alternative_url field
    video.alternative_url = alternative_url
    await session.commit()
    await session.refresh(video)

    # Build response (reuse logic from get_video endpoint)
    transcript_summary = build_transcript_summary(list(video.transcripts))
    channel_title = video.channel.title if video.channel else None
    tags = [tag.tag for tag in video.tags] if video.tags else []
    category_name = video.category.name if video.category else None

    # Build topics list with parent paths
    topic_cache: dict[str, TopicCategory] = {}
    if video.video_topics:
        all_topic_ids: set[str] = set()
        for vt in video.video_topics:
            all_topic_ids.add(vt.topic_id)
            if vt.topic_category and vt.topic_category.parent_topic_id:
                all_topic_ids.add(vt.topic_category.parent_topic_id)

        # Load parent topics that might not be in video_topics
        if all_topic_ids:
            parent_query = select(TopicCategory).where(
                TopicCategory.topic_id.in_(all_topic_ids)
            )
            parent_result = await session.execute(parent_query)
            for tc in parent_result.scalars().all():
                topic_cache[tc.topic_id] = tc

    topics_list: List[TopicSummary] = []
    if video.video_topics:
        for vt in video.video_topics:
            tc = vt.topic_category
            if tc:
                parent_path = _build_parent_path(tc, topic_cache)
                topics_list.append(
                    TopicSummary(
                        topic_id=tc.topic_id,
                        name=tc.category_name,
                        parent_path=parent_path,
                    )
                )

    detail = VideoDetail(
        video_id=video.video_id,
        title=video.title,
        description=video.description,
        channel_id=video.channel_id,
        channel_title=channel_title,
        upload_date=video.upload_date,
        duration=video.duration,
        view_count=video.view_count,
        like_count=video.like_count,
        comment_count=video.comment_count,
        tags=tags,
        category_id=video.category_id,
        category_name=category_name,
        default_language=video.default_language,
        made_for_kids=video.made_for_kids,
        transcript_summary=transcript_summary,
        topics=topics_list,
        availability_status=video.availability_status,
        alternative_url=video.alternative_url,
        recovered_at=video.recovered_at,
        recovery_source=video.recovery_source,
    )

    return VideoDetailResponse(data=detail)


@router.post(
    "/videos/{video_id}/recover",
    response_model=VideoRecoveryResponse,
    responses={
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
        503: {"description": "Wayback Machine CDX API unavailable"},
    },
)
async def recover_video_endpoint(
    video_id: str = Path(
        ...,
        min_length=11,
        max_length=11,
        description="YouTube video ID (11 characters)",
        example="dQw4w9WgXcQ",
    ),
    start_year: Optional[int] = Query(
        None,
        ge=2005,
        le=2026,
        description="Only search snapshots from this year onward (2005-2026)",
    ),
    end_year: Optional[int] = Query(
        None,
        ge=2005,
        le=2026,
        description="Only search snapshots up to this year (2005-2026)",
    ),
    session: AsyncSession = Depends(get_db),
) -> VideoRecoveryResponse | JSONResponse:
    """
    Recover metadata for an unavailable video using the Wayback Machine.

    Queries the Internet Archive's CDX API for archived snapshots of the
    video's YouTube page, extracts metadata from the best available snapshot,
    and updates the database with recovered fields.

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    start_year : Optional[int]
        Only search snapshots from this year onward (2005-2026).
    end_year : Optional[int]
        Only search snapshots up to this year (2005-2026).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    VideoRecoveryResponse
        Recovery result with fields recovered, snapshot used, and duration.

    Raises
    ------
    NotFoundError
        If video not found (404).
    ConflictError
        If video is currently available (409).
    BadRequestError
        If year range is invalid (422-level via BadRequestError).
    JSONResponse (503)
        If the Wayback Machine CDX API is unavailable.
    """
    # Validate year range: end_year >= start_year
    if start_year is not None and end_year is not None and end_year < start_year:
        raise BadRequestError(
            message=(
                f"Invalid year range: end_year ({end_year}) must be "
                f">= start_year ({start_year})"
            ),
            details={
                "start_year": start_year,
                "end_year": end_year,
                "constraint": "end_year >= start_year",
            },
        )

    # Verify video exists
    video_query = select(VideoDB).where(VideoDB.video_id == video_id)
    result = await session.execute(video_query)
    video = result.scalar_one_or_none()

    if not video:
        raise NotFoundError(
            resource_type="Video",
            identifier=video_id,
            hint="Verify the video ID or run: chronovista sync videos",
        )

    # Verify video is unavailable (not available)
    if video.availability_status == AvailabilityStatus.AVAILABLE.value:
        raise ConflictError(
            message="Cannot recover an available video",
            details={
                "video_id": video_id,
                "availability_status": video.availability_status,
                "hint": "Recovery is only supported for unavailable videos",
            },
        )

    # T033: Idempotency guard — skip Wayback Machine if recently recovered
    if video.recovered_at is not None:
        now_utc = datetime.now(timezone.utc)
        # Ensure recovered_at is timezone-aware for comparison
        recovered_at = video.recovered_at
        if recovered_at.tzinfo is None:
            recovered_at = recovered_at.replace(tzinfo=timezone.utc)
        elapsed = now_utc - recovered_at
        if elapsed < timedelta(minutes=RECOVERY_IDEMPOTENCY_MINUTES):
            logger.info(
                "Video %s was already recovered %s ago (< %d min); "
                "returning cached result",
                video_id,
                elapsed,
                RECOVERY_IDEMPOTENCY_MINUTES,
            )
            result_data = VideoRecoveryResultData(
                video_id=video_id,
                success=True,
                fields_recovered=[],
                failure_reason=None,
                duration_seconds=0.0,
            )
            return VideoRecoveryResponse(data=result_data)

    # Get recovery dependencies
    cdx_client, page_parser, rate_limiter = get_recovery_deps()

    # Call the recovery orchestrator
    from chronovista.services.recovery.orchestrator import recover_video

    try:
        recovery_result = await recover_video(
            session=session,
            video_id=video_id,
            cdx_client=cdx_client,
            page_parser=page_parser,
            rate_limiter=rate_limiter,
            from_year=start_year,
            to_year=end_year,
        )
    except CDXError as exc:
        logger.warning(
            "CDX API error during recovery of video %s: %s",
            video_id,
            exc.message,
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": f"Wayback Machine CDX API unavailable: {exc.message}",
            },
            headers={"Retry-After": "60"},
        )

    # Wrap result in response envelope
    result_data = VideoRecoveryResultData(
        video_id=recovery_result.video_id,
        success=recovery_result.success,
        snapshot_used=recovery_result.snapshot_used,
        fields_recovered=recovery_result.fields_recovered,
        fields_skipped=recovery_result.fields_skipped,
        snapshots_available=recovery_result.snapshots_available,
        snapshots_tried=recovery_result.snapshots_tried,
        failure_reason=recovery_result.failure_reason,
        duration_seconds=recovery_result.duration_seconds,
        channel_recovery_candidates=recovery_result.channel_recovery_candidates,
        channel_recovered=recovery_result.channel_recovered,
        channel_fields_recovered=recovery_result.channel_fields_recovered,
        channel_fields_skipped=recovery_result.channel_fields_skipped,
        channel_failure_reason=recovery_result.channel_failure_reason,
    )

    return VideoRecoveryResponse(data=result_data)
