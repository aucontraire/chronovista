#!/usr/bin/env python3
"""Load the human-REVIEWED relationship layer into Neo4j (run AFTER load_neo4j.py).

This is the bridge the typed-edge store will eventually formalize: it takes the confirmed
verdicts from the novel-relationship review (`verdicts.jsonl`, in the gitignored wayfinder
tree) and writes them as a third graph layer, alongside CO_OCCURS_* (observed) and the
Wikidata semantic layer.

  verdict -> edge
    R  (connected/social)                 -> :ASSOCIATED_WITH
    R  with via="cast:<work>" (castmates) -> :CO_CAST          (co-cast != acquaintance)
    T  (covers/focus)                     -> :COVERS           (see DIRECTION caveat below)
    C  (coincidence)                      -> :REVIEWED_COINCIDENCE  (undirected; carries origin
                                             so the explorer can origin-gate its suppression)
    A / ? / unmarked                      -> no edge (artifact / undecided)

Each edge carries provenance so downstream can filter on trust:
    verdict, confidence, source, origin, confirmedBy, confirmedAt, via, reason, layer='reviewed'
  confidence = 'high'  when origin is absent (human-originated) or origin='reaudited-C'
             = 'medium' when origin='suggested-agreed' (machine-proposed, human-kept, not researched)
  Evidence (sharedVideos, lift) is joined from novel_queue.json when present.

Idempotent (all MERGE). --wipe-reviewed clears the layer first. --high-only loads only
confidence='high' edges (CDWA's ingestion guard: trust origin != 'suggested-agreed').

CAVEATS (first version / sketch):
  * DIRECTION — the review stored pairs unordered (sorted eid pair), so COVERS has no
    direction: it is written lower-eid -> higher-eid with `direction:'unknown'`. "X covers Y"
    vs "Y covers X" is not recoverable from the current data; capture direction at review time
    before COVERS is treated as directed.
  * SPARSE NODES — a reviewed pair co-occurs in the TITLE+DESCRIPTION channel, but the default
    graph nodes come from the TRANSCRIPT channel, so an endpoint may not be a node yet. We
    MERGE it (ON CREATE SET name, reviewedOnly=true) so no edge is lost; such nodes are flagged.
  * This layer is NOT produced by export_graph.sh and is wiped by `load_neo4j.py --wipe`
    (which clears the whole DB) — re-run this loader after any full reload.

Env (same as load_neo4j.py): NEO4J_URI, NEO4J_USER(/NAME), NEO4J_PWD(/PASSWORD), DB_NAME.
Usage:
  python load_reviewed.py --dry-run     # print the edge plan and exit (no creds, no neo4j driver needed)
  python load_reviewed.py               # load all 811, tagged by confidence
  python load_reviewed.py --high-only   # only confidence='high' (origin != 'suggested-agreed')
  python load_reviewed.py --wipe-reviewed
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import neo4j_target  # shared Neo4j target resolver + remote-write guard (scripts/graph/)

REL_TYPES = {
    "ASSOCIATED_WITH",
    "COVERS",
    "CO_CAST",
    "REVIEWED_COINCIDENCE",
}  # never interpolate untrusted text as a type
HERE = Path(__file__).resolve().parent
# verdicts live in the gitignored wayfinder tree, not next to this script. Derive the repo root
# from this file's location (HERE = scripts/graph) so it works wherever the repo is checked out;
# CHRONO_REPO / CHRONO_VERDICTS override.
_REPO = Path(os.environ.get("CHRONO_REPO") or HERE.parents[1])
VERDICTS = Path(
    os.environ.get("CHRONO_VERDICTS")
    or _REPO / "src/chronovista/docs/wayfinder/knowledge-graph-jobs/verdicts.jsonl"
)
QUEUE = VERDICTS.with_name("novel_queue.json")


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def edge_type(rec) -> str | None:
    v = rec.get("verdict")
    if v == "R":
        return (
            "CO_CAST"
            if str(rec.get("via", "")).startswith("cast:")
            else "ASSOCIATED_WITH"
        )
    if v == "T":
        return "COVERS"
    if v == "C":
        return "REVIEWED_COINCIDENCE"  # undirected; the explorer origin-gates its suppression
    return None  # A / ? -> not an edge


def confidence(rec) -> str:
    o = rec.get("origin")
    return (
        "medium" if o == "suggested-agreed" else "high"
    )  # absent or 'reaudited-C' -> high


def build_rows(high_only: bool):
    verdicts = [json.loads(l) for l in VERDICTS.read_text().splitlines() if l.strip()]
    # eid -> name and pair -> evidence, from the queue mirror (authoritative name per eid)
    name, ev = {}, {}
    if QUEUE.exists():
        for r in json.load(QUEUE.open()):
            name[r["entity_a"]] = r["name_a"]
            name[r["entity_b"]] = r["name_b"]
            dv = r.get("discovered_via") or {}
            ev["__".join(sorted((r["entity_a"], r["entity_b"])))] = (
                dv.get("shared_videos"),
                dv.get("lift"),
            )
    groups: dict[str, list[dict]] = defaultdict(list)
    skipped_conf = 0
    for rec in verdicts:
        et = edge_type(rec)
        if not et:
            continue
        conf = confidence(rec)
        if high_only and conf != "high":
            skipped_conf += 1
            continue
        a, b = rec["pair"].split("__")  # already sorted
        sv, lift = ev.get(rec["pair"], (None, None))
        groups[et].append(
            {
                "a": a,
                "b": b,
                "na": name.get(a, rec.get("name_a")),
                "nb": name.get(b, rec.get("name_b")),
                "verdict": rec.get("verdict"),
                "confidence": conf,
                "source": rec.get("source"),
                "origin": rec.get("origin"),
                "cb": rec.get("confirmed_by"),
                "ca": rec.get("confirmed_at"),
                "via": rec.get("via"),
                "reason": rec.get("reason"),
                "sv": sv,
                "lift": lift,
                "directed": et not in {"COVERS", "REVIEWED_COINCIDENCE"},
            }
        )
    return groups, skipped_conf


def load_group(session, rel, rows, batch_size):
    cypher = (
        "UNWIND $rows AS r "
        "MERGE (a:Entity {entityId: r.a}) ON CREATE SET a.name = r.na, a.reviewedOnly = true "
        "MERGE (b:Entity {entityId: r.b}) ON CREATE SET b.name = r.nb, b.reviewedOnly = true "
        f"MERGE (a)-[e:{rel}]->(b) "
        "SET e.verdict=r.verdict, e.confidence=r.confidence, e.source=r.source, e.origin=r.origin, "
        "    e.confirmedBy=r.cb, e.confirmedAt=r.ca, e.via=r.via, e.reason=r.reason, "
        "    e.sharedVideos=r.sv, e.lift=r.lift, e.directed=r.directed, e.layer='reviewed'"
    )
    total = 0
    for batch in chunked(rows, batch_size):
        session.run(cypher, rows=batch).consume()
        total += len(batch)
        print(f"  edges :{rel:<16} +{len(batch):>4}  (total {total})")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch-size", type=int, default=2000)
    ap.add_argument(
        "--wipe-reviewed",
        action="store_true",
        help="delete the reviewed layer (layer='reviewed' edges + orphan reviewedOnly nodes) first",
    )
    ap.add_argument(
        "--high-only",
        action="store_true",
        help="load only confidence='high' edges (origin != 'suggested-agreed')",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print the edge plan and exit — no DB connection, no creds needed",
    )
    neo4j_target.add_argument(ap)
    args = ap.parse_args()

    if not VERDICTS.exists():
        sys.exit(f"verdicts not found: {VERDICTS}")

    groups, skipped_conf = build_rows(args.high_only)
    n = sum(len(v) for v in groups.values())
    print(
        f"Prepared {n} reviewed edges "
        + ", ".join(f"{k} {len(v)}" for k, v in sorted(groups.items()))
        + (
            f"  (skipped {skipped_conf} medium-confidence via --high-only)"
            if skipped_conf
            else ""
        )
    )

    if args.dry_run:
        print("\n[DRY RUN] no DB connection — edge plan:")
        for rel, rows in sorted(groups.items()):
            cc = Counter(r["confidence"] for r in rows)
            miss = sum(1 for r in rows if r["sv"] is None)
            print(
                f"  :{rel:<16} {len(rows):>4}  (high {cc['high']}, medium {cc['medium']}"
                + (f", {miss} w/o evidence" if miss else "")
                + ")"
            )
            for r in rows[:3]:
                arrow = "->" if rel == "COVERS" else "<->"
                print(
                    f"       {r['na']} {arrow} {r['nb']}  [{r['confidence']}]"
                    + (f" via={r['via']}" if r["via"] else "")
                    + (f" sv={r['sv']} lift={r['lift']}" if r["sv"] is not None else "")
                )
        sparse = {e for rows in groups.values() for r in rows for e in (r["a"], r["b"])}
        print(
            f"\n  distinct entities referenced: {len(sparse)} "
            "(any not already in the graph are MERGEd as reviewedOnly nodes)"
        )
        print(
            "  COVERS direction is not captured → written undirected (directed:false)."
        )
        return 0

    uri, user, pw, db_name = neo4j_target.resolve(allow_remote=args.allow_remote)

    from neo4j import (
        GraphDatabase,
    )  # lazy: --dry-run needs neither creds nor the driver installed

    driver = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        driver.verify_connectivity()
        with driver.session(database=db_name) as session:
            if args.wipe_reviewed:
                print("Wiping reviewed layer...")
                for rel in REL_TYPES:
                    session.run(
                        f"MATCH ()-[r:{rel} {{layer:'reviewed'}}]->() DELETE r"
                    ).consume()
                session.run(
                    "MATCH (n:Entity {reviewedOnly:true}) WHERE NOT (n)--() DELETE n"
                ).consume()
            session.run(
                "CREATE INDEX entity_id IF NOT EXISTS FOR (e:Entity) ON (e.entityId)"
            ).consume()
            total = 0
            for rel, rows in sorted(groups.items()):
                total += load_group(session, rel, rows, args.batch_size)
            counts = session.run(
                "MATCH ()-[r]->() WHERE r.layer='reviewed' "
                "RETURN type(r) AS t, r.confidence AS c, count(*) AS n ORDER BY t, c"
            ).data()
        print(f"\nDone. Wrote {total} reviewed edges.")
        for row in counts:
            print(f"  :{row['t']:<16} {row['c']:<7} {row['n']}")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
