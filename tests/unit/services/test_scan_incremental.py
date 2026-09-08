"""Unit tests for the resumable / incremental-commit scan spine (#291, T005).

Covers the loop mechanics at mock level: resume_from start, per-batch commit,
cursor advance + checkpoint callback, cooperative stop, completed flag, and
dry-run leaving no commit/cursor. Real-DB behavior is covered by the [SEAM]
integration tests.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _service() -> Any:
    from chronovista.services.entity_mention_scan_service import (
        EntityMentionScanService,
    )

    return EntityMentionScanService(session_factory=MagicMock())


def _session() -> AsyncMock:
    s = AsyncMock()
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    s.flush = AsyncMock()
    return s


def _factory(session: AsyncMock) -> Any:
    class _CM:
        async def __aenter__(self) -> AsyncMock:
            return session

        async def __aexit__(self, *a: object) -> bool:
            return False

    return lambda: _CM()


def _pattern(entity_id: Any) -> Any:
    import re as _re

    from chronovista.services.entity_mention_scan_service import _EntityPattern

    return _EntityPattern(
        entity_id=entity_id,
        canonical_name="Acme",
        entity_type="organization",
        pg_pattern=_re.escape("Acme"),
        alias_names=["Acme"],
    )


def _seg(seg_id: int) -> MagicMock:
    m = MagicMock()
    m.id = seg_id
    return m


def _wire(svc: Any) -> None:
    svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=0)
    svc._mention_repo.update_entity_counters = AsyncMock()
    svc._mention_repo.update_alias_counters = AsyncMock()
    svc._mention_repo.delete_transcript_mentions_by_segments = AsyncMock(return_value=0)
    svc._mention_repo.entities_with_transcript_mentions_in_segments = AsyncMock(
        return_value=[]
    )


class TestResumeFrom:
    async def test_resume_from_used_as_first_cursor(self) -> None:
        import uuid

        svc = _service()
        session = _session()
        svc._session_factory = _factory(session)
        _wire(svc)
        fetch = AsyncMock(side_effect=[[]])  # immediately empty
        with (
            patch.object(
                svc, "_load_entity_patterns", return_value=[_pattern(uuid.uuid4())]
            ),
            patch.object(svc, "_fetch_segment_batch", fetch),
        ):
            result = await svc.scan(resume_from=500, dry_run=False)
        assert fetch.call_args.kwargs["after_id"] == 500
        assert result.completed is True  # empty fetch = exhausted


class TestPerBatchCommitAndCursor:
    async def test_commits_per_batch_and_advances_cursor(self) -> None:
        import uuid

        svc = _service()
        session = _session()
        svc._session_factory = _factory(session)
        _wire(svc)
        checkpoints: list[int] = []
        fetch = AsyncMock(side_effect=[[_seg(10), _seg(11)], [_seg(20)], []])
        with (
            patch.object(
                svc, "_load_entity_patterns", return_value=[_pattern(uuid.uuid4())]
            ),
            patch.object(svc, "_fetch_segment_batch", fetch),
            patch.object(svc, "_scan_batch", AsyncMock(return_value=([], 0, [], 0, 0))),
        ):
            result = await svc.scan(
                dry_run=False, checkpoint_callback=checkpoints.append
            )
        # two non-empty batches -> two commits, cursor advanced to last id
        assert session.commit.await_count == 2
        assert result.last_processed_id == 20
        assert result.completed is True
        assert checkpoints == [11, 20]  # persisted only after each commit


class TestCooperativeStop:
    async def test_stop_after_first_batch(self) -> None:
        import uuid

        svc = _service()
        session = _session()
        svc._session_factory = _factory(session)
        _wire(svc)
        # should_continue returns False after the first batch
        calls = {"n": 0}

        def _cont() -> bool:
            calls["n"] += 1
            return False  # stop immediately after batch 1

        fetch = AsyncMock(side_effect=[[_seg(10)], [_seg(20)], []])
        with (
            patch.object(
                svc, "_load_entity_patterns", return_value=[_pattern(uuid.uuid4())]
            ),
            patch.object(svc, "_fetch_segment_batch", fetch),
            patch.object(svc, "_scan_batch", AsyncMock(return_value=([], 0, [], 0, 0))),
        ):
            result = await svc.scan(dry_run=False, should_continue=_cont)
        assert result.completed is False  # stopped early
        assert result.last_processed_id == 10  # only first batch committed
        assert session.commit.await_count == 1


class TestDryRunUnchanged:
    async def test_dry_run_no_commit_no_cursor(self) -> None:
        import uuid

        svc = _service()
        session = _session()
        svc._session_factory = _factory(session)
        _wire(svc)
        checkpoints: list[int] = []
        fetch = AsyncMock(side_effect=[[_seg(10)], []])
        with (
            patch.object(
                svc, "_load_entity_patterns", return_value=[_pattern(uuid.uuid4())]
            ),
            patch.object(svc, "_fetch_segment_batch", fetch),
            patch.object(svc, "_scan_batch", AsyncMock(return_value=([], 0, [], 0, 0))),
        ):
            result = await svc.scan(
                dry_run=True, checkpoint_callback=checkpoints.append
            )
        session.commit.assert_not_called()
        assert checkpoints == []
        assert result.dry_run is True
