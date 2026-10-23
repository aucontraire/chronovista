"""SQL-artifact tests for NamedEntityRepository.inbound_relations (Feature 087).

A mock session captures the emitted statement; assertions inspect the compiled SQL rather than the
mock return value.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services.relation_groups import INBOUND_FIELDS

pytestmark = pytest.mark.asyncio


async def _sql(fields: tuple[str, ...]) -> str:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result
    out = await NamedEntityRepository().inbound_relations(session, "Q42", fields)
    assert out == []
    session.execute.assert_awaited_once()
    stmt = session.execute.await_args.args[0]
    return str(stmt.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


async def test_empty_inputs_short_circuit() -> None:
    session = AsyncMock(spec=AsyncSession)
    assert (
        await NamedEntityRepository().inbound_relations(session, "", INBOUND_FIELDS)
        == []
    )
    assert await NamedEntityRepository().inbound_relations(session, "Q1", ()) == []
    session.execute.assert_not_awaited()


async def test_active_containment_order() -> None:
    sql = await _sql(INBOUND_FIELDS)
    low = sql.lower()
    # JSONB array containment (GIN-friendly), not a scalar/LIKE
    assert "@>" in sql
    # active-only
    assert "status" in low
    # total order: lower(canonical_name) then id — stable
    order = sql.split("ORDER BY", 1)[1].lower()
    assert "lower(" in order and "canonical_name" in order and "id" in order
    # membership searches BOTH synonymous fields; employer present; country absent
    assert "member_of" in sql and "part_of" in sql and "employer" in sql
    assert "country" not in sql


async def test_single_statement_select(self=None) -> None:
    sql = await _sql(("employer",))
    assert sql.lstrip().upper().startswith("SELECT")
