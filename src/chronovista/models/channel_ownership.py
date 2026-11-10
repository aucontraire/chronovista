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

from pydantic import BaseModel, ConfigDict


class ChannelOperatorMatch(BaseModel):
    """A raw repository result: one active entity that operates a given channel.

    Ownership is **not** person-scoped — the operator may be a person, an organisation,
    or any grounded entity type. (A channel *principal*, by contrast, is a person who
    appears; that is a separate, later relation — see DESIGN-CHANNEL-PRINCIPALS.)
    """

    entity_id: uuid.UUID
    entity_type: str
    canonical_name: str

    model_config = ConfigDict(from_attributes=True)
