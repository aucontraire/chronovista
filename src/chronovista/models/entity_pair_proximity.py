"""
Transcript proximity co-occurrence models (Features 116, 117).

``EntityPairProximity`` is one close co-mention of two library entities inside a
single transcript language. Pairs are stored canonically ordered
(``entity_a_id < entity_b_id``), mirroring the DB CHECK constraints.

Feature 117 adds read models for consumers: per-scope freshness
(:class:`ProximityScopeState`), the per-pair summary derived on read from the
records (:class:`PairProximitySummary`), and the processing outcome
(:class:`ProcessSummary`).
"""

from __future__ import annotations

import datetime
import uuid
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class ProximityScopeStatus(str, Enum):
    """Freshness of one ``(video, language)`` scope.

    ``not_computed``: no published result exists. ``current``: computed from the
    scope's latest revision under the current measurement-rule version (possibly
    with zero records). ``stale``: a published result exists, but its source
    revision or rule version is no longer the latest.
    """

    NOT_COMPUTED = "not_computed"
    CURRENT = "current"
    STALE = "stale"


class ProximityScopeState(BaseModel):
    """Read view of one scope's freshness (FR-019/FR-020)."""

    model_config = ConfigDict(frozen=True)

    video_id: str = Field(..., max_length=20)
    language_code: str = Field(..., max_length=10)
    state: ProximityScopeStatus
    failing: bool = Field(
        ..., description="attempts >= 3 under the current rule version (still retried)"
    )
    revision: int | None = Field(
        None, description="None when the scope has no state row yet"
    )
    computed_revision: int | None = None
    computed_rule_version: str | None = None
    computed_at: datetime.datetime | None = None
    attempts: int = 0
    next_attempt_at: datetime.datetime | None = None
    last_error: str | None = None


class PairProximitySummary(BaseModel):
    """Per-pair summary derived on read from the co-mention records (FR-021).

    ``videos_within_*`` count each video once regardless of language, mentions, or
    records. ``segment_pairs_within_*`` are *segment-pair co-mention counts*: they
    measure mention density, not separate discussions, and parallel-language
    transcripts add to them. ``complete`` is ``True`` only when every scope that
    could contribute to the pair is current; otherwise the totals are provisional.
    """

    model_config = ConfigDict(frozen=True)

    entity_a_id: uuid.UUID
    entity_b_id: uuid.UUID
    videos_within_15: int = Field(..., ge=0)
    videos_within_30: int = Field(..., ge=0)
    videos_within_60: int = Field(..., ge=0)
    videos_within_120: int = Field(..., ge=0)
    segment_pairs_within_15: int = Field(..., ge=0)
    segment_pairs_within_30: int = Field(..., ge=0)
    segment_pairs_within_60: int = Field(..., ge=0)
    segment_pairs_within_120: int = Field(..., ge=0)
    min_gap_seconds: float | None = Field(
        None, ge=0, description="None when the pair has no records"
    )
    complete: bool

    @model_validator(mode="after")
    def _canonical_order(self) -> PairProximitySummary:
        _check_canonical_pair(self.entity_a_id, self.entity_b_id)
        return self


class ProximityWorkerState(str, Enum):
    """Lifecycle of the in-process proximity worker (reported by ``/health``)."""

    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    DISABLED = "disabled"


class ProximityWorkerStatus(BaseModel):
    """Mutable in-process status of the proximity worker."""

    state: ProximityWorkerState = ProximityWorkerState.STOPPED
    last_cycle_at: datetime.datetime | None = None


class ScopeFilter(BaseModel):
    """Which scopes a processing call may claim: some videos, one entity, or all."""

    model_config = ConfigDict(frozen=True)

    video_ids: tuple[str, ...] | None = None
    entity_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_selector(self) -> ScopeFilter:
        if self.video_ids is not None and self.entity_id is not None:
            raise ValueError("a scope filter selects videos or an entity, not both")
        return self


class ProcessSummary(BaseModel):
    """Outcome of one processing call over a (possibly filtered) scope set."""

    model_config = ConfigDict(frozen=True)

    processed: int = Field(0, ge=0, description="Scopes published by this call")
    failed: int = Field(0, ge=0, description="Computation failures recorded")
    deferred: int = Field(
        0, ge=0, description="Scopes deferred after exhausting lock-contention retries"
    )
    records_written: int = Field(0, ge=0)
    locked_elsewhere: int = Field(
        0, ge=0, description="Non-current scopes held by another processor at the end"
    )
    failing: int = Field(0, ge=0, description="Scopes flagged failing at the end")
    waiting_to_retry: int = Field(
        0, ge=0, description="Scopes in a backoff or deferral window at the end"
    )
    remaining: int = Field(0, ge=0, description="Non-current scopes left at the end")
    complete: bool = Field(
        False, description="True only if every scope in the set is current"
    )


class RebuildOutcome(BaseModel):
    """Result of ``rebuild_proximity``: ``locked`` means another rebuild holds the lock."""

    model_config = ConfigDict(frozen=True)

    status: Literal["completed", "incomplete", "locked"]
    run_id: uuid.UUID | None = None
    summary: ProcessSummary | None = None


class DryRunScope(BaseModel):
    """One scope a dry run computed, and how many records it WOULD write."""

    model_config = ConfigDict(frozen=True)

    video_id: str
    language_code: str
    records: int = Field(..., ge=0)


class DryRunReport(BaseModel):
    """A non-publishing dry run. ``sampled`` is True when no scope was requested and
    a bounded sample was computed instead; its counts cover only those scopes."""

    model_config = ConfigDict(frozen=True)

    scopes: list[DryRunScope]
    sampled: bool


class FailingScope(BaseModel):
    """A scope that keeps failing (it is still retried with backoff)."""

    model_config = ConfigDict(frozen=True)

    video_id: str
    language_code: str
    attempts: int
    last_error: str | None
    next_attempt_at: datetime.datetime | None


class ProximityStatusReport(BaseModel):
    """Operator view of proximity freshness (``proximity status``, FR-024)."""

    model_config = ConfigDict(frozen=True)

    rule_version: str
    not_computed: int = Field(..., ge=0)
    current: int = Field(..., ge=0)
    stale: int = Field(..., ge=0)
    failing: list[FailingScope]
    failing_total: int = Field(..., ge=0)
    oldest_not_current_at: datetime.datetime | None
    rebuild_lock_holder_pid: int | None
