"""Entity mention endpoints for video entity summaries and entity-to-videos lookups.

This module handles the REST API endpoints for querying entity mentions
across videos, including per-video entity summaries and reverse lookups
from entity to videos.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.entity_mentions import (
    EntityVideoResponse,
    EntityVideoResult,
    MentionPreview,
    VideoEntitiesResponse,
    VideoEntitySummary,
)
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.exceptions import NotFoundError
from chronovista.repositories.entity_mention_repository import EntityMentionRepository

router = APIRouter(dependencies=[Depends(require_auth)])

# Module-level repository instantiation (singleton pattern)
_mention_repo = EntityMentionRepository()


@router.get(
    "/entities",
    status_code=200,
    summary="List named entities with filtering and sorting",
)
async def list_entities(
    type: str | None = Query(default=None, description="Filter by entity type"),
    has_mentions: bool | None = Query(
        default=None, description="Filter by mention presence"
    ),
    search: str | None = Query(default=None, description="Search by name"),
    sort: str | None = Query(
        default=None, description="Sort field: name (default), mentions"
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List named entities with optional filters, search, and sorting.

    Parameters
    ----------
    type : str | None
        Filter by entity_type value (person, organization, place, etc.).
    has_mentions : bool | None
        If True, only entities with mention_count > 0.
        If False, only entities with mention_count = 0.
    search : str | None
        Case-insensitive substring search on canonical_name.
    sort : str | None
        Sort order: "name" (alphabetical, default) or "mentions" (desc).
    limit : int
        Maximum results per page (1-200, default 50).
    offset : int
        Pagination offset.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Paginated list of entity objects with pagination metadata.
    """
    # Base query: active entities only
    base = select(NamedEntityDB).where(NamedEntityDB.status == "active")
    count_base = select(func.count(NamedEntityDB.id)).where(
        NamedEntityDB.status == "active"
    )

    # Apply filters
    if type is not None:
        base = base.where(NamedEntityDB.entity_type == type)
        count_base = count_base.where(NamedEntityDB.entity_type == type)

    if has_mentions is True:
        base = base.where(NamedEntityDB.mention_count > 0)
        count_base = count_base.where(NamedEntityDB.mention_count > 0)
    elif has_mentions is False:
        base = base.where(NamedEntityDB.mention_count == 0)
        count_base = count_base.where(NamedEntityDB.mention_count == 0)

    if search:
        base = base.where(NamedEntityDB.canonical_name.ilike(f"%{search}%"))
        count_base = count_base.where(
            NamedEntityDB.canonical_name.ilike(f"%{search}%")
        )

    # Total count
    total = (await session.execute(count_base)).scalar() or 0

    # Sorting
    if sort == "mentions":
        base = base.order_by(
            NamedEntityDB.mention_count.desc(),
            NamedEntityDB.canonical_name.asc(),
        )
    else:
        base = base.order_by(NamedEntityDB.canonical_name.asc())

    # Pagination
    base = base.offset(offset).limit(limit)

    result = await session.execute(base)
    entities = list(result.scalars().all())

    data = [
        {
            "entity_id": str(e.id),
            "canonical_name": e.canonical_name,
            "entity_type": e.entity_type,
            "description": e.description,
            "status": e.status,
            "mention_count": e.mention_count or 0,
            "video_count": e.video_count or 0,
        }
        for e in entities
    ]

    return {
        "data": data,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        },
    }


