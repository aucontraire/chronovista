#!/usr/bin/env python3
"""Backfill entity categories from ``named_entities.properties`` into the normalized tables.

Feature 083. Reads the existing per-entity ``properties->'category'`` block
(``{"values": [...], "source": ..., "set_at": ...}``) and writes it into
``wikipedia_categories`` (one row per distinct category, with its global size) and
``entity_categories`` (the assignment). Then fetches each distinct category's Wikipedia-wide
``global_size`` and stores it.

Safety (the whole point of a one-off prod write):
- **Default is dry-run.** Writes happen only with ``--apply``.
- **Non-destructive** — never writes ``properties``; existing readers are untouched (FR-008).
- **Target confirmation** — ``--apply`` requires ``--confirm-target <dbname>`` matching
  ``current_database()``, so a write cannot land on the wrong database by mistake (FR-010).
- **Row capture** — before committing, an ``--apply`` run writes a JSON capture of exactly the
  rows it inserted, sufficient to reverse the operation (FR-009). The capture contains category
  names (library content), so it is written to a gitignored path and never committed.
- **Idempotent** — upserts/adds use ON CONFLICT DO NOTHING; a re-run creates no duplicates (FR-012).
- **Graceful** — a category whose global size cannot be fetched is left NULL and can be filled on a
  later run (FR-006 / Principle VIII).

This script is name-free: category/entity names are runtime data, never embedded in source.

Usage:
  python scripts/utilities/backfill_category_tables.py            # dry-run (default)
  python scripts/utilities/backfill_category_tables.py --no-fetch # dry-run, skip size fetch
  python scripts/utilities/backfill_category_tables.py --apply --confirm-target chronovista
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
import uuid
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from rich.console import Console  # noqa: E402
from sqlalchemy import text  # noqa: E402

from chronovista.config.database import db_manager  # noqa: E402
from chronovista.repositories.entity_category_repository import (  # noqa: E402
    EntityCategoryRepository,
)
from chronovista.repositories.wikipedia_category_repository import (  # noqa: E402
    WikipediaCategoryRepository,
)
from chronovista.services.category_size import CategorySizeService  # noqa: E402

console = Console()

# Capture lands here; scripts/entity_resolution/ is gitignored, so a file of real category
# names never reaches version control.
_CAPTURE_DIR = _PROJECT_ROOT / "scripts" / "entity_resolution"


def extract_assignments(
    properties: dict[str, Any],
) -> list[tuple[str, str, datetime.datetime | None]]:
    """Return ``(category_name, source, set_at)`` for each category in one entity's bag.

    Pure and name-agnostic. A missing/empty/malformed ``category`` block yields ``[]`` (the
    caller skips and reports it) — this is the malformed-block edge case.
    """
    block = properties.get("category")
    if not isinstance(block, dict):
        return []
    values = block.get("values")
    if not isinstance(values, list):
        return []
    source = block.get("source")
    source_str = source if isinstance(source, str) and source else "unknown"
    set_at_raw = block.get("set_at")
    set_at: datetime.datetime | None = None
    if isinstance(set_at_raw, str):
        try:
            set_at = datetime.datetime.fromisoformat(set_at_raw)
        except ValueError:
            set_at = None
    return [
        (name, source_str, set_at) for name in values if isinstance(name, str) and name
    ]


async def _load_rows(session: Any) -> list[tuple[uuid.UUID, dict[str, Any]]]:
    """Load (entity_id, properties) for every entity carrying a category block."""
    result = await session.execute(
        text("SELECT id, properties FROM named_entities WHERE properties ? 'category'")
    )
    return [(row.id, row.properties or {}) for row in result.fetchall()]


async def run_backfill(apply: bool, confirm_target: str | None, fetch: bool) -> int:
    repo_cat = WikipediaCategoryRepository()
    repo_assign = EntityCategoryRepository()
    size_service = CategorySizeService()

    async with db_manager.session(echo=False) as session:
        dbname = (await session.execute(text("SELECT current_database()"))).scalar_one()
        console.print(f"Effective database: {dbname}")

        if apply:
            if confirm_target != dbname:
                console.print(
                    f"REFUSED: --apply requires --confirm-target {dbname!r} "
                    f"(got {confirm_target!r}). No changes made."
                )
                return 2

        rows = await _load_rows(session)
        assignments: list[tuple[uuid.UUID, str, str, datetime.datetime | None]] = []
        skipped = 0
        for entity_id, props in rows:
            parsed = extract_assignments(props)
            if not parsed:
                skipped += 1
                continue
            for name, source, set_at in parsed:
                assignments.append((entity_id, name, source, set_at))

        distinct_categories = sorted({a[1] for a in assignments})
        console.print(
            f"Entities with a category block: {len(rows):,} "
            f"(skipped malformed/empty: {skipped:,})"
        )
        console.print(f"Assignments to insert: {len(assignments):,}")
        console.print(f"Distinct categories: {len(distinct_categories):,}")

        if not apply:
            console.print(
                "\nDRY RUN — no changes made. Re-run with --apply --confirm-target "
                f"{dbname} to write."
            )
            return 0

        # --- apply path ---
        name_to_id: dict[str, uuid.UUID] = {}
        for name in distinct_categories:
            cat = await repo_cat.upsert(session, name)
            name_to_id[name] = cat.id
        for entity_id, name, source, set_at in assignments:
            await repo_assign.add(session, entity_id, name_to_id[name], source, set_at)

        sizes: dict[str, int] = {}
        if fetch:
            # Incremental: fetch only categories still missing a global_size, so a re-run after a
            # rate-limited pass resumes cheaply instead of re-querying every category.
            to_fetch = await repo_cat.names_without_global_size(
                session, distinct_categories
            )
            console.print(
                f"Categories needing a global-size fetch: {len(to_fetch):,} "
                f"(of {len(distinct_categories):,} distinct)"
            )
            sizes = await size_service.sizes_for(to_fetch)
            fetched_at = datetime.datetime.now(datetime.UTC)
            for name, size in sizes.items():
                await repo_cat.set_global_size(
                    session, name_to_id[name], size, fetched_at
                )

        _CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        capture_path = _CAPTURE_DIR / f"category_backfill_capture_{stamp}.json"
        capture_path.write_text(
            json.dumps(
                {
                    "database": dbname,
                    "created_at": datetime.datetime.now().isoformat(),
                    "categories_inserted": [
                        {"id": str(cid), "name": name}
                        for name, cid in name_to_id.items()
                    ],
                    "assignments_inserted": [
                        {"entity_id": str(eid), "category_id": str(name_to_id[name])}
                        for eid, name, _src, _sa in assignments
                    ],
                    "global_sizes_set": sizes,
                },
                indent=2,
            )
        )
        console.print(f"Capture written (gitignored): {capture_path}")

        await session.commit()
        console.print(
            f"APPLIED: {len(name_to_id):,} categories, {len(assignments):,} assignments, "
            f"{len(sizes):,} global sizes."
        )
        return 0

    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backfill_category_tables",
        description="Backfill entity categories from JSONB into the normalized tables (Feature 083).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Perform writes. Without this flag the script is a read-only dry run (default).",
    )
    parser.add_argument(
        "--confirm-target",
        metavar="DBNAME",
        default=None,
        help="Required with --apply: must equal the effective current_database().",
    )
    parser.add_argument(
        "--no-fetch",
        dest="fetch",
        action="store_false",
        default=True,
        help="Skip the Wikipedia global-size fetch (categories get NULL size, fill later).",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    exit_code = asyncio.run(
        run_backfill(
            apply=args.apply, confirm_target=args.confirm_target, fetch=args.fetch
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
