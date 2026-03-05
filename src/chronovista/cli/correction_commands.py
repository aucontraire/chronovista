"""
Correction CLI commands for chronovista.

Commands for batch transcript correction tools including find-replace,
rebuild, export, statistics, pattern discovery, and batch revert operations.

Feature 036 — Batch Correction Tools (T012–T016)
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import datetime
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from chronovista.config.database import db_manager
from chronovista.models.batch_correction_models import BatchCorrectionResult
from chronovista.models.enums import CorrectionType
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)
from chronovista.services.batch_correction_service import BatchCorrectionService
from chronovista.services.transcript_correction_service import (
    TranscriptCorrectionService,
)

logger = logging.getLogger(__name__)

console = Console()
correction_app = typer.Typer(
    name="corrections",
    help="Batch transcript correction tools",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate_with_context(text: str, pattern: str, max_len: int = 80) -> str:
    """
    Truncate *text* to *max_len* chars, centred on the first occurrence of
    *pattern*.  The matched substring is wrapped in Rich ``[bold]...[/bold]``
    markup.  Surrounding context is padded with ``...`` when truncated.

    Parameters
    ----------
    text : str
        Full segment text.
    pattern : str
        Substring to highlight (plain text, not regex).
    max_len : int
        Maximum display width (default 80).

    Returns
    -------
    str
        Truncated string with Rich bold markup around the match.
    """
    idx = text.lower().find(pattern.lower())
    if idx == -1:
        # Fallback: just end-truncate
        return _truncate_end(text, max_len)

    match_text = text[idx : idx + len(pattern)]
    bold_match = f"[bold]{match_text}[/bold]"

    # Budget for context around the match (subtract markup-free match length)
    remaining = max_len - len(pattern)
    left_budget = remaining // 2
    right_budget = remaining - left_budget

    start = max(0, idx - left_budget)
    end = min(len(text), idx + len(pattern) + right_budget)

    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""

    before = text[start:idx]
    after = text[idx + len(pattern) : end]

    return f"{prefix}{before}{bold_match}{after}{suffix}"


def _truncate_end(text: str, max_len: int = 80) -> str:
    """
    End-truncate *text* to *max_len* characters, adding trailing ``...`` if
    the string was shortened.

    Parameters
    ----------
    text : str
        Text to truncate.
    max_len : int
        Maximum display width (default 80).

    Returns
    -------
    str
        Truncated string.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _parse_correction_type(value: str) -> CorrectionType:
    """
    Parse a string into a ``CorrectionType`` enum member.

    Parameters
    ----------
    value : str
        Raw string value (e.g. ``"asr_error"``, ``"spelling"``).

    Returns
    -------
    CorrectionType
        The corresponding enum member.

    Raises
    ------
    typer.BadParameter
        If *value* does not match any ``CorrectionType`` member.
    """
    try:
        return CorrectionType(value)
    except ValueError:
        valid = ", ".join(ct.value for ct in CorrectionType)
        raise typer.BadParameter(
            f"Invalid correction type '{value}'. Valid types: {valid}"
        )


def _create_batch_correction_service() -> BatchCorrectionService:
    """
    Instantiate a ``BatchCorrectionService`` with all required
    sub-services and repositories.

    Returns
    -------
    BatchCorrectionService
        Ready-to-use service instance.
    """
    segment_repo = TranscriptSegmentRepository()
    correction_repo = TranscriptCorrectionRepository()
    transcript_repo = VideoTranscriptRepository()

    correction_service = TranscriptCorrectionService(
        correction_repo=correction_repo,
        segment_repo=segment_repo,
        transcript_repo=transcript_repo,
    )

    return BatchCorrectionService(
        correction_service=correction_service,
        segment_repo=segment_repo,
        correction_repo=correction_repo,
    )


# ---------------------------------------------------------------------------
# find-replace command  (T012–T015)
# ---------------------------------------------------------------------------