@router.get(
    "/videos/{video_id}/entities",
    response_model=VideoEntitiesResponse,
    status_code=200,
    summary="Get entity summary for a video",
)
async def get_video_entities(
    video_id: str = Path(..., description="YouTube video ID"),
    language_code: str | None = Query(
        default=None, description="BCP-47 language code filter"
    ),
    session: AsyncSession = Depends(get_db),
) -> VideoEntitiesResponse:
    """Get all named entities mentioned in a video with mention counts.

    Returns entities sorted by mention_count descending. Each entity
    includes the total number of distinct segments where it is mentioned
    and the timestamp of its first mention.

    Parameters
    ----------
    video_id : str
        YouTube video ID.
    language_code : str | None
        Optional BCP-47 language code to filter mentions by language.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    VideoEntitiesResponse
        List of entity summaries for the video.

    Raises
    ------
    NotFoundError
        If the video does not exist in the database (404).
    """
    # Check video existence
    video_query = select(VideoDB.video_id).where(VideoDB.video_id == video_id)
    video_result = await session.execute(video_query)
    if not video_result.scalar_one_or_none():
        raise NotFoundError(resource_type="Video", identifier=video_id)

    # Fetch entity summaries from repository
    summaries = await _mention_repo.get_video_entity_summary(
        session, video_id=video_id, language_code=language_code
    )

    # Map dicts to response models
    data = [VideoEntitySummary(**s) for s in summaries]

    return VideoEntitiesResponse(data=data)


@router.get(
    "/entities/{entity_id}",
    status_code=200,
    summary="Get entity detail",
)
async def get_entity_detail(
    entity_id: str = Path(..., description="Named entity UUID"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get detail for a single named entity.

    Parameters
    ----------
    entity_id : str
        Named entity UUID (string representation).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Entity detail wrapped in a ``data`` envelope.

    Raises
    ------
    NotFoundError
        If the entity does not exist in the database (404).
    """
    try:
        parsed_entity_id = uuid.UUID(entity_id)
    except ValueError:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    entity_query = select(NamedEntityDB).where(
        NamedEntityDB.id == parsed_entity_id
    )
    entity_result = await session.execute(entity_query)
    entity = entity_result.scalar_one_or_none()
    if entity is None:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    return {
        "data": {
            "entity_id": str(entity.id),
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type,
            "description": entity.description,
            "status": entity.status,
            "mention_count": entity.mention_count or 0,
        }
    }


@router.get(
    "/entities/{entity_id}/videos",
    response_model=EntityVideoResponse,
    status_code=200,
    summary="Get videos where an entity is mentioned",
)
async def get_entity_videos(
    entity_id: str = Path(..., description="Named entity UUID"),
    language_code: str | None = Query(
        default=None, description="BCP-47 language code filter"
    ),
    limit: int = Query(
        default=20, ge=1, le=100, description="Items per page"
    ),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> EntityVideoResponse:
    """Get a paginated list of videos where a named entity is mentioned.

    Each video result includes the mention count and up to 5 mention
    previews showing segment ID, start time, and matched text.

    Parameters
    ----------
    entity_id : str
        Named entity UUID (string representation).
    language_code : str | None
        Optional BCP-47 language code to filter mentions by language.
    limit : int
        Maximum number of results per page (1--100, default 20).
    offset : int
        Number of results to skip (default 0).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    EntityVideoResponse
        Paginated list of video results with mention previews.

    Raises
    ------
    NotFoundError
        If the entity does not exist in the database (404).
    """
    # Parse entity_id string to UUID
    try:
        parsed_entity_id = uuid.UUID(entity_id)
    except ValueError:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # Check entity existence
    entity_query = select(NamedEntityDB.id).where(
        NamedEntityDB.id == parsed_entity_id
    )
    entity_result = await session.execute(entity_query)
    if not entity_result.scalar_one_or_none():
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # Fetch paginated video list from repository
    results, total = await _mention_repo.get_entity_video_list(
        session,
        entity_id=parsed_entity_id,
        language_code=language_code,
        limit=limit,
        offset=offset,
    )

    # Map dicts to response models
    data = [
        EntityVideoResult(
            video_id=r["video_id"],
            video_title=r["video_title"],
            channel_name=r["channel_name"],
            mention_count=r["mention_count"],
            mentions=[MentionPreview(**m) for m in r["mentions"]],
        )
        for r in results
    ]

    return EntityVideoResponse(
        data=data,
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + limit < total,
        ),
    )
