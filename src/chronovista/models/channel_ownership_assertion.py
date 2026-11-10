"""Pydantic read-model for a user-asserted channel-ownership link (Feature 109).

The DECIDED-space complement to the imported ``youtube_channel_id`` (P2397) read model in
:mod:`chronovista.models.channel_ownership`. This is one row of
``channel_ownership_assertions`` as stored, before it is folded into the provenance-tagged
union the API returns.
"""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class ChannelOwnershipAssertion(BaseModel):
    """One user-asserted "entity operates channel" link, as persisted."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_id: uuid.UUID
    channel_id: str
    note: str | None
    asserted_at: datetime.datetime
    created_at: datetime.datetime
    updated_at: datetime.datetime
