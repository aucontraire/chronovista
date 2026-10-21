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
