#!/usr/bin/env python3
"""Backfill entity→Wikipedia categories into the Feature 083 tables (Feature 084).

Brings category coverage from the ~373 already categorized to all grounded entities by fetching
each entity's categories from **live Wikipedia** (``prop=categories&clshow=!hidden``) and writing
them as ``source = "wikipedia"`` assignments. This script is one of the two orchestrations of the
shared ``services.category_coverage`` logic (the other is the on-approval enrichment seam) — it
never re-implements the resolve/fetch/store pipeline, only drives it in bulk.

Architecture (why it is shaped this way):
- **All network happens outside any write transaction** (Phase A): resolve each entity's article
  title, bulk-fetch categories (batched ≤50/request, paced), and bulk-fetch the new categories'
  global sizes. This avoids holding a database transaction open across minutes of Wikipedia calls.
- **One network-free write transaction** (Phase B): upsert categories, write assignments, set the
  pre-fetched sizes, write the reversible capture, then commit once (capture-before-commit, so a
  failure writes nothing — mirrors Feature 083's ``backfill_category_tables.py``).

Two cohorts: the **add** path for grounded entities that currently have *no* categories (the
~1,441), and the **replace** path for entities already on a foreign source (the existing ~373 on
DBpedia) — their DBpedia categories are removed and the Wikipedia namespace written (delete-then-add)
so the whole corpus is one uniform namespace (FR-005/FR-007). The replace is measured: the run
reports an aggregate diff (added / removed / unchanged) and the capture records each entity's
before/after plus the removed rows, so it is auditable and fully reversible (FR-009/FR-013/SC-007).
A replace whose fetch comes back empty or failed is left untouched (its DBpedia categories kept,
retried later) — a replace never deletes an entity's categories down to nothing.

Safety (the point of a one-off prod write):
- **Default is dry-run.** Writes happen only with ``--apply`` (FR-009).
- **Target confirmation** — ``--apply`` requires ``--confirm-target <dbname>`` matching
  ``current_database()`` (FR-010).
- **Reversible capture** — an ``--apply`` run writes a JSON capture of the assignments it inserted,
  to a gitignored path (category names are library content), before committing (FR-009).
- **Idempotent / resumable** — ``add`` is ON CONFLICT DO NOTHING and already-categorized entities
  are skipped, so a re-run after a rate-limited pass creates no duplicates and re-processes only
  what is still missing (FR-008).
- **Graceful** — a title that cannot be resolved, or whose fetch fails, is skipped and reported;
  the run never aborts on one entity (FR-014 / Principle VIII).

Name-free: article titles and category names are runtime data, never embedded in source.

Usage:
  python scripts/utilities/backfill_entity_categories.py                      # dry-run (default)
  python scripts/utilities/backfill_entity_categories.py --apply --confirm-target chronovista
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
from chronovista.repositories.named_entity_repository import (  # noqa: E402
    NamedEntityRepository,
)
from chronovista.repositories.wikipedia_category_repository import (  # noqa: E402
    WikipediaCategoryRepository,
)
from chronovista.services.category_coverage import (  # noqa: E402
    WIKIPEDIA_SOURCE,
    resolve_article_title,
    store_categories_for_entity,
)
from chronovista.services.category_size import CategorySizeService  # noqa: E402
from chronovista.services.dbpedia_resolver import DbpediaResolver  # noqa: E402
from chronovista.services.entity_category_fetch import (  # noqa: E402
    EntityCategoryFetchService,
)

console = Console()

# Capture lands here; scripts/entity_resolution/ is gitignored, so a file of real category
# names never reaches version control.
_CAPTURE_DIR = _PROJECT_ROOT / "scripts" / "entity_resolution"


def qid_of(external_ids: dict[str, Any]) -> str | None:
    """Extract the Wikidata QID from an entity's ``external_ids`` bag, or ``None``."""
    wikidata = external_ids.get("wikidata") if isinstance(external_ids, dict) else None
    qid = wikidata.get("id") if isinstance(wikidata, dict) else None
    return qid if isinstance(qid, str) and qid else None


