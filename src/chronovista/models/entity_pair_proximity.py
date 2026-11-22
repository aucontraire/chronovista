"""
Transcript proximity co-occurrence models (Feature 116).

``EntityPairProximity`` is one close co-mention of two library entities inside a
single transcript language. Pairs are stored canonically ordered
(``entity_a_id < entity_b_id``), mirroring the DB CHECK constraints. The per-pair
rollup is aggregated in SQL by the repository, so it has no Pydantic model here.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, model_validator


def _check_canonical_pair(entity_a_id: uuid.UUID, entity_b_id: uuid.UUID) -> None:
    if entity_a_id == entity_b_id:
        raise ValueError("a proximity pair cannot pair an entity with itself")
    if entity_a_id >= entity_b_id:
        raise ValueError(
            "entity_a_id must be < entity_b_id (canonical order); "
            "order the pair before constructing the model"
        )


class EntityPairProximityBase(BaseModel):
    """Shared fields of one close co-mention instance."""

    entity_a_id: uuid.UUID = Field(
        ..., description="Canonically the smaller of the two entity ids"
    )
    entity_b_id: uuid.UUID = Field(
        ..., description="Canonically the larger of the two entity ids"
    )
    video_id: str = Field(..., max_length=20, description="Video of both segments")
    language_code: str = Field(
        ...,
        max_length=10,
        description="Transcript language shared by both segments",
    )
    segment_a_id: int = Field(
        ..., description="transcript_segments.id of entity_a's mention (start anchor)"
    )
    segment_b_id: int = Field(
        ..., description="transcript_segments.id of entity_b's mention (start anchor)"
    )
    gap_seconds: float = Field(
        ..., ge=0, description="abs(start_time(a) - start_time(b))"
    )

    @model_validator(mode="after")
    def _canonical_order(self) -> EntityPairProximityBase:
        _check_canonical_pair(self.entity_a_id, self.entity_b_id)
        return self


class EntityPairProximityCreate(EntityPairProximityBase):
    """What the computor inserts."""
