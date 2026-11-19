"""Serving-state behaviour against a REAL Neo4j graph (Feature 113, T032).

These are the seam tests Principle V wants: they exercise the actual ``:Meta`` read, the per-layer
presence Cypher, and ``Neo4jGraphRepository.is_servable`` against a live graph — not a mock. They
``skip`` when the graph is unreachable OR not loaded (no ``:Entity`` nodes), so they run only
against a real ``--profile graph`` container that has been loaded (``scripts/graph/reload_all.sh``).

Two connections are used deliberately: the repository under test goes through the **read-only**
``Neo4jClient`` (the explorer never writes), so the ``:Meta`` setup/teardown needs a **separate
write driver**. The setup preserves and restores ``:Meta`` so these tests never leave the shared
graph in a non-servable state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

from chronovista.config.settings import settings
from chronovista.graph import GraphUnavailableError, Neo4jClient, serving_state
from chronovista.graph.serving_state import GraphLayer
from chronovista.repositories.neo4j_graph_repository import Neo4jGraphRepository

pytestmark = pytest.mark.asyncio

_ALWAYS = ("observed", "semantic", "categories")


@pytest.fixture
async def client() -> AsyncIterator[Neo4jClient]:
    """Read-only client for the repository under test. Skip if the graph is unreachable OR not
    loaded (the serving-state tests need real ``:Entity``/``:Category`` data to probe).
    """
    graph = Neo4jClient.from_settings()
    try:
        async with graph.session() as session:
            loaded = await (
                await session.run("MATCH (e:Entity) RETURN e LIMIT 1")
            ).single()
    except (GraphUnavailableError, Neo4jError, DriverError) as exc:
        await graph.close()
        pytest.skip(f"Neo4j graph unavailable or not usable ({type(exc).__name__})")
    if loaded is None:
        await graph.close()
        pytest.skip("Neo4j graph reachable but not loaded (no :Entity nodes)")
    try:
        yield graph
    finally:
        await graph.close()


@pytest.fixture
async def writer() -> AsyncIterator[AsyncDriver]:
    """A WRITE-capable driver for :Meta setup/teardown (the read-only client cannot write)."""
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        yield driver
    finally:
        await driver.close()


@pytest.fixture
async def preserve_meta(writer: AsyncDriver) -> AsyncIterator[None]:
    """Snapshot :Meta, let the test mutate it, then restore it exactly (or remove a test-created
    one) so these tests never leave the shared graph unservable."""
    async with writer.session() as session:
        rec = await (
            await session.run(
                "MATCH (m:Meta {id:'graph'}) "
                "RETURN m.status AS status, m.loadedAt AS loadedAt, "
                "m.declaredLayers AS declaredLayers, m.bracketDepth AS bracketDepth"
            )
        ).single()
    saved = dict(rec) if rec is not None else None
    try:
        yield
    finally:
        async with writer.session() as session:
            if saved is None:
                await session.run("MATCH (m:Meta {id:'graph'}) DELETE m")
            else:
                await session.run(
                    "MERGE (m:Meta {id:'graph'}) SET m.status=$status, "
                    "m.loadedAt=$loadedAt, m.declaredLayers=$declaredLayers, "
                    "m.bracketDepth=$bracketDepth",
                    **saved,
                )


async def _set_meta(writer: AsyncDriver, *, status: str, declared: list[str]) -> None:
    async with writer.session() as session:
        await session.run(
            "MERGE (m:Meta {id:'graph'}) "
            "SET m.status=$status, m.declaredLayers=$declared, m.bracketDepth=0, "
            "m.loadedAt=datetime()",
            status=status,
            declared=declared,
        )


async def test_presence_probes_match_the_real_graph(client: Neo4jClient) -> None:
    """Each always-expected layer's presence probe returns a row against the real loaded graph —
    i.e. the markers (``:Entity``, ``layer='wikidata'``, ``:Category``) actually match what the
    loaders write. This is the assertion that cannot be made without a live, loaded graph.
    """
    async with client.session() as session:
        for layer in (GraphLayer.OBSERVED, GraphLayer.SEMANTIC, GraphLayer.CATEGORIES):
            row = await (
                await session.run(serving_state.LAYER_PRESENCE_CYPHER[layer])
            ).single()
            assert (
                row is not None
            ), f"layer '{layer.value}' has no elements in the loaded graph"


async def test_complete_graph_with_declared_layers_is_servable(
    client: Neo4jClient, writer: AsyncDriver, preserve_meta: None
) -> None:
    await _set_meta(writer, status="complete", declared=list(_ALWAYS))
    repo = Neo4jGraphRepository(client)
    assert await repo.is_servable() is True


async def test_loading_graph_is_not_servable(
    client: Neo4jClient, writer: AsyncDriver, preserve_meta: None
) -> None:
    """A rebuild in progress (status='loading') is never servable, regardless of what's present."""
    await _set_meta(writer, status="loading", declared=list(_ALWAYS))
    repo = Neo4jGraphRepository(client)
    assert await repo.is_servable() is False


async def test_declared_but_absent_layer_is_not_servable(
    client: Neo4jClient, writer: AsyncDriver, preserve_meta: None
) -> None:
    """A declared-expected layer that is NOT present makes the graph unservable (an accidental
    loss is caught, not read as 'absent by design'). Modelled with a synthetic declared layer no
    element carries, so the test stays non-destructive."""
    await _set_meta(writer, status="complete", declared=[*_ALWAYS, "__never_present__"])
    repo = Neo4jGraphRepository(client)
    assert await repo.is_servable() is False


async def test_reviewed_absent_by_declaration_is_servable(
    client: Neo4jClient, writer: AsyncDriver, preserve_meta: None
) -> None:
    """When 'reviewed' is NOT declared, its absence does not make the graph unservable (FR-011)."""
    await _set_meta(
        writer, status="complete", declared=list(_ALWAYS)
    )  # reviewed omitted
    repo = Neo4jGraphRepository(client)
    assert await repo.is_servable() is True
