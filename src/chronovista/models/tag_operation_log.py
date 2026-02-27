"""
Tag operation log models for audit trail of tag normalization operations.

Defines Pydantic models for tag operation logs that record merges, splits,
renames, deletions, and creations of canonical tags, with rollback support.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_OPERATION_TYPES = {"merge", "split", "rename", "delete", "create"}


class TagOperationLogBase(BaseModel):
    """Base model for tag operation log data."""

    operation_type: str = Field(
        ...,
        max_length=30,
        description="Type of operation: merge, split, rename, delete, or create",
    )
    reason: Optional[str] = Field(
        default=None, description="Human-readable reason for the operation"
    )

    @field_validator("operation_type")
    @classmethod
    def validate_operation_type(cls, v: str) -> str:
        """Validate operation_type is one of the allowed values."""
        if v not in ALLOWED_OPERATION_TYPES:
            raise ValueError(
                f"operation_type must be one of {sorted(ALLOWED_OPERATION_TYPES)}, got {v!r}"
            )
        return v

    model_config = ConfigDict(
        validate_assignment=True,
    )


class TagOperationLogCreate(TagOperationLogBase):
    """Model for creating tag operation log entries."""

    source_canonical_ids: list[str] = Field(
        default_factory=list,
        description="List of source canonical tag UUID strings (stored as JSONB)",
    )
    target_canonical_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Target canonical tag UUID (e.g. merge destination)",
    )
    affected_alias_ids: list[str] = Field(
        default_factory=list,
        description="List of tag alias UUID strings (stored as JSONB)",
    )
    rollback_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot data required to reverse the operation",
    )
    performed_by: str = Field(
        default="cli",
        max_length=100,
        description="Actor that performed the operation (e.g. 'cli', 'system')",
    )


class TagOperationLogUpdate(BaseModel):
    """Model for updating tag operation logs (PATCH-style, all fields optional)."""

    rolled_back: Optional[bool] = Field(
        default=None, description="Whether this operation has been rolled back"
    )
    rolled_back_at: Optional[datetime] = Field(
        default=None, description="Timestamp when the rollback was performed"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class TagOperationLog(TagOperationLogBase):
    """Full tag operation log model with all persisted fields."""

    id: uuid.UUID = Field(..., description="Tag operation log UUID (UUIDv7)")
    source_canonical_ids: list[uuid.UUID] = Field(
        ..., description="List of source canonical tag UUIDs involved in the operation"
    )
    target_canonical_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Target canonical tag UUID (e.g. merge destination)",
    )
    affected_alias_ids: list[uuid.UUID] = Field(
        ..., description="List of tag alias UUIDs affected by the operation"
    )
    performed_by: str = Field(
        ...,
        max_length=100,
        description="Actor that performed the operation",
    )
    performed_at: datetime = Field(
        ..., description="Timestamp when the operation was performed"
    )
    rollback_data: dict[str, Any] = Field(
        ..., description="Snapshot data required to reverse the operation"
    )
    rolled_back: bool = Field(
        ..., description="Whether this operation has been rolled back"
    )
    rolled_back_at: Optional[datetime] = Field(
        default=None, description="Timestamp when the rollback was performed"
    )

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )
