"""Video list and detail endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import ColumnElement, ScalarSelect, Subquery
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_canonical_tag_repository,
    get_db,
    get_entity_mention_repository,
    get_named_entity_repository,
    get_playlist_membership_repository,
    get_recovery_deps,
    get_topic_category_repository,
    get_transcript_segment_repository,
    get_video_category_repository,
    get_video_repository,
    get_video_tag_repository,
    require_auth,
)
from chronovista.api.query_protection import (
    QUERY_TIMEOUT_SECONDS,
    check_rate_limit,
    get_client_id,
)
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
    VideoEntityMatch,
    VideoListItem,
    VideoListResponse,
    VideoListResponseWithWarnings,
    VideoPlaylistMembership,
    VideoPlaylistsResponse,
    VideoRecoveryResponse,
    VideoRecoveryResultData,
)
from chronovista.db.models import (
    TopicCategory,
    VideoTranscript,
)
from chronovista.db.models import Video as VideoDB
from chronovista.exceptions import (
    BadRequestError,
    CDXError,
    ConflictError,
    NotFoundError,
)
from chronovista.models.enums import AvailabilityStatus, EvidenceScope
from chronovista.repositories.canonical_tag_repository import (
    CanonicalTagRepository,
)
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.playlist_membership_repository import (
    PlaylistMembershipRepository,
)
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_category_repository import VideoCategoryRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_tag_repository import VideoTagRepository

logger = logging.getLogger(__name__)


class VideoSortField(str, Enum):
    """Sort fields for video list endpoint.

    Values correspond to database column names used in ORDER BY clauses.
    The frontend display label "Date Added" maps to ``upload_date`` (FR-017).
    """

    UPLOAD_DATE = "upload_date"
    TITLE = "title"
    RELEVANCE = "relevance"  # Feature 062: ordering comes from the entity
    # qualification subquery, not a VideoDB column, so it is deliberately
    # absent from _VIDEO_SORT_COLUMN_MAP below.


# Mapping from VideoSortField enum to actual SQLAlchemy column references.
# Used by the list_videos endpoint to build ORDER BY clauses.
_VIDEO_SORT_COLUMN_MAP = {
    VideoSortField.UPLOAD_DATE: VideoDB.upload_date,
    VideoSortField.TITLE: VideoDB.title,
}

# Filter limits per FR-034
MAX_TAGS = 10
MAX_CANONICAL_TAGS = 10
MAX_TOPICS = 10
MAX_TOTAL_FILTERS = 15
# Feature 062: applied SEPARATELY to the required and excluded sets (FR-002a),
# while both sets also count toward MAX_TOTAL_FILTERS above (FR-002d).
MAX_ENTITIES = 10

# Rate limiting configuration (T097)
# In-memory rate limiter - requests per minute per client
RATE_LIMIT_FILTER_QUERIES = 100  # requests per minute

# Storage for rate limit tracking
_filter_request_counts: dict[str, list[float]] = defaultdict(list)


# Recovery idempotency guard (T033)
# Skip Wayback Machine requests if entity was recovered within this window
RECOVERY_IDEMPOTENCY_MINUTES = 5


router = APIRouter(dependencies=[Depends(require_auth)])


def build_transcript_summary(
    transcripts: list[VideoTranscript],
    has_corrections: bool = False,
) -> TranscriptSummary:
    """
    Build transcript summary from transcript list.

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


