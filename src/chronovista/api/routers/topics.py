"""Topic list and detail endpoints.

This module provides API endpoints for accessing topic (TopicCategory) data
with aggregated video and channel counts. The database entity is TopicCategory,
but the API exposes it as "Topic" for simplicity.

Route Order: The videos endpoint MUST be defined before the detail endpoint
because the detail endpoint uses :path which would otherwise greedily match
requests to /topics/{topic_id}/videos.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_db,
    get_topic_category_repository,
    get_video_repository,
    require_auth,
)
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
from chronovista.exceptions import NotFoundError
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.repositories.video_repository import VideoRepository

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/topics", response_model=TopicListResponse, responses=LIST_ERRORS)
async def list_topics(
    session: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    topic_repo: TopicCategoryRepository = Depends(get_topic_category_repository),
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
    total, rows = await topic_repo.list_with_counts(session, offset=offset, limit=limit)

    items = [
        TopicListItem(
            topic_id=topic.topic_id,
            name=topic.category_name,
            video_count=video_count,
            channel_count=channel_count,
        )
        for topic, video_count, channel_count in rows
    ]

    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )

    return TopicListResponse(data=items, pagination=pagination)


@router.get(
    "/topics/hierarchy", response_model=TopicHierarchyResponse, responses=LIST_ERRORS
)
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
    topic_repo: TopicCategoryRepository = Depends(get_topic_category_repository),
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
    rows = await topic_repo.list_hierarchy_with_counts(
        session, min_video_count=min_video_count, include_empty=include_empty
    )

    # Build topic lookup for parent path computation
    topic_map: dict[str, dict[str, Any]] = {}
    for topic, video_count in rows:
        topic_map[topic.topic_id] = {
            "topic_id": topic.topic_id,
            "name": topic.category_name,
            "parent_topic_id": topic.parent_topic_id,
            "video_count": video_count,
        }

    def compute_depth_path_and_sort_key(
        topic_id: str,
    ) -> tuple[int, str | None, list[str]]:
        """Compute depth, parent path, and hierarchical sort key for a topic."""
        depth = 0
        path_parts: list[str] = []
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
    items: list[TopicHierarchyItem] = []
    sort_keys: dict[str, list[str]] = {}
    for topic, video_count in rows:
        depth, parent_path, sort_key = compute_depth_path_and_sort_key(topic.topic_id)
        sort_keys[topic.topic_id] = sort_key
        items.append(
            TopicHierarchyItem(
                topic_id=topic.topic_id,
                name=topic.category_name,
                parent_topic_id=topic.parent_topic_id,
                parent_path=parent_path,
                depth=depth,
                video_count=video_count,
            )
        )

    # Sort hierarchically: children appear immediately after their parent
    # e.g., Music, Christian music, Classical music, ..., Sports, American football
    items.sort(key=lambda x: [s.lower() for s in sort_keys.get(x.topic_id, [x.name])])

    return TopicHierarchyResponse(data=items)


# IMPORTANT: This endpoint MUST be defined before the detail endpoint below
# because /topics/{topic_id:path} would otherwise greedily match this URL pattern.
@router.get(
    "/topics/{topic_id}/videos",
    response_model=VideoListResponse,
    responses=GET_ITEM_ERRORS,
)
async def get_topic_videos(
    topic_id: str = Path(
        ...,
        description="Topic ID (knowledge graph format like /m/xxx or alphanumeric). "
        "Note: For IDs with slashes (e.g., /m/019_rr), URL-encode the ID "
        "(e.g., %2Fm%2F019_rr) for this endpoint.",
        examples=["gaming", "%2Fm%2F019_rr"],
    ),
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
    topic_repo: TopicCategoryRepository = Depends(get_topic_category_repository),
    video_repo: VideoRepository = Depends(get_video_repository),
) -> VideoListResponse:
    """
    Get videos associated with a topic.

    Returns videos that have been classified with the specified topic,
    ordered by upload date descending.

    Parameters
    ----------
    topic_id : str
        Topic ID (knowledge graph format like /m/xxx or alphanumeric).
    include_unavailable : bool
        Include unavailable videos (default False).
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
    if not await topic_repo.exists_by_topic_id(session, topic_id):
        raise NotFoundError(
            resource_type="Topic",
            identifier=topic_id,
            hint="Verify the topic ID or check available topics.",
        )

    total, videos = await video_repo.list_by_topic(
        session,
        topic_id,
        include_unavailable=include_unavailable,
        offset=offset,
        limit=limit,
    )

    # Transform to response items (reusing pattern from videos router)
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


# IMPORTANT: This endpoint uses :path which greedily matches all remaining path segments.
# It MUST be defined after the /topics/{topic_id}/videos endpoint above.
# When a slash-containing topic_id is used with /videos, this route will match
# and we need to handle it by forwarding to get_topic_videos.
@router.get(
    "/topics/{topic_id:path}",
    response_model=TopicDetailResponse | VideoListResponse,
    responses={
        200: {
            "description": "Topic details or videos list if path ends with /videos",
            "content": {
                "application/json": {
                    "examples": {
                        "topic_detail": {
                            "summary": "Topic detail response",
                            "value": {
                                "data": {"topic_id": "/m/098wr", "name": "Society"}
                            },
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
    include_unavailable: bool = Query(
        False,
        description="Include unavailable records in results (for /videos)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items per page (for /videos)"),
    offset: int = Query(0, ge=0, description="Pagination offset (for /videos)"),
    topic_repo: TopicCategoryRepository = Depends(get_topic_category_repository),
    video_repo: VideoRepository = Depends(get_video_repository),
) -> TopicDetailResponse | VideoListResponse:
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
    include_unavailable : bool
        Include unavailable videos (used when path ends with /videos).
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
    # This happens because :path greedily matches /m/098wr/videos as topic_id.
    # include_unavailable must be forwarded explicitly: this is a plain function
    # call, so get_topic_videos' own Query(False) default would arrive as an
    # unresolved sentinel (truthy) and silently disable the availability filter.
    if topic_id.endswith("/videos"):
        actual_topic_id = topic_id[:-7]  # Remove "/videos" suffix
        return await get_topic_videos(
            topic_id=actual_topic_id,
            include_unavailable=include_unavailable,
            limit=limit,
            offset=offset,
            session=session,
            topic_repo=topic_repo,
            video_repo=video_repo,
        )

    result = await topic_repo.get_with_counts(session, topic_id)

    if result is None:
        raise NotFoundError(
            resource_type="Topic",
            identifier=topic_id,
            hint="Verify the topic ID or check available topics.",
        )

    topic, video_count, channel_count = result

    # Build response
    detail = TopicDetail(
        topic_id=topic.topic_id,
        name=topic.category_name,
        video_count=video_count,
        channel_count=channel_count,
        parent_topic_id=topic.parent_topic_id,
        topic_type=topic.topic_type,
        wikipedia_url=topic.wikipedia_url,
        normalized_name=topic.normalized_name,
        source=topic.source,
        created_at=topic.created_at,
    )

    return TopicDetailResponse(data=detail)