async def sources_by_entity(session: Any) -> dict[uuid.UUID, set[str]]:
    """Return ``{entity_id: {assignment sources}}`` for every entity that has any category.

    One read used to classify entities: no categories → *add*; already on the Wikipedia source →
    *skip (done)*; on a foreign source (the DBpedia 373) → *skip (defer to the replace path)*.
    """
    result = await session.execute(
        text("SELECT entity_id, source FROM entity_categories")
    )
    out: dict[uuid.UUID, set[str]] = {}
    for row in result.fetchall():
        out.setdefault(row.entity_id, set()).add(row.source)
    return out


async def old_categories_by_entity(session: Any) -> dict[uuid.UUID, list[str]]:
    """Return ``{entity_id: [current category names]}`` for the diff + capture of the 373 replace."""
    result = await session.execute(
        text(
            "SELECT ec.entity_id AS entity_id, wc.name AS name "
            "FROM entity_categories ec "
            "JOIN wikipedia_categories wc ON wc.id = ec.category_id"
        )
    )
    out: dict[uuid.UUID, list[str]] = {}
    for row in result.fetchall():
        out.setdefault(row.entity_id, []).append(row.name)
    return out


def _norm(name: str) -> str:
    """Normalize a category name for diffing (``_``/blanks and case fold together)."""
    return name.replace("_", " ").strip().lower()


class _Plan:
    """The in-memory plan built in Phase A (network) and written in Phase B (no network)."""

    def __init__(self) -> None:
        self.to_add: list[tuple[uuid.UUID, str, list[str]]] = (
            []
        )  # (entity, title, new names) — the 1,441 with no categories
        # (entity, title, new names, old names) — the 373 DBpedia→Wikipedia rewrite
        self.to_replace: list[tuple[uuid.UUID, str, list[str], list[str]]] = []
        self.sizes: dict[str, int] = {}
        self.skipped_done = 0  # already on the Wikipedia source
        self.unresolvable = 0  # no resolvable article (SC-006)
        self.fetch_omitted = 0  # fetch failed/missing — retry on a later run
        self.zero_categories = 0  # article exists but has no non-hidden categories
        # Replace cohort that is left untouched this run (never replace-to-empty / never on a
        # failed fetch — the DBpedia categories are kept and retried later).
        self.replace_skipped_empty = (
            0  # fetch omitted or zero → keep DBpedia, retry later
        )
        # Aggregate diff across the 373 rewrite (FR-013), by normalized category name.
        self.diff_added = 0
        self.diff_removed = 0
        self.diff_unchanged = 0


