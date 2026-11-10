"""Load the reviewed channel-principal verdicts into the `channel_principals` table.

Reads the gitignored verdict corpus (``scripts/entity_resolution/channel_principals_verdicts.jsonl``)
and upserts one row per verdict (DESIGN-CHANNEL-PRINCIPALS):

- ``cast`` verdicts become live principal links (``decision='cast'``); the 3 former-cast
  carry a ``through`` date (current-vs-all-time, §8a).
- ``recurring_guest`` / ``credited_subject`` / ``stuffing`` verdicts are written as
  **tombstones** (``decision`` = the category, ``decided_at`` set) so a future detector
  re-run skips the pair instead of re-proposing it — the loader seeds *both* the cast and
  the "reviewed, not cast" rows.

Each row records its evidence (the detector counts) and the human decision; nothing here
materialises a per-video mention (§6 — a principal link never mints a mention).

**Dry-run by default.** ``--apply`` requires ``--confirm-target <dbname>`` to match
``SELECT current_database()`` — the guard that stops a write landing on the wrong DB
(the ``DEVELOPMENT_MODE`` DSN trap). Run against PROD only after the migration is applied
there; prod writes are the operator's to run.

Usage::

    # dry-run (no writes), against PROD:
    DEVELOPMENT_MODE=false \\
    DATABASE_URL=postgresql+asyncpg://chronovista:chronovista@localhost:5435/chronovista \\
    python scripts/utilities/load_channel_principals.py

    # apply:
    DEVELOPMENT_MODE=false DATABASE_URL=...:5435/chronovista \\
    python scripts/utilities/load_channel_principals.py --apply --confirm-target chronovista
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
import uuid
from collections import Counter
from pathlib import Path

from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chronovista.config.database import db_manager  # noqa: E402
from chronovista.db.models import Channel as ChannelDB  # noqa: E402
from chronovista.db.models import NamedEntity as NamedEntityDB  # noqa: E402
from chronovista.repositories.channel_principal_repository import (  # noqa: E402
    ChannelPrincipalRepository,
)

_DEFAULT_VERDICTS = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "entity_resolution"
    / "channel_principals_verdicts.jsonl"
)
_GENERATOR = (
    "spike-2026-11-10"  # fits channel_principals.derived_generator_version (30)
)


def _decided_at(rec: dict[str, object]) -> datetime.datetime:
    raw = rec.get("reviewed_at")
    if isinstance(raw, str) and raw:
        return datetime.datetime.fromisoformat(raw).replace(tzinfo=datetime.UTC)
    return datetime.datetime.now(datetime.UTC)


def _through(rec: dict[str, object]) -> datetime.date | None:
    raw = rec.get("through")
    return datetime.date.fromisoformat(raw) if isinstance(raw, str) and raw else None


async def load(verdicts_path: Path, apply: bool, confirm_target: str | None) -> int:
    records = [
        json.loads(line)
        for line in verdicts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    reviewed = [r for r in records if r.get("verdict")]
    skipped = len(records) - len(reviewed)

    by_decision = Counter(r["verdict"] for r in reviewed)
    cast = by_decision.get("cast", 0)
    former = sum(1 for r in reviewed if r["verdict"] == "cast" and r.get("through"))
    print(
        f"Verdict corpus: {len(records)} records, {len(reviewed)} reviewed "
        f"({skipped} without a verdict, skipped)."
    )
    print(f"  by decision: {dict(by_decision)}")
    print(
        f"  cast links: {cast} ({former} former, through-dated); "
        f"tombstones: {len(reviewed) - cast}"
    )

    repo = ChannelPrincipalRepository()
    async with db_manager.session(echo=False) as session:
        current_db = await session.scalar(text("SELECT current_database()"))
        print(f"  database: {current_db}")

        # A verdict loads only if its channel AND entity still exist (an entity may have
        # been merged or deleted since the review). Skip-and-report rather than FK-crash
        # the whole load.
        want_channels = {r["channel_id"] for r in reviewed}
        want_entities = {uuid.UUID(r["entity_id"]) for r in reviewed}
        have_channels = set(
            (
                await session.execute(
                    select(ChannelDB.channel_id).where(
                        ChannelDB.channel_id.in_(want_channels)
                    )
                )
            ).scalars()
        )
        have_entities = set(
            (
                await session.execute(
                    select(NamedEntityDB.id).where(NamedEntityDB.id.in_(want_entities))
                )
            ).scalars()
        )
        loadable = [
            r
            for r in reviewed
            if r["channel_id"] in have_channels
            and uuid.UUID(r["entity_id"]) in have_entities
        ]
        n_missing = len(reviewed) - len(loadable)
        if n_missing:
            print(
                f"  WARNING: {n_missing} verdict(s) reference a channel/entity absent "
                "from this DB — skipped (merged or deleted since review)."
            )

        if not apply:
            await session.rollback()
            print(
                f"\nDRY RUN — nothing written. {len(loadable)} loadable. Re-run with "
                f"--apply --confirm-target {current_db} to load."
            )
            return 0

        if confirm_target != current_db:
            await session.rollback()
            print(
                f"\nREFUSED: --confirm-target {confirm_target!r} != current_database() "
                f"{current_db!r}. No write performed.",
                file=sys.stderr,
            )
            return 2

        for r in loadable:
            ev = r.get("evidence", {})
            await repo.upsert_review(
                session,
                channel_id=r["channel_id"],
                entity_id=uuid.UUID(r["entity_id"]),
                decision=r["verdict"],
                decided_at=_decided_at(r),
                decided_reason=(r.get("note") or None),
                through=_through(r),
                generator_version=_GENERATOR,
                tag_credited_count=ev.get("tag_credited"),
                text_credited_count=ev.get("text_credited"),
                checkable_video_count=ev.get("checkable"),
                spoken_video_count=ev.get("spoken"),
            )
        await session.commit()
        print(
            f"\nAPPLIED — upserted {len(loadable)} rows into channel_principals on "
            f"{current_db} ({n_missing} skipped for missing refs)."
        )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="load_channel_principals")
    p.add_argument(
        "--verdicts",
        type=Path,
        default=_DEFAULT_VERDICTS,
        help="Path to the verdict JSONL (default: the gitignored corpus)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write the rows (default: dry-run). Requires --confirm-target.",
    )
    p.add_argument(
        "--confirm-target",
        type=str,
        default=None,
        help="Must equal SELECT current_database() for --apply to proceed.",
    )
    a = p.parse_args()
    if not a.verdicts.exists():
        print(f"Verdict file not found: {a.verdicts}", file=sys.stderr)
        return 2
    return asyncio.run(load(a.verdicts, a.apply, a.confirm_target))


if __name__ == "__main__":
    raise SystemExit(main())
