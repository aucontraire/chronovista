"""Candidate GENERATION run API, crossed from outside (Feature 097, T030, US2).

Real JSON through the app (``ASGITransport``) against the real integration DB.

Why the ``db_manager`` patch exists: ``_run_generation`` (the detached sweep) calls
``db_manager.get_session_factory()`` directly, which BYPASSES the ``async_client``
fixture's ``get_db`` override. Left alone, a sweep triggered through the client would
open the app's own engine against the app's own database (and a foreign event loop).
The autouse fixture below points ``get_session_factory`` at this test's
``integration_session_factory``, so request sessions and the sweep's sessions hit the
same database. The sweep is then awaited through the router's own
``_generation_tasks`` registry -- no sleeps, no polling races.

The integration DB is shared and never reset: every seeded row uses a per-run random
QID / label / video id and is removed on teardown; generation-run rows are owned
wholly by this module (cleared before and after each test) because at most one may
be ``running`` at a time.
"""

from __future__ import annotations

import asyncio
import datetime
import random
import string
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.api.routers import candidates as candidates_router
from chronovista.config.database import db_manager
from chronovista.db.models import CandidateGenerationRun as RunDB
from chronovista.db.models import CandidateSuggestion as CandidateDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.repositories.candidate_generation_run_repository import (
    CandidateGenerationRunRepository,
)
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from tests.factories.candidate_generation_run_factory import (
    create_candidate_generation_run_db,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_GENERATION = "/api/v1/candidates/generation"
_STATUS = "/api/v1/candidates/generation/status"
_SweepFinished = Callable[[], Awaitable[None]]


def _letters(n: int) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


def _qid(prefix: str) -> str:
    return prefix + "".join(random.choices(string.digits, k=9))


class _Seeder:
    """Seeds a grounded seed entity + corpus video; records everything for teardown."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory
        self.entity_ids: list[uuid.UUID] = []
        self.video_ids: list[str] = []
        self.target_qids: list[str] = []

    async def seed(self, *, targets: dict[str, str]) -> None:
        """Seed one grounded seed whose stored relations point at ``targets``.

        ``targets`` maps relation field name -> target label. Each target gets a
        fresh QID that is NOT grounded, and a corpus video whose title contains the
        label, so the sweep discovers it and grounds it against the corpus.
        """
        properties: dict[str, Any] = {}
        for relation, label in targets.items():
            target_qid = _qid("Q97030")
            self.target_qids.append(target_qid)
            properties[relation] = {
                "qids": [target_qid],
                "values": [label],
                "source": "wikidata",
                "set_at": "2026-10-27T00:00:00Z",
            }
        entity_id = uuid.uuid4()
        self.entity_ids.append(entity_id)
        name = f"Seed {_letters(10)} {_letters(8)}"
        async with self.factory() as session:
            session.add(
                NamedEntityDB(
                    id=entity_id,
                    canonical_name=name,
                    canonical_name_normalized=name.lower(),
                    entity_type="person",
                    external_ids={"wikidata": {"id": _qid("Q97031")}},
                    properties=properties,
                )
            )
            for label in targets.values():
                video_id = "v97" + _letters(8)
                self.video_ids.append(video_id)
                session.add(
                    VideoDB(
                        video_id=video_id,
                        title=f"A talk featuring {label}",
                        description=None,
                        upload_date=datetime.datetime(2019, 1, 1, tzinfo=datetime.UTC),
                        duration=120,
                    )
                )
            await session.commit()

    async def candidate(self, qid: str) -> CandidateDB:
        async with self.factory() as session:
            row = (
                await session.execute(
                    select(CandidateDB).where(
                        CandidateDB.source_channel == "relation",
                        CandidateDB.wikidata_qid == qid,
                    )
                )
            ).scalar_one_or_none()
        assert row is not None, f"sweep did not produce a candidate for {qid}"
        return row


async def _delete_all_runs(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        await session.execute(delete(RunDB))
        await session.commit()


@pytest.fixture(autouse=True)
async def sweep_uses_test_database(
    monkeypatch: pytest.MonkeyPatch,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[None, None]:
    """Point the detached sweep at the test DB and guarantee no run outlives a test."""
    monkeypatch.setattr(
        db_manager, "get_session_factory", lambda: integration_session_factory
    )
    await _delete_all_runs(integration_session_factory)
    yield
    # A sweep still in flight must finish BEFORE its rows and engine disappear.
    pending = list(candidates_router._generation_tasks)
    if pending:
        await asyncio.wait_for(asyncio.gather(*pending), timeout=60)
    await _delete_all_runs(integration_session_factory)


@pytest.fixture
async def sweep_finished() -> _SweepFinished:
    """Await every detached sweep the router has launched (bounded)."""

    async def _wait() -> None:
        pending = list(candidates_router._generation_tasks)
        assert pending, "POST /generation launched no sweep task"
        await asyncio.wait_for(asyncio.gather(*pending), timeout=60)

    return _wait


@pytest.fixture
async def seeder(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[_Seeder, None]:
    seeder = _Seeder(integration_session_factory)
    yield seeder
    async with integration_session_factory() as session:
        await session.execute(
            delete(CandidateDB).where(CandidateDB.wikidata_qid.in_(seeder.target_qids))
        )
        await session.execute(
            delete(NamedEntityDB).where(NamedEntityDB.id.in_(seeder.entity_ids))
        )
        await session.execute(
            delete(VideoDB).where(VideoDB.video_id.in_(seeder.video_ids))
        )
        await session.commit()


async def _running_rows(factory: async_sessionmaker[AsyncSession]) -> int:
    async with factory() as session:
        return int(
            await session.scalar(
                select(func.count()).select_from(RunDB).where(RunDB.status == "running")
            )
            or 0
        )


async def _status_run(client: AsyncClient) -> dict[str, Any]:
    resp = await client.get(_STATUS)
    assert resp.status_code == 200, resp.text
    run = resp.json()["run"]
    assert run is not None
    return dict(run)


class TestGenerationLifecycle:
    async def test_post_runs_sweep_to_completion_with_determinate_progress(
        self,
        async_client: AsyncClient,
        seeder: _Seeder,
        sweep_finished: _SweepFinished,
    ) -> None:
        label = f"Zg {_letters(10)} {_letters(8)}"
        await seeder.seed(targets={"spouse": label, "father": f"Zh {_letters(12)}"})

        # Every heartbeat the sweep writes goes through the REAL repository method;
        # the wrapper only records what was written so progress can be inspected.
        real = CandidateGenerationRunRepository.record_progress
        written: list[int] = []

        async def _recording(
            self: CandidateGenerationRunRepository,
            session: AsyncSession,
            *,
            run_id: uuid.UUID,
            progress_percent: int,
        ) -> None:
            written.append(progress_percent)
            await real(self, session, run_id=run_id, progress_percent=progress_percent)

        with patch.object(
            CandidateGenerationRunRepository, "record_progress", _recording
        ):
            started = await async_client.post(_GENERATION)
            assert started.status_code == 202, started.text
            body = started.json()
            # The running state is observable before the sweep has had a turn.
            assert body["status"] == "running"
            assert body["progress_percent"] == 0
            run_id = body["id"]

            await sweep_finished()

        run = await _status_run(async_client)
        assert run["id"] == run_id
        assert run["status"] == "completed"
        assert run["progress_percent"] == 100
        assert run["candidates_discovered"] >= 2
        assert run["pending_total"] >= 1
        assert run["completed_at"] is not None
        assert run["error"] is None

        # Determinate: intermediate percentages strictly inside (0, 100), rising.
        assert written, "sweep reported no intermediate progress"
        assert all(0 < pct < 100 for pct in written), written
        assert written == sorted(set(written)), f"non-monotonic: {written}"

        # The artifact, not just the status: the corpus-present target was produced
        # AND grounded against the seeded video.
        cand = await seeder.candidate(seeder.target_qids[0])
        assert cand.review_status == "pending"
        assert cand.salience >= 1

    async def test_status_is_readable_through_the_read_path_after_completion(
        self,
        async_client: AsyncClient,
        seeder: _Seeder,
        sweep_finished: _SweepFinished,
    ) -> None:
        """The queue summary (another reader of the mutated data) sees the sweep."""
        await seeder.seed(targets={"spouse": f"Zs {_letters(10)} {_letters(8)}"})
        before = (await async_client.get("/api/v1/candidates/summary")).json()["data"]

        assert (await async_client.post(_GENERATION)).status_code == 202
        await sweep_finished()

        after = (await async_client.get("/api/v1/candidates/summary")).json()["data"]
        assert after["pending"] >= before["pending"] + 1


class TestGenerationConcurrency:
    async def test_second_post_while_running_is_409_and_adds_no_row(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with integration_session_factory() as session:
            active = create_candidate_generation_run_db(progress_percent=40)
            session.add(active)
            await session.commit()
            active_id = str(active.id)

        resp = await async_client.post(_GENERATION)

        # A fresh active run is refused with a 409 problem detail (the UI reads
        # the in-flight run's progress from GET /generation/status, not this body).
        assert resp.status_code == 409, resp.text
        assert "already in progress" in resp.text.lower()
        assert await _running_rows(integration_session_factory) == 1
        assert (
            not candidates_router._generation_tasks
        ), "a refused POST launched a sweep"
        # The active run is still observable via the status endpoint.
        status_resp = await async_client.get(f"{_GENERATION}/status")
        assert status_resp.status_code == 200
        run = status_resp.json()["run"]
        assert run["id"] == active_id
        assert run["progress_percent"] == 40

    async def test_unique_index_not_an_app_check_refuses_a_second_running_row(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-024 holds at the DB: the app-level 409 is not the only guard."""
        from sqlalchemy.exc import IntegrityError

        async with integration_session_factory() as session:
            session.add(create_candidate_generation_run_db())
            await session.commit()
        async with integration_session_factory() as session:
            session.add(create_candidate_generation_run_db())
            with pytest.raises(IntegrityError):
                await session.commit()


class TestStaleReaping:
    async def test_stale_running_run_reads_failed_and_frees_the_slot(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        sweep_finished: _SweepFinished,
    ) -> None:
        stale_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=10)
        async with integration_session_factory() as session:
            stale = create_candidate_generation_run_db(
                updated_at=stale_at, started_at=stale_at, progress_percent=30
            )
            session.add(stale)
            await session.commit()
            stale_id = str(stale.id)

        run = await _status_run(async_client)
        assert run["id"] == stale_id
        assert run["status"] == "failed"
        assert "stalled" in (run["error"] or "").lower()
        assert await _running_rows(integration_session_factory) == 0

        # The reap is persisted, and the slot is free: a new run can start.
        restarted = await async_client.post(_GENERATION)
        assert restarted.status_code == 202, restarted.text
        assert restarted.json()["id"] != stale_id
        await sweep_finished()

    async def test_fresh_heartbeat_is_not_reaped(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with integration_session_factory() as session:
            session.add(create_candidate_generation_run_db(progress_percent=55))
            await session.commit()

        run = await _status_run(async_client)

        assert run["status"] == "running"
        assert run["progress_percent"] == 55


class TestZeroSeeds:
    async def test_completed_run_with_no_grounded_seeds_states_why(
        self,
        async_client: AsyncClient,
        sweep_finished: _SweepFinished,
    ) -> None:
        # The integration DB is shared and may hold grounded entities leaked by other
        # suites, so the "no grounded seeds" STATE is pinned at the one query that
        # defines it. Everything else -- run row, detached task, finish(), the status
        # endpoint -- is real.
        async def _no_seeds(
            self: NamedEntityRepository, session: AsyncSession
        ) -> set[str]:
            return set()

        with patch.object(NamedEntityRepository, "get_grounded_qids", _no_seeds):
            assert (await async_client.post(_GENERATION)).status_code == 202
            await sweep_finished()

        run = await _status_run(async_client)
        assert run["status"] == "completed"
        assert run["progress_percent"] == 100
        assert run["seeds_grounded"] == 0
        assert run["candidates_discovered"] == 0
        assert run["empty_reason"] is not None
        assert "ground" in run["empty_reason"].lower()


class TestNoRunState:
    async def test_status_with_no_runs_is_a_null_run(
        self, async_client: AsyncClient
    ) -> None:
        # The autouse fixture clears the (module-owned) runs table, so this is exact.
        resp = await async_client.get(_STATUS)

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"run": None}


