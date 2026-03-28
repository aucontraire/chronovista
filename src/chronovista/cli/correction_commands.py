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
import uuid
from datetime import datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from chronovista.config.database import db_manager
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.batch_correction_models import BatchCorrectionResult
from chronovista.models.enums import CorrectionType
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
)
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
from chronovista.services.phonetic_matcher import PhoneticMatcher
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
        Raw string value (e.g. ``"proper_noun"``, ``"spelling"``).

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
    except ValueError as err:
        valid = ", ".join(ct.value for ct in CorrectionType)
        raise typer.BadParameter(
            f"Invalid correction type '{value}'. Valid types: {valid}"
        ) from err


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
    language: str | None = typer.Option(
        None, "--language", help="Filter by language code"
    ),
    channel: str | None = typer.Option(
        None, "--channel", help="Filter by channel ID"
    ),
    video_id: list[str] | None = typer.Option(
        None, "--video-id", help="Filter by video ID (repeatable)"
    ),
    correction_type: str = typer.Option(
        "proper_noun", "--correction-type", help="Correction type value"
    ),
    correction_note: str | None = typer.Option(
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
    cross_segment: bool = typer.Option(
        False, "--cross-segment", help="Enable matching across adjacent segment pairs"
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
            raise typer.Exit(code=1) from exc

    service = _create_batch_correction_service()

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            # ---- T027: Unscoped cross-segment warning (FR-014) ----
            if cross_segment and not language and not channel and not video_id:
                segment_repo = TranscriptSegmentRepository()
                total_count = await segment_repo.count_filtered(session)
                if total_count > 5000 and not yes:
                    console.print(
                        f"[yellow]Warning: --cross-segment with no scope filter will load "
                        f"~{total_count:,} segments into memory.\n"
                        f"For large libraries this may be slow. Use --video-id, --language, "
                        f"or --channel to narrow the scope, or pass --yes to proceed.[/yellow]"
                    )
                    confirmed = typer.confirm("Continue?", default=False)
                    if not confirmed:
                        console.print("[yellow]Cancelled.[/yellow]")
                        raise typer.Exit(code=0)

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
                    cross_segment=cross_segment,
                )

                # previews is list[tuple[str, int, float, str, str]]
                assert isinstance(previews, list)

                if not previews:
                    console.print(
                        "[yellow]No segments matched the pattern.[/yellow]"
                    )
                    raise typer.Exit(code=0)

                # Build Rich preview table
                if cross_segment:
                    preview_table = Table(
                        title="Dry-Run Preview",
                        show_header=True,
                        header_style="bold blue",
                    )
                    preview_table.add_column("video_id", style="dim", width=14)
                    preview_table.add_column("segment_id", style="dim", width=12)
                    preview_table.add_column("start_time", style="dim", width=10)
                    preview_table.add_column("Type", style="dim", width=6)
                    preview_table.add_column("Current Text", style="cyan", width=40)
                    preview_table.add_column("Proposed Text", style="green", width=40)

                    # Detect cross-segment pairs by checking for consecutive
                    # segment_ids originating from the same video in sequence.
                    # The service returns rows sorted by video/start_time, and
                    # cross-segment pair rows share a common boundary marker stored
                    # in the tuple's 5th element (proposed text prefix "[cross-segment").
                    # We use a simpler heuristic: track which row indices form pairs
                    # by looking at consecutive rows from the same video where the
                    # proposed text of the first starts matching the combined text.
                    # Since the service does not currently annotate pair membership
                    # in the dry-run tuples, we identify pairs by consecutive rows
                    # from the same video with adjacent segment IDs.
                    pair_indices: set[int] = set()
                    for idx in range(len(previews) - 1):
                        curr_vid, curr_seg, _, curr_text, curr_proposed = previews[idx]
                        next_vid, next_seg, _, next_text, next_proposed = previews[idx + 1]
                        if curr_vid == next_vid and next_seg == curr_seg + 1:
                            pair_indices.add(idx)
                            pair_indices.add(idx + 1)

                    cross_pair_count = len(pair_indices) // 2

                    for idx, row in enumerate(previews[:limit]):
                        vid, seg_id, start, current, proposed = row
                        if idx in pair_indices:
                            # Determine if first or second in pair
                            is_first = idx not in {j + 1 for j in pair_indices if j < idx and j in pair_indices}
                            pair_marker = "\u2576\u2500\u2510" if is_first else "\u2576\u2500\u2518"
                            # Tail truncation for first; head truncation for second
                            if is_first:
                                current_display = _truncate_end(current, max_len=80)
                            else:
                                current_display = (
                                    "..." + current[-(80 - 3):] if len(current) > 80 else current
                                )
                            proposed_display = _truncate_end(proposed, max_len=80)
                        else:
                            pair_marker = ""
                            current_display = _truncate_with_context(
                                current, pattern if not regex else pattern, max_len=80
                            )
                            proposed_display = _truncate_end(proposed, max_len=80)

                        preview_table.add_row(
                            vid,
                            str(seg_id),
                            f"{start:.1f}",
                            pair_marker,
                            current_display,
                            proposed_display,
                        )

                    console.print(preview_table)

                    unique_videos = len({r[0] for r in previews})
                    console.print(
                        f"\nDry run complete: [bold]{len(previews)}[/bold] segments "
                        f"would be corrected across [bold]{unique_videos}[/bold] videos "
                        f"([bold]{cross_pair_count}[/bold] cross-segment pairs)."
                    )
                else:
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
                cross_segment=cross_segment,
            )
            assert isinstance(previews_for_count, list)

            total_matches = len(previews_for_count)

            if total_matches == 0:
                console.print(
                    "[yellow]No segments matched the pattern.[/yellow]"
                )
                raise typer.Exit(code=0)

            unique_videos = len({r[0] for r in previews_for_count})

            # Count cross-segment pairs for confirmation message
            cross_pair_count = 0
            if cross_segment:
                for idx in range(len(previews_for_count) - 1):
                    curr_vid, curr_seg = previews_for_count[idx][0], previews_for_count[idx][1]
                    next_vid, next_seg = previews_for_count[idx + 1][0], previews_for_count[idx + 1][1]
                    if curr_vid == next_vid and next_seg == curr_seg + 1:
                        cross_pair_count += 1

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
            if cross_segment:
                filters.append("cross-segment=enabled")
            if filters:
                console.print(
                    f"[bold]Filters:[/bold]      {', '.join(filters)}"
                )
            console.print()

            if not yes:
                if cross_segment:
                    confirm_msg = (
                        f"This will correct {total_matches} segments "
                        f"across {unique_videos} videos "
                        f"({cross_pair_count} cross-segment pairs). Proceed?"
                    )
                else:
                    confirm_msg = (
                        f"This will correct {total_matches} segments "
                        f"across {unique_videos} videos. Proceed?"
                    )
                confirmed = typer.confirm(confirm_msg, default=False)
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

                def _advance(n: int, _task: TaskID = task) -> None:
                    progress.advance(_task, advance=n)

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
                    cross_segment=cross_segment,
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

            # ---- T028: Empty segment warning after cross-segment correction ----
            if cross_segment and result.total_applied > 0:
                from sqlalchemy import or_
                from sqlalchemy import select as sa_select

                from chronovista.db.models import (
                    TranscriptSegment as TranscriptSegmentDB,
                )

                empty_stmt = sa_select(
                    TranscriptSegmentDB.id, TranscriptSegmentDB.video_id
                ).where(
                    TranscriptSegmentDB.has_correction.is_(True),
                    or_(
                        TranscriptSegmentDB.corrected_text.is_(None),
                        TranscriptSegmentDB.corrected_text == "",
                        TranscriptSegmentDB.corrected_text == " ",
                    ),
                )
                if video_id:
                    empty_stmt = empty_stmt.where(
                        TranscriptSegmentDB.video_id.in_(video_id)
                    )

                empty_result = await session.execute(empty_stmt)
                empty_segments = list(empty_result.all())

                if empty_segments:
                    seg_ids = [str(row.id) for row in empty_segments]
                    ids_display = ", ".join(seg_ids[:10])
                    suffix = "..." if len(seg_ids) > 10 else ""
                    console.print(
                        f"\n[yellow]Warning: {len(empty_segments)} segment(s) were left "
                        f"empty or whitespace-only after cross-segment correction: "
                        f"segment IDs {ids_display}{suffix}[/yellow]"
                    )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# rebuild-text command  (T018)
