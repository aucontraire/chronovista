#!/usr/bin/env python3
"""
Retroactively assign ``batch_id`` values to historical transcript corrections.

The ``transcript_corrections`` table gained a nullable ``batch_id`` UUID column
(Feature 045).  This script identifies groups of corrections that were applied
together in a single batch run and assigns them a shared UUIDv7 ``batch_id``.

Two complementary grouping strategies are applied in sequence:

Strategy 1 — CLI batches (same-text grouping)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Groups by (``corrected_by_user_id``, ``original_text``, ``corrected_text``),
then applies a sliding-window on ``corrected_at``.  This catches CLI
find-replace operations where every correction shares the same original
and replacement text.

Strategy 2 — Frontend/API batches (same-timestamp grouping)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Groups by (``corrected_by_user_id``, ``corrected_at``) regardless of text
content.  This catches frontend batch applies where corrections are written
in a single DB transaction (identical timestamp) but each segment has
different surrounding context text.

Both strategies only assign batch IDs to groups of 2+ corrections.
Single-correction groups remain with ``batch_id = NULL``.

The script is **idempotent** — re-running it skips already-assigned rows.

Usage examples
--------------
  python scripts/utilities/backfill_batch_ids.py
  python scripts/utilities/backfill_batch_ids.py --dry-run
  python scripts/utilities/backfill_batch_ids.py --window 10
  python scripts/utilities/backfill_batch_ids.py --window 2.5 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap: add src/ to sys.path so the script runs from the project root
# without needing an editable install.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from sqlalchemy import text, update  # noqa: E402
from uuid_utils import uuid7  # noqa: E402

from chronovista.config.database import db_manager  # noqa: E402

# ---------------------------------------------------------------------------
# Rich imports
# ---------------------------------------------------------------------------
from rich.console import Console  # noqa: E402
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402
from rich import box  # noqa: E402

console = Console()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WINDOW_SECONDS: float = 5.0


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class CorrectionRow:
    """Lightweight container for a single correction row."""

    id: str
    corrected_by_user_id: str | None
    original_text: str
    corrected_text: str
    corrected_at: Any  # datetime from DB


@dataclass
class BatchGroup:
    """A group of corrections that should share a batch_id."""

    correction_ids: list[str] = field(default_factory=list)
    strategy: str = "cli"  # "cli" or "timestamp"


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

async def fetch_unassigned_corrections(session: Any) -> list[CorrectionRow]:
    """
    Fetch all corrections where batch_id IS NULL and both original_text and
    corrected_text are non-empty.

    Returns rows ordered by corrected_by_user_id, original_text, corrected_text,
    corrected_at — exactly the order needed for Strategy 1 grouping.
    """
    result = await session.execute(text("""
        SELECT
            id::text,
            corrected_by_user_id,
            original_text,
            corrected_text,
            corrected_at
        FROM transcript_corrections
        WHERE batch_id IS NULL
          AND original_text IS NOT NULL
          AND original_text != ''
          AND corrected_text IS NOT NULL
          AND corrected_text != ''
        ORDER BY
            corrected_by_user_id NULLS FIRST,
            original_text,
            corrected_text,
            corrected_at
    """))

    rows = result.fetchall()
    return [
        CorrectionRow(
            id=row.id,
            corrected_by_user_id=row.corrected_by_user_id,
            original_text=row.original_text,
            corrected_text=row.corrected_text,
            corrected_at=row.corrected_at,
        )
        for row in rows
    ]


async def assign_batch_id(
    session: Any,
    correction_ids: list[str],
    batch_id: uuid.UUID,
) -> None:
    """UPDATE the given correction rows with the provided batch_id and commit."""
    from chronovista.db.models import TranscriptCorrection as TC

    stmt = (
        update(TC)
        .where(TC.id.in_(correction_ids))
        .values(batch_id=batch_id)
    )
    await session.execute(stmt)
    await session.commit()


# ---------------------------------------------------------------------------
# Strategy 1: CLI batches — group by (actor, original_text, corrected_text)
# ---------------------------------------------------------------------------

def _group_key(row: CorrectionRow) -> tuple[str | None, str, str]:
    """Return the grouping key for a correction row (Strategy 1)."""
    return (row.corrected_by_user_id, row.original_text, row.corrected_text)


def identify_batches_by_text(
    corrections: list[CorrectionRow],
    window_seconds: float,
) -> list[BatchGroup]:
    """
    Strategy 1: Group corrections by (actor, original_text, corrected_text),
    then apply sliding-window within each group.

    This catches CLI find-replace operations where every matched segment
    produces the same original→corrected text pair.

    Only returns batch groups with 2+ corrections.
    """
    if not corrections:
        return []

    batches: list[BatchGroup] = []

    current_key = _group_key(corrections[0])
    current_window: list[CorrectionRow] = [corrections[0]]

    def _flush_window(window: list[CorrectionRow]) -> None:
        if len(window) >= 2:
            batches.append(BatchGroup(
                correction_ids=[c.id for c in window],
                strategy="cli",
            ))

    for row in corrections[1:]:
        key = _group_key(row)

        if key != current_key:
            _flush_window(current_window)
            current_key = key
            current_window = [row]
        else:
            prev = current_window[-1]
            gap = (row.corrected_at - prev.corrected_at).total_seconds()

            if gap < window_seconds:
                current_window.append(row)
            else:
                _flush_window(current_window)
                current_window = [row]

    _flush_window(current_window)

    return batches


# ---------------------------------------------------------------------------
# Strategy 2: Frontend/API batches — group by (actor, exact timestamp)
# ---------------------------------------------------------------------------

def identify_batches_by_timestamp(
    corrections: list[CorrectionRow],
) -> list[BatchGroup]:
    """
    Strategy 2: Group corrections by (actor, corrected_at) exact match.

    This catches frontend/API batch applies where all corrections in a
    single request share the exact same timestamp (written in one DB
    transaction) but each segment has different surrounding context text.

    Only returns batch groups with 2+ corrections.
    """
    if not corrections:
        return []

    # Build groups keyed by (actor, timestamp)
    groups: dict[tuple[str | None, Any], list[str]] = {}
    for row in corrections:
        key = (row.corrected_by_user_id, row.corrected_at)
        groups.setdefault(key, []).append(row.id)

    return [
        BatchGroup(correction_ids=ids, strategy="timestamp")
        for ids in groups.values()
        if len(ids) >= 2
    ]


# ---------------------------------------------------------------------------
# Combined identification
# ---------------------------------------------------------------------------

def identify_all_batches(
    corrections: list[CorrectionRow],
    window_seconds: float,
) -> list[BatchGroup]:
    """
    Apply both grouping strategies in sequence.

    Strategy 1 (same-text sliding-window) runs first.  Corrections that
    were assigned to a batch in Strategy 1 are excluded from Strategy 2
    to avoid double-assignment.

    Returns the combined list of batch groups from both strategies.
    """
    # Strategy 1: CLI batches
    cli_batches = identify_batches_by_text(corrections, window_seconds)

    # Collect IDs already assigned by Strategy 1
    assigned_ids: set[str] = set()
    for bg in cli_batches:
        assigned_ids.update(bg.correction_ids)

    # Strategy 2: timestamp batches on remaining corrections
    remaining = [c for c in corrections if c.id not in assigned_ids]
    timestamp_batches = identify_batches_by_timestamp(remaining)

    return cli_batches + timestamp_batches


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

async def run_backfill(dry_run: bool, window_seconds: float) -> int:
    """
    Execute the backfill process.

    Returns
    -------
    int
        Exit code: 0 on success, 1 on error.
    """
    try:
        async for session in db_manager.get_session(echo=False):
            console.print("[dim]Fetching unassigned corrections...[/dim]")
            corrections = await fetch_unassigned_corrections(session)

            if not corrections:
                console.print(
                    "[green]No unassigned batch corrections found. "
                    "Nothing to backfill.[/green]"
                )
                return 0

            console.print(
                f"[dim]Found {len(corrections):,} corrections without batch_id.[/dim]"
            )

            # Identify batches via both strategies.
            batch_groups = identify_all_batches(corrections, window_seconds)

            if not batch_groups:
                console.print(
                    "[green]No multi-correction batches identified. "
                    "All corrections are standalone.[/green]"
                )
                return 0

            cli_batches = [bg for bg in batch_groups if bg.strategy == "cli"]
            ts_batches = [bg for bg in batch_groups if bg.strategy == "timestamp"]
            cli_count = sum(len(bg.correction_ids) for bg in cli_batches)
            ts_count = sum(len(bg.correction_ids) for bg in ts_batches)

            console.print(
                f"[dim]Strategy 1 (same-text): "
                f"{len(cli_batches)} batches, {cli_count:,} corrections[/dim]"
            )
            console.print(
                f"[dim]Strategy 2 (same-timestamp): "
                f"{len(ts_batches)} batches, {ts_count:,} corrections[/dim]"
            )

            total_assigned = cli_count + ts_count

            if dry_run:
                console.print()
                console.print(
                    Panel(
                        "[bold yellow]DRY RUN[/bold yellow] — no changes will be made.",
                        box=box.ROUNDED,
                        padding=(0, 2),
                    )
                )

            # Process batches with progress bar.
            console.print()
            assigned_count = 0

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Assigning batch IDs...",
                    total=len(batch_groups),
                )

                for bg in batch_groups:
                    batch_uuid = uuid.UUID(bytes=uuid7().bytes)

                    if not dry_run:
                        await assign_batch_id(session, bg.correction_ids, batch_uuid)

                    assigned_count += len(bg.correction_ids)
                    progress.advance(task)

            # Summary report.
            console.print()
            _display_summary(
                total_corrections=len(corrections),
                batches_identified=len(batch_groups),
                corrections_assigned=assigned_count,
                corrections_left_null=len(corrections) - assigned_count,
                dry_run=dry_run,
                window_seconds=window_seconds,
                cli_batches=len(cli_batches),
                cli_corrections=cli_count,
                ts_batches=len(ts_batches),
                ts_corrections=ts_count,
            )

            # Break after first session yield.
            break

        return 0

    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1


def _display_summary(
    total_corrections: int,
    batches_identified: int,
    corrections_assigned: int,
    corrections_left_null: int,
    dry_run: bool,
    window_seconds: float,
    cli_batches: int,
    cli_corrections: int,
    ts_batches: int,
    ts_corrections: int,
) -> None:
    """Display a Rich summary table of the backfill results."""
    mode_label = "[yellow]DRY RUN[/yellow]" if dry_run else "[green]APPLIED[/green]"

    table = Table(
        title=f"Batch ID Backfill Summary ({mode_label})",
        box=box.ROUNDED,
        show_header=False,
        padding=(0, 2),
    )
    table.add_column("Label", style="dim", width=40)
    table.add_column("Value", justify="right")

    table.add_row("Window threshold (Strategy 1):", f"{window_seconds}s")
    table.add_row("Corrections processed:", f"{total_corrections:,}")
    table.add_row("", "")
    table.add_row(
        "Strategy 1 (same-text, CLI):",
        f"{cli_batches:,} batches, {cli_corrections:,} corrections",
    )
    table.add_row(
        "Strategy 2 (same-timestamp, API/frontend):",
        f"{ts_batches:,} batches, {ts_corrections:,} corrections",
    )
    table.add_row("", "")
    table.add_row("Total batches identified:", f"{batches_identified:,}")
    table.add_row("Total corrections assigned:", f"{corrections_assigned:,}")
    table.add_row("Corrections left as NULL:", f"{corrections_left_null:,}")

    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backfill_batch_ids",
        description=(
            "Retroactively assign batch_id values to historical transcript "
            "corrections that were applied together in batch runs.\n\n"
            "Two strategies are used:\n"
            "  Strategy 1: Group by (actor, original_text, corrected_text) with\n"
            "              a sliding time window (catches CLI find-replace).\n"
            "  Strategy 2: Group by (actor, exact timestamp) regardless of text\n"
            "              (catches frontend/API batch applies)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python scripts/utilities/backfill_batch_ids.py
  python scripts/utilities/backfill_batch_ids.py --dry-run
  python scripts/utilities/backfill_batch_ids.py --window 10
  python scripts/utilities/backfill_batch_ids.py --window 2.5 --dry-run
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview groupings without modifying data.",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=DEFAULT_WINDOW_SECONDS,
        metavar="SECONDS",
        help=(
            f"Maximum gap (in seconds) between consecutive corrections "
            f"to consider them part of the same batch. Only applies to "
            f"Strategy 1 (default: {DEFAULT_WINDOW_SECONDS})."
        ),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.window <= 0:
        parser.error("--window must be a positive number.")

    exit_code = asyncio.run(run_backfill(dry_run=args.dry_run, window_seconds=args.window))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
