"""Candidate generation run repository (Feature 097).

Backs the durable, UI-observable generation-run record: a guarded insert that
enforces one active run per channel (FR-024), a progress heartbeat write
(FR-023a), terminal transitions, and the reads the status endpoint uses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import CandidateGenerationRun as CandidateGenerationRunDB
from chronovista.models.candidate_generation_run import (
    CandidateGenerationRun,
    CandidateGenerationRunCreate,
    CandidateGenerationRunUpdate,
)
from chronovista.models.enums import GenerationRunStatus
from chronovista.repositories.base import BaseSQLAlchemyRepository


class CandidateGenerationRunRepository(
    BaseSQLAlchemyRepository[
        CandidateGenerationRunDB,
        CandidateGenerationRunCreate,
        CandidateGenerationRunUpdate,
    ]
):
    """Data access for the candidate generation-run record."""

    def __init__(self) -> None:
        """Initialize with the CandidateGenerationRun model."""
        super().__init__(CandidateGenerationRunDB)

    async def start_run(
        self,
        session: AsyncSession,
        *,
        source_channel: str = "relation",
        seeds_grounded: int = 0,
    ) -> CandidateGenerationRun | None:
        """Insert a new running run, or return None if one is already active (FR-024).

        The ``uq_candidate_generation_runs_active`` partial unique index is the
        real guard; the insert is wrapped in a SAVEPOINT so a concurrent-run
        IntegrityError rolls back only this insert, leaving the request
        transaction usable.
        """
        run = CandidateGenerationRunDB(
            source_channel=source_channel,
            status=GenerationRunStatus.RUNNING.value,
            progress_percent=0,
            seeds_grounded=seeds_grounded,
        )
        try:
            async with session.begin_nested():
                session.add(run)
                await session.flush()
        except IntegrityError:
            return None
        await session.refresh(run)
        return CandidateGenerationRun.model_validate(run)

    async def get_active(
        self, session: AsyncSession, *, source_channel: str = "relation"
    ) -> CandidateGenerationRun | None:
        """Return the current running run for the channel, if any."""
        stmt = select(CandidateGenerationRunDB).where(
            CandidateGenerationRunDB.source_channel == source_channel,
            CandidateGenerationRunDB.status == GenerationRunStatus.RUNNING.value,
        )
        row = (await session.execute(stmt)).scalars().first()
        return CandidateGenerationRun.model_validate(row) if row is not None else None

    async def get_latest(
        self, session: AsyncSession, *, source_channel: str = "relation"
    ) -> CandidateGenerationRun | None:
        """Return the most recently started run for the channel, if any."""
        stmt = (
            select(CandidateGenerationRunDB)
            .where(CandidateGenerationRunDB.source_channel == source_channel)
            .order_by(CandidateGenerationRunDB.started_at.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).scalars().first()
        return CandidateGenerationRun.model_validate(row) if row is not None else None

    async def record_progress(
        self, session: AsyncSession, *, run_id: uuid.UUID, progress_percent: int
    ) -> None:
        """Write the progress percentage and bump the ``updated_at`` heartbeat.

        ``updated_at`` is set explicitly (redundant with the column's ORM
        ``onupdate`` but kept for clarity) — the heartbeat is what FR-025 reads
        for staleness. **Guarded by ``status='running'``**: once a run has been
        reaped to ``failed`` (stale) or finished, a late write from a lingering
        detached task is a no-op and cannot resurrect it.
        """
        await session.execute(
            update(CandidateGenerationRunDB)
            .where(
                CandidateGenerationRunDB.id == run_id,
                CandidateGenerationRunDB.status == GenerationRunStatus.RUNNING.value,
            )
            .values(progress_percent=progress_percent, updated_at=func.now())
        )

    async def finish(
        self,
        session: AsyncSession,
        *,
        run_id: uuid.UUID,
        candidates_discovered: int,
        candidates_upserted: int,
        superseded: int,
        pending_total: int,
        by_triage: dict[str, int],
        empty_reason: str | None = None,
    ) -> None:
        """Transition a run to completed with its result counts (progress → 100).

        Guarded by ``status='running'`` so a run already reaped to ``failed``
        (stale heartbeat) is never resurrected to ``completed`` by its lingering
        detached task.
        """
        await session.execute(
            update(CandidateGenerationRunDB)
            .where(
                CandidateGenerationRunDB.id == run_id,
                CandidateGenerationRunDB.status == GenerationRunStatus.RUNNING.value,
            )
            .values(
                status=GenerationRunStatus.COMPLETED.value,
                progress_percent=100,
                candidates_discovered=candidates_discovered,
                candidates_upserted=candidates_upserted,
                superseded=superseded,
                pending_total=pending_total,
                by_triage=by_triage,
                empty_reason=empty_reason,
                completed_at=func.now(),
                updated_at=func.now(),
            )
        )

    async def fail(
        self, session: AsyncSession, *, run_id: uuid.UUID, error: str
    ) -> None:
        """Transition a run to failed with an error detail.

        Guarded by ``status='running'`` so it is idempotent: reaping an already
        terminal run is a no-op, and a late failure from a lingering task cannot
        overwrite a run that already completed.
        """
        await session.execute(
            update(CandidateGenerationRunDB)
            .where(
                CandidateGenerationRunDB.id == run_id,
                CandidateGenerationRunDB.status == GenerationRunStatus.RUNNING.value,
            )
            .values(
                status=GenerationRunStatus.FAILED.value,
                error=error,
                completed_at=func.now(),
                updated_at=func.now(),
            )
        )

    @staticmethod
    def is_stale(
        run: CandidateGenerationRun, *, stale_after_seconds: int = 120
    ) -> bool:
        """True if a running run's heartbeat is older than the staleness cutoff (FR-025)."""
        if run.status != GenerationRunStatus.RUNNING:
            return False
        updated = run.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        return (datetime.now(UTC) - updated) > timedelta(seconds=stale_after_seconds)
