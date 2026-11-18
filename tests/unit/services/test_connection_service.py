"""Unit tests for ConnectionService + the connection-explorer Cypher safety guards (F112).

Two layers:

* **Service policy** (mocked repository): token resolution (id vs exact name, not-found,
  ambiguous) and parameter-preserving delegation.
* **Cypher contract guards** (real repository + a recording fake driver): FR-008 (the read
  path issues no write clause) and FR-016 (no ``LIMIT``-as-filter on a variable-length
  match — which would make "no connection" a sampling artifact rather than a proven
  absence). These run the *real* repository query-builders against a fake session that
  records every query, so a future edit that adds a write or bounds the traversal with
  ``LIMIT`` fails right here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from chronovista.models.graph_connection import (
    ConnectionChain,
    ConnectionKind,
    GraphConnection,
    GraphNode,
    PathStep,
    ReviewedVerdict,
)
from chronovista.repositories import neo4j_graph_repository
from chronovista.repositories.neo4j_graph_repository import (
    EntityNotInGraphError,
    Neo4jGraphRepository,
)
from chronovista.services.connection_service import (
    AmbiguousEntityError,
    ConnectionService,
)

pytestmark = pytest.mark.asyncio


def _node(name: str = "E") -> GraphNode:
    return GraphNode(entity_id=uuid4(), name=name)


def _chain(kind: ConnectionKind, end: GraphNode, **kw: Any) -> ConnectionChain:
    return ConnectionChain(
        kind=kind, steps=[PathStep(edge_type="E", kind=kind, to_node=end)], **kw
    )


# --- Service policy (mocked repository) ---------------------------------------------------


class TestConnectionServicePolicy:
    async def test_connect_delegates_with_all_params(self) -> None:
        repo = AsyncMock(spec=Neo4jGraphRepository)
        a, b = uuid4(), uuid4()
        expected = GraphConnection(
            entity_a=_node(), entity_b=_node(), searched_max_hops=4
        )
        repo.connection.return_value = expected
        service = ConnectionService(repo)

        result = await service.connect(a, b, max_hops=3, max_category_size=500)

        assert result is expected
        repo.connection.assert_awaited_once_with(
            a, b, max_hops=3, max_category_size=500
        )

    async def test_resolve_uuid_token_looks_up_by_id(self) -> None:
        repo = AsyncMock(spec=Neo4jGraphRepository)
        node = _node()
        repo.get_entity_node.return_value = node
        service = ConnectionService(repo)

        resolved = await service.resolve(str(uuid4()))

        assert resolved is node
        repo.get_entity_node.assert_awaited_once()
        repo.find_entities_by_name.assert_not_awaited()

    async def test_resolve_exact_name_single_match(self) -> None:
        repo = AsyncMock(spec=Neo4jGraphRepository)
        node = _node("Alpha")
        repo.find_entities_by_name.return_value = [node]
        service = ConnectionService(repo)

        resolved = await service.resolve("Alpha")

        assert resolved is node
        repo.get_entity_node.assert_not_awaited()

    async def test_resolve_name_not_found_raises(self) -> None:
        repo = AsyncMock(spec=Neo4jGraphRepository)
        repo.find_entities_by_name.return_value = []
        service = ConnectionService(repo)

        with pytest.raises(EntityNotInGraphError):
            await service.resolve("nobody")

    async def test_resolve_ambiguous_name_raises_with_matches(self) -> None:
        repo = AsyncMock(spec=Neo4jGraphRepository)
        matches = [_node("Dup"), _node("Dup")]
        repo.find_entities_by_name.return_value = matches
        service = ConnectionService(repo)

        with pytest.raises(AmbiguousEntityError) as excinfo:
            await service.resolve("Dup")
        assert excinfo.value.matches == matches
        assert excinfo.value.token == "Dup"


# --- Cypher contract guards (real repository + recording fake driver) ---------------------


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    async def single(self) -> dict[str, Any] | None:
        return self._records[0] if self._records else None

    def __aiter__(self) -> Any:
        return self._agen()

    async def _agen(self) -> Any:
        for record in self._records:
            yield record


class _FakeSession:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def run(self, query: str, **params: Any) -> _FakeResult:
        self._log.append(query)
        # Only get_entity_node must yield a row (else EntityNotInGraphError short-circuits
        # the traversal before the other tiers run); every other query returns empty so all
        # the tier queries still get issued and recorded.
        if "AS kb_degree" in query:
            return _FakeResult(
                [
                    {
                        "entity_id": str(uuid4()),
                        "name": "E",
                        "entity_type": "PERSON",
                        "kb_degree": 3,
                    }
                ]
            )
        return _FakeResult([])


class _RecordingClient:
    """A duck-typed Neo4jClient whose session records every Cypher query issued."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def session(self) -> _FakeSession:
        return _FakeSession(self.queries)


