#!/usr/bin/env python3
"""Load the category layer into Neo4j (run AFTER load_neo4j.py, which creates the :Entity nodes).

Adds, from category_edges.jsonl (produced by export_graph.sh):
  - (:Category {name, globalSize}) nodes, deduped by name — so a category node's DEGREE is "how many
    of your entities share it" (local specificity), and globalSize is the category's global Wikipedia
    member count (global specificity: a huge category like "Living people" is near-useless, a niche
    one is gold).
  - (:Entity)-[:IN_CATEGORY]->(:Category) edges; the exporter scopes these to entities already in the
    graph, so there are no orphan category endpoints.

Shared-category relatedness is then a 2-hop:
  (e1:Entity)-[:IN_CATEGORY]->(c:Category)<-[:IN_CATEGORY]-(e2:Entity)
ranked by 1/c.globalSize or 1/size((c)<-[:IN_CATEGORY]-()) — rank by specificity, never filter.

Source note: these are the LIVE Wikipedia category tables (chronovista Features 083/084:
entity_categories JOIN wikipedia_categories), fetched from the MediaWiki API — NOT the DBpedia
snapshot. The DBpedia snapshot is the separate, smaller named_entities.properties->'category'
store, which Feature 086 measured as diverging ~27% from this live set (that divergence is the
proof these are not DBpedia, not a reason to distrust them). This layer also carries the v0.104.1
redirect-fix recoveries and the Feature 100 foreign-language cross-walk recoveries, so it is the
best-measured category signal in the graph.

Idempotent (all MERGE). --wipe-categories clears the layer first for a clean rebuild.

CAVEAT: load_semantic.py --wipe-semantic deletes EVERY non-CO_OCCURS edge (it includes :IN_CATEGORY),
so re-run this loader after any semantic wipe. The full rebuild (reload_all.sh) runs this layer LAST
for exactly that reason — same discipline as the reviewed layer.

Env (same as the sibling loaders): NEO4J_URI, NEO4J_USER(/NAME), NEO4J_PWD(/PASSWORD), DB_NAME.
Usage:
  python load_categories.py
  python load_categories.py --wipe-categories
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from neo4j import GraphDatabase

import neo4j_target  # shared Neo4j target resolver + remote-write guard (scripts/graph/)

HERE = Path(__file__).resolve().parent


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def load_category_nodes(session, rows, batch_size):
    # Dedup categories by name (the shared-node key). globalSize may be null; coalesce keeps a value
    # already set rather than overwriting it with null.
    seen: dict[str, object] = {}
    for r in rows:
        name = r["categoryName"]
        if name not in seen or seen[name] is None:
            seen[name] = r.get("globalSize")
    nodes = [{"name": n, "globalSize": gs} for n, gs in seen.items()]
    cypher = (
        "UNWIND $rows AS row "
        "MERGE (c:Category {name: row.name}) "
        "SET c.globalSize = coalesce(row.globalSize, c.globalSize)"
    )
    total = 0
    for batch in chunked(nodes, batch_size):
        session.run(cypher, rows=batch).consume()
        total += len(batch)
        print(f"  nodes :Category    +{len(batch):>5}  (total {total})")
    return total


def load_category_edges(session, rows, batch_size):
    cypher = (
        "UNWIND $rows AS r "
        "MATCH (e:Entity {entityId: r.entityId}) "
        "MATCH (c:Category {name: r.categoryName}) "
        "MERGE (e)-[:IN_CATEGORY]->(c)"
    )
    total = 0
    for batch in chunked(rows, batch_size):
        session.run(cypher, rows=batch).consume()
        total += len(batch)
        print(f"  edges :IN_CATEGORY +{len(batch):>5}  (total {total})")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--edges", default=str(HERE / "category_edges.jsonl"))
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument(
        "--wipe-categories",
        action="store_true",
        help="delete all :Category nodes (and their :IN_CATEGORY edges) first",
    )
    neo4j_target.add_argument(ap)
    args = ap.parse_args()

    uri, user, pw, db_name = neo4j_target.resolve(allow_remote=args.allow_remote)

    rows = [
        json.loads(line)
        for line in Path(args.edges).read_text().splitlines()
        if line.strip()
    ]
    print(f"Loaded {len(rows)} entity->category edges from disk.")

    driver = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        driver.verify_connectivity()
        with driver.session(database=db_name) as session:
            if args.wipe_categories:
                print("Wiping category layer...")
                session.run("MATCH (c:Category) DETACH DELETE c").consume()
            # Uniqueness constraint dedupes categories + makes the edge MATCH fast.
            session.run(
                "CREATE CONSTRAINT category_name IF NOT EXISTS "
                "FOR (c:Category) REQUIRE c.name IS UNIQUE"
            ).consume()
            print("Loading category nodes...")
            n_nodes = load_category_nodes(session, rows, args.batch_size)
            print("Loading :IN_CATEGORY edges...")
            n_edges = load_category_edges(session, rows, args.batch_size)
            counts = session.run(
                "MATCH (c:Category) WITH count(c) AS cats "
                "OPTIONAL MATCH ()-[r:IN_CATEGORY]->() "
                "RETURN cats, count(r) AS edges"
            ).single()
        print(f"\nDone. Wrote {n_nodes} category nodes / {n_edges} edges.")
        print(
            f"Graph now holds {counts['cats']} :Category nodes "
            f"and {counts['edges']} :IN_CATEGORY edges."
        )
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
