"""Entity mention endpoints for video entity summaries and entity-to-videos lookups.

This module handles the REST API endpoints for querying entity mentions
across videos, including per-video entity summaries and reverse lookups
from entity to videos.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_db,
    get_entity_alias_repository,
    get_entity_curation_service,
    get_entity_mention_repository,
    get_named_entity_repository,
    get_video_repository,
    require_auth,
)
from chronovista.api.query_protection import (
    check_rate_limit,
    get_client_id,
    run_with_timeout,
)
from chronovista.api.schemas.entity_mentions import (
    AddEntityTagRequest,
    AddEntityTagResponse,
    AddEntityTagResult,
    ClassifyTagRequest,
    CooccurringEntitiesResponse,
    CooccurringEntity,
    CreateEntityAliasRequest,
    CreateEntityRequest,
    DuplicateCheckResponse,
    EntityAliasSummary,
    EntitySearchResult,
    EntityTagsResponse,
    EntityTagsResult,
    EntityVideoResponse,
    EntityVideoResult,
    ExclusionPatternRequest,
    ExistingEntityInfo,
    LinkedTagSummary,
    ManualAssociationResponse,
    MentionPreview,
    MergedTagSummary,
    PhoneticMatchResponse,
    ScanJobData,
    ScanJobResponse,
    ScanRequest,
    ScanResultData,
    UnlinkResponse,
    UnlinkResult,
    UnMergeRequest,
    UnMergeResponse,
    UnMergeResult,
    UpdateEntityAliasRequest,
    UpdateEntityRequest,
    VideoEntitiesResponse,
    VideoEntitySummary,
)
from chronovista.api.schemas.responses import ApiResponse, PaginationMeta
from chronovista.config.database import db_manager
from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.exceptions import (
    APIValidationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from chronovista.models.correction_actors import ACTOR_USER_LOCAL
from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.entity_enrichment import (
    EntityEnrichment,
    EntityIdentifierView,
    ExternalIdentifier,
)
from chronovista.models.enums import (
    DiscoveryMethod,
    EntityAliasType,
    EntityType,
    EvidenceScope,
    TagStatus,
)
from chronovista.models.named_entity import NamedEntityCreate
from chronovista.repositories.canonical_tag_repository import CanonicalTagRepository
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.repositories.entity_operation_log_repository import (
    EntityOperationLogRepository,
)
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.tag_alias_repository import TagAliasRepository
from chronovista.repositories.tag_operation_log_repository import (
    TagOperationLogRepository,
)
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.entity_curation_service import (
    EntityCurationService,
    EntityNameCollisionError,
    EntityNotFoundError,
    InvalidEntityEditError,
    OperationAlreadyUndoneError,
    OperationNotFoundError,
)
from chronovista.services.entity_enrichment_service import (
    EntityEnrichmentService,
    get_enrichment_service,
)
from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
    ScanResult,
)
from chronovista.services.phonetic_matcher import PhoneticMatcher
from chronovista.services.tag_management import TagManagementService
from chronovista.services.tag_normalization import TagNormalizationService
from chronovista.services.wikidata_client import WikidataClient, WikidataUnavailable

router = APIRouter(dependencies=[Depends(require_auth)])

# Retained handles for detached on-approval enrichment tasks (Feature 068, research D1). A bare
# ``asyncio.create_task`` handle can be garbage-collected mid-flight, silently dropping the
# enrichment; the set + done-callback keep it alive until completion (mirrors ``_scan_tasks``).
_enrichment_tasks: set[asyncio.Task[None]] = set()


def _schedule_enrichment(
    service: EntityEnrichmentService, entity_id: uuid.UUID, qid: str
) -> None:
    """Schedule the on-approval property fetch as a detached, GC-safe background task.

    ``entity_id`` is normalized to a stdlib ``uuid.UUID`` so both call sites (create reads a
    refreshed id; classify reads a pending object's ``uuid_utils.UUID`` default) feed the repository
    WHERE an identical type — avoiding a latent zero-row silent no-op.
    """
    normalized_id = uuid.UUID(str(entity_id))
    task = asyncio.create_task(service.enrich_on_approval(normalized_id, qid))
    _enrichment_tasks.add(task)
    task.add_done_callback(_enrichment_tasks.discard)


# Module-level repository / service instantiation (singleton pattern)
_mention_repo = EntityMentionRepository()

# Ceiling for the appears-with panel (FR-023a). The default of 12 fills a
# column without scrolling; this bound exists so "reveal more" cannot walk the
# list to an unbounded size on a hub entity with hundreds of partners.
MAX_COOCCURRING_LIMIT = 50
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
_entity_curation_service = EntityCurationService(
    named_entity_repo=NamedEntityRepository(),
    operation_log_repo=EntityOperationLogRepository(),
)

logger = logging.getLogger(__name__)

# In-flight scan guard: tracks entity/video scans currently running
_scans_in_progress: set[str] = set()

# Registry of asynchronous scan jobs, keyed by job id. Ephemeral and in-memory:
# jobs do not survive a server restart (acceptable for a single-user tool — a
# lost scan is simply re-run). If durability is ever needed, back this with a
# jobs table.
_scan_jobs: dict[str, ScanJobData] = {}
# Strong references to running background scan tasks so the event loop does not
# garbage-collect them mid-run.
_scan_tasks: set[asyncio.Task[None]] = set()
# Cap on retained jobs to bound memory; oldest terminal jobs are pruned first.
_MAX_SCAN_JOBS = 100

# Rate limit for the duplicate check. This endpoint fires on every keystroke
# with no client-side debounce (useCheckDuplicate is keyed on the name input),
# which is what earns it a limiter — see chronovista.api.query_protection for
# the rule and why it is not applied router-wide.
RATE_LIMIT_DUPLICATE_CHECK = 50

# Storage for rate limit tracking
_duplicate_check_counts: dict[str, list[float]] = defaultdict(list)


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
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
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

    # Parse the comma-separated alias-type exclusion list (request concern).
    excluded_types = (
        [t.strip() for t in exclude_alias_types.split(",") if t.strip()]
        if exclude_alias_types
        else None
    )

    entities, total = await entity_repo.list_filtered(
        session,
        status=effective_status,
        entity_type=type,
        has_mentions=has_mentions,
        search=search,
        search_aliases=search_aliases,
        exclude_alias_types=excluded_types,
        sort=sort,
        skip=offset,
        limit=limit,
    )

    # video_count is the combined association count (mentions ∪ tag ∪ manual),
    # computed once for the whole page by the shared resolver so the list and the
    # detail endpoint can never report different numbers for the same entity
    # (Feature 066, FR-001/FR-002). Previously this read the denormalised
    # mention-only column, which showed 0 for a tag-only entity that the detail
    # reported in full. Batched — one set of queries for the page, not per row.
    counts = await mention_repo.get_association_counts(
        session, [e.id for e in entities]
    )

    data = [
        {
            "entity_id": str(e.id),
            "canonical_name": e.canonical_name,
            "entity_type": e.entity_type,
            "description": e.description,
            "status": e.status,
            "mention_count": e.mention_count or 0,
            "video_count": counts[e.id].total,
            "by_source": counts[e.id].by_source.model_dump(),
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
    video_id: str | None = Query(
        default=None, description="Video ID for is_linked check"
    ),
    limit: int = Query(default=10, ge=1, le=20, description="Max results"),
    session: AsyncSession = Depends(get_db),
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
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
    results = await mention_repo.search_entities(
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
    video_repo: VideoRepository = Depends(get_video_repository),
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
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
    if not await video_repo.exists_by_video_id(session, video_id):
        raise NotFoundError(resource_type="Video", identifier=video_id)

    # Fetch entity associations from the shared resolver — entities linked
    # through ANY source (tag-only and manual included), matching the entity
    # detail's membership by construction (US2 / FR-005 / FR-006).
    summaries = await mention_repo.get_video_entity_associations(
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
    type: str = Query(
        ..., description="Entity type (person, organization, place, etc.)"
    ),
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
    client_id = get_client_id(request)
    is_allowed, retry_after = check_rate_limit(
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
    "/entities/wikidata-candidates",
    status_code=200,
    summary="Search Wikidata for entity-creation grounding candidates",
)
async def wikidata_candidates(
    name: str = Query(..., min_length=1, description="Name to search Wikidata for"),
    entity_type: str = Query(
        ..., description="Entity type being assigned (for the cross-check)"
    ),
    limit: int = Query(5, ge=1, le=10, description="Max candidates (default 5)"),
) -> dict[str, Any]:
    """Return a ranked Wikidata shortlist for the create-time approval modal (US3).

    Registered BEFORE ``/entities/{entity_id}`` so the static path is not captured as an id.

    Degrades gracefully (Constitution VIII, FR-012/015): a reachable knowledge base with no
    match returns ``candidates: []`` with ``unavailable: false`` (a benign "no match"); a
    timeout / transport failure returns ``candidates: []`` with ``unavailable: true`` (a soft
    failure) — never a 5xx that would block the modal. The two states are distinct so the
    frontend can message them differently.
    """
    client = WikidataClient()
    try:
        candidates = await client.search_candidates(name, entity_type, limit=limit)
        unavailable = False
    except WikidataUnavailable:
        candidates = []
        unavailable = True

    return {
        "data": {
            "candidates": [c.model_dump() for c in candidates],
            "unavailable": unavailable,
        }
    }


def _identifier_url(source: str, identifier: str) -> str:
    """Build a public knowledge-base link for an identifier (Feature 067, FR-010)."""
    if source == "wikidata":
        return f"https://www.wikidata.org/wiki/{identifier}"
    if source == "dbpedia":
        return (
            identifier
            if identifier.startswith("http")
            else f"http://dbpedia.org/resource/{identifier}"
        )
    return identifier


def _build_enrichment(
    external_ids: dict[str, Any] | None, properties: dict[str, Any] | None
) -> EntityEnrichment:
    """Assemble the viewer-facing enrichment block from the stored columns (US2).

    Tolerates BOTH shapes of ``external_ids`` — the legacy bare string (e.g.
    ``{"wikidata": "Q42"}``) and the Feature-067 structured object (``{"wikidata":
    {"id": "Q42", "verified": true, "status": "confirmed"}}``) — so the coordinated shape
    change does not break the detail page during the transition (ST-003). A recorded negative
    (``id`` is null / ``status`` absent) yields no viewer-facing link, and the backend-only
    ``status`` / ``link_provenance`` are never surfaced (FR-010, US2 clarification).

    Non-dict inputs (e.g. a missing column or a test double) coerce to empty rather than
    crashing the endpoint — the block simply renders "not grounded".
    """
    if not isinstance(external_ids, dict):
        external_ids = {}
    if not isinstance(properties, dict):
        properties = {}
    identifiers: list[EntityIdentifierView] = []
    for source, value in external_ids.items():
        if isinstance(value, str):
            ident_id: str | None = value
            verified = False
        elif isinstance(value, dict):
            raw_id = value.get("id")
            ident_id = raw_id if isinstance(raw_id, str) else None
            verified = bool(value.get("verified", False))
        else:
            continue
        if not ident_id:
            continue  # absent/negative — not a link
        identifiers.append(
            EntityIdentifierView(
                source=source,
                id=ident_id,
                url=_identifier_url(source, ident_id),
                verified=verified,
            )
        )

    props = properties or {}
    grounded = bool(props) or bool(identifiers)
    return EntityEnrichment(
        grounded=grounded, properties=props, identifiers=identifiers
    )


@router.get(
    "/entities/{entity_id}",
    status_code=200,
    summary="Get entity detail",
)
async def get_entity_detail(
    entity_id: str = Path(..., description="Named entity UUID"),
    session: AsyncSession = Depends(get_db),
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
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

    entity = await entity_repo.get_with_aliases(session, parsed_entity_id)
    if entity is None:
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # Filter out asr_error aliases — those are internal detection noise and
    # are not useful to display to users. Genuine alias types are:
    # name_variant, abbreviation, nickname, translated_name, former_name.
    genuine_aliases = [
        EntityAliasSummary(
            id=a.id,
            alias_name=a.alias_name,
            alias_type=a.alias_type,
            occurrence_count=a.occurrence_count,
            case_sensitive=a.case_sensitive,
        )
        for a in entity.aliases
        if a.alias_type != "asr_error"
    ]
    # Sort by occurrence count descending, then alphabetically for stability
    genuine_aliases.sort(key=lambda a: (-a.occurrence_count, a.alias_name))

    # Combined association count + per-source breakdown from the shared resolver,
    # the same call the list endpoint makes, so the two agree by construction
    # (Feature 066, FR-001/FR-002/FR-004). Supersedes the single-purpose
    # get_combined_video_count.
    association = (
        await mention_repo.get_association_counts(session, [parsed_entity_id])
    )[parsed_entity_id]

    return {
        "data": {
            "entity_id": str(entity.id),
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type,
            "description": entity.description,
            "status": entity.status,
            "mention_count": entity.mention_count or 0,
            "video_count": association.total,
            "by_source": association.by_source.model_dump(),
            "aliases": [a.model_dump() for a in genuine_aliases],
            "exclusion_patterns": list(entity.exclusion_patterns or []),
            "enrichment": _build_enrichment(
                entity.external_ids, entity.properties
            ).model_dump(),
        }
    }


@router.get(
    "/entities/{entity_id}/co-occurring",
    response_model=CooccurringEntitiesResponse,
    status_code=200,
    summary="Entities that share videos with this entity",
)
async def get_cooccurring_entities(
    entity_id: str = Path(..., description="Named entity UUID"),
    limit: int = Query(
        default=12,
        ge=1,
        le=MAX_COOCCURRING_LIMIT,
        description=(
            "Maximum partners to return. Bounded rather than unbounded: a "
            "handful of entities co-occur with hundreds of others, and an "
            "unbounded list would be unusable and slow (FR-023a)."
        ),
    ),
    min_evidence: EvidenceScope = Query(
        EvidenceScope.ANY,
        description=(
            "Which mentions count as co-occurrence. Must match the scope of "
            "the surrounding view, or the count shown and the intersection it "
            "opens will disagree (FR-024a)."
        ),
    ),
    session: AsyncSession = Depends(get_db),
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
) -> CooccurringEntitiesResponse:
    """Get the entities most often appearing alongside this one.

    Powers the "appears with" panel on the entity detail page. Each partner's
    ``shared_video_count`` equals the total the videos list reports when
    filtered to that pair under the same evidence scope (FR-024b).

    Parameters
    ----------
    entity_id : str
        Named entity UUID (string representation).
    limit : int
        Maximum partners returned, bounded by ``MAX_COOCCURRING_LIMIT``
        (default 12).
    min_evidence : EvidenceScope
        Evidence scope to compute co-occurrence under.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    CooccurringEntitiesResponse
        Partners ordered by shared-video count descending, tiebroken by id.

    Raises
    ------
    NotFoundError
        If the entity does not exist (404).
    """
    try:
        parsed_entity_id = uuid.UUID(entity_id)
    except ValueError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc

    if not await entity_repo.exists(session, parsed_entity_id):
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # MAX_COOCCURRING_LIMIT bounds the result SIZE, not the query cost: the
    # scan is over the entity's whole co-occurrence set before the limit
    # applies. Measured at 923 ms on the most connected entity.
    partners = await run_with_timeout(
        mention_repo.get_cooccurring_entities(
            session,
            entity_id=parsed_entity_id,
            limit=limit,
            evidence_scope=min_evidence,
        ),
        operation="co-occurring entities",
        session=session,
    )

    # An entity with no co-occurrences returns an empty list, not an error
    # (FR-024): "nothing appears alongside this" is an answer, not a failure.
    return CooccurringEntitiesResponse(
        data=[CooccurringEntity(**partner) for partner in partners]
    )


# Provenance values the association filter accepts (FR-007) — the
# where-an-association-came-from axis. Detection method (rule_match, spacy_ner,
# ...) is deliberately NOT here: provenance and detection method are separate
# axes and detection method is not a user-facing filter dimension (FR-009).
_PROVENANCE_FILTER_VALUES = frozenset(
    {"manual", "transcript", "title", "description", "tag"}
)


def parse_provenance_filter(raw: list[str] | None) -> list[str] | None:
    """Normalise the multi-select provenance query param (Feature 066 US3).

    Accepts both the repeated (``?source=tag&source=title``) and the
    comma-separated (``?source=tag,title``) forms, so a single legacy
    ``?source=tag`` keeps working as "tag only" — the change is arity, not a
    break. Returns the deduplicated, sorted list of requested sources, or
    ``None`` when nothing is selected, which downstream reads as "all sources"
    (clarify A4).

    Parameters
    ----------
    raw : list[str] | None
        The raw ``source`` query values as parsed by FastAPI.

    Returns
    -------
    list[str] | None
        Sorted, deduplicated provenance values, or ``None`` for "all".

    Raises
    ------
    APIValidationError
        If any value is not a provenance source. Detection-method values are
        rejected here — provenance and detection method are separate axes
        (FR-009).
    """
    if not raw:
        return None
    values: list[str] = [
        token for item in raw for piece in item.split(",") if (token := piece.strip())
    ]
    if not values:
        return None
    invalid = sorted({v for v in values if v not in _PROVENANCE_FILTER_VALUES})
    if invalid:
        raise APIValidationError(
            message=(
                f"Invalid source value(s): {', '.join(invalid)}. "
                f"Must be one of: {', '.join(sorted(_PROVENANCE_FILTER_VALUES))}"
            ),
            details={"field": "source", "invalid_values": invalid},
        )
    return sorted(set(values))


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
    source: list[str] | None = Query(
        default=None,
        description=(
            "Filter videos by association provenance. Multi-select over "
            "{manual, transcript, title, description, tag}; repeatable "
            "(?source=tag&source=title) or comma-separated (?source=tag,title). "
            "Multiple values are unioned; a single value shows that source "
            "only; omitted returns all sources. Provenance only — not detection "
            "method."
        ),
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
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
    source : list[str] | None
        Optional multi-select provenance filter over {manual, transcript,
        title, description, tag}; repeatable or comma-separated. Values are
        unioned; omitted returns all sources. Provenance, not detection method.
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
    if not await entity_repo.exists(session, parsed_entity_id):
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # Normalise the multi-select provenance filter (raises on invalid values,
    # including detection-method values, which are a separate axis — FR-009).
    source_filter = parse_provenance_filter(source)

    # Fetch paginated video list from repository
    # Merges mention-derived and tag-derived video sets, then filters by source
    # in Python after the query — cost scales with the entity's whole video
    # population, not with the requested page.
    results, total = await run_with_timeout(
        mention_repo.get_entity_video_list(
            session,
            entity_id=parsed_entity_id,
            language_code=language_code,
            source_filter=source_filter,
            limit=limit,
            offset=offset,
        ),
        operation="entity video list",
        session=session,
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
            description_context=r.get("description_context"),
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
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    alias_repo: EntityAliasRepository = Depends(get_entity_alias_repository),
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

    # Verify the entity exists
    if not await entity_repo.exists(session, parsed_entity_id):
        raise NotFoundError(resource_type="Entity", identifier=entity_id)

    # Normalize alias name
    normalized_alias = _normalizer.normalize(body.alias_name)
    if normalized_alias is None:
        raise ConflictError(
            message="Alias name normalizes to an empty string",
            details={"alias_name": body.alias_name},
        )

    # Check for duplicate (same entity + same normalized name)
    existing_alias = await alias_repo.get_by_entity_and_normalized(
        session, parsed_entity_id, normalized_alias
    )
    if existing_alias is not None:
        raise ConflictError(
            message=(
                f"Already covered by the existing alias "
                f"'{existing_alias.alias_name}' — accents and case are ignored "
                f"when matching, so this variant is treated as the same."
            ),
            details={
                "entity_id": entity_id,
                "alias_name": body.alias_name,
                "existing_alias_name": existing_alias.alias_name,
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
    db_alias = await alias_repo.create(session, obj_in=alias_create)
    await session.commit()
    await session.refresh(db_alias)

    return {
        "data": EntityAliasSummary(
            id=db_alias.id,
            alias_name=db_alias.alias_name,
            alias_type=db_alias.alias_type,
            occurrence_count=db_alias.occurrence_count,
            case_sensitive=db_alias.case_sensitive,
        ).model_dump()
    }


# ═══════════════════════════════════════════════════════════════════════════
# PATCH /entities/{entity_id}/aliases/{alias_id}
# ═══════════════════════════════════════════════════════════════════════════


@router.patch(
    "/entities/{entity_id}/aliases/{alias_id}",
    status_code=200,
    summary="Update an alias's matching behaviour",
)
async def update_entity_alias(
    entity_id: uuid.UUID = Path(..., description="Named entity UUID"),
    alias_id: uuid.UUID = Path(..., description="Alias UUID"),
    body: UpdateEntityAliasRequest = Body(...),
    session: AsyncSession = Depends(get_db),
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    alias_repo: EntityAliasRepository = Depends(get_entity_alias_repository),
) -> dict[str, Any]:
    """Set whether an alias matches case-sensitively.

    Changing the flag does not retroactively alter existing mentions — matching
    rules are applied when a scan runs. A caller that wants the change
    reflected must follow this with a full rescan of the entity; an incremental
    scan only adds, so it would never retract the mentions the previous rule
    produced.

    Parameters
    ----------
    entity_id : uuid.UUID
        Named entity that owns the alias.
    alias_id : uuid.UUID
        Alias to update.
    body : UpdateEntityAliasRequest
        New matching behaviour.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        The updated alias wrapped in a ``data`` envelope.

    Raises
    ------
    NotFoundError
        If the entity does not exist, or the alias does not exist on it (404).
    """
    if not await entity_repo.exists(session, entity_id):
        raise NotFoundError(resource_type="Entity", identifier=str(entity_id))

    alias = await alias_repo.get(session, alias_id)
    # The entity_id check is what makes the path meaningful: without it, an
    # alias could be updated through any entity's URL, and a 404 for a
    # mismatched pair would instead silently succeed.
    if alias is None or alias.entity_id != entity_id:
        raise NotFoundError(resource_type="Alias", identifier=str(alias_id))

    alias.case_sensitive = body.case_sensitive
    await session.commit()
    await session.refresh(alias)

    return {
        "data": EntityAliasSummary(
            id=alias.id,
            alias_name=alias.alias_name,
            alias_type=alias.alias_type,
            occurrence_count=alias.occurrence_count,
            case_sensitive=alias.case_sensitive,
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
    matches = await run_with_timeout(
        matcher.match_entity(
            entity_id=entity_id,
            session=session,
            threshold=threshold,
        ),
        operation="phonetic matches",
        session=session,
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
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
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

    # Look up entity (mutated below, so fetch the row, not just existence)
    entity = await entity_repo.get(session, parsed_entity_id)
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
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
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

    # Look up entity (mutated below, so fetch the row, not just existence)
    entity = await entity_repo.get(session, parsed_entity_id)
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
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
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

    mention = await mention_repo.create_manual_association(
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
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
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

    await mention_repo.delete_manual_association(
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
    enrichment_service: EntityEnrichmentService = Depends(get_enrichment_service),
) -> dict[str, Any]:
    """Classify an existing canonical tag to create or link a named entity.

    Delegates to ``TagManagementService.classify()`` which handles entity
    creation/linking and alias management. Maps service-layer ``ValueError``
    exceptions to appropriate HTTP status codes.

    Parameters
    ----------
    body : ClassifyTagRequest
        Request body with normalized_form and either entity_type (to create a
        new entity) or link_entity_id (to attach the tag to an existing one,
        inferring the type from it). Optional description and display_name
        apply to the creation case only.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Created/linked entity details with alias count and operation ID.

    Raises
    ------
    NotFoundError
        If the canonical tag is not found or inactive, or if link_entity_id
        names no entity (404).
    ConflictError
        If the tag is already classified as an entity, or link_entity_id
        names an entity that is not active (409).
    APIValidationError
        If the request is otherwise invalid (400).
    """
    # Resolve the link target first, when there is one. The service checks the
    # entity too, but reports both failures as ValueError("... not found") /
    # ("... not active"), and the mapping below would attribute either to the
    # CanonicalTag — a 404 naming the wrong resource. Resolving here also
    # supplies the entity_type when the caller omitted it.
    effective_entity_type = body.entity_type
    if body.link_entity_id is not None:
        target_entity = await session.get(NamedEntityDB, body.link_entity_id)
        if target_entity is None:
            raise NotFoundError(
                resource_type="NamedEntity",
                identifier=str(body.link_entity_id),
            )
        if target_entity.status != "active":
            raise ConflictError(
                message=(
                    f"Entity '{target_entity.canonical_name}' is not active "
                    f"(status: {target_entity.status})."
                ),
                details={"entity_id": str(target_entity.id)},
            )
        if effective_entity_type is None:
            effective_entity_type = target_entity.entity_type
        elif effective_entity_type != target_entity.entity_type:
            # The service writes the caller's type onto the tag while pointing
            # it at this entity, leaving tag.entity_type contradicting the type
            # of the entity it links to. The target owns its own type; a
            # disagreement is a stale client, not an instruction.
            raise ConflictError(
                message=(
                    f"entity_type '{effective_entity_type}' does not match "
                    f"entity '{target_entity.canonical_name}', which is a "
                    f"'{target_entity.entity_type}'. Omit entity_type to use "
                    f"the entity's own type."
                ),
                details={
                    "requested_entity_type": effective_entity_type,
                    "entity_entity_type": target_entity.entity_type,
                    "entity_id": str(target_entity.id),
                },
            )

    try:
        entity_type_enum = EntityType(effective_entity_type)
    except ValueError as exc:
        raise BadRequestError(
            message=f"Invalid entity_type: {effective_entity_type}",
            details={"entity_type": effective_entity_type},
        ) from exc

    # Grounding (US3): a user-approved identifier is applied only when classify creates a NEW
    # entity from the tag (not when it links/matches an existing one). Same structured shape as
    # the standalone create path.
    grounding_external_ids: dict[str, Any] = {}
    if body.approved_identifier is not None:
        grounding_external_ids[body.approved_identifier.source] = ExternalIdentifier(
            id=body.approved_identifier.id,
            verified=True,
            status="verified",
        ).model_dump()

    try:
        result = await _tag_mgmt_service.classify(
            session,
            body.normalized_form,
            entity_type_enum,
            description=body.description,
            auto_case=True,
            display_name=body.display_name,
            link_entity_id=body.link_entity_id,
            external_ids=grounding_external_ids,
            actor=ACTOR_USER_LOCAL,
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

            # The service's message ends "Use --force to override." — correct
            # for the CLI, meaningless over HTTP, where no such flag exists.
            # Clients surface `detail` directly to users, so rewrite it here
            # and name the entity holding the tag instead, which is the part
            # someone can act on.
            claimed_by = (
                existing_entity_data["canonical_name"] if existing_entity_data else None
            )
            conflict_message = (
                f"Tag '{body.normalized_form}' is already linked to " f"'{claimed_by}'."
                if claimed_by
                else (
                    f"Tag '{body.normalized_form}' is already classified and "
                    f"cannot be reassigned here."
                )
            )
            raise ConflictError(
                message=conflict_message,
                details=(
                    {"existing_entity": existing_entity_data}
                    if existing_entity_data
                    else None
                ),
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

    # The entity the tag now resolves to — the newly created one OR a linked existing one.
    resolved_entity_id: uuid.UUID | None = None
    if tag is not None and tag.entity_id is not None:
        entity = await session.get(NamedEntityDB, tag.entity_id)
        if entity is not None:
            entity_id_str = str(entity.id)
            canonical_name = entity.canonical_name
            description = entity.description
            resolved_entity_id = entity.id

    await session.commit()

    # Fetch curated properties in the background ONLY when classify CREATED a new grounded entity
    # (FR-005). Linking/matching an existing entity never triggers a fetch (FR-009) — enforced by the
    # ``result.entity_created`` guard, so a linked (not created) entity never fires.
    if (
        body.approved_identifier is not None
        and result.entity_created
        and resolved_entity_id is not None
    ):
        _schedule_enrichment(
            enrichment_service, resolved_entity_id, body.approved_identifier.id
        )

    return {
        "entity_id": entity_id_str,
        "canonical_name": canonical_name,
        "entity_type": result.entity_type,
        "description": description,
        "alias_count": result.entity_alias_count,
        "entity_created": result.entity_created,
        "grounded": bool(grounding_external_ids) and result.entity_created,
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
    enrichment_service: EntityEnrichmentService = Depends(get_enrichment_service),
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    alias_repo: EntityAliasRepository = Depends(get_entity_alias_repository),
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

    # 3. Store the provided name verbatim (only trim whitespace) — casing is a
    # human decision and must not be flattened (Feature 057, FR-012).
    canonical_name = body.name.strip()

    # 4. Check for duplicate (same normalized name + type + active status)
    existing = await entity_repo.find_active_by_normalized_and_type(
        session, normalized_name, entity_type_enum.value
    )
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

    # 5. Create entity via repository. If the user approved a knowledge-base match, ground the
    # entity with a human-verified identifier (US3, FR-014); otherwise it is created ungrounded
    # (grounding never blocks creation — FR-012). No DBpedia call here; that IRI is filled by
    # the back-fill (spec Non-Goals).
    external_ids: dict[str, Any] = {}
    if body.approved_identifier is not None:
        external_ids[body.approved_identifier.source] = ExternalIdentifier(
            id=body.approved_identifier.id,
            verified=True,
            status="verified",
        ).model_dump()

    entity_create = NamedEntityCreate(
        canonical_name=canonical_name,
        canonical_name_normalized=normalized_name,
        entity_type=entity_type_enum,
        description=body.description,
        status=TagStatus.ACTIVE,
        discovery_method=DiscoveryMethod.USER_CREATED,
        confidence=1.0,
        external_ids=external_ids,
    )
    db_entity = await entity_repo.create(session, obj_in=entity_create)

    # 6. Create canonical name as first alias
    canonical_alias = EntityAliasCreate(
        entity_id=db_entity.id,
        alias_name=canonical_name,
        alias_name_normalized=normalized_name,
        alias_type=EntityAliasType.NAME_VARIANT,
        occurrence_count=0,
    )
    await alias_repo.create(session, obj_in=canonical_alias)

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
        await alias_repo.create(session, obj_in=alias_create)

    # 8. Commit and return 201
    await session.commit()
    await session.refresh(db_entity)

    # 9. If grounded, fetch the entity's curated Wikidata properties in the background so a fresh
    # grounded entity is enriched moments later (Feature 068, FR-005). Detached — the create action
    # returns immediately (SC-003); a failed fetch leaves the entity grounded (FR-006).
    if body.approved_identifier is not None:
        _schedule_enrichment(
            enrichment_service, db_entity.id, body.approved_identifier.id
        )

    return {
        "entity_id": str(db_entity.id),
        "canonical_name": db_entity.canonical_name,
        "entity_type": db_entity.entity_type,
        "description": db_entity.description,
        "alias_count": len(seen_normalized),
        "grounded": bool(external_ids),
    }


# ═══════════════════════════════════════════════════════════════════════════
# PATCH /entities/{entity_id} — Edit entity name / description (Feature 057)
# ═══════════════════════════════════════════════════════════════════════════


@router.patch(
    "/entities/{entity_id}",
    status_code=200,
    summary="Edit an entity's display name, description, and/or type",
)
async def update_entity(
    entity_id: str = Path(..., description="Named entity UUID"),
    body: UpdateEntityRequest = Body(...),
    session: AsyncSession = Depends(get_db),
    curation_service: EntityCurationService = Depends(get_entity_curation_service),
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
) -> dict[str, Any]:
    """Edit a named entity's display name, description, and/or type.

    Delegates to ``EntityCurationService.update_entity`` which validates,
    recomputes the normalized identity together with the name (INV-1),
    pre-checks same-type uniqueness, persists the change, and appends an
    audit/rollback log entry attributed to the web actor. The entity's tag(s)
    and aliases are never modified (FR-003, FR-015).

    Parameters
    ----------
    entity_id : str
        Named entity UUID (string representation).
    body : UpdateEntityRequest
        Optional ``canonical_name`` / ``description`` / ``entity_type``
        (at least one required).
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Updated entity detail wrapped in a ``data`` envelope.

    Raises
    ------
    BadRequestError
        Invalid input (empty / normalizes-to-empty name) — 400.
    NotFoundError
        The entity does not exist — 404.
    ConflictError
        The resulting ``(normalized name, entity type)`` pair collides with an
        existing entity — 409.
    """
    try:
        parsed_entity_id = uuid.UUID(entity_id)
    except ValueError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc

    try:
        updated = await curation_service.update_entity(
            session,
            parsed_entity_id,
            canonical_name=body.canonical_name,
            description=body.description,
            entity_type=(
                body.entity_type.value if body.entity_type is not None else None
            ),
            actor=ACTOR_USER_LOCAL,
        )
    except EntityNotFoundError as exc:
        raise NotFoundError(resource_type="Entity", identifier=entity_id) from exc
    except InvalidEntityEditError as exc:
        raise BadRequestError(
            message=str(exc), details={"entity_id": entity_id}
        ) from exc
    except EntityNameCollisionError as exc:
        raise ConflictError(message=str(exc), details={"entity_id": entity_id}) from exc

    await session.commit()
    return await get_entity_detail(
        str(updated.id),
        session,
        entity_repo=entity_repo,
        mention_repo=mention_repo,
    )


@router.post(
    "/entities/operations/{operation_id}/undo",
    status_code=200,
    summary="Undo a previously logged entity edit",
)
async def undo_entity_operation(
    operation_id: uuid.UUID = Path(..., description="Entity operation ID to undo"),
    session: AsyncSession = Depends(get_db),
    curation_service: EntityCurationService = Depends(get_entity_curation_service),
    entity_repo: NamedEntityRepository = Depends(get_named_entity_repository),
    mention_repo: EntityMentionRepository = Depends(get_entity_mention_repository),
) -> dict[str, Any]:
    """Undo an entity name/description edit, restoring the previous values.

    Delegates to ``EntityCurationService.undo_operation`` (mirrors the tag
    ``operations/{id}/undo`` contract). Restores the ``before`` snapshot,
    re-checks uniqueness on a restored name, and marks the log entry rolled
    back. An already-rolled-back entry cannot be undone again.

    Parameters
    ----------
    operation_id : uuid.UUID
        The entity operation log entry to undo.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    dict
        Restored entity detail wrapped in a ``data`` envelope.

    Raises
    ------
    NotFoundError
        The operation (or its entity) does not exist — 404.
    ConflictError
        Already rolled back, or restoring would collide — 409.
    """
    try:
        restored = await curation_service.undo_operation(
            session,
            operation_id,
            actor=ACTOR_USER_LOCAL,
        )
    except OperationNotFoundError as exc:
        raise NotFoundError(
            resource_type="EntityOperation", identifier=str(operation_id)
        ) from exc
    except EntityNotFoundError as exc:
        raise NotFoundError(
            resource_type="Entity", identifier=str(exc.entity_id)
        ) from exc
    except InvalidEntityEditError as exc:
        raise BadRequestError(
            message=str(exc), details={"operation_id": str(operation_id)}
        ) from exc
    except (OperationAlreadyUndoneError, EntityNameCollisionError) as exc:
        raise ConflictError(
            message=str(exc), details={"operation_id": str(operation_id)}
        ) from exc

    await session.commit()
    return await get_entity_detail(
        str(restored.id),
        session,
        entity_repo=entity_repo,
        mention_repo=mention_repo,
    )


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


async def _dispatch_scan(
    *,
    service: EntityMentionScanService,
    sources: list[str],
    entity_ids: list[uuid.UUID] | None = None,
    video_ids: list[str] | None = None,
    entity_type: str | None = None,
    language_code: str | None = None,
    dry_run: bool = False,
    full_rescan: bool = False,
) -> ScanResult:
    """Dispatch scan calls based on the requested sources.

    If ``"transcript"`` is in *sources*, calls ``service.scan()``.
    If ``"title"`` or ``"description"`` is in *sources*, calls
    ``service.scan_metadata()`` with the metadata sources.
    When both are requested the two results are merged.

    Parameters
    ----------
    service : EntityMentionScanService
        Scan service singleton.
    sources : list[str]
        Validated list of source values.
    entity_ids : list[uuid.UUID] | None
        Restrict scanning to these entities.
    video_ids : list[str] | None
        Restrict scanning to these videos.
    entity_type : str | None
        Restrict scanning to entities of this type.
    language_code : str | None
        Restrict scanning to segments in this language.
    dry_run : bool
        Preview matches without writing to the database.
    full_rescan : bool
        Delete existing mentions in scope before scanning.

    Returns
    -------
    ScanResult
        Merged scan result from all dispatched calls.
    """
    results: list[ScanResult] = []

    if "transcript" in sources:
        transcript_result = await service.scan(
            entity_ids=entity_ids,
            video_ids=video_ids,
            entity_type=entity_type,
            language_code=language_code,
            dry_run=dry_run,
            full_rescan=full_rescan,
        )
        results.append(transcript_result)

    metadata_sources = [s for s in sources if s in ("title", "description")]
    if metadata_sources:
        metadata_result = await service.scan_metadata(
            sources=metadata_sources,
            entity_ids=entity_ids,
            video_ids=video_ids,
            entity_type=entity_type,
            language_code=language_code,
            dry_run=dry_run,
            full_rescan=full_rescan,
        )
        results.append(metadata_result)

    if not results:
        # Should not happen with validated sources, but defensive
        return ScanResult(dry_run=dry_run)

    if len(results) == 1:
        return results[0]

    return _merge_scan_results(results)


def _merge_scan_results(results: list[ScanResult]) -> ScanResult:
    """Merge multiple :class:`ScanResult` instances into one.

    Numeric fields are summed.  ``dry_run`` is taken from the first result.

    Parameters
    ----------
    results : list[ScanResult]
        Two or more results to merge.

    Returns
    -------
    ScanResult
        Combined result.
    """
    merged = ScanResult(dry_run=results[0].dry_run)
    for r in results:
        merged.segments_scanned += r.segments_scanned
        merged.mentions_found += r.mentions_found
        merged.mentions_skipped += r.mentions_skipped
        merged.unique_entities += r.unique_entities
        merged.unique_videos += r.unique_videos
        merged.duration_seconds += r.duration_seconds
        merged.failed_batches += r.failed_batches
        merged.skipped_longest_match += r.skipped_longest_match
        merged.skipped_exclusion_pattern += r.skipped_exclusion_pattern
    return merged


def _scan_result_to_data(result: ScanResult) -> ScanResultData:
    """Convert a service-layer :class:`ScanResult` into API ``ScanResultData``."""
    return ScanResultData(
        segments_scanned=result.segments_scanned,
        mentions_found=result.mentions_found,
        mentions_skipped=result.mentions_skipped,
        unique_entities=result.unique_entities,
        unique_videos=result.unique_videos,
        duration_seconds=result.duration_seconds,
        dry_run=result.dry_run,
    )


def _prune_scan_jobs() -> None:
    """Bound the job registry by dropping the oldest terminal (finished) jobs.

    Running jobs are never pruned. Relies on ``dict`` insertion order so the
    oldest-registered finished jobs are removed first.
    """
    if len(_scan_jobs) <= _MAX_SCAN_JOBS:
        return
    for job_id in list(_scan_jobs.keys()):
        if len(_scan_jobs) <= _MAX_SCAN_JOBS:
            break
        if _scan_jobs[job_id].status != "running":
            del _scan_jobs[job_id]


async def _run_scan_job(
    job_id: str,
    guard_key: str,
    *,
    sources: list[str],
    entity_ids: list[uuid.UUID] | None = None,
    video_ids: list[str] | None = None,
    entity_type: str | None = None,
    language_code: str | None = None,
    dry_run: bool = False,
    full_rescan: bool = False,
) -> None:
    """Run a scan in the background and record the outcome on its job.

    Never raises: any failure is captured on the job's ``status``/``error`` so
    the polling client can observe it. Clears the in-flight guard when done.
    """
    job = _scan_jobs[job_id]
    try:
        service = _get_scan_service()
        result = await _dispatch_scan(
            service=service,
            sources=sources,
            entity_ids=entity_ids,
            video_ids=video_ids,
            entity_type=entity_type,
            language_code=language_code,
            dry_run=dry_run,
            full_rescan=full_rescan,
        )
        job.result = _scan_result_to_data(result)
        job.status = "succeeded"
    except Exception as exc:  # noqa: BLE001 - surface any failure via the job
        logger.exception("Scan job %s failed", job_id)
        job.status = "failed"
        job.error = str(exc)
    finally:
        job.finished_at = datetime.now(UTC)
        _scans_in_progress.discard(guard_key)


def _launch_scan_job(
    *,
    kind: Literal["entity", "video"],
    target_id: str,
    guard_key: str,
    sources: list[str],
    entity_ids: list[uuid.UUID] | None = None,
    video_ids: list[str] | None = None,
    entity_type: str | None = None,
    language_code: str | None = None,
    dry_run: bool = False,
    full_rescan: bool = False,
) -> ScanJobData:
    """Register a scan job and start it as a background task.

    The caller must have validated inputs and added ``guard_key`` to
    ``_scans_in_progress``; the background task clears the guard on completion.
    Returns the freshly-created job for the ``202`` response body.
    """
    job_id = str(uuid.uuid4())
    job = ScanJobData(
        job_id=job_id,
        kind=kind,
        target_id=target_id,
        status="running",
        result=None,
        error=None,
        started_at=datetime.now(UTC),
        finished_at=None,
    )
    _scan_jobs[job_id] = job
    _prune_scan_jobs()

    task = asyncio.create_task(
        _run_scan_job(
            job_id,
            guard_key,
            sources=sources,
            entity_ids=entity_ids,
            video_ids=video_ids,
            entity_type=entity_type,
            language_code=language_code,
            dry_run=dry_run,
            full_rescan=full_rescan,
        )
    )
    _scan_tasks.add(task)
    task.add_done_callback(_scan_tasks.discard)
    return job


@router.post(
    "/entities/{entity_id}/scan",
    response_model=ScanJobResponse,
    status_code=202,
    summary="Start an entity mention scan for a specific entity",
)
async def scan_entity(
    entity_id: uuid.UUID = Path(..., description="Named entity UUID"),
    request: ScanRequest = Body(default_factory=ScanRequest),
    session: AsyncSession = Depends(get_db),
) -> ScanJobResponse:
    """Launch an asynchronous entity mention scan for a single entity.

    Scanning transcript segments (and optionally titles/descriptions) can take
    minutes on a large corpus, so this endpoint validates the request, starts
    the scan as a background job, and returns ``202`` with a job id. Poll
    ``GET /scan-jobs/{job_id}`` for progress and the final result.

    Parameters
    ----------
    entity_id : uuid.UUID
        UUID of the named entity to scan.
    request : ScanRequest
        Optional scan configuration (sources, language_code, dry_run,
        full_rescan).
    session : AsyncSession
        Injected database session (used only for validation).

    Returns
    -------
    ScanJobResponse
        The created scan job (status ``"running"``) wrapped in ``data``.
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
        raise ConflictError(message="A scan is already in progress for this entity")

    # 4. Launch the scan in the background and return the job (202).
    _scans_in_progress.add(guard_key)
    try:
        job = _launch_scan_job(
            kind="entity",
            target_id=str(entity_id),
            guard_key=guard_key,
            sources=request.sources or ["transcript"],
            entity_ids=[entity_id],
            entity_type=request.entity_type,
            language_code=request.language_code,
            dry_run=request.dry_run,
            full_rescan=request.full_rescan,
        )
    except Exception:
        # If we failed to even start the task, don't leak the guard.
        _scans_in_progress.discard(guard_key)
        raise
    return ScanJobResponse(data=job)


# ═══════════════════════════════════════════════════════════════════════════
# POST /videos/{video_id}/scan-entities
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/videos/{video_id}/scan-entities",
    response_model=ScanJobResponse,
    status_code=202,
    summary="Start an entity mention scan for a single video",
)
async def scan_video_entities(
    video_id: str = Path(..., description="YouTube video ID"),
    request: ScanRequest = Body(default_factory=ScanRequest),
    session: AsyncSession = Depends(get_db),
) -> ScanJobResponse:
    """Launch an asynchronous entity mention scan for a single video.

    Validates that the video exists, checks a concurrency guard to prevent
    duplicate scans, starts the scan as a background job, and returns ``202``
    with a job id. Poll ``GET /scan-jobs/{job_id}`` for progress and result.

    Parameters
    ----------
    video_id : str
        YouTube video ID (string path parameter).
    request : ScanRequest
        Optional scan parameters (sources, entity_type, language_code,
        dry_run, full_rescan).
    session : AsyncSession
        Database session (used only for validation).

    Returns
    -------
    ScanJobResponse
        The created scan job (status ``"running"``) wrapped in ``data``.

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

    # 3. Launch the scan in the background and return the job (202).
    _scans_in_progress.add(guard_key)
    try:
        job = _launch_scan_job(
            kind="video",
            target_id=video_id,
            guard_key=guard_key,
            sources=request.sources or ["transcript"],
            video_ids=[video_id],
            entity_type=request.entity_type,
            language_code=request.language_code,
            dry_run=request.dry_run,
            full_rescan=request.full_rescan,
        )
    except Exception:
        _scans_in_progress.discard(guard_key)
        raise
    return ScanJobResponse(data=job)


@router.get(
    "/scan-jobs/{job_id}",
    response_model=ScanJobResponse,
    summary="Get the status and result of an entity scan job",
)
async def get_scan_job(
    job_id: str = Path(..., description="Scan job identifier"),
) -> ScanJobResponse:
    """Return the current state of an asynchronous scan job.

    While running, ``status`` is ``"running"`` and ``result`` is null. On
    completion it becomes ``"succeeded"`` (with ``result`` metrics) or
    ``"failed"`` (with ``error``). Jobs are in-memory and ephemeral, so an
    unknown id (including after a server restart) returns ``404``.
    """
    job = _scan_jobs.get(job_id)
    if job is None:
        raise NotFoundError(resource_type="Scan job", identifier=job_id)
    return ScanJobResponse(data=job)


# ═══════════════════════════════════════════════════════════════════════════
# POST /entities/{entity_id}/tags — Attach a canonical tag (Feature 064)
# ═══════════════════════════════════════════════════════════════════════════


_canonical_tag_repo = CanonicalTagRepository()


@router.post(
    "/entities/{entity_id}/tags",
    status_code=201,
    summary="Attach a canonical tag to an entity",
    response_model=AddEntityTagResponse,
)
async def add_entity_tag(
    entity_id: uuid.UUID = Path(..., description="Named entity UUID"),
    body: AddEntityTagRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> AddEntityTagResponse:
    """Attach a canonical tag to an entity, linking or merging as appropriate.

    The server chooses the operation from the entity's current state so the
    rule cannot be overridden by a client (Feature 064, FR-001/FR-002/FR-003):

    - **no linked tag** — link this one by setting ``entity_id``
    - **one linked tag** — merge this one *into* it, that tag always surviving
      as the target irrespective of either tag's size
    - **several linked tags** — refuse. That is a legacy state the browser can
      no longer create (FR-011a) and it leaves no defined merge target, so
      choosing one would be a guess (FR-002a)

    Creates no entity alias on any path (FR-004): aliases are curated patterns
    for detecting a name in text, and a tag form follows uploader convention.

    Parameters
    ----------
    entity_id : uuid.UUID
        The entity to attach to.
    body : AddEntityTagRequest
        Carries only ``normalized_form``.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    AddEntityTagResponse
        Which operation ran, its id, the surviving tag, and the entity's
        resulting video count.

    Raises
    ------
    NotFoundError
        The entity or the tag does not exist (404).
    ConflictError
        The tag already belongs to an entity, is already merged, or the entity
        holds more than one linked tag (409).
    APIValidationError
        The tag is the entity's own linked tag (422).
    """
    # Resolve both records before calling the service. The service reports a
    # missing entity and a missing tag with the same ValueError("... not
    # found"), and the mapping below keys on that substring — so resolving here
    # is what keeps a 404 from naming the wrong resource.
    entity = await session.get(NamedEntityDB, entity_id)
    if entity is None:
        raise NotFoundError(resource_type="NamedEntity", identifier=str(entity_id))

    # status=None deliberately: the default filters to active, which would turn
    # "this tag is merged" into "this tag does not exist" — a 404 for a row that
    # is present. The caller needs to know the difference, so the status is
    # checked below rather than hidden in the lookup.
    tag = await _canonical_tag_repo.get_by_normalized_form(
        session, body.normalized_form, status=None
    )
    if tag is None:
        raise NotFoundError(
            resource_type="CanonicalTag", identifier=body.normalized_form
        )
    if tag.status != "active":
        raise ConflictError(
            message=(
                f"Tag '{body.normalized_form}' is {tag.status} and cannot be "
                f"attached. Only active tags can represent an entity."
            ),
            details={"status": tag.status},
        )

    linked = await _canonical_tag_repo.get_linked_tags(session, entity_id)

    if len(linked) > 1:
        raise ConflictError(
            message=(
                f"'{entity.canonical_name}' has {len(linked)} linked tags. "
                f"Resolve which one represents it before attaching another — "
                f"with several there is no defined tag to merge into."
            ),
            details={
                "linked_normalized_forms": [t.normalized_form for t in linked],
            },
        )

    if any(t.id == tag.id for t in linked):
        raise APIValidationError(
            message=(
                f"'{body.normalized_form}' already represents "
                f"'{entity.canonical_name}'. A tag cannot be merged into itself."
            ),
        )

    if tag.entity_id is not None:
        other = await session.get(NamedEntityDB, tag.entity_id)
        raise ConflictError(
            message=(
                f"Tag '{body.normalized_form}' already represents "
                f"'{other.canonical_name if other else tag.entity_id}'. "
                f"Unlink it there before attaching it here."
            ),
            details={"entity_id": str(tag.entity_id)},
        )

    operation: str
    target_form: str
    target_display: str

    if not linked:
        # FR-001: nothing to merge into, so this tag becomes the entity's.
        result = await _tag_mgmt_service.classify(
            session,
            body.normalized_form,
            EntityType(entity.entity_type),
            link_entity_id=entity_id,
            actor=ACTOR_USER_LOCAL,
        )
        operation = "link"
        target_form = body.normalized_form
        target_display = tag.canonical_form
        operation_id = result.operation_id
    else:
        # FR-002/FR-003: the entity's tag is always the target.
        target = linked[0]
        merge_result = await _tag_mgmt_service.merge(
            session,
            [body.normalized_form],
            target.normalized_form,
            reason=f"Attached to entity '{entity.canonical_name}'",
            actor=ACTOR_USER_LOCAL,
        )
        operation = "merge"
        target_form = target.normalized_form
        target_display = target.canonical_form
        operation_id = merge_result.operation_id

    await session.commit()

    refreshed = await _canonical_tag_repo.get_linked_tags(session, entity_id)
    entity_video_count = refreshed[0].video_count if refreshed else 0

    return AddEntityTagResponse(
        data=AddEntityTagResult(
            operation=operation,  # type: ignore[arg-type]
            operation_id=str(operation_id),
            target_normalized_form=target_form,
            target_canonical_form=target_display,
            entity_video_count=entity_video_count,
        )
    )


@router.get(
    "/entities/{entity_id}/tags",
    summary="Tags representing an entity, and what they have absorbed",
    response_model=EntityTagsResponse,
)
async def get_entity_tags(
    entity_id: uuid.UUID = Path(..., description="Named entity UUID"),
    session: AsyncSession = Depends(get_db),
) -> EntityTagsResponse:
    """Return the entity's linked tag(s), each with the tags merged into it.

    Without this the tag section is write-only: a curator cannot tell whether
    an entity already has a tag, which is the question that precedes every
    other action here (Feature 064, US3).

    An empty ``linked_tags`` is a meaningful answer, not an error — it is the
    signal that the entity's video count omits every tag-associated video
    (FR-011). More than one sets ``needs_attention``: legacy data reached that
    state, the browser can no longer create it, and the page renders it rather
    than raising (FR-011a).

    Parameters
    ----------
    entity_id : uuid.UUID
        The entity to inspect.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    EntityTagsResponse
        Linked tags with their absorbed tags, and whether attention is needed.

    Raises
    ------
    NotFoundError
        The entity does not exist (404).
    """
    entity = await session.get(NamedEntityDB, entity_id)
    if entity is None:
        raise NotFoundError(resource_type="NamedEntity", identifier=str(entity_id))

    linked = await _canonical_tag_repo.get_linked_tags(session, entity_id)

    summaries: list[LinkedTagSummary] = []
    for tag in linked:
        merged = await _canonical_tag_repo.get_merged_into(session, tag.id)
        summaries.append(
            LinkedTagSummary(
                canonical_form=tag.canonical_form,
                normalized_form=tag.normalized_form,
                video_count=tag.video_count,
                alias_count=tag.alias_count,
                merged_tags=[
                    MergedTagSummary(
                        canonical_form=m.canonical_form,
                        normalized_form=m.normalized_form,
                        # Frozen at merge time. Not additive with the parent's
                        # count, since the video sets may overlap (FR-014).
                        contributed_video_count=m.video_count,
                        operation_id=str(op_id) if op_id is not None else None,
                        operation_source_count=source_count,
                    )
                    for m, op_id, source_count in merged
                ],
            )
        )

    return EntityTagsResponse(
        data=EntityTagsResult(
            linked_tags=summaries,
            needs_attention=len(summaries) > 1,
        )
    )


@router.post(
    "/entities/{entity_id}/tags/{normalized_form}/un-merge",
    summary="Restore a tag that was merged into the entity's tag",
    response_model=UnMergeResponse,
)
async def un_merge_entity_tag(
    entity_id: uuid.UUID = Path(..., description="Named entity UUID"),
    normalized_form: str = Path(..., description="Normalized form of the merged tag"),
    body: UnMergeRequest = Body(default_factory=UnMergeRequest),
    session: AsyncSession = Depends(get_db),
) -> UnMergeResponse:
    """Reverse the merge that folded a tag into the entity's tag (FR-015).

    Reverses the whole operation rather than extracting one tag: undo restores
    the original row — status, ``merged_into_id``, its own raw forms and its
    entity link — whereas splitting would fabricate a different tag with a
    recomputed name and leave the original tombstone behind.

    Because the unit is the operation, a merge that folded several tags at once
    restores all of them. 465 of 489 merges took a single source, so this is
    rare; where it applies the caller must confirm, having been told **which**
    tags return, since a count alone cannot be judged (FR-016).

    Parameters
    ----------
    entity_id : uuid.UUID
        The entity whose tag absorbed this one.
    normalized_form : str
        The merged tag to restore.
    body : UnMergeRequest
        ``confirm_multi_source`` acknowledges a multi-tag reversal.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    UnMergeResponse
        The tags restored and the operation reversed.

    Raises
    ------
    NotFoundError
        The entity, the tag, or a live merge for it does not exist (404).
    ConflictError
        Confirmation is required, or the merge was already reversed (409).
    """
    entity = await session.get(NamedEntityDB, entity_id)
    if entity is None:
        raise NotFoundError(resource_type="NamedEntity", identifier=str(entity_id))

    linked = await _canonical_tag_repo.get_linked_tags(session, entity_id)
    if not linked:
        raise NotFoundError(
            resource_type="CanonicalTag",
            identifier=normalized_form,
            hint="This entity has no linked tag, so nothing is merged into one.",
        )

    # Only tags merged into *this entity's* tag may be reversed here. Reversing
    # an arbitrary merge would let one entity's page mutate another's group.
    candidates = [
        (tag, op_id, count)
        for parent in linked
        for tag, op_id, count in await _canonical_tag_repo.get_merged_into(
            session, parent.id
        )
        if tag.normalized_form == normalized_form
    ]
    if not candidates:
        raise NotFoundError(
            resource_type="CanonicalTag",
            identifier=normalized_form,
            hint="No tag by that name is merged into this entity's tag.",
        )

    tag, operation_id, source_count = candidates[0]
    if operation_id is None:
        raise ConflictError(
            message=(
                f"'{tag.canonical_form}' is merged, but no reversible operation "
                f"is recorded for it. It must be un-merged with the CLI."
            ),
        )

    if source_count > 1 and not body.confirm_multi_source:
        siblings = await _canonical_tag_repo.get_merged_into(session, linked[0].id)
        # Exclude the tag being un-merged: the sentence says "N *other* tags",
        # so listing it among them contradicts its own count.
        names = sorted(
            t.canonical_form
            for t, op, _ in siblings
            if op == operation_id and t.id != tag.id
        )
        raise ConflictError(
            message=(
                f"Un-merging '{tag.canonical_form}' also restores "
                f"{source_count - 1} other tag"
                f"{'' if source_count == 2 else 's'}, because they were merged "
                f"in one operation: {', '.join(names)}."
            ),
            details={"restored_tags": names, "confirm_field": "confirm_multi_source"},
        )

    try:
        await _tag_mgmt_service.undo(session, operation_id)
    except ValueError as exc:
        # Preconditions are re-checked against current state, not the state at
        # merge time (FR-031) — the service refuses if the operation was
        # already reversed since this page loaded.
        raise ConflictError(message=str(exc)) from exc

    await session.commit()

    restored = await _canonical_tag_repo.get_merged_into(session, linked[0].id)
    still_merged = {t.normalized_form for t, _, _ in restored}
    return UnMergeResponse(
        data=UnMergeResult(
            restored=[normalized_form] if normalized_form not in still_merged else [],
            operation_id=str(operation_id),
        )
    )


@router.delete(
    "/entities/{entity_id}/tags/{normalized_form}",
    summary="Stop a tag representing an entity",
    response_model=UnlinkResponse,
)
async def unlink_entity_tag(
    entity_id: uuid.UUID = Path(..., description="Named entity UUID"),
    normalized_form: str = Path(..., description="Normalized form of the linked tag"),
    session: AsyncSession = Depends(get_db),
) -> UnlinkResponse:
    """Clear a tag's entity link, leaving the tag itself intact (FR-018).

    The tag is neither deleted nor deprecated — it returns to the searchable
    pool, so a tag attached to the wrong entity can be corrected rather than
    stranded (FR-019).

    Refused while anything is merged into it (FR-017): those tags' raw forms
    live on this one, so unlinking would take the whole group's videos away
    from the entity in a single click that names only one tag.

    Parameters
    ----------
    entity_id : uuid.UUID
        The entity to detach from.
    normalized_form : str
        The linked tag.
    session : AsyncSession
        Database session (injected).

    Returns
    -------
    UnlinkResponse
        The tag that no longer represents the entity.

    Raises
    ------
    NotFoundError
        The entity does not exist, or that tag does not represent it (404).
    ConflictError
        Tags are merged into it and must be un-merged first (409).
    """
    entity = await session.get(NamedEntityDB, entity_id)
    if entity is None:
        raise NotFoundError(resource_type="NamedEntity", identifier=str(entity_id))

    linked = await _canonical_tag_repo.get_linked_tags(session, entity_id)
    target = next((t for t in linked if t.normalized_form == normalized_form), None)
    if target is None:
        raise NotFoundError(
            resource_type="CanonicalTag",
            identifier=normalized_form,
            hint="That tag does not represent this entity.",
        )

    merged = await _canonical_tag_repo.get_merged_into(session, target.id)
    if merged:
        raise ConflictError(
            message=(
                f"{len(merged)} tag{'' if len(merged) == 1 else 's'} "
                f"{'is' if len(merged) == 1 else 'are'} merged into "
                f"'{target.canonical_form}'. Un-merge "
                f"{'it' if len(merged) == 1 else 'them'} first — "
                f"{'its' if len(merged) == 1 else 'their'} raw forms live on "
                f"this tag, so unlinking would take "
                f"{'its' if len(merged) == 1 else 'their'} videos from this "
                f"entity too."
            ),
            details={
                "merged_normalized_forms": [t.normalized_form for t, _, _ in merged]
            },
        )

    target.entity_id = None
    session.add(target)
    await session.commit()

    return UnlinkResponse(data=UnlinkResult(unlinked=normalized_form))