@correction_app.command("find-replace")
def find_replace(
    pattern: str = typer.Option(
        ..., "--pattern", help="Text pattern to find"
    ),
    replacement: str = typer.Option(
        ..., "--replacement", help="Replacement text"
    ),
    regex: bool = typer.Option(
        False, "--regex", help="Treat pattern as a regular expression"
    ),
    case_insensitive: bool = typer.Option(
        False, "--case-insensitive", "-i", help="Case-insensitive matching"
    ),
    language: Optional[str] = typer.Option(
        None, "--language", help="Filter by language code"
    ),
    channel: Optional[str] = typer.Option(
        None, "--channel", help="Filter by channel ID"
    ),
    video_id: Optional[List[str]] = typer.Option(
        None, "--video-id", help="Filter by video ID (repeatable)"
    ),
    correction_type: str = typer.Option(
        "asr_error", "--correction-type", help="Correction type value"
    ),
    correction_note: Optional[str] = typer.Option(
        None, "--correction-note", help="Note for audit records"
    ),
    batch_size: int = typer.Option(
        100, "--batch-size", help="Transaction batch size"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview without writing"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt"
    ),
    limit: int = typer.Option(
        50, "--limit", help="Max preview rows in dry-run mode"
    ),
) -> None:
    """Find and replace text patterns across transcript segments."""

    # Validate correction_type early
    ct = _parse_correction_type(correction_type)

    # Validate regex pattern early
    if regex:
        try:
            re.compile(pattern)
        except re.error as exc:
            console.print(f"[red]Invalid regex pattern: {exc}[/red]")
            raise typer.Exit(code=1)

    service = _create_batch_correction_service()

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            if dry_run:
                # ---- Dry-run mode (T013) ----
                previews = await service.find_and_replace(
                    session,
                    pattern=pattern,
                    replacement=replacement,
                    regex=regex,
                    case_insensitive=case_insensitive,
                    language=language,
                    channel=channel,
                    video_ids=video_id,
                    correction_type=ct,
                    correction_note=correction_note,
                    batch_size=batch_size,
                    dry_run=True,
                )

                # previews is list[tuple[str, int, float, str, str]]
                assert isinstance(previews, list)

                if not previews:
                    console.print(
                        "[yellow]No segments matched the pattern.[/yellow]"
                    )
                    raise typer.Exit(code=0)

                # Build Rich preview table
                preview_table = Table(
                    title="Dry-Run Preview",
                    show_header=True,
                    header_style="bold blue",
                )
                preview_table.add_column("video_id", style="dim", width=14)
                preview_table.add_column("segment_id", style="dim", width=12)
                preview_table.add_column("start_time", style="dim", width=10)
                preview_table.add_column("Current Text", style="cyan", width=40)
                preview_table.add_column("Proposed Text", style="green", width=40)

                display_pattern = pattern if not regex else pattern
                for row in previews[:limit]:
                    vid, seg_id, start, current, proposed = row
                    current_display = _truncate_with_context(
                        current, display_pattern, max_len=80
                    )
                    proposed_display = _truncate_end(proposed, max_len=80)
                    preview_table.add_row(
                        vid,
                        str(seg_id),
                        f"{start:.1f}",
                        current_display,
                        proposed_display,
                    )

                console.print(preview_table)

                unique_videos = len({r[0] for r in previews})
                console.print(
                    f"\nDry run complete: [bold]{len(previews)}[/bold] segments "
                    f"would be corrected across [bold]{unique_videos}[/bold] videos."
                )
                return

            # ---- Live mode: scan first for confirmation (T014) ----
            previews_for_count = await service.find_and_replace(
                session,
                pattern=pattern,
                replacement=replacement,
                regex=regex,
                case_insensitive=case_insensitive,
                language=language,
                channel=channel,
                video_ids=video_id,
                correction_type=ct,
                correction_note=correction_note,
                batch_size=batch_size,
                dry_run=True,
            )
            assert isinstance(previews_for_count, list)

            total_matches = len(previews_for_count)

            if total_matches == 0:
                console.print(
                    "[yellow]No segments matched the pattern.[/yellow]"
                )
                raise typer.Exit(code=0)

            unique_videos = len({r[0] for r in previews_for_count})

            # Show confirmation info
            console.print(f"\n[bold]Pattern:[/bold]      {pattern}")
            console.print(f"[bold]Replacement:[/bold]  {replacement}")
            console.print(f"[bold]Type:[/bold]         {ct.value}")
            filters: list[str] = []
            if language:
                filters.append(f"language={language}")
            if channel:
                filters.append(f"channel={channel}")
            if video_id:
                filters.append(f"video_ids={video_id}")
            if filters:
                console.print(
                    f"[bold]Filters:[/bold]      {', '.join(filters)}"
                )
            console.print()

            if not yes:
                confirmed = typer.confirm(
                    f"This will correct {total_matches} segments "
                    f"across {unique_videos} videos. Proceed?",
                    default=False,
                )
                if not confirmed:
                    console.print("[yellow]Cancelled.[/yellow]")
                    raise typer.Exit(code=0)

            # ---- Apply corrections with progress bar (T015) ----
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Applying corrections...", total=total_matches
                )

                def _advance(n: int) -> None:
                    progress.advance(task, advance=n)

                result = await service.find_and_replace(
                    session,
                    pattern=pattern,
                    replacement=replacement,
                    regex=regex,
                    case_insensitive=case_insensitive,
                    language=language,
                    channel=channel,
                    video_ids=video_id,
                    correction_type=ct,
                    correction_note=correction_note,
                    batch_size=batch_size,
                    dry_run=False,
                    progress_callback=_advance,
                )

            assert isinstance(result, BatchCorrectionResult)

            # ---- Summary table (T015) ----
            summary_table = Table(
                title="Find-Replace Results",
                show_header=True,
                header_style="bold blue",
            )
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Count", style="green")

            summary_table.add_row(
                "Segments scanned", f"{result.total_scanned:,}"
            )
            summary_table.add_row(
                "Matches found", f"{result.total_matched:,}"
            )
            summary_table.add_row(
                "Corrections applied", f"{result.total_applied:,}"
            )
            summary_table.add_row(
                "Skipped (no-op)", f"{result.total_skipped:,}"
            )
            summary_table.add_row("Failed", f"{result.total_failed:,}")
            summary_table.add_row(
                "Unique videos", f"{result.unique_videos:,}"
            )

            if result.failed_batches > 0:
                summary_table.add_row(
                    "Failed batches", f"{result.failed_batches:,}"
                )

            console.print(summary_table)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# rebuild-text command  (T018)
