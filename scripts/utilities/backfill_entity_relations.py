"""Backfill ``founder`` + ``significant_person`` onto already-grounded entities (Feature 087).

``founder`` (P112) was not captured before this feature, and ``significant_person`` (P3342) was
captured only on entities enriched after it was added. This re-fetches each grounded entity's curated
Wikidata properties and **merges** the two relation fields in, so existing orgs show their founders
and significant people (forward, and in reverse on the referenced entities' pages).

Safety (mirrors Feature 084):
- **Default is dry-run.** Writes happen only with ``--apply``.
- **Target confirmation** — ``--apply`` requires ``--confirm-target <dbname>`` matching the effective
  database, so a prod write is a deliberate act.
- **Additive merge, never a replace** — uses ``NamedEntityRepository.merge_properties`` (JSONB ``||``)
  so every OTHER stored property is preserved. (``replace_properties`` would wipe the bag.)
- **Absence vs never-fetched** — a field the source does not assert is simply not added; a field whose
  stored value already matches the fetched one is skipped. So a re-run is idempotent.
- **Reversible capture** — an ``--apply`` run writes a gitignored JSON capture of each entity's
  BEFORE/AFTER for the two fields, before the single commit.

Usage::

    python scripts/utilities/backfill_entity_relations.py                      # dry-run (default)
    python scripts/utilities/backfill_entity_relations.py --apply --confirm-target chronovista
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sqlalchemy import text  # noqa: E402

from chronovista.config.database import db_manager  # noqa: E402
from chronovista.repositories.named_entity_repository import (  # noqa: E402
    NamedEntityRepository,
)
from chronovista.services.wikidata_client import (  # noqa: E402
    WikidataClient,
    WikidataUnavailable,
)
from chronovista.services.wikidata_properties import SOURCE, wikidata_qid  # noqa: E402

_FIELDS = ("founder", "significant_person")
_CAPTURE_DIR = Path(__file__).resolve().parents[1] / "entity_resolution"


def _substantive(block: Any) -> tuple[Any, Any]:
    """The comparable content of a relation block: ``(values, qids)``, ignoring volatile provenance.

    ``set_at`` is stamped fresh on every fetch (``assemble_block``), so a whole-block ``!=`` reports a
    change on every re-run — which would make the backfill rewrite every entity forever. Idempotency
    must compare only the substantive payload, not the provenance timestamp.
    """
    if not isinstance(block, dict):
        return (None, None)
    return (block.get("values"), block.get("qids"))


def _patch_for(current: dict[str, Any], fetched: dict[str, Any]) -> dict[str, Any]:
    """The founder/significant_person blocks to merge in.

    A field is included only when ALL of:
    - the source asserts a non-empty block (so a genuine *absence* is left alone);
    - the stored block, if any, was itself Wikidata-sourced (a manual/other-pipeline curation owns
      the key and is never clobbered);
    - its substantive content (values + qids) differs from what is stored — so a re-run whose only
      difference is a fresh ``set_at`` writes nothing (true idempotency, finding-1 fix).
    Never touches any field outside ``_FIELDS``.
    """
    patch: dict[str, Any] = {}
    for f in _FIELDS:
        incoming = fetched.get(f)
        if not (isinstance(incoming, dict) and incoming):
            continue
        existing = current.get(f)
        if isinstance(existing, dict) and existing.get("source") not in (None, SOURCE):
            continue
        if _substantive(existing) == _substantive(incoming):
            continue
        patch[f] = incoming
    return patch


async def build_plan(client: WikidataClient) -> dict[uuid.UUID, dict[str, Any]]:
    """{entity_id: patch} — the founder/significant_person blocks to merge in, per entity.

    A field is included only when the source asserts it AND the stored value differs (so the plan is
    empty on a second run — idempotent). Fetch failures are skipped and counted, not fatal.
    """
    repo = NamedEntityRepository()
    async with db_manager.session(echo=False) as session:
        grounded = await repo.list_wikidata_grounded(session)
        # snapshot (id, qid, current founder/significant_person) while the session is open
        snapshot = [
            (e.id, wikidata_qid(e.external_ids), dict(e.properties or {}))
            for e in grounded
        ]
        await session.rollback()
    print(f"Read {len(snapshot):,} grounded entities.", flush=True)

    to_fetch = [(eid, qid, props) for eid, qid, props in snapshot if qid is not None]
    no_qid = len(snapshot) - len(to_fetch)
    total = len(to_fetch)
    print(
        f"Fetching Wikidata properties for {total:,} entities one at a time "
        f"(~200/min — expect several minutes; progress every 100)…",
        flush=True,
    )

    plan: dict[uuid.UUID, dict[str, Any]] = {}
    failures = 0
    unresolvable = 0
    for i, (entity_id, qid, props) in enumerate(to_fetch, start=1):
        try:
            fetched = await client.fetch_properties(qid)
        except WikidataUnavailable:
            failures += 1  # transport/429/non-2xx — a retry could still yield data
        else:
            if not fetched:
                unresolvable += (
                    1  # QID redirected/merged/deleted — NOT "asserts nothing"
                )
            else:
                patch = _patch_for(props, fetched)
                if patch:
                    plan[entity_id] = patch
        if i % 100 == 0 or i == total:
            print(
                f"  …{i:,}/{total:,} fetched — {len(plan):,} with a new field, "
                f"{failures:,} unavailable, {unresolvable:,} unresolvable",
                flush=True,
            )
    if no_qid:
        print(f"  ({no_qid:,} entities had no Wikidata QID — skipped)", flush=True)
    if failures:
        print(
            f"  ({failures} entities skipped — Wikidata unavailable; a re-run may complete them)",
            flush=True,
        )
    if unresolvable:
        print(
            f"  ({unresolvable} entities skipped — QID did not resolve to a Wikidata item)",
            flush=True,
        )
    return plan


def _report(plan: dict[uuid.UUID, dict[str, Any]], grounded: int) -> None:
    founder = sum(1 for p in plan.values() if "founder" in p)
    sig = sum(1 for p in plan.values() if "significant_person" in p)
    print(f"Grounded entities scanned: {grounded}")
    print(f"Entities that would gain/refresh a field: {len(plan)}")
    print(f"  + founder: {founder}")
    print(f"  + significant_person: {sig}")


async def _apply(plan: dict[uuid.UUID, dict[str, Any]], dbname: str) -> None:
    """One write transaction. The reversible capture is written (as ``*.pending.json``) BEFORE the
    single commit, then renamed to its final name only AFTER the commit succeeds — so a capture file
    that claims the change was applied exists only when it actually was (findings 2 + 3).

    To undo from a capture: for each row, set every key in ``before`` back to its recorded value and
    **delete** every key listed in ``absent`` (it did not exist pre-backfill — restoring it as JSON
    ``null`` would be wrong).
    """
    repo = NamedEntityRepository()
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    _CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    final_path = _CAPTURE_DIR / f"entity_relations_backfill_capture_{stamp}.json"
    pending_path = final_path.with_suffix(".pending.json")
    async with db_manager.session(echo=False) as session:
        capture: list[dict[str, Any]] = []
        for entity_id, patch in plan.items():
            before = await repo.get(session, entity_id)
            if before is None:
                continue
            props = before.properties or {}
            await repo.merge_properties(session, entity_id, patch)
            capture.append(
                {
                    "entity_id": str(entity_id),
                    "before": {f: props[f] for f in patch if f in props},
                    "absent": [f for f in patch if f not in props],
                    "after": patch,
                }
            )
        pending_path.write_text(json.dumps(capture, indent=2))
        await session.commit()
    pending_path.rename(
        final_path
    )  # commit succeeded → promote the capture to its final name
    print(
        f"Applied {len(capture)} merges to {dbname}. Capture (gitignored): {final_path}"
    )


async def run_backfill(apply: bool, confirm_target: str | None) -> int:
    async with db_manager.session(echo=False) as session:
        dbname = (await session.execute(text("SELECT current_database()"))).scalar_one()
        await session.rollback()
    print(f"Effective database: {dbname}")
    if apply and confirm_target != dbname:
        print(
            f"REFUSED: --apply requires --confirm-target {dbname!r} "
            f"(got {confirm_target!r}). No changes made."
        )
        return 2

    client = WikidataClient()
    async with db_manager.session(echo=False) as session:
        grounded = len(await repo_grounded(session))
        await session.rollback()
    plan = await build_plan(client)
    _report(plan, grounded)

    if not apply:
        print(
            f"\nDRY RUN — no changes. Re-run with --apply --confirm-target {dbname} to write."
        )
        return 0
    await _apply(plan, dbname)
    return 0


async def repo_grounded(session: Any) -> Any:
    return await NamedEntityRepository().list_wikidata_grounded(session)


def main() -> int:
    parser = argparse.ArgumentParser(prog="backfill_entity_relations")
    parser.add_argument(
        "--apply", action="store_true", help="Write changes (default: dry-run)"
    )
    parser.add_argument(
        "--confirm-target", default=None, help="Must match the effective db name"
    )
    args = parser.parse_args()
    return asyncio.run(run_backfill(args.apply, args.confirm_target))


if __name__ == "__main__":
    raise SystemExit(main())
