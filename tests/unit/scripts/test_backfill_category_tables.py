"""Unit tests for scripts/utilities/backfill_category_tables.py (Feature 083).

Covers the pure parse logic (``extract_assignments``) — including the malformed-block edge
case — and the argument parser's safety defaults. The script bootstraps ``src/`` on import, so a
direct import works. All category names here are neutral placeholders (Constitution VI).
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.utilities import backfill_category_tables as bct
from scripts.utilities.backfill_category_tables import (  # noqa: E402
    build_parser,
    extract_assignments,
)


class TestExtractAssignments:
    def test_well_formed_block(self) -> None:
        props = {
            "category": {
                "values": ["cat-x", "cat-y"],
                "source": "dbpedia",
                "set_at": "2026-08-08T00:00:00+00:00",
            }
        }
        out = extract_assignments(props)
        assert [name for name, _s, _t in out] == ["cat-x", "cat-y"]
        assert {s for _n, s, _t in out} == {"dbpedia"}
        assert all(
            t == datetime.datetime(2026, 8, 8, tzinfo=datetime.UTC) for _n, _s, t in out
        )

    def test_missing_category_key(self) -> None:
        assert extract_assignments({"other": {"values": ["x"]}}) == []

    def test_block_not_a_dict(self) -> None:
        assert extract_assignments({"category": ["cat-x"]}) == []

    def test_values_not_a_list(self) -> None:
        assert extract_assignments({"category": {"values": "cat-x"}}) == []

    def test_non_string_values_filtered(self) -> None:
        props = {"category": {"values": ["cat-x", 42, None, ""], "source": "dbpedia"}}
        out = extract_assignments(props)
        assert [name for name, _s, _t in out] == ["cat-x"]

    def test_missing_source_defaults_unknown(self) -> None:
        out = extract_assignments({"category": {"values": ["cat-x"]}})
        assert out[0][1] == "unknown"

    def test_bad_set_at_is_none(self) -> None:
        out = extract_assignments(
            {
                "category": {
                    "values": ["cat-x"],
                    "source": "dbpedia",
                    "set_at": "not-a-date",
                }
            }
        )
        assert out[0][2] is None

    def test_empty_values(self) -> None:
        assert (
            extract_assignments({"category": {"values": [], "source": "dbpedia"}}) == []
        )


class TestParserDefaults:
    def test_default_is_dry_run(self) -> None:
        args = build_parser().parse_args([])
        assert args.apply is False
        assert args.fetch is True
        assert args.confirm_target is None

    def test_apply_and_confirm_target(self) -> None:
        args = build_parser().parse_args(["--apply", "--confirm-target", "chronovista"])
        assert args.apply is True
        assert args.confirm_target == "chronovista"

    def test_no_fetch(self) -> None:
        args = build_parser().parse_args(["--no-fetch"])
        assert args.fetch is False


def _result(scalar: object = None, rows: list[object] | None = None) -> MagicMock:
    r = MagicMock()
    r.scalar_one.return_value = scalar
    r.fetchall.return_value = rows or []
    return r


class _FakeSessionCtx:
    """Async context manager standing in for ``db_manager.session()`` (mirrors the real seam)."""

    def __init__(self, session: MagicMock) -> None:
        self._session = session

    async def __aenter__(self) -> MagicMock:
        return self._session

    async def __aexit__(self, *exc: object) -> bool:
        return False


@pytest.mark.asyncio
class TestRunBackfillSafety:
    """The two irreversible-write guards: dry-run writes nothing, apply confirms the target."""

    async def test_apply_refuses_on_target_mismatch(self) -> None:
        session = MagicMock()
        session.execute = AsyncMock(side_effect=[_result(scalar="prod_db")])
        session.commit = AsyncMock()

        with patch.object(
            bct.db_manager, "session", lambda echo=False: _FakeSessionCtx(session)
        ):
            code = await bct.run_backfill(
                apply=True, confirm_target="wrong_db", fetch=False
            )

        assert code == 2  # refused
        session.commit.assert_not_awaited()

    async def test_dry_run_writes_nothing(self) -> None:
        session = MagicMock()
        # 1st execute: current_database(); 2nd: the SELECT of named_entities rows (empty).
        session.execute = AsyncMock(
            side_effect=[_result(scalar="testdb"), _result(rows=[])]
        )
        session.commit = AsyncMock()

        with patch.object(
            bct.db_manager, "session", lambda echo=False: _FakeSessionCtx(session)
        ):
            code = await bct.run_backfill(apply=False, confirm_target=None, fetch=False)

        assert code == 0
        session.commit.assert_not_awaited()
