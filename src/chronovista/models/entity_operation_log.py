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

ALLOWED_ENTITY_OPERATION_TYPES = {"update", "reground", "refetch", "alias_delete"}


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
    entity_type: str | None = Field(
        default=None, description="Entity type at this point"
    )

    # extra="forbid" so this snapshot is distinguishable from GroundingSnapshot
    # in the rollback_data smart union (their field sets are disjoint).
    model_config = ConfigDict(validate_assignment=True, extra="forbid")


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


class GroundingSnapshot(BaseModel):
    """Snapshot of an entity's grounding at one point in a re-ground/refetch.

    The field set is disjoint from EntityEditSnapshot (and both forbid extra
    fields) so the two rollback shapes are unambiguously distinguishable in the
    ``rollback_data`` smart union.
    """

    wikidata_id: str | None = Field(
        default=None, description="Wikidata QID at this point"
    )
    dbpedia_id: str | None = Field(
        default=None, description="DBpedia IRI at this point"
    )
    description: str | None = Field(
        default=None, description="Entity description at this point"
    )

    model_config = ConfigDict(validate_assignment=True, extra="forbid")


class GroundingRollback(BaseModel):
    """Typed rollback payload for a grounding change (reground/refetch).

    Stored as JSONB in ``entity_operation_logs.rollback_data``.
    """

    before: GroundingSnapshot = Field(..., description="Grounding prior to the change")
    after: GroundingSnapshot = Field(..., description="Grounding after the change")
    changed_fields: list[str] = Field(
        default_factory=list,
        description="Which of {wikidata, dbpedia, description, properties} changed",
    )

    model_config = ConfigDict(validate_assignment=True)


class AliasSnapshot(BaseModel):
    """Snapshot of a deleted alias, enough to recreate the row (#298)."""

    id: uuid.UUID = Field(..., description="Alias UUID (restored verbatim)")
    entity_id: uuid.UUID = Field(..., description="Owning entity UUID")
    alias_name: str = Field(..., description="Alias display text")
    alias_name_normalized: str = Field(..., description="Normalized identity")
    alias_type: str = Field(..., description="Alias type")
    case_sensitive: bool = Field(
        default=False, description="Case-sensitive matching flag"
    )
    occurrence_count: int = Field(default=0, description="Occurrence counter")

    model_config = ConfigDict(
        validate_assignment=True, extra="forbid", from_attributes=True
    )


class MentionSnapshot(BaseModel):
    """Snapshot of an auto-detected mention removed by an alias deletion (#298).

    Captures every column needed to re-insert the row verbatim on undo (the
    same ``id`` is restored to preserve identity). ``segment_id`` may reference
    a segment that no longer exists at undo time — the restore skips those.
    """

    id: uuid.UUID = Field(..., description="Mention UUID (restored verbatim)")
    entity_id: uuid.UUID = Field(..., description="Owning entity UUID")
    segment_id: int | None = Field(default=None, description="Transcript segment id")
    video_id: str = Field(..., description="Video id")
    language_code: str | None = Field(default=None, description="Language code")
    mention_text: str = Field(..., description="Matched text span")
    detection_method: str = Field(..., description="Detection method (rule_match)")
    confidence: float | None = Field(default=None, description="Detection confidence")
    match_start: int | None = Field(default=None, description="Match start offset")
    match_end: int | None = Field(default=None, description="Match end offset")
    correction_id: uuid.UUID | None = Field(
        default=None, description="Correction link, if any"
    )
    mention_source: str = Field(
        default="transcript", description="Source (transcript/title/description)"
    )
    mention_context: str | None = Field(default=None, description="Context snippet")
    alias_id: uuid.UUID | None = Field(
        default=None, description="The alias this mention was attributed to"
    )

    model_config = ConfigDict(
        validate_assignment=True, extra="forbid", from_attributes=True
    )


class AliasDeleteRollback(BaseModel):
    """Typed rollback payload for an alias deletion (#298, Level 3).

    Captures the removed alias and the auto-detected mentions the deletion took
    with it, so an undo restores both. Its top-level field set (``alias`` +
    ``removed_mentions``) is disjoint from the edit/grounding rollbacks, keeping
    the ``rollback_data`` smart union unambiguous.
    """

    alias: AliasSnapshot = Field(..., description="The deleted alias to restore")
    removed_mentions: list[MentionSnapshot] = Field(
        default_factory=list,
        description="Auto-detected mentions removed with the alias",
    )

    model_config = ConfigDict(validate_assignment=True, extra="forbid")


class EntityOperationLogBase(BaseModel):
    """Base model for entity operation log data."""

    entity_id: uuid.UUID = Field(..., description="Edited named entity UUID")
    operation_type: str = Field(
        default="update",
        max_length=30,
        description="Type of operation ('update', 'reground', or 'refetch')",
    )
    rollback_data: EntityEditRollback | GroundingRollback | AliasDeleteRollback = Field(
        ...,
        description=(
            "Typed rollback payload for undo (entity edit, grounding, or "
            "alias deletion)"
        ),
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
