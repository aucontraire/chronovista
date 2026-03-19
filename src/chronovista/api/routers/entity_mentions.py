"""Entity mention endpoints for video entity summaries and entity-to-videos lookups.

This module handles the REST API endpoints for querying entity mentions
across videos, including per-video entity summaries and reverse lookups
from entity to videos.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.entity_mentions import (
    CreateEntityAliasRequest,
    EntityAliasSummary,
    EntityVideoResponse,
    EntityVideoResult,
    ExclusionPatternRequest,
    MentionPreview,
    PhoneticMatchResponse,
    VideoEntitiesResponse,
    VideoEntitySummary,
)
from chronovista.api.schemas.responses import ApiResponse, PaginationMeta
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.exceptions import ConflictError, NotFoundError
from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.enums import EntityAliasType
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.services.phonetic_matcher import PhoneticMatcher
from chronovista.services.tag_normalization import TagNormalizationService

router = APIRouter(dependencies=[Depends(require_auth)])

# Module-level repository / service instantiation (singleton pattern)
_mention_repo = EntityMentionRepository()
_alias_repo = EntityAliasRepository()
_normalizer = TagNormalizationService()


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
    status: str | None = Query(
        default=None, description="Filter by entity status (active, merged, deprecated)"
    ),
    search_aliases: bool = Query(
        default=False,
        description=(
            "When true, also search entity_aliases.alias_name (ILIKE) in addition to "
            "canonical_name. Only aliases of active entities are searched."
        ),
    ),
    exclude_alias_types: str | None = Query(
        default=None,
        description=(
            "Comma-separated alias types to exclude from alias search when "
            "search_aliases=true. E.g. 'asr_error' excludes ASR-error aliases."
        ),
    ),
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
        Case-insensitive substring search on canonical_name (and alias_name
        when search_aliases=true).
    sort : str | None
        Sort order: "name" (alphabetical, default) or "mentions" (desc).
    limit : int
        Maximum results per page (1-200, default 50).
    offset : int
        Pagination offset.
    status : str | None
        Filter by entity status. When omitted, only "active" entities are
        returned (preserves backwards-compatible behaviour for callers that
        do not pass the parameter).
    search_aliases : bool
        When True, JOIN entity_aliases and match on alias_name ILIKE as well
        as canonical_name ILIKE. Excluded alias types (see exclude_alias_types)
        are filtered out before the match is attempted. Only entities whose
        status is 'active' are surfaced through the alias join path.
    exclude_alias_types : str | None
        Comma-separated list of alias_type values to exclude when
        search_aliases=True. For example, ``asr_error`` prevents ASR-error
        aliases from matching even if their text happens to match the query.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Paginated list of entity objects with pagination metadata.
    """
    # Determine the effective status filter.
    # Default to "active" to preserve backwards-compatible behaviour.
    effective_status = status if status is not None else "active"

    # Base query: filter by status
    base = select(NamedEntityDB).where(NamedEntityDB.status == effective_status)
    count_base = select(func.count(NamedEntityDB.id)).where(
        NamedEntityDB.status == effective_status
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
        if search_aliases:
            # Build the list of excluded alias types from the comma-separated param.
            excluded_types: list[str] = (
                [t.strip() for t in exclude_alias_types.split(",") if t.strip()]
                if exclude_alias_types
                else []
            )

            # Sub-select: entity IDs that have a matching alias (not excluded).
            alias_select = select(EntityAliasDB.entity_id).where(
                EntityAliasDB.alias_name.ilike(f"%{search}%")
            )
            if excluded_types:
                alias_select = alias_select.where(
                    EntityAliasDB.alias_type.notin_(excluded_types)
                )
            alias_scalar_subq = alias_select.scalar_subquery()

            # Match on canonical_name OR matching alias.
            name_filter = NamedEntityDB.canonical_name.ilike(f"%{search}%")
            alias_filter = NamedEntityDB.id.in_(alias_scalar_subq)
            combined_filter = or_(name_filter, alias_filter)
            base = base.where(combined_filter)
            count_base = count_base.where(combined_filter)
        else:
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

    entity_query = (
        select(NamedEntityDB)
        .where(NamedEntityDB.id == parsed_entity_id)
        .options(selectinload(NamedEntityDB.aliases))
    )
    entity_result = await session.execute(entity_query)
    entity = entity_result.scalar_one_or_none()
    if entity is None:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # Filter out asr_error aliases — those are internal detection noise and
    # are not useful to display to users. Genuine alias types are:
    # name_variant, abbreviation, nickname, translated_name, former_name.
    genuine_aliases = [
        EntityAliasSummary(
            alias_name=a.alias_name,
            alias_type=a.alias_type,
            occurrence_count=a.occurrence_count,
        )
        for a in entity.aliases
        if a.alias_type != "asr_error"
    ]
    # Sort by occurrence count descending, then alphabetically for stability
    genuine_aliases.sort(key=lambda a: (-a.occurrence_count, a.alias_name))

    return {
        "data": {
            "entity_id": str(entity.id),
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type,
            "description": entity.description,
            "status": entity.status,
            "mention_count": entity.mention_count or 0,
            "video_count": entity.video_count or 0,
            "aliases": [a.model_dump() for a in genuine_aliases],
            "exclusion_patterns": list(entity.exclusion_patterns or []),
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


@router.post(
    "/entities/{entity_id}/aliases",
    status_code=201,
    summary="Add an alias to a named entity",
)
async def create_entity_alias(
    entity_id: str = Path(..., description="Named entity UUID"),
    body: CreateEntityAliasRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new alias for a named entity.

    Normalizes the alias name, checks for duplicates, and persists the
    new alias. Returns the created alias in the standard response envelope.

    Parameters
    ----------
    entity_id : str
        Named entity UUID (string representation).
    body : CreateEntityAliasRequest
        Request body with alias_name and optional alias_type.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Created alias wrapped in a ``data`` envelope.

    Raises
    ------
    NotFoundError
        If the entity does not exist (404).
    ConflictError
        If an alias with the same normalized name already exists on
        this entity (409).
    """
    # Parse entity_id
    try:
        parsed_entity_id = uuid.UUID(entity_id)
    except ValueError:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # Look up entity
    entity_query = select(NamedEntityDB).where(NamedEntityDB.id == parsed_entity_id)
    entity_result = await session.execute(entity_query)
    entity = entity_result.scalar_one_or_none()
    if entity is None:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # Normalize alias name
    normalized_alias = _normalizer.normalize(body.alias_name)
    if normalized_alias is None:
        raise ConflictError(
            message="Alias name normalizes to an empty string",
            details={"alias_name": body.alias_name},
        )

    # Check for duplicate (same entity + same normalized name)
    dup_query = select(EntityAliasDB).where(
        EntityAliasDB.entity_id == parsed_entity_id,
        EntityAliasDB.alias_name_normalized == normalized_alias,
    )
    dup_result = await session.execute(dup_query)
    if dup_result.scalar_one_or_none() is not None:
        raise ConflictError(
            message=f"Alias '{body.alias_name}' already exists for this entity",
            details={
                "entity_id": entity_id,
                "alias_name": body.alias_name,
                "normalized": normalized_alias,
            },
        )

    # Create alias
    alias_create = EntityAliasCreate(
        entity_id=parsed_entity_id,
        alias_name=body.alias_name,
        alias_name_normalized=normalized_alias,
        alias_type=EntityAliasType(body.alias_type),
        occurrence_count=0,
    )
    db_alias = await _alias_repo.create(session, obj_in=alias_create)
    await session.commit()
    await session.refresh(db_alias)

    return {
        "data": EntityAliasSummary(
            alias_name=db_alias.alias_name,
            alias_type=db_alias.alias_type,
            occurrence_count=db_alias.occurrence_count,
        ).model_dump()
    }


# ═══════════════════════════════════════════════════════════════════════════
# GET /entities/{entity_id}/phonetic-matches
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/entities/{entity_id}/phonetic-matches",
    response_model=ApiResponse[list[PhoneticMatchResponse]],
    status_code=200,
    summary="Find phonetic ASR variants for an entity",
)
async def get_phonetic_matches(
    entity_id: uuid.UUID,
    threshold: float = Query(default=0.5, ge=0.0, le=1.0),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[PhoneticMatchResponse]]:
    """Find suspected phonetic ASR variants for a named entity.

    Uses ``PhoneticMatcher`` to scan transcript segments from videos
    associated with the entity and scores N-grams against the entity
    name and aliases.

    Parameters
    ----------
    entity_id : uuid.UUID
        Named entity UUID.
    threshold : float
        Minimum confidence score to include a match (0.0-1.0, default 0.5).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ApiResponse[list[PhoneticMatchResponse]]
        List of phonetic matches with video title enrichment.

    Raises
    ------
    NotFoundError
        If the entity does not exist in the database (404).
    """
    # Verify entity exists
    entity = await session.get(NamedEntityDB, entity_id)
    if entity is None:
        raise NotFoundError(resource_type="Entity", identifier=str(entity_id))

    # Run phonetic matcher
    matcher = PhoneticMatcher(entity_mention_repo=EntityMentionRepository())
    matches = await matcher.match_entity(
        entity_id=entity_id,
        session=session,
        threshold=threshold,
    )

    # Video title enrichment
    video_ids = list({m.video_id for m in matches})
    if video_ids:
        stmt = select(VideoDB.video_id, VideoDB.title).where(
            VideoDB.video_id.in_(video_ids)
        )
        rows = (await session.execute(stmt)).all()
        title_map = {r.video_id: r.title for r in rows}
    else:
        title_map = {}

    results = [
        PhoneticMatchResponse(
            original_text=m.original_text,
            proposed_correction=m.proposed_correction,
            confidence=m.confidence,
            evidence_description=m.evidence_description,
            video_id=m.video_id,
            segment_id=m.segment_id,
            video_title=title_map.get(m.video_id),
        )
        for m in matches
    ]

    return ApiResponse[list[PhoneticMatchResponse]](data=results)


# ═══════════════════════════════════════════════════════════════════════════
# POST /entities/{entity_id}/exclusion-patterns
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/entities/{entity_id}/exclusion-patterns",
    status_code=201,
    summary="Add an exclusion pattern to a named entity",
)
async def add_exclusion_pattern(
    entity_id: str = Path(..., description="Named entity UUID"),
    body: ExclusionPatternRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Add an exclusion pattern to a named entity.

    Exclusion patterns are strings that, when found in a transcript segment,
    cause the entity mention scanner to skip that segment for this entity.

    Parameters
    ----------
    entity_id : str
        Named entity UUID (string representation).
    body : ExclusionPatternRequest
        Request body with the pattern string.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Updated exclusion_patterns list wrapped in a ``data`` envelope.

    Raises
    ------
    NotFoundError
        If the entity does not exist (404).
    ConflictError
        If the pattern already exists on this entity (409).
    """
    # Parse entity_id
    try:
        parsed_entity_id = uuid.UUID(entity_id)
    except ValueError:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # Look up entity
    entity = await session.get(NamedEntityDB, parsed_entity_id)
    if entity is None:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    trimmed = body.pattern.strip()
    if not trimmed:
        raise ConflictError(
            message="Pattern is empty after trimming whitespace",
            details={"pattern": body.pattern},
        )

    current_patterns: list[str] = list(entity.exclusion_patterns or [])

    # Check for duplicate
    if trimmed in current_patterns:
        raise ConflictError(
            message=f"Exclusion pattern '{trimmed}' already exists for this entity",
            details={
                "entity_id": entity_id,
                "pattern": trimmed,
            },
        )

    current_patterns.append(trimmed)
    entity.exclusion_patterns = current_patterns
    session.add(entity)
    await session.commit()
    await session.refresh(entity)

    return {
        "data": {
            "exclusion_patterns": list(entity.exclusion_patterns or []),
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# DELETE /entities/{entity_id}/exclusion-patterns
# ═══════════════════════════════════════════════════════════════════════════


@router.delete(
    "/entities/{entity_id}/exclusion-patterns",
    status_code=200,
    summary="Remove an exclusion pattern from a named entity",
)
async def remove_exclusion_pattern(
    entity_id: str = Path(..., description="Named entity UUID"),
    body: ExclusionPatternRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove an exclusion pattern from a named entity.

    Parameters
    ----------
    entity_id : str
        Named entity UUID (string representation).
    body : ExclusionPatternRequest
        Request body with the pattern string to remove.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Updated exclusion_patterns list wrapped in a ``data`` envelope.

    Raises
    ------
    NotFoundError
        If the entity does not exist (404), or if the pattern is not
        found in the entity's exclusion_patterns list (404).
    """
    # Parse entity_id
    try:
        parsed_entity_id = uuid.UUID(entity_id)
    except ValueError:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # Look up entity
    entity = await session.get(NamedEntityDB, parsed_entity_id)
    if entity is None:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    trimmed = body.pattern.strip()
    current_patterns: list[str] = list(entity.exclusion_patterns or [])

    if trimmed not in current_patterns:
        raise NotFoundError(
            resource_type="ExclusionPattern",
            identifier=trimmed,
        )

    current_patterns.remove(trimmed)
    entity.exclusion_patterns = current_patterns
    session.add(entity)
    await session.commit()
    await session.refresh(entity)

    return {
        "data": {
            "exclusion_patterns": list(entity.exclusion_patterns or []),
        }
    }
