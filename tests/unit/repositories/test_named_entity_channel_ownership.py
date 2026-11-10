"""Tests for the channel-ownership read methods (ownership promotion, read-path).

``operators_of_channel`` is checked as a SQL artifact (the compiled statement), mirroring
``test_named_entity_inbound_relations``; ``channels_operated_by`` and the empty short-circuits
are checked behaviourally against a mock session. No schema, no migration — these read the
existing ``named_entities.properties`` JSONB only.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.named_entity_repository import NamedEntityRepository

pytestmark = pytest.mark.asyncio


async def _operators_compiled(channel_id: str) -> tuple[str, dict[str, object]]:
    """Return (compiled SQL, bound params) for the operators query with no matches."""
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result
    out = await NamedEntityRepository().operators_of_channel(session, channel_id)
    assert out == []
    session.execute.assert_awaited_once()
    stmt = session.execute.await_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    return str(compiled), dict(compiled.params)


async def test_operators_empty_channel_short_circuits() -> None:
    session = AsyncMock(spec=AsyncSession)
    assert await NamedEntityRepository().operators_of_channel(session, "") == []
    session.execute.assert_not_awaited()


async def test_operators_values_containment_active_order() -> None:
    sql, params = await _operators_compiled("UCabc")
    low = sql.lower()
    # Array containment, JSONB-cast — NOT a scalar/LIKE.
    assert "@>" in sql
    assert "::jsonb" in low
    # The JSONB path keys compile as bound params; assert on them, not the SQL text.
    pvals = list(params.values())
    assert "youtube_channel_id" in pvals  # the identifier property
    assert "values" in pvals  # its `values` array ...
    assert "qids" not in pvals  # ... not a relation's `qids`
    assert [
        "UCabc"
    ] in pvals  # containment value is the channel id, as a 1-element array
    # Active-only.
    assert "status" in low
    # Stable total order: lower(canonical_name) then id.
    order = sql.split("ORDER BY", 1)[1].lower()
    assert "lower(" in order and "canonical_name" in order and "id" in order


async def test_operators_not_person_scoped() -> None:
    # Ownership spans all entity types (person, org, ...) — the query must not filter entity_type
    # in its WHERE clause. (entity_type still appears in the SELECT list; we check the predicate.)
    sql, _ = await _operators_compiled("UCabc")
    where_clause = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0].lower()
    assert "entity_type" not in where_clause


async def test_operators_maps_rows() -> None:
    session = AsyncMock(spec=AsyncSession)
    row = MagicMock()
    row.id = uuid.uuid4()
    row.entity_type = "organization"  # an org operator — ownership is not person-scoped
    row.canonical_name = "placeholder"
    result = MagicMock()
    result.all.return_value = [row]
    session.execute.return_value = result
    out = await NamedEntityRepository().operators_of_channel(session, "UCabc")
    assert len(out) == 1
    assert out[0].entity_id == row.id
    assert out[0].entity_type == "organization"
    assert out[0].canonical_name == "placeholder"


async def test_channels_operated_by_reads_values_and_drops_non_strings() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    # `properties` is an open bag: a stray non-string must be dropped, not 500 the caller.
    result.scalar_one_or_none.return_value = ["UCaaa", "UCbbb", 42]
    session.execute.return_value = result
    out = await NamedEntityRepository().channels_operated_by(session, uuid.uuid4())
    assert out == ["UCaaa", "UCbbb"]


async def test_channels_operated_by_absent_or_ungrounded_is_empty() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    # Entity absent OR present-but-no-identifier both yield NULL -> scalar_one_or_none() is None.
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    out = await NamedEntityRepository().channels_operated_by(session, uuid.uuid4())
    assert out == []