class TestRerunPreservesVerdicts:
    async def test_rerun_leaves_a_rejected_verdict_untouched_and_still_refreshes(
        self,
        async_client: AsyncClient,
        seeder: _Seeder,
        sweep_finished: _SweepFinished,
    ) -> None:
        await seeder.seed(
            targets={
                "spouse": f"Zk {_letters(10)} {_letters(8)}",
                "father": f"Zr {_letters(10)} {_letters(8)}",
            }
        )
        keep_qid, reject_qid = seeder.target_qids

        assert (await async_client.post(_GENERATION)).status_code == 202
        await sweep_finished()
        rejected = await seeder.candidate(reject_qid)
        kept_first = await seeder.candidate(keep_qid)

        verdict = await async_client.post(f"/api/v1/candidates/{rejected.id}/reject")
        assert verdict.status_code == 200, verdict.text
        assert verdict.json()["outcome"] == "rejected"
        rejected_before = await seeder.candidate(reject_qid)
        assert rejected_before.reviewed_at is not None

        # Second run: the first is terminal, so the slot is free.
        second = await async_client.post(_GENERATION)
        assert second.status_code == 202, second.text
        await sweep_finished()
        assert (await _status_run(async_client))["status"] == "completed"

        rejected_after = await seeder.candidate(reject_qid)
        assert rejected_after.review_status == "rejected"
        assert rejected_after.reviewed_by == rejected_before.reviewed_by
        assert rejected_after.reviewed_at == rejected_before.reviewed_at
        assert rejected_after.id == rejected.id, "re-run duplicated the candidate"

        # ...while the untouched pending candidate was refreshed, not skipped.
        kept_after = await seeder.candidate(keep_qid)
        assert kept_after.review_status == "pending"
        assert kept_after.last_generated_at > kept_first.last_generated_at

        # And the rejected one is not re-offered through the read path.
        pending = (await async_client.get("/api/v1/candidates?limit=100")).json()
        assert reject_qid not in {c["wikidata_qid"] for c in pending["data"]}
