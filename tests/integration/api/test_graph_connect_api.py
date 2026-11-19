"""Contract tests for the graph API (Feature 113, T022): /graph/connect + /graph/health.

Seam tests between the router and the graph repository, using a FAKE repository via
``dependency_overrides`` (the real graph needs Neo4j — the serving-state gate and the RFC-7807
error mapping are what these assert, and they are mutation-verifiable: break the gate or the
mapping and the matching test fails). The live-graph behaviour is exercised in Phase 4's
``tests/integration/graph/`` suite.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from chronovista.api.deps import require_auth
from chronovista.api.main import app
from chronovista.api.routers.graph import get_graph_repository
from chronovista.graph import GraphUnavailableError
from chronovista.models.graph_connection import (
    GraphConnection,
    GraphNode,
    ServingHealth,
)
from chronovista.repositories.neo4j_graph_repository import EntityNotInGraphError

pytestmark = pytest.mark.asyncio


class _FakeRepo:
    """Minimal stand-in exposing exactly what the endpoint + ConnectionService call."""

    def __init__(
        self,
        *,
        servable: bool = True,
        down: bool = False,
        missing: bool = False,
        result: GraphConnection | None = None,
    ) -> None:
        self._servable = servable
        self._down = down
        self._missing = missing
        self._result = result

    async def is_servable(self) -> bool:
        if self._down:
            raise GraphUnavailableError("graph down")
        return self._servable

    async def get_entity_node(self, entity_id: UUID) -> GraphNode:
        if self._missing:
            raise EntityNotInGraphError(entity_id, kind="id")
        return GraphNode(entity_id=entity_id, name="Entity A", label="Person")

    async def find_entities_by_name(self, name: str) -> list[GraphNode]:
        return []  # unused: the API resolves UUID tokens, never names

    async def connection(
        self, a_id: UUID, b_id: UUID, *, max_hops: int, max_category_size: int | None
    ) -> GraphConnection:
        assert self._result is not None
        return self._result


def _install(fake: _FakeRepo) -> None:
    app.dependency_overrides[get_graph_repository] = lambda: fake
    app.dependency_overrides[require_auth] = lambda: None


def _reset() -> None:
    app.dependency_overrides.pop(get_graph_repository, None)
    app.dependency_overrides.pop(require_auth, None)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_connect_rebuilding_graph_returns_503() -> None:
    """FR-010/SC-003: a non-servable graph MUST return 503, never a connection result."""
    _install(_FakeRepo(servable=False))
    try:
        async with _client() as client:
            resp = await client.get(f"/api/v1/graph/connect?a={uuid4()}&b={uuid4()}")
        assert resp.status_code == 503
    finally:
        _reset()


async def test_connect_unreachable_graph_returns_503() -> None:
    """A down/unreachable graph (GraphUnavailableError) also returns 503, not a 500."""
    _install(_FakeRepo(down=True))
    try:
        async with _client() as client:
            resp = await client.get(f"/api/v1/graph/connect?a={uuid4()}&b={uuid4()}")
        assert resp.status_code == 503
    finally:
        _reset()


async def test_connect_entity_not_in_graph_returns_404() -> None:
    """FR-003: a valid id absent from the current graph returns 404 (not a 500 or empty 200)."""
    _install(_FakeRepo(servable=True, missing=True))
    try:
        async with _client() as client:
            resp = await client.get(f"/api/v1/graph/connect?a={uuid4()}&b={uuid4()}")
        assert resp.status_code == 404
    finally:
        _reset()


async def test_connect_below_hop_floor_is_422() -> None:
    """FR-013: the reach control cannot be set below 3 (validation, not a result)."""
    _install(_FakeRepo(servable=True))
    try:
        async with _client() as client:
            resp = await client.get(
                f"/api/v1/graph/connect?a={uuid4()}&b={uuid4()}&max_hops=2"
            )
        assert resp.status_code == 422
    finally:
        _reset()


async def test_connect_above_hop_ceiling_is_422() -> None:
    """The served endpoint caps reach (le=6): a value above the ceiling is rejected, never run —
    so a disconnected pair can't force an unbounded allShortestPaths over the whole component.
    """
    _install(_FakeRepo(servable=True))
    try:
        async with _client() as client:
            resp = await client.get(
                f"/api/v1/graph/connect?a={uuid4()}&b={uuid4()}&max_hops=7"
            )
        assert resp.status_code == 422
    finally:
        _reset()


async def test_connect_same_entity_returns_422() -> None:
    """FR + contract: a == b is rejected (422), never run as a self-connection."""
    same = uuid4()
    _install(_FakeRepo(servable=True))
    try:
        async with _client() as client:
            resp = await client.get(f"/api/v1/graph/connect?a={same}&b={same}")
        assert resp.status_code == 422
    finally:
        _reset()


async def test_connect_servable_returns_200() -> None:
    """A servable graph returns the connection body with both endpoints."""
    a, b = uuid4(), uuid4()
    result = GraphConnection(
        entity_a=GraphNode(entity_id=a, name="Entity A", label="Person"),
        entity_b=GraphNode(entity_id=b, name="Entity B", label="Person"),
        searched_max_hops=3,
    )
    _install(_FakeRepo(servable=True, result=result))
    try:
        async with _client() as client:
            resp = await client.get(f"/api/v1/graph/connect?a={a}&b={b}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_a"]["entity_id"] == str(a)
        assert body["entity_b"]["entity_id"] == str(b)
    finally:
        _reset()


async def test_health_reports_servable() -> None:
    """/graph/health surfaces servability for the UI."""

    class _HealthRepo(_FakeRepo):
        async def health(self) -> ServingHealth:
            return ServingHealth(
                status="complete",
                loaded_at="2026-11-18T00:00:00",
                declared_layers=["observed", "semantic", "categories"],
                servable=True,
            )

    _install(_HealthRepo())
    try:
        async with _client() as client:
            resp = await client.get("/api/v1/graph/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["servable"] is True
        assert body["status"] == "complete"
    finally:
        _reset()
