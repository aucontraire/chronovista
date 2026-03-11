#!/usr/bin/env python3
"""
Post-migration reclassification tool for transcript corrections.

After migration 039, all rows in `transcript_corrections` that previously had
`correction_type = 'asr_error'` were remapped to `'other'` as a safe neutral
default. This script helps you review and reclassify those rows into the correct
specific correction types using three operating modes:

  --audit      (default) Read-only analysis. Groups corrections by their
               corrected_at timestamp (the natural batch boundary) and shows
               samples, notes, and an auto-suggested type for each batch.
               Prints a summary of how many rows are auto-classifiable vs.
               require manual review.

  --apply      Applies all auto-classification suggestions that meet the 80%
               confidence threshold. Shows a preview of every batch that will
               change, then asks for confirmation before executing any UPDATE.

  --batch-id <corrected_at_timestamp> --set-type <type>
               Manual per-batch override. Targets all corrections that share
               the exact corrected_at value and sets them to the given type.

Valid correction types (user-assignable):
  spelling           Non-name orthographic errors (typos, common-word misspellings)
  proper_noun        Names of people, places, or organizations ASR misrecognized
  context_correction Right sound, wrong word — valid word that doesn't fit context
  word_boundary      Run-together words or wrongly split compounds
  formatting         Punctuation, capitalization, or spacing corrections
  profanity_fix      ASR garbled/censored profanity that needs restoration
  other              Corrections that don't fit any other category

Usage examples:
  python scripts/utilities/reclassify_asr_corrections.py --audit
  python scripts/utilities/reclassify_asr_corrections.py --apply
  python scripts/utilities/reclassify_asr_corrections.py --apply --dry-run
  python scripts/utilities/reclassify_asr_corrections.py \\
      --batch-id "2026-03-03 21:45:12" --set-type proper_noun
  python scripts/utilities/reclassify_asr_corrections.py \\
      --batch-id "2026-03-03 21:45:12" --set-type proper_noun --dry-run

Run this script from the project root so that the chronovista package is
importable, or ensure your virtual environment's site-packages are on PYTHONPATH.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap: add src/ to sys.path so the script runs from the project root
# without needing an editable install.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from sqlalchemy import text  # noqa: E402  (after sys.path fixup)

from chronovista.config.database import db_manager  # noqa: E402

# ---------------------------------------------------------------------------
# Rich imports — the library is a project dependency so it is always present.
# ---------------------------------------------------------------------------
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402
from rich import box  # noqa: E402

console = Console()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# All types a human operator may assign.
USER_ASSIGNABLE_TYPES: set[str] = {
    "spelling",
    "proper_noun",
    "context_correction",
    "word_boundary",
    "formatting",
    "profanity_fix",
    "other",
}

# Threshold: if this fraction of corrections in a batch share the same
# auto-suggested type, the whole batch gets that suggestion.
BATCH_CONFIDENCE_THRESHOLD = 0.80

MAX_SAMPLES = 3  # Samples shown per batch in --audit mode


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class Correction:
    id: str
    video_id: str
    language_code: str
    segment_id: str | None
    original_text: str
    corrected_text: str
    correction_note: str | None
    corrected_at: datetime
    version_number: int


@dataclass
class BatchAnalysis:
    corrected_at: datetime
    corrections: list[Correction]
    per_row_suggestions: list[str]          # one entry per correction
    batch_suggestion: str                   # dominant type or "manual"
    auto_classifiable: bool                 # True when confidence >= threshold
    dominant_type: str | None               # None when mixed
    confidence: float                       # fraction for dominant type


# ---------------------------------------------------------------------------
# Heuristic classifier
# ---------------------------------------------------------------------------

def _words(text: str) -> list[str]:
    return text.split()


def _is_title_cased_word(word: str) -> bool:
    """Return True if word starts with an uppercase letter."""
    return bool(word) and word[0].isupper()


def classify_correction(original: str, corrected: str) -> str:
    """
    Return a suggested correction_type string for a single (original, corrected)
    pair using simple, explainable heuristics.

    Core insight: humans capitalise proper nouns when correcting ASR errors, and
    they don't capitalise common words.  So if any changed token in the corrected
    text is title-cased, the correction is almost certainly a proper noun fix —
    regardless of whether the spelling also changed.

    Priority order:
    1. Spaces added or removed:
       - If a changed token in corrected text is title-cased → proper_noun
         (ASR split a name, e.g. "Shane Bomb" → "Sheinbaum")
       - Otherwise → word_boundary
    2. Same token count — if ANY changed token in corrected text is title-cased
       → proper_noun  (catches "Chsky" → "Chomsky", "Galain" → "Ghislaine",
       "norm" → "Noam", etc.)
    3. Identical ignoring case (no other signal) → formatting
    4. Fallback → other

    Parameters
    ----------
    original : str
        The original (pre-correction) text.
    corrected : str
        The corrected text.

    Returns
    -------
    str
        One of: "formatting", "word_boundary", "proper_noun", "other"
    """
    if original == corrected:
        return "other"

    orig_words = _words(original)
    corr_words = _words(corrected)

    # 1. Space count changed → word_boundary, unless a corrected token is
    #    title-cased (ASR split a name, e.g. "Shane Bomb" → "Sheinbaum").
    if original.count(" ") != corrected.count(" "):
        # Check if any token in the corrected text that differs is title-cased.
        # For unequal-length token lists we scan the corrected tokens that are
        # NOT present (case-insensitive) in the original tokens.
        orig_lower_set = {w.lower() for w in orig_words}
        has_title_cased_new_token = any(
            _is_title_cased_word(w)
            for w in corr_words
            if w.lower() not in orig_lower_set
        )
        return "proper_noun" if has_title_cased_new_token else "word_boundary"

    # 2. Same token count — analyse differing tokens.
    if len(orig_words) == len(corr_words):
        total_diffs = 0
        any_corrected_title = False

        for ow, cw in zip(orig_words, corr_words):
            if ow == cw:
                continue
            total_diffs += 1
            if _is_title_cased_word(cw):
                any_corrected_title = True

        if total_diffs > 0 and any_corrected_title:
            return "proper_noun"

    # 3. Identical ignoring case → formatting (pure capitalisation fix).
    if original.lower() == corrected.lower():
        return "formatting"

    return "other"


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

async def fetch_other_corrections(session: Any) -> list[Correction]:
    """
    Return all transcript_corrections rows where correction_type = 'other',
    ordered by corrected_at so natural batch groups stay together.
    """
    result = await session.execute(text("""
        SELECT
            id::text,
            video_id,
            language_code,
            segment_id::text,
            original_text,
            corrected_text,
            correction_note,
            corrected_at,
            version_number
        FROM transcript_corrections
        WHERE correction_type = 'other'
        ORDER BY corrected_at, id
    """))

    rows = result.fetchall()
    corrections: list[Correction] = []
    for row in rows:
        corrections.append(Correction(
            id=row.id,
            video_id=row.video_id,
            language_code=row.language_code,
            segment_id=row.segment_id,
            original_text=row.original_text or "",
            corrected_text=row.corrected_text or "",
            correction_note=row.correction_note,
            corrected_at=row.corrected_at,
            version_number=row.version_number,
        ))

    return corrections


async def apply_reclassification(
    session: Any,
    batch_timestamp: datetime,
    new_type: str,
    dry_run: bool,
) -> int:
    """
    UPDATE transcript_corrections SET correction_type = :new_type
    WHERE corrected_at = :ts AND correction_type = 'other'.

    Returns the number of rows that would be / were updated.
    """
    # Match within a 1-second window so users can copy timestamps from --audit
    # output (which shows second precision) without needing microseconds.
    from datetime import timedelta
    ts_start = batch_timestamp.replace(microsecond=0)
    ts_end = ts_start + timedelta(seconds=1)

    # First count how many rows are affected.
    count_result = await session.execute(text("""
        SELECT COUNT(*) FROM transcript_corrections
        WHERE corrected_at >= :ts_start AND corrected_at < :ts_end
          AND correction_type = 'other'
    """), {"ts_start": ts_start, "ts_end": ts_end})
    count: int = count_result.scalar_one()

    if not dry_run and count > 0:
        await session.execute(text("""
            UPDATE transcript_corrections
            SET correction_type = :new_type
            WHERE corrected_at >= :ts_start AND corrected_at < :ts_end
              AND correction_type = 'other'
        """), {"ts_start": ts_start, "ts_end": ts_end, "new_type": new_type})
        await session.commit()

    return count


# ---------------------------------------------------------------------------
# Batch analysis logic
# ---------------------------------------------------------------------------

def group_into_batches(corrections: list[Correction]) -> list[BatchAnalysis]:
    """
    Group corrections by corrected_at timestamp and run the heuristic classifier
    on each item.  Compute per-batch confidence and dominant type suggestion.
    """
    # Group by corrected_at (treat as an opaque key — same timestamp = same batch).
    from collections import defaultdict

    groups: dict[datetime, list[Correction]] = defaultdict(list)
    for c in corrections:
        groups[c.corrected_at].append(c)

    batches: list[BatchAnalysis] = []

    for ts in sorted(groups.keys()):
        batch_corrections = groups[ts]
        suggestions = [
            classify_correction(c.original_text, c.corrected_text)
            for c in batch_corrections
        ]

        # Tally suggestions.
        from collections import Counter
        counts = Counter(suggestions)
        total = len(suggestions)
        dominant_type, dominant_count = counts.most_common(1)[0]
        confidence = dominant_count / total if total > 0 else 0.0

        auto_classifiable = confidence >= BATCH_CONFIDENCE_THRESHOLD
        batch_suggestion = dominant_type if auto_classifiable else "manual"
        resolved_dominant = dominant_type if auto_classifiable else None

        batches.append(BatchAnalysis(
            corrected_at=ts,
            corrections=batch_corrections,
            per_row_suggestions=suggestions,
            batch_suggestion=batch_suggestion,
            auto_classifiable=auto_classifiable,
            dominant_type=resolved_dominant,
            confidence=confidence,
        ))

    return batches


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

_TYPE_COLOUR: dict[str, str] = {
    "proper_noun": "cyan",
    "word_boundary": "yellow",
    "formatting": "magenta",
    "spelling": "green",
    "context_correction": "blue",
    "profanity_fix": "red",
    "other": "white",
    "manual": "bright_red",
}


def _type_badge(suggestion: str) -> str:
    colour = _TYPE_COLOUR.get(suggestion, "white")
    return f"[{colour}]{suggestion}[/{colour}]"


def _truncate(text: str, max_len: int = 60) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def display_audit(batches: list[BatchAnalysis]) -> None:
    """Print the full audit report to the console."""
    total_rows = sum(len(b.corrections) for b in batches)

    auto_batches = [b for b in batches if b.auto_classifiable]
    manual_batches = [b for b in batches if not b.auto_classifiable]
    auto_rows = sum(len(b.corrections) for b in auto_batches)
    manual_rows = sum(len(b.corrections) for b in manual_batches)

    console.print(Panel(
        f"[bold]ASR Correction Reclassification Audit[/bold]\n"
        f"Rows needing review: [bold yellow]{total_rows}[/bold yellow] "
        f"(correction_type='other')",
        box=box.ROUNDED,
        padding=(0, 2),
    ))
    console.print()

    if not batches:
        console.print("[green]No rows with correction_type='other' found. Nothing to do.[/green]")
        return

    for idx, batch in enumerate(batches, start=1):
        ts_str = batch.corrected_at.strftime("%Y-%m-%d %H:%M:%S")
        count = len(batch.corrections)
        suggestion_display = _type_badge(batch.batch_suggestion)

        if batch.auto_classifiable:
            conf_pct = f"{batch.confidence * 100:.0f}% agreement"
            label = f"Suggested: {suggestion_display} [dim]({conf_pct})[/dim]"
        else:
            label = f"[bright_red]Mixed — manual review recommended[/bright_red]"

        console.print(
            f"[bold]Batch {idx}[/bold]  "
            f"[dim]│[/dim]  {ts_str}  "
            f"[dim]│[/dim]  {count} correction{'s' if count != 1 else ''}  "
            f"[dim]│[/dim]  {label}"
        )

        # Samples.
        samples = batch.corrections[:MAX_SAMPLES]
        for sample in samples:
            orig = _truncate(sample.original_text)
            corr = _truncate(sample.corrected_text)
            console.print(f"    [dim]\"{orig}\"[/dim] → [green]\"{corr}\"[/green]")

        # Notes.
        notes = {c.correction_note for c in batch.corrections if c.correction_note}
        if notes:
            for note in list(notes)[:2]:
                console.print(f"    [dim italic]Note: {_truncate(note, 80)}[/dim italic]")

        console.print()

    # Summary table.
    console.rule("[bold]Summary[/bold]")
    console.print()

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Label", style="dim", width=36)
    table.add_column("Value", justify="right")

    table.add_row("Total batches:", str(len(batches)))
    table.add_row(
        f"Auto-classifiable (>={int(BATCH_CONFIDENCE_THRESHOLD * 100)}% agreement):",
        f"{len(auto_batches)} batches ({auto_rows:,} rows)",
    )

    # Break down auto batches by dominant type.
    from collections import Counter
    type_counts: Counter[str] = Counter()
    type_row_counts: Counter[str] = Counter()
    for b in auto_batches:
        if b.dominant_type:
            type_counts[b.dominant_type] += 1
            type_row_counts[b.dominant_type] += len(b.corrections)

    for tp, batch_count in type_counts.most_common():
        colour = _TYPE_COLOUR.get(tp, "white")
        table.add_row(
            f"  [{colour}]{tp}[/{colour}]:",
            f"{batch_count} batches ({type_row_counts[tp]:,} rows)",
        )

    table.add_row(
        "Manual review needed:",
        f"{len(manual_batches)} batches ({manual_rows:,} rows)",
    )
    console.print(table)

    if manual_batches:
        console.print()
        console.print("[dim]To manually override a batch, run:[/dim]")
        example_ts = manual_batches[0].corrected_at.strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            f'  [cyan]python scripts/utilities/reclassify_asr_corrections.py '
            f'--batch-id "{example_ts}" --set-type <type>[/cyan]'
        )


def display_apply_preview(batches: list[BatchAnalysis]) -> None:
    """Print the list of batches that --apply will change."""
    auto_batches = [b for b in batches if b.auto_classifiable]

    if not auto_batches:
        console.print("[yellow]No auto-classifiable batches found. Nothing to apply.[/yellow]")
        return

    console.print(Panel(
        "[bold]Apply Auto-Classification Preview[/bold]",
        box=box.ROUNDED,
        padding=(0, 2),
    ))
    console.print()

    table = Table(
        "Batch",
        "Timestamp",
        "Rows",
        "New Type",
        "Confidence",
        box=box.SIMPLE_HEAD,
    )

    for idx, batch in enumerate(auto_batches, start=1):
        ts_str = batch.corrected_at.strftime("%Y-%m-%d %H:%M:%S")
        colour = _TYPE_COLOUR.get(batch.dominant_type or "other", "white")
        table.add_row(
            str(idx),
            ts_str,
            str(len(batch.corrections)),
            f"[{colour}]{batch.dominant_type}[/{colour}]",
            f"{batch.confidence * 100:.0f}%",
        )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------

async def run_audit(session: Any) -> None:
    """Fetch 'other' corrections and display the audit report."""
    console.print("[dim]Fetching corrections from database...[/dim]")
    corrections = await fetch_other_corrections(session)

    if not corrections:
        console.print(Panel(
            "[green]No rows with correction_type='other' found. Nothing to review.[/green]",
            box=box.ROUNDED,
        ))
        return

    batches = group_into_batches(corrections)
    display_audit(batches)


async def run_apply(session: Any, dry_run: bool) -> None:
    """Apply auto-classification suggestions to all confident batches."""
    console.print("[dim]Fetching corrections from database...[/dim]")
    corrections = await fetch_other_corrections(session)

    if not corrections:
        console.print("[green]No rows with correction_type='other' found.[/green]")
        return

    batches = group_into_batches(corrections)
    auto_batches = [b for b in batches if b.auto_classifiable]

    display_apply_preview(batches)

    if not auto_batches:
        return

    total_rows = sum(len(b.corrections) for b in auto_batches)

    if dry_run:
        console.print(
            f"[yellow][DRY RUN][/yellow] Would update {total_rows:,} rows across "
            f"{len(auto_batches)} batches. No changes made."
        )
        return

    # Confirm before executing.
    console.print(
        f"[bold]This will update {total_rows:,} rows across {len(auto_batches)} "
        f"batches in [red]transcript_corrections[/red].[/bold]"
    )
    answer = console.input("Proceed? [bold]yes/no[/bold]: ").strip().lower()
    if answer not in {"yes", "y"}:
        console.print("[yellow]Aborted. No changes made.[/yellow]")
        return

    updated_total = 0
    for batch in auto_batches:
        assert batch.dominant_type is not None  # guaranteed by auto_classifiable
        count = await apply_reclassification(
            session=session,
            batch_timestamp=batch.corrected_at,
            new_type=batch.dominant_type,
            dry_run=False,
        )
        updated_total += count
        ts_str = batch.corrected_at.strftime("%Y-%m-%d %H:%M:%S")
        colour = _TYPE_COLOUR.get(batch.dominant_type, "white")
        console.print(
            f"  [green]✓[/green]  {ts_str}  →  "
            f"[{colour}]{batch.dominant_type}[/{colour}]  ({count} rows)"
        )

    console.print()
    console.print(f"[green]Done.[/green] Updated {updated_total:,} rows.")


async def run_batch_override(
    session: Any,
    batch_id: str,
    new_type: str,
    dry_run: bool,
) -> None:
    """Set all 'other' corrections with the given corrected_at to new_type."""
    # Parse the timestamp string.
    try:
        batch_ts = datetime.fromisoformat(batch_id)
    except ValueError:
        console.print(
            f"[red]Error:[/red] Cannot parse --batch-id value as a timestamp: {batch_id!r}\n"
            "Expected format: YYYY-MM-DD HH:MM:SS"
        )
        sys.exit(1)

    count = await apply_reclassification(
        session=session,
        batch_timestamp=batch_ts,
        new_type=new_type,
        dry_run=dry_run,
    )

    if count == 0:
        console.print(
            f"[yellow]No rows found[/yellow] with corrected_at = {batch_id!r} "
            "and correction_type = 'other'."
        )
        return

    colour = _TYPE_COLOUR.get(new_type, "white")
    if dry_run:
        console.print(
            f"[yellow][DRY RUN][/yellow] Would update {count} rows "
            f"(corrected_at = {batch_id!r}) → [{colour}]{new_type}[/{colour}]"
        )
    else:
        console.print(
            f"[green]Updated {count} rows[/green] "
            f"(corrected_at = {batch_id!r}) → [{colour}]{new_type}[/{colour}]"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reclassify_asr_corrections",
        description=(
            "Review and reclassify transcript_corrections rows that were mapped "
            "to correction_type='other' by migration 039."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
modes:
  (default / --audit)
      Read-only analysis grouped by corrected_at batch timestamp.
      Shows samples, notes, and an auto-suggested type per batch.

  --apply
      Applies all auto-classification suggestions with >=80%% agreement.
      Asks for confirmation before writing to the database.

  --batch-id TIMESTAMP --set-type TYPE
      Manual override for a single batch.  Sets every row whose
      corrected_at matches TIMESTAMP to the given TYPE.

examples:
  python scripts/utilities/reclassify_asr_corrections.py --audit
  python scripts/utilities/reclassify_asr_corrections.py --apply --dry-run
  python scripts/utilities/reclassify_asr_corrections.py --apply
  python scripts/utilities/reclassify_asr_corrections.py \\
      --batch-id "2026-03-03 21:45:12" --set-type proper_noun
  python scripts/utilities/reclassify_asr_corrections.py \\
      --batch-id "2026-03-03 21:45:12" --set-type proper_noun --dry-run
        """,
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--audit",
        action="store_true",
        default=False,
        help="(default) Read-only audit: show batches with suggested types.",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply auto-classification suggestions (asks for confirmation).",
    )

    parser.add_argument(
        "--batch-id",
        metavar="TIMESTAMP",
        default=None,
        help=(
            "corrected_at timestamp of the batch to override "
            "(e.g. '2026-03-03 21:45:12'). Requires --set-type."
        ),
    )
    parser.add_argument(
        "--set-type",
        metavar="TYPE",
        default=None,
        choices=sorted(USER_ASSIGNABLE_TYPES),
        help=(
            "Correction type to assign to the --batch-id batch. "
            f"Choices: {', '.join(sorted(USER_ASSIGNABLE_TYPES))}"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would change without writing to the database.",
    )

    return parser


async def _run(args: argparse.Namespace) -> None:
    """Async entry point — obtains a single DB session and dispatches to mode."""
    async for session in db_manager.get_session(echo=False):
        if args.batch_id is not None:
            await run_batch_override(
                session=session,
                batch_id=args.batch_id,
                new_type=args.set_type,
                dry_run=args.dry_run,
            )
        elif args.apply:
            await run_apply(session=session, dry_run=args.dry_run)
        else:
            # Default: --audit
            await run_audit(session=session)

        # Break after first (and only) session — the generator yields exactly one.
        break


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Validate --batch-id / --set-type pairing.
    if args.batch_id is not None and args.set_type is None:
        parser.error("--batch-id requires --set-type.")
    if args.set_type is not None and args.batch_id is None:
        parser.error("--set-type requires --batch-id.")
    if args.batch_id is not None and args.apply:
        parser.error("--batch-id and --apply cannot be used together.")

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
