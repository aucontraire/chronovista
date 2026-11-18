"""Integration tests for Neo4jGraphRepository against a real dev-scoped graph (Feature 112).

``skipif``-gated: if the configured graph is unreachable (e.g. in CI), the whole module
skips, so ``make pre-push`` stays green with the graph down. Run locally against the loaded
dev graph, e.g. ``NEO4J_URI=bolt://localhost:7688 NEO4J_USER=neo4j NEO4J_PWD=dev_password``.

Pairs are discovered DYNAMICALLY by querying the live graph — never hardcoded ids or names.
This repository is public; library content (entity names, QIDs) must not land in committed
artifacts, so every pair is found by structural query and referred to only by id in memory.

The assertions check SHAPE and DIRECTION, not merely that a path exists — the shape-split's
whole purpose is that co-membership is a ``shared_referent`` ("both → X"), never a fabricated
directed ``asserted`` chain.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest

from chronovista.graph import GraphUnavailableError, Neo4jClient
from chronovista.models.graph_connection import ConnectionKind
from chronovista.repositories.neo4j_graph_repository import Neo4jGraphRepository

pytestmark = pytest.mark.asyncio

# A directed KB chain a→m→b (either traversal direction), KB-layer only.
_CHAIN_PAIR = (
    "MATCH (a:Entity)-[r1]->(m)-[r2]->(b:Entity) "
    "WHERE r1.layer='wikidata' AND r2.layer='wikidata' "
    "AND a.entityId < b.entityId AND m <> a AND m <> b "
    "RETURN a.entityId AS a, b.entityId AS b LIMIT 1"
)

# Convergence: a and b both point AT a shared KB node m, with NO direct edge and NO directed
# KB chain either way (so an `asserted` chain appearing would be a bug, not a real fact).
_CONVERGENT_PAIR = (
    "MATCH (a:Entity)-[r1]->(m)<-[r2]-(b:Entity) "
    "WHERE r1.layer='wikidata' AND r2.layer='wikidata' "
    "AND a.entityId < b.entityId AND m <> a AND m <> b "
    "AND NOT EXISTS { MATCH (a)-[x]-(b) WHERE x.layer='wikidata' } "
    "AND NOT EXISTS { MATCH p=(a)-[*1..4]->(b) "
    "WHERE all(r IN relationships(p) WHERE r.layer='wikidata') } "
    "AND NOT EXISTS { MATCH p=(b)-[*1..4]->(a) "
    "WHERE all(r IN relationships(p) WHERE r.layer='wikidata') } "
    "RETURN a.entityId AS a, b.entityId AS b LIMIT 1"
)

# Co-occurring, but with no KB connection at all: no direct KB edge, no shared KB referent
# (2-hop undirected), and no directed KB chain either way → a pure "qualify the absence" case.
_NO_KB_PAIR = (
    "MATCH (a:Entity)-[c]-(b:Entity) "
    "WHERE type(c) STARTS WITH 'CO_OCCURS_' AND a.entityId < b.entityId "
    "AND NOT EXISTS { MATCH (a)-[z]-(b) WHERE z.layer='wikidata' } "
    "AND NOT EXISTS { MATCH (a)-[x]-(mm)-[y]-(b) "
    "WHERE x.layer='wikidata' AND y.layer='wikidata' } "
    "AND NOT EXISTS { MATCH p=(a)-[*1..4]->(b) "
    "WHERE all(r IN relationships(p) WHERE r.layer='wikidata') } "
    "AND NOT EXISTS { MATCH p=(b)-[*1..4]->(a) "
    "WHERE all(r IN relationships(p) WHERE r.layer='wikidata') } "
    "RETURN a.entityId AS a, b.entityId AS b LIMIT 1"
)

# A pair with a 2-hop all-wikidata directed chain AND a SHORTER (length-1) direct non-wikidata
# edge. The globally-shortest directed path is the length-1 non-wikidata edge, so the KB filter
# must search PAST it to the length-2 wikidata chain — a proven absence, not a filtered single
# shortest path. Deliberately found WITHOUT shortestPath+WHERE, so the test fails (not skips)
# if that construct ever regresses to shortest-then-filter.
_MIXED_SHORTER_THAN_WIKIDATA_PAIR = (
    "MATCH (a:Entity)-[r1]->(m)-[r2]->(b:Entity) "
    "WHERE r1.layer='wikidata' AND r2.layer='wikidata' "
    "AND a.entityId < b.entityId AND m <> a AND m <> b "
    "AND EXISTS { MATCH (a)-[e]->(b) WHERE e.layer IS NULL OR e.layer <> 'wikidata' } "
    # Exclude a direct WIKIDATA edge: without this, a pair with both a direct wikidata edge
    # and a direct non-wikidata edge has a length-1 wikidata shortest path, so even a
    # shortest-then-filter regression would still return a chain — the test would pass
    # vacuously (CDWA measured 10.6% of the candidate pool).
    "AND NOT EXISTS { MATCH (a)-[e2]->(b) WHERE e2.layer = 'wikidata' } "
    "RETURN a.entityId AS a, b.entityId AS b LIMIT 1"
)

# The globally-shortest directed path length between two entities (any layer).
_SHORTEST_ANY_LEN = (
    "MATCH p=shortestPath((a:Entity {entityId:$a})-[*1..4]->(b:Entity {entityId:$b})) "
    "RETURN length(p) AS len"
)


@pytest.fixture
async def client() -> AsyncIterator[Neo4jClient]:
    """A connected client, or skip the module if the graph is unreachable. Always closed."""
    graph = Neo4jClient.from_settings()
    try:
        async with graph.session() as session:
            await (await session.run("RETURN 1 AS ok")).single()
    except GraphUnavailableError:
        await graph.close()
        pytest.skip("Neo4j graph unavailable")
    try:
        yield graph
    finally:
        await graph.close()


async def _discover(graph: Neo4jClient, cypher: str) -> tuple[UUID, UUID] | None:
    async with graph.session() as session:
        record = await (await session.run(cypher)).single()
    if record is None:
        return None
    return UUID(record["a"]), UUID(record["b"])


class TestConnectionShapeAndDirection:
    async def test_directed_chain_pair_is_asserted_and_ranks_first(
        self, client: Neo4jClient
    ) -> None:
        pair = await _discover(client, _CHAIN_PAIR)
        if pair is None:
            pytest.skip("no directed KB-chain pair in graph")
        conn = await Neo4jGraphRepository(client).connection(*pair)

        asserted = [c for c in conn.chains if c.kind is ConnectionKind.ASSERTED]
        assert asserted, "expected a directed KB chain to surface as an asserted chain"
        # Real a→…→b arrows: a forward-traversed chain flags every step forward.
        assert all(step.forward for step in asserted[0].steps)
        # Strongest-first: asserted outranks every inferred kind.
        assert conn.chains[0].kind is ConnectionKind.ASSERTED

    async def test_convergent_pair_is_shared_referent_not_asserted(
        self, client: Neo4jClient
    ) -> None:
        pair = await _discover(client, _CONVERGENT_PAIR)
        if pair is None:
            pytest.skip("no pure-convergence pair in graph")
        conn = await Neo4jGraphRepository(client).connection(*pair)

        kinds = {c.kind for c in conn.chains}
        # The decisive assertion: co-membership is NOT fabricated into a directed chain.
        assert ConnectionKind.ASSERTED not in kinds
        assert ConnectionKind.SHARED_REFERENT in kinds

        referent = next(
            c for c in conn.chains if c.kind is ConnectionKind.SHARED_REFERENT
        )
        # Convergent "both → «m»": step0 a→m (forward), step1 b→m (not forward).
        assert [step.forward for step in referent.steps] == [True, False]
        # Scored by local specificity, not a 1e6 hub constant.
        assert referent.score is not None and referent.score > 0.0

    async def test_no_kb_pair_qualifies_absence_with_endpoint_degree(
        self, client: Neo4jClient
    ) -> None:
        pair = await _discover(client, _NO_KB_PAIR)
        if pair is None:
            pytest.skip("no co-occurring-without-KB pair in graph")
        conn = await Neo4jGraphRepository(client).connection(*pair)

        kinds = {c.kind for c in conn.chains}
        assert ConnectionKind.ASSERTED not in kinds
        assert ConnectionKind.SHARED_REFERENT not in kinds
        # FR-016: the endpoints carry a KB-degree so the absence can be attributed to
        # enrichment coverage rather than asserted as a stated non-relationship.
        assert conn.entity_a.kb_degree is not None
        assert conn.entity_b.kb_degree is not None

    async def test_directed_absence_is_proven_not_shortest_sampled(
        self, client: Neo4jClient
    ) -> None:
        pair = await _discover(client, _MIXED_SHORTER_THAN_WIKIDATA_PAIR)
        if pair is None:
            pytest.skip(
                "no pair whose all-wikidata path exceeds its shortest mixed path"
            )
        a, b = pair
        # Check the precondition, don't assume it: the globally-shortest directed path is
        # length 1 (the direct non-wikidata edge — the discovery excludes a direct wikidata
        # one), while the all-wikidata chain is length 2. The KB filter must search PAST the
        # shorter path for this test to mean anything.
        async with client.session() as session:
            rec = await (
                await session.run(_SHORTEST_ANY_LEN, a=str(a), b=str(b))
            ).single()
        assert rec is not None and rec["len"] == 1
        conn = await Neo4jGraphRepository(client).connection(a, b)
        # An asserted chain MUST be present — its absence would be FR-016's sampling artifact
        # (the filtered shortestPath giving up at the shorter non-wikidata path).
        assert any(c.kind is ConnectionKind.ASSERTED for c in conn.chains)