def _validate_filter_limits(
    tags: list[str],
    canonical_tags: list[str],
    topic_ids: list[str],
    category: str | None,
    entity_ids: list[UUID] | None = None,
    excluded_entity_ids: list[UUID] | None = None,
) -> None:
    """
    Validate filter limits per FR-034.

    Parameters
    ----------
    tags : List[str]
        List of tag filters.
    canonical_tags : List[str]
        List of canonical tag filters.
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

    # Check canonical tag limit
    if len(canonical_tags) > MAX_CANONICAL_TAGS:
        raise BadRequestError(
            message=(
                f"Maximum {MAX_CANONICAL_TAGS} canonical tags allowed, "
                f"received {len(canonical_tags)}. "
                f"Remove {len(canonical_tags) - MAX_CANONICAL_TAGS} canonical tags to continue."
            ),
            details={
                "field": "canonical_tag",
                "max_allowed": MAX_CANONICAL_TAGS,
                "received": len(canonical_tags),
                "excess": len(canonical_tags) - MAX_CANONICAL_TAGS,
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

    # Entity ceilings (Feature 062). Applied to each set SEPARATELY rather than
    # to their combined size (FR-002a): requiring five entities and excluding
    # five is two five-item decisions, not one ten-item one.
    required = entity_ids or []
    excluded = excluded_entity_ids or []
    for field, values in (("entity_id", required), ("exclude_entity_id", excluded)):
        if len(values) > MAX_ENTITIES:
            raise BadRequestError(
                message=(
                    f"Maximum {MAX_ENTITIES} entities allowed per set, "
                    f"received {len(values)}. "
                    f"Remove {len(values) - MAX_ENTITIES} to continue."
                ),
                details={
                    "field": field,
                    "max_allowed": MAX_ENTITIES,
                    "received": len(values),
                    "excess": len(values) - MAX_ENTITIES,
                },
            )

    # Check total filter count. Entities count toward the global cap on the
    # same terms as every other filter type (FR-002d), so the per-set ceiling
    # above is a sub-cap: with other filters active, neither set reaches 10.
    total_filters = (
        len(tags)
        + len(canonical_tags)
        + len(topic_ids)
        + (1 if category else 0)
        + len(required)
        + len(excluded)
    )
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
) -> str | None:
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

    path_parts: list[str] = []
    current_id: str | None = topic.parent_topic_id

    # Walk up the parent chain
    while current_id is not None and current_id in topic_cache:
        parent = topic_cache[current_id]
        path_parts.insert(0, parent.category_name)
        current_id = parent.parent_topic_id

    return " > ".join(path_parts) if path_parts else None


async def _validate_tags(
    session: AsyncSession,
    tags: list[str],
    tag_repo: VideoTagRepository,
) -> tuple[list[str], list[FilterWarning]]:
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

    existing_tags = await tag_repo.get_existing_tags(session, tags)

    valid_tags: list[str] = []
    warnings: list[FilterWarning] = []

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
    category: str | None,
    category_repo: VideoCategoryRepository,
) -> tuple[str | None, list[FilterWarning]]:
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

    exists = await category_repo.exists(session, category)

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
    topic_ids: list[str],
    topic_repo: TopicCategoryRepository,
) -> tuple[list[str], list[FilterWarning]]:
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

    existing_topics = await topic_repo.get_existing_topic_ids(session, topic_ids)

    valid_topics: list[str] = []
    warnings: list[FilterWarning] = []

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
    response_model=VideoListResponse | VideoListResponseWithWarnings,
    responses={
        **LIST_ERRORS,
        429: {"description": "Rate limit exceeded"},
        504: {"description": "Query timeout exceeded"},
    },
)
async def list_videos(
    request: Request,
    session: AsyncSession = Depends(get_db),
    channel_id: str | None = Query(
        None,
        min_length=24,
        max_length=24,
        description="Filter by channel ID",
    ),
    has_transcript: bool | None = Query(
        None,
        description="Filter by transcript availability",
    ),
    uploaded_after: datetime | None = Query(
        None,
        description="Filter by upload date (ISO 8601)",
    ),
    uploaded_before: datetime | None = Query(
        None,
        description="Filter by upload date (ISO 8601)",
    ),
    # Classification filters (Feature 020)
    tag: list[str] = Query(
        default=[],
        description="Filter by tag(s) - OR logic between multiple tags. Max 10.",
    ),
    category: str | None = Query(
        None,
        description="Filter by YouTube category ID (single value)",
    ),
    canonical_tag: list[str] = Query(
        default=[],
        description="Filter by canonical tag(s) - OR logic between multiple. Max 10.",
    ),
    topic_id: list[str] = Query(
        default=[],
        description="Filter by topic ID(s) - OR logic between multiple topics. Max 10.",
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    sort_by: VideoSortField | None = Query(
        None,
        description=(
            "Sort field (upload_date, title, or relevance). Defaults to "
            "upload_date. Left unset here rather than defaulted at the "
            "parameter layer so the endpoint can distinguish 'caller sent "
            "nothing' from 'caller explicitly chose upload_date' (FR-009e)."
        ),
    ),
    sort_order: SortOrder = Query(
        SortOrder.DESC,
        description="Sort order (asc or desc)",
    ),
    saved_unwatched: bool = Query(
        False,
        description=(
            "Filter to videos saved in at least one curated playlist and never "
            "watched (the dashboard's Saved & Forgotten set)"
        ),
    ),
    liked_only: bool = Query(
        False,
        description="Filter to only liked videos",
    ),
    # Entity intersection (Feature 062). Repeated keys, matching the binding
    # already used by tag / canonical_tag / topic_id (research R4).
    entity_id: list[UUID] = Query(
        default=[],
        description=(
            "Required entity UUID(s) - AND logic. A video qualifies only if "
            "EVERY listed entity has at least one qualifying mention. Max 10."
        ),
    ),
    exclude_entity_id: list[UUID] = Query(
        default=[],
        description=(
            "Excluded entity UUID(s). A video mentioning ANY of these is "
            "removed regardless of required matches. Max 10."
        ),
    ),
    min_evidence: EvidenceScope = Query(
        EvidenceScope.ANY,
        description=(
            "Which mentions qualify. 'any' counts transcript, title, and "
            "description; 'transcript' restricts to transcript-sourced "
            "mentions, which inherently retains every human-added mention. "
            "Accepted and ignored when no entity filter is present, since "
            "there is nothing being qualified — unlike sort_by=relevance, "
            "which rejects under the same condition because it would have to "
            "invent an ordering it cannot compute."
        ),
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    video_repo: VideoRepository = Depends(get_video_repository),
    tag_repo: VideoTagRepository = Depends(get_video_tag_repository),
    category_repo: VideoCategoryRepository = Depends(get_video_category_repository),
    topic_repo: TopicCategoryRepository = Depends(get_topic_category_repository),
    segment_repo: TranscriptSegmentRepository = Depends(
        get_transcript_segment_repository
    ),
    named_entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
    canonical_tag_repo: CanonicalTagRepository = Depends(get_canonical_tag_repository),
) -> VideoListResponse | VideoListResponseWithWarnings | JSONResponse:
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
    client_id = get_client_id(request)
    is_allowed, retry_after = check_rate_limit(
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

    # FR-009e: apply the sort default here rather than at the parameter layer,
    # so "unset" stays distinguishable from an explicit choice of the same
    # value. Feature 062 needs that distinction to auto-select relevance only
    # when the caller expressed no preference (FR-009b).
    # FR-009b: relevance is auto-selected when an entity filter is active AND
    # the caller expressed no preference. FR-009c: an explicit choice is never
    # overridden. The unset state (FR-009e) is what makes the distinction
    # possible -- a default applied at the parameter layer would make
    # "sent nothing" indistinguishable from "explicitly chose upload_date".
    if sort_by is not None:
        effective_sort_by = sort_by
    elif entity_id:
        effective_sort_by = VideoSortField.RELEVANCE
    else:
        effective_sort_by = VideoSortField.UPLOAD_DATE
    if effective_sort_by is VideoSortField.RELEVANCE and not entity_id:
        # Relevance ranks by mention volume across the required entities, so it
        # has no meaning without a required set (FR-009d).
        raise BadRequestError(
            message=(
                "sort_by=relevance requires at least one entity filter. "
                "Add an entity to sort by relevance, or choose another sort."
            ),
            details={"field": "sort_by", "invalid_value": "relevance"},
        )

    # Deduplicate the entity sets before anything counts or queries them.
    # Requesting an entity twice is idempotent and must not raise the
    # qualification bar or consume two slots against the ceiling.
    required_entity_ids = list(dict.fromkeys(entity_id))
    excluded_entity_ids = list(dict.fromkeys(exclude_entity_id))

    # Validate filter limits (FR-034, and FR-002a/FR-002d for entities)
    _validate_filter_limits(
        tag,
        canonical_tag,
        topic_id,
        category,
        required_entity_ids,
        excluded_entity_ids,
    )

    # The two entity sets must be disjoint. Rejected with the offending entity
    # named, never a silently empty result (FR-016).
    overlap = set(required_entity_ids) & set(excluded_entity_ids)
    if overlap:
        raise BadRequestError(
            message=(
                "An entity cannot be both required and excluded: "
                f"{', '.join(str(e) for e in sorted(overlap, key=str))}."
            ),
            details={
                "field": "entity_id",
                "conflicting_entity_ids": [str(e) for e in sorted(overlap, key=str)],
            },
        )

    # Unknown entity ids are rejected, not ignored-with-a-warning like this
    # endpoint's other multi-value filters. The divergence is deliberate
    # (FR-016b): the entity filter is conjunctive, so silently dropping a
    # required entity BROADENS the result -- a three-entity intersection
    # quietly answered as a two-entity one returns more videos, presenting a
    # wrong answer confidently. Dropping a disjunct narrows visibly instead.
    all_entity_ids = required_entity_ids + excluded_entity_ids
    if all_entity_ids:
        known = await named_entity_repo.get_existing_ids(session, all_entity_ids)
        unknown = [e for e in all_entity_ids if e not in known]
        if unknown:
            raise BadRequestError(
                message=(
                    "Unknown entity id(s): " f"{', '.join(str(e) for e in unknown)}."
                ),
                details={
                    "field": "entity_id",
                    "unknown_entity_ids": [str(e) for e in unknown],
                },
            )

    # Validate filter values and collect warnings (FR-042 through FR-045)
    all_warnings: list[FilterWarning] = []

    # Validate tags
    valid_tags, tag_warnings = await _validate_tags(session, tag, tag_repo)
    all_warnings.extend(tag_warnings)

    # Validate category
    valid_category, category_warnings = await _validate_category(
        session, category, category_repo
    )
    all_warnings.extend(category_warnings)

    # Validate topics
    valid_topics, topic_warnings = await _validate_topics(session, topic_id, topic_repo)
    all_warnings.extend(topic_warnings)

    # Canonical tag filter: build subqueries (OR logic)
    canonical_tag_subqueries: list[Any] | None = None
    if canonical_tag:
        canonical_tag_subqueries = (
            await canonical_tag_repo.build_canonical_tag_video_subqueries(
                session, canonical_tag
            )
        )
        if not canonical_tag_subqueries:
            # All requested canonical tags were unrecognized — short-circuit
            logger.warning(
                "Canonical tag filter short-circuit: no valid tags found among: %s",
                canonical_tag,
            )
            pagination = PaginationMeta(
                total=0,
                limit=limit,
                offset=offset,
                has_more=False,
            )
            return VideoListResponse(data=[], pagination=pagination)

    # Entity intersection (Feature 062). The qualification (required-AND) and
    # exclusion (excluded-OR) subqueries are built by EntityMentionRepository
    # and passed into the video query builder, which applies them before
    # deriving the count -- so the total inherits them like every other filter
    # (FR-033, research R9). A parallel query or a hand-rolled count would give
    # correct rows with a wrong total, which no row-inspecting test detects.
    qualification: Subquery | None = None
    if required_entity_ids:
        qualification = await mention_repo.build_entity_qualification_subquery(
            session, required_entity_ids, min_evidence
        )
    excluded_videos: ScalarSelect[str] | None = None
    if excluded_entity_ids:
        excluded_videos = await mention_repo.build_entity_exclusion_subquery(
            session, excluded_entity_ids, min_evidence
        )

    # Resolve the primary sort expression (Feature 027); the repository appends
    # a deterministic video_id tiebreak (FR-029). Relevance orders by the
    # qualification subquery's mention total, not a VideoDB column, which is why
    # RELEVANCE is deliberately absent from _VIDEO_SORT_COLUMN_MAP. The guard
    # earlier guarantees `qualification` exists whenever relevance is active.
    ascending = sort_order == SortOrder.ASC
    if effective_sort_by is VideoSortField.RELEVANCE:
        assert qualification is not None
        relevance_col = qualification.c.total_mentions
        order_clause: ColumnElement[Any] = (
            relevance_col.asc() if ascending else relevance_col.desc()
        )
    else:
        sort_col = _VIDEO_SORT_COLUMN_MAP[effective_sort_by]
        order_clause = sort_col.asc() if ascending else sort_col.desc()

    # T099: Execute queries with timeout (FR-036: 10s timeout)
    try:

        async def execute_queries() -> (
            tuple[int, list[VideoDB], dict[str, TopicCategory], set[str]]
        ):
            """Execute all database queries for video listing."""
            # The filter/count/sort/paginate all live in the repository so the
            # count always inherits the same filters as the returned page.
            total, videos = await video_repo.list_videos_filtered(
                session,
                include_unavailable=include_unavailable,
                channel_id=channel_id,
                uploaded_after=uploaded_after,
                uploaded_before=uploaded_before,
                has_transcript=has_transcript,
                valid_tags=valid_tags,
                valid_category=valid_category,
                valid_topics=valid_topics,
                canonical_tag_subqueries=canonical_tag_subqueries,
                liked_only=liked_only,
                saved_unwatched=saved_unwatched,
                qualification=qualification,
                excluded_videos=excluded_videos,
                order_clause=order_clause,
                offset=offset,
                limit=limit,
            )

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
                for tc in await topic_repo.get_by_topic_ids(session, all_topic_ids):
                    topic_cache[tc.topic_id] = tc

            # Which videos on this page have corrected segments (Feature 035)
            videos_with_corrections = await segment_repo.get_video_ids_with_corrections(
                session, [v.video_id for v in videos]
            )

            return total, videos, topic_cache, videos_with_corrections

        total, videos, topic_cache, videos_with_corrections = await asyncio.wait_for(
            execute_queries(),
            timeout=QUERY_TIMEOUT_SECONDS,
        )
    except TimeoutError:
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
    # Per-entity evidence for the RETURNED PAGE ONLY (research R1). This is the
    # single place transcript_segments is joined; doing it before pagination
    # instead returns byte-identical output at roughly 8x the cost, a
    # regression no value-based assertion can detect. Only timing can.
    page_entity_matches: dict[str, list[dict[str, Any]]] = {}
    if required_entity_ids:
        page_entity_matches = await mention_repo.get_page_entity_matches(
            session,
            video_ids=[v.video_id for v in videos],
            entity_ids=required_entity_ids,
            evidence_scope=min_evidence,
        )

    items: list[VideoListItem] = []
    for video in videos:
        transcript_summary = build_transcript_summary(
            list(video.transcripts),
            has_corrections=video.video_id in videos_with_corrections,
        )
        channel_title = video.channel.title if video.channel else None

        # Entity intersection fields (Feature 062). None when no entity filter
        # of either kind is active, so existing callers see an unchanged shape;
        # present-and-empty for an exclusion-only filter, which IS an active
        # filter (FR-015a).
        video_entity_matches: list[VideoEntityMatch] | None = None
        video_total_mentions: int | None = None
        if required_entity_ids or excluded_entity_ids:
            raw_matches = page_entity_matches.get(video.video_id, [])
            # Ordered by the caller's required-set sequence. Without this the
            # order is whatever the GROUP BY returned, so per-entity badges on
            # one video can reorder between requests and two pages of one
            # result set can present the same entities differently. The
            # co-occurrence query got a tiebreak for exactly this reason; this
            # path needs the same determinism.
            by_id = {m["entity_id"]: m for m in raw_matches}
            raw_matches = [by_id[eid] for eid in required_entity_ids if eid in by_id]
            video_entity_matches = [
                VideoEntityMatch(
                    entity_id=m["entity_id"],
                    entity_type=m["entity_type"],
                    canonical_name=m["canonical_name"],
                    mention_count=m["mention_count"],
                    first_timestamp=m["first_timestamp"],
                )
                for m in raw_matches
            ]
            video_total_mentions = sum(m.mention_count for m in video_entity_matches)

        # Extract tags
        video_tags = [t.tag for t in video.tags] if video.tags else []

        # Extract category info
        category_id_val = video.category_id
        category_name = video.category.name if video.category else None

        # Extract topics with parent paths
        topics_list: list[TopicSummary] = []
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
                entity_matches=video_entity_matches,
                total_mentions=video_total_mentions,
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
        "[videos] Filter query completed in %.0fms (tags=%d, canonical_tags=%d, category=%s, topics=%d)",
        query_elapsed_ms,
        len(valid_tags),
        len(canonical_tag),
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


@router.get(
    "/videos/{video_id}", response_model=VideoDetailResponse, responses=GET_ITEM_ERRORS
)
async def get_video(
    video_id: str = Path(
        ...,
        min_length=11,
        max_length=11,
        description="YouTube video ID (11 characters)",
        example="dQw4w9WgXcQ",
    ),
    session: AsyncSession = Depends(get_db),
    video_repo: VideoRepository = Depends(get_video_repository),
    segment_repo: TranscriptSegmentRepository = Depends(
        get_transcript_segment_repository
    ),
    topic_repo: TopicCategoryRepository = Depends(get_topic_category_repository),
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
    video = await video_repo.get_with_relations(session, video_id)

    if not video:
        raise NotFoundError(
            resource_type="Video",
            identifier=video_id,
            hint="Verify the video ID or run: chronovista sync videos",
        )

    # Check if any segments have corrections (Feature 035)
    has_corrections = await segment_repo.video_has_corrections(session, video_id)

    # Build response
    transcript_summary = build_transcript_summary(
        list(video.transcripts),
        has_corrections=has_corrections,
    )
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
            for tc in await topic_repo.get_by_topic_ids(session, all_topic_ids):
                topic_cache[tc.topic_id] = tc

    topics_list: list[TopicSummary] = []
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
    video_repo: VideoRepository = Depends(get_video_repository),
    membership_repo: PlaylistMembershipRepository = Depends(
        get_playlist_membership_repository
    ),
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
    if not await video_repo.exists_by_video_id(session, video_id):
        raise NotFoundError(
            resource_type="Video",
            identifier=video_id,
            hint="Verify the video ID or run: chronovista sync videos",
        )

    # Get all playlist memberships for this video
    memberships = await membership_repo.get_video_playlists(session, video_id)

    # Transform to response schema
    playlist_memberships: list[VideoPlaylistMembership] = []
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
    video_repo: VideoRepository = Depends(get_video_repository),
    segment_repo: TranscriptSegmentRepository = Depends(
        get_transcript_segment_repository
    ),
    topic_repo: TopicCategoryRepository = Depends(get_topic_category_repository),
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
    video = await video_repo.get_with_relations(session, video_id)

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
        if not (
            alternative_url.startswith("http://")
            or alternative_url.startswith("https://")
        ):
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

    # Check if any segments have corrections (Feature 035)
    has_corrections = await segment_repo.video_has_corrections(session, video_id)

    # Build response (reuse logic from get_video endpoint)
    transcript_summary = build_transcript_summary(
        list(video.transcripts),
        has_corrections=has_corrections,
    )
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
            for tc in await topic_repo.get_by_topic_ids(session, all_topic_ids):
                topic_cache[tc.topic_id] = tc

    topics_list: list[TopicSummary] = []
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
    start_year: int | None = Query(
        None,
        ge=2005,
        le=2026,
        description="Only search snapshots from this year onward (2005-2026)",
    ),
    end_year: int | None = Query(
        None,
        ge=2005,
        le=2026,
        description="Only search snapshots up to this year (2005-2026)",
    ),
    session: AsyncSession = Depends(get_db),
    video_repo: VideoRepository = Depends(get_video_repository),
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
    video = await video_repo.get_by_video_id(session, video_id)

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
        now_utc = datetime.now(UTC)
        # Ensure recovered_at is timezone-aware for comparison
        recovered_at = video.recovered_at
        if recovered_at.tzinfo is None:
            recovered_at = recovered_at.replace(tzinfo=UTC)
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
