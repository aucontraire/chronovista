#!/usr/bin/env python3
"""Load the chronovista entity graph into Neo4j AuraDB (typed co-occurrence edges).

Reads two files produced by the Postgres export:
  - entities.jsonl : one JSON object per entity node (key = entityId; qid rides along)
  - cooccurs.csv   : e1,e2,reltype,n  — one row per (pair, channel); reltype is one of
                     CO_OCCURS_TRANSCRIPT / _TITLEDESC / _MANUAL / _TAGS. A pair that co-occurs
                     in several channels gets one parallel typed edge per channel.

Idempotent: every write is a MERGE, so re-running after the local DB grows updates
counts and adds new nodes/edges without creating duplicates. Pass --wipe for a clean
full rebuild instead.

Credentials come from the environment (Aura gives you these on instance creation):
  NEO4J_URI        e.g. neo4j+s://xxxxxxxx.databases.neo4j.io
  NEO4J_USERNAME   usually 'neo4j'
  NEO4J_PASSWORD   the instance password

Usage:
  pip install neo4j
  export NEO4J_URI=... NEO4J_USERNAME=neo4j NEO4J_PASSWORD=...
  python load_neo4j.py                      # idempotent upsert
  python load_neo4j.py --wipe               # delete everything first, then load
  python load_neo4j.py --batch-size 2000    # smaller batches
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from neo4j import GraphDatabase

from chronovista.models.enums import EntityType

import neo4j_target  # shared Neo4j target resolver + remote-write guard (scripts/graph/)

# Co-occurrence is split into one edge TYPE per presence channel (CO_OCCURS_TRANSCRIPT /
# _TITLEDESC / _MANUAL / _TAGS). A reltype is loadable iff the export emitted it as a safe
# Cypher identifier; matching by PATTERN (not a hardcoded list) keeps the loader in sync with
# the export's channel set and is the injection guard for the type interpolated into Cypher.
_SAFE_COOCCUR = re.compile(r"^CO_OCCURS_[A-Z]+$")

# entity_type -> Neo4j secondary label (PascalCase), DERIVED from the single-source EntityType
# enum rather than re-inlining the vocabulary here (architecture single-source guard). Still a
# whitelist: only a known enum value becomes a label — an unmapped/untrusted entityType gets
# just :Entity — because the label is interpolated into Cypher.
TYPE_LABELS = {
    t.value: "".join(word.capitalize() for word in t.value.split("_"))
    for t in EntityType
}

HERE = Path(__file__).resolve().parent


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def load_nodes(session, nodes, batch_size):
    # Group by label so each MERGE carries the right (compile-time, whitelisted) label.
    by_label: dict[str, list[dict]] = {}
    for n in nodes:
        label = TYPE_LABELS.get(n.get("entityType", ""), None)
        by_label.setdefault(label or "", []).append(n)

    total = 0
    for label, rows in by_label.items():
        labels = "Entity" + (f":{label}" if label else "")
        cypher = (
            f"UNWIND $rows AS row "
            f"MERGE (e:{labels} {{entityId: row.entityId}}) "
            f"SET e += row"
        )
        for batch in chunked(rows, batch_size):
            session.run(cypher, rows=batch).consume()
            total += len(batch)
            print(f"  nodes :{labels:<24} +{len(batch):>5}  (total {total})")
    return total


def load_edges(session, edges, batch_size):
    # Group by reltype so each MERGE carries a compile-time, pattern-guarded relationship type.
    # A pair that co-occurs in several channels gets one typed edge per channel (parallel edges),
    # each with its own sharedVideos count — the combined/weighted view is a query-time concern.
    groups: dict[str, list[dict]] = defaultdict(list)
    skipped = 0
    for e in edges:
        rel = e["reltype"]
        if not _SAFE_COOCCUR.match(rel):
            skipped += 1
            continue
        groups[rel].append(e)
    if skipped:
        print(f"  (skipped {skipped} edges with unexpected reltypes)")

    total = 0
    for rel, rows in groups.items():
        cypher = (
            f"UNWIND $rows AS r "
            f"MATCH (a:Entity {{entityId: r.e1}}), (b:Entity {{entityId: r.e2}}) "
            f"MERGE (a)-[c:{rel}]->(b) "
            f"SET c.sharedVideos = toInteger(r.n)"
        )
        for batch in chunked(rows, batch_size):
            session.run(cypher, rows=batch).consume()
            total += len(batch)
            print(f"  edges :{rel:<22} +{len(batch):>5}  (total {total})")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entities", default=str(HERE / "entities.jsonl"))
    ap.add_argument("--edges", default=str(HERE / "cooccurs.csv"))
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--wipe", action="store_true", help="DETACH DELETE everything first")
    neo4j_target.add_argument(ap)
    args = ap.parse_args()

    uri, user, pw, db_name = neo4j_target.resolve(allow_remote=args.allow_remote)

    nodes = [json.loads(line) for line in Path(args.entities).read_text().splitlines() if line.strip()]
    with Path(args.edges).open() as f:
        edges = list(csv.DictReader(f))  # columns: e1, e2, reltype, n
    print(f"Loaded {len(nodes)} nodes and {len(edges)} edges from disk.")

    driver = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        driver.verify_connectivity()
        with driver.session(database=db_name) as session:
            if args.wipe:
                print("Wiping graph (DETACH DELETE)...")
                session.run("MATCH (n) DETACH DELETE n").consume()
            # Uniqueness constraint makes MERGE fast (index-backed) and blocks dupes.
            session.run(
                "CREATE CONSTRAINT entity_id IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.entityId IS UNIQUE"
            ).consume()
            print("Loading nodes...")
            n_nodes = load_nodes(session, nodes, args.batch_size)
            print("Loading CO_OCCURS_* edges (typed per channel)...")
            n_edges = load_edges(session, edges, args.batch_size)
            counts = session.run(
                "MATCH (e:Entity) WITH count(e) AS nodes "
                "MATCH ()-[c]->() WHERE type(c) STARTS WITH 'CO_OCCURS_' "
                "RETURN nodes, count(c) AS edges"
            ).single()
            by_type = session.run(
                "MATCH ()-[c]->() WHERE type(c) STARTS WITH 'CO_OCCURS_' "
                "RETURN type(c) AS t, count(c) AS n ORDER BY n DESC"
            ).data()
        print(f"\nDone. Wrote {n_nodes} nodes / {n_edges} edges.")
        print(f"Graph now holds {counts['nodes']} :Entity nodes and {counts['edges']} CO_OCCURS_* edges:")
        for row in by_type:
            print(f"  :{row['t']:<22} {row['n']:>7}")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
