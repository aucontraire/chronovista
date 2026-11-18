"""SC-002 hub-suppression property check over the live hub-only population (DB-gated).

Complements the by-construction invariant in
``tests/unit/architecture/test_connection_ranking_invariant.py``. The invariant is the
*guarantee* (a broad category's term floors to 0, so a broad-only overlap scores 0 and
``shared_category_chain`` returns ``None``); this is the empirical backstop that runs the real
repository against actual hub-only pairs — those whose EVERY shared category is near-universal
(``globalSize >= _CATEGORY_REFERENCE``) — and asserts not one is emitted as a category chain.

Honest scope: this tests the EXPLORER's suppression directly (per-pair ``shared_category_chain``)
rather than re-deriving the category signal in SQL — that is a separate concern in
``scripts/entity_resolution/verify_category_signal_f112.sql``. It is capped for runtime; when the
graph returns fewer hub-only pairs than the cap the check is genuinely exhaustive, and the
unit invariant covers the rest by construction. ``skipif`` the graph is unavailable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from neo4j.exceptions import DriverError, Neo4jError

from chronovista.graph import GraphUnavailableError, Neo4jClient
from chronovista.repositories.neo4j_graph_repository import Neo4jGraphRepository

pytestmark = pytest.mark.asyncio

# Pairs whose every shared category is near-universal (globalSize >= the 1e6 reference) — the
# hub-only population. Capped so the per-pair check stays fast; fewer rows than the cap means
# the slice is the whole population.
_HUB_ONLY_PAIRS = (
    "MATCH (a:Entity)-[:IN_CATEGORY]->(c:Category)<-[:IN_CATEGORY]-(b:Entity) "
    "WHERE a.entityId < b.entityId "
    "WITH a, b, collect(DISTINCT c.globalSize) AS sizes "
    "WHERE all(s IN sizes WHERE s >= 1000000) "
    "RETURN a.entityId AS a, b.entityId AS b LIMIT 300"
)


@pytest.fixture
async def client() -> AsyncIterator[Neo4jClient]:
    graph = Neo4jClient.from_settings()
    try:
        async with graph.session() as session:
            await (await session.run("RETURN 1 AS ok")).single()
    except (GraphUnavailableError, Neo4jError, DriverError) as exc:
        # Skip (don't error) when the configured graph is unreachable OR reachable-but-unusable
        # — e.g. NEO4J_URI points at an instance whose 'neo4j' database is missing/empty, which
        # surfaces as a bare DatabaseNotFound (a ClientError), NOT GraphUnavailableError. The
        # RETURN 1 probe cannot fail for a query-logic reason, so any neo4j-level failure means
        # the graph is not usable for these opportunistic integration tests. The type name keeps
        # the skip reason legible (GraphUnavailableError = unreachable; ClientError = db issue).
        await graph.close()
        pytest.skip(f"Neo4j graph unavailable or not usable ({type(exc).__name__})")
    try:
        yield graph
    finally:
        await graph.close()


class TestHubSuppressionExhaustive:
    async def test_no_hub_only_pair_is_emitted_as_a_category_chain(
        self, client: Neo4jClient
    ) -> None:
        repo = Neo4jGraphRepository(client)
        async with client.session() as session:
            rows = [record async for record in await session.run(_HUB_ONLY_PAIRS)]
        if not rows:
            pytest.skip("no hub-only (broad-category-only) pairs in graph")
        offenders: list[tuple[str, str]] = []
        for row in rows:
            chain = await repo.shared_category_chain(UUID(row["a"]), UUID(row["b"]))
            if chain is not None:
                offenders.append((row["a"], row["b"]))
        assert offenders == [], (
            f"{len(offenders)} hub-only pair(s) emitted a category chain "
            f"(SC-002 violated): {offenders[:5]}"
        )
