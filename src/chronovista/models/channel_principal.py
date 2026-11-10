"""Pydantic read-model for `channel_principals` (DESIGN-CHANNEL-PRINCIPALS).

A channel-level cast link. ``decision`` is the versioned verdict category
(``cast`` | ``recurring_guest`` | ``credited_subject`` | ``stuffing`` | ``retired``),
not a boolean; a row is a live principal when ``decision == 'cast'`` (current when
``through`` is ``None``). Non-cast rows are tombstones that keep a reviewed candidate
from being re-proposed. This is a channel-level fact only — it never implies presence
in any individual video.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ChannelPrincipal(BaseModel):
    """One channel_principals row."""

    id: UUID
    channel_id: str
    entity_id: UUID

    # imported-assertion slot
    wikidata_linked_at: datetime | None = None

    # corpus-observation slot
    derived_generator_version: str | None = None
    tag_credited_count: int | None = None
    text_credited_count: int | None = None
    checkable_video_count: int | None = None
    spoken_video_count: int | None = None

    # human-decision slot (decision = versioned category)
    decided_at: datetime | None = None
    decision: str | None = None
    decided_reason: str | None = None

    # tenure (through is None => current)
    first_seen: date | None = None
    last_seen: date | None = None
    through: date | None = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
