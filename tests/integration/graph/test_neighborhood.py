"""Integration tests for Neo4jGraphRepository.neighborhood (Feature 115, Explore mode).

``skipif``-gated the same way as ``test_connection_repository``: if the configured graph is
unreachable or empty (CI, or a native run without a loaded dev graph), the module skips, so
``make pre-push`` stays green. Run locally against a loaded graph, e.g.
``NEO4J_URI=bolt://localhost:7688 NEO4J_USER=neo4j NEO4J_PWD=dev_password``.

Pairs/seeds are discovered DYNAMICALLY by structural query and referred to only by id — no
entity names or QIDs in this committed file (Constitution VI; the repo is public).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from neo4j.exceptions import DriverError, Neo4jError

from chronovista.graph import GraphUnavailableError, Neo4jClient
from chronovista.models.graph_connection import EdgeLayer
from chronovista.repositories.neo4j_graph_repository import (
    EntityNotInGraphError,
    Neo4jGraphRepository,
)

pytestmark = pytest.mark.asyncio

# A high-degree seed (plenty of neighbors to exercise the cap).
_BUSY_SEED = (
    "MATCH (s:Entity) WHERE s.entityId IS NOT NULL "
    "RETURN s.entityId AS a, count {(s)--()} AS d ORDER BY d DESC LIMIT 1"
)
# A seed that has at least one CO_OCCURS_* neighbor (for the default-hides-co-occurrence test).
_SEED_WITH_CO_OCCURRENCE = (
    "MATCH (s:Entity)-[r]-(:Entity) WHERE type(r) STARTS WITH 'CO_OCCURS_' "
    "RETURN s.entityId AS a LIMIT 1"
)
# A seed that has BOTH a verified (wikidata) neighbor and co-occurrence neighbors.
_SEED_MIXED_LAYERS = (
    "MATCH (s:Entity)-[v]-(:Entity) WHERE v.layer='wikidata' "
    "AND EXISTS { MATCH (s)-[c]-(:Entity) WHERE type(c) STARTS WITH 'CO_OCCURS_' } "
    "RETURN s.entityId AS a LIMIT 1"
)


@pytest.fixture
async def client() -> AsyncIterator[Neo4jClient]:
    """A connected client, or skip the module if the graph is unreachable OR not usable."""
    graph = Neo4jClient.from_settings()
    try:
        async with graph.session() as session:
            await (await session.run("RETURN 1 AS ok")).single()
    except (GraphUnavailableError, Neo4jError, DriverError) as exc:
        await graph.close()
        pytest.skip(f"Neo4j graph unavailable or not usable ({type(exc).__name__})")
    try:
        yield graph
    finally:
        await graph.close()


async def _one(graph: Neo4jClient, cypher: str) -> UUID | None:
    async with graph.session() as session:
        record = await (await session.run(cypher)).single()
    return UUID(record["a"]) if record is not None else None


class TestNeighborhood:
    async def test_seed_neighborhood_is_a_bounded_subgraph(
        self, client: Neo4jClient
    ) -> None:
        seed = await _one(client, _BUSY_SEED)
        if seed is None:
            pytest.skip("no entity in graph")
        sg = await Neo4jGraphRepository(client).neighborhood([seed], limit=20)

        keys = {n.node_key for n in sg.nodes}
        assert any(n.node.entity_id == seed for n in sg.nodes)  # seed present
        assert len(sg.nodes) <= 20  # initial cap (FR-003)
        # every edge references a node in the set (mesh integrity, D9 / model validator)
        for edge in sg.edges:
            assert edge.source_key in keys and edge.target_key in keys
        assert sg.total_available >= len(
            sg.nodes
        )  # "showing N of M" denominator (FR-005)

    async def test_default_hides_co_occurrence_optin_shows_it(
        self, client: Neo4jClient
    ) -> None:
        seed = await _one(client, _SEED_WITH_CO_OCCURRENCE)
        if seed is None:
            pytest.skip("no seed with a co-occurrence neighbor")
        repo = Neo4jGraphRepository(client)
        default_sg = await repo.neighborhood([seed], limit=200)
        assert all(
            e.layer is not EdgeLayer.CO_OCCURRENCE for e in default_sg.edges
        )  # FR-007
        optin_sg = await repo.neighborhood(
            [seed],
            limit=200,
            layers=frozenset(
                {EdgeLayer.VERIFIED, EdgeLayer.CATEGORY, EdgeLayer.CO_OCCURRENCE}
            ),
        )
        assert any(e.layer is EdgeLayer.CO_OCCURRENCE for e in optin_sg.edges)

    async def test_cap_drops_co_occurrence_before_verified(
        self, client: Neo4jClient
    ) -> None:
        # Integration-level SC-005: with all layers on but a tiny cap, verified neighbors are
        # kept while co-occurrence ones are dropped. Complements the pure-unit ranking test.
        seed = await _one(client, _SEED_MIXED_LAYERS)
        if seed is None:
            pytest.skip("no seed with both verified and co-occurrence neighbors")
        sg = await Neo4jGraphRepository(client).neighborhood(
            [seed],
            limit=3,
            layers=frozenset(
                {EdgeLayer.VERIFIED, EdgeLayer.CATEGORY, EdgeLayer.CO_OCCURRENCE}
            ),
        )
        assert sg.truncated is True
        kept_layers = {e.layer for e in sg.edges}
        # a verified neighbor survived; no co-occurrence-only survivor crowded it out
        assert EdgeLayer.VERIFIED in kept_layers
        assert EdgeLayer.CO_OCCURRENCE not in kept_layers

    async def test_missing_seed_raises_not_in_graph(self, client: Neo4jClient) -> None:
        with pytest.raises(EntityNotInGraphError):
            await Neo4jGraphRepository(client).neighborhood([uuid4()])
