#!/usr/bin/env python3
"""
Retroactively assign ``batch_id`` values to historical transcript corrections.

The ``transcript_corrections`` table gained a nullable ``batch_id`` UUID column
(Feature 045).  This script identifies groups of corrections that were applied
together in a single batch run and assigns them a shared UUIDv7 ``batch_id``.

Algorithm
---------
1. Query all corrections where ``batch_id IS NULL`` and both ``original_text``
   and ``corrected_text`` are non-empty.
2. Group by (``corrected_by_user_id``, ``original_text``, ``corrected_text``).
3. Within each group, apply a sliding-window: consecutive corrections whose
   ``corrected_at`` gap is strictly less than ``--window`` seconds belong to
   the same batch.  A gap >= the threshold starts a new batch.
4. Groups of 2+ corrections receive a generated UUIDv7 ``batch_id``.
5. Single-correction groups remain with ``batch_id = NULL``.
6. Changes are committed after each batch assignment for interruption safety.

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


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

async def fetch_unassigned_corrections(session: Any) -> list[CorrectionRow]:
    """
    Fetch all corrections where batch_id IS NULL and both original_text and
    corrected_text are non-empty.

    Returns rows ordered by corrected_by_user_id, original_text, corrected_text,
    corrected_at — exactly the order needed for grouping.
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
# Grouping and sliding-window logic
# ---------------------------------------------------------------------------

def _group_key(row: CorrectionRow) -> tuple[str | None, str, str]:
    """Return the grouping key for a correction row."""
    return (row.corrected_by_user_id, row.original_text, row.corrected_text)


def identify_batches(
    corrections: list[CorrectionRow],
    window_seconds: float,
) -> list[BatchGroup]:
    """
    Group corrections by (corrected_by_user_id, original_text, corrected_text),
    then apply sliding-window within each group to identify batch runs.

    Only returns batch groups with 2+ corrections (single-correction groups
    are intentionally excluded — they keep batch_id = NULL).

    Parameters
    ----------
    corrections : list[CorrectionRow]
        Corrections pre-sorted by corrected_by_user_id, original_text,
        corrected_text, corrected_at.
    window_seconds : float
        Maximum gap (exclusive) between consecutive corrected_at timestamps
        for corrections to be considered part of the same batch.

    Returns
    -------
    list[BatchGroup]
        Batch groups with 2+ corrections each.
    """
    if not corrections:
        return []

    batches: list[BatchGroup] = []

    # Group by key — since input is sorted, we can do a single pass.
    current_key = _group_key(corrections[0])
    current_window: list[CorrectionRow] = [corrections[0]]

    def _flush_window(window: list[CorrectionRow]) -> None:
        """If the window has 2+ corrections, record it as a batch."""
        if len(window) >= 2:
            batches.append(BatchGroup(correction_ids=[c.id for c in window]))

    for row in corrections[1:]:
        key = _group_key(row)

        if key != current_key:
            # New group — flush current window and start fresh.
            _flush_window(current_window)
            current_key = key
            current_window = [row]
        else:
            # Same group — check time gap with previous correction.
            prev = current_window[-1]
            gap = (row.corrected_at - prev.corrected_at).total_seconds()

            if gap < window_seconds:
                # Within window — extend current batch.
                current_window.append(row)
            else:
                # Gap too large — flush and start new window.
                _flush_window(current_window)
                current_window = [row]

    # Flush the last window.
    _flush_window(current_window)

    return batches


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
                    "[green]No unassigned batch corrections found.[/green]"
                )
                return 0

            console.print(
                f"[dim]Found {len(corrections):,} corrections without batch_id.[/dim]"
            )

            # Identify batches via sliding window.
            batch_groups = identify_batches(corrections, window_seconds)

            if not batch_groups:
                console.print(
                    "[green]No multi-correction batches identified. "
                    "All corrections are standalone.[/green]"
                )
                return 0

            total_assigned = sum(len(bg.correction_ids) for bg in batch_groups)

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

    table.add_row("Window threshold:", f"{window_seconds}s")
    table.add_row("Corrections processed:", f"{total_corrections:,}")
    table.add_row("Batches identified:", f"{batches_identified:,}")
    table.add_row("Corrections assigned to batches:", f"{corrections_assigned:,}")
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
            "corrections that were applied together in batch runs."
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
            f"to consider them part of the same batch (default: {DEFAULT_WINDOW_SECONDS})."
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
