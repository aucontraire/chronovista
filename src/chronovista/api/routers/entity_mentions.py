"""Entity mention endpoints for video entity summaries and entity-to-videos lookups.

This module handles the REST API endpoints for querying entity mentions
across videos, including per-video entity summaries and reverse lookups
from entity to videos.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Body, Depends, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.entity_mentions import (
    ClassifyTagRequest,
    CreateEntityAliasRequest,
    CreateEntityRequest,
    DuplicateCheckResponse,
    EntityAliasSummary,
    EntitySearchResult,
    EntityVideoResponse,
    EntityVideoResult,
    ExclusionPatternRequest,
    ExistingEntityInfo,
    ManualAssociationResponse,
    MentionPreview,
    PhoneticMatchResponse,
    ScanRequest,
    ScanResultData,
    ScanResultResponse,
    VideoEntitiesResponse,
    VideoEntitySummary,
)
from chronovista.api.schemas.responses import ApiResponse, PaginationMeta
from chronovista.config.database import db_manager
from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.exceptions import (
    APIValidationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.enums import (
    DiscoveryMethod,
    EntityAliasType,
    EntityType,
    TagStatus,
)
from chronovista.models.named_entity import NamedEntityCreate
from chronovista.repositories.canonical_tag_repository import CanonicalTagRepository
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.tag_alias_repository import TagAliasRepository
from chronovista.repositories.tag_operation_log_repository import (
    TagOperationLogRepository,
)
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from chronovista.services.phonetic_matcher import PhoneticMatcher
from chronovista.services.tag_management import TagManagementService
from chronovista.services.tag_normalization import TagNormalizationService

router = APIRouter(dependencies=[Depends(require_auth)])

# Module-level repository / service instantiation (singleton pattern)
_mention_repo = EntityMentionRepository()
_alias_repo = EntityAliasRepository()
_entity_repo = NamedEntityRepository()
_normalizer = TagNormalizationService()
_tag_mgmt_service = TagManagementService(
    canonical_tag_repo=CanonicalTagRepository(),
    tag_alias_repo=TagAliasRepository(),
    named_entity_repo=NamedEntityRepository(),
    entity_alias_repo=EntityAliasRepository(),
    operation_log_repo=TagOperationLogRepository(),
)

# In-flight scan guard: tracks entity/video scans currently running
_scans_in_progress: set[str] = set()

# Rate limiting configuration for duplicate check (50 req/min per client)
RATE_LIMIT_DUPLICATE_CHECK = 50
RATE_LIMIT_WINDOW_SECONDS = 60

# Storage for rate limit tracking
_duplicate_check_counts: dict[str, list[float]] = defaultdict(list)


def _get_client_id(request: Request) -> str:
    """Get client identifier from request.

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
    request_counts: dict[str, list[float]],
    rate_limit: int,
) -> tuple[bool, int]:
    """Check if client has exceeded rate limit.

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
    "/entities/search",
    status_code=200,
    summary="Search entities for autocomplete",
)
async def search_entities(
    q: str = Query(..., min_length=2, description="Search query (min 2 chars)"),
    video_id: str | None = Query(default=None, description="Video ID for is_linked check"),
    limit: int = Query(default=10, ge=1, le=20, description="Max results"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Search named entities by name or alias for autocomplete.

    Performs ILIKE prefix search on canonical_name and alias_name,
    deduplicates by entity_id, and optionally checks whether each
    entity is already linked to a given video.

    Parameters
    ----------
    q : str
        Search query (minimum 2 characters).
    video_id : str | None
        Optional video ID; when provided, each result includes
        ``is_linked`` and ``link_sources`` fields.
    limit : int
        Maximum number of results (1-20, default 10).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        List of entity search results wrapped in a ``data`` envelope.
    """
    results = await _mention_repo.search_entities(
        session, query=q, video_id=video_id, limit=limit
    )
    return {"data": [EntitySearchResult(**r) for r in results]}


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
    "/entities/check-duplicate",
    response_model=DuplicateCheckResponse,
    status_code=200,
    summary="Check for duplicate entity by normalized name and type",
)
async def check_duplicate_entity(
    request: Request,
    name: str = Query(..., description="Entity name to check"),
    type: str = Query(..., description="Entity type (person, organization, place, etc.)"),
    session: AsyncSession = Depends(get_db),
) -> DuplicateCheckResponse | JSONResponse:
    """Check whether an entity with the same normalized name and type already exists.

    Normalizes the provided name using ``TagNormalizationService`` and queries
    the ``named_entities`` table for an active entity with the same normalized
    canonical name and entity type.

    Rate-limited to 50 requests per minute per client IP.

    Parameters
    ----------
    request : Request
        FastAPI request object (used for rate limiting).
    name : str
        Entity name to check for duplicates.
    type : str
        Entity type to filter by (person, organization, place, etc.).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    DuplicateCheckResponse
        Contains ``is_duplicate`` flag and optional ``existing_entity`` details.
    JSONResponse (429)
        If rate limit is exceeded.
    """
    # Rate limiting
    client_id = _get_client_id(request)
    is_allowed, retry_after = _check_rate_limit(
        client_id, _duplicate_check_counts, RATE_LIMIT_DUPLICATE_CHECK
    )
    if not is_allowed:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded. Maximum 50 duplicate-check requests per minute.",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    # Normalize the input name
    normalized_name = _normalizer.normalize(name)
    if not normalized_name:
        return DuplicateCheckResponse(is_duplicate=False, existing_entity=None)

    # Query for an active entity with the same normalized name and type
    query = select(NamedEntityDB).where(
        NamedEntityDB.canonical_name_normalized == normalized_name,
        NamedEntityDB.entity_type == type,
        NamedEntityDB.status == "active",
    )
    result = await session.execute(query)
    entity = result.scalar_one_or_none()

    if entity is not None:
        return DuplicateCheckResponse(
            is_duplicate=True,
            existing_entity=ExistingEntityInfo(
                entity_id=str(entity.id),
                canonical_name=entity.canonical_name,
                entity_type=entity.entity_type,
                description=entity.description,
            ),
        )

    return DuplicateCheckResponse(is_duplicate=False, existing_entity=None)


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
    except ValueError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc

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
    except ValueError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc

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
            sources=r["sources"],
            has_manual=r["has_manual"],
            first_mention_time=r["first_mention_time"],
            upload_date=r["upload_date"],
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
    except ValueError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc

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
    except ValueError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc

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
    except ValueError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc

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


