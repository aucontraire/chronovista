"""Unit tests for ``CandidateGenerationRunRepository`` (Feature 097, T031).

Pure-logic half: the staleness predicate around its 120s cutoff, and the SET clause
of the terminal-transition UPDATEs (inspected from the compiled statement, because a
fake session returns success whichever columns were written — Constitution, Cross-
Feature Data Contract Verification). The behaviour that only a real Postgres can
show — the partial unique index behind ``start_run`` — lives in
``tests/integration/repositories/test_candidate_generation_run_repository_db.py``.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from chronovista.models.enums import GenerationRunStatus
from chronovista.repositories.candidate_generation_run_repository import (
    CandidateGenerationRunRepository,
)
from tests.factories.candidate_generation_run_factory import (
    create_candidate_generation_run,
)


class TestIsStale:
    """``is_stale`` flips strictly after ``stale_after_seconds`` of silence."""

    def test_fresh_heartbeat_is_not_stale(self) -> None:
        run = create_candidate_generation_run(
            updated_at=datetime.now(UTC) - timedelta(seconds=5)
        )
        assert CandidateGenerationRunRepository.is_stale(run) is False

    def test_just_inside_the_cutoff_is_not_stale(self) -> None:
        run = create_candidate_generation_run(
            updated_at=datetime.now(UTC) - timedelta(seconds=110)
        )
        assert CandidateGenerationRunRepository.is_stale(run) is False

    def test_just_past_the_cutoff_is_stale(self) -> None:
        run = create_candidate_generation_run(
            updated_at=datetime.now(UTC) - timedelta(seconds=130)
        )
        assert CandidateGenerationRunRepository.is_stale(run) is True

    def test_cutoff_is_configurable(self) -> None:
        run = create_candidate_generation_run(
            updated_at=datetime.now(UTC) - timedelta(seconds=30)
        )
        assert CandidateGenerationRunRepository.is_stale(run) is False
        assert (
            CandidateGenerationRunRepository.is_stale(run, stale_after_seconds=10)
            is True
        )

    def test_naive_timestamp_is_treated_as_utc(self) -> None:
        naive_old = (datetime.now(UTC) - timedelta(seconds=600)).replace(tzinfo=None)
        run = create_candidate_generation_run(updated_at=naive_old)
        assert CandidateGenerationRunRepository.is_stale(run) is True

    @pytest.mark.parametrize(
        "terminal", [GenerationRunStatus.COMPLETED, GenerationRunStatus.FAILED]
    )
    def test_terminal_run_is_never_stale_however_old(
        self, terminal: GenerationRunStatus
    ) -> None:
        run = create_candidate_generation_run(
            status=terminal, updated_at=datetime.now(UTC) - timedelta(days=3)
        )
        assert CandidateGenerationRunRepository.is_stale(run) is False


def _set_columns(sql: str) -> set[str]:
    match = re.search(r"\bset\b(.*?)\bwhere\b", sql, re.IGNORECASE | re.DOTALL)
    assert match, f"no SET ... WHERE in statement: {sql}"
    return {c.lower() for c in re.findall(r"([a-z_]+)\s*=", match.group(1), re.I)}


async def _capture_update(
    call: Any,
) -> tuple[str, dict[str, Any]]:
    """Run a repository write against a fake session; return its UPDATE SQL + params."""
    captured: list[tuple[str, dict[str, Any]]] = []

    async def _execute(stmt: Any, *a: Any, **kw: Any) -> Any:
        compiled = stmt.compile(dialect=postgresql.dialect())
        text = str(compiled).lower()
        if text.strip().startswith("update"):
            captured.append((text, dict(compiled.params)))
        return MagicMock()

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    await call(session)
    assert len(captured) == 1, "expected exactly one UPDATE"
    return captured[0]


@pytest.mark.asyncio
class TestTerminalTransitionSetClauses:
    async def test_finish_sets_status_progress_counts_and_completion(self) -> None:
        repo = CandidateGenerationRunRepository()
        run_id = uuid.uuid4()

        sql, params = await _capture_update(
            lambda s: repo.finish(
                s,
                run_id=run_id,
                candidates_discovered=7,
                candidates_upserted=6,
                superseded=1,
                pending_total=5,
                by_triage={"worth_review": 5},
                empty_reason=None,
            )
        )

        assert {
            "status",
            "progress_percent",
            "candidates_discovered",
            "candidates_upserted",
            "superseded",
            "pending_total",
            "by_triage",
            "empty_reason",
            "completed_at",
            "updated_at",
        } <= _set_columns(sql)
        assert params["status"] == "completed"
        assert params["progress_percent"] == 100
        assert params["candidates_discovered"] == 7
        assert params["candidates_upserted"] == 6
        assert params["superseded"] == 1
        assert params["pending_total"] == 5
        assert params["by_triage"] == {"worth_review": 5}
        assert run_id in params.values(), "UPDATE must be scoped to the run id"

    async def test_fail_sets_status_error_and_completion_only(self) -> None:
        repo = CandidateGenerationRunRepository()
        run_id = uuid.uuid4()

        sql, params = await _capture_update(
            lambda s: repo.fail(s, run_id=run_id, error="boom")
        )

        columns = _set_columns(sql)
        assert {"status", "error", "completed_at", "updated_at"} <= columns
        assert "progress_percent" not in columns, "a failure must not claim 100%"
        assert params["status"] == "failed"
        assert params["error"] == "boom"
        assert run_id in params.values()

    async def test_record_progress_bumps_the_heartbeat(self) -> None:
        repo = CandidateGenerationRunRepository()

        sql, params = await _capture_update(
            lambda s: repo.record_progress(s, run_id=uuid.uuid4(), progress_percent=42)
        )

        # FR-025 reads updated_at; a Core UPDATE does not fire ORM onupdate.
        assert {"progress_percent", "updated_at"} <= _set_columns(sql)
        assert params["progress_percent"] == 42
