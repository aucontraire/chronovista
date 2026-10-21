"""Unit tests for scripts/utilities/backfill_entity_categories.py (Feature 084).

Covers the argument parser's safety defaults, the QID extractor, and the two irreversible-write
guards (dry-run writes nothing; --apply refuses on a target mismatch). The script bootstraps
``src/`` on import, so a direct import works. Category names are neutral placeholders
(Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.utilities import backfill_entity_categories as bec
from scripts.utilities.backfill_entity_categories import build_parser, qid_of


class TestParserDefaults:
    def test_default_is_dry_run(self) -> None:
        args = build_parser().parse_args([])
        assert args.apply is False
        assert args.confirm_target is None

    def test_apply_and_confirm_target(self) -> None:
        args = build_parser().parse_args(["--apply", "--confirm-target", "chronovista"])
        assert args.apply is True
        assert args.confirm_target == "chronovista"


class TestQidOf:
    def test_extracts_qid(self) -> None:
        assert qid_of({"wikidata": {"id": "Q42"}}) == "Q42"

    def test_missing_or_malformed_is_none(self) -> None:
        assert qid_of({}) is None
        assert qid_of({"wikidata": {}}) is None
        assert qid_of({"wikidata": "Q1"}) is None
        assert qid_of({"wikidata": {"id": ""}}) is None


def _result(scalar: object = None) -> MagicMock:
    r = MagicMock()
    r.scalar_one.return_value = scalar
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
        # First session reads current_database() then the grounded count.
        session.execute = AsyncMock(
            side_effect=[_result(scalar="prod_db"), _result(scalar=0)]
        )
        session.rollback = AsyncMock()
        session.commit = AsyncMock()

        with (
            patch.object(
                bec.db_manager, "session", lambda echo=False: _FakeSessionCtx(session)
            ),
            patch.object(bec, "build_plan", AsyncMock()) as build_plan,
        ):
            code = await bec.run_backfill(apply=True, confirm_target="wrong_db")

        assert code == 2  # refused before any planning or writing
        build_plan.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_dry_run_writes_nothing(self) -> None:
        session = MagicMock()
        session.execute = AsyncMock(
            side_effect=[_result(scalar="testdb"), _result(scalar=0)]
        )
        session.rollback = AsyncMock()
        session.commit = AsyncMock()

        with (
            patch.object(
                bec.db_manager, "session", lambda echo=False: _FakeSessionCtx(session)
            ),
            patch.object(
                bec, "build_plan", AsyncMock(return_value=bec._Plan())
            ) as build_plan,
            patch.object(bec, "_apply", AsyncMock()) as apply_fn,
        ):
            code = await bec.run_backfill(apply=False, confirm_target=None)

        assert code == 0
        build_plan.assert_awaited_once()  # planning (read-only) runs
        apply_fn.assert_not_awaited()  # but no write path
        session.commit.assert_not_awaited()


class _StubFetch:
    def __init__(self, preset: dict[str, list[str]]) -> None:
        self._preset = preset

    async def categories_for_titles(self, titles: Any) -> dict[str, list[str]]:
        return {t: self._preset[t] for t in titles if t in self._preset}


class _StubResolver:
    async def resolve(self, qid: str) -> tuple[str, str] | None:  # pragma: no cover
        return None


class _StubSizes:
    async def sizes_for(self, names: Any) -> dict[str, int]:
        return {}


class _DetachOnClose:
    """A fake ORM row that detaches when the session context closes.

    Reproduces ``NamedEntityDB`` behavior: reading an attribute after the owning session closes
    raises (SQLAlchemy would raise DetachedInstanceError). This is what guards against regressing
    to holding ORM instances past the ``async with`` — an inert SimpleNamespace would not.
    """

    def __init__(self, external_ids: dict[str, Any]) -> None:
        self._id = uuid.uuid4()
        self._external_ids = external_ids
        self.attached = True

    @property
    def id(self) -> uuid.UUID:
        if not self.attached:
            raise RuntimeError(
                "DetachedInstanceError (simulated): .id after session close"
            )
        return self._id

    @property
    def external_ids(self) -> dict[str, Any]:
        if not self.attached:
            raise RuntimeError(
                "DetachedInstanceError (simulated): .external_ids after session close"
            )
        return self._external_ids


class _DetachingSessionCtx:
    """Async context manager that detaches its entities on exit (like a closing ORM session)."""

    def __init__(self, session: Any, entities: list[_DetachOnClose]) -> None:
        self._session = session
        self._entities = entities

    async def __aenter__(self) -> Any:
        return self._session

    async def __aexit__(self, *exc: object) -> bool:
        for entity in self._entities:
            entity.attached = False
        return False


@pytest.mark.asyncio
class TestBuildPlanClassification:
    """Exercise the REAL build_plan wiring (not a mock): each entity lands in the right bucket,
    and the ORM rows are read before the session closes (DetachedInstanceError regression).
    """

    async def test_classifies_every_bucket(self) -> None:
        iri = "http://dbpedia.org/resource/"
        e_add = _DetachOnClose({"dbpedia": {"id": f"{iri}Title_1"}})
        e_done = _DetachOnClose({"dbpedia": {"id": f"{iri}Title_2"}})
        e_replace = _DetachOnClose({"dbpedia": {"id": f"{iri}Title_3"}})  # → replace
        e_replace_empty = _DetachOnClose({"dbpedia": {"id": f"{iri}Title_4"}})  # kept
        e_unresolvable = _DetachOnClose({})  # no IRI, no QID
        e_omitted = _DetachOnClose({"dbpedia": {"id": f"{iri}Title_5"}})
        e_zero = _DetachOnClose({"dbpedia": {"id": f"{iri}Title_6"}})
        grounded = [
            e_add,
            e_done,
            e_replace,
            e_replace_empty,
            e_unresolvable,
            e_omitted,
            e_zero,
        ]
        # Capture ids up front — after build_plan runs, the session has closed and the fakes are
        # detached, so their .id would raise (which is exactly the behavior under test).
        add_id, done_id = e_add.id, e_done.id
        replace_id, replace_empty_id = e_replace.id, e_replace_empty.id

        entity_repo = MagicMock()
        entity_repo.list_wikidata_grounded = AsyncMock(return_value=grounded)

        existing = {
            done_id: {"wikipedia"},
            replace_id: {"dbpedia"},
            replace_empty_id: {"dbpedia"},
        }
        old_cats = {replace_id: ["cat-old"], replace_empty_id: ["cat-keep"]}
        fetch = _StubFetch(
            {
                "Title_1": ["cat-x"],  # add
                "Title_3": ["cat-new"],  # replace: -cat-old +cat-new
                "Title_4": [],  # replace fetch empty → kept as-is
                "Title_6": [],  # add, zero categories
            }  # Title_5 omitted entirely
        )

        session = MagicMock()

        with (
            patch.object(
                bec.db_manager,
                "session",
                lambda echo=False: _DetachingSessionCtx(session, grounded),
            ),
            patch.object(bec, "sources_by_entity", AsyncMock(return_value=existing)),
            patch.object(
                bec, "old_categories_by_entity", AsyncMock(return_value=old_cats)
            ),
        ):
            plan = await bec.build_plan(
                entity_repo=entity_repo,
                resolver=_StubResolver(),  # type: ignore[arg-type]
                fetch_service=fetch,  # type: ignore[arg-type]
                size_service=_StubSizes(),  # type: ignore[arg-type]
            )

        # The entities are now detached — build_plan must have read them before the close.
        assert not e_add.attached

        # add cohort
        assert [eid for eid, _t, _n in plan.to_add] == [add_id]
        assert plan.to_add[0][2] == ["cat-x"]
        assert plan.zero_categories == 1  # e_zero
        assert plan.fetch_omitted == 1  # e_omitted
        # replace cohort
        assert [eid for eid, _t, _n, _o in plan.to_replace] == [replace_id]
        assert plan.to_replace[0][2] == ["cat-new"]  # new names
        assert plan.to_replace[0][3] == ["cat-old"]  # old names captured for reversal
        assert (
            plan.replace_skipped_empty == 1
        )  # e_replace_empty kept (never replace-to-empty)
        assert (plan.diff_added, plan.diff_removed, plan.diff_unchanged) == (1, 1, 0)
        # untouched cohorts
        assert plan.skipped_done == 1  # e_done
        assert plan.unresolvable == 1  # e_unresolvable


@pytest.mark.asyncio
class TestApplyCapture:
    """The capture must record the REMOVED rows of the 373 replace, not only inserts (FR-009)."""

    async def test_capture_includes_before_after_and_diff(self, tmp_path: Any) -> None:
        plan = bec._Plan()
        add_id = uuid.uuid4()
        rep_id = uuid.uuid4()
        plan.to_add = [(add_id, "Title_1", ["cat-x"])]
        plan.to_replace = [
            (rep_id, "Title_3", ["cat-new", "cat-keep"], ["cat-old", "cat-keep"])
        ]
        plan.diff_added, plan.diff_removed, plan.diff_unchanged = 1, 1, 1

        session = MagicMock()
        session.commit = AsyncMock()

        with (
            patch.object(
                bec.db_manager, "session", lambda echo=False: _FakeSessionCtx(session)
            ),
            patch.object(bec, "store_categories_for_entity", AsyncMock()) as store,
            patch.object(bec, "_CAPTURE_DIR", tmp_path),
        ):
            await bec._apply(
                plan, "testdb", cat_repo=MagicMock(), assign_repo=MagicMock()
            )

        # add + replace both written; the replace used replace=True (delete-then-add).
        replace_calls = [
            c for c in store.await_args_list if c.kwargs.get("replace") is True
        ]
        assert len(replace_calls) == 1
        session.commit.assert_awaited_once()

        import json

        captures = list(tmp_path.glob("entity_category_backfill_capture_*.json"))
        assert len(captures) == 1
        data = json.loads(captures[0].read_text())
        assert data["assignments_inserted"] == [
            {"entity_id": str(add_id), "categories": ["cat-x"]}
        ]
        # The REMOVED rows (before) are captured for reversal, not only the inserts.
        assert data["assignments_replaced"] == [
            {
                "entity_id": str(rep_id),
                "before": ["cat-old", "cat-keep"],
                "after": ["cat-new", "cat-keep"],
            }
        ]
        assert data["diff"] == {"added": 1, "removed": 1, "unchanged": 1}