# Enforce the PROPERTY (read-only), not the uppercase convention that currently satisfies it:
# case-insensitive, and catch the APOC write procedures a bare-keyword scan would miss.
_WRITE_CLAUSE = re.compile(
    r"\b(?:CREATE|MERGE|SET|DELETE|REMOVE|DROP)\b|\bapoc\.(?:create|merge|refactor)\.",
    re.IGNORECASE,
)

# A variable-length relationship pattern — `[*1..4]`, `[r*1..3]`, `[:T*]`, etc. A bare
# `"[*" in q` check misses the named/typed forms, so match a `[` then any non-`]` run then `*`.
_VAR_LENGTH = re.compile(r"\[[^\]]*\*")

# The repository methods the recording guards actually drive: connection() transitively, plus
# resolve()'s name path (find_entities_by_name). Pinned against the AST truth below so a NEW
# query-builder method can't escape the FR-008/FR-016 guards by living off connection()'s path.
_EXERCISED_QUERY_METHODS = {
    "get_entity_node",
    "find_entities_by_name",
    "_entity_count",
    "get_reviewed_verdict",
    "get_coincidence_verdict",
    "chain",
    "shared_referents",
    "shared_category_chain",
    "co_occurrence_chains",
}


async def _exercise_all_query_methods(repo: Neo4jGraphRepository) -> None:
    """Drive every query-issuing path so the recording client sees every query it builds."""
    await repo.connection(uuid4(), uuid4())
    await repo.find_entities_by_name("x")


def _query_builder_methods() -> set[str]:
    """AST: names of Neo4jGraphRepository methods that issue a ``session.run(...)`` query."""
    tree = ast.parse(Path(neo4j_graph_repository.__file__).read_text())
    cls = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "Neo4jGraphRepository"
    )
    found: set[str] = set()
    for method in cls.body:
        if not isinstance(method, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for sub in ast.walk(method):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "run"
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "session"
            ):
                found.add(method.name)
                break
    return found


# Cypher-shaped string literals (uppercase clause keywords). Used by the companion guard so a
# method issuing Cypher via a path other than session.run (e.g. the driver's top-level
# execute_query) is still caught — the session.run scan alone would miss it.
_CYPHER_LITERAL = re.compile(r"\b(?:MATCH|MERGE|CREATE|DELETE|RETURN|UNWIND)\b")


