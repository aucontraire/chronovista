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

# Provenance is defined once in the models layer; re-exported here for the API schemas.
from chronovista.models.channel_ownership import Provenance


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
    provenance: Provenance = Field(
        ...,
        description="'wikidata' (imported P2397) or 'manual' (user-asserted). A 'manual' "
        "link is never emitted as 'wikidata'; when both exist for a channel it is shown "
        "once as 'wikidata'.",
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
    provenance: Provenance = Field(
        ...,
        description="'wikidata' (imported P2397) or 'manual' (user-asserted).",
    )


class ChannelOperatorsResponse(BaseModel):
    """Response envelope for the entities operating a channel."""

    model_config = ConfigDict(strict=True)

    channel_id: str = Field(..., description="Channel ID (echo of the path param)")
    total_entities: int = Field(
        ..., ge=0, description="Total entities operating the channel"
    )
    items: list[ChannelOperatorItem]


class AddEntityChannelRequest(BaseModel):
    """Body for asserting (entity-side) that an entity operates a channel (Feature 109)."""

    model_config = ConfigDict(strict=True)

    channel_ref: str = Field(
        ...,
        description="A raw channel ID (UC…) or a youtube.com/channel/UC… URL; parsed and "
        "format-validated server-side (no network call, no @handle/custom-URL support).",
    )
    note: str | None = Field(
        None, description="Optional free-text rationale for the assertion."
    )


class AddChannelOperatorRequest(BaseModel):
    """Body for asserting (channel-side) that an entity operates this channel (Feature 109).

    Not ``strict``: a request body carries ``entity_id`` as a JSON string, which must coerce
    to ``UUID`` (strict mode would reject the string). Response models stay strict.
    """

    entity_id: UUID = Field(
        ..., description="The operating entity (must already exist)."
    )
    note: str | None = Field(
        None, description="Optional free-text rationale for the assertion."
    )
