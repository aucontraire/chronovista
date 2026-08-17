"""Merge guard for NamedEntityRepository.add_external_id (on-approval DBpedia).

The write must ADD a key to ``external_ids`` via a JSONB merge (``external_ids = external_ids || ...``)
rather than replacing the whole column — otherwise adding a DBpedia link would clobber the verified
Wikidata identifier. This inspects the compiled UPDATE (Constitution Cross-Feature Data Contract §4):
the SET clause must reference ``external_ids`` on BOTH sides (a merge), and must never touch
``properties`` or the display fields.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.repositories.named_entity_repository import NamedEntityRepository

pytestmark = pytest.mark.asyncio


async def _capture_update_sql() -> str:
    session = AsyncMock()
    captured: list[Any] = []

    async def _execute(stmt: Any, *a: Any, **k: Any) -> MagicMock:
        captured.append(stmt)
        result = MagicMock()
        result.rowcount = 1
        return result

    session.execute = _execute
    rowcount = await NamedEntityRepository().add_external_id(
        session,
        uuid.uuid4(),
        source="dbpedia",
        identifier={
            "id": "http://dbpedia.org/resource/X",
            "verified": False,
            "status": "confirmed",
        },
    )
    assert rowcount == 1
    assert len(captured) == 1
    return str(captured[0].compile(compile_kwargs={"literal_binds": False}))


class TestAddExternalIdSetClause:
    async def test_is_a_merge_not_a_replace(self) -> None:
        sql = (await _capture_update_sql()).lower()
        set_clause = sql.split(" where ")[0].split(" set ", 1)[1]
        # A merge references external_ids on BOTH the assignment target and the value expression,
        # via the JSONB `||` operator. A bare replace would have external_ids only once (as target).
        assert set_clause.count("external_ids") >= 2, set_clause
        assert "||" in set_clause, set_clause

    async def test_never_touches_properties_or_display_fields(self) -> None:
        sql = (await _capture_update_sql()).lower()
        set_clause = sql.split(" where ")[0]
        for forbidden in (
            "properties=",
            "canonical_name",
            "canonical_name_normalized",
            "description=",
        ):
            assert forbidden not in set_clause.replace(" ", ""), forbidden

    async def test_targets_by_id(self) -> None:
        sql = (await _capture_update_sql()).lower()
        assert " where " in sql and "named_entities.id" in sql
