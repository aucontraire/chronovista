"""Topic list and detail endpoints.

This module provides API endpoints for accessing topic (TopicCategory) data
with aggregated video and channel counts. The database entity is TopicCategory,
but the API exposes it as "Topic" for simplicity.

Route Order: The videos endpoint MUST be defined before the detail endpoint
because the detail endpoint uses :path which would otherwise greedily match
requests to /topics/{topic_id}/videos.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.api.deps import get_db, require_auth
from chronovista.api.routers.responses import GET_ITEM_ERRORS, LIST_ERRORS
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.topics import (
    TopicDetail,
    TopicDetailResponse,
    TopicHierarchyItem,
    TopicHierarchyResponse,
    TopicListItem,
    TopicListResponse,
)
from chronovista.api.schemas.videos import VideoListItem, VideoListResponse
from chronovista.db.models import ChannelTopic, TopicCategory, Video, VideoTopic
from chronovista.exceptions import NotFoundError


router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/topics", response_model=TopicListResponse, responses=LIST_ERRORS)
async def list_topics(
    session: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> TopicListResponse:
    """
    List topics with pagination and aggregated counts.

    Returns topics sorted by video_count in descending order by default.
    Includes aggregated video_count and channel_count for each topic.

    Parameters
    ----------
    session : AsyncSession
        Database session from dependency.
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).

    Returns
    -------
    TopicListResponse
        Paginated list of topics with metadata.
    """
    # Subquery for video count
    video_count_subq = (
        select(func.count(VideoTopic.video_id))
        .where(VideoTopic.topic_id == TopicCategory.topic_id)
        .correlate(TopicCategory)
        .scalar_subquery()
    )

    # Subquery for channel count
    channel_count_subq = (
        select(func.count(ChannelTopic.channel_id))
        .where(ChannelTopic.topic_id == TopicCategory.topic_id)
        .correlate(TopicCategory)
        .scalar_subquery()
    )

    # Main query with counts - selecting specific columns for aggregation
    query = select(
        TopicCategory.topic_id,
        TopicCategory.category_name.label("name"),
        video_count_subq.label("video_count"),
        channel_count_subq.label("channel_count"),
    )

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(TopicCategory)
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering (video_count DESC per spec) and pagination
    query = (
        query.order_by(video_count_subq.desc())
        .offset(offset)
        .limit(limit)
    )

    # Execute query
    result = await session.execute(query)
    rows = result.all()

    # Transform to response items
    items: List[TopicListItem] = []
    for row in rows:
        items.append(
            TopicListItem(
                topic_id=row.topic_id,
                name=row.name,
                video_count=row.video_count or 0,
                channel_count=row.channel_count or 0,
            )
        )

    # Build pagination
    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return TopicListResponse(data=items, pagination=pagination)


@router.get("/topics/hierarchy", response_model=TopicHierarchyResponse, responses=LIST_ERRORS)
async def get_topic_hierarchy(
    session: AsyncSession = Depends(get_db),
    min_video_count: int = Query(
        0,
        ge=0,
        description="Minimum video count to include topic (filter out rarely-used topics)",
    ),
    include_empty: bool = Query(
        False,
        description="Include topics with zero videos",
    ),
) -> TopicHierarchyResponse:
    """
    Get topics with hierarchy information.

    Returns all topics with pre-computed hierarchy paths for use in
    hierarchical combobox UI. Topics are ordered by depth first, then
    alphabetically within each level.

    Parameters
    ----------
    session : AsyncSession
        Database session from dependency.
    min_video_count : int
        Minimum video count to include topic (default 0).
    include_empty : bool
        Include topics with zero videos (default False).

    Returns
    -------
    TopicHierarchyResponse
        Flattened topic list with hierarchy information.
    """
    # Subquery for video count
    video_count_subq = (
        select(func.count(VideoTopic.video_id))
        .where(VideoTopic.topic_id == TopicCategory.topic_id)
        .correlate(TopicCategory)
        .scalar_subquery()
    )

    # Build query with video counts
    query = select(
        TopicCategory.topic_id,
        TopicCategory.category_name.label("name"),
        TopicCategory.parent_topic_id,
        video_count_subq.label("video_count"),
    )

    # Apply filters
    if not include_empty:
        query = query.where(video_count_subq > 0)
    if min_video_count > 0:
        query = query.where(video_count_subq >= min_video_count)

    # Order by name for consistent output
    query = query.order_by(TopicCategory.category_name)

    # Execute query
    result = await session.execute(query)
    rows = result.all()

    # Build topic lookup for parent path computation
    topic_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        topic_map[row.topic_id] = {
            "topic_id": row.topic_id,
            "name": row.name,
            "parent_topic_id": row.parent_topic_id,
            "video_count": row.video_count or 0,
        }

    def compute_depth_path_and_sort_key(
        topic_id: str,
    ) -> tuple[int, Optional[str], List[str]]:
        """Compute depth, parent path, and hierarchical sort key for a topic."""
        depth = 0
        path_parts: List[str] = []
        current = topic_map.get(topic_id)
        if not current:
            return 0, None, []

        parent_id = current.get("parent_topic_id")
        while parent_id and parent_id in topic_map:
            parent = topic_map[parent_id]
            path_parts.insert(0, parent["name"])
            parent_id = parent.get("parent_topic_id")
            depth += 1

        parent_path = " > ".join(path_parts) if path_parts else None

        # Build sort key: full hierarchical path as list for proper ordering
        # e.g., "Music" -> ["Music"], "Christian music" -> ["Music", "Christian music"]
        sort_key = path_parts + [current["name"]]

        return depth, parent_path, sort_key

    # Build hierarchy items with computed depth and parent paths
    items: List[TopicHierarchyItem] = []
    sort_keys: dict[str, List[str]] = {}
    for row in rows:
        depth, parent_path, sort_key = compute_depth_path_and_sort_key(row.topic_id)
        sort_keys[row.topic_id] = sort_key
        items.append(
            TopicHierarchyItem(
                topic_id=row.topic_id,
                name=row.name,
                parent_topic_id=row.parent_topic_id,
                parent_path=parent_path,
                depth=depth,
                video_count=row.video_count or 0,
            )
        )

    # Sort hierarchically: children appear immediately after their parent
    # e.g., Music, Christian music, Classical music, ..., Sports, American football
    items.sort(key=lambda x: [s.lower() for s in sort_keys.get(x.topic_id, [x.name])])

    return TopicHierarchyResponse(data=items)


# IMPORTANT: This endpoint MUST be defined before the detail endpoint below
# because /topics/{topic_id:path} would otherwise greedily match this URL pattern.
@router.get("/topics/{topic_id}/videos", response_model=VideoListResponse, responses=GET_ITEM_ERRORS)
async def get_topic_videos(
    topic_id: str = Path(
        ...,
        description="Topic ID (knowledge graph format like /m/xxx or alphanumeric). "
        "Note: For IDs with slashes (e.g., /m/019_rr), URL-encode the ID "
        "(e.g., %2Fm%2F019_rr) for this endpoint.",
        examples=["gaming", "%2Fm%2F019_rr"],
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> VideoListResponse:
    """
    Get videos associated with a topic.

    Returns videos that have been classified with the specified topic,
    ordered by upload date descending.

    Parameters
    ----------
    topic_id : str
        Topic ID (knowledge graph format like /m/xxx or alphanumeric).
    limit : int
        Items per page (1-100, default 20).
    offset : int
        Pagination offset (default 0).
    session : AsyncSession
        Database session from dependency.

    Returns
    -------
    VideoListResponse
        Paginated list of videos with the topic.

    Raises
    ------
    NotFoundError
        404 if topic not found.
    """
    # Verify topic exists
    topic_result = await session.execute(
        select(TopicCategory.topic_id).where(TopicCategory.topic_id == topic_id)
    )
    if not topic_result.scalar_one_or_none():
        raise NotFoundError(
            resource_type="Topic",
            identifier=topic_id,
            hint="Verify the topic ID or check available topics.",
        )

    # Build query for videos with this topic
    query = (
        select(Video)
        .join(VideoTopic, Video.video_id == VideoTopic.video_id)
        .where(VideoTopic.topic_id == topic_id)
        .where(Video.deleted_flag.is_(False))
        .options(selectinload(Video.transcripts))
        .options(selectinload(Video.channel))
        .options(selectinload(Video.tags))
        .options(selectinload(Video.category))
    )

    # Get total count (before pagination)
    count_query = (
        select(func.count(Video.video_id))
        .select_from(Video)
        .join(VideoTopic, Video.video_id == VideoTopic.video_id)
        .where(VideoTopic.topic_id == topic_id)
        .where(Video.deleted_flag.is_(False))
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    query = query.order_by(Video.upload_date.desc()).offset(offset).limit(limit)

    # Execute query
    result = await session.execute(query)
    videos = result.scalars().all()

    # Transform to response items (reusing pattern from videos router)
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

        # Extract tags (may be empty if not loaded)
        video_tags = [t.tag for t in video.tags] if video.tags else []

        # Extract category info (may be None if not loaded)
        category_id_val = video.category_id
        category_name = video.category.name if video.category else None

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


# IMPORTANT: This endpoint uses :path which greedily matches all remaining path segments.
# It MUST be defined after the /topics/{topic_id}/videos endpoint above.
# When a slash-containing topic_id is used with /videos, this route will match
# and we need to handle it by forwarding to get_topic_videos.
@router.get(
    "/topics/{topic_id:path}",
    response_model=Union[TopicDetailResponse, VideoListResponse],
    responses={
        200: {
            "description": "Topic details or videos list if path ends with /videos",
            "content": {
                "application/json": {
                    "examples": {
                        "topic_detail": {
                            "summary": "Topic detail response",
                            "value": {"data": {"topic_id": "/m/098wr", "name": "Society"}},
                        },
                        "topic_videos": {
                            "summary": "Topic videos response (when path ends with /videos)",
                            "value": {"data": [], "pagination": {"total": 0}},
                        },
                    }
                }
            },
        },
        **GET_ITEM_ERRORS,
    },
)
async def get_topic(
    topic_id: str = Path(
        ...,
        description="Topic ID (knowledge graph format like /m/xxx or alphanumeric). "
        "Supports slashes in IDs without URL encoding. "
        "If path ends with /videos, returns videos for that topic.",
        examples=["/m/019_rr", "gaming", "/m/098wr/videos"],
    ),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100, description="Items per page (for /videos)"),
    offset: int = Query(0, ge=0, description="Pagination offset (for /videos)"),
) -> Union[TopicDetailResponse, VideoListResponse]:
    """
    Get topic details by ID.

    Returns full topic metadata including aggregated video and channel counts.
    Also handles /videos sub-path for topic IDs containing slashes.

    Parameters
    ----------
    topic_id : str
        Topic ID (knowledge graph format like /m/xxx or alphanumeric).
    session : AsyncSession
        Database session from dependency.
    limit : int
        Items per page (used when path ends with /videos).
    offset : int
        Pagination offset (used when path ends with /videos).

    Returns
    -------
    TopicDetailResponse
        Full topic details with aggregated counts.

    Raises
    ------
    NotFoundError
        404 if topic not found.
    """
    # Handle /videos suffix - forward to videos logic for slash-containing topic IDs
    # This happens because :path greedily matches /m/098wr/videos as topic_id
    if topic_id.endswith("/videos"):
        actual_topic_id = topic_id[:-7]  # Remove "/videos" suffix
        return await get_topic_videos(
            topic_id=actual_topic_id,
            limit=limit,
            offset=offset,
            session=session,
        )

    # Subquery for video count
    video_count_subq = (
        select(func.count(VideoTopic.video_id))
        .where(VideoTopic.topic_id == TopicCategory.topic_id)
        .correlate(TopicCategory)
        .scalar_subquery()
    )

    # Subquery for channel count
    channel_count_subq = (
        select(func.count(ChannelTopic.channel_id))
        .where(ChannelTopic.topic_id == TopicCategory.topic_id)
        .correlate(TopicCategory)
        .scalar_subquery()
    )

    # Query topic with counts
    query = select(
        TopicCategory.topic_id,
        TopicCategory.category_name.label("name"),
        TopicCategory.parent_topic_id,
        TopicCategory.topic_type,
        TopicCategory.wikipedia_url,
        TopicCategory.normalized_name,
        TopicCategory.source,
        TopicCategory.created_at,
        video_count_subq.label("video_count"),
        channel_count_subq.label("channel_count"),
    ).where(TopicCategory.topic_id == topic_id)

    result = await session.execute(query)
    row = result.one_or_none()

    if not row:
        raise NotFoundError(
            resource_type="Topic",
            identifier=topic_id,
            hint="Verify the topic ID or check available topics.",
        )

    # Build response
    detail = TopicDetail(
        topic_id=row.topic_id,
        name=row.name,
        video_count=row.video_count or 0,
        channel_count=row.channel_count or 0,
        parent_topic_id=row.parent_topic_id,
        topic_type=row.topic_type,
        wikipedia_url=row.wikipedia_url,
        normalized_name=row.normalized_name,
        source=row.source,
        created_at=row.created_at,
    )

    return TopicDetailResponse(data=detail)
