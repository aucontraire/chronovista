"""Read-only connection-graph API (Features 112/113).

Three endpoints for the connection-explorer frontend: serving-state health (``/graph/health``),
graph-membership for the picker (``POST /graph/entities``), and the neighbourhood itself
(``/graph/connect``). Read-only: all access goes through ``Neo4jGraphRepository`` (Principle III).

Errors are RFC-7807 problems (Feature 013). The frontend keys on the HTTP **status** (503 / 404 /
422), not a graph-specific ``type`` URI: a non-servable graph is a 503 with the shared
``SERVICE_UNAVAILABLE`` code, and an id absent from the current graph is a 404 with the shared
``NOT_FOUND`` code (the dedicated ``/graph/connect`` endpoint, plus the detail/hint text, is what
distinguishes "valid id, not in this graph" from any other not-found — not a bespoke type string).

The Neo4j client is a single long-lived instance reused across requests. The reconnect fix
(Feature 112, #408) makes a reused client safe: a mid-session outage surfaces as
``GraphUnavailableError`` and the cached driver is invalidated so the next request reconnects.
``/graph/health`` and ``/graph/entities`` degrade gracefully on an unavailable graph (Principle
VIII) rather than 500; ``/graph/connect`` returns 503.
"""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from chronovista.api.deps import require_auth
from chronovista.exceptions import APIError, APIValidationError, NotFoundError
from chronovista.graph import GraphUnavailableError, Neo4jClient
from chronovista.models.graph_connection import (
    EdgeLayer,
    GraphConnection,
    GraphSubgraph,
    ServingHealth,
)
from chronovista.repositories.neo4j_graph_repository import (
    EntityNotInGraphError,
    Neo4jGraphRepository,
)
from chronovista.services.connection_service import ConnectionService


class GraphUnavailableAPIError(APIError):
    """503 problem for a rebuilding / not-yet-loaded / unreachable graph (FR-010).

    Distinct from the internal :class:`~chronovista.graph.GraphUnavailableError` (which the
    endpoints catch and translate here) — this is the API-layer RFC-7807 response.
    """

    status_code = 503
    _error_code_value = "SERVICE_UNAVAILABLE"


@lru_cache(maxsize=1)
def _graph_client() -> Neo4jClient:
    """One long-lived client for the app (lazy-connect; reused safely — see module docstring)."""
    return Neo4jClient.from_settings()


def get_graph_repository() -> Neo4jGraphRepository:
    """FastAPI dependency: the read-only graph repository over the shared client."""
    return Neo4jGraphRepository(_graph_client())


router = APIRouter(dependencies=[Depends(require_auth)])


@router.get(
    "/graph/health",
    response_model=ServingHealth,
    summary="Connection-graph serving state",
)
async def graph_health(
    repo: Neo4jGraphRepository = Depends(get_graph_repository),
) -> ServingHealth:
    """Whether the graph may be served. A down/unreachable graph reads as **not servable** (the
    honest 'not available' state), never a 500 — the frontend distinguishes this from a real
    'no connection' result (FR-009/FR-010).
    """
    try:
        return await repo.health()
    except GraphUnavailableError:
        return ServingHealth(
            status=None, loaded_at=None, declared_layers=[], servable=False
        )


class GraphMembershipRequest(BaseModel):
    entity_ids: list[UUID] = Field(
        max_length=500,
        description="Entity ids to test for graph membership (bounded — the picker probes a page).",
    )


class GraphMembershipResponse(BaseModel):
    present: list[UUID]


@router.post(
    "/graph/entities",
    response_model=GraphMembershipResponse,
    summary="Which of these entity ids are present in the graph",
)
async def graph_entities(
    body: GraphMembershipRequest,
    repo: Neo4jGraphRepository = Depends(get_graph_repository),
) -> GraphMembershipResponse:
    """Return the subset of the given ids present in the graph — for the graph-present-only picker
    (FR-002). On an unavailable graph, returns an empty set (nothing is known to be present).
    """
    try:
        present = await repo.entity_ids_in_graph(body.entity_ids)
    except GraphUnavailableError:
        present = set()
    return GraphMembershipResponse(present=sorted(present, key=str))


