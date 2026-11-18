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

from chronovista.models.graph_connection import GraphConnection, GraphNode
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

# The repository methods the recording guards actually drive: connection() transitively, plus
# resolve()'s name path (find_entities_by_name). Pinned against the AST truth below so a NEW
# query-builder method can't escape the FR-008/FR-016 guards by living off connection()'s path.
_EXERCISED_QUERY_METHODS = {
    "get_entity_node",
    "find_entities_by_name",
    "_entity_count",
    "get_reviewed_verdict",
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
        offenders = [q for q in client.queries if "[*" in q and "LIMIT" in q.upper()]
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
