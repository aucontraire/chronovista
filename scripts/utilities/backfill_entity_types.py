"""Re-type grounded entities from their own stored Wikidata ``instance_of`` (Feature 099).

Completes the Feature 098 classifier work: extending ``INSTANCE_OF_BY_TYPE`` unmasks grounded
entities whose stored ``entity_type`` disagrees with their own P31 classification (e.g. an
intelligence agency stored as ``person``). This re-types them via the shared classifier.

**OFFLINE**: reads each entity's already-stored ``properties.instance_of.qids`` — no Wikidata calls,
so no session is ever held across a network round-trip.

Safety (mirrors ``backfill_candidate_types.py`` / ``backfill_entity_relations.py``):
- **Default is dry-run** — reports the actionable corrections + the undeterminable (OTHER) rate,
  and writes nothing. The dry run IS the review surface (FR-011).
- **Direction A** — overrides the stored type only on positive, determinate classification
  evidence; an entity classifying to OTHER (unrecognized/absent P31) keeps its stored type (FR-005).
- **``--apply`` requires ``--confirm-target <dbname>``** matching the effective database (FR-006).
- **Reversible capture** — ``--apply`` writes a gitignored JSON (id, old→new) under ``backups/``
  before committing (FR-006).
- **Writes ``entity_type`` (plus the automatic ``updated_at`` audit timestamp)** — no other data
  column; ``entity_subtype``, name, grounding, mentions and associations are untouched (FR-013).
- **Idempotent** — a compare-and-set on the captured pre-image means a second run changes nothing
  (FR-009 / SC-005).
- **Accurate reversal** — the capture records only the rows the compare-and-set actually matched
  (not the planned superset), written after a successful commit.
- **Reviewed subset** — the dry run IS the review; after it, the operator may apply only a vetted
  subset with ``--only <id,id,...>`` (e.g. to hold genuine dual-type entities whose stored type is
  defensible). Omit ``--only`` to apply every actionable correction.

Output is counts + ids + types only — no entity names (no library content).

Usage::

    python scripts/utilities/backfill_entity_types.py                    # dry run
    DEVELOPMENT_MODE=false DATABASE_URL=postgresql+asyncpg://chronovista:chronovista@localhost:5435/chronovista \\
      python scripts/utilities/backfill_entity_types.py --apply --confirm-target chronovista
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pydantic import BaseModel  # noqa: E402
from sqlalchemy import select, text, update  # noqa: E402

from chronovista.config.database import db_manager  # noqa: E402
from chronovista.db.models import NamedEntity  # noqa: E402
from chronovista.services.wikidata_taxonomy import (  # noqa: E402
    classify_if_determinate,
)

_MERGED = "merged"


class EntityTypeCorrection(BaseModel):
    """One actionable retype: the entity, its current stored type, and its classified type."""

    entity_id: uuid.UUID
    old_type: str
    new_type: str


def _qids(properties: object) -> list[str]:
    """Extract stored P31 QIDs from ``properties.instance_of.qids`` defensively."""
    if not isinstance(properties, dict):
        return []
    instance_of = properties.get("instance_of")
    if not isinstance(instance_of, dict):
        return []
    qids = instance_of.get("qids")
    if not isinstance(qids, list):
        return []
    return [q for q in qids if isinstance(q, str)]


async def _load() -> list[tuple[uuid.UUID, str, list[str]]]:
    """Read (id, entity_type, stored P31 qids) for every non-merged entity that carries a stored
    classification, then release the session (read-only)."""
    async with db_manager.session(echo=False) as session:
        result = await session.execute(
            select(
                NamedEntity.id, NamedEntity.entity_type, NamedEntity.properties
            ).where(NamedEntity.status != _MERGED)
        )
        rows: list[tuple[uuid.UUID, str, list[str]]] = []
        for eid, etype, props in result.all():
            qids = _qids(props)
            if qids:
                rows.append((eid, etype, qids))
        await session.rollback()  # read-only; release without holding a txn
    return rows


def _compute_changes(
    rows: list[tuple[uuid.UUID, str, list[str]]],
) -> list[EntityTypeCorrection]:
    """Actionable mismatch = classification is determinate (not OTHER) AND differs from stored.
    Direction A: an OTHER classification never overrides the stored type."""
    changes: list[EntityTypeCorrection] = []
    for eid, old, qids in rows:
        classified = classify_if_determinate(qids)
        if classified is not None and classified.value != old:
            changes.append(
                EntityTypeCorrection(
                    entity_id=eid, old_type=old, new_type=classified.value
                )
            )
    return changes


def _report(
    rows: list[tuple[uuid.UUID, str, list[str]]],
    changes: list[EntityTypeCorrection],
) -> None:
    other = sum(1 for _, _, qids in rows if classify_if_determinate(qids) is None)
    pct = (other / len(rows) * 100) if rows else 0.0
    print(f"Grounded entities with stored instance_of: {len(rows)}")
    print(f"  undeterminable (OTHER, kept): {other} ({pct:.1f}%)")
    print(f"  actionable corrections: {len(changes)}\n")
    pairs: Counter[tuple[str, str]] = Counter((c.old_type, c.new_type) for c in changes)
    for (old, new), n in sorted(pairs.items(), key=lambda kv: -kv[1]):
        print(f"  {old} -> {new}: {n}")
    if changes:
        print()
    for c in changes:
        print(f"  {c.entity_id}  {c.old_type} -> {c.new_type}")


def _write_capture(changes: list[EntityTypeCorrection]) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = Path("backups") / f"entity_type_backfill_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.model_dump(mode="json") for c in changes], indent=2))
    return path


async def _apply(
    changes: list[EntityTypeCorrection], confirm_target: str | None
) -> int:
    async with db_manager.session(echo=False) as session:
        dbname = (await session.execute(text("SELECT current_database()"))).scalar_one()
        if confirm_target != dbname:
            await session.rollback()
            print(
                f"REFUSED: --apply requires --confirm-target {dbname!r} "
                f"(got {confirm_target!r}).",
                file=sys.stderr,
            )
            return 2
        applied: list[EntityTypeCorrection] = []
        for c in changes:
            # Compare-and-set on the captured pre-image: write only when the row is still
            # non-merged and still carries `old_type`, so a row changed between load and apply is
            # never clobbered and re-runs are no-ops. rowcount tells us which rows actually matched
            # so the capture records what was applied, not the planned superset.
            result = await session.execute(
                update(NamedEntity)
                .where(
                    NamedEntity.id == c.entity_id,
                    NamedEntity.status != _MERGED,
                    NamedEntity.entity_type == c.old_type,
                )
                .values(entity_type=c.new_type)
            )
            if result.rowcount:
                applied.append(c)
        await session.commit()
    # Capture only the rows that actually changed, after the commit — an accurate reversal source.
    capture = _write_capture(applied)
    skipped = len(changes) - len(applied)
    tail = f", skipped {skipped} (changed since load)" if skipped else ""
    print(f"\nApplied {len(applied)} change(s){tail}. Reversible capture: {capture}")
    return 0


async def _run(
    apply: bool, confirm_target: str | None, only: set[str] | None = None
) -> int:
    rows = await _load()
    if not rows:
        print("No grounded entities with a stored instance_of classification.")
        return 0
    changes = _compute_changes(rows)
    _report(rows, changes)
    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply --confirm-target <db>.")
        return 0
    # The dry run above IS the review. When the operator has reviewed it and wants to apply only a
    # vetted subset (e.g. clear corrections, holding genuine dual-type cases), they pass --only with
    # those entity ids; otherwise every actionable correction is applied.
    if only is not None:
        unknown = only - {str(c.entity_id) for c in changes}
        if unknown:
            print(
                f"\nREFUSED: --only ids are not actionable corrections: {sorted(unknown)}",
                file=sys.stderr,
            )
            return 2
        changes = [c for c in changes if str(c.entity_id) in only]
        print(f"\n--only: applying {len(changes)} reviewed correction(s).")
    if not changes:
        print("\nNothing to apply.")
        return 0
    return await _apply(changes, confirm_target)


def main() -> int:
    parser = argparse.ArgumentParser(prog="backfill_entity_types")
    parser.add_argument(
        "--apply", action="store_true", help="Write changes (default: dry-run)"
    )
    parser.add_argument(
        "--confirm-target", default=None, help="Must match the effective db name"
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Comma-separated entity ids to apply (a reviewed subset); omit to apply all",
    )
    args = parser.parse_args()
    only = (
        {s.strip() for s in args.only.split(",") if s.strip()}
        if args.only is not None
        else None
    )
    return asyncio.run(_run(args.apply, args.confirm_target, only))


if __name__ == "__main__":
    raise SystemExit(main())
