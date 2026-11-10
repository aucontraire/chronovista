"""Pydantic read-model for the channel-ownership surface (ownership promotion).

"Entity E operates channel C" is the imported ``youtube_channel_id`` identifier
(Wikidata P2397) surfaced as a queryable relation — a read-path promotion of an
existing JSONB property, no schema change (ADR-010 "promote-on-query"). The
repository returns the raw match below; the viewer-facing shapes (which fold in the
channel title and in-library status) live in ``api/schemas/``, mirroring how the
inverse-relation surface splits :class:`~chronovista.models.entity_relations.InboundRelationMatch`
from its API response models.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Where an ownership link came from — the single-source definition, imported by the API
# schemas. "wikidata" = imported P2397 identifier; "manual" = a user-asserted
# ``channel_ownership_assertions`` row (Feature 109).
Provenance = Literal["wikidata", "manual"]


class ChannelOperatorMatch(BaseModel):
    """A repository result: one active entity that operates a given channel.

    Ownership is **not** person-scoped — the operator may be a person, an organisation,
    or any grounded entity type. (A channel *principal*, by contrast, is a person who
    appears; that is a separate, later relation — see DESIGN-CHANNEL-PRINCIPALS.)

    ``provenance`` tags whether this match came from the imported P2397 identifier or a
    user-asserted link; the union read never emits a ``manual`` match as ``wikidata``.
    """

    entity_id: uuid.UUID
    entity_type: str
    canonical_name: str
    provenance: Provenance

    model_config = ConfigDict(from_attributes=True)


class OwnedChannelMatch(BaseModel):
    """A repository result: one channel an entity operates, with its provenance.

    The entity-side counterpart of :class:`ChannelOperatorMatch`. Carries only the raw
    channel id and provenance; the route resolves in-library status and title against the
    ``channels`` table at read time (so an external channel later ingested flips for free).
    """

    channel_id: str
    provenance: Provenance

    model_config = ConfigDict(from_attributes=True)