# ---------------------------------------------------------------------------


@correction_app.command("rebuild-text")
def rebuild_text(
    video_id: Optional[List[str]] = typer.Option(
        None, "--video-id", help="Filter by video ID (repeatable)"
    ),
    language: Optional[str] = typer.Option(
        None, "--language", help="Filter by language code"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview without writing"
    ),
) -> None:
    """Rebuild full transcript text from corrected segments."""
    service = _create_batch_correction_service()

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            if dry_run:
                previews = await service.rebuild_text(
                    session,
                    video_ids=video_id,
                    language=language,
                    dry_run=True,
                )
                assert isinstance(previews, list)

                if not previews:
                    console.print(
                        "[yellow]No transcripts with corrections found.[/yellow]"
                    )
                    raise typer.Exit(code=0)

                preview_table = Table(
                    title="Rebuild Preview",
                    show_header=True,
                    header_style="bold blue",
                )
                preview_table.add_column("video_id", style="dim", width=14)
                preview_table.add_column("language_code", style="dim", width=12)
                preview_table.add_column("Current Length", style="cyan", width=14)
                preview_table.add_column("New Length", style="green", width=14)

                for row in previews:
                    preview_table.add_row(
                        row["video_id"],
                        row["language_code"],
                        f"{row['current_length']:,}",
                        f"{row['new_length']:,}",
                    )

                console.print(preview_table)
                console.print(
                    f"\nDry run complete: [bold]{len(previews)}[/bold] "
                    f"transcripts would be rebuilt"
                )
                return

            # ---- Live mode ----
            # First do a dry-run to get the count for the progress bar
            previews_for_count = await service.rebuild_text(
                session,
                video_ids=video_id,
                language=language,
                dry_run=True,
            )
            assert isinstance(previews_for_count, list)
            total = len(previews_for_count)

            if total == 0:
                console.print(
                    "[yellow]No transcripts with corrections found.[/yellow]"
                )
                raise typer.Exit(code=0)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Rebuilding transcripts...", total=total
                )

                def _advance(n: int) -> None:
                    progress.advance(task, advance=n)

                result = await service.rebuild_text(
                    session,
                    video_ids=video_id,
                    language=language,
                    dry_run=False,
                    progress_callback=_advance,
                )

            assert isinstance(result, tuple)
            rebuilt, segments = result

            console.print(
                f"\nRebuilt [bold]{rebuilt:,}[/bold] transcripts "
                f"([bold]{segments:,}[/bold] segments processed)"
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# export command  (T020)
# ---------------------------------------------------------------------------


@correction_app.command("export")
def export_corrections(
    format: str = typer.Option(
        ..., "--format", help="Output format: csv or json"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", help="Output file path (stdout if omitted)"
    ),
    video_id: Optional[List[str]] = typer.Option(
        None, "--video-id", help="Filter by video ID (repeatable)"
    ),
    correction_type: Optional[str] = typer.Option(
        None, "--correction-type", help="Filter by correction type"
    ),
    since: Optional[str] = typer.Option(
        None, "--since", help="Inclusive lower bound (ISO 8601)"
    ),
    until: Optional[str] = typer.Option(
        None, "--until", help="Inclusive upper bound (ISO 8601)"
    ),
    compact: bool = typer.Option(
        False, "--compact", help="Compact JSON output (no indentation)"
    ),
) -> None:
    """Export correction audit records as CSV or JSON."""
    # Validate format
    if format not in ("csv", "json"):
        console.print(
            f"[red]Invalid format '{format}'. Must be 'csv' or 'json'.[/red]"
        )
        raise typer.Exit(code=1)

    # Parse correction_type if provided
    ct: CorrectionType | None = None
    if correction_type is not None:
        ct = _parse_correction_type(correction_type)

    # Parse date filters
    since_dt: datetime | None = None
    until_dt: datetime | None = None
    if since is not None:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            console.print(
                f"[red]Invalid --since date: '{since}'. Use ISO 8601 format.[/red]"
            )
            raise typer.Exit(code=1)
    if until is not None:
        try:
            until_dt = datetime.fromisoformat(until)
        except ValueError:
            console.print(
                f"[red]Invalid --until date: '{until}'. Use ISO 8601 format.[/red]"
            )
            raise typer.Exit(code=1)

    # Validate since < until
    if since_dt is not None and until_dt is not None and since_dt >= until_dt:
        console.print(
            "[red]--since must be earlier than --until.[/red]"
        )
        raise typer.Exit(code=1)

    service = _create_batch_correction_service()

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Exporting corrections...", total=None)

                count, data_string = await service.export_corrections(
                    session,
                    video_ids=video_id,
                    correction_type=ct,
                    since=since_dt,
                    until=until_dt,
                    compact=compact,
                    format=format,
                )

            if output:
                with open(output, "w", encoding="utf-8") as f:
                    f.write(data_string)
            else:
                sys.stdout.write(data_string)

            stderr_console = Console(stderr=True)
            stderr_console.print(
                f"\nExported [bold]{count:,}[/bold] correction records"
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# stats command  (T022)
# ---------------------------------------------------------------------------


@correction_app.command("stats")
def stats(
    language: Optional[str] = typer.Option(
        None, "--language", help="Filter by language code"
    ),
    top: int = typer.Option(
        10, "--top", help="Number of top videos to display"
    ),
) -> None:
    """Display aggregate correction statistics."""
    service = _create_batch_correction_service()

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            result = await service.get_statistics(
                session,
                language=language,
                top=top,
            )

            # Build summary panel content
            summary_lines = [
                f"Total corrections (excl. reverts): [bold]{result.total_corrections:,}[/bold]",
                f"Total reverts: [bold]{result.total_reverts:,}[/bold]",
                f"Unique segments: [bold]{result.unique_segments:,}[/bold]",
                f"Unique videos: [bold]{result.unique_videos:,}[/bold]",
            ]
            console.print(
                Panel(
                    "\n".join(summary_lines),
                    title="Correction Statistics",
                    border_style="blue",
                )
            )

            # Type breakdown table
            if result.by_type:
                type_table = Table(
                    title="Corrections by Type",
                    show_header=True,
                    header_style="bold blue",
                )
                type_table.add_column("Correction Type", style="cyan")
                type_table.add_column("Count", style="green")

                for entry in result.by_type:
                    type_table.add_row(
                        entry.correction_type, f"{entry.count:,}"
                    )

                console.print(type_table)

            # Top videos table
            if result.top_videos:
                video_table = Table(
                    title=f"Top {top} Most-Corrected Videos",
                    show_header=True,
                    header_style="bold blue",
                )
                video_table.add_column("video_id", style="dim", width=14)
                video_table.add_column("Title", style="cyan", width=50)
                video_table.add_column("Count", style="green")

                for video_entry in result.top_videos:
                    video_table.add_row(
                        video_entry.video_id,
                        video_entry.title or "(no title)",
                        f"{video_entry.count:,}",
                    )

                console.print(video_table)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# patterns command  (T024)
# ---------------------------------------------------------------------------


@correction_app.command("patterns")
def patterns(
    min_occurrences: int = typer.Option(
        2, "--min-occurrences", help="Minimum occurrences to include"
    ),
    limit: int = typer.Option(
        25, "--limit", help="Maximum patterns to return"
    ),
    show_completed: bool = typer.Option(
        False, "--show-completed", help="Include patterns with zero remaining matches"
    ),
) -> None:
    """Discover recurring correction patterns."""
    service = _create_batch_correction_service()

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            result = await service.get_patterns(
                session,
                min_occurrences=min_occurrences,
                limit=limit,
                show_completed=show_completed,
            )

            if not result:
                console.print(
                    "[yellow]No recurring correction patterns found[/yellow]"
                )
                raise typer.Exit(code=0)

            pattern_table = Table(
                title="Correction Patterns",
                show_header=True,
                header_style="bold blue",
            )
            pattern_table.add_column("Original Text", style="cyan", width=30)
            pattern_table.add_column("Corrected Text", style="green", width=30)
            pattern_table.add_column("Occurrences", style="dim", width=12)
            pattern_table.add_column("Remaining", style="dim", width=12)
            pattern_table.add_column("Suggested Command", style="dim")

            for p in result:
                suggested = (
                    f'corrections find-replace --pattern "{p.original_text}" '
                    f'--replacement "{p.corrected_text}"'
                )
                pattern_table.add_row(
                    _truncate_end(p.original_text, 80),
                    _truncate_end(p.corrected_text, 80),
                    f"{p.occurrences:,}",
                    f"{p.remaining_matches:,}",
                    suggested,
                )

            console.print(pattern_table)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# batch-revert command  (T026)
# ---------------------------------------------------------------------------


@correction_app.command("batch-revert")
def batch_revert(
    pattern: str = typer.Option(
        ..., "--pattern", help="Text pattern to match for revert"
    ),
    video_id: Optional[List[str]] = typer.Option(
        None, "--video-id", help="Filter by video ID (repeatable)"
    ),
    language: Optional[str] = typer.Option(
        None, "--language", help="Filter by language code"
    ),
    regex: bool = typer.Option(
        False, "--regex", help="Treat pattern as a regular expression"
    ),
    case_insensitive: bool = typer.Option(
        False, "--case-insensitive", "-i", help="Case-insensitive matching"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview without writing"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt"
    ),
    batch_size: int = typer.Option(
        100, "--batch-size", help="Transaction batch size"
    ),
) -> None:
    """Revert corrections matching a pattern."""
    # Validate regex pattern early
    if regex:
        try:
            re.compile(pattern)
        except re.error as exc:
            console.print(f"[red]Invalid regex pattern: {exc}[/red]")
            raise typer.Exit(code=1)

    service = _create_batch_correction_service()

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            if dry_run:
                previews = await service.batch_revert(
                    session,
                    pattern=pattern,
                    regex=regex,
                    case_insensitive=case_insensitive,
                    language=language,
                    video_ids=video_id,
                    batch_size=batch_size,
                    dry_run=True,
                )
                assert isinstance(previews, list)

                if not previews:
                    console.print(
                        "[yellow]No corrected segments matched the pattern[/yellow]"
                    )
                    raise typer.Exit(code=0)

                preview_table = Table(
                    title="Batch Revert Preview",
                    show_header=True,
                    header_style="bold blue",
                )
                preview_table.add_column("video_id", style="dim", width=14)
                preview_table.add_column("segment_id", style="dim", width=12)
                preview_table.add_column("start_time", style="dim", width=10)
                preview_table.add_column("Corrected Text", style="cyan", width=40)

                for vid, seg_id, start, corrected in previews:
                    preview_table.add_row(
                        vid,
                        str(seg_id),
                        f"{start:.1f}",
                        _truncate_end(corrected, 80),
                    )

                console.print(preview_table)

                unique_videos = len({r[0] for r in previews})
                console.print(
                    f"\nDry run complete: [bold]{len(previews)}[/bold] segments "
                    f"would be reverted across [bold]{unique_videos}[/bold] videos."
                )
                return

            # ---- Live mode: scan first for confirmation ----
            previews_for_count = await service.batch_revert(
                session,
                pattern=pattern,
                regex=regex,
                case_insensitive=case_insensitive,
                language=language,
                video_ids=video_id,
                batch_size=batch_size,
                dry_run=True,
            )
            assert isinstance(previews_for_count, list)

            total_matches = len(previews_for_count)

            if total_matches == 0:
                console.print(
                    "[yellow]No corrected segments matched the pattern[/yellow]"
                )
                raise typer.Exit(code=0)

            unique_videos = len({r[0] for r in previews_for_count})

            if not yes:
                confirmed = typer.confirm(
                    f"This will revert {total_matches} corrections "
                    f"across {unique_videos} videos. Proceed?",
                    default=False,
                )
                if not confirmed:
                    console.print("[yellow]Cancelled.[/yellow]")
                    raise typer.Exit(code=0)

            # ---- Apply reverts with progress bar ----
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Reverting corrections...", total=total_matches
                )

                def _advance(n: int) -> None:
                    progress.advance(task, advance=n)

                result = await service.batch_revert(
                    session,
                    pattern=pattern,
                    regex=regex,
                    case_insensitive=case_insensitive,
                    language=language,
                    video_ids=video_id,
                    batch_size=batch_size,
                    dry_run=False,
                    progress_callback=_advance,
                )

            assert isinstance(result, BatchCorrectionResult)

            # ---- Summary table ----
            summary_table = Table(
                title="Batch Revert Results",
                show_header=True,
                header_style="bold blue",
            )
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Count", style="green")

            summary_table.add_row(
                "Segments scanned", f"{result.total_scanned:,}"
            )
            summary_table.add_row(
                "Matches found", f"{result.total_matched:,}"
            )
            summary_table.add_row(
                "Reverted", f"{result.total_applied:,}"
            )
            summary_table.add_row(
                "Skipped", f"{result.total_skipped:,}"
            )
            summary_table.add_row("Failed", f"{result.total_failed:,}")
            summary_table.add_row(
                "Unique videos", f"{result.unique_videos:,}"
            )

            if result.failed_batches > 0:
                summary_table.add_row(
                    "Failed batches", f"{result.failed_batches:,}"
                )

            console.print(summary_table)

    asyncio.run(_run())
