"""Channel API endpoints.

This module provides REST API endpoints for channel operations:
- GET /channels - List channels with pagination and filtering
- GET /channels/{channel_id} - Get channel details by ID
- GET /channels/{channel_id}/entities - Rank a channel's entities by distinctiveness
- GET /channels/{channel_id}/videos - Get videos belonging to a channel
- POST /channels/{channel_id}/recover - Recover metadata for unavailable channel

All endpoints require authentication via the require_auth dependency.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Body, Depends, Path, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_channel_repository,
    get_db,
    get_entity_mention_repository,
    get_named_entity_repository,
    get_recovery_deps,
    get_transcript_segment_repository,
    get_video_repository,
    require_auth,
)
from chronovista.api.routers.responses import (
    CONFLICT_RESPONSE,
    GET_ITEM_ERRORS,
    LIST_ERRORS,
    NOT_FOUND_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from chronovista.api.schemas.channel_ownership import (
    AddChannelOperatorRequest,
    ChannelOperatorItem,
    ChannelOperatorsResponse,
)
from chronovista.api.schemas.channels import (
    ChannelDetail,
    ChannelDetailResponse,
    ChannelListItem,
    ChannelListResponse,
    ChannelRecoveryResponse,
    ChannelRecoveryResultData,
)
from chronovista.api.schemas.entity_mentions import (
    ChannelEntitiesResponse,
    ChannelEntityRanking,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.sorting import SortOrder
from chronovista.api.schemas.topics import TopicSummary
from chronovista.api.schemas.videos import (
    TranscriptSummary,
    VideoListItem,
    VideoListResponse,
)
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import (
    VideoTranscript,
)
from chronovista.exceptions import (
    BadRequestError,
    CDXError,
    ConflictError,
    NotFoundError,
)
from chronovista.models.enums import AvailabilityStatus
from chronovista.repositories.channel_ownership_assertion_repository import (
    ChannelOwnershipAssertionRepository,
)
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_repository import VideoRepository

logger = logging.getLogger(__name__)


class ChannelSortField(str, Enum):
    """Valid fields for sorting channels."""

    VIDEO_COUNT = "video_count"
    NAME = "name"


class ChannelVideoSortField(str, Enum):
    """Valid fields for sorting videos within a channel."""

    UPLOAD_DATE = "upload_date"
    TITLE = "title"


# Mapping from ChannelVideoSortField enum to SQLAlchemy column references.
_CHANNEL_VIDEO_SORT_COLUMN_MAP = {
    ChannelVideoSortField.UPLOAD_DATE: VideoDB.upload_date,
    ChannelVideoSortField.TITLE: VideoDB.title,
}


# Recovery idempotency guard (T033)
# Skip Wayback Machine requests if entity was recovered within this window
RECOVERY_IDEMPOTENCY_MINUTES = 5

router = APIRouter(dependencies=[Depends(require_auth)])


def _build_transcript_summary(
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


@router.get("/channels", response_model=ChannelListResponse, responses=LIST_ERRORS)
async def list_channels(
    sort_by: ChannelSortField = Query(
        ChannelSortField.VIDEO_COUNT,
        description="Sort field (video_count or name)",
    ),
    sort_order: SortOrder = Query(
        SortOrder.DESC,
        description="Sort order (asc or desc)",
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    has_videos: bool | None = Query(
        default=None, description="Filter to channels with/without videos"
    ),
    is_subscribed: bool | None = Query(
        default=None,
        description="Filter by subscription status: true=subscribed only, false=not subscribed only, omitted=all",
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    channel_repo: ChannelRepository = Depends(get_channel_repository),
    db: AsyncSession = Depends(get_db),
) -> ChannelListResponse:
    """
    List all channels with pagination, sorting, and filtering.

    Returns a paginated list of channels with configurable sort order.
    Optionally filter to channels that have (or don't have) videos,
    or by subscription status.

    Parameters
    ----------
    sort_by : ChannelSortField
        Sort field: video_count or name (default: video_count).
    sort_order : SortOrder
        Sort direction: asc or desc (default: desc).
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Number of items to skip (default 0).
    has_videos : Optional[bool]
        If True, return only channels with videos.
        If False, return only channels without videos.
        If None, return all channels.
    is_subscribed : Optional[bool]
        If True, return only subscribed channels.
        If False, return only not-subscribed channels.
        If None, return all channels.
    include_unavailable : bool
        If True, include unavailable channels in results.
        If False (default), only return available channels.
    db : AsyncSession
        Database session from dependency.

    Returns
    -------
    ChannelListResponse
        Paginated list of channels with metadata.
    """
    channels, total = await channel_repo.list_filtered(
        db,
        include_unavailable=include_unavailable,
        has_videos=has_videos,
        is_subscribed=is_subscribed,
        order_by_name=(sort_by == ChannelSortField.NAME),
        descending=(sort_order == SortOrder.DESC),
        skip=offset,
        limit=limit,
    )

    # Transform to response items
    items: list[ChannelListItem] = []
    for channel in channels:
        items.append(
            ChannelListItem(
                channel_id=channel.channel_id,
                title=channel.title,
                description=channel.description,
                subscriber_count=channel.subscriber_count,
                video_count=channel.video_count,
                thumbnail_url=channel.thumbnail_url,
                custom_url=None,  # Not yet persisted in DB
                availability_status=channel.availability_status,
                is_subscribed=channel.is_subscribed,
            )
        )

    return ChannelListResponse(
        data=items,
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


@router.get(
    "/channels/{channel_id}",
    response_model=ChannelDetailResponse,
    responses=GET_ITEM_ERRORS,
)
async def get_channel(
    channel_id: str = Path(
        ...,
        min_length=24,
        max_length=24,
        description="YouTube channel ID (24 characters)",
    ),
    channel_repo: ChannelRepository = Depends(get_channel_repository),
    db: AsyncSession = Depends(get_db),
) -> ChannelDetailResponse:
    """
    Get channel details by ID.

    Returns full channel metadata including subscription status and timestamps.

    Parameters
    ----------
    channel_id : str
        YouTube channel ID (exactly 24 characters).
    db : AsyncSession
        Database session from dependency.

    Returns
    -------
    ChannelDetailResponse
        Full channel details.

    Raises
    ------
    NotFoundError
        If channel with given ID does not exist.
    """
    channel = await channel_repo.get_by_channel_id(db, channel_id)

    if not channel:
        raise NotFoundError(
            resource_type="Channel",
            identifier=channel_id,
            hint="Verify the channel ID or run a sync.",
        )

    # Build response
    detail = ChannelDetail(
        channel_id=channel.channel_id,
        title=channel.title,
        description=channel.description,
        subscriber_count=channel.subscriber_count,
        video_count=channel.video_count,
        thumbnail_url=channel.thumbnail_url,
        custom_url=None,  # Not yet persisted in DB
        default_language=channel.default_language,
        country=channel.country,
        is_subscribed=channel.is_subscribed,
        availability_status=channel.availability_status,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
        recovered_at=channel.recovered_at,
        recovery_source=channel.recovery_source,
    )

    return ChannelDetailResponse(data=detail)


@router.get(
    "/channels/{channel_id}/entities",
    response_model=ChannelEntitiesResponse,
    responses=GET_ITEM_ERRORS,
)
async def get_channel_entities(
    channel_id: str = Path(
        ...,
        min_length=24,
        max_length=24,
        description="YouTube channel ID (24 characters)",
    ),
    channel_repo: ChannelRepository = Depends(get_channel_repository),
    entity_mention_repo: EntityMentionRepository = Depends(
        get_entity_mention_repository
    ),
    db: AsyncSession = Depends(get_db),
) -> ChannelEntitiesResponse:
    """
    Get the named entities appearing on a channel's videos, ranked by distinctiveness.

    Returns the entities associated with the channel's videos (Feature 070 /
    #171), ordered by ``channel_video_count / corpus_video_count`` — the
    share-ranked group first, then the "also appears" group. "Associated" is the
    Feature 066 definition (mentions plus tag associations), the same one the
    entity's counts use elsewhere, so this panel and the pinned
    ``/videos?channel_id=&entity_id=`` filter agree by construction
    (FR-004/FR-007).

    Parameters
    ----------
    channel_id : str
        YouTube channel ID (exactly 24 characters).
    db : AsyncSession
        Database session from dependency.

    Returns
    -------
    ChannelEntitiesResponse
        The full ranked entity list. ``items`` is empty when the channel exists
        but has no associated entities (FR-012).

    Raises
    ------
    NotFoundError
        If the channel does not exist (FR-016).
    """
    # Distinguish an unknown channel (404) from a known channel with no entities
    # (200 empty): the ranking method returns [] for both, so verify existence
    # first — mirrors get_channel's own existence check.
    if not await channel_repo.exists_by_channel_id(db, channel_id):
        raise NotFoundError(
            resource_type="Channel",
            identifier=channel_id,
            hint="Verify the channel ID or run a sync.",
        )

    rows = await entity_mention_repo.get_channel_entity_rankings(db, channel_id)
    items = [
        ChannelEntityRanking(
            entity_id=str(row.entity_id),
            display_name=row.display_name,
            entity_type=row.entity_type,
            channel_video_count=row.channel_video_count,
            corpus_video_count=row.corpus_video_count,
            share=row.share,
            is_ranked=row.is_ranked,
        )
        for row in rows
    ]
    return ChannelEntitiesResponse(
        channel_id=channel_id,
        total_entities=len(items),
        items=items,
    )


@router.get(
    "/channels/{channel_id}/operators",
    response_model=ChannelOperatorsResponse,
    responses=GET_ITEM_ERRORS,
)
async def get_channel_operators(
    channel_id: str = Path(
        ...,
        min_length=24,
        max_length=24,
        description="YouTube channel ID (24 characters)",
    ),
    channel_repo: ChannelRepository = Depends(get_channel_repository),
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    db: AsyncSession = Depends(get_db),
) -> ChannelOperatorsResponse:
    """Get the entities that operate this channel (ownership promotion, read-path).

    Surfaces the imported "entity operates channel" relation — the Wikidata
    ``youtube_channel_id`` identifier (P2397) read from ``named_entities.properties``
    with no schema change (ADR-010 promote-on-query). Returns **active** entities of
    **any** type (person, organization, ...) whose stored channel ids include this
    channel: ownership is not person-scoped (a channel *principal*, who appears in the
    videos, is a separate, later relation).

    Parameters
    ----------
    channel_id : str
        YouTube channel ID (exactly 24 characters).
    db : AsyncSession
        Database session from dependency.

    Returns
    -------
    ChannelOperatorsResponse
        The operating entities. ``items`` is empty when the channel exists but has no
        known operator.

    Raises
    ------
    NotFoundError
        If the channel does not exist.
    """
    # Distinguish an unknown channel (404) from a known channel with no operator
    # (200 empty) — mirror get_channel_entities' existence check first.
    if not await channel_repo.exists_by_channel_id(db, channel_id):
        raise NotFoundError(
            resource_type="Channel",
            identifier=channel_id,
            hint="Verify the channel ID or run a sync.",
        )

    operators = await entity_repo.operators_of_channel(db, channel_id)
    items = [
        ChannelOperatorItem(
            entity_id=operator.entity_id,
            entity_type=operator.entity_type,
            canonical_name=operator.canonical_name,
            provenance=operator.provenance,
        )
        for operator in operators
    ]
    return ChannelOperatorsResponse(
        channel_id=channel_id,
        total_entities=len(items),
        items=items,
    )


@router.post(
    "/channels/{channel_id}/operators",
    status_code=201,
    response_model=ChannelOperatorItem,
    responses={
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
    summary="Assign by hand an entity as an operator of this channel",
)
async def add_channel_operator(
    channel_id: str = Path(
        ...,
        min_length=24,
        max_length=24,
        description="YouTube channel ID (24 characters)",
    ),
    body: AddChannelOperatorRequest = Body(...),
    channel_repo: ChannelRepository = Depends(get_channel_repository),
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    db: AsyncSession = Depends(get_db),
) -> ChannelOperatorItem:
    """Assert a user-authored "entity operates channel" link from the channel side (Feature 109).

    The mirror of the entity-side add, over the same store. The **channel side is the
    in-library surface**: the channel must exist (a 404 otherwise), matching this endpoint's
    GET sibling — so a link created here is always readable back through
    ``GET /channels/{id}/operators``. Ownership of an *external* channel is asserted from the
    entity side instead (``POST /entities/{id}/channels``), which intentionally accepts
    not-in-library channels. The entity MUST already exist — this endpoint NEVER creates
    entities (FR-020). Redundancy (already recorded via Wikidata, or already asserted) is a
    409, not a duplicate.

    Raises
    ------
    NotFoundError
        If the channel is not in the library, or the entity does not exist (404).
    ConflictError
        If the entity is already an operator via Wikidata or already asserted (409).
    """
    if not await channel_repo.exists_by_channel_id(db, channel_id):
        raise NotFoundError(
            resource_type="Channel",
            identifier=channel_id,
            hint="Verify the channel ID or run a sync.",
        )
    entity = await entity_repo.get(db, body.entity_id)
    if entity is None:
        raise NotFoundError(resource_type="Entity", identifier=str(body.entity_id))

    # Redundancy via the union (which distinguishes imported from manual).
    for op in await entity_repo.operators_of_channel(db, channel_id):
        if op.entity_id == body.entity_id:
            if op.provenance == "wikidata":
                raise ConflictError(
                    message="This entity is already recorded as operating the channel "
                    "from Wikidata; nothing to add.",
                    details={
                        "channel_id": channel_id,
                        "entity_id": str(body.entity_id),
                    },
                )
            raise ConflictError(
                message="This entity is already added as an operator of the channel.",
                details={"channel_id": channel_id, "entity_id": str(body.entity_id)},
            )

    await ChannelOwnershipAssertionRepository().add(
        db, entity_id=body.entity_id, channel_id=channel_id, note=body.note
    )
    await db.commit()
    return ChannelOperatorItem(
        entity_id=entity.id,
        entity_type=entity.entity_type,
        canonical_name=entity.canonical_name,
        provenance="manual",
    )


@router.delete(
    "/channels/{channel_id}/operators/{entity_id}",
    status_code=204,
    response_class=Response,
    responses={**NOT_FOUND_RESPONSE},
    summary="Remove a user-asserted operator from a channel",
)
async def remove_channel_operator(
    channel_id: str = Path(
        ...,
        min_length=24,
        max_length=24,
        description="YouTube channel ID (24 characters)",
    ),
    entity_id: str = Path(..., description="Named entity UUID"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Remove a user-asserted ownership link from the channel side (mirror of the entity-side
    delete). Manual links only; an imported Wikidata link has no row here and is not removable
    (404), by design (FR-015).
    """
    try:
        parsed_entity_id = uuid.UUID(entity_id)
    except ValueError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc
    removed = await ChannelOwnershipAssertionRepository().delete(
        db, parsed_entity_id, channel_id
    )
    if not removed:
        raise NotFoundError(
            resource_type="ChannelOwnershipAssertion",
            identifier=f"{channel_id}/{entity_id}",
        )
    await db.commit()
    return Response(status_code=204)


@router.get(
    "/channels/{channel_id}/videos",
    response_model=VideoListResponse,
    responses=GET_ITEM_ERRORS,
)
async def get_channel_videos(
    channel_id: str = Path(
        ...,
        min_length=24,
        max_length=24,
        description="YouTube channel ID (24 characters)",
    ),
    sort_by: ChannelVideoSortField = Query(
        ChannelVideoSortField.UPLOAD_DATE,
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
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    db: AsyncSession = Depends(get_db),
    channel_repo: ChannelRepository = Depends(get_channel_repository),
    video_repo: VideoRepository = Depends(get_video_repository),
    segment_repo: TranscriptSegmentRepository = Depends(
        get_transcript_segment_repository
    ),
) -> VideoListResponse:
    """
    Get videos belonging to a channel.

    Returns a paginated list of videos for the specified channel,
    with configurable sort order and liked filter.

    Parameters
    ----------
    channel_id : str
        YouTube channel ID (exactly 24 characters).
    sort_by : ChannelVideoSortField
        Sort field: upload_date or title (default: upload_date).
    sort_order : SortOrder
        Sort direction: asc or desc (default: desc).
    liked_only : bool
        If True, only return videos the user has liked (default: False).
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Number of items to skip (default 0).
    include_unavailable : bool
        If True, include unavailable videos in results (default: False).
    db : AsyncSession
        Database session from dependency.

    Returns
    -------
    VideoListResponse
        Paginated list of videos with metadata.

    Raises
    ------
    NotFoundError
        If channel with given ID does not exist.
    """
    # Verify the channel exists
    if not await channel_repo.exists_by_channel_id(db, channel_id):
        raise NotFoundError(
            resource_type="Channel",
            identifier=channel_id,
            hint="Verify the channel ID or run a sync.",
        )

    # Resolve the sort expression (Feature 027); the repository appends a
    # deterministic video_id tiebreak (FR-029).
    sort_column = _CHANNEL_VIDEO_SORT_COLUMN_MAP[sort_by]
    order_clause = (
        sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
    )

    # Videos in this channel via the shared filtered listing (#256).
    total, videos = await video_repo.list_videos_filtered(
        db,
        channel_id=channel_id,
        liked_only=liked_only,
        include_unavailable=include_unavailable,
        order_clause=order_clause,
        offset=offset,
        limit=limit,
    )

    # Which videos on this page have corrected segments (Feature 035)
    videos_with_corrections = await segment_repo.get_video_ids_with_corrections(
        db, [v.video_id for v in videos]
    )

    # Transform to response items
    items: list[VideoListItem] = []
    for video in videos:
        transcript_summary = _build_transcript_summary(
            list(video.transcripts),
            has_corrections=video.video_id in videos_with_corrections,
        )
        channel_title = video.channel.title if video.channel else None

        # Build classification fields
        category_name = video.category.name if video.category else None
        tags = [tag.tag for tag in video.tags] if video.tags else []
        topics = (
            [
                TopicSummary(
                    topic_id=vt.topic_category.topic_id,
                    name=vt.topic_category.category_name,
                    parent_path=None,  # TODO: Compute hierarchy path if needed
                )
                for vt in video.video_topics
            ]
            if video.video_topics
            else []
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
                category_id=video.category_id,
                category_name=category_name,
                tags=tags,
                topics=topics,
                availability_status=video.availability_status,
            )
        )

    return VideoListResponse(
        data=items,
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


@router.post(
    "/channels/{channel_id}/recover",
    response_model=ChannelRecoveryResponse,
    responses={
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
        503: {"description": "Wayback Machine CDX API unavailable"},
    },
)
async def recover_channel_endpoint(
    channel_id: str = Path(
        ...,
        min_length=24,
        max_length=24,
        description="YouTube channel ID (24 characters)",
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
    channel_repo: ChannelRepository = Depends(get_channel_repository),
    session: AsyncSession = Depends(get_db),
) -> ChannelRecoveryResponse | JSONResponse:
    """
    Recover metadata for an unavailable channel using the Wayback Machine.

    Queries the Internet Archive's CDX API for archived snapshots of the
    channel's YouTube page, extracts metadata from the best available snapshot,
    and updates the database with recovered fields.

    Parameters
    ----------
    channel_id : str
        YouTube channel ID (24 characters, starts with UC).
    start_year : Optional[int]
        Only search snapshots from this year onward (2005-2026).
    end_year : Optional[int]
        Only search snapshots up to this year (2005-2026).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    ChannelRecoveryResponse
        Recovery result with fields recovered, snapshot used, and duration.

    Raises
    ------
    NotFoundError
        If channel not found (404).
    ConflictError
        If channel is currently available (409).
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

    # Verify channel exists
    channel = await channel_repo.get_by_channel_id(session, channel_id)

    if not channel:
        raise NotFoundError(
            resource_type="Channel",
            identifier=channel_id,
            hint="Verify the channel ID or run a sync.",
        )

    # Verify channel is unavailable (not available)
    if channel.availability_status == AvailabilityStatus.AVAILABLE.value:
        raise ConflictError(
            message="Cannot recover an available channel",
            details={
                "channel_id": channel_id,
                "availability_status": channel.availability_status,
                "hint": "Recovery is only supported for unavailable channels",
            },
        )

    # T033: Idempotency guard — skip Wayback Machine if recently recovered
    if channel.recovered_at is not None:
        now_utc = datetime.now(UTC)
        # Ensure recovered_at is timezone-aware for comparison
        recovered_at = channel.recovered_at
        if recovered_at.tzinfo is None:
            recovered_at = recovered_at.replace(tzinfo=UTC)
        elapsed = now_utc - recovered_at
        if elapsed < timedelta(minutes=RECOVERY_IDEMPOTENCY_MINUTES):
            logger.info(
                "Channel %s was already recovered %s ago (< %d min); "
                "returning cached result",
                channel_id,
                elapsed,
                RECOVERY_IDEMPOTENCY_MINUTES,
            )
            result_data = ChannelRecoveryResultData(
                channel_id=channel_id,
                success=True,
                fields_recovered=[],
                failure_reason=None,
                duration_seconds=0.0,
            )
            return ChannelRecoveryResponse(data=result_data)

    # Get recovery dependencies
    cdx_client, page_parser, rate_limiter = get_recovery_deps()

    # Call the recovery orchestrator
    from chronovista.services.recovery.orchestrator import recover_channel

    try:
        recovery_result = await recover_channel(
            session=session,
            channel_id=channel_id,
            cdx_client=cdx_client,
            page_parser=page_parser,
            rate_limiter=rate_limiter,
            from_year=start_year,
            to_year=end_year,
        )
    except CDXError as exc:
        logger.warning(
            "CDX API error during recovery of channel %s: %s",
            channel_id,
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
    result_data = ChannelRecoveryResultData(
        channel_id=recovery_result.channel_id,
        success=recovery_result.success,
        snapshot_used=recovery_result.snapshot_used,
        fields_recovered=recovery_result.fields_recovered,
        fields_skipped=recovery_result.fields_skipped,
        snapshots_available=recovery_result.snapshots_available,
        snapshots_tried=recovery_result.snapshots_tried,
        failure_reason=recovery_result.failure_reason,
        duration_seconds=recovery_result.duration_seconds,
    )

    return ChannelRecoveryResponse(data=result_data)