def _cypher_literal_methods() -> set[str]:
    """AST: Neo4jGraphRepository methods holding a Cypher-shaped string literal."""
    tree = ast.parse(Path(neo4j_graph_repository.__file__).read_text())
    cls = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "Neo4jGraphRepository"
    )
    found: set[str] = set()
    for method in cls.body:
        if not isinstance(method, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for sub in ast.walk(method):
            if (
                isinstance(sub, ast.Constant)
                and isinstance(sub.value, str)
                and _CYPHER_LITERAL.search(sub.value)
            ):
                found.add(method.name)
                break
    return found


class TestConnectionCypherGuards:
    async def test_connection_issues_no_write_clause(self) -> None:
        client = _RecordingClient()
        repo = Neo4jGraphRepository(client)  # type: ignore[arg-type]

        await _exercise_all_query_methods(repo)

        assert client.queries, "expected the traversal to issue queries"
        offenders = [q for q in client.queries if _WRITE_CLAUSE.search(q)]
        assert offenders == [], f"FR-008: write clause(s) in read path: {offenders}"

    async def test_variable_length_match_carries_no_limit(self) -> None:
        client = _RecordingClient()
        repo = Neo4jGraphRepository(client)  # type: ignore[arg-type]

        await _exercise_all_query_methods(repo)

        # A variable-length pattern is written `[*...]`; it must never be bounded by LIMIT.
        offenders = [
            q for q in client.queries if _VAR_LENGTH.search(q) and "LIMIT" in q.upper()
        ]
        assert (
            offenders == []
        ), f"FR-016: variable-length match bounded by LIMIT: {offenders}"

    async def test_guard_exercises_every_query_builder(self) -> None:
        # The guards only see queries the exercised methods issue; pin the exercised set to
        # the AST truth so adding (or dropping) a query-builder method fails here loudly.
        builders = _query_builder_methods()
        assert builders == _EXERCISED_QUERY_METHODS, (
            "query-builder methods drifted from the guard's exercised set — "
            f"new/unguarded: {sorted(builders - _EXERCISED_QUERY_METHODS)}; "
            f"stale: {sorted(_EXERCISED_QUERY_METHODS - builders)}"
        )

    async def test_no_cypher_builder_escapes_via_a_non_session_path(self) -> None:
        # Companion guard: a method could issue Cypher via the driver's top-level
        # execute_query() and be invisible to a session.run-keyed scan. Pin every method
        # holding a Cypher-shaped literal to the exercised set, so one fails here instead of
        # slipping both the session.run scan and the FR-008/FR-016 guards.
        literal_methods = _cypher_literal_methods()
        assert literal_methods == _EXERCISED_QUERY_METHODS, (
            "methods holding Cypher literals drifted from the guard's exercised set — "
            f"new/unguarded: {sorted(literal_methods - _EXERCISED_QUERY_METHODS)}; "
            f"stale: {sorted(_EXERCISED_QUERY_METHODS - literal_methods)}"
        )


# --- US2 self-suppression (SC-002): a broad-grouping-only overlap is never emitted ---------


class _ScriptedSession:
    def __init__(self, script: dict[str, list[dict[str, Any]]]) -> None:
        self._script = script

    async def __aenter__(self) -> _ScriptedSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def run(self, query: str, **params: Any) -> _FakeResult:
        for substring, rows in self._script.items():
            if substring in query:
                return _FakeResult(rows)
        return _FakeResult([])


class _ScriptedClient:
    """A fake client returning canned rows for the first query matching a substring key."""

    def __init__(self, script: dict[str, list[dict[str, Any]]]) -> None:
        self._script = script

    def session(self) -> _ScriptedSession:
        return _ScriptedSession(self._script)


def _category_row(global_size: int, b_id: str) -> dict[str, Any]:
    return {
        "cat_name": "C",
        "global_size": global_size,
        "b_id": b_id,
        "b_name": "B",
        "b_type": "PERSON",
    }


class TestUS2CategorySelfSuppression:
    async def test_broad_only_category_is_not_emitted(self) -> None:
        # Every shared category near-universal (globalSize >= 1e6) ⇒ each term 0 ⇒ score 0 ⇒
        # None. SC-002: a broad-grouping-only overlap is absent, not shown-and-labeled.
        client = _ScriptedClient(
            {"IN_CATEGORY": [_category_row(2_000_000, str(uuid4()))]}
        )
        repo = Neo4jGraphRepository(client)  # type: ignore[arg-type]
        assert await repo.shared_category_chain(uuid4(), uuid4()) is None

    async def test_specific_category_is_emitted_with_positive_score(self) -> None:
        client = _ScriptedClient({"IN_CATEGORY": [_category_row(5, str(uuid4()))]})
        repo = Neo4jGraphRepository(client)  # type: ignore[arg-type]
        chain = await repo.shared_category_chain(uuid4(), uuid4())
        assert chain is not None and chain.score is not None and chain.score > 0.0

    async def test_one_specific_among_broad_is_emitted(self) -> None:
        # The count enters as the number of terms: a single specific category rescues an
        # otherwise-broad overlap (sum > 0), so it is emitted rather than suppressed.
        bid = str(uuid4())
        client = _ScriptedClient(
            {"IN_CATEGORY": [_category_row(2_000_000, bid), _category_row(10, bid)]}
        )
        repo = Neo4jGraphRepository(client)  # type: ignore[arg-type]
        chain = await repo.shared_category_chain(uuid4(), uuid4())
        assert chain is not None and chain.score is not None and chain.score > 0.0


# --- US2 coincidence policy: scoped, origin-gated co-occurrence suppression (T023) ----------


class TestUS2CoincidencePolicy:
    @staticmethod
    def _result(
        end: GraphNode, verdict: ReviewedVerdict, chains: list[ConnectionChain]
    ) -> GraphConnection:
        return GraphConnection(
            entity_a=_node("A"),
            entity_b=end,
            reviewed_verdict=verdict,
            chains=chains,
            searched_max_hops=4,
        )

    async def _connect_through(self, result: GraphConnection) -> GraphConnection:
        repo = AsyncMock(spec=Neo4jGraphRepository)
        repo.connection.return_value = result
        return await ConnectionService(repo).connect(uuid4(), uuid4())

    async def test_high_coincidence_suppresses_co_occurrence_keeps_rest(self) -> None:
        # origin 'human' ⇒ high confidence ⇒ the pair's co-occurrence is dropped, but the
        # asserted and shared_category chains (never in judged_over) are kept and shown.
        b = _node("B")
        verdict = ReviewedVerdict(verdict="coincidence", origin="human")
        out = await self._connect_through(
            self._result(
                b,
                verdict,
                [
                    _chain(ConnectionKind.ASSERTED, b, score=3.0),
                    _chain(ConnectionKind.SHARED_CATEGORY, b, score=5.0),
                    _chain(ConnectionKind.CO_OCCURRENCE_TRANSCRIPT, b),
                    _chain(ConnectionKind.CO_OCCURRENCE_TAGS, b),
                ],
            )
        )
        kinds = {c.kind for c in out.chains}
        assert ConnectionKind.CO_OCCURRENCE_TRANSCRIPT not in kinds
        assert ConnectionKind.CO_OCCURRENCE_TAGS not in kinds
        assert {ConnectionKind.ASSERTED, ConnectionKind.SHARED_CATEGORY} <= kinds

    async def test_medium_coincidence_suppresses_nothing(self) -> None:
        # origin 'suggested_agreed' ⇒ medium ⇒ treated as no verdict: co-occurrence survives.
        b = _node("B")
        verdict = ReviewedVerdict(verdict="coincidence", origin="suggested_agreed")
        out = await self._connect_through(
            self._result(
                b, verdict, [_chain(ConnectionKind.CO_OCCURRENCE_TRANSCRIPT, b)]
            )
        )
        assert ConnectionKind.CO_OCCURRENCE_TRANSCRIPT in {c.kind for c in out.chains}
        assert out.reviewed_verdict is None  # dropped: treated as no verdict

    async def test_relationship_verdict_never_suppresses_chains(self) -> None:
        # A relationship verdict is a positive — the inferred chains are always shown alongside.
        b = _node("B")
        verdict = ReviewedVerdict(
            verdict="relationship", relation="associated_with", origin="human"
        )
        out = await self._connect_through(
            self._result(
                b, verdict, [_chain(ConnectionKind.CO_OCCURRENCE_TRANSCRIPT, b)]
            )
        )
        assert ConnectionKind.CO_OCCURRENCE_TRANSCRIPT in {c.kind for c in out.chains}
