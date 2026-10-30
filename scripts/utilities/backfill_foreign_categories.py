#!/usr/bin/env python3
"""Backfill English categories for foreign-only grounded entities via cross-walk (Feature 100).

The sibling of ``backfill_entity_categories.py``. That one recovers categories for entities with an
**English** Wikipedia article; this one recovers them for grounded entities that have **no English
article** but do have one or more foreign-language articles, by cross-walking each foreign category
to its English equivalent (``category → its Wikidata item → enwiki sitelink``) and storing the
English names in the same ``wikipedia`` namespace. It never re-implements the cross-walk — it drives
the shared per-entity primitive ``services.category_coverage.resolve_and_crosswalk_entity`` in bulk
(the same primitive the on-approval enrichment seam uses).

Architecture (mirrors the English backfill):
- **All network outside any write transaction** (Phase A): for each eligible entity, resolve its
  foreign articles and cross-walk their categories (no DB session held — the 094 deadlock lesson),
  then bulk-fetch the resulting English categories' global sizes.
- **One network-free write transaction** (Phase B): add the cross-walked assignments (add-only,
  ON CONFLICT DO NOTHING), write the reversible capture, then commit once.

Eligibility: ``status='active'`` AND a Wikidata QID AND **no** stored DBpedia IRI (a DBpedia IRI
implies an English article — out of scope, FR-001) AND currently zero categories. ``resolve_and_
crosswalk_entity`` additionally skips any entity whose QID turns out to have an English sitelink.

Safety (a one-off prod write):
- **Default is dry-run.** Writes happen only with ``--apply`` (FR-009).
- **Target confirmation** — ``--apply`` requires ``--confirm-target <dbname>`` matching
  ``current_database()`` (FR-010).
- **Reversible capture** — an ``--apply`` run writes a JSON capture of the assignments it inserted
  (with the originating language per category, FR-010) to a gitignored path, before committing.
- **Idempotent / add-only** — a re-run creates no duplicates and re-processes only what is still
  missing (FR-015).
- **Graceful** — an entity that cannot be resolved or cross-walked is skipped and reported; the run
  never aborts on one entity (FR-014).

Name-free: article titles and category names are runtime data, never embedded in source.

Usage:
  DEVELOPMENT_MODE=false DATABASE_URL=<prod dsn> \
    python scripts/utilities/backfill_foreign_categories.py                      # dry-run (default)
  DEVELOPMENT_MODE=false DATABASE_URL=<prod dsn> \
    python scripts/utilities/backfill_foreign_categories.py --apply --confirm-target chronovista
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
import uuid
from pathlib import Path

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
from chronovista.services.category_coverage import (  # noqa: E402
    WIKIPEDIA_SOURCE,
    EntityCrosswalkResult,
    FetchServiceFactory,
    default_fetch_factory,
    resolve_and_crosswalk_entity,
    store_categories_for_entity,
)
from chronovista.services.category_size import CategorySizeService  # noqa: E402
from chronovista.services.wikidata_client import (  # noqa: E402
    WikidataClient,
    WikidataUnavailable,
)

console = Console()

# Capture lands here; scripts/entity_resolution/ is gitignored, so a file of real category names
# never reaches version control.
_CAPTURE_DIR = _PROJECT_ROOT / "scripts" / "entity_resolution"

# Polite gap (seconds) between entities — each entity hits several Wikipedia/Wikidata endpoints, so
# pace the loop in addition to the per-request batching inside the fetch service (FR-016).
_INTER_ENTITY_PAUSE = 0.5

_ELIGIBLE_SQL = text(
    """
    SELECT ne.id AS id, ne.external_ids -> 'wikidata' ->> 'id' AS qid
    FROM named_entities ne
    WHERE ne.status = 'active'
      AND (ne.external_ids -> 'wikidata' ->> 'id') IS NOT NULL
      -- No *usable* DBpedia IRI (a real IRI implies an English article — out of scope, FR-001).
      -- Keys off id truthiness, not key presence, to match the enrichment hook's has_dbpedia_iri
      -- guard exactly (a vestigial {"dbpedia": {"id": null}} block is still eligible).
      AND (ne.external_ids #>> '{dbpedia,id}') IS NULL
      AND NOT EXISTS (
        SELECT 1 FROM entity_categories ec WHERE ec.entity_id = ne.id
      )
    ORDER BY ne.id
    """
)


class _Plan:
    """The in-memory plan built in Phase A (network) and written in Phase B (no network)."""

    def __init__(self) -> None:
        # (entity_id, english category names, {english name: [source langs]})
        self.to_write: list[tuple[uuid.UUID, list[str], dict[str, list[str]]]] = []
        self.sizes: dict[str, int] = {}
        self.eligible = 0
        self.no_foreign_article = 0  # None result: has enwiki, or no foreign article
        self.recovered_zero = 0  # foreign article(s) but nothing cross-walked
        self.dropped_categories = 0  # foreign categories with no English equivalent
        self.errors = 0  # entities skipped on an unexpected error (FR-014)


async def build_plan(
    *,
    wikidata_client: WikidataClient,
    size_service: CategorySizeService,
    fetch_factory: FetchServiceFactory = default_fetch_factory,
) -> _Plan:
    """Phase A — all network, no write transaction. Classify, resolve, cross-walk, size."""
    plan = _Plan()

    async with db_manager.session(echo=False) as session:
        rows = (await session.execute(_ELIGIBLE_SQL)).all()
        await session.rollback()  # read-only
    eligible = [(uuid.UUID(str(r.id)), str(r.qid)) for r in rows]
    plan.eligible = len(eligible)
    console.print(f"Eligible foreign-only, zero-category entities: {plan.eligible:,}")

    new_category_names: set[str] = set()
    for index, (entity_id, qid) in enumerate(eligible):
        if index > 0 and _INTER_ENTITY_PAUSE > 0:
            await asyncio.sleep(_INTER_ENTITY_PAUSE)
        try:
            result: EntityCrosswalkResult | None = await resolve_and_crosswalk_entity(
                qid,
                wikidata_client=wikidata_client,
                fetch_factory=fetch_factory,
            )
        except WikidataUnavailable:
            plan.errors += 1
            continue
        except (
            Exception
        ):  # noqa: BLE001 — never abort the bulk run on one entity (FR-014)
            # A per-entity failure is tallied in `plan.errors` and reported. A HIGH errors count
            # is a signal to INVESTIGATE (a systematic code/shape bug), not merely "retry later".
            plan.errors += 1
            continue
        if result is None:
            plan.no_foreign_article += 1
            continue
        plan.dropped_categories += result.dropped_count
        if not result.english_categories:
            plan.recovered_zero += 1
            continue
        plan.to_write.append(
            (entity_id, result.english_categories, result.source_langs_by_category)
        )
        new_category_names.update(result.english_categories)
        if (len(plan.to_write)) % 10 == 0:
            console.print(f"  …{len(plan.to_write):,} entities cross-walked so far")

    if new_category_names:
        console.print(
            f"Fetching global sizes for {len(new_category_names):,} distinct new categories…"
        )
        plan.sizes = await size_service.sizes_for(sorted(new_category_names))
    console.print("Planning complete.")
    return plan


def _report(plan: _Plan) -> None:
    console.print(f"Eligible entities: {plan.eligible:,}")
    console.print(f"  will receive cross-walked categories: {len(plan.to_write):,}")
    console.print(
        f"  no foreign article / has English article (skipped): {plan.no_foreign_article:,}"
    )
    console.print(
        f"  foreign article but nothing cross-walked (recovered zero): {plan.recovered_zero:,}"
    )
    console.print(
        f"  foreign categories dropped (no English equivalent): {plan.dropped_categories:,}"
    )
    console.print(f"  skipped on error (retry later): {plan.errors:,}")
    console.print(f"  distinct new category sizes fetched: {len(plan.sizes):,}")


async def _apply(
    plan: _Plan,
    dbname: str,
    *,
    cat_repo: WikipediaCategoryRepository,
    assign_repo: EntityCategoryRepository,
) -> None:
    """Phase B — one network-free write transaction; capture written before the single commit."""
    if not plan.to_write:
        console.print("Nothing to write — no capture file created.")
        return
    async with db_manager.session(echo=False) as session:
        for entity_id, names, _langs in plan.to_write:
            await store_categories_for_entity(
                session,
                entity_id,
                names,
                cat_repo=cat_repo,
                assign_repo=assign_repo,
                sizes=plan.sizes,
                replace=False,
                source=WIKIPEDIA_SOURCE,
            )

        _CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        capture_path = _CAPTURE_DIR / f"foreign_category_crosswalk_capture_{stamp}.json"
        capture_path.write_text(
            json.dumps(
                {
                    "database": dbname,
                    "created_at": datetime.datetime.now().isoformat(),
                    # Reversal = delete these (entity, category) assignments; orphaned category rows
                    # are harmless. Add-only run, so there is no before/after set to restore.
                    "assignments_inserted": [
                        {
                            "entity_id": str(entity_id),
                            "categories": names,
                            "source_langs": langs,
                        }
                        for entity_id, names, langs in plan.to_write
                    ],
                },
                indent=2,
            )
        )
        console.print(f"Capture written (gitignored): {capture_path}")
        await session.commit()

    console.print(
        f"APPLIED: cross-walked categories for {len(plan.to_write):,} entities."
    )


async def run_backfill(apply: bool, confirm_target: str | None) -> int:
    cat_repo = WikipediaCategoryRepository()
    assign_repo = EntityCategoryRepository()
    size_service = CategorySizeService()
    wikidata_client = WikidataClient()

    async with db_manager.session(echo=False) as session:
        dbname = (await session.execute(text("SELECT current_database()"))).scalar_one()
        await session.rollback()
    console.print(f"Effective database: {dbname}")

    if apply and confirm_target != dbname:
        console.print(
            f"REFUSED: --apply requires --confirm-target {dbname!r} "
            f"(got {confirm_target!r}). No changes made."
        )
        return 2

    plan = await build_plan(wikidata_client=wikidata_client, size_service=size_service)
    _report(plan)

    if not apply:
        console.print(
            "\nDRY RUN — no changes made. Re-run with --apply --confirm-target "
            f"{dbname} to write."
        )
        return 0

    await _apply(plan, dbname, cat_repo=cat_repo, assign_repo=assign_repo)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backfill_foreign_categories",
        description="Cross-walk foreign-language categories to English for foreign-only grounded entities (Feature 100).",
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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    exit_code = asyncio.run(
        run_backfill(apply=args.apply, confirm_target=args.confirm_target)
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