@router.get(
    "/graph/connect",
    response_model=GraphConnection,
    summary="How two entities connect (the allShortestPaths neighbourhood)",
)
async def graph_connect(
    a: UUID = Query(..., description="first entity id"),
    b: UUID = Query(..., description="second entity id"),
    max_hops: int = Query(
        3,
        ge=3,
        le=6,
        description=(
            "reach (floor 3; 2 reliably returns empty). Capped at 6: real KB paths here are "
            "shallow, and a served endpoint must not run an unbounded allShortestPaths on a "
            "disconnected pair (which would exhaust the reachable component) — FR-013"
        ),
    ),
    max_category_size: int = Query(
        500,
        ge=1,
        description="category-specificity floor; broader categories excluded — FR-014",
    ),
    repo: Neo4jGraphRepository = Depends(get_graph_repository),
) -> GraphConnection:
    """Return the connection between two entities.

    Precondition (FR-010): the graph MUST be servable — a rebuilding / not-yet-loaded /
    unreachable graph returns **503**, never a connection or a 'no connection' result. A valid id
    absent from the current graph returns **404** (the detail explains the id is valid but not in
    the current graph — distinct from a connection that genuinely has no path). Two equal ids
    return **422**. ``AmbiguousEntityError`` cannot occur — the picker sends ids, and an id
    resolves to at most one entity.
    """
    if a == b:
        raise APIValidationError(
            message="The two entities must be different (a and b are the same id)."
        )
    # Servability gate: never serve a result from a non-servable graph (FR-010).
    try:
        servable = await repo.is_servable()
    except GraphUnavailableError as exc:
        raise GraphUnavailableAPIError("The connection graph is unavailable.") from exc
    if not servable:
        raise GraphUnavailableAPIError(
            "The connection graph is rebuilding or not yet loaded."
        )

    service = ConnectionService(repo)
    try:
        node_a = await service.resolve(str(a))
        node_b = await service.resolve(str(b))
        if node_a.entity_id is None or node_b.entity_id is None:
            raise NotFoundError(
                resource_type="Entity",
                identifier=f"{a} / {b}",
                hint="An endpoint resolved to a non-entity node.",
            )
        return await service.connect(
            node_a.entity_id,
            node_b.entity_id,
            max_hops=max_hops,
            max_category_size=max_category_size,
        )
    except GraphUnavailableError as exc:
        raise GraphUnavailableAPIError(
            "The connection graph became unavailable."
        ) from exc
    except EntityNotInGraphError as exc:
        hint = (
            "The id is valid but is not in the current graph (the graph may be older than the "
            "library)."
            if exc.kind == "id"
            else "No entity matches that name."
        )
        raise NotFoundError(
            resource_type="Entity", identifier=str(exc.identifier), hint=hint
        ) from exc


@router.get(
    "/graph/neighborhood",
    response_model=GraphSubgraph,
    summary="A bounded neighborhood subgraph around one or more seed entities",
)
async def graph_neighborhood(
    seed: list[UUID] = Query(
        ...,
        description="seed entity id(s): 1 = single-entity, 2 = pair (the explorer default)",
    ),
    radius: int = Query(
        1, ge=1, le=2, description="hop radius (1 default, 2 max) — FR-014"
    ),
    limit: int = Query(60, ge=1, description="initial node cap — FR-003"),
    ceiling: int = Query(
        250, ge=1, description="total node ceiling for accumulated expansion — FR-008"
    ),
    edge_types: list[str] | None = Query(
        None,
        description=(
            "trust layers to include: verified, category, co_occurrence "
            "(default: verified + category; co-occurrence hidden — FR-007)"
        ),
    ),
    max_category_size: int = Query(
        500,
        ge=1,
        description="category-specificity floor; broader categories excluded — FR-013",
    ),
    repo: Neo4jGraphRepository = Depends(get_graph_repository),
) -> GraphSubgraph:
    """Return the Explore-mode neighborhood subgraph for the seed(s).

    Read-only (FR-012). Same servability contract as ``/graph/connect``: a rebuilding /
    not-yet-loaded / unreachable graph returns **503**; a seed id valid but absent from the
    current graph returns **404**; invalid parameters (no seed, ``ceiling < limit``, unknown
    layer name, out-of-range bounds) return **422**.
    """
    if not seed:
        raise APIValidationError(message="At least one seed entity id is required.")
    if ceiling < limit:
        raise APIValidationError(
            message="ceiling must be greater than or equal to limit."
        )
    layers: frozenset[EdgeLayer] | None
    if edge_types is None:
        layers = None
    else:
        try:
            layers = frozenset(EdgeLayer(value) for value in edge_types)
        except ValueError as exc:
            raise APIValidationError(
                message="edge_types must be layer names: verified, category, co_occurrence."
            ) from exc
    # Servability gate (FR-010): never serve from a non-servable graph.
    try:
        servable = await repo.is_servable()
    except GraphUnavailableError as exc:
        raise GraphUnavailableAPIError("The connection graph is unavailable.") from exc
    if not servable:
        raise GraphUnavailableAPIError(
            "The connection graph is rebuilding or not yet loaded."
        )
    service = ConnectionService(repo)
    try:
        return await service.neighborhood(
            seed,
            radius=radius,
            limit=limit,
            ceiling=ceiling,
            layers=layers,
            max_category_size=max_category_size,
        )
    except GraphUnavailableError as exc:
        raise GraphUnavailableAPIError(
            "The connection graph became unavailable."
        ) from exc
    except EntityNotInGraphError as exc:
        raise NotFoundError(
            resource_type="Entity",
            identifier=str(exc.identifier),
            hint=(
                "The id is valid but is not in the current graph (the graph may be older "
                "than the library)."
            ),
        ) from exc
