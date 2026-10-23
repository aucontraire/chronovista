"""Advisory, READ-ONLY: per ``instance_of`` type, which curated property fields are populated (088).

Grounding spike for Feature 088 (SC-006) — it does NOT gate the feature. It reads only our own stored
``named_entities.properties`` (no Wikidata calls, no writes) and reports, for each ``instance_of`` type
label present among grounded entities, how many of those entities populate each curated field and at
what rate. This informs LATER tuning (which fine-grained filter types to collapse; which credit kinds
matter for which types) and the deferred ontology/type-model decision (ADR-010 D3 promote-on-query).

Output is type labels + field names + counts only — no entity names. Usage::

    python scripts/utilities/measure_type_field_prevalence.py            # all grounded entities
    python scripts/utilities/measure_type_field_prevalence.py --top 15   # limit the type rows shown
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chronovista.config.database import db_manager  # noqa: E402
from chronovista.repositories.named_entity_repository import (  # noqa: E402
    NamedEntityRepository,
)
from chronovista.services.wikidata_properties import WANTED  # noqa: E402

# The relational/credit fields most worth measuring (curated item-valued relations), newest first.
_FIELDS = tuple(dict.fromkeys(WANTED.values()))


def _types(props: dict[str, Any]) -> list[str]:
    block = props.get("instance_of")
    values = block.get("values") if isinstance(block, dict) else None
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(v for v in values if isinstance(v, str)))


def _populated(props: dict[str, Any], field: str) -> bool:
    block = props.get(field)
    return isinstance(block, dict) and bool(block.get("qids") or block.get("values"))


async def measure(top: int) -> int:
    repo = NamedEntityRepository()
    async with db_manager.session(echo=False) as session:
        grounded = await repo.list_wikidata_grounded(session)
        snapshot = [dict(e.properties or {}) for e in grounded]
        await session.rollback()

    type_counts: Counter[str] = Counter()
    # type -> field -> populated count
    field_counts: dict[str, Counter[str]] = defaultdict(Counter)
    untyped = 0
    for props in snapshot:
        types = _types(props)
        if not types:
            untyped += 1
            continue
        for t in types:
            type_counts[t] += 1
            for f in _FIELDS:
                if _populated(props, f):
                    field_counts[t][f] += 1

    print(f"Grounded entities scanned: {len(snapshot)}  (untyped: {untyped})")
    print(f"Distinct instance_of types: {len(type_counts)}\n")
    for t, n in type_counts.most_common(top):
        present = [
            f"{f} {field_counts[t][f]}/{n} ({field_counts[t][f] * 100 // n}%)"
            for f in _FIELDS
            if field_counts[t][f]
        ]
        print(f"[{t}] — {n} entities")
        print(
            "  "
            + (
                ", ".join(present)
                if present
                else "(no curated relation fields populated)"
            )
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="measure_type_field_prevalence")
    parser.add_argument("--top", type=int, default=25, help="Max type rows to show")
    args = parser.parse_args()
    return asyncio.run(measure(args.top))


if __name__ == "__main__":
    raise SystemExit(main())
