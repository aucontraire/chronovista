"""CLI write-gating tests for `chronovista entities recount` (Feature 069, US2 / T020).

The recompute *correctness* is covered by the real-DB integration tests
(``test_accent_insensitive_membership.py::TestFoldedRecount``). This file covers the command wiring and
the write-gate: ``--dry-run`` must NOT commit; apply mode must. The command calls ``asyncio.run``
internally, so — like the other entity CLI tests — ``db_manager`` and the repository are mocked to
avoid a nested event loop; the assertion is on whether ``session.commit`` was awaited.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from chronovista.cli.main import app

runner = CliRunner()


def _make_get_session(mock_session: AsyncMock) -> Any:
    async def _gen(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    return _gen()


def _empty_result() -> MagicMock:
    """A result object that is empty both when iterated and via .all()."""
    result = MagicMock()
    result.__iter__ = lambda self: iter([])
    result.all.return_value = []
    return result


def _run_recount(*args: str) -> tuple[Any, AsyncMock]:
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=_empty_result())
    mock_session.commit = AsyncMock()

    with (
        patch("chronovista.cli.entity_commands.db_manager") as mock_db,
        patch("chronovista.cli.entity_commands.EntityMentionRepository") as MockRepo,
    ):
        mock_db.get_session.return_value = _make_get_session(mock_session)
        repo = AsyncMock()
        repo.update_entity_counters = AsyncMock(return_value=0)
        repo.update_alias_counters = AsyncMock(return_value=0)
        MockRepo.return_value = repo
        result = runner.invoke(app, ["entities", "recount", *args])
    return result, mock_session


class TestRecountCommand:
    def test_dry_run_rolls_back_and_does_not_commit(self) -> None:
        result, session = _run_recount("--dry-run")
        assert result.exit_code == 0, result.output
        # Dry-run must ROLL BACK explicitly (not merely skip commit) — get_session auto-commits on
        # scope exit, so a skipped commit alone would still persist. This is the deployment bug.
        assert session.rollback.await_count == 1
        assert session.commit.await_count == 0
        assert "dry run" in result.output.lower()

    def test_apply_commits_and_does_not_rollback(self) -> None:
        result, session = _run_recount()
        assert result.exit_code == 0, result.output
        assert session.commit.await_count == 1  # apply persists
        assert session.rollback.await_count == 0
        assert "complete" in result.output.lower()
