"""Sweep pending candidates seeded ONLY from categorically-untypeable relations.

The forward fix (``candidate_suggestion_service._UNTYPEABLE_SEED_RELATIONS``) stops *minting*
``award_received`` / ``position_held`` candidates — whose targets (awards, offices) have no
``EntityType`` slot and never will under the OntoNotes contract. But there is **no self-cleaning
path** for the ~3,000 already in the queue: ``supersede_grounded`` only fires when a candidate's QID
becomes a library entity, never when a candidate stops being emitted. So this script clears them.

Each swept row is marked ``REJECTED`` (terminal, never re-offered) with
``reviewed_by='policy:untypeable-relation'`` — because ``rejected`` has never been used before and
there is no reason/notes column, the policy marker is the only way to keep a machine bulk-clear
distinguishable from a human verdict (the project's "record which fallback ran" rule).

Criterion: ``review_status='pending'`` AND ``type_hint='other'`` AND ``provenance->'relations'`` is a
**non-empty subset** of the denylist — i.e. no typeable relation would still emit it under the
narrowed seed. A candidate carrying ``award_received`` *and* a typeable relation (e.g.
``participant_in``) is NOT swept: the narrowed seed still emits it.

Usage::

    python scripts/utilities/sweep_untypeable_candidates.py                      # dry run
    DEVELOPMENT_MODE=false DATABASE_URL=postgresql+asyncpg://chronovista:chronovista@localhost:5435/chronovista \\
      python scripts/utilities/sweep_untypeable_candidates.py --apply --confirm-target chronovista

Default is dry-run (reports the count + a sample of ids, writes nothing). ``--apply`` requires
``--confirm-target <dbname>`` matching the effective database and writes a reversible id capture to
``backups/`` before mutating.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import pathlib

from sqlalchemy import text

from chronovista.config.database import db_manager

# The categorically-untypeable relations this one-time sweep targets. Defined here (no longer
# imported from the service): Feature 105 made candidate seeding an explicit ``SEED_ALLOWLIST``
# and removed the denylist from the seeding path, so this historical sweep keeps its own copy.
_UNTYPEABLE_SEED_RELATIONS: frozenset[str] = frozenset(
    {"award_received", "position_held"}
)

POLICY_MARKER = "policy:untypeable-relation"
BACKUPS = pathlib.Path(__file__).resolve().parents[2] / "backups"


async def _candidates_to_sweep() -> list[str]:
    """Pending `other` candidates whose relations are a non-empty subset of the denylist."""
    async with db_manager.session(echo=False) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, provenance->'relations' AS relations "
                    "FROM candidate_suggestions "
                    "WHERE review_status = 'pending' AND type_hint = 'other' "
                    "AND provenance->'relations' IS NOT NULL"
                )
            )
        ).all()
        await session.rollback()  # read-only
    deny = set(_UNTYPEABLE_SEED_RELATIONS)
    ids: list[str] = []
    for row in rows:
        rels = set(row.relations or [])
        if rels and rels <= deny:
            ids.append(str(row.id))
    return ids


async def _apply(ids: list[str], confirm_target: str | None) -> int:
    async with db_manager.session(echo=False) as session:
        dbname = (await session.execute(text("SELECT current_database()"))).scalar_one()
        if confirm_target != dbname:
            await session.rollback()
            print(
                f"REFUSED: --apply requires --confirm-target {dbname!r} (got {confirm_target!r})."
            )
            return 1
        BACKUPS.mkdir(exist_ok=True)
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        capture = BACKUPS / f"sweep_untypeable_candidates_{stamp}.json"
        capture.write_text(
            json.dumps(
                {
                    "db": dbname,
                    "policy": POLICY_MARKER,
                    "prior_status": "pending",
                    "ids": ids,
                },
                indent=0,
            )
        )
        result = await session.execute(
            text(
                "UPDATE candidate_suggestions "
                "SET review_status = 'rejected', reviewed_by = :marker, reviewed_at = now() "
                "WHERE id = ANY(:ids) AND review_status = 'pending'"
            ),
            {"marker": POLICY_MARKER, "ids": ids},
        )
        await session.commit()
        print(
            f"swept {result.rowcount} rows → rejected (reviewed_by={POLICY_MARKER!r})"
        )
        print(f"reversible capture: {capture}")
    return 0


async def _run(apply: bool, confirm_target: str | None) -> int:
    ids = await _candidates_to_sweep()
    print(
        f"candidates to sweep (pending/other, relations ⊆ {sorted(_UNTYPEABLE_SEED_RELATIONS)}): {len(ids)}"
    )
    print("  sample ids:", ids[:5])
    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply --confirm-target <db>.")
        return 0
    if not ids:
        return 0
    return await _apply(ids, confirm_target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
