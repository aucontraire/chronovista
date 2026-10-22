"""Response schemas for the category detail surface (Feature 086).

The category detail page lists the active library entities in a Wikipedia category. The
category is addressed by **id**; its name is shown but kept out of URLs (names are library
content). Classes are prefixed ``WikipediaCategory`` to avoid colliding with the unrelated
YouTube ``CategoryDetail`` in :mod:`chronovista.api.schemas.categories`.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from chronovista.api.schemas.responses import PaginationMeta


class WikipediaCategoryDetail(BaseModel):
    """Identity and breadth of one Wikipedia category (Feature 086).

    Attributes
    ----------
    id : UUID
        Category UUID (the stable address; names stay out of OUR URLs).
    name : str
        Display name.
    global_size : int | None
        Wikipedia-wide member count; ``None`` while unknown (unmeasured).
    is_broad : bool
        Whether the category is a broad/generic grouping — derived at the API boundary by
        comparing ``global_size`` to the broad-category ceiling. ``False`` when the size is
        unknown (breadth is not asserted without a measure).
    member_count : int
        Active library entities assigned to this category.
    wikipedia_url : str
        Outbound link to this category's page on the public Wikipedia (so a viewer can see the
        full Wikipedia listing). Wikipedia's own public URL — the name is inherently public there.
    """

    model_config = ConfigDict(strict=True)

    id: UUID
    name: str
    global_size: int | None
    is_broad: bool
    member_count: int
    wikipedia_url: str


class WikipediaCategoryDetailResponse(BaseModel):
    """Response envelope for the category meta endpoint."""

    model_config = ConfigDict(strict=True)

    data: WikipediaCategoryDetail


class WikipediaCategoryMember(BaseModel):
    """One active library entity assigned to a category (Feature 086).

    Attributes
    ----------
    entity_id : UUID
        The member entity (links to its own detail page).
    entity_type : str
        Carried so the type badge renders without a second lookup.
    canonical_name : str
        Display name.
    """

    model_config = ConfigDict(strict=True)

    entity_id: UUID
    entity_type: str
    canonical_name: str


class WikipediaCategoryEntitiesResponse(BaseModel):
    """Paginated response envelope for a category's member entities."""

    model_config = ConfigDict(strict=True)

    data: list[WikipediaCategoryMember]
    pagination: PaginationMeta
