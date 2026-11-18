"""Architecture invariant (SC-002): a broad grouping contributes exactly zero, and its chain
is not emitted.

Mutation-verified, no DB. Two things must hold by construction, not by sampling:

  1. The log-specificity term floors at 0 for a near-universal grouping (globalSize >= 1e6).
     Remove the ``max(0, ...)`` and a broad category contributes a NEGATIVE term, perturbing
     the score instead of self-cancelling — this test catches that.
  2. A shared-category overlap whose every term is 0 scores 0 and self-suppresses (returns
     ``None``). Remove the ``if score <= 0: return None`` and a junk broad-only grouping leaks
     into the result — this test catches that too.

SC-002 is proved here as an invariant (the CI guard) and exhaustively over the full hub-only
population in ``tests/integration/graph/test_hub_suppression_exhaustive.py`` (DB-gated). This
is a behavioural guard, not a literal scan: it fails if the floor or the suppression is
removed, which is exactly the regression SC-002 forbids.
"""

from __future__ import annotations

import math
from typing import Any
from uuid import uuid4

import pytest

from chronovista.repositories.neo4j_graph_repository import Neo4jGraphRepository

pytestmark = pytest.mark.asyncio


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def __aiter__(self) -> Any:
        return self._gen()

    async def _gen(self) -> Any:
        for row in self._rows:
            yield row


class _Session:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def run(self, query: str, **params: Any) -> _Result:
        return _Result(self._rows)


class _Client:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def session(self) -> _Session:
        return _Session(self._rows)


def _cat(global_size: int) -> dict[str, Any]:
    return {
        "cat_name": "C",
        "global_size": global_size,
        "b_id": str(uuid4()),
        "b_name": "B",
        "b_type": "PERSON",
    }


class TestSpecificityFloor:
    async def test_broad_grouping_term_is_exactly_zero(self) -> None:
        # globalSize == 1e6 ⇒ ln(1) == 0; > 1e6 would be negative without the max(0, ...) floor.
        assert Neo4jGraphRepository._specificity(1_000_000) == 0.0
        assert Neo4jGraphRepository._specificity(2_000_000) == 0.0

    async def test_specific_grouping_term_is_positive(self) -> None:
        assert Neo4jGraphRepository._specificity(10) == pytest.approx(
            math.log(1e6 / 10)
        )
        assert Neo4jGraphRepository._specificity(999_999) > 0.0

    async def test_null_or_zero_global_size_is_zero(self) -> None:
        assert Neo4jGraphRepository._specificity(None) == 0.0
        assert Neo4jGraphRepository._specificity(0) == 0.0


class TestBroadOnlySelfSuppression:
    async def test_broad_only_category_is_not_emitted(self) -> None:
        repo = Neo4jGraphRepository(_Client([_cat(2_000_000)]))  # type: ignore[arg-type]
        assert await repo.shared_category_chain(uuid4(), uuid4()) is None

    async def test_any_specific_term_rescues_emission(self) -> None:
        repo = Neo4jGraphRepository(_Client([_cat(2_000_000), _cat(5)]))  # type: ignore[arg-type]
        chain = await repo.shared_category_chain(uuid4(), uuid4())
        assert chain is not None and chain.score is not None and chain.score > 0.0
