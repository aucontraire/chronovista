"""Real-DB tests for ``CandidateGenerationRunRepository`` (Feature 097, T031).

``start_run``'s guarantee is the ``uq_candidate_generation_runs_active`` partial
unique index behind a SAVEPOINT; a mocked session cannot exercise either. These run
against the real integration Postgres via the ``db_session`` fixture
(create_all + drop_all per test). Name-free placeholders only.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import CandidateGenerationRun as RunDB
from chronovista.models.enums import GenerationRunStatus
from chronovista.repositories.candidate_generation_run_repository import (
    CandidateGenerationRunRepository,
)

pytestmark = pytest.mark.asyncio


async def _running_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(RunDB).where(RunDB.status == "running")
        )
        or 0
    )


async def test_start_run_inserts_a_running_run(db_session: AsyncSession) -> None:
    repo = CandidateGenerationRunRepository()

    run = await repo.start_run(db_session)

    assert run is not None
    assert run.status == GenerationRunStatus.RUNNING
    assert run.progress_percent == 0
    assert run.completed_at is None
    assert await _running_count(db_session) == 1


async def test_start_run_returns_none_when_a_run_is_active_and_inserts_nothing(
    db_session: AsyncSession,
) -> None:
    repo = CandidateGenerationRunRepository()
    first = await repo.start_run(db_session)
    assert first is not None

    second = await repo.start_run(db_session)

    assert second is None
    assert await _running_count(db_session) == 1
    active = await repo.get_active(db_session)
    assert active is not None and active.id == first.id


async def test_session_stays_usable_after_a_refused_start(
    db_session: AsyncSession,
) -> None:
    """The SAVEPOINT must roll back only the refused insert, not the transaction."""
    repo = CandidateGenerationRunRepository()
    first = await repo.start_run(db_session)
    assert first is not None
    assert await repo.start_run(db_session) is None

    # The pre-existing row is still visible and the session can still write.
    await repo.record_progress(db_session, run_id=first.id, progress_percent=10)
    await db_session.flush()
    active = await repo.get_active(db_session)
    assert active is not None and active.progress_percent == 10


async def test_slot_frees_after_finish_and_after_fail(db_session: AsyncSession) -> None:
    repo = CandidateGenerationRunRepository()

    first = await repo.start_run(db_session)
    assert first is not None
    await repo.finish(
        db_session,
        run_id=first.id,
        candidates_discovered=3,
        candidates_upserted=3,
        superseded=0,
        pending_total=3,
        by_triage={"worth_review": 3},
    )
    second = await repo.start_run(db_session)
    assert second is not None and second.id != first.id

    await repo.fail(db_session, run_id=second.id, error="boom")
    third = await repo.start_run(db_session)
    assert third is not None and third.id not in {first.id, second.id}


async def test_finish_and_fail_persist_terminal_fields(
    db_session: AsyncSession,
) -> None:
    repo = CandidateGenerationRunRepository()
    done = await repo.start_run(db_session)
    assert done is not None
    await repo.finish(
        db_session,
        run_id=done.id,
        candidates_discovered=4,
        candidates_upserted=3,
        superseded=1,
        pending_total=2,
        by_triage={"worth_review": 2},
        empty_reason=None,
    )
    latest = await repo.get_latest(db_session)
    assert latest is not None and latest.id == done.id
    # Core UPDATEs bypass the identity map; re-read the row from the DB.
    row = (
        await db_session.execute(
            select(RunDB)
            .where(RunDB.id == done.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.status == "completed"
    assert row.progress_percent == 100
    assert (row.candidates_discovered, row.candidates_upserted) == (4, 3)
    assert (row.superseded, row.pending_total) == (1, 2)
    assert row.by_triage == {"worth_review": 2}
    assert row.completed_at is not None

    failed = await repo.start_run(db_session)
    assert failed is not None
    await repo.fail(db_session, run_id=failed.id, error="sweep exploded")
    row = (
        await db_session.execute(
            select(RunDB)
            .where(RunDB.id == failed.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.status == "failed"
    assert row.error == "sweep exploded"
    assert row.completed_at is not None


async def test_get_latest_is_none_with_no_runs(db_session: AsyncSession) -> None:
    assert await CandidateGenerationRunRepository().get_latest(db_session) is None