# ---------------------------------------------------------------------------


@correction_app.command("rebuild-text")
def rebuild_text(
    video_id: list[str] | None = typer.Option(
        None, "--video-id", help="Filter by video ID (repeatable)"
    ),
    language: str | None = typer.Option(
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

                def _advance(n: int, _task: TaskID = task) -> None:
                    progress.advance(_task, advance=n)

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
    output: str | None = typer.Option(
        None, "--output", help="Output file path (stdout if omitted)"
    ),
    video_id: list[str] | None = typer.Option(
        None, "--video-id", help="Filter by video ID (repeatable)"
    ),
    correction_type: str | None = typer.Option(
        None, "--correction-type", help="Filter by correction type"
    ),
    since: str | None = typer.Option(
        None, "--since", help="Inclusive lower bound (ISO 8601)"
    ),
    until: str | None = typer.Option(
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
        except ValueError as err:
            console.print(
                f"[red]Invalid --since date: '{since}'. Use ISO 8601 format.[/red]"
            )
            raise typer.Exit(code=1) from err
    if until is not None:
        try:
            until_dt = datetime.fromisoformat(until)
        except ValueError as err:
            console.print(
                f"[red]Invalid --until date: '{until}'. Use ISO 8601 format.[/red]"
            )
            raise typer.Exit(code=1) from err

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
    language: str | None = typer.Option(
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
    pattern: str | None = typer.Option(
        None,
        "--pattern",
        help=(
            "Text pattern to match corrected segments for revert. "
            "Mutually exclusive with --batch-id."
        ),
    ),
    batch_id_str: str | None = typer.Option(
        None,
        "--batch-id",
        help=(
            "UUID of a prior batch to revert entirely. "
            "Mutually exclusive with --pattern. "
            "Obtain batch IDs from 'corrections stats'."
        ),
    ),
    video_id: list[str] | None = typer.Option(
        None, "--video-id", help="Filter by video ID (repeatable; pattern mode only)"
    ),
    language: str | None = typer.Option(
        None, "--language", help="Filter by language code (pattern mode only)"
    ),
    regex: bool = typer.Option(
        False, "--regex", help="Treat --pattern as a regular expression (pattern mode only)"
    ),
    case_insensitive: bool = typer.Option(
        False, "--case-insensitive", "-i", help="Case-insensitive matching (pattern mode only)"
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
    """Revert corrections by pattern or by batch ID.

    Provide exactly one of --pattern or --batch-id:

    \b
      --pattern TEXT    Match corrected segments by text substring or regex.
      --batch-id UUID   Revert every correction that belongs to a prior batch.

    Examples:

    \b
      # Revert all corrections containing "gonna" in their corrected text
      chronovista corrections batch-revert --pattern "gonna"

    \b
      # Revert an entire batch by its UUID
      chronovista corrections batch-revert --batch-id 01932f4a-dead-7000-beef-000000000001

    \b
      # Dry-run a batch-id revert first
      chronovista corrections batch-revert --batch-id <uuid> --dry-run
    """
    # ---- Mutual exclusivity guard ----
    if pattern is not None and batch_id_str is not None:
        console.print(
            "[red]Error:[/red] --pattern and --batch-id are mutually exclusive. "
            "Provide exactly one."
        )
        raise typer.Exit(code=1)

    if pattern is None and batch_id_str is None:
        console.print(
            "[red]Error:[/red] One of --pattern or --batch-id is required."
        )
        raise typer.Exit(code=1)

    # ---- Resolve batch_id when provided ----
    batch_id: uuid.UUID | None = None
    if batch_id_str is not None:
        try:
            batch_id = uuid.UUID(batch_id_str)
        except ValueError:
            console.print(
                f"[red]Error:[/red] '{batch_id_str}' is not a valid UUID. "
                "Expected format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            )
            raise typer.Exit(code=1) from None

    # ---- Validate regex pattern early (pattern mode only) ----
    if pattern is not None and regex:
        try:
            re.compile(pattern)
        except re.error as exc:
            console.print(f"[red]Invalid regex pattern: {exc}[/red]")
            raise typer.Exit(code=1) from exc

    # Normalise: pattern must be a str for service calls in pattern mode
    effective_pattern: str = pattern or ""

    service = _create_batch_correction_service()

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            if dry_run:
                previews = await service.batch_revert(
                    session,
                    pattern=effective_pattern,
                    regex=regex,
                    case_insensitive=case_insensitive,
                    language=language,
                    video_ids=video_id,
                    batch_size=batch_size,
                    dry_run=True,
                    batch_id=batch_id,
                )
                assert isinstance(previews, list)

                if not previews:
                    if batch_id is not None:
                        console.print(
                            f"[yellow]No corrections found for batch {batch_id}[/yellow]"
                        )
                    else:
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
                preview_table.add_column("Note", style="dim", width=12)

                # T041: Count partner cascade segments
                partner_cascade_count = 0
                for row in previews:
                    # Previews are 5-tuples: (vid, seg_id, start, text, is_partner)
                    vid, seg_id, start, corrected = row[0], row[1], row[2], row[3]
                    is_partner = row[4] if len(row) > 4 else False
                    note_label = "(partner)" if is_partner else ""
                    if is_partner:
                        partner_cascade_count += 1
                    preview_table.add_row(
                        vid,
                        str(seg_id),
                        f"{start:.1f}",
                        _truncate_end(corrected, 80),
                        note_label,
                    )

                console.print(preview_table)

                unique_videos = len({r[0] for r in previews})
                if batch_id is not None:
                    console.print(
                        f"\nDry run complete: [bold]{len(previews)}[/bold] corrections "
                        f"from batch [bold]{batch_id}[/bold] would be reverted "
                        f"across [bold]{unique_videos}[/bold] videos."
                    )
                elif partner_cascade_count > 0:
                    console.print(
                        f"\nDry run complete: [bold]{len(previews)}[/bold] segments "
                        f"would be reverted across [bold]{unique_videos}[/bold] videos "
                        f"([bold]{partner_cascade_count}[/bold] via cross-segment "
                        f"partner cascade)."
                    )
                else:
                    console.print(
                        f"\nDry run complete: [bold]{len(previews)}[/bold] segments "
                        f"would be reverted across [bold]{unique_videos}[/bold] videos."
                    )
                return

            # ---- Live mode: scan first for confirmation ----
            previews_for_count = await service.batch_revert(
                session,
                pattern=effective_pattern,
                regex=regex,
                case_insensitive=case_insensitive,
                language=language,
                video_ids=video_id,
                batch_size=batch_size,
                dry_run=True,
                batch_id=batch_id,
            )
            assert isinstance(previews_for_count, list)

            total_matches = len(previews_for_count)

            if total_matches == 0:
                if batch_id is not None:
                    console.print(
                        f"[yellow]No corrections found for batch {batch_id}[/yellow]"
                    )
                else:
                    console.print(
                        "[yellow]No corrected segments matched the pattern[/yellow]"
                    )
                raise typer.Exit(code=0)

            unique_videos = len({r[0] for r in previews_for_count})

            if not yes:
                if batch_id is not None:
                    prompt = (
                        f"This will revert {total_matches} corrections "
                        f"from batch {batch_id} across {unique_videos} videos. Proceed?"
                    )
                else:
                    prompt = (
                        f"This will revert {total_matches} corrections "
                        f"across {unique_videos} videos. Proceed?"
                    )
                confirmed = typer.confirm(prompt, default=False)
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

                def _advance(n: int, _task: TaskID = task) -> None:
                    progress.advance(_task, advance=n)

                result = await service.batch_revert(
                    session,
                    pattern=effective_pattern,
                    regex=regex,
                    case_insensitive=case_insensitive,
                    language=language,
                    video_ids=video_id,
                    batch_size=batch_size,
                    dry_run=False,
                    progress_callback=_advance,
                    batch_id=batch_id,
                )

            assert isinstance(result, BatchCorrectionResult)

            # ---- Summary table ----
            title = (
                f"Batch Revert Results (batch {batch_id})"
                if batch_id is not None
                else "Batch Revert Results"
            )
            summary_table = Table(
                title=title,
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


# ---------------------------------------------------------------------------
# analyze-diffs command  (T023 — Feature 045)
# ---------------------------------------------------------------------------


@correction_app.command("analyze-diffs")
def analyze_diffs(
    limit: int = typer.Option(
        50, "--limit", help="Maximum rows to display"
    ),
    min_frequency: int = typer.Option(
        1, "--min-frequency", help="Minimum frequency to include"
    ),
) -> None:
    """Analyze word-level diffs across all corrections.

    Iterates all non-revert corrections, computes word-level diffs, and
    aggregates by (error_token, canonical_form) with frequency counts.
    Displays associated entities for each error token.
    """
    from collections import defaultdict

    from chronovista.services.asr_alias_registry import resolve_entity_id_from_text
    from chronovista.services.batch_correction_service import word_level_diff

    correction_repo = TranscriptCorrectionRepository()

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            # Fetch all non-revert corrections
            corrections = await correction_repo.get_all_filtered(session)

            # Filter out reverts and no-ops
            active_corrections = [
                c
                for c in corrections
                if c.correction_type != "revert"
                and c.correction_type != "revert_to_original"
                and c.correction_type != "revert_to_prior"
                and c.original_text != c.corrected_text
            ]

            if not active_corrections:
                console.print(
                    "[yellow]No corrections found to analyze[/yellow]"
                )
                raise typer.Exit(code=0)

            # Aggregate: (error_token, canonical_form) -> frequency
            pair_freq: dict[tuple[str, str], int] = defaultdict(int)
            # Track entity associations per error token
            token_entities: dict[str, set[str]] = defaultdict(set)

            for correction in active_corrections:
                diff = word_level_diff(
                    correction.original_text, correction.corrected_text
                )
                for error_token, canonical_token in diff.changed_pairs:
                    if not error_token or not canonical_token:
                        continue
                    pair_freq[(error_token, canonical_token)] += 1

                    # Try to resolve entity for the canonical token
                    match = await resolve_entity_id_from_text(
                        session, canonical_token
                    )
                    if match is not None:
                        _, entity_name = match
                        token_entities[error_token].add(entity_name)

            if not pair_freq:
                console.print(
                    "[yellow]No word-level differences found in corrections[/yellow]"
                )
                raise typer.Exit(code=0)

            # Sort by frequency descending
            sorted_pairs = sorted(
                pair_freq.items(), key=lambda x: x[1], reverse=True
            )

            # Apply min_frequency filter
            sorted_pairs = [
                (pair, freq)
                for pair, freq in sorted_pairs
                if freq >= min_frequency
            ]

            if not sorted_pairs:
                console.print(
                    f"[yellow]No word-level diffs with frequency >= {min_frequency}[/yellow]"
                )
                raise typer.Exit(code=0)

            # Limit output
            display_pairs = sorted_pairs[:limit]

            diff_table = Table(
                title="Word-Level Diff Analysis",
                show_header=True,
                header_style="bold blue",
            )
            diff_table.add_column("Error Token", style="red", width=25)
            diff_table.add_column("Canonical Form", style="green", width=25)
            diff_table.add_column("Frequency", style="dim", width=10)
            diff_table.add_column(
                "Associated Entities", style="cyan", width=40
            )

            for (error_token, canonical_token), freq in display_pairs:
                entities = token_entities.get(error_token, set())
                entities_str = ", ".join(sorted(entities)) if entities else "—"
                diff_table.add_row(
                    _truncate_end(error_token, 25),
                    _truncate_end(canonical_token, 25),
                    f"{freq:,}",
                    _truncate_end(entities_str, 40),
                )

            console.print(diff_table)

            # Summary
            total_unique = len(sorted_pairs)
            total_occurrences = sum(freq for _, freq in sorted_pairs)
            console.print(
                f"\n[bold]{total_unique:,}[/bold] unique error\u2192canonical pairs "
                f"([bold]{total_occurrences:,}[/bold] total occurrences) "
                f"from [bold]{len(active_corrections):,}[/bold] corrections analyzed."
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# detect-boundaries command  (T029 — US4)
# ---------------------------------------------------------------------------


@correction_app.command("detect-boundaries")
def detect_boundaries(
    entity: str | None = typer.Option(
        None,
        "--entity",
        help="Filter by entity canonical name (substring match, case-insensitive)",
    ),
    threshold: float = typer.Option(
        0.5,
        "--threshold",
        help="Minimum confidence score to include a match (0.0-1.0)",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        help="Maximum matches to display per entity",
    ),
) -> None:
    """Detect ASR error boundaries using phonetic matching against named entities.

    Scans transcript segments associated with each entity and identifies
    N-grams that phonetically resemble entity names or aliases, suggesting
    potential ASR transcription errors.

    \b
    Examples:
      chronovista corrections detect-boundaries
      chronovista corrections detect-boundaries --entity "Chomsky" --threshold 0.6
    """
    from sqlalchemy import func as sqla_func
    from sqlalchemy import select as sa_select

    entity_mention_repo = EntityMentionRepository()
    matcher = PhoneticMatcher(entity_mention_repo=entity_mention_repo)

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            # Load entities (optionally filtered by name)
            stmt = (
                sa_select(NamedEntityDB)
                .where(NamedEntityDB.status == "active")
                .order_by(NamedEntityDB.canonical_name)
            )
            if entity is not None:
                stmt = stmt.where(
                    sqla_func.lower(NamedEntityDB.canonical_name).contains(
                        entity.lower()
                    )
                )

            result = await session.execute(stmt)
            entities = list(result.scalars().all())

            if not entities:
                console.print(
                    "[yellow]No entities found matching the filter.[/yellow]"
                )
                raise typer.Exit(code=0)

            console.print(
                f"[blue]Scanning {len(entities)} entit{'y' if len(entities) == 1 else 'ies'} "
                f"with threshold {threshold}...[/blue]"
            )

            total_candidates = 0
            entities_skipped = 0

            for ent in entities:
                matches = await matcher.match_entity(
                    entity_id=ent.id,
                    session=session,
                    threshold=threshold,
                )

                if not matches:
                    entities_skipped += 1
                    continue

                # Limit displayed matches per entity
                displayed = matches[:limit]
                total_candidates += len(matches)

                # Build table for this entity
                match_table = Table(
                    title=(
                        f"Entity: {ent.canonical_name} ({ent.entity_type})"
                        f" -- {len(matches)} candidate(s)"
                    ),
                    show_header=True,
                    header_style="bold blue",
                )
                match_table.add_column("Original Text", style="cyan", width=30)
                match_table.add_column("Proposed Correction", style="green", width=25)
                match_table.add_column("Confidence", style="yellow", width=12)
                match_table.add_column("Evidence", style="dim", width=40)

                for m in displayed:
                    match_table.add_row(
                        _truncate_end(m.original_text, 30),
                        m.proposed_correction,
                        f"{m.confidence:.4f}",
                        _truncate_end(m.evidence_description, 40),
                    )

                console.print(match_table)

                if len(matches) > limit:
                    console.print(
                        f"  [dim]... and {len(matches) - limit} more matches"
                        f" (use --limit to show more)[/dim]"
                    )

            # Summary
            summary_lines = [
                f"Entities scanned: [bold]{len(entities)}[/bold]",
                f"Entities skipped (no associated videos): [bold]{entities_skipped}[/bold]",
                f"Total candidates found: [bold]{total_candidates:,}[/bold]",
            ]
            console.print(
                Panel(
                    "\n".join(summary_lines),
                    title="ASR Error Boundary Detection Summary",
                    border_style="blue",
                )
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# suggest-cross-segment command  (T034)
# ---------------------------------------------------------------------------


@correction_app.command("suggest-cross-segment")
def suggest_cross_segment(
    min_corrections: int = typer.Option(
        3,
        "--min-corrections",
        help="Minimum correction occurrences for a pattern to be considered",
    ),
    entity: str | None = typer.Option(
        None,
        "--entity",
        help="Filter by entity name (case-insensitive substring match)",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        help="Maximum candidates to display",
    ),
) -> None:
    """Discover cross-segment ASR error candidates from correction patterns.

    Analyses recurring correction patterns and finds adjacent segment pairs
    where an error form is split across the segment boundary. Candidates are
    scored and ranked by confidence.

    \b
    Examples:
      chronovista corrections suggest-cross-segment
      chronovista corrections suggest-cross-segment --min-corrections 5
      chronovista corrections suggest-cross-segment --entity "Chomsky"
    """
    from chronovista.services.cross_segment_discovery import (
        CrossSegmentDiscovery,
    )

    service = _create_batch_correction_service()
    discovery = CrossSegmentDiscovery(batch_service=service)

    async def _run() -> None:
        async for session in db_manager.get_session(echo=False):
            candidates = await discovery.discover(
                session,
                min_corrections=min_corrections,
                entity_name=entity,
            )

            if not candidates:
                console.print(
                    "[yellow]No cross-segment candidates found.[/yellow]"
                )
                if min_corrections > 2:
                    console.print(
                        f"[dim]Tip: Try lowering --min-corrections "
                        f"(currently {min_corrections}) to broaden the search.[/dim]"
                    )
                raise typer.Exit(code=0)

            displayed = candidates[:limit]

            candidate_table = Table(
                title=f"Cross-Segment Candidates ({len(candidates)} total)",
                show_header=True,
                header_style="bold blue",
            )
            candidate_table.add_column("Seg N", style="dim", width=8)
            candidate_table.add_column("Segment N Text", style="cyan", width=25)
            candidate_table.add_column("Seg N+1", style="dim", width=8)
            candidate_table.add_column("Segment N+1 Text", style="cyan", width=25)
            candidate_table.add_column("Source Pattern", style="red", width=20)
            candidate_table.add_column("Proposed Fix", style="green", width=20)
            candidate_table.add_column("Conf.", style="yellow", width=8)
            candidate_table.add_column("Flag", style="magenta", width=6)

            for c in displayed:
                flag = "PARTIAL" if c.is_partially_corrected else ""
                candidate_table.add_row(
                    str(c.segment_n_id),
                    _truncate_end(c.segment_n_text, 25),
                    str(c.segment_n1_id),
                    _truncate_end(c.segment_n1_text, 25),
                    _truncate_end(c.source_pattern, 20),
                    _truncate_end(c.proposed_correction, 20),
                    f"{c.confidence:.4f}",
                    flag,
                )

            console.print(candidate_table)

            if len(candidates) > limit:
                console.print(
                    f"  [dim]... and {len(candidates) - limit} more candidates"
                    f" (use --limit to show more)[/dim]"
                )

            # Summary panel
            partial_count = sum(
                1 for c in candidates if c.is_partially_corrected
            )
            unique_videos = len({c.video_id for c in candidates})
            summary_lines = [
                f"Total candidates: [bold]{len(candidates):,}[/bold]",
                f"Partially corrected: [bold]{partial_count:,}[/bold]",
                f"Unique videos: [bold]{unique_videos:,}[/bold]",
            ]
            console.print(
                Panel(
                    "\n".join(summary_lines),
                    title="Cross-Segment Discovery Summary",
                    border_style="blue",
                )
            )

    asyncio.run(_run())
