"""API response schemas for the channel-ownership surface (ownership promotion).

The viewer-facing shapes for the imported "entity E operates channel C" relation
(Wikidata P2397 ``youtube_channel_id``), surfaced from ``named_entities.properties``
with no schema change (ADR-010 promote-on-query):

- :class:`EntityChannelsResponse` — the channels an entity operates (entity-detail side).
- :class:`ChannelOperatorsResponse` — the entities operating a channel (channel-detail side).

The repository-return model lives in :mod:`chronovista.models.channel_ownership`; these
are the API envelopes, mirroring how the inverse-relation surface splits
``InboundRelationMatch`` from its ``ReferencedBy*`` response models.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EntityChannelLink(BaseModel):
    """One channel an entity operates, with in-library status (entity-detail side)."""

    model_config = ConfigDict(strict=True)

    channel_id: str = Field(..., description="YouTube channel ID")
    title: str | None = Field(
        None,
        description="Channel title when the channel is in the library; null otherwise",
    )
    in_library: bool = Field(
        ...,
        description="True when the channel is in the library (linkable in-app); "
        "False for an external channel (channel discovery is a separate feature)",
    )


class EntityChannelsResponse(BaseModel):
    """Response envelope for the channels an entity operates."""

    model_config = ConfigDict(strict=True)

    data: list[EntityChannelLink]


class ChannelOperatorItem(BaseModel):
    """One entity that operates the channel (channel-detail side).

    Ownership is not person-scoped — ``entity_type`` may be person, organization, etc.
    """

    model_config = ConfigDict(strict=True)

    entity_id: UUID
    entity_type: str
    canonical_name: str


class ChannelOperatorsResponse(BaseModel):
    """Response envelope for the entities operating a channel."""

    model_config = ConfigDict(strict=True)

    channel_id: str = Field(..., description="Channel ID (echo of the path param)")
    total_entities: int = Field(
        ..., ge=0, description="Total entities operating the channel"
    )
    items: list[ChannelOperatorItem]
