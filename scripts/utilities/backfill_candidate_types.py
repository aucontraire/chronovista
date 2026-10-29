"""Re-type pending candidate suggestions from their own Wikidata ``instance_of`` (Feature 098).

Fixes #351 for the existing backlog: ``type_hint`` was derived from the relation that surfaced a
candidate (so e.g. a country reached via ``founder`` was typed ``person``). This recomputes it from
the candidate's own P31 via the shared classifier.

Safety (mirrors ``backfill_entity_relations.py``):
- **Default is dry-run** — reports the before→after type distribution and writes nothing.
- **Pending only** — decided candidates (approved/rejected/superseded) are historical, untouched.
- **``--apply`` requires ``--confirm-target <dbname>``** matching the effective database.
- **Reversible capture** — ``--apply`` writes a gitignored JSON of every changed row
  (id, qid, old→new) under ``backups/`` before committing.
- **Direction A / graceful** — the stored type is overridden only on positive, determinate
  evidence: a candidate with no usable P31 (QID unknown/absent) OR whose P31 classifies to the
  catch-all (OTHER) keeps its current type; a Wikidata outage aborts cleanly having written nothing.
- The DB session is NOT held across the Wikidata fetch (load → close → fetch → reopen to write).

Output is counts + QIDs only — no entity names (no library content).

Usage::

    python scripts/utilities/backfill_candidate_types.py                    # dry run
    DEVELOPMENT_MODE=false DATABASE_URL=postgresql+asyncpg://chronovista:chronovista@localhost:5435/chronovista \\
      python scripts/utilities/backfill_candidate_types.py --apply --confirm-target chronovista
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

from sqlalchemy import select, text, update  # noqa: E402

from chronovista.config.database import db_manager  # noqa: E402
from chronovista.db.models import CandidateSuggestion  # noqa: E402
from chronovista.services.wikidata_client import (  # noqa: E402
    WikidataClient,
    WikidataUnavailable,
)
from chronovista.services.wikidata_taxonomy import classify_entity_type  # noqa: E402

_PENDING = "pending"
_OTHER = "other"

# A change row: (candidate id, qid, old type_hint, new type_hint)
Change = tuple[uuid.UUID, str, str, str]


async def _load_pending() -> list[tuple[uuid.UUID, str, str]]:
    """Read (id, qid, type_hint) for every pending candidate, then release the session."""
    async with db_manager.session(echo=False) as session:
        result = await session.execute(
            select(
                CandidateSuggestion.id,
                CandidateSuggestion.wikidata_qid,
                CandidateSuggestion.type_hint,
            ).where(CandidateSuggestion.review_status == _PENDING)
        )
        rows = [(r[0], r[1], r[2]) for r in result.all()]
        await session.rollback()  # read-only; release without holding a txn
    return rows


async def _compute_changes(
    pending: list[tuple[uuid.UUID, str, str]],
) -> list[Change]:
    """Classify each candidate from its P31 (no DB session held across this network call).

    Direction A: override the stored type only on positive, determinate evidence. A candidate
    with no usable P31 (QID unknown/absent) OR whose P31 classifies to the catch-all (OTHER — an
    unrecognized class) keeps its current type, rather than being flooded into ``other``.
    """
    qids = sorted({qid for _, qid, _ in pending})
    p31_by_qid = await WikidataClient().fetch_instance_of(qids)
    changes: list[Change] = []
    for cid, qid, old in pending:
        p31 = p31_by_qid.get(qid)
        if not p31:  # unknown/absent → undeterminable → leave unchanged
            continue
        new = classify_entity_type(p31).value
        if (
            new != old and new != _OTHER
        ):  # Direction A: only override with a determinate type
            changes.append((cid, qid, old, new))
    return changes


def _report(pending: list[tuple[uuid.UUID, str, str]], changes: list[Change]) -> None:
    before: Counter[str] = Counter(t for _, _, t in pending)
    after: Counter[str] = Counter(before)
    for _, _, old, new in changes:
        after[old] -= 1
        after[new] += 1
    print(f"Pending candidates: {len(pending)}  |  would change: {len(changes)}\n")
    print(f"{'type':<16}{'before':>8}{'after':>8}{'delta':>8}")
    for t in sorted(set(before) | set(after)):
        b, a = before.get(t, 0), after.get(t, 0)
        print(f"{t:<16}{b:>8}{a:>8}{a - b:>+8}")


def _write_capture(changes: list[Change]) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = Path("backups") / f"candidate_type_backfill_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {"id": str(cid), "qid": qid, "old": old, "new": new}
                for cid, qid, old, new in changes
            ],
            indent=2,
        )
    )
    return path


async def _apply(changes: list[Change], confirm_target: str | None) -> int:
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
        capture = _write_capture(changes)
        for cid, _qid, old, new in changes:
            # Guard against a row decided (or re-typed) between load and apply: only write when
            # it is still pending AND still carries the captured pre-image type, so we never
            # overwrite a now-decided candidate and the reversible capture stays accurate.
            await session.execute(
                update(CandidateSuggestion)
                .where(
                    CandidateSuggestion.id == cid,
                    CandidateSuggestion.review_status == _PENDING,
                    CandidateSuggestion.type_hint == old,
                )
                .values(type_hint=new)
            )
        await session.commit()
    print(f"\nApplied {len(changes)} change(s). Reversible capture: {capture}")
    return 0


async def _run(apply: bool, confirm_target: str | None) -> int:
    pending = await _load_pending()
    try:
        changes = await _compute_changes(pending)
    except WikidataUnavailable:
        print("ABORTED: Wikidata is unavailable; nothing was written.", file=sys.stderr)
        return 3
    _report(pending, changes)
    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply --confirm-target <db>.")
        return 0
    if not changes:
        print("\nNothing to apply.")
        return 0
    return await _apply(changes, confirm_target)


def main() -> int:
    parser = argparse.ArgumentParser(prog="backfill_candidate_types")
    parser.add_argument(
        "--apply", action="store_true", help="Write changes (default: dry-run)"
    )
    parser.add_argument(
        "--confirm-target", default=None, help="Must match the effective db name"
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.apply, args.confirm_target))


if __name__ == "__main__":
    raise SystemExit(main())
