#!/usr/bin/env python3
"""Load the v2 semantic layer into Neo4j (run AFTER load_neo4j.py).

Adds, from two files produced by export_graph.sh:
  - wikidata_stubs.jsonl : (:WikidataItem {qid, name}) for relation targets that are
    NOT already entity nodes in the graph.
  - semantic_edges.csv   : src,reltype,targetqid,targetIsEntity  -> typed relationships
    (:Entity)-[:EMPLOYER|:EDUCATED_AT|...]->(:Entity | :WikidataItem)

targetIsEntity=1 links to an existing :Entity (by qid); =0 links to a :WikidataItem stub.
Idempotent (all MERGE). --wipe-semantic clears the layer first for a clean rebuild.

Env (same as load_neo4j.py): NEO4J_URI, NEO4J_USER(/NAME), NEO4J_PWD(/PASSWORD), DB_NAME.
Usage:
  python load_semantic.py
  python load_semantic.py --wipe-semantic
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from neo4j import GraphDatabase

from chronovista.graph import serving_state  # serving-state bracket (Feature 113)

import neo4j_target  # shared Neo4j target resolver + remote-write guard (scripts/graph/)

# Whitelist of relationship types we emit (never interpolate untrusted text as a type).
# A relationship type is loadable iff the export emitted it as a safe Cypher identifier (uppercase
# letters + underscores). The export's RELS derives from wikidata_properties.RELATIONS, so matching by
# PATTERN (not a hardcoded allowlist) keeps this loader auto-synced with the registry and drift-proof —
# the old static allowlist silently dropped the 087/088/095 edge types for releases. This regex is also
# the injection guard for the rel type interpolated into Cypher below.
_SAFE_REL = re.compile(r"^[A-Z][A-Z_]+$")
HERE = Path(__file__).resolve().parent


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def load_stubs(session, stubs, batch_size):
    cypher = "UNWIND $rows AS row MERGE (w:WikidataItem {qid: row.qid}) SET w.name = row.name"
    total = 0
    for batch in chunked(stubs, batch_size):
        session.run(cypher, rows=batch).consume()
        total += len(batch)
        print(f"  stubs :WikidataItem +{len(batch):>5}  (total {total})")
    return total


def load_edges(session, edges, batch_size):
    # Group by (relType, targetIsEntity) so each MERGE has a compile-time rel type and
    # the right target label.
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    skipped = 0
    for e in edges:
        rel = e["reltype"]
        if not _SAFE_REL.match(rel):
            skipped += 1
            continue
        groups[(rel, e["targetIsEntity"])].append(e)
    if skipped:
        print(f"  (skipped {skipped} edges with unexpected rel types)")

    total = 0
    for (rel, is_entity), rows in groups.items():
        target_label = "Entity" if is_entity == "1" else "WikidataItem"
        # Stamp layer='wikidata' so the connection explorer can tell KB facts from the
        # reviewed layer (layer='reviewed') with ONE predicate — drift-proof vs an
        # allowlist of rel-type names (Feature 112, DESIGN §9.3).
        cypher = (
            f"UNWIND $rows AS r "
            f"MATCH (s:Entity {{entityId: r.src}}) "
            f"MATCH (t:{target_label} {{qid: r.targetqid}}) "
            f"MERGE (s)-[e:{rel}]->(t) "
            f"SET e.layer = 'wikidata'"
        )
        for batch in chunked(rows, batch_size):
            session.run(cypher, rows=batch).consume()
            total += len(batch)
            print(
                f"  edges :{rel:<16}->{target_label:<13} +{len(batch):>5}  (total {total})"
            )
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stubs", default=str(HERE / "wikidata_stubs.jsonl"))
    ap.add_argument("--edges", default=str(HERE / "semantic_edges.csv"))
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument(
        "--wipe-semantic",
        action="store_true",
        help="delete all WikidataItem nodes and semantic rel types first",
    )
    neo4j_target.add_argument(ap)
    args = ap.parse_args()

    uri, user, pw, db_name = neo4j_target.resolve(allow_remote=args.allow_remote)

    stubs = [
        json.loads(l) for l in Path(args.stubs).read_text().splitlines() if l.strip()
    ]
    with Path(args.edges).open() as f:
        edges = list(csv.DictReader(f))  # src, reltype, targetqid, targetIsEntity
    print(f"Loaded {len(stubs)} stubs and {len(edges)} semantic edges from disk.")

    driver = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        driver.verify_connectivity()
        with driver.session(database=db_name) as session:
            serving_state.enter(session)  # bracket this layer (Feature 113)
            if args.wipe_semantic:
                print("Wiping semantic layer...")
                # Delete every non-co-occurrence edge. Guards the WHOLE CO_OCCURS_* family (the
                # edge-type split renamed CO_OCCURS_WITH → CO_OCCURS_TRANSCRIPT/_TITLEDESC/_MANUAL/
                # _TAGS; a `<> 'CO_OCCURS_WITH'` test would now wipe the entire observed layer).
                # Drift-proof (prefix, no rel-type list). DETACH DELETE of stubs clears the rest.
                session.run(
                    "MATCH ()-[r]->() WHERE NOT type(r) STARTS WITH 'CO_OCCURS_' DELETE r"
                ).consume()
                session.run("MATCH (w:WikidataItem) DETACH DELETE w").consume()
            # Constraint dedupes stubs + makes target MATCH fast; index speeds entity-target MATCH.
            session.run(
                "CREATE CONSTRAINT wikidata_qid IF NOT EXISTS "
                "FOR (w:WikidataItem) REQUIRE w.qid IS UNIQUE"
            ).consume()
            session.run(
                "CREATE INDEX entity_qid IF NOT EXISTS FOR (e:Entity) ON (e.qid)"
            ).consume()
            print("Loading stub nodes...")
            n_stubs = load_stubs(session, stubs, args.batch_size)
            print("Loading semantic edges...")
            n_edges = load_edges(session, edges, args.batch_size)
            counts = session.run(
                "MATCH (w:WikidataItem) WITH count(w) AS stubs "
                "MATCH ()-[r]->() WHERE NOT type(r) STARTS WITH 'CO_OCCURS_' "
                "RETURN stubs, count(r) AS semrels"
            ).single()
            serving_state.leave(session)  # close bracket only on success (Feature 113)
        print(f"\nDone. Wrote {n_stubs} stubs / {n_edges} semantic edges.")
        print(
            f"Graph now holds {counts['stubs']} :WikidataItem nodes and {counts['semrels']} semantic relationships."
        )
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
