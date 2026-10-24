"""Storage-boundary mock-SQL tests for the manual entity image (Feature 092, T010).

The manual-image columns live OUTSIDE the enrichment ``properties`` bag precisely so no
enrichment write can clobber an operator-uploaded portrait (FR-010). These tests compile
the two enrichment write statements (``replace_properties`` / ``replace_enrichment``) and
assert the three manual-image column names are ABSENT from the compiled UPDATE — the
SQL-column check the constitution mandates for mutation unit tests. Name-free (Constitution VI).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.named_entity_repository import NamedEntityRepository

_REPO = NamedEntityRepository()
_EID = uuid.UUID(int=1)
_MANUAL_COLUMNS = (
    "manual_image_ext",
    "manual_image_uploaded_at",
    "image_source_preference",
)


class _FakeResult:
    rowcount = 1


class _CapturingSession:
    """Records the executed statement without touching a database."""

    def __init__(self) -> None:
        self.executed: list[Any] = []

    async def execute(self, stmt: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        self.executed.append(stmt)
        return _FakeResult()


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


class TestEnrichmentWritesExcludeManualImageColumns:
    def test_replace_properties_set_clause_excludes_manual_columns(self) -> None:
        session = _CapturingSession()
        asyncio.run(
            _REPO.replace_properties(
                cast(AsyncSession, session),
                _EID,
                properties={"image": {"values": ["x"], "set_at": "2026-10-24"}},
            )
        )
        sql = _sql(session.executed[0]).lower()
        assert sql.startswith("update named_entities set")
        for column in _MANUAL_COLUMNS:
            assert (
                column not in sql
            ), f"enrichment replace_properties must never write {column} (FR-010)"

    def test_replace_enrichment_set_clause_excludes_manual_columns(self) -> None:
        session = _CapturingSession()
        asyncio.run(
            _REPO.replace_enrichment(
                cast(AsyncSession, session),
                _EID,
                properties={"image": {"values": ["x"], "set_at": "2026-10-24"}},
                external_ids={"wikidata": {"id": "Q1"}},
            )
        )
        sql = _sql(session.executed[0]).lower()
        assert sql.startswith("update named_entities set")
        for column in _MANUAL_COLUMNS:
            assert (
                column not in sql
            ), f"enrichment replace_enrichment must never write {column} (FR-010)"
