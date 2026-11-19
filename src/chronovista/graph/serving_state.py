"""Serving-state contract for the connection-explorer graph (Features 112/113).

ONE home for the rule that decides whether the graph may be served, shared by the four
destructive loaders (``scripts/graph/load_{neo4j,semantic,categories,reviewed}.py``) and the
read API. The governing decisions below are guarded by a mutation-verified fitness test
(``tests/unit/architecture/test_graph_serving_state_bracket.py``) so they cannot quietly
leave committed code — editing them is a reviewable diff.

Committed contract
------------------
**DECLARED, not inferred.** A build records which layers it was *configured* to contain, in
``:Meta.declaredLayers``. The serving check compares the layers actually PRESENT against that
DECLARED set — never against a fixed "all layers always present" assumption, and never against
whether an input file happens to exist. A layer absent *by declaration* is fine; a
declared-expected layer that is absent makes the graph **not-servable** (so an accidental loss
is caught, not read as "by design"). Inferring "skip" from a missing file would let an
accidental loss serve a silently-degraded graph — the asymmetry (a wrongly-required layer
fails loud and cheap; a wrongly-optional one degrades silently and expensively) puts the
default on the loud side.

**PRESENCE, not completeness.** The check verifies each declared layer has >=1 element. It
catches a fully-wiped declared layer, NOT a half-populated one; the single production refresh
trigger (``reload_all.sh``) covers the half-populated residual. The name is "presence" so no
reader over-trusts it.

**The declared set describes the BUILD, not live config.** It is recorded at build time in
``:Meta``; the serving check reads ``:Meta``, never configuration at serve time. Editing config
without reloading must not retroactively mark a correctly-built graph unservable — a change to
the expected layer set takes effect at the next refresh.

**Re-entrant bracket.** ``:Meta.bracketDepth`` counts nested open/close across the four
independently-runnable loaders; ``status`` is ``'complete'`` only at depth 0. The orchestrator
(``reload_all.sh``) holds an outer bracket (``begin_build`` -> ``leave``) so an orchestrated run
never flips servable *between* layer steps. A standalone loader run (depth 0 -> 1 -> 0) still
brackets correctly.

The functions here take a ``neo4j`` **synchronous** session (the loaders are sync scripts). The
read API computes servability asynchronously in ``Neo4jGraphRepository`` using
:data:`META_READ_CYPHER`, :data:`LAYER_PRESENCE_CYPHER`, and the pure predicate
:func:`is_servable`; it never calls the bracket mutators.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

#: Singleton key for the serving-state node (one per graph).
META_ID = "graph"


class GraphLayer(str, Enum):
    """The data layers a build can declare. Values are what ``:Meta.declaredLayers`` stores."""

    OBSERVED = "observed"  # :Entity nodes + CO_OCCURS_* edges  (load_neo4j)
    SEMANTIC = (
        "semantic"  # edges stamped layer='wikidata' + :WikidataItem  (load_semantic)
    )
    CATEGORIES = "categories"  # :Category nodes + :IN_CATEGORY edges  (load_categories)
    REVIEWED = (
        "reviewed"  # edges stamped layer='reviewed'  (load_reviewed) — CONDITIONAL
    )


#: Per-layer "is at least one element present?" probes. Markers verified against the loaders:
#: semantic edges carry ``layer='wikidata'`` (load_semantic), reviewed carry ``layer='reviewed'``
#: (load_reviewed), categories materialise ``:Category`` nodes, observed materialise ``:Entity``.
#: Existence only (``RETURN 1``, never the hydrated node/relationship) and directed edge matches
#: (``-[r]->``, so each edge is matched once, not twice as an undirected pattern would). ``LIMIT 1``
#: short-circuits the present case; the absent case the probe is meant to catch still scans, so a
#: relationship-property index on ``layer`` is the lever if that failure path ever gets hot.
LAYER_PRESENCE_CYPHER: dict[GraphLayer, str] = {
    GraphLayer.OBSERVED: "MATCH (e:Entity) RETURN 1 LIMIT 1",
    GraphLayer.SEMANTIC: "MATCH ()-[r]->() WHERE r.layer = 'wikidata' RETURN 1 LIMIT 1",
    GraphLayer.CATEGORIES: "MATCH (c:Category) RETURN 1 LIMIT 1",
    GraphLayer.REVIEWED: "MATCH ()-[r]->() WHERE r.layer = 'reviewed' RETURN 1 LIMIT 1",
}

#: Read the serving-state node (status, loadedAt, declaredLayers).
META_READ_CYPHER = (
    f"MATCH (m:Meta {{id: '{META_ID}'}}) "
    "RETURN m.status AS status, m.loadedAt AS loaded_at, "
    "m.declaredLayers AS declared_layers"
)


class _Session(Protocol):
    """Minimal structural type for a neo4j sync session (avoids importing neo4j here)."""

    def run(self, query: str, **kwargs: object) -> object: ...


def begin_build(session: _Session, declared_layers: list[str]) -> None:
    """Start a fresh build (the orchestrator's outer bracket).

    Records the declared layer set, marks the graph loading, and sets the bracket depth to 1.
    Called once by ``reload_all.sh`` before the wipe. ``:Meta`` survives the subsequent
    ``load_neo4j --wipe`` because that delete is scoped ``WHERE NOT n:Meta``.

    NOTE: the depth is set absolutely (to 1), so **concurrent orchestrated reloads are not
    supported** — two overlapping ``reload_all.sh`` runs would corrupt the depth and could flip
    the graph servable mid-rebuild. This is safe because FR-016 exposes exactly ONE refresh
    trigger in production; do not run two reloads at once.
    """
    session.run(
        f"MERGE (m:Meta {{id: '{META_ID}'}}) "
        "SET m.status = 'loading', m.bracketDepth = 1, "
        "m.declaredLayers = $layers, m.loadedAt = null",
        layers=declared_layers,
    )


def enter(session: _Session) -> None:
    """Enter a loader's bracket (depth += 1, mark loading). Call at the start of each loader."""
    session.run(
        f"MERGE (m:Meta {{id: '{META_ID}'}}) "
        "SET m.bracketDepth = coalesce(m.bracketDepth, 0) + 1, m.status = 'loading'"
    )


def leave(session: _Session) -> None:
    """Leave a bracket (depth -= 1). At depth 0 the graph becomes ``complete`` with a fresh
    ``loadedAt``; above 0 it stays ``loading``. Call at the end of each loader, and once by the
    orchestrator to close its outer bracket.
    """
    session.run(
        f"MATCH (m:Meta {{id: '{META_ID}'}}) "
        "SET m.bracketDepth = coalesce(m.bracketDepth, 1) - 1 "
        "WITH m, (coalesce(m.bracketDepth, 0) <= 0) AS done "
        "SET m.status = CASE WHEN done THEN 'complete' ELSE 'loading' END, "
        "m.loadedAt = CASE WHEN done THEN datetime() ELSE m.loadedAt END"
    )


def is_servable(
    status: str | None,
    declared_layers: list[str] | None,
    present_layers: set[str],
) -> bool:
    """Pure predicate: may the graph be served?

    Servable iff the build is ``complete`` AND every *declared* layer is present. A declared
    layer that is absent (lost/wiped) makes it unservable; a layer absent by declaration does
    not. Unknown/absent declaration (no build yet) is not servable (safe default).
    """
    if status != "complete" or not declared_layers:
        return False
    return all(layer in present_layers for layer in declared_layers)
