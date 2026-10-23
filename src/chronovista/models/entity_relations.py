"""Pydantic read-models for the inverse relation surface (Feature 087).

The repository returns these for the "Referenced by" section — the active library entities whose
Wikidata relations point TO the viewed entity, grouped by relationship (synonymous fields unioned).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class InboundRelationMatch(BaseModel):
    """A raw repository result: one active entity + which relation fields of it point at the target.

    The repository stays free of grouping semantics — it reports *which fields matched*; the caller
    (which owns the canonical grouping) folds these into display groups.
    """

    entity_id: uuid.UUID
    entity_type: str
    canonical_name: str
    matched_fields: list[str] = Field(
        ..., description="WANTED field names whose qids contained the target"
    )
    instance_of: list[str] = Field(
        default_factory=list,
        description="Resolved instance_of labels (de-duplicated; [] if absent) — Feature 088 type filter",
    )

    model_config = ConfigDict(from_attributes=True)


# The viewer-facing grouped shapes (ReferencedByEntity / ReferencedByGroup / ReferencedByResponse)
# live in `api/schemas/entity_mentions.py` — the endpoint assembles them from the raw
# InboundRelationMatch rows above. This model module intentionally holds only the repository return
# type, to avoid two near-identical class pairs inviting an edit to the wrong one.
