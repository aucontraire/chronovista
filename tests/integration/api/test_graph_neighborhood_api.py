"""Contract tests for GET /graph/neighborhood (Feature 115, Explore mode).

Seam tests between the router/service and the graph repository via a FAKE repository
(``dependency_overrides``) — the real graph needs Neo4j; what these assert is the servability
gate, the RFC-7807 error mapping, the parameter validation, and the layer-param plumbing, all
mutation-verifiable (break any and the matching test fails). Live-graph behaviour is in
``tests/integration/graph/test_neighborhood.py``. Entity ids are synthetic (no library content).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from chronovista.api.deps import require_auth
from chronovista.api.main import app
from chronovista.api.routers.graph import get_graph_repository
from chronovista.graph import GraphUnavailableError
from chronovista.models.graph_connection import (
    EdgeLayer,
    GraphEdge,
    GraphNode,
    GraphSubgraph,
    SubgraphNode,
)
from chronovista.repositories.neo4j_graph_repository import EntityNotInGraphError

pytestmark = pytest.mark.asyncio


def _sample_subgraph(seed: UUID) -> GraphSubgraph:
    return GraphSubgraph(
        nodes=[
            SubgraphNode(
                node_key="n1",
                node=GraphNode(entity_id=seed, name="A", label="person"),
            ),
            SubgraphNode(
                node_key="n2",
                node=GraphNode(
                    entity_id=None, name="Cat", label="Category", is_bridge=True
                ),
            ),
        ],
        edges=[
            GraphEdge(
                source_key="n1",
                target_key="n2",
                edge_type="IN_CATEGORY",
                layer=EdgeLayer.CATEGORY,
            )
        ],
        truncated=False,
        total_available=5,
        seeds=[seed],
        at_ceiling=False,
    )


class _FakeRepo:
    """Stand-in exposing exactly what the endpoint + ConnectionService.neighborhood call."""

    def __init__(
        self, *, servable: bool = True, down: bool = False, missing: bool = False
    ) -> None:
        self._servable = servable
        self._down = down
        self._missing = missing
        self.last_kwargs: dict[str, Any] = {}

    async def is_servable(self) -> bool:
        if self._down:
            raise GraphUnavailableError("graph down")
        return self._servable

    async def neighborhood(self, seeds: list[UUID], **kwargs: Any) -> GraphSubgraph:
        self.last_kwargs = kwargs
        if self._missing:
            raise EntityNotInGraphError(seeds[0], kind="id")
        return _sample_subgraph(seeds[0])


def _install(fake: _FakeRepo) -> None:
    app.dependency_overrides[get_graph_repository] = lambda: fake
    app.dependency_overrides[require_auth] = lambda: None


def _reset() -> None:
    app.dependency_overrides.pop(get_graph_repository, None)
    app.dependency_overrides.pop(require_auth, None)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_rebuilding_graph_returns_503() -> None:
    _install(_FakeRepo(servable=False))
    try:
        async with _client() as client:
            resp = await client.get(f"/api/v1/graph/neighborhood?seed={uuid4()}")
        assert resp.status_code == 503
    finally:
        _reset()


async def test_unreachable_graph_returns_503() -> None:
    _install(_FakeRepo(down=True))
    try:
        async with _client() as client:
            resp = await client.get(f"/api/v1/graph/neighborhood?seed={uuid4()}")
        assert resp.status_code == 503
    finally:
        _reset()


async def test_missing_seed_returns_404() -> None:
    _install(_FakeRepo(servable=True, missing=True))
    try:
        async with _client() as client:
            resp = await client.get(f"/api/v1/graph/neighborhood?seed={uuid4()}")
        assert resp.status_code == 404
    finally:
        _reset()


async def test_ceiling_below_limit_is_422() -> None:
    _install(_FakeRepo(servable=True))
    try:
        async with _client() as client:
            resp = await client.get(
                f"/api/v1/graph/neighborhood?seed={uuid4()}&limit=60&ceiling=10"
            )
        assert resp.status_code == 422
    finally:
        _reset()


async def test_unknown_edge_type_is_422() -> None:
    _install(_FakeRepo(servable=True))
    try:
        async with _client() as client:
            resp = await client.get(
                f"/api/v1/graph/neighborhood?seed={uuid4()}&edge_types=bogus"
            )
        assert resp.status_code == 422
    finally:
        _reset()


async def test_no_seed_is_422() -> None:
    _install(_FakeRepo(servable=True))
    try:
        async with _client() as client:
            resp = await client.get("/api/v1/graph/neighborhood")
        assert resp.status_code == 422
    finally:
        _reset()


async def test_radius_out_of_range_is_422() -> None:
    _install(_FakeRepo(servable=True))
    try:
        async with _client() as client:
            resp = await client.get(
                f"/api/v1/graph/neighborhood?seed={uuid4()}&radius=3"
            )
        assert resp.status_code == 422
    finally:
        _reset()


async def test_servable_returns_200_subgraph() -> None:
    seed = uuid4()
    _install(_FakeRepo(servable=True))
    try:
        async with _client() as client:
            resp = await client.get(f"/api/v1/graph/neighborhood?seed={seed}")
        assert resp.status_code == 200
        body = resp.json()
        assert {n["node_key"] for n in body["nodes"]} == {"n1", "n2"}
        assert body["edges"][0]["layer"] == "category"
        assert body["total_available"] == 5
    finally:
        _reset()


async def test_default_edge_types_passed_as_none() -> None:
    # FR-007 default visibility is the repository's job; the endpoint must pass layers=None when
    # edge_types is omitted (so the repo applies verified+category), not an empty set.
    fake = _FakeRepo(servable=True)
    _install(fake)
    try:
        async with _client() as client:
            await client.get(f"/api/v1/graph/neighborhood?seed={uuid4()}")
        assert fake.last_kwargs["layers"] is None
    finally:
        _reset()


async def test_edge_types_resolved_to_layer_set() -> None:
    fake = _FakeRepo(servable=True)
    _install(fake)
    try:
        async with _client() as client:
            await client.get(
                f"/api/v1/graph/neighborhood?seed={uuid4()}"
                "&edge_types=verified&edge_types=co_occurrence"
            )
        assert fake.last_kwargs["layers"] == frozenset(
            {EdgeLayer.VERIFIED, EdgeLayer.CO_OCCURRENCE}
        )
    finally:
        _reset()
