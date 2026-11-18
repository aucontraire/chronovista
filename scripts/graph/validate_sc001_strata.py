#!/usr/bin/env python3
"""SC-001 stratified validation — a MEASUREMENT activity, not a CI gate (Feature 112, T034).

SC-001: for pairs with a documented asserted connection, the explorer returns the asserted tie
labelled *asserted* (not swallowed into co-occurrence), measured with **per-stratum minimums**
(>=10 each), not a single global n — because a global sample is dominated by the easy
no-competitor case and ranking failures concentrate. The strata:

  (a) forward-asserted ........... a directed KB chain A -> ... -> B
  (b) inverse-only-asserted ...... a chain that exists ONLY on the inverse side (B -> ... -> A),
                                   with no forward path — the hard, motivating case
  (c) high-co-occurrence+asserted  an asserted tie on a pair that ALSO co-occurs (the competitor)
  (d) non-co-occurring+grouping .. a specific shared grouping between NON-co-occurring entities
                                   (the measured-review "untested cell")

Consult integrity is a PASS CONDITION: a pair whose ``connection()`` raised (an unverified
consultation) FAILS the stratum — it never silently counts as "no connection". Output is
counts and rates only; no entity names or ids are printed (this repo is public).

Run against the loaded dev graph, e.g.:
  NEO4J_URI=bolt://localhost:7688 NEO4J_USER=neo4j NEO4J_PWD=dev_password \
    poetry run python scripts/graph/validate_sc001_strata.py
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from chronovista.graph import GraphUnavailableError, Neo4jClient
from chronovista.models.graph_connection import ConnectionKind, GraphConnection
from chronovista.repositories.neo4j_graph_repository import Neo4jGraphRepository

# Each stratum: a discovery query (returns a, b entity ids) + a predicate on the result that
# encodes SC-001's expectation for that stratum.
_STRATA: dict[str, str] = {
    "forward-asserted": (
        "MATCH (a:Entity)-[r1]->(m)-[r2]->(b:Entity) "
        "WHERE r1.layer='wikidata' AND r2.layer='wikidata' "
        "AND a.entityId < b.entityId AND m <> a AND m <> b "
        "RETURN a.entityId AS a, b.entityId AS b LIMIT $lim"
    ),
    "inverse-only-asserted": (
        "MATCH (b:Entity)-[r1]->(m)-[r2]->(a:Entity) "
        "WHERE r1.layer='wikidata' AND r2.layer='wikidata' "
        "AND a.entityId < b.entityId AND m <> a AND m <> b "
        "AND NOT EXISTS { MATCH p=(a)-[*1..4]->(b) "
        "WHERE all(r IN relationships(p) WHERE r.layer='wikidata') } "
        "RETURN a.entityId AS a, b.entityId AS b LIMIT $lim"
    ),
    "high-co-occurrence+asserted": (
        "MATCH (a:Entity)-[r1]->(m)-[r2]->(b:Entity) "
        "WHERE r1.layer='wikidata' AND r2.layer='wikidata' "
        "AND a.entityId < b.entityId AND m <> a AND m <> b "
        "AND EXISTS { MATCH (a)-[c]-(b) WHERE type(c) STARTS WITH 'CO_OCCURS_' } "
        "RETURN a.entityId AS a, b.entityId AS b LIMIT $lim"
    ),
    "non-co-occurring+grouping": (
        "MATCH (a:Entity)-[:IN_CATEGORY]->(c:Category)<-[:IN_CATEGORY]-(b:Entity) "
        "WHERE a.entityId < b.entityId AND c.globalSize < 1000000 "
        "AND NOT EXISTS { MATCH (a)-[x]-(b) WHERE type(x) STARTS WITH 'CO_OCCURS_' } "
        "RETURN a.entityId AS a, b.entityId AS b LIMIT $lim"
    ),
}


def _has(conn: GraphConnection, kind: ConnectionKind) -> bool:
    return any(chain.kind is kind for chain in conn.chains)


def _has_co_occurrence(conn: GraphConnection) -> bool:
    return any(chain.kind.value.startswith("co_occurrence_") for chain in conn.chains)


def _passes(stratum: str, conn: GraphConnection) -> bool:
    """SC-001 expectation per stratum."""
    if stratum in ("forward-asserted", "inverse-only-asserted"):
        return _has(conn, ConnectionKind.ASSERTED)
    if stratum == "high-co-occurrence+asserted":
        # The asserted tie must be surfaced AS asserted even when co-occurrence competes.
        return _has(conn, ConnectionKind.ASSERTED) and _has_co_occurrence(conn)
    # non-co-occurring+grouping: the grouping surfaces for a non-co-occurring pair.
    return (
        _has(conn, ConnectionKind.SHARED_CATEGORY)
        or _has(conn, ConnectionKind.SHARED_REFERENT)
    ) and not _has_co_occurrence(conn)


async def _draw(client: Neo4jClient, cypher: str, limit: int) -> list[tuple[UUID, UUID]]:
    async with client.session() as session:
        rows = [rec async for rec in await session.run(cypher, lim=limit)]
    return [(UUID(r["a"]), UUID(r["b"])) for r in rows]


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=20, help="pairs to draw per stratum (>=10)")
    args = ap.parse_args()

    client = Neo4jClient.from_settings()
    try:
        repo = Neo4jGraphRepository(client)
        print(f"SC-001 stratified validation (limit {args.limit}/stratum)\n")
        overall_ok = True
        for stratum, cypher in _STRATA.items():
            pairs = await _draw(client, cypher, args.limit)
            drawn = len(pairs)
            passed = consult_failures = 0
            for a_id, b_id in pairs:
                try:
                    conn = await repo.connection(a_id, b_id)
                except Exception:  # an unverified consultation fails the criterion
                    consult_failures += 1
                    continue
                if _passes(stratum, conn):
                    passed += 1
            rate = f"{passed}/{drawn}" if drawn else "0/0"
            flags = []
            if drawn < 10:
                flags.append("UNDER-SAMPLED (<10)")
            if consult_failures:
                flags.append(f"{consult_failures} consult failures")
            if drawn and passed < drawn:
                flags.append("MISSES")
            note = ("  <- " + "; ".join(flags)) if flags else ""
            print(f"  {stratum:<28} {rate:>7}{note}")
            if drawn < 10 or consult_failures or (drawn and passed < drawn):
                overall_ok = False
        print(
            "\nSC-001 "
            + ("PASS" if overall_ok else "ATTENTION — see flagged strata above")
        )
        return 0 if overall_ok else 1
    except GraphUnavailableError as exc:
        print(f"graph unavailable: {exc}")
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
