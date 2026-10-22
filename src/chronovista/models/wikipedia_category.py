"""Pydantic V2 models for category persistence (Feature 083).

Mirrors the ORM tables ``wikipedia_categories`` and ``entity_categories``. ``max_length``
bounds match the DB column widths exactly (``name`` 500, ``source`` 50) so a value cannot
validate in Pydantic and then fail on insert.
"""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class WikipediaCategoryCreate(BaseModel):
    """Input model for creating/upserting a Wikipedia category."""

    name: str = Field(
        min_length=1, max_length=500, description="Exact category name (unique)"
    )
    global_size: int | None = Field(
        default=None,
        ge=0,
        description="Wikipedia-wide member count; None until fetched",
    )
    global_size_fetched_at: datetime.datetime | None = Field(
        default=None, description="When global_size was fetched; None while unknown"
    )


class WikipediaCategory(WikipediaCategoryCreate):
    """A persisted Wikipedia category."""

    id: uuid.UUID = Field(..., description="Category UUID (UUIDv7)")
    created_at: datetime.datetime = Field(..., description="Row creation time")

    model_config = ConfigDict(from_attributes=True)


class EntityCategoryCreate(BaseModel):
    """Input model for an entity-to-category assignment."""

    entity_id: uuid.UUID = Field(..., description="The entity")
    category_id: uuid.UUID = Field(..., description="The category")
    source: str = Field(
        min_length=1, max_length=50, description="Assignment provenance, e.g. 'dbpedia'"
    )
    set_at: datetime.datetime | None = Field(
        default=None, description="When the assignment was originally recorded"
    )


class EntityCategory(EntityCategoryCreate):
    """A persisted assignment (composite identity: entity_id + category_id)."""

    model_config = ConfigDict(from_attributes=True)


class BridgeNeighbor(BaseModel):
    """One shared-category neighbor returned by the bridge query."""

    neighbor_id: uuid.UUID = Field(
        ..., description="An entity sharing a category with the queried entity"
    )
    shared_category: str = Field(..., description="The category they share")
    global_size: int | None = Field(
        default=None, description="The shared category's global size"
    )

    model_config = ConfigDict(from_attributes=True)


class SharedCategoryRef(BaseModel):
    """A shared category identified by ``id`` + ``name`` (Feature 086).

    Feature 085 originally exposed shared categories as bare name strings. The category
    detail page (086) is addressed by category **id**, so the shared-category chips must
    carry the id to link there — this ref is the honest model for "a category, by id and
    display name". This is a breaking element-shape change to 085's shipped response
    (``list[str]`` → ``list[SharedCategoryRef]``), coordinated in the same change with its
    sole consumer (the 085 panel); not additive.
    """

    id: uuid.UUID = Field(..., description="Category UUID")
    name: str = Field(..., description="Category display name")

    model_config = ConfigDict(from_attributes=True)


class CategoryMember(BaseModel):
    """One active library entity assigned to a category (Feature 086).

    The row the category detail page lists. Carries the entity's display fields so the list
    renders (name + type badge) and links to the entity page without a second lookup.
    """

    entity_id: uuid.UUID = Field(..., description="The member entity")
    entity_type: str = Field(..., description="The member's entity type")
    canonical_name: str = Field(..., description="The member's display name")

    model_config = ConfigDict(from_attributes=True)


class SharedCategoryNeighbour(BaseModel):
    """An aggregated shared-category neighbour (Feature 085): one row per neighbour entity.

    Distinct from :class:`BridgeNeighbor` (one row per shared category), this is the
    aggregate the entity-page surface consumes — one neighbour, the categories it shares, and
    the shared-category count that is the ranking primary key.
    """

    entity_id: uuid.UUID = Field(..., description="The neighbour entity")
    entity_type: str = Field(..., description="The neighbour's entity type")
    canonical_name: str = Field(..., description="The neighbour's display name")
    shared_categories: list[SharedCategoryRef] = Field(
        default_factory=list,
        description=(
            "Categories shared with the queried entity, most-specific first, each as an "
            "{id, name} ref so a chip can link to the category detail page (Feature 086)"
        ),
    )
    shared_category_count: int = Field(
        ..., ge=1, description="Number of shared categories (the ranking primary key)"
    )

    model_config = ConfigDict(from_attributes=True)
