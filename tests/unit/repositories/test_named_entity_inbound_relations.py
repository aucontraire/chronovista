"""SQL-artifact tests for NamedEntityRepository.inbound_relations (Feature 087).

A mock session captures the emitted statement; assertions inspect the compiled SQL rather than the
mock return value.
"""

from __future__ import annotations

import uuid
from typing import Any
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


async def test_credit_fields_spanned_by_query() -> None:
    # Feature 088 — the credit fields flow through INBOUND_FIELDS into the same query, no shape change:
    # each is OR-ed into the WHERE as a JSONB `@>` containment and labelled in the SELECT.
    sql = await _sql(INBOUND_FIELDS)
    for field in ("cast_member", "director", "producer", "screenwriter", "composer"):
        assert field in sql, field
    # still one containment form, still active-only
    assert "@>" in sql and "status" in sql.lower()


async def test_instance_of_selected(self=None) -> None:
    # Feature 088 — the referencing entity's instance_of labels are SELECTed for the type filter.
    sql = await _sql(INBOUND_FIELDS)
    assert "instance_of" in sql


async def _one_match(instance_of_values: Any) -> list[Any]:
    """Drive inbound_relations with a single matching row carrying the given instance_of payload."""
    session = AsyncMock(spec=AsyncSession)
    row = MagicMock()
    row.id = uuid.uuid4()
    row.entity_type = "work"
    row.canonical_name = "placeholder"
    mapping: dict[str, Any] = dict.fromkeys(INBOUND_FIELDS, False)
    mapping["cast_member"] = True  # one credit match
    mapping["instance_of_values"] = instance_of_values
    row._mapping = mapping
    result = MagicMock()
    result.all.return_value = [row]
    session.execute.return_value = result
    return await NamedEntityRepository().inbound_relations(
        session, "Q42", INBOUND_FIELDS
    )


async def test_row_instance_of_deduped() -> None:
    out = await _one_match(["film", "film", "television series"])
    assert len(out) == 1
    assert out[0].instance_of == [
        "film",
        "television series",
    ]  # de-duplicated, order preserved
    assert out[0].matched_fields == ["cast_member"]


async def test_row_instance_of_absent_is_empty_list() -> None:
    out = await _one_match(None)  # path NULL — entity has no instance_of
    assert out[0].instance_of == []


async def test_row_instance_of_filters_non_strings() -> None:
    # Robustness: `properties` is an open bag — a stray non-string (or unhashable value) must not
    # 500 the endpoint; only string labels survive, de-duplicated.
    out = await _one_match(["film", 42, {"nested": 1}, "film"])
    assert out[0].instance_of == ["film"]


async def test_reserved_select_labels_do_not_collide_with_inbound_fields() -> None:
    # Future-proofing: the SELECT's fixed labels must stay disjoint from the group field names, or
    # `row._mapping[...]` would become ambiguous.
    reserved = {"instance_of_values", "id", "entity_type", "canonical_name"}
    assert reserved.isdisjoint(INBOUND_FIELDS)
