"""
Entity operation log models for the audit trail of entity curation edits.

Defines Pydantic V2 models for the ``entity_operation_logs`` table, which
records name/description edits to named entities with typed rollback data,
mirroring the ``tag_operation_logs`` pattern (Feature 057).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_ENTITY_OPERATION_TYPES = {"update"}


class EntityEditSnapshot(BaseModel):
    """Snapshot of the mutable entity fields at one point in an edit.

    Only the fields that participated in the edit are populated; the rest
    remain ``None`` so a rollback restores exactly what changed.
    """

    canonical_name: str | None = Field(
        default=None, description="Entity display name at this point"
    )
    canonical_name_normalized: str | None = Field(
        default=None, description="Normalized identity at this point"
    )
    description: str | None = Field(
        default=None, description="Entity description at this point"
    )

    model_config = ConfigDict(validate_assignment=True)


class EntityEditRollback(BaseModel):
    """Typed rollback payload for an entity name/description edit.

    Stored as JSONB in ``entity_operation_logs.rollback_data``. Undo restores
    the ``before`` snapshot for the fields listed in ``changed_fields``.
    """

    before: EntityEditSnapshot = Field(
        ..., description="Field values prior to the edit"
    )
    after: EntityEditSnapshot = Field(..., description="Field values after the edit")
    changed_fields: list[str] = Field(
        default_factory=list,
        description="Names of the fields that changed in this edit",
    )

    model_config = ConfigDict(validate_assignment=True)


class EntityOperationLogBase(BaseModel):
    """Base model for entity operation log data."""

    entity_id: uuid.UUID = Field(..., description="Edited named entity UUID")
    operation_type: str = Field(
        default="update",
        max_length=30,
        description="Type of operation (currently only 'update')",
    )
    rollback_data: EntityEditRollback = Field(
        ..., description="Typed before/after snapshot for undo"
    )
    performed_by: str = Field(
        default="system",
        max_length=100,
        description="Actor that performed the edit (e.g. 'user:local', 'cli')",
    )

    @field_validator("operation_type")
    @classmethod
    def validate_operation_type(cls, v: str) -> str:
        """Validate operation_type is one of the allowed values."""
        if v not in ALLOWED_ENTITY_OPERATION_TYPES:
            raise ValueError(
                f"operation_type must be one of "
                f"{sorted(ALLOWED_ENTITY_OPERATION_TYPES)}, got {v!r}"
            )
        return v

    model_config = ConfigDict(validate_assignment=True)


class EntityOperationLogCreate(EntityOperationLogBase):
    """Model for creating entity operation log entries."""


class EntityOperationLogUpdate(BaseModel):
    """Model for updating entity operation logs (PATCH-style, all optional)."""

    rolled_back: bool | None = Field(
        default=None, description="Whether this operation has been rolled back"
    )
    rolled_back_at: datetime | None = Field(
        default=None, description="Timestamp when the rollback was performed"
    )

    model_config = ConfigDict(validate_assignment=True)


class EntityOperationLog(EntityOperationLogBase):
    """Full entity operation log model with all persisted fields."""

    id: uuid.UUID = Field(..., description="Entity operation log UUID (UUIDv7)")
    performed_at: datetime = Field(
        ..., description="Timestamp when the operation was performed"
    )
    rolled_back: bool = Field(
        ..., description="Whether this operation has been rolled back"
    )
    rolled_back_at: datetime | None = Field(
        default=None, description="Timestamp when the rollback was performed"
    )

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )
