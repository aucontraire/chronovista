"""Unit tests for the backfill safety seam (Feature 087).

Two load-bearing guards: the write MERGES (preserves every other property — never a full replace),
and the patch filter distinguishes "source asserts nothing" from "new value to add" (idempotent,
absence-aware). The patch names are neutral placeholders.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.named_entity_repository import NamedEntityRepository

# Load the backfill script module (scripts/ is not a package) to test its pure patch filter.
_BF_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "utilities"
    / "backfill_entity_relations.py"
)
_spec = importlib.util.spec_from_file_location("_bf087", _BF_PATH)
assert _spec and _spec.loader
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


@pytest.mark.asyncio
class TestMergePropertiesIsAMergeNotReplace:
    async def test_set_clause_merges_with_pipe_pipe(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.rowcount = 1
        session.execute.return_value = result
        patch: dict[str, Any] = {"founder": {"qids": ["Q1"], "values": ["x"]}}
        await NamedEntityRepository().merge_properties(session, uuid.uuid4(), patch)
        compiled = session.execute.await_args.args[0].compile(
            dialect=postgresql.dialect()  # type: ignore[no-untyped-call]
        )
        set_clause = str(compiled).split("SET", 1)[1]
        # the whole point: `properties || :patch`, NOT `properties = :patch`
        assert "||" in set_clause
        assert "properties" in set_clause

    async def test_empty_patch_is_a_no_op_write(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        out = await NamedEntityRepository().merge_properties(session, uuid.uuid4(), {})
        assert out == 0
        session.execute.assert_not_awaited()  # no UPDATE at all for an empty patch


def _block(values: list[str], qids: list[str], set_at: str) -> dict[str, Any]:
    """A relation block in the stored shape (values + qids + wikidata provenance + timestamp)."""
    return {"values": values, "qids": qids, "source": "wikidata", "set_at": set_at}


class TestPatchFilter:
    def test_includes_new_asserted_fields_only(self) -> None:
        current = {
            "employer": _block(["x"], ["Q9"], "T0")
        }  # unrelated key; not a backfill field
        fetched = {
            "founder": _block(["a"], ["Q1"], "T1"),
            "significant_person": _block(["b"], ["Q2"], "T1"),
            "occupation": _block(["c"], [], "T1"),  # not a backfilled field
        }
        patch = backfill._patch_for(current, fetched)
        assert set(patch) == {
            "founder",
            "significant_person",
        }  # only the two, not occupation

    def test_absence_is_left_alone(self) -> None:
        # Source asserts no founder/significant_person → patch is empty (genuine absence preserved).
        assert backfill._patch_for({}, {"occupation": _block(["x"], [], "T1")}) == {}
        assert (
            backfill._patch_for({}, {"founder": {}}) == {}
        )  # empty block is not asserted

    def test_fresh_set_at_alone_is_a_no_op_idempotent(self) -> None:
        # THE finding-1 regression: a re-fetch stamps a new set_at but the same values + qids.
        # A whole-block `!=` would (wrongly) rewrite every entity forever; the patch must be empty.
        stored = _block(["a"], ["Q1"], "2026-01-01T00:00:00")
        refetched = _block(
            ["a"], ["Q1"], "2026-10-22T12:00:00"
        )  # later timestamp, same payload
        assert (
            stored != refetched
        )  # guard: the fixture really does differ (only in set_at)
        assert backfill._patch_for({"founder": stored}, {"founder": refetched}) == {}

    def test_changed_payload_is_included(self) -> None:
        # A genuine content change (new qid) IS applied, despite also having a new set_at.
        stored = _block(["a"], ["Q1"], "T0")
        refetched = _block(["a", "b"], ["Q1", "Q2"], "T1")
        assert backfill._patch_for({"founder": stored}, {"founder": refetched}) == {
            "founder": refetched
        }

    def test_non_wikidata_curation_is_not_clobbered(self) -> None:
        # A manually/other-pipeline curated block (source != wikidata) owns the key — never overwrite.
        manual = {
            "values": ["hand"],
            "qids": ["Q1"],
            "source": "manual",
            "set_at": "T0",
        }
        fetched = {"founder": _block(["auto"], ["Q2"], "T1")}
        assert backfill._patch_for({"founder": manual}, fetched) == {}
