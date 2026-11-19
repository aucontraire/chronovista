#!/usr/bin/env python3
"""reload_all.sh's hook into the serving-state bracket (Feature 113).

Opens (``begin``) and closes (``end``) the orchestrator's OUTER bracket so an orchestrated full
rebuild never flips the graph 'complete' BETWEEN layer steps — the loaders' own enter/leave keep
the depth above zero only while each is running, so without this outer bracket the graph would
read servable in the gaps between layers. Connects through the shared ``neo4j_target`` guard, so
it inherits the same remote-write protection as the loaders.

Usage (from reload_all.sh):
  python serving_state_cli.py begin --layers observed,semantic,categories,reviewed [--allow-remote]
  python serving_state_cli.py end [--allow-remote]
"""
from __future__ import annotations

import argparse

from neo4j import GraphDatabase

from chronovista.graph import serving_state

import neo4j_target  # shared Neo4j target resolver + remote-write guard (scripts/graph/)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["begin", "end"])
    ap.add_argument(
        "--layers",
        default="",
        help="comma-separated declared layer names (begin only)",
    )
    neo4j_target.add_argument(ap)
    args = ap.parse_args()

    uri, user, pw, db_name = neo4j_target.resolve(allow_remote=args.allow_remote)
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        driver.verify_connectivity()
        with driver.session(database=db_name) as session:
            if args.action == "begin":
                layers = [x for x in args.layers.split(",") if x]
                serving_state.begin_build(session, layers)
                print(
                    "Serving-state: build begun; declared layers: "
                    + (", ".join(layers) or "(none)")
                )
            else:
                serving_state.leave(session)
                print("Serving-state: outer bracket closed (complete at depth 0).")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