# ═══════════════════════════════════════════════════════════════════════════
# POST /videos/{video_id}/entities/{entity_id}/manual
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/videos/{video_id}/entities/{entity_id}/manual",
    status_code=201,
    summary="Create manual entity-video association",
)
async def create_manual_association(
    video_id: str = Path(..., description="YouTube video ID"),
    entity_id: str = Path(..., description="Named entity UUID"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a manual association between a named entity and a video.

    Validates that both the video and entity exist, the entity is not
    deprecated, and no duplicate manual association exists.

    Parameters
    ----------
    video_id : str
        YouTube video ID.
    entity_id : str
        Named entity UUID (string representation).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Created mention wrapped in a ``data`` envelope with
        ManualAssociationResponse fields.

    Raises
    ------
    NotFoundError
        If the video or entity does not exist (404), or if entity_id
        is not a valid UUID.
    APIValidationError
        If the entity is deprecated (422).
    ConflictError
        If a manual association already exists (409).
    """
    # Parse entity_id to UUID
    try:
        parsed_entity_id = uuid.UUID(entity_id)
    except ValueError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc

    mention = await _mention_repo.create_manual_association(
        session, video_id=video_id, entity_id=parsed_entity_id
    )
    await session.commit()
    await session.refresh(mention)

    return {
        "data": ManualAssociationResponse(
            id=str(mention.id),
            entity_id=str(mention.entity_id),
            video_id=mention.video_id,
            detection_method=mention.detection_method,
            mention_text=mention.mention_text,
            created_at=mention.created_at.isoformat(),
        ).model_dump()
    }


# ═══════════════════════════════════════════════════════════════════════════
# DELETE /videos/{video_id}/entities/{entity_id}/manual
# ═══════════════════════════════════════════════════════════════════════════


@router.delete(
    "/videos/{video_id}/entities/{entity_id}/manual",
    status_code=204,
    response_class=Response,
    summary="Remove manual entity-video association",
)
async def delete_manual_association(
    video_id: str = Path(..., description="YouTube video ID"),
    entity_id: str = Path(..., description="Named entity UUID"),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Remove a manual association between a named entity and a video.

    Deletes the ``entity_mentions`` row with ``detection_method='manual'``
    for the given video and entity, and updates entity counters.

    Parameters
    ----------
    video_id : str
        YouTube video ID.
    entity_id : str
        Named entity UUID (string representation).
    session : AsyncSession
        Database session (injected).

    Raises
    ------
    NotFoundError
        If no manual association exists for this entity+video (404),
        or if entity_id is not a valid UUID.
    """
    # Parse entity_id to UUID
    try:
        parsed_entity_id = uuid.UUID(entity_id)
    except ValueError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc

    await _mention_repo.delete_manual_association(
        session, video_id=video_id, entity_id=parsed_entity_id
    )
    await session.commit()
    return Response(status_code=204)


# ═══════════════════════════════════════════════════════════════════════════
# POST /entities/classify — Tag-Backed Entity Creation
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/entities/classify",
    status_code=201,
    summary="Classify a canonical tag as a named entity",
)
async def classify_tag(
    body: ClassifyTagRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Classify an existing canonical tag to create or link a named entity.

    Delegates to ``TagManagementService.classify()`` which handles entity
    creation/linking and alias management. Maps service-layer ``ValueError``
    exceptions to appropriate HTTP status codes.

    Parameters
    ----------
    body : ClassifyTagRequest
        Request body with normalized_form, entity_type, and optional description.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Created/linked entity details with alias count and operation ID.

    Raises
    ------
    NotFoundError
        If the canonical tag is not found or inactive (404).
    ConflictError
        If the tag is already classified as an entity (409).
    APIValidationError
        If the request is otherwise invalid (400).
    """
    try:
        entity_type_enum = EntityType(body.entity_type)
    except ValueError as exc:
        raise BadRequestError(
            message=f"Invalid entity_type: {body.entity_type}",
            details={"entity_type": body.entity_type},
        ) from exc

    try:
        result = await _tag_mgmt_service.classify(
            session,
            body.normalized_form,
            entity_type_enum,
            description=body.description,
            auto_case=True,
        )
    except ValueError as exc:
        error_msg = str(exc)

        if "not found" in error_msg.lower() or "status" in error_msg.lower():
            raise NotFoundError(
                resource_type="CanonicalTag",
                identifier=body.normalized_form,
            ) from exc

        if "already classified" in error_msg.lower():
            # Look up the canonical tag to get existing entity details
            tag_query = select(CanonicalTagDB).where(
                CanonicalTagDB.normalized_form == body.normalized_form,
            )
            tag_result = await session.execute(tag_query)
            tag = tag_result.scalar_one_or_none()

            existing_entity_data: dict[str, Any] | None = None
            if tag is not None and tag.entity_id is not None:
                entity = await session.get(NamedEntityDB, tag.entity_id)
                if entity is not None:
                    existing_entity_data = {
                        "entity_id": str(entity.id),
                        "canonical_name": entity.canonical_name,
                        "entity_type": entity.entity_type,
                        "description": entity.description,
                    }

            raise ConflictError(
                message=error_msg,
                details={"existing_entity": existing_entity_data}
                if existing_entity_data
                else None,
            ) from exc

        # Other ValueError → 400 Bad Request
        raise BadRequestError(
            message=error_msg,
            details={"normalized_form": body.normalized_form},
        ) from exc

    # After successful classification, look up the canonical tag to get entity_id
    tag_query = select(CanonicalTagDB).where(
        CanonicalTagDB.normalized_form == body.normalized_form,
    )
    tag_result = await session.execute(tag_query)
    tag = tag_result.scalar_one_or_none()

    entity_id_str: str | None = None
    canonical_name = result.canonical_form
    description: str | None = body.description

    if tag is not None and tag.entity_id is not None:
        entity = await session.get(NamedEntityDB, tag.entity_id)
        if entity is not None:
            entity_id_str = str(entity.id)
            canonical_name = entity.canonical_name
            description = entity.description

    await session.commit()

    return {
        "entity_id": entity_id_str,
        "canonical_name": canonical_name,
        "entity_type": result.entity_type,
        "description": description,
        "alias_count": result.entity_alias_count,
        "entity_created": result.entity_created,
        "operation_id": str(result.operation_id),
    }


# ═══════════════════════════════════════════════════════════════════════════
# POST /entities — Standalone Entity Creation
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/entities",
    status_code=201,
    summary="Create a new named entity",
)
async def create_entity(
    body: CreateEntityRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a standalone named entity with optional aliases.

    Normalizes the entity name, checks for duplicates by normalized name
    and type, creates the entity, and registers aliases (including the
    canonical name as the first alias).

    Parameters
    ----------
    body : CreateEntityRequest
        Request body with name, entity_type, optional description and aliases.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Created entity summary with entity_id, canonical_name, entity_type,
        description, and alias_count.

    Raises
    ------
    BadRequestError
        If entity_type is not a valid EntityType enum value (400).
    APIValidationError
        If the name normalizes to an empty string (422).
    ConflictError
        If an active entity with the same normalized name and type already
        exists (409).
    """
    # 1. Convert entity_type string to enum
    try:
        entity_type_enum = EntityType(body.entity_type)
    except ValueError as exc:
        raise BadRequestError(
            message=f"Invalid entity_type: {body.entity_type}",
            details={"entity_type": body.entity_type},
        ) from exc

    # 2. Normalize the name
    normalized_name = _normalizer.normalize(body.name)
    if not normalized_name:
        raise APIValidationError(
            message="Entity name normalizes to an empty string",
            details={"name": body.name},
        )

    # 3. Auto-title-case
    canonical_name = body.name.strip().title()

    # 4. Check for duplicate (same normalized name + type + active status)
    dup_query = select(NamedEntityDB).where(
        NamedEntityDB.canonical_name_normalized == normalized_name,
        NamedEntityDB.entity_type == entity_type_enum.value,
        NamedEntityDB.status == "active",
    )
    dup_result = await session.execute(dup_query)
    existing = dup_result.scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            message=(
                f"An active entity with normalized name '{normalized_name}' "
                f"and type '{entity_type_enum.value}' already exists"
            ),
            details={
                "existing_entity": {
                    "entity_id": str(existing.id),
                    "canonical_name": existing.canonical_name,
                    "entity_type": existing.entity_type,
                    "description": existing.description,
                }
            },
        )

    # 5. Create entity via repository
    entity_create = NamedEntityCreate(
        canonical_name=canonical_name,
        canonical_name_normalized=normalized_name,
        entity_type=entity_type_enum,
        description=body.description,
        status=TagStatus.ACTIVE,
        discovery_method=DiscoveryMethod.USER_CREATED,
        confidence=1.0,
    )
    db_entity = await _entity_repo.create(session, obj_in=entity_create)

    # 6. Create canonical name as first alias
    canonical_alias = EntityAliasCreate(
        entity_id=db_entity.id,
        alias_name=canonical_name,
        alias_name_normalized=normalized_name,
        alias_type=EntityAliasType.NAME_VARIANT,
        occurrence_count=0,
    )
    await _alias_repo.create(session, obj_in=canonical_alias)

    # 7. Create additional aliases, skipping normalized duplicates
    seen_normalized: set[str] = {normalized_name}
    for alias_text in body.aliases:
        alias_normalized = _normalizer.normalize(alias_text)
        if not alias_normalized or alias_normalized in seen_normalized:
            continue
        seen_normalized.add(alias_normalized)
        alias_create = EntityAliasCreate(
            entity_id=db_entity.id,
            alias_name=alias_text.strip(),
            alias_name_normalized=alias_normalized,
            alias_type=EntityAliasType.NAME_VARIANT,
            occurrence_count=0,
        )
        await _alias_repo.create(session, obj_in=alias_create)

    # 8. Commit and return 201
    await session.commit()
    await session.refresh(db_entity)

    return {
        "entity_id": str(db_entity.id),
        "canonical_name": db_entity.canonical_name,
        "entity_type": db_entity.entity_type,
        "description": db_entity.description,
        "alias_count": len(seen_normalized),
    }


# ---------------------------------------------------------------------------
# Entity scan endpoint (Feature 038 API)
# ---------------------------------------------------------------------------

# Lazily-initialised scan service singleton (needs db_manager to be configured).
_scan_service: EntityMentionScanService | None = None


def _get_scan_service() -> EntityMentionScanService:
    """Return the module-level EntityMentionScanService singleton.

    Lazily initialised so that ``db_manager`` has been configured by the
    time the first request arrives.
    """
    global _scan_service
    if _scan_service is None:
        _scan_service = EntityMentionScanService(
            session_factory=db_manager.get_session_factory(),
        )
    return _scan_service


@router.post(
    "/entities/{entity_id}/scan",
    response_model=ScanResultResponse,
    status_code=200,
    summary="Scan transcript segments for mentions of a specific entity",
)
async def scan_entity(
    entity_id: uuid.UUID = Path(..., description="Named entity UUID"),
    request: ScanRequest = Body(default_factory=ScanRequest),
    session: AsyncSession = Depends(get_db),
) -> ScanResultResponse:
    """Trigger an entity mention scan for a single entity.

    Scans transcript segments for mentions of the specified entity using
    PostgreSQL regex matching with word-boundary support.

    Parameters
    ----------
    entity_id : uuid.UUID
        UUID of the named entity to scan.
    request : ScanRequest
        Optional scan configuration (language_code, dry_run, full_rescan).
    session : AsyncSession
        Injected database session.

    Returns
    -------
    ScanResultResponse
        Scan result metrics wrapped in a ``data`` envelope.
    """
    # 1. Validate entity exists
    entity = await session.get(NamedEntityDB, entity_id)
    if entity is None:
        raise NotFoundError(resource_type="Entity", identifier=str(entity_id))

    # 2. Validate entity is active
    if entity.status != "active":
        raise BadRequestError(
            message=f"Entity is not in an active state (status: {entity.status})"
        )

    # 3. Concurrency guard
    guard_key = f"scan:entity:{entity_id}"
    if guard_key in _scans_in_progress:
        raise ConflictError(
            message="A scan is already in progress for this entity"
        )

    _scans_in_progress.add(guard_key)
    try:
        # 4. Run the scan
        service = _get_scan_service()
        result = await service.scan(
            entity_ids=[entity_id],
            language_code=request.language_code,
            dry_run=request.dry_run,
            full_rescan=request.full_rescan,
        )

        # 5. Build response
        return ScanResultResponse(
            data=ScanResultData(
                segments_scanned=result.segments_scanned,
                mentions_found=result.mentions_found,
                mentions_skipped=result.mentions_skipped,
                unique_entities=result.unique_entities,
                unique_videos=result.unique_videos,
                duration_seconds=result.duration_seconds,
                dry_run=result.dry_run,
            )
        )
    finally:
        _scans_in_progress.discard(guard_key)


# ═══════════════════════════════════════════════════════════════════════════
# POST /videos/{video_id}/scan-entities
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/videos/{video_id}/scan-entities",
    response_model=ScanResultResponse,
    status_code=200,
    summary="Scan a single video for entity mentions",
)
async def scan_video_entities(
    video_id: str = Path(..., description="YouTube video ID"),
    request: ScanRequest = Body(default_factory=ScanRequest),
    session: AsyncSession = Depends(get_db),
) -> ScanResultResponse:
    """Trigger an entity mention scan for a single video.

    Validates that the video exists, checks a concurrency guard to prevent
    duplicate scans, then delegates to ``EntityMentionScanService.scan()``
    with the given video ID.

    Parameters
    ----------
    video_id : str
        YouTube video ID (string path parameter).
    request : ScanRequest
        Optional scan parameters (entity_type, language_code, dry_run,
        full_rescan).  All fields default to ``None`` / ``False``.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    ScanResultResponse
        Scan result metrics wrapped in a ``data`` envelope.

    Raises
    ------
    NotFoundError
        If the video does not exist (404).
    ConflictError
        If a scan is already in progress for this video (409).
    """
    # 1. Validate video exists
    video = await session.get(VideoDB, video_id)
    if video is None:
        raise NotFoundError(resource_type="Video", identifier=video_id)

    # 2. Concurrency guard
    guard_key = f"scan:video:{video_id}"
    if guard_key in _scans_in_progress:
        raise ConflictError(
            message="A scan is already in progress for this video",
        )

    _scans_in_progress.add(guard_key)
    try:
        # 3. Run the scan
        service = _get_scan_service()
        result = await service.scan(
            video_ids=[video_id],
            entity_type=request.entity_type,
            language_code=request.language_code,
            dry_run=request.dry_run,
            full_rescan=request.full_rescan,
        )

        # 4. Build response
        return ScanResultResponse(
            data=ScanResultData(
                segments_scanned=result.segments_scanned,
                mentions_found=result.mentions_found,
                mentions_skipped=result.mentions_skipped,
                unique_entities=result.unique_entities,
                unique_videos=result.unique_videos,
                duration_seconds=result.duration_seconds,
                dry_run=result.dry_run,
            )
        )
    finally:
        _scans_in_progress.discard(guard_key)
