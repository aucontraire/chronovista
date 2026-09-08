"""Unit tests for the whitespace-normalization backfill (Feature 076 / #293, US3).

Uses scripted fake sessions so the multi-session flow (candidate query, then a
per-video session) is exercised without a DB. Verifies the core guarantees:
dry-run writes nothing; apply updates only changed segments' `text` and
re-scans with full_rescan=True; the UPDATE's SET touches `text` only.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from chronovista.services.transcript_whitespace_service import (
    _ARTIFACT_CLASS,
    TranscriptWhitespaceBackfillService,
    WhitespaceBackfillSummary,
)

pytestmark = pytest.mark.asyncio


class _Result:
    def __init__(self, *, rows: list[Any] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def all(self) -> list[Any]:
        return self._rows

    def scalars(self) -> _Result:
        return self

    def scalar_one(self) -> Any:
        return self._scalar


class _FakeSession:
    def __init__(self, results: list[_Result]) -> None:
        self._results = list(results)
        self.executed: list[Any] = []
        self.commits = 0

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def execute(self, stmt: Any, *a: Any, **k: Any) -> _Result:
        self.executed.append(stmt)
        return self._results.pop(0) if self._results else _Result()

    async def commit(self) -> None:
        self.commits += 1


def _factory(sessions: list[_FakeSession]):
    it = iter(sessions)

    def _make() -> _FakeSession:
        return next(it)

    return _make


def _stmt_is_update(stmt: Any) -> bool:
    return type(stmt).__name__ == "Update"


class TestArtifactClass:
    def test_class_contains_newline_nbsp_zerowidth(self) -> None:
        assert "\n" in _ARTIFACT_CLASS
        assert chr(0x00A0) in _ARTIFACT_CLASS  # nbsp
        assert chr(0x200B) in _ARTIFACT_CLASS  # zwsp
        assert chr(0x00AD) in _ARTIFACT_CLASS  # soft hyphen
        assert _ARTIFACT_CLASS != " "  # a plain space is not, on its own, listed


class TestCandidateShortcut:
    async def test_single_video_id_shortcut_runs_no_query(self) -> None:
        svc = TranscriptWhitespaceBackfillService(
            _factory([]), scan_service=AsyncMock()
        )
        # candidate resolution with an explicit video_id must not touch the DB
        session = _FakeSession([])
        ids = await svc._candidate_video_ids(session, video_id="vidX", limit=None)
        assert ids == ["vidX"]
        assert session.executed == []


class TestDryRun:
    async def test_dry_run_writes_nothing(self) -> None:
        scan = AsyncMock()
        # candidate session: seg ids {v1}, mention ids {}
        cand = _FakeSession([_Result(rows=["v1"]), _Result(rows=[])])
        # per-video session: rows (id, text) then the rule_match count
        pv = _FakeSession(
            [
                _Result(rows=[(1, "foo\nbar"), (2, "clean text")]),
                _Result(scalar=3),  # existing rule_match mentions
            ]
        )
        svc = TranscriptWhitespaceBackfillService(
            _factory([cand, pv]), scan_service=scan
        )
        summary = await svc.run(apply=False)

        assert isinstance(summary, WhitespaceBackfillSummary)
        assert summary.dry_run is True
        assert summary.segments_normalized == 1  # only seg 1 changes
        assert summary.mentions_regenerated == 3  # projected
        assert pv.commits == 0
        assert not any(_stmt_is_update(s) for s in pv.executed)
        scan.scan.assert_not_called()


class TestApply:
    async def test_apply_updates_only_changed_and_rescans(self) -> None:
        scan = AsyncMock()
        scan.scan.return_value = type("R", (), {"mentions_found": 5})()
        rebuilt: list[str] = []

        async def _rebuild(vid: str) -> None:
            rebuilt.append(vid)

        cand = _FakeSession([_Result(rows=["v1"]), _Result(rows=[])])
        pv = _FakeSession([_Result(rows=[(1, "foo\nbar"), (2, "clean text")])])
        svc = TranscriptWhitespaceBackfillService(
            _factory([cand, pv]), scan_service=scan, rebuild_text=_rebuild
        )
        summary = await svc.run(apply=True)

        assert summary.dry_run is False
        assert summary.segments_normalized == 1
        # exactly one UPDATE (for the changed segment), then a commit
        updates = [s for s in pv.executed if _stmt_is_update(s)]
        assert len(updates) == 1
        assert pv.commits == 1
        # re-scan called for the video with full_rescan
        scan.scan.assert_awaited_once()
        assert scan.scan.await_args.kwargs["video_ids"] == ["v1"]
        assert scan.scan.await_args.kwargs["full_rescan"] is True
        assert summary.mentions_regenerated == 5
        assert rebuilt == ["v1"]

    async def test_update_set_touches_text_only(self) -> None:
        scan = AsyncMock()
        scan.scan.return_value = type("R", (), {"mentions_found": 0})()
        cand = _FakeSession([_Result(rows=["v1"]), _Result(rows=[])])
        pv = _FakeSession([_Result(rows=[(1, "a\nb")])])
        svc = TranscriptWhitespaceBackfillService(
            _factory([cand, pv]), scan_service=scan
        )
        await svc.run(apply=True)

        update_stmt = next(s for s in pv.executed if _stmt_is_update(s))
        compiled = str(update_stmt).lower()
        assert "set" in compiled and "text" in compiled
        assert "corrected_text" not in compiled
        assert "transcript_corrections" not in compiled

    async def test_no_changed_segments_skips_rescan(self) -> None:
        scan = AsyncMock()
        cand = _FakeSession([_Result(rows=["v1"]), _Result(rows=[])])
        pv = _FakeSession([_Result(rows=[(1, "already clean")])])
        svc = TranscriptWhitespaceBackfillService(
            _factory([cand, pv]), scan_service=scan
        )
        summary = await svc.run(apply=True)

        assert summary.segments_normalized == 0
        assert pv.commits == 0
        scan.scan.assert_not_called()
