"""
Factory for the CandidateGenerationRun models using factory_boy (Feature 097).

Two factories, mirroring the project's ORM/Pydantic split:

- ``CandidateGenerationRunDBFactory`` builds the persistable ORM row
  (``chronovista.db.models.CandidateGenerationRun``) for real-DB tests.
- ``CandidateGenerationRunFactory`` builds the validated Pydantic read model
  (``chronovista.models.candidate_generation_run.CandidateGenerationRun``) for
  pure unit tests such as ``is_stale``.

ORM column defaults only apply at flush time, so the ORM factory sets them
explicitly to yield a fully populated in-memory object. Timestamps default to
"just now" so a freshly built running run is never stale unless a test ages it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import factory
from factory import LazyFunction
from uuid_utils import uuid7

from chronovista.db.models import CandidateGenerationRun as CandidateGenerationRunDB
from chronovista.models.candidate_generation_run import CandidateGenerationRun
from chronovista.models.enums import GenerationRunStatus, SourceChannel


def _uuid7() -> uuid.UUID:
    """Generate a UUIDv7 as a standard uuid.UUID (ORM PGUUID compatible)."""
    return uuid.UUID(bytes=uuid7().bytes)


def _now() -> datetime:
    return datetime.now(UTC)


class CandidateGenerationRunDBFactory(factory.Factory[CandidateGenerationRunDB]):
    """Factory for the CandidateGenerationRun ORM row (a fresh ``running`` run)."""

    class Meta:
        model = CandidateGenerationRunDB

    id: Any = LazyFunction(_uuid7)
    source_channel: Any = LazyFunction(lambda: "relation")
    status: Any = LazyFunction(lambda: GenerationRunStatus.RUNNING.value)
    progress_percent: Any = LazyFunction(lambda: 0)
    seeds_grounded: Any = LazyFunction(lambda: 0)
    candidates_discovered: Any = LazyFunction(lambda: 0)
    candidates_upserted: Any = LazyFunction(lambda: 0)
    superseded: Any = LazyFunction(lambda: 0)
    pending_total: Any = LazyFunction(lambda: 0)
    by_triage: Any = LazyFunction(dict)
    empty_reason: Any = LazyFunction(lambda: None)
    error: Any = LazyFunction(lambda: None)
    started_at: Any = LazyFunction(_now)
    updated_at: Any = LazyFunction(_now)
    completed_at: Any = LazyFunction(lambda: None)


class CandidateGenerationRunFactory(factory.Factory[CandidateGenerationRun]):
    """Factory for the validated CandidateGenerationRun Pydantic read model."""

    class Meta:
        model = CandidateGenerationRun

    id: Any = LazyFunction(_uuid7)
    source_channel: Any = LazyFunction(lambda: SourceChannel.RELATION)
    status: Any = LazyFunction(lambda: GenerationRunStatus.RUNNING)
    progress_percent: Any = LazyFunction(lambda: 0)
    started_at: Any = LazyFunction(_now)
    updated_at: Any = LazyFunction(_now)


def create_candidate_generation_run_db(**kwargs: Any) -> CandidateGenerationRunDB:
    """Build an in-memory CandidateGenerationRun ORM row with keyword overrides."""
    result = CandidateGenerationRunDBFactory.build(**kwargs)
    assert isinstance(result, CandidateGenerationRunDB)
    return result


def create_candidate_generation_run(**kwargs: Any) -> CandidateGenerationRun:
    """Build a CandidateGenerationRun read model with keyword overrides."""
    result = CandidateGenerationRunFactory.build(**kwargs)
    assert isinstance(result, CandidateGenerationRun)
    return result
