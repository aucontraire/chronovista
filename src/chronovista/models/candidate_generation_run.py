"""Candidate generation run models (Feature 097).

A generation run is the durable, UI-observable state of a background candidate
sweep: its status, a determinate completion percentage, the result counts, and
timestamps. Persisted (not in-process) so the live percentage is readable by any
worker answering a status poll, a crashed/stale run is detectable, and state
survives a container restart (FR-023/FR-024/FR-025).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import GenerationRunStatus, SourceChannel


class CandidateGenerationRunBase(BaseModel):
    """Base fields shared across the run models."""

    source_channel: SourceChannel = Field(
        default=SourceChannel.RELATION,
        description="Discovery channel the run generated for",
    )
    status: GenerationRunStatus = Field(
        default=GenerationRunStatus.RUNNING, description="Run lifecycle state"
    )
    progress_percent: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Determinate completion percentage (capped at 99 until terminal)",
    )
    seeds_grounded: int = Field(
        default=0, ge=0, description="Grounded seed entities the run grew from"
    )
    candidates_discovered: int = Field(default=0, ge=0)
    candidates_upserted: int = Field(default=0, ge=0)
    superseded: int = Field(default=0, ge=0)
    pending_total: int = Field(default=0, ge=0)
    by_triage: dict[str, int] = Field(
        default_factory=dict, description="Per-triage pending counts on completion"
    )
    empty_reason: str | None = Field(
        default=None, description="Why the run produced nothing (no grounded seeds)"
    )
    error: str | None = Field(
        default=None, description="Error detail when status is failed"
    )

    model_config = ConfigDict(validate_assignment=True)


class CandidateGenerationRunCreate(CandidateGenerationRunBase):
    """Model for inserting a new (running) generation run."""


class CandidateGenerationRunUpdate(BaseModel):
    """Model for updating a run (progress writes and terminal transitions)."""

    status: GenerationRunStatus | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    seeds_grounded: int | None = Field(default=None, ge=0)
    candidates_discovered: int | None = Field(default=None, ge=0)
    candidates_upserted: int | None = Field(default=None, ge=0)
    superseded: int | None = Field(default=None, ge=0)
    pending_total: int | None = Field(default=None, ge=0)
    by_triage: dict[str, int] | None = None
    empty_reason: str | None = None
    error: str | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(validate_assignment=True)


class CandidateGenerationRun(CandidateGenerationRunBase):
    """Full generation run with identifiers and timestamps."""

    id: uuid.UUID = Field(..., description="Run UUID (UUIDv7)")
    started_at: datetime = Field(..., description="When the run started")
    updated_at: datetime = Field(
        ..., description="Heartbeat — bumped on each progress write"
    )
    completed_at: datetime | None = Field(
        default=None, description="When the run reached a terminal state"
    )

    model_config = ConfigDict(from_attributes=True, validate_assignment=True)
