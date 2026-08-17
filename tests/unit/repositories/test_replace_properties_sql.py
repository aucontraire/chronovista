"""SET-clause guard for NamedEntityRepository.replace_properties (Feature 068, T006 / D4).

Constitution Cross-Feature Data Contract §4: a mutation's mock test MUST inspect the actual SQL SET
clause, not just return values. This is the **anti-clobber guard** — the on-approval property write
must set ONLY ``properties`` and MUST NOT touch ``external_ids`` (the verified grounding identifier
set at create) nor the Feature 057 display fields. A regression that widened the write to
``external_ids`` would silently wipe the identifier and be invisible to a return-value assertion —
but caught here.
"""

from __future__ import annotations

import re
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.repositories.named_entity_repository import NamedEntityRepository

pytestmark = pytest.mark.asyncio


def _assigned_columns(sql: str) -> set[str]:
    """The set of column names on the left of each SET assignment."""
    set_clause = sql.lower().split(" where ")[0].split(" set ", 1)[1]
    return {m.group(1) for m in re.finditer(r"(\w+)\s*=", set_clause)}


async def _capture_update_sql() -> str:
    """Run replace_properties against a recording mock; return the compiled UPDATE SQL."""
    session = AsyncMock()
    captured: list[Any] = []

    async def _execute(stmt: Any, *a: Any, **k: Any) -> MagicMock:
        captured.append(stmt)
        result = MagicMock()
        result.rowcount = 1
        return result

    session.execute = _execute
    rowcount = await NamedEntityRepository().replace_properties(
        session,
        uuid.uuid4(),
        properties={
            "occupation": {"values": ["x"], "qids": ["Q1"], "source": "wikidata"}
        },
    )
    assert rowcount == 1
    assert len(captured) == 1, "replace_properties must issue exactly one statement"
    return str(captured[0].compile(compile_kwargs={"literal_binds": False}))


class TestReplacePropertiesSetClause:
    async def test_writes_only_properties(self) -> None:
        sql = (await _capture_update_sql()).lower()
        assert sql.startswith("update named_entities"), sql[:60]
        # The ONLY assigned columns are `properties` and the automatic `updated_at` bump.
        # A regression adding any other writable column (external_ids, status, ...) fails here.
        assert _assigned_columns(sql) == {"properties", "updated_at"}

    async def test_never_writes_external_ids(self) -> None:
        """The anti-clobber invariant: external_ids MUST NOT be in the SET clause (D4)."""
        sql = (await _capture_update_sql()).lower()
        set_clause = sql.split(" where ")[0]
        assert (
            "external_ids" not in set_clause
        ), "external_ids must not be clobbered by this write"

    async def test_never_writes_display_fields(self) -> None:
        """FR-008: Feature 057 display fields must NOT be in the SET clause."""
        sql = (await _capture_update_sql()).lower()
        set_clause = sql.split(" where ")[0]
        for forbidden in ("canonical_name", "canonical_name_normalized", "description"):
            assert forbidden not in set_clause, f"{forbidden} must not be written"

    async def test_targets_by_id(self) -> None:
        sql = (await _capture_update_sql()).lower()
        assert " where " in sql and "named_entities.id" in sql
