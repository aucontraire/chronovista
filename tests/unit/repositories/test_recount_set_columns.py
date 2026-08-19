"""SET-clause column guard for the counter recompute (Feature 069, Cross-Feature contract).

The recount is a mutation of the stored counters. Its UPDATE statements MUST write ONLY the counter
columns and NEVER the human-authored display fields (canonical_name, canonical_name_normalized,
description, alias_name) — a stray column in the SET clause would silently overwrite curated data. Per
the constitution, mock tests for a mutation MUST inspect the SQL SET clause, not just return values.
This captures the compiled UPDATEs and asserts their SET targets. No DB.
"""

from __future__ import annotations

import re
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from chronovista.repositories.entity_mention_repository import EntityMentionRepository

pytestmark = pytest.mark.asyncio

_DISPLAY_FIELDS = {
    "canonical_name",
    "canonical_name_normalized",
    "description",
    "alias_name",
    "alias_name_normalized",
}


def _set_columns(sql: str) -> set[str]:
    """Extract the column names in an UPDATE ... SET <cols> = ... clause."""
    m = re.search(r"\bset\b(.*?)\bwhere\b", sql, re.IGNORECASE | re.DOTALL)
    body = m.group(1) if m else sql
    # column names are the identifiers immediately left of '=' in the SET body
    return {c.lower() for c in re.findall(r"([a-z_]+)\s*=", body, re.IGNORECASE)}


async def _capture_update_sql(method_name: str) -> list[str]:
    """Run a counter-update method against a fake session, capturing compiled UPDATE SQL."""
    captured: list[str] = []

    async def _execute(stmt: Any, *a: Any, **kw: Any) -> Any:
        text = str(stmt.compile(dialect=postgresql.dialect())).lower()
        if text.strip().startswith("update"):
            captured.append(text)
        result = AsyncMock()
        result.scalar_one.return_value = 0
        result.all.return_value = []
        result.first.return_value = None
        return result

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)

    repo = EntityMentionRepository()
    method = getattr(repo, method_name)
    await method(session, [uuid.uuid4()])
    return captured


class TestRecountSetColumns:
    async def test_entity_counter_update_sets_only_counter_columns(self) -> None:
        updates = await _capture_update_sql("update_entity_counters")
        assert updates, "expected at least one UPDATE from update_entity_counters"
        # The counter columns must be written; NO human-authored display field may be. An automatic
        # ``updated_at`` bump (ORM onupdate) is allowed — it is not a display field.
        counter_update = next(
            sql for sql in updates if "mention_count" in _set_columns(sql)
        )
        cols = _set_columns(counter_update)
        assert "mention_count" in cols and "video_count" in cols
        assert not (cols & _DISPLAY_FIELDS), f"display field in SET clause: {cols}"
        assert cols <= {
            "mention_count",
            "video_count",
            "updated_at",
        }, f"unexpected non-counter column in SET: {cols}"

    async def test_alias_counter_update_sets_only_occurrence_count(self) -> None:
        updates = await _capture_update_sql("update_alias_counters")
        assert updates, "expected at least one UPDATE from update_alias_counters"
        occ_update = next(
            sql for sql in updates if "occurrence_count" in _set_columns(sql)
        )
        cols = _set_columns(occ_update)
        assert "occurrence_count" in cols
        assert not (cols & _DISPLAY_FIELDS), f"display field in SET clause: {cols}"
        assert cols <= {
            "occurrence_count",
            "updated_at",
        }, f"unexpected non-counter column in SET: {cols}"
