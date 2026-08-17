"""SET-clause guard for NamedEntityRepository.replace_enrichment (Feature 067, ST-001).

Constitution Cross-Feature Data Contract §4: a mutation's mock test MUST inspect the actual
SQL SET clause, not just return values. This guards FR-006 — the enrichment load writes ONLY
``properties`` and ``external_ids`` and NEVER the human-authored display fields (Feature 057:
canonical_name, canonical_name_normalized, description). A regression that adds a display
column to the write would be invisible to a return-value assertion but caught here.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.repositories.named_entity_repository import NamedEntityRepository

pytestmark = pytest.mark.asyncio


async def _capture_update_sql() -> str:
    """Run replace_enrichment against a recording mock; return the compiled UPDATE SQL."""
    session = AsyncMock()
    captured: list[Any] = []

    async def _execute(stmt: Any, *a: Any, **k: Any) -> MagicMock:
        captured.append(stmt)
        result = MagicMock()
        result.rowcount = 1
        return result

    session.execute = _execute
    await NamedEntityRepository().replace_enrichment(
        session,
        uuid.uuid4(),
        properties={"occupation": {"values": ["x"], "qids": ["Q1"]}},
        external_ids={
            "wikidata": {"id": "Q1", "verified": False, "status": "confirmed"}
        },
    )
    assert len(captured) == 1, "replace_enrichment must issue exactly one statement"
    return str(captured[0].compile(compile_kwargs={"literal_binds": False}))


class TestReplaceEnrichmentSetClause:
    async def test_writes_only_enrichment_columns(self) -> None:
        sql = (await _capture_update_sql()).lower()
        assert sql.startswith("update named_entities"), sql[:60]
        assert "set" in sql
        assert "properties=" in sql.replace(" ", "")
        assert "external_ids=" in sql.replace(" ", "")

    async def test_never_writes_display_fields(self) -> None:
        """FR-006: the display fields owned by Feature 057 must NOT be in the SET clause."""
        sql = (await _capture_update_sql()).lower()
        # SQLAlchemy renders the SET clause before the WHERE; only inspect assignments.
        set_clause = sql.split(" where ")[0]
        for forbidden in (
            "canonical_name",
            "canonical_name_normalized",
            "description",
        ):
            assert (
                forbidden not in set_clause
            ), f"{forbidden} must not be written by the load"

    async def test_targets_by_id(self) -> None:
        sql = (await _capture_update_sql()).lower()
        assert " where " in sql and "named_entities.id" in sql
