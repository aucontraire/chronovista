"""Unit tests for the ``graph connect`` CLI — graceful degradation + messaging (US3).

The command must catch every expected failure (graph unavailable, ambiguous name, id- vs
name-not-found, and an unexpected query error) and exit cleanly with a clear message and NO
traceback (FR-009). The service is mocked, so no graph is needed; ``container.neo4j_client``
stays unconnected and its ``close()`` is a no-op.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from chronovista.cli.commands.graph import app
from chronovista.container import container
from chronovista.graph import GraphUnavailableError
from chronovista.models.graph_connection import GraphConnection, GraphNode
from chronovista.repositories.neo4j_graph_repository import EntityNotInGraphError
from chronovista.services.connection_service import AmbiguousEntityError


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _service(*, resolve: object, connect: object | None = None) -> AsyncMock:
    svc = AsyncMock()
    if isinstance(resolve, BaseException):
        svc.resolve.side_effect = resolve
    else:
        svc.resolve.return_value = resolve
    if connect is not None:
        if isinstance(connect, BaseException):
            svc.connect.side_effect = connect
        else:
            svc.connect.return_value = connect
    return svc


def _invoke(runner: CliRunner, svc: AsyncMock) -> object:
    with patch.object(container, "create_connection_service", return_value=svc):
        return runner.invoke(app, ["connect", "A", "B"])


class TestGraphConnectDegradation:
    def test_graph_unavailable_exits_cleanly(self, runner: CliRunner) -> None:
        result = _invoke(runner, _service(resolve=GraphUnavailableError("refused")))
        assert result.exit_code == 1
        assert "Graph unavailable" in result.output
        assert "docker compose" in result.output  # a recovery hint, not a traceback
        assert not isinstance(result.exception, GraphUnavailableError)

    def test_mid_session_unavailable_from_connect_degrades_cleanly(
        self, runner: CliRunner
    ) -> None:
        # The reconnect-gap fix makes a mid-query connectivity loss surface as
        # GraphUnavailableError from connect() (not a bare driver error). It must land on the
        # same clean handler — "Graph unavailable" + restart hint — not the generic
        # "Graph query failed" catch-all it used to fall through to.
        node = GraphNode(entity_id=uuid4(), name="X")
        result = _invoke(
            runner,
            _service(resolve=node, connect=GraphUnavailableError("lost connection")),
        )
        assert result.exit_code == 1
        assert "Graph unavailable" in result.output
        assert "docker compose" in result.output
        assert "Graph query failed" not in result.output
        assert not isinstance(result.exception, GraphUnavailableError)

    def test_name_not_found_message(self, runner: CliRunner) -> None:
        result = _invoke(
            runner, _service(resolve=EntityNotInGraphError("nobody", kind="name"))
        )
        assert result.exit_code == 1
        assert "Not found" in result.output
        assert "no entity named" in result.output

    def test_valid_id_not_in_loaded_graph_message(self, runner: CliRunner) -> None:
        result = _invoke(
            runner, _service(resolve=EntityNotInGraphError(uuid4(), kind="id"))
        )
        assert result.exit_code == 1
        assert "Not in the loaded graph" in result.output

    def test_ambiguous_name_lists_ids(self, runner: CliRunner) -> None:
        matches = [
            GraphNode(entity_id=uuid4(), name="Dup"),
            GraphNode(entity_id=uuid4(), name="Dup"),
        ]
        result = _invoke(runner, _service(resolve=AmbiguousEntityError("Dup", matches)))
        assert result.exit_code == 1
        assert "matches 2 entities" in result.output

    def test_unexpected_query_error_degrades_without_traceback(
        self, runner: CliRunner
    ) -> None:
        node = GraphNode(entity_id=uuid4(), name="X")
        result = _invoke(
            runner, _service(resolve=node, connect=RuntimeError("cypher boom"))
        )
        assert result.exit_code == 1
        assert "Graph query failed" in result.output
        # FR-009: the raw error is logged, not raised to the user as a traceback.
        assert not isinstance(result.exception, RuntimeError)

    def test_success_path_exits_zero(self, runner: CliRunner) -> None:
        node = GraphNode(entity_id=uuid4(), name="X")
        conn = GraphConnection(entity_a=node, entity_b=node, searched_max_hops=4)
        result = _invoke(runner, _service(resolve=node, connect=conn))
        assert result.exit_code == 0

    def test_kb_coverage_reads_hydrated_endpoints_not_resolved_nodes(
        self, runner: CliRunner
    ) -> None:
        # The name path resolves nodes WITHOUT kb_degree; the FR-016 coverage line must read it
        # from the id-hydrated result.entity_a/entity_b (which carry it). Before the fix it read
        # the resolved nodes and the line silently vanished on the name path.
        resolved = GraphNode(entity_id=uuid4(), name="X")  # kb_degree defaults None
        hydrated_a = GraphNode(entity_id=uuid4(), name="X", kb_degree=1)
        hydrated_b = GraphNode(entity_id=uuid4(), name="Y", kb_degree=40)
        conn = GraphConnection(
            entity_a=hydrated_a, entity_b=hydrated_b, searched_max_hops=4
        )
        result = _invoke(runner, _service(resolve=resolved, connect=conn))
        assert result.exit_code == 0
        assert "KB coverage" in result.output
        assert "barely in the knowledge base" in result.output  # min degree 1 < 3
