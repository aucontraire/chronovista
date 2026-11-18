"""Neo4j-backed connection-explorer repository (Feature 112).

Reads the dev-scoped graph (read-only) to answer "how are entity A and entity B
connected?", returning a :class:`GraphConnection`: the human-reviewed verdict where one
exists, plus one labeled chain per inferred connecting kind, in a fixed by-kind order.

This is the Phase-2 SHELL. The tiered Cypher search (asserted/reviewed → shared-category →
co-occurrence), the log-specificity ranking, and proven-absence handling land in US1+
(tasks T014+).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from chronovista.graph import Neo4jClient
from chronovista.models.graph_connection import (
    ConnectionChain,
    ConnectionKind,
    GraphConnection,
    GraphNode,
    PathStep,
    ReviewedVerdict,
)

if TYPE_CHECKING:
    from neo4j.graph import Node, Path


# CO_OCCURS_* graph rel type -> its labeled co-occurrence ConnectionKind. The four channels
# are never merged into one score (measured review §4) — each is its own kind.
_CO_OCCURS_KIND: dict[str, ConnectionKind] = {
    "CO_OCCURS_TRANSCRIPT": ConnectionKind.CO_OCCURRENCE_TRANSCRIPT,
    "CO_OCCURS_TITLEDESC": ConnectionKind.CO_OCCURRENCE_TITLEDESC,
    "CO_OCCURS_TAGS": ConnectionKind.CO_OCCURRENCE_TAGS,
    "CO_OCCURS_MANUAL": ConnectionKind.CO_OCCURRENCE_MANUAL,
}

# Reviewed relationship edge type -> the ReviewedVerdict.relation value. The graph carries
# only RELATIONSHIP verdicts; coincidence verdicts produce no edge (load_reviewed skips them),
# so a direct reviewed edge is always a relationship verdict.
_REVIEWED_RELATION: dict[str, Literal["associated_with", "covers", "co_cast"]] = {
    "ASSOCIATED_WITH": "associated_with",
    "COVERS": "covers",
    "CO_CAST": "co_cast",
}


def _normalize_origin(
    raw: object,
) -> Literal["human", "reaudited_c", "suggested_agreed"]:
    """Map a stored reviewed-edge origin to the model enum (null/absent/unknown -> human)."""
    if not raw:
        return "human"
    norm = str(raw).replace("-", "_").lower()
    if norm == "suggested_agreed":
        return "suggested_agreed"
    if norm == "reaudited_c":
        return "reaudited_c"
    return "human"


class EntityNotInGraphError(LookupError):
    """An entity identifier (id or name) was not found in the graph.

    Distinct from :class:`GraphUnavailableError` (the graph is reachable, the entity just
    isn't there) so the CLI can tell "no such entity" from "graph is down".
    """

    def __init__(self, identifier: object) -> None:
        super().__init__(f"no entity matching '{identifier}' in the graph")
        self.identifier = identifier


class Neo4jGraphRepository:
    """Read-only access to the connection graph.

    All graph reads go through this repository (Principle III). It depends on a
    :class:`Neo4jClient` — a distinct data source from the Postgres repositories — and
    never writes (FR-008).
    """

    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    async def get_entity_node(self, entity_id: UUID) -> GraphNode:
        """Hydrate the :class:`GraphNode` for an entity, by its ``entityId``.

        Parameters
        ----------
        entity_id : UUID
            The entity to look up. Neo4j stores ``entityId`` as a string; it is passed as
            ``str`` to the query and coerced back to ``UUID`` by :class:`GraphNode`.

        Returns
        -------
        GraphNode
            The hydrated node (``is_bridge=False``; ``label`` is the entity type).

        Raises
        ------
        EntityNotInGraphError
            If no ``:Entity`` with that id exists in the graph.
        GraphUnavailableError
            If the graph cannot be reached.
        """
        # kb_degree counts WIKIDATA edges only — NOT reviewed edges. The number drives the
        # "enrichment gap vs stated non-relationship" line, and reviewed edges are human
        # judgments, not the knowledge base; counting them would read a heavily-reviewed pair
        # as well-covered and suppress the gap line exactly when the gap is real (round-2
        # purity argument, applied consistently with the KB-only asserted tier).
        query = (
            "MATCH (e:Entity {entityId: $entity_id}) "
            "RETURN e.entityId AS entity_id, e.name AS name, e.entityType AS entity_type, "
            "count { (e)-[r]-() WHERE r.layer = 'wikidata' } AS kb_degree"
        )
        async with self._client.session() as session:
            result = await session.run(query, entity_id=str(entity_id))
            record = await result.single()
        if record is None:
            raise EntityNotInGraphError(entity_id)
        return GraphNode(
            entity_id=record["entity_id"],
            name=record["name"] or "",
            label=record["entity_type"] or "",
            is_bridge=False,
            kb_degree=record["kb_degree"],
        )

    async def find_entities_by_name(self, name: str) -> list[GraphNode]:
        """Entities whose name matches ``name`` exactly (case-insensitive), most-mentioned first.

        Used by the CLI to resolve a human-typed name to an entity. Exact match only (the MVP
        does not fuzzy-match); the caller handles 0 (not found) and >1 (ambiguous).
        """
        query = (
            "MATCH (e:Entity) WHERE toLower(e.name) = toLower($name) "
            "RETURN e.entityId AS entity_id, e.name AS name, e.entityType AS entity_type "
            "ORDER BY coalesce(e.mentionCount, 0) DESC LIMIT 25"
        )
        async with self._client.session() as session:
            result = await session.run(query, name=name)
            rows = [record async for record in result]
        return [
            GraphNode(
                entity_id=row["entity_id"],
                name=row["name"] or "",
                label=row["entity_type"] or "",
                is_bridge=False,
            )
            for row in rows
        ]

    @staticmethod
    def _node_to_graphnode(node: Node) -> GraphNode:
        """Build a :class:`GraphNode` from a path node — a real :Entity or a stub referent.

        An ``:Entity`` carries ``entityId`` (coerced to UUID); a ``:WikidataItem`` is a stub
        with no ``entityId`` (``is_bridge=True``) — admissible only as a shared referent,
        which holds by construction since stubs have no onward edges.
        """
        if "entityId" in node:
            return GraphNode(
                entity_id=node["entityId"],
                name=node.get("name") or "",
                label=node.get("entityType") or "",
                is_bridge=False,
            )
        return GraphNode(
            entity_id=None,
            name=node.get("name") or node.get("qid") or "",
            label="WikidataItem",
            is_bridge=True,
        )

    async def _entity_count(self) -> int:
        """Total ``:Entity`` count — the reference population for log-specificity scoring."""
        async with self._client.session() as session:
            record = await (
                await session.run("MATCH (e:Entity) RETURN count(e) AS n")
            ).single()
        return int(record["n"]) if record else 0

    async def chain(
        self,
        a_id: UUID,
        b_id: UUID,
        *,
        max_hops: int = 4,
        entity_count: int | None = None,
    ) -> ConnectionChain | None:
        """Shortest DIRECTED KB chain A→…→B (or B→…→A), scored by its weakest hub, or ``None``.

        A chain is a composition of *stated KB facts whose directions compose* — found by a
        **directed** ``shortestPath`` over ``layer='wikidata'`` edges (forward and backward,
        shorter wins). A co-membership "both → X" is therefore NOT a chain — it does not match
        a directed path and falls to :meth:`shared_referents`. Each step's ``forward`` flag
        preserves the stored edge direction so the renderer shows real arrows. Reviewed edges
        are excluded (``layer != 'wikidata'``). ``None`` = no directed KB chain within
        ``max_hops`` (a proven absence, by exhaustive shortestPath — not a sampling artifact).

        ``score`` is the log-specificity of the chain's WEAKEST (highest-degree) intermediate
        hub — ``min_m max(0, ln(entity_count / degree(m)))``; chain LENGTH does not enter it.
        A chain through a mega-hub (a node tied to hundreds of entities identically) scores LOW
        *relative to other chains*, flagging that it is barely a connection between these two.
        The score is a WITHIN-TIER quantity: it ranks chains against chains and is NOT
        comparable to a shared_category score (different reference, different population) — so
        cross-kind ordering is by kind, never by score. A direct edge (no intermediate) tops
        the scale (:meth:`_top_specificity`).
        """
        if entity_count is None:
            entity_count = await self._entity_count()
        base = "MATCH (a:Entity {entityId: $a}), (b:Entity {entityId: $b}) "
        # Per-intermediate DISTINCT-entity KB degree (NOT edge count — parallel edges would
        # inflate it), computed in the same query so no extra round-trip. Literal braces here,
        # so this is concatenated (not an f-string) into the query below.
        mids = (
            "[n IN nodes(p)[1..-1] | "
            "count { MATCH (n)-[x]-(e:Entity) WHERE x.layer = 'wikidata' RETURN DISTINCT e }"
            "] AS mid_degrees"
        )
        tail = (
            "WHERE all(r IN relationships(p) WHERE r.layer = 'wikidata') RETURN p, "
            + mids
        )
        forward_q = (
            f"{base}MATCH p = shortestPath((a)-[*1..{int(max_hops)}]->(b)) {tail}"
        )
        backward_q = (
            f"{base}MATCH p = shortestPath((a)<-[*1..{int(max_hops)}]-(b)) {tail}"
        )
        async with self._client.session() as session:
            fwd = await (
                await session.run(forward_q, a=str(a_id), b=str(b_id))
            ).single()
            bwd = await (
                await session.run(backward_q, a=str(a_id), b=str(b_id))
            ).single()
        # A forward query yields all edges a→…→b (forward=True); a backward query yields edges
        # pointing toward a, i.e. the KB chain reads b→…→a (forward=False). So step direction
        # is simply which query won — no per-edge start_node inspection needed.
        candidates: list[tuple[Path, list[int], bool]] = []
        if fwd is not None:
            candidates.append((fwd["p"], list(fwd["mid_degrees"]), True))
        if bwd is not None:
            candidates.append((bwd["p"], list(bwd["mid_degrees"]), False))
        if not candidates:
            return None
        path, mid_degrees, is_forward = min(
            candidates, key=lambda c: len(c[0].relationships)
        )
        nodes = path.nodes
        steps = [
            PathStep(
                edge_type=rel.type,
                kind=ConnectionKind.ASSERTED,
                to_node=self._node_to_graphnode(nodes[i + 1]),
                forward=is_forward,
            )
            for i, rel in enumerate(path.relationships)
        ]
        # Weakest-link: the chain is only as specific as its most generic hub. A direct edge
        # (no intermediate) shares nothing → top of the scale. NOTE: chain LENGTH deliberately
        # does NOT enter — `min` over intermediates is a pure specificity signal, so a long
        # chain of specific nodes can score like a short one. Length is absent by choice (it
        # could re-enter in a later tier now that specificity carries the hub problem), not
        # overlooked; do not assume it is factored in.
        score = min(
            (
                self._referent_specificity(degree, entity_count)
                for degree in mid_degrees
            ),
            default=self._top_specificity(entity_count),
        )
        return ConnectionChain(kind=ConnectionKind.ASSERTED, steps=steps, score=score)

    @staticmethod
    def _referent_specificity(degree: int | None, entity_count: int) -> float:
        """How specific a shared KB referent is: ``max(0, ln(entity_count / degree))``.

        ``degree`` = how many library entities share the referent (a LOCAL count — so NOT
        the category tier's ``1e6`` global reference). A referent few entities share scores
        high; a hub everyone shares floors to ~0.
        """
        if not degree or degree <= 0 or entity_count <= 0:
            return 0.0
        return max(0.0, math.log(entity_count / degree))

    @staticmethod
    def _top_specificity(entity_count: int) -> float:
        """Top of the specificity scale: a direct stated edge shares NO referent, so it is
        maximally specific. Named rather than spelled ``_referent_specificity(1, …)`` so the
        direct-edge score does not silently move if that referent formula changes for referent
        reasons — a direct edge has no referent to be specific about.
        """
        return max(0.0, math.log(entity_count)) if entity_count > 1 else 0.0

    async def shared_referents(
        self, a_id: UUID, b_id: UUID, *, entity_count: int | None = None
    ) -> ConnectionChain | None:
        """Shared-KB-referent convergence A↔B (both relate to a common KB node), or ``None``.

        A and B both point at (convergent) or are pointed at by (divergent) one or more KB
        nodes ``m`` — a co-membership / shared-affiliation tie, NOT a composed chain. Scored
        by how specific the shared node is (local degree); representative = the most specific.
        The ``forward`` flags encode convergent ("both → «m»") vs divergent ("«m» → both").
        """
        if entity_count is None:
            entity_count = await self._entity_count()
        # degree = DISTINCT :Entity neighbours of m over wikidata edges (NOT edge count —
        # parallel edges between the same pair would inflate it and deflate specificity).
        query = (
            "MATCH (a:Entity {entityId: $a})-[r1]-(m)-[r2]-(b:Entity {entityId: $b}) "
            "WHERE r1.layer = 'wikidata' AND r2.layer = 'wikidata' AND m <> a AND m <> b "
            "AND (startNode(r1) = a) = (startNode(r2) = b) "
            "WITH m, (startNode(r1) = a) AS a_to_m, type(r1) AS t1, type(r2) AS t2 "
            "WITH m, head(collect({a_to_m: a_to_m, t1: t1, t2: t2})) AS rep "
            "RETURN m.entityId AS m_id, m.name AS m_name, (m:WikidataItem) AS is_stub, "
            "rep.a_to_m AS a_to_m, rep.t1 AS t1, rep.t2 AS t2, "
            "count { MATCH (m)-[x]-(e:Entity) WHERE x.layer = 'wikidata' "
            "RETURN DISTINCT e } AS degree"
        )
        async with self._client.session() as session:
            rows = [
                rec async for rec in await session.run(query, a=str(a_id), b=str(b_id))
            ]
        if not rows:
            return None
        scored = [
            (row, self._referent_specificity(row["degree"], entity_count))
            for row in rows
        ]
        score = sum((spec for _, spec in scored), 0.0)
        best, best_spec = max(scored, key=lambda t: t[1])
        a_to_m = bool(best["a_to_m"])
        referent = GraphNode(
            entity_id=None if best["is_stub"] else best["m_id"],
            name=best["m_name"] or "",
            label="WikidataItem" if best["is_stub"] else "",
            is_bridge=True,
        )
        b_node = await self.get_entity_node(b_id)
        steps = [
            PathStep(
                edge_type=best["t1"],
                kind=ConnectionKind.SHARED_REFERENT,
                to_node=referent,
                specificity=best_spec,
                forward=a_to_m,
            ),
            PathStep(
                edge_type=best["t2"],
                kind=ConnectionKind.SHARED_REFERENT,
                to_node=b_node,
                forward=not a_to_m,
            ),
        ]
        return ConnectionChain(
            kind=ConnectionKind.SHARED_REFERENT, steps=steps, score=score
        )

    @staticmethod
    def _specificity(global_size: int | None) -> float:
        """Log-specificity term ``max(0, ln(1e6 / globalSize))``; 0 for null/0/broad."""
        if not global_size or global_size <= 0:
            return 0.0
        return max(0.0, math.log(1e6 / global_size))

    async def shared_category_chain(
        self, a_id: UUID, b_id: UUID
    ) -> ConnectionChain | None:
        """The shared-category connection A↔B, scored by log-specificity, or ``None``.

        Two entities are category-connected when they share one or more Wikipedia categories
        (2-hop ``IN_CATEGORY``). The chain's steps show the single most specific shared
        category (the most specific bridge); its ``score`` is the SINGLE ranking value
        ``Σ max(0, ln(1e6 / globalSize(c)))`` over ALL shared categories — the count enters as
        the number of terms, and a broad category (globalSize ≥ 1e6) contributes 0, so a
        broad-only overlap floors to 0 and self-suppresses (dropped downstream in US2).
        """
        query = (
            "MATCH (a:Entity {entityId: $a})-[:IN_CATEGORY]->(c:Category)"
            "<-[:IN_CATEGORY]-(b:Entity {entityId: $b}) "
            "RETURN c.name AS cat_name, c.globalSize AS global_size, "
            "b.entityId AS b_id, b.name AS b_name, b.entityType AS b_type"
        )
        async with self._client.session() as session:
            result = await session.run(query, a=str(a_id), b=str(b_id))
            rows = [record async for record in result]
        if not rows:
            return None
        terms = [
            (row["cat_name"], self._specificity(row["global_size"])) for row in rows
        ]
        score = sum((term for _, term in terms), 0.0)
        best_name, best_term = max(terms, key=lambda t: t[1])
        first = rows[0]
        category_node = GraphNode(
            entity_id=None, name=best_name or "", label="Category", is_bridge=True
        )
        b_node = GraphNode(
            entity_id=first["b_id"],
            name=first["b_name"] or "",
            label=first["b_type"] or "",
            is_bridge=False,
        )
        steps = [
            PathStep(
                edge_type="IN_CATEGORY",
                kind=ConnectionKind.SHARED_CATEGORY,
                to_node=category_node,
                specificity=best_term,
            ),
            PathStep(
                edge_type="IN_CATEGORY",
                kind=ConnectionKind.SHARED_CATEGORY,
                to_node=b_node,
            ),
        ]
        return ConnectionChain(
            kind=ConnectionKind.SHARED_CATEGORY, steps=steps, score=score
        )

    async def co_occurrence_chains(
        self, a_id: UUID, b_id: UUID
    ) -> list[ConnectionChain]:
        """One chain per ``CO_OCCURS_*`` channel directly linking A↔B (each its own kind).

        The four channels (transcript / title-desc / tags / manual) are NEVER merged into a
        single score — each present channel is returned as its own labeled
        :class:`ConnectionChain` (measured review §4). A channel not present is simply absent.
        """
        query = (
            "MATCH (a:Entity {entityId: $a})-[r]-(b:Entity {entityId: $b}) "
            "WHERE type(r) STARTS WITH 'CO_OCCURS_' "
            "RETURN DISTINCT type(r) AS rel_type, "
            "b.entityId AS b_id, b.name AS b_name, b.entityType AS b_type"
        )
        async with self._client.session() as session:
            result = await session.run(query, a=str(a_id), b=str(b_id))
            rows = [record async for record in result]
        chains: list[ConnectionChain] = []
        for row in rows:
            kind = _CO_OCCURS_KIND.get(row["rel_type"])
            if kind is None:
                continue
            b_node = GraphNode(
                entity_id=row["b_id"],
                name=row["b_name"] or "",
                label=row["b_type"] or "",
                is_bridge=False,
            )
            chains.append(
                ConnectionChain(
                    kind=kind,
                    steps=[
                        PathStep(edge_type=row["rel_type"], kind=kind, to_node=b_node)
                    ],
                )
            )
        return chains

    async def get_reviewed_verdict(
        self, a_id: UUID, b_id: UUID
    ) -> ReviewedVerdict | None:
        """The human-reviewed RELATIONSHIP verdict for a direct A↔B reviewed edge, or None.

        The graph carries only relationship verdicts (``ASSOCIATED_WITH`` / ``COVERS`` /
        ``CO_CAST``); coincidence verdicts produce no edge, so ``None`` here means "no
        relationship verdict", not "no verdict of any kind" (coincidence handling is US2 and
        needs those verdicts loaded). ``confidence`` is computed from ``origin`` by the model.
        """
        query = (
            "MATCH (a:Entity {entityId: $a})-[r]-(b:Entity {entityId: $b}) "
            "WHERE type(r) IN ['ASSOCIATED_WITH', 'COVERS', 'CO_CAST'] "
            "RETURN type(r) AS rel_type, r.origin AS origin, r.source AS source LIMIT 1"
        )
        async with self._client.session() as session:
            result = await session.run(query, a=str(a_id), b=str(b_id))
            record = await result.single()
        if record is None:
            return None
        return ReviewedVerdict(
            verdict="relationship",
            relation=_REVIEWED_RELATION[record["rel_type"]],
            origin=_normalize_origin(record["origin"]),
            provenance=record["source"] or "reviewed",
        )

    async def connection(
        self,
        a_id: UUID,
        b_id: UUID,
        *,
        max_hops: int = 4,
        max_category_size: int | None = None,
    ) -> GraphConnection:
        """Return how two entities are connected (reviewed verdict + inferred chains).

        Parameters
        ----------
        a_id, b_id : UUID
            The two entities to connect.
        max_hops : int
            The traversal hop budget for the asserted tier (default 4).
        max_category_size : int | None
            A NAMED tractability bound on a shared category's global size — NOT a signal
            ceiling. ``None`` (the default) applies no cut: rank by log-specificity, never
            filter by breadth (measured review).

        Returns
        -------
        GraphConnection
            The result, with ``has_connection`` False when neither a verdict nor any
            inferred chain exists.
        """
        entity_a = await self.get_entity_node(a_id)
        entity_b = await self.get_entity_node(b_id)
        # One entity-count query shared by the two log-specificity tiers (chain + referent).
        entity_count = await self._entity_count()
        reviewed = await self.get_reviewed_verdict(a_id, b_id)
        kb_chain = await self.chain(
            a_id, b_id, max_hops=max_hops, entity_count=entity_count
        )
        referent = await self.shared_referents(a_id, b_id, entity_count=entity_count)
        category = await self.shared_category_chain(a_id, b_id)
        co_occurrence = await self.co_occurrence_chains(a_id, b_id)
        chains = [
            c for c in [kb_chain, referent, category, *co_occurrence] if c is not None
        ]
        # The model sorts chains into by-kind order and validates each ends at entity_b.
        return GraphConnection(
            entity_a=entity_a,
            entity_b=entity_b,
            reviewed_verdict=reviewed,
            chains=chains,
            searched_max_hops=max_hops,
            any_truncated=False,
        )
