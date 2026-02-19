"""Channel API endpoints.

This module provides REST API endpoints for channel operations:
- GET /channels - List channels with pagination and filtering
- GET /channels/{channel_id} - Get channel details by ID
- GET /channels/{channel_id}/videos - Get videos belonging to a channel
- POST /channels/{channel_id}/recover - Recover metadata for unavailable channel

All endpoints require authentication via the require_auth dependency.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
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
from chronovista.api.schemas.channels import (
    ChannelDetail,
    ChannelDetailResponse,
    ChannelListItem,
    ChannelListResponse,
    ChannelRecoveryResponse,
    ChannelRecoveryResultData,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.topics import TopicSummary
from chronovista.api.schemas.videos import (
    TranscriptSummary,
    VideoListItem,
    VideoListResponse,
)
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoCategory, VideoTag, VideoTopic, TopicCategory
from chronovista.db.models import VideoTranscript
from chronovista.exceptions import BadRequestError, CDXError, ConflictError, NotFoundError
from chronovista.models.enums import AvailabilityStatus

logger = logging.getLogger(__name__)

# Recovery idempotency guard (T033)
# Skip Wayback Machine requests if entity was recovered within this window
RECOVERY_IDEMPOTENCY_MINUTES = 5

router = APIRouter(dependencies=[Depends(require_auth)])


def _build_transcript_summary(transcripts: List[VideoTranscript]) -> TranscriptSummary:
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


@router.get("/channels", response_model=ChannelListResponse, responses=LIST_ERRORS)
async def list_channels(
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    has_videos: Optional[bool] = Query(
        default=None, description="Filter to channels with/without videos"
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    db: AsyncSession = Depends(get_db),
) -> ChannelListResponse:
    """
    List all channels with pagination.

    Returns a paginated list of channels, ordered by video count descending.
    Optionally filter to channels that have (or don't have) videos.

    Parameters
    ----------
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Number of items to skip (default 0).
    has_videos : Optional[bool]
        If True, return only channels with videos.
        If False, return only channels without videos.
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
    # Build base query
    query = select(ChannelDB)

    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        query = query.where(ChannelDB.availability_status == AvailabilityStatus.AVAILABLE)

    # Apply has_videos filter
    if has_videos is True:
        query = query.where(ChannelDB.video_count > 0)
    elif has_videos is False:
        query = query.where(
            (ChannelDB.video_count == 0) | (ChannelDB.video_count.is_(None))
        )

    # Count total before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering and pagination (video_count DESC per spec)
    query = (
        query.order_by(ChannelDB.video_count.desc().nulls_last())
        .offset(offset)
        .limit(limit)
    )

    # Execute query
    result = await db.execute(query)
    channels = result.scalars().all()

    # Transform to response items
    items: List[ChannelListItem] = []
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


@router.get("/channels/{channel_id}", response_model=ChannelDetailResponse, responses=GET_ITEM_ERRORS)
async def get_channel(
    channel_id: str = Path(
        ...,
        min_length=24,
        max_length=24,
        description="YouTube channel ID (24 characters)",
    ),
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
    # Query channel by ID
    result = await db.execute(
        select(ChannelDB).where(ChannelDB.channel_id == channel_id)
    )
    channel = result.scalar_one_or_none()

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


@router.get("/channels/{channel_id}/videos", response_model=VideoListResponse, responses=GET_ITEM_ERRORS)
async def get_channel_videos(
    channel_id: str = Path(
        ...,
        min_length=24,
        max_length=24,
        description="YouTube channel ID (24 characters)",
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    db: AsyncSession = Depends(get_db),
) -> VideoListResponse:
    """
    Get videos belonging to a channel.

    Returns a paginated list of videos for the specified channel,
    ordered by upload date descending.

    Parameters
    ----------
    channel_id : str
        YouTube channel ID (exactly 24 characters).
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Number of items to skip (default 0).
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
    # First verify the channel exists
    channel_result = await db.execute(
        select(ChannelDB.channel_id).where(ChannelDB.channel_id == channel_id)
    )
    if not channel_result.scalar_one_or_none():
        raise NotFoundError(
            resource_type="Channel",
            identifier=channel_id,
            hint="Verify the channel ID or run a sync.",
        )

    # Build video query with eager loading
    query = (
        select(VideoDB)
        .where(VideoDB.channel_id == channel_id)
        .options(selectinload(VideoDB.transcripts))
        .options(selectinload(VideoDB.channel))
        .options(selectinload(VideoDB.category))
        .options(selectinload(VideoDB.tags))
        .options(selectinload(VideoDB.video_topics).selectinload(VideoTopic.topic_category))
    )

    # Apply availability filter unless include_unavailable is True
    if not include_unavailable:
        query = query.where(VideoDB.availability_status == AvailabilityStatus.AVAILABLE)

    # Count total before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    query = query.order_by(VideoDB.upload_date.desc()).offset(offset).limit(limit)

    # Execute query
    result = await db.execute(query)
    videos = result.scalars().all()

    # Transform to response items
    items: List[VideoListItem] = []
    for video in videos:
        transcript_summary = _build_transcript_summary(list(video.transcripts))
        channel_title = video.channel.title if video.channel else None

        # Build classification fields
        category_name = video.category.name if video.category else None
        tags = [tag.tag for tag in video.tags] if video.tags else []
        topics = [
            TopicSummary(
                topic_id=vt.topic_category.topic_id,
                name=vt.topic_category.category_name,
                parent_path=None,  # TODO: Compute hierarchy path if needed
            )
            for vt in video.video_topics
        ] if video.video_topics else []

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
    channel_query = select(ChannelDB).where(ChannelDB.channel_id == channel_id)
    result = await session.execute(channel_query)
    channel = result.scalar_one_or_none()

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
        now_utc = datetime.now(timezone.utc)
        # Ensure recovered_at is timezone-aware for comparison
        recovered_at = channel.recovered_at
        if recovered_at.tzinfo is None:
            recovered_at = recovered_at.replace(tzinfo=timezone.utc)
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
