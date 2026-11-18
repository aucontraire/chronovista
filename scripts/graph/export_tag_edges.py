#!/usr/bin/env python3
"""Export CO_OCCURS_TAGS edges from the FULL tag-association layer (Option B).

The SQL canonical-tag arm in export_graph.sh is only ONE of the app's two tag arms.
This reuses the app's own association definition via
``EntityMentionRepository.association_triples``, so the tag channel:
  - includes the ALIAS-TAG arm (entity aliases Python-normalised via TagNormalizationService —
    the #207 "don't reimplement the normaliser in SQL" trap, which the pure-SQL export can't do);
  - honours Feature-091 manual exclusions (``entity_video_exclusions``), which the SQL export
    silently ignored.
So CO_OCCURS_TAGS becomes byte-for-byte the app's tag-association definition.

Read-only against PROD. Emits ``e1,e2,CO_OCCURS_TAGS,n`` rows (NO header) to stdout;
export_graph.sh appends them to cooccurs.csv alongside the SQL mention channels.

Env: CHRONO_REPO (repo path, for imports; default ~/PycharmProjects/chronovista).
Targets PROD via db_target (DEFAULT_URL = …:5435; refuses a dev DB unless --allow-dev).
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = Path(os.environ.get("CHRONO_REPO") or _HERE.parents[1])
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_HERE))  # db_target is vendored beside this script (self-contained in-repo)

import db_target  # noqa: E402  (prod-target guard, vendored into scripts/graph/)
from sqlalchemy import text  # noqa: E402

from chronovista.config.database import db_manager  # noqa: E402
from chronovista.repositories.entity_mention_repository import (  # noqa: E402
    EntityMentionRepository,
)

# association_triples is a BATCHED builder ("a page of entities"); feed it in chunks rather
# than all ~1,900 ids in one call.
_CHUNK = 200


async def _tag_pairs(session) -> set[tuple[str, str]]:
    """Global (entity_id, video_id) TAG link-set = canonical ∪ alias arms, exclusions subtracted."""
    ids = [
        row[0]
        for row in (
            await session.execute(
                text(
                    "SELECT id FROM named_entities "
                    "WHERE status = 'active' AND merged_into_id IS NULL"
                )
            )
        ).all()
    ]
    repo = EntityMentionRepository()
    pairs: set[tuple[str, str]] = set()
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i : i + _CHUNK]
        for entity_id, video_id, source in await repo.association_triples(session, chunk):
            if source == "tag":
                pairs.add((str(entity_id), video_id))
    return pairs


def _cooccurrence(pairs: set[tuple[str, str]], threshold: int):
    """Self-join the link-set on shared video → (e1<e2, shared_count) with count >= threshold."""
    video_entities: dict[str, set[str]] = defaultdict(set)
    for entity_id, video_id in pairs:
        video_entities[video_id].add(entity_id)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for ents in video_entities.values():
        for e1, e2 in combinations(sorted(ents), 2):  # sorted → e1 < e2, matches the SQL convention
            counts[(e1, e2)] += 1
    return ((e1, e2, n) for (e1, e2), n in counts.items() if n >= threshold)


async def _run(threshold: int, allow_dev: bool) -> int:
    # db_target.use() prints its target to stdout — redirect to stderr so stdout stays pure CSV.
    with contextlib.redirect_stdout(sys.stderr):
        db_target.use(allow_dev=allow_dev)
    async with db_manager.session(echo=False) as session:
        pairs = await _tag_pairs(session)
    for e1, e2, n in _cooccurrence(pairs, threshold):
        print(f"{e1},{e2},CO_OCCURS_TAGS,{n}")
    print(f"export_tag_edges: {len(pairs)} tag links → edges above (threshold {threshold})", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threshold", type=int, default=2)
    ap.add_argument("--allow-dev", action="store_true", help="permit a dev DB (default: refuse)")
    args = ap.parse_args()
    return asyncio.run(_run(args.threshold, args.allow_dev))


if __name__ == "__main__":
    raise SystemExit(main())
