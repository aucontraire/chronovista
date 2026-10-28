"""SET-clause guard for ``CandidateSuggestionRepository.set_verdict`` (Feature 097).

Constitution (Cross-Feature Data Contract Verification, requirement 4): a mock test of an
UPDATE MUST inspect the emitted statement, not the return value. A fake session returns a
row regardless of which columns were written, so asserting on the return would pass even if
a verdict column were dropped. This captures the compiled UPDATE and asserts its SET targets
and its compare-and-set guard. No DB.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from chronovista.models.enums import ReviewStatus
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)

pytestmark = pytest.mark.asyncio


def _set_columns(sql: str) -> set[str]:
    """Extract the column names in an UPDATE ... SET <cols> WHERE clause."""
    match = re.search(r"\bset\b(.*?)\bwhere\b", sql, re.IGNORECASE | re.DOTALL)
    assert match, f"no SET ... WHERE in statement: {sql}"
    return {c.lower() for c in re.findall(r"([a-z_]+)\s*=", match.group(1), re.I)}


async def _capture_update(
    created_entity_id: uuid.UUID | None,
) -> tuple[str, dict[str, Any]]:
    """Run set_verdict against a fake session; return the UPDATE SQL and its params."""
    captured: list[tuple[str, dict[str, Any]]] = []

    async def _execute(stmt: Any, *a: Any, **kw: Any) -> Any:
        compiled = stmt.compile(dialect=postgresql.dialect())
        text = str(compiled).lower()
        if text.strip().startswith("update"):
            captured.append((text, dict(compiled.params)))
        result = MagicMock()
        result.rowcount = 1
        result.scalar_one_or_none.return_value = None
        return result

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)

    await CandidateSuggestionRepository().set_verdict(
        session,
        candidate_id=uuid.uuid4(),
        review_status=ReviewStatus.APPROVED,
        reviewed_by="reviewer-x",
        reviewed_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_entity_id=created_entity_id,
    )
    assert len(captured) == 1, "set_verdict must issue exactly one UPDATE"
    return captured[0]


class TestSetVerdictSetClause:
    async def test_approval_update_sets_every_verdict_column(self) -> None:
        entity_id = uuid.uuid4()
        sql, params = await _capture_update(entity_id)

        columns = _set_columns(sql)
        assert {
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "created_entity_id",
        } <= columns, f"verdict column missing from SET: {columns}"

        # Bound values, not just column names: the right values reach the right columns.
        assert params["review_status"] == "approved"
        assert params["reviewed_by"] == "reviewer-x"
        assert params["reviewed_at"] == datetime(2026, 1, 1, tzinfo=UTC)
        assert params["created_entity_id"] == entity_id

    async def test_update_is_guarded_by_pending_status(self) -> None:
        sql, params = await _capture_update(uuid.uuid4())
        where = sql.split(" where ", 1)[1]
        assert "review_status" in where and "pending" in params.values()

    async def test_reject_leaves_created_entity_id_out_of_set(self) -> None:
        sql, _ = await _capture_update(None)
        columns = _set_columns(sql)
        assert "created_entity_id" not in columns
        assert {"review_status", "reviewed_by", "reviewed_at"} <= columns
