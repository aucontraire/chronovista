"""Category detail endpoints (Feature 086) — the inverse of the shared-category bridge.

Lists the active library entities assigned to a Wikipedia category, reachable by clicking a
category chip. Read-only over Features 083/084 tables; no schema change. The resource is
``/wikipedia-categories`` — the bare ``/categories`` path is the unrelated YouTube
VideoCategory router.
"""

from __future__ import annotations

import urllib.parse
import uuid

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import (
    get_db,
    get_entity_category_repository,
    get_wikipedia_category_repository,
    require_auth,
)
from chronovista.api.query_protection import run_with_timeout
from chronovista.api.routers.responses import GET_ITEM_ERRORS
from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.wikipedia_categories import (
    WikipediaCategoryDetail,
    WikipediaCategoryDetailResponse,
    WikipediaCategoryEntitiesResponse,
    WikipediaCategoryMember,
)
from chronovista.exceptions import NotFoundError
from chronovista.repositories.entity_category_repository import EntityCategoryRepository
from chronovista.repositories.wikipedia_category_repository import (
    WikipediaCategoryRepository,
)

router = APIRouter(dependencies=[Depends(require_auth)])

# Feature 086: a category whose Wikipedia-wide size exceeds this is flagged "broad" on its detail
# page. Same value as Feature 085's DEFAULT_MAX_CATEGORY_SIZE hub-suppression ceiling today, but a
# SEPARATE constant by design (reconcile I1) — the suppression ceiling (which neighbours 085 hides)
# and this display flag (how 086 labels a category) can be tuned independently later without one
# silently moving the other.
BROAD_CATEGORY_SIZE = 20_000

# The public English-Wikipedia base for a category page.
_WIKIPEDIA_CATEGORY_BASE = "https://en.wikipedia.org/wiki/Category:"


def _wikipedia_category_url(name: str) -> str:
    """Build the public Wikipedia URL for a category name (Feature 086).

    MediaWiki page titles use ``_`` for spaces; the rest is percent-encoded but the readable
    punctuation Wikipedia keeps in category titles (parentheses, commas, colons, ampersands …)
    is left intact so the link is human-legible. This is Wikipedia's own public URL, not ours —
    the name is inherently public there.
    """
    title = urllib.parse.quote(name.replace(" ", "_"), safe="_:,()&!*';@=+$/-")
    return f"{_WIKIPEDIA_CATEGORY_BASE}{title}"


def _parse_category_id(category_id: str) -> uuid.UUID:
    """Parse a category id, raising 404 on a malformed value (not a 422).

    A category is addressed by UUID; a non-UUID path segment simply does not identify any
    category, so the honest answer is not-found, consistent with the 085 endpoint.
    """
    try:
        return uuid.UUID(category_id)
    except ValueError as exc:
        raise NotFoundError(
            resource_type="WikipediaCategory", identifier=category_id
        ) from exc


@router.get(
    "/wikipedia-categories/{category_id}",
    response_model=WikipediaCategoryDetailResponse,
    responses=GET_ITEM_ERRORS,
    summary="Wikipedia category detail (identity, breadth, member count)",
)
async def get_wikipedia_category(
    category_id: str = Path(..., description="Wikipedia category UUID"),
    session: AsyncSession = Depends(get_db),
    cat_repo: WikipediaCategoryRepository = Depends(get_wikipedia_category_repository),
    entity_cat_repo: EntityCategoryRepository = Depends(get_entity_category_repository),
) -> WikipediaCategoryDetailResponse:
    """Identity + breadth + active-member count for one Wikipedia category (Feature 086).

    The header of the category detail page. Membership is an editorial fact, so the page
    states it plainly. ``is_broad`` is derived here (an API-layer presentation flag) by
    comparing the category's Wikipedia-wide size to :data:`BROAD_CATEGORY_SIZE`; an unknown
    (unmeasured) size is never flagged broad.

    Parameters
    ----------
    category_id : str
        Wikipedia category UUID (string form; a malformed value is a 404).

    Returns
    -------
    WikipediaCategoryDetailResponse
        The category's id, name, global size, broad flag, and active-member count.

    Raises
    ------
    NotFoundError
        If the id is malformed or no such category exists (404).
    """
    parsed_id = _parse_category_id(category_id)
    category = await cat_repo.get_by_id(session, parsed_id)
    if category is None:
        raise NotFoundError(resource_type="WikipediaCategory", identifier=category_id)
    member_count = await run_with_timeout(
        entity_cat_repo.count_active_members(session, parsed_id),
        operation="category member count",
        session=session,
    )
    is_broad = (
        category.global_size is not None and category.global_size > BROAD_CATEGORY_SIZE
    )
    return WikipediaCategoryDetailResponse(
        data=WikipediaCategoryDetail(
            id=category.id,
            name=category.name,
            global_size=category.global_size,
            is_broad=is_broad,
            member_count=member_count,
            wikipedia_url=_wikipedia_category_url(category.name),
        )
    )


@router.get(
    "/wikipedia-categories/{category_id}/entities",
    response_model=WikipediaCategoryEntitiesResponse,
    responses=GET_ITEM_ERRORS,
    summary="Active library entities in a Wikipedia category",
)
async def list_wikipedia_category_entities(
    category_id: str = Path(..., description="Wikipedia category UUID"),
    limit: int = Query(25, ge=1, le=100, description="Members per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
    cat_repo: WikipediaCategoryRepository = Depends(get_wikipedia_category_repository),
    entity_cat_repo: EntityCategoryRepository = Depends(get_entity_category_repository),
) -> WikipediaCategoryEntitiesResponse:
    """Active library entities assigned to a category, paginated (Feature 086).

    One bounded page of members in a stable total order (``lower(name)`` then id) so paging
    never skips or repeats. Active entities only (merged/inactive excluded, mirroring 085). A
    category that exists but has no active members is an empty page (``data: []``,
    ``total: 0``), not an error; only a malformed/unknown id is a 404.

    Parameters
    ----------
    category_id : str
        Wikipedia category UUID (a malformed value is a 404).
    limit : int
        Members per page (1–100, default 25).
    offset : int
        Pagination offset for incremental loading.

    Returns
    -------
    WikipediaCategoryEntitiesResponse
        The page of members and pagination metadata.

    Raises
    ------
    NotFoundError
        If the id is malformed or no such category exists (404).
    """
    parsed_id = _parse_category_id(category_id)
    if await cat_repo.get_by_id(session, parsed_id) is None:
        raise NotFoundError(resource_type="WikipediaCategory", identifier=category_id)
    members = await run_with_timeout(
        entity_cat_repo.entities_in_category(
            session, parsed_id, limit=limit, offset=offset
        ),
        operation="category members",
        session=session,
    )
    total = await run_with_timeout(
        entity_cat_repo.count_active_members(session, parsed_id),
        operation="category member count",
        session=session,
    )
    return WikipediaCategoryEntitiesResponse(
        data=[
            WikipediaCategoryMember(
                entity_id=m.entity_id,
                entity_type=m.entity_type,
                canonical_name=m.canonical_name,
            )
            for m in members
        ],
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
    )
