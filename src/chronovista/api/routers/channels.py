"""Channel API endpoints.

This module provides REST API endpoints for channel operations:
- GET /channels - List channels with pagination and filtering
- GET /channels/{channel_id} - Get channel details by ID
- GET /channels/{channel_id}/videos - Get videos belonging to a channel

All endpoints require authentication via the require_auth dependency.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import GET_ITEM_ERRORS, LIST_ERRORS
from chronovista.api.schemas.channels import (
    ChannelDetail,
    ChannelDetailResponse,
    ChannelListItem,
    ChannelListResponse,
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
from chronovista.exceptions import NotFoundError

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
    db : AsyncSession
        Database session from dependency.

    Returns
    -------
    ChannelListResponse
        Paginated list of channels with metadata.
    """
    # Build base query
    query = select(ChannelDB)

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
        created_at=channel.created_at,
        updated_at=channel.updated_at,
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
        .where(VideoDB.deleted_flag.is_(False))
        .options(selectinload(VideoDB.transcripts))
        .options(selectinload(VideoDB.channel))
        .options(selectinload(VideoDB.category))
        .options(selectinload(VideoDB.tags))
        .options(selectinload(VideoDB.video_topics).selectinload(VideoTopic.topic_category))
    )

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