async def build_plan(
    *,
    entity_repo: NamedEntityRepository,
    resolver: DbpediaResolver,
    fetch_service: EntityCategoryFetchService,
    size_service: CategorySizeService,
) -> _Plan:
    """Phase A — all network, no write transaction. Classify, resolve titles, fetch, size."""
    plan = _Plan()

    async with db_manager.session(echo=False) as session:
        # Extract plain (id, external_ids) WHILE the session is open: the ORM instances detach
        # when the context closes, and reading an attribute off a detached instance raises
        # DetachedInstanceError. The classify loop below runs after the block (so no transaction
        # is held open across the network work), so it must see plain data, not ORM rows.
        grounded = [
            (row.id, dict(row.external_ids or {}))
            for row in await entity_repo.list_wikidata_grounded(session)
        ]
        existing = await sources_by_entity(session)
        old_categories = await old_categories_by_entity(session)

    console.print(f"Read {len(grounded):,} grounded entities.")

    # Classify into add (no categories) vs replace (on a foreign DBpedia source) and resolve titles
    # (resolve is network for QID-only entities). Add and replace cohorts are kept apart so the
    # replace path can compute its diff and capture the removed rows.
    add_titles: dict[uuid.UUID, str] = {}
    replace_titles: dict[uuid.UUID, str] = {}

    def _needs_qid_lookup(external_ids: dict[str, Any]) -> bool:
        """True when there is no stored DBpedia IRI, so the title needs a live QID→title call."""
        dbpedia = external_ids.get("dbpedia")
        return not (isinstance(dbpedia, dict) and dbpedia.get("id"))

    qid_lookups_total = sum(
        1
        for eid, ext in grounded
        if WIKIPEDIA_SOURCE not in existing.get(eid, set()) and _needs_qid_lookup(ext)
    )
    console.print(
        f"Resolving article titles — {qid_lookups_total:,} need a live QID→title lookup "
        "(the slow, one-at-a-time step)…"
    )
    qid_done = 0
    for entity_id, external_ids in grounded:
        sources = existing.get(entity_id, set())
        if WIKIPEDIA_SOURCE in sources:
            plan.skipped_done += 1
            continue
        if _needs_qid_lookup(external_ids):
            qid_done += 1
            if qid_done % 25 == 0 or qid_done == qid_lookups_total:
                console.print(f"  …{qid_done:,}/{qid_lookups_total:,} QID lookups done")
        title = await resolve_article_title(
            external_ids, qid_of(external_ids), resolver
        )
        if title is None:
            plan.unresolvable += 1
            continue
        if sources:  # on a foreign source (the DBpedia 373) → replace path (US3)
            replace_titles[entity_id] = title
        else:  # no categories yet → add path (US1)
            add_titles[entity_id] = title

    # One bulk fetch for both cohorts' distinct titles (batched + paced inside the service).
    titles = list(dict.fromkeys([*add_titles.values(), *replace_titles.values()]))
    n_batches = -(-len(titles) // 50)  # ceil, 50 titles/request
    console.print(
        f"Fetching categories for {len(titles):,} titles (~{n_batches:,} paced requests)…"
    )
    fetched = await fetch_service.categories_for_titles(titles) if titles else {}
    console.print(f"  categories fetched for {len(fetched):,} titles.")

    new_category_names: set[str] = set()

    for entity_id, title in add_titles.items():
        names = fetched.get(title)
        if names is None:
            plan.fetch_omitted += 1  # fetch failed/missing — leave as-is, retry later
            continue
        if not names:
            plan.zero_categories += 1  # processed, zero — add-only no-op
            continue
        plan.to_add.append((entity_id, title, names))
        new_category_names.update(names)

    for entity_id, title in replace_titles.items():
        names = fetched.get(title)
        # Never replace-to-empty: a failed/empty fetch keeps the entity's DBpedia categories.
        if not names:
            plan.replace_skipped_empty += 1
            continue
        old_names = old_categories.get(entity_id, [])
        old_norm = {_norm(n) for n in old_names}
        new_norm = {_norm(n) for n in names}
        plan.diff_added += len(new_norm - old_norm)
        plan.diff_removed += len(old_norm - new_norm)
        plan.diff_unchanged += len(new_norm & old_norm)
        plan.to_replace.append((entity_id, title, names, old_names))
        new_category_names.update(names)

    # Bulk-fetch global sizes for every new category (still network, still off any write txn).
    if new_category_names:
        n_size_batches = -(-len(new_category_names) // 50)
        console.print(
            f"Fetching global sizes for {len(new_category_names):,} new categories "
            f"(~{n_size_batches:,} paced requests)…"
        )
        plan.sizes = await size_service.sizes_for(sorted(new_category_names))
    console.print("Planning complete.")

    return plan


def _report(plan: _Plan, grounded_count: int) -> None:
    console.print(f"Grounded entities: {grounded_count:,}")
    console.print(f"  already on the Wikipedia source (skipped): {plan.skipped_done:,}")
    console.print(f"  unresolvable article (skipped + reported): {plan.unresolvable:,}")
    console.print("  ADD (no categories yet):")
    console.print(f"    will receive categories: {len(plan.to_add):,}")
    console.print(f"    fetch omitted (retry on a later run): {plan.fetch_omitted:,}")
    console.print(
        f"    article has zero non-hidden categories: {plan.zero_categories:,}"
    )
    console.print("  REPLACE (existing DBpedia 373 → Wikipedia namespace):")
    console.print(f"    will be rewritten: {len(plan.to_replace):,}")
    console.print(
        f"    kept as-is (fetch empty/failed — retry later): {plan.replace_skipped_empty:,}"
    )
    console.print(
        f"    diff — categories added {plan.diff_added:,} / removed {plan.diff_removed:,} "
        f"/ unchanged {plan.diff_unchanged:,}"
    )
    console.print(f"  distinct new category sizes fetched: {len(plan.sizes):,}")


async def _apply(
    plan: _Plan,
    dbname: str,
    *,
    cat_repo: WikipediaCategoryRepository,
    assign_repo: EntityCategoryRepository,
) -> None:
    """Phase B — one network-free write transaction; capture written before the single commit."""
    async with db_manager.session(echo=False) as session:
        for entity_id, _title, names in plan.to_add:
            await store_categories_for_entity(
                session,
                entity_id,
                names,
                cat_repo=cat_repo,
                assign_repo=assign_repo,
                sizes=plan.sizes,
                replace=False,
            )
        for entity_id, _title, names, _old in plan.to_replace:
            # delete-then-add: the entity's DBpedia assignments are removed and the Wikipedia set
            # written (the never-replace-to-empty guard already excluded empty fetches upstream).
            await store_categories_for_entity(
                session,
                entity_id,
                names,
                cat_repo=cat_repo,
                assign_repo=assign_repo,
                sizes=plan.sizes,
                replace=True,
            )

        _CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        capture_path = _CAPTURE_DIR / f"entity_category_backfill_capture_{stamp}.json"
        capture_path.write_text(
            json.dumps(
                {
                    "database": dbname,
                    "created_at": datetime.datetime.now().isoformat(),
                    # Reversal of ADD = delete these Wikipedia assignments; orphaned category rows
                    # are harmless (spec).
                    "assignments_inserted": [
                        {"entity_id": str(entity_id), "categories": names}
                        for entity_id, _title, names in plan.to_add
                    ],
                    # Reversal of REPLACE = restore `before` (the removed DBpedia rows, FR-009) and
                    # delete `after`; `before`/`after` are each entity's full set (FR-013/SC-007).
                    "assignments_replaced": [
                        {
                            "entity_id": str(entity_id),
                            "before": old,
                            "after": names,
                        }
                        for entity_id, _title, names, old in plan.to_replace
                    ],
                    "diff": {
                        "added": plan.diff_added,
                        "removed": plan.diff_removed,
                        "unchanged": plan.diff_unchanged,
                    },
                },
                indent=2,
            )
        )
        console.print(f"Capture written (gitignored): {capture_path}")

        await session.commit()

    console.print(
        f"APPLIED: added for {len(plan.to_add):,} entities; "
        f"replaced for {len(plan.to_replace):,} (diff +{plan.diff_added:,} "
        f"/ -{plan.diff_removed:,} / ={plan.diff_unchanged:,})."
    )


async def run_backfill(apply: bool, confirm_target: str | None) -> int:
    entity_repo = NamedEntityRepository()
    cat_repo = WikipediaCategoryRepository()
    assign_repo = EntityCategoryRepository()
    size_service = CategorySizeService()
    fetch_service = EntityCategoryFetchService()
    resolver = DbpediaResolver()

    async with db_manager.session(echo=False) as session:
        dbname = (await session.execute(text("SELECT current_database()"))).scalar_one()
        grounded_count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM named_entities "
                    "WHERE external_ids -> 'wikidata' ->> 'id' IS NOT NULL"
                )
            )
        ).scalar_one()
        await session.rollback()
    console.print(f"Effective database: {dbname}")

    if apply and confirm_target != dbname:
        console.print(
            f"REFUSED: --apply requires --confirm-target {dbname!r} "
            f"(got {confirm_target!r}). No changes made."
        )
        return 2

    plan = await build_plan(
        entity_repo=entity_repo,
        resolver=resolver,
        fetch_service=fetch_service,
        size_service=size_service,
    )
    _report(plan, int(grounded_count))

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
        prog="backfill_entity_categories",
        description="Backfill entity→Wikipedia categories into the Feature 083 tables (Feature 084).",
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
