"""Unit tests for `chronovista playlist reclassify` core logic (Feature 058, US2).

Targets the async `_reclassify` helper directly with a mock repository/session
so the promote-only, dry-run, idempotency, and interruption-safety guarantees
are unit-tested without a database.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from chronovista.cli.commands.playlist import _reclassify
from chronovista.models.enums import PlaylistType

pytestmark = pytest.mark.asyncio


def _pl(playlist_id: str, title: str) -> SimpleNamespace:
    return SimpleNamespace(playlist_id=playlist_id, title=title)


def _repo(regulars: list[SimpleNamespace]) -> AsyncMock:
    repo = AsyncMock()
    repo.get_playlists_by_type = AsyncMock(return_value=regulars)
    repo.promote_playlist_type = AsyncMock()
    return repo


async def test_dry_run_reports_counts_and_writes_nothing() -> None:
    repo = _repo([_pl("PL1", "Watch later"), _pl("PL2", "History"), _pl("PL3", "AI")])
    session = AsyncMock()

    counts = await _reclassify(session, repo, dry_run=True)

    assert counts == {"watch_later": 1, "history": 1}  # FR-007
    repo.promote_playlist_type.assert_not_awaited()
    session.commit.assert_not_awaited()


async def test_apply_promotes_matching_rows_and_commits() -> None:
    repo = _repo([_pl("PL1", "Watch later"), _pl("PL2", "History"), _pl("PL3", "AI")])
    session = AsyncMock()

    counts = await _reclassify(session, repo, dry_run=False)

    assert counts == {"watch_later": 1, "history": 1}  # FR-008
    assert repo.promote_playlist_type.await_count == 2  # only the 2 system-named
    session.commit.assert_awaited()


async def test_promote_only_loads_regular_set_exclusively() -> None:
    # FR-006: only REGULAR rows are ever fetched → non-regular rows untouched.
    repo = _repo([_pl("PL3", "AI")])
    session = AsyncMock()

    await _reclassify(session, repo, dry_run=False)

    repo.get_playlists_by_type.assert_awaited_once_with(session, PlaylistType.REGULAR)


async def test_idempotent_no_changes_when_no_system_named_regulars() -> None:
    repo = _repo([_pl("PL3", "AI"), _pl("PL4", "Cooking")])
    session = AsyncMock()

    counts = await _reclassify(session, repo, dry_run=False)

    assert counts == {}  # FR-009: second run (post-promotion) changes nothing
    repo.promote_playlist_type.assert_not_awaited()
    session.commit.assert_not_awaited()


async def test_dry_run_and_apply_report_identical_counts() -> None:
    rows = [_pl("PL1", "Watch later"), _pl("PL2", "History"), _pl("PL3", "AI")]
    dry = await _reclassify(AsyncMock(), _repo(list(rows)), dry_run=True)
    apply = await _reclassify(AsyncMock(), _repo(list(rows)), dry_run=False)
    assert dry == apply  # SC-003


async def test_interruption_safe_convergence() -> None:
    # FR-009 interruption-safety: WL was already promoted out-of-band (so it is
    # NOT in the regular set); a full run promotes the remaining regular (History)
    # and converges, leaving the already-promoted row untouched.
    repo = _repo([_pl("PL2", "History"), _pl("PL3", "AI")])
    session = AsyncMock()

    counts = await _reclassify(session, repo, dry_run=False)

    assert counts == {"history": 1}
    repo.promote_playlist_type.assert_awaited_once_with(
        session, "PL2", PlaylistType.HISTORY
    )
