"""Mock-SQL tests for the Feature 091 exclusion subtraction.

The spec's FR-004 (and the constitution's Cross-Feature Data Contract mandate) require
that an excluded ``(entity_id, video_id)`` pair is removed from EVERY association surface
— the entity filter AND the association counts — so the filter and counts cannot drift.
The arms union is assembled in three separate methods, so the subtraction is a single
helper (``_without_exclusions``) applied at every union site. These tests assert the
**LEFT JOIN anti-join** (``IS NULL``) against ``entity_video_exclusions`` is present in
the compiled SQL (the predicate, not a return value) — and that a correlated ``EXISTS``
is NOT used (the #56 perf guard). Name-free (Constitution VI).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

from sqlalchemy import Uuid, literal, select
from sqlalchemy import cast as sa_cast
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.models.enums import EvidenceScope
from chronovista.repositories.entity_mention_repository import EntityMentionRepository

_REPO = EntityMentionRepository()
_IDS = [uuid.UUID(int=1)]


class _EmptyResult:
    def all(self) -> list[Any]:
        return []


class _NoAliasSession:
    """Yields no alias-tag pairs so the statement compiles with literal_binds."""

    async def execute(self, *args: Any, **kwargs: Any) -> _EmptyResult:
        return _EmptyResult()

    async def scalar(self, *args: Any, **kwargs: Any) -> int:
        return 0


class _CapturingSession(_NoAliasSession):
    """Records every executed statement so the counts path can be inspected."""

    def __init__(self) -> None:
        self.executed: list[Any] = []

    async def execute(self, stmt: Any, *args: Any, **kwargs: Any) -> _EmptyResult:
        self.executed.append(stmt)
        return _EmptyResult()


def _sql(stmt: Any) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True})).replace("\n", " ")


def _has_exclusion_antijoin(sql: str) -> bool:
    # Non-correlated LEFT JOIN anti-join against the exclusion table — NOT a
    # correlated EXISTS (the #56 perf regression the count path forbids).
    low = sql.lower()
    return (
        "entity_video_exclusions" in low
        and "left outer join" in low
        and "is null" in low
    )


class TestExclusionSubtractionSQL:
    def test_helper_emits_antijoin_on_both_keys(self) -> None:
        src = select(
            sa_cast(literal("00000000-0000-0000-0000-000000000000"), Uuid).label(
                "entity_id"
            ),
            literal("v").label("video_id"),
        ).subquery("assoc_src")
        sql = _sql(select(_REPO._without_exclusions(src, "assoc"))).lower()
        assert "entity_video_exclusions" in sql
        assert "left outer join" in sql and "is null" in sql
        # Must NOT be a correlated EXISTS (#56 perf guard, enforced for the count path).
        assert "exists" not in sql
        # Anti-join correlated on BOTH keys — a per-pair exclusion.
        assert "entity_id" in sql and "video_id" in sql

    def test_filter_path_subtracts_exclusions(self) -> None:
        subq = asyncio.run(
            _REPO.build_entity_qualification_subquery(
                cast(AsyncSession, _NoAliasSession()), _IDS, EvidenceScope.ANY
            )
        )
        assert _has_exclusion_antijoin(_sql(subq.element))

    def test_counts_path_subtracts_exclusions(self) -> None:
        session = _CapturingSession()
        asyncio.run(_REPO.get_association_counts(cast(AsyncSession, session), _IDS))
        compiled = [_sql(s) for s in session.executed if hasattr(s, "compile")]
        assert any(_has_exclusion_antijoin(c) for c in compiled), (
            "the association counts statement must subtract exclusions too, "
            "or the filter and counts will drift (FR-004)"
        )

    def test_cooccurrence_path_subtracts_exclusions(self) -> None:
        subq = asyncio.run(
            _REPO._associations_in_video_set(
                cast(AsyncSession, _NoAliasSession()), ["v"], EvidenceScope.ANY
            )
        )
        assert _has_exclusion_antijoin(_sql(subq.element))

    def test_exclude_entity_subquery_inherits_exclusions(self) -> None:
        # build_entity_exclusion_subquery reuses the filter arms (site 1), so the
        # exclude_entity_id path inherits the subtraction automatically.
        scalar_sel = asyncio.run(
            _REPO.build_entity_exclusion_subquery(
                cast(AsyncSession, _NoAliasSession()), _IDS, EvidenceScope.ANY
            )
        )
        assert _has_exclusion_antijoin(_sql(scalar_sel))
