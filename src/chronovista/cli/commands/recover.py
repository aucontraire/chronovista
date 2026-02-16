"""
CLI commands for recovering deleted video metadata via Wayback Machine.

This module provides the `chronovista recover video` command for recovering
metadata from deleted YouTube videos using the Internet Archive's Wayback Machine.

Supports single-video recovery, batch recovery with configurable limits and delays,
dry-run mode for preview, and detailed summary reports.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from chronovista.config.database import db_manager
from chronovista.config.settings import settings
from chronovista.exceptions import (
    CDXError,
    EXIT_CODE_NETWORK_ERROR,
    PageParseError,
    RecoveryDependencyError,
)
from chronovista.models.enums import AvailabilityStatus
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.recovery import SELENIUM_AVAILABLE
from chronovista.services.recovery.cdx_client import CDXClient, RateLimiter
from chronovista.services.recovery.models import RecoveryResult
from chronovista.services.recovery.orchestrator import recover_video
from chronovista.services.recovery.page_parser import PageParser

# Check for required dependencies
try:
    import bs4  # noqa: F401

    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False

console = Console()

# Create the recover Typer app
recover_app = typer.Typer(
    name="recover",
    help="Recover metadata for deleted videos",
    no_args_is_help=True,
)


@recover_app.command(name="video")
def recover_video_command(
    video_id: Optional[str] = typer.Option(
        None,
        "--video-id",
        "-v",
        help="Recover a single video by ID",
    ),
    all_videos: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Recover all unavailable videos",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of videos to recover (batch mode only)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview recovery without making changes",
    ),
    delay: float = typer.Option(
        1.0,
        "--delay",
        "-d",
        help="Delay in seconds between videos (batch mode only)",
        min=0.0,
    ),
    start_year: Optional[int] = typer.Option(
        None,
        "--start-year",
        help="Only search Wayback snapshots from this year onward (e.g., 2018).",
        min=2005,
        max=2026,
    ),
    end_year: Optional[int] = typer.Option(
        None,
        "--end-year",
        help="Only search Wayback snapshots up to this year (e.g., 2020).",
        min=2005,
        max=2026,
    ),
) -> None:
    """
    Recover metadata for deleted YouTube videos via Wayback Machine.

    Recovers video metadata (title, description, tags, etc.) from archived
    YouTube pages in the Internet Archive. Supports both single-video and
    batch recovery modes with configurable rate limiting.

    Examples:
        chronovista recover video --video-id dQw4w9WgXcQ
        chronovista recover video --all --limit 10
        chronovista recover video --all --dry-run
        chronovista recover video --all --delay 2.0
    """
    # T050: Validate arguments
    if video_id and all_videos:
        console.print(
            "[red]Error: --video-id and --all are mutually exclusive[/red]"
        )
        raise typer.Exit(code=2)

    if not video_id and not all_videos:
        console.print(
            "[yellow]Error: Must specify either --video-id or --all[/yellow]"
        )
        console.print("Use 'chronovista recover video --help' for usage information.")
        raise typer.Exit(code=2)

    if start_year is not None and end_year is not None and start_year > end_year:
        console.print(
            "[red]Error: --start-year cannot be greater than --end-year[/red]"
        )
        raise typer.Exit(code=2)

    # T056: Check dependencies
    if not BEAUTIFULSOUP_AVAILABLE:
        console.print(
            Panel(
                "[red]Error: beautifulsoup4 is required for video recovery[/red]\n\n"
                "Install with: pip install beautifulsoup4",
                title="Missing Dependency",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    if not SELENIUM_AVAILABLE:
        console.print(
            "[yellow]Warning: selenium is not installed. Pre-2017 page fallback disabled.[/yellow]"
        )

    # Run async recovery
    try:
        asyncio.run(_recover_async(video_id, all_videos, limit, dry_run, delay, start_year, end_year))
    except KeyboardInterrupt:
        console.print("\n[yellow]Recovery interrupted by user[/yellow]")
        raise typer.Exit(code=130)


async def _recover_async(
    video_id: Optional[str],
    all_videos: bool,
    limit: Optional[int],
    dry_run: bool,
    delay: float,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> None:
    """
    Async implementation of video recovery.

    Parameters
    ----------
    video_id : str | None
        Single video ID to recover, or None for batch mode.
    all_videos : bool
        Whether to recover all unavailable videos (batch mode).
    limit : int | None
        Maximum number of videos to recover in batch mode.
    dry_run : bool
        If True, preview recovery without making changes.
    delay : float
        Delay in seconds between videos in batch mode.
    start_year : int | None, optional
        Only search Wayback snapshots from this year onward (default: None).
    end_year : int | None, optional
        Only search Wayback snapshots up to this year (default: None).
    """
    # T050: Initialize services
    cache_dir = settings.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    cdx_client = CDXClient(cache_dir=cache_dir)
    rate_limiter = RateLimiter(rate=40.0)
    page_parser = PageParser(rate_limiter=rate_limiter)

    if video_id:
        # T052: Single-video recovery
        await _recover_single_video(
            video_id=video_id,
            cdx_client=cdx_client,
            page_parser=page_parser,
            rate_limiter=rate_limiter,
            dry_run=dry_run,
            start_year=start_year,
            end_year=end_year,
        )
    else:
        # T053: Batch recovery
        await _recover_batch(
            cdx_client=cdx_client,
            page_parser=page_parser,
            rate_limiter=rate_limiter,
            limit=limit,
            dry_run=dry_run,
            delay=delay,
            start_year=start_year,
            end_year=end_year,
        )


async def _recover_single_video(
    video_id: str,
    cdx_client: CDXClient,
    page_parser: PageParser,
    rate_limiter: RateLimiter,
    dry_run: bool,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> None:
    """
    Recover a single video by ID.

    Parameters
    ----------
    video_id : str
        YouTube video ID to recover.
    cdx_client : CDXClient
        CDX API client for fetching snapshots.
    page_parser : PageParser
        Page parser for extracting metadata.
    rate_limiter : RateLimiter
        Rate limiter for throttling requests.
    dry_run : bool
        If True, preview recovery without making changes.
    start_year : int | None, optional
        Only search Wayback snapshots from this year onward (default: None).
    end_year : int | None, optional
        Only search Wayback snapshots up to this year (default: None).
    """
    # T052: Show progress spinner
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Recovering video {video_id}...",
            total=None,
        )

        exit_code = 1
        try:
            async for session in db_manager.get_session(echo=False):
                result = await recover_video(
                    session=session,
                    video_id=video_id,
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=dry_run,
                    from_year=start_year,
                    to_year=end_year,
                )

                progress.update(task, completed=True)

                # T052: Display result
                _display_single_result(result, dry_run)

                # T052: Exit codes
                exit_code = 0 if result.success else 1

        except CDXError as e:
            console.print(f"[red]CDX API error: {e.message}[/red]")
            raise typer.Exit(code=EXIT_CODE_NETWORK_ERROR)
        except PageParseError as e:
            console.print(f"[red]Page parsing error: {e.message}[/red]")
            raise typer.Exit(code=1)

    raise typer.Exit(code=exit_code)


async def _recover_batch(
    cdx_client: CDXClient,
    page_parser: PageParser,
    rate_limiter: RateLimiter,
    limit: Optional[int],
    dry_run: bool,
    delay: float,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> None:
    """
    Recover all unavailable videos in batch mode.

    Parameters
    ----------
    cdx_client : CDXClient
        CDX API client for fetching snapshots.
    page_parser : PageParser
        Page parser for extracting metadata.
    rate_limiter : RateLimiter
        Rate limiter for throttling requests.
    limit : int | None
        Maximum number of videos to recover.
    dry_run : bool
        If True, preview recovery without making changes.
    delay : float
        Delay in seconds between videos.
    start_year : int | None, optional
        Only search Wayback snapshots from this year onward (default: None).
    end_year : int | None, optional
        Only search Wayback snapshots up to this year (default: None).
    """
    # T053: Query unavailable videos
    video_repo = VideoRepository()

    exit_code = 1
    async for session in db_manager.get_session(echo=False):
        # Query unavailable videos (ordered by unavailability_first_detected ASC NULLS LAST, then created_at ASC)
        from sqlalchemy import asc, select
        from chronovista.db.models import Video as VideoDB

        stmt = (
            select(VideoDB)
            .where(VideoDB.availability_status != AvailabilityStatus.AVAILABLE.value)
            .order_by(
                asc(VideoDB.unavailability_first_detected.is_(None)),
                asc(VideoDB.unavailability_first_detected),
                asc(VideoDB.created_at),
            )
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        videos = list(result.scalars().all())

        # T053: Handle zero videos
        if not videos:
            console.print(
                Panel(
                    "[yellow]No unavailable videos found in the database.[/yellow]",
                    title="Batch Recovery",
                    border_style="yellow",
                )
            )
            exit_code = 0
            break

        console.print(
            Panel(
                f"[cyan]Found {len(videos)} unavailable video(s) to recover[/cyan]",
                title="Batch Recovery",
                border_style="cyan",
            )
        )

        # T053: Process videos with delay
        results: list[RecoveryResult] = []

        for i, video in enumerate(videos):
            try:
                recovery_result = await recover_video(
                    session=session,
                    video_id=video.video_id,
                    cdx_client=cdx_client,
                    page_parser=page_parser,
                    rate_limiter=rate_limiter,
                    dry_run=dry_run,
                    from_year=start_year,
                    to_year=end_year,
                )
                results.append(recovery_result)

                # Show progress
                console.print(
                    f"[dim]Progress: {i + 1}/{len(videos)} - "
                    f"{'✓' if recovery_result.success else '✗'} {video.video_id}[/dim]"
                )

                # T053: Apply delay between videos (except after last video)
                if i < len(videos) - 1 and delay > 0:
                    await asyncio.sleep(delay)

            except CDXError as e:
                console.print(
                    f"[red]CDX error for {video.video_id}: {e.message}[/red]"
                )
                # T053: Continue past failures
                results.append(
                    RecoveryResult(
                        video_id=video.video_id,
                        success=False,
                        failure_reason="cdx_error",
                        duration_seconds=0.0,
                    )
                )
                continue
            except Exception as e:
                console.print(
                    f"[red]Unexpected error for {video.video_id}: {e}[/red]"
                )
                results.append(
                    RecoveryResult(
                        video_id=video.video_id,
                        success=False,
                        failure_reason="unexpected_error",
                        duration_seconds=0.0,
                    )
                )
                continue

        # T055: Display summary report
        _display_batch_summary(results, dry_run)

        # Exit based on results
        success_count = sum(1 for r in results if r.success)
        exit_code = 0 if success_count > 0 else 1

    raise typer.Exit(code=exit_code)


def _display_single_result(result: RecoveryResult, dry_run: bool) -> None:
    """
    Display single-video recovery result.

    Parameters
    ----------
    result : RecoveryResult
        Recovery result for a single video.
    dry_run : bool
        Whether this was a dry-run recovery.
    """
    # T052: Create result table
    table = Table(title=f"Recovery Result: {result.video_id}")

    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green" if result.success else "red")

    table.add_row("Status", "✓ Success" if result.success else "✗ Failed")

    if result.success:
        table.add_row("Snapshot Used", result.snapshot_used or "N/A")
        table.add_row(
            "Fields Recovered",
            f"{len(result.fields_recovered)} ({', '.join(result.fields_recovered)})"
            if result.fields_recovered
            else "0",
        )
        if result.fields_skipped:
            table.add_row(
                "Fields Skipped",
                f"{len(result.fields_skipped)} ({', '.join(result.fields_skipped[:5])})",
            )
        table.add_row("Snapshots Available", str(result.snapshots_available))
        table.add_row("Snapshots Tried", str(result.snapshots_tried))
    else:
        table.add_row("Failure Reason", result.failure_reason or "Unknown")
        if result.snapshots_available > 0:
            table.add_row("Snapshots Available", str(result.snapshots_available))
            table.add_row("Snapshots Tried", str(result.snapshots_tried))

    table.add_row("Duration", f"{result.duration_seconds:.2f}s")

    if dry_run:
        table.add_row("Mode", "[yellow]DRY RUN - No changes made[/yellow]")

    console.print(table)


def _display_batch_summary(results: list[RecoveryResult], dry_run: bool) -> None:
    """
    Display batch recovery summary report.

    Parameters
    ----------
    results : list[RecoveryResult]
        List of recovery results for all processed videos.
    dry_run : bool
        Whether this was a dry-run recovery.
    """
    # T055: Calculate summary statistics
    total = len(results)
    succeeded = sum(1 for r in results if r.success)
    failed = total - succeeded
    no_archive = sum(
        1 for r in results if not r.success and r.failure_reason == "no_snapshots_found"
    )

    # T055: Summary panel
    summary_text = (
        f"[cyan]Attempted:[/cyan] {total}\n"
        f"[green]Succeeded:[/green] {succeeded}\n"
        f"[red]Failed:[/red] {failed}\n"
        f"[yellow]No Archive Found:[/yellow] {no_archive}"
    )

    if dry_run:
        summary_text += "\n\n[yellow]DRY RUN - No changes were made[/yellow]"

    console.print(
        Panel(
            summary_text,
            title="Batch Recovery Summary",
            border_style="cyan",
        )
    )

    # T055: Per-video results table
    table = Table(title="Per-Video Results")

    table.add_column("Video ID", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Fields Recovered", style="green")
    table.add_column("Snapshot Used", style="dim")

    for result in results:
        status = "✓ Success" if result.success else "✗ Failed"
        status_style = "[green]" if result.success else "[red]"

        fields_count = (
            str(len(result.fields_recovered)) if result.success else "-"
        )

        snapshot = result.snapshot_used if result.success else "-"

        table.add_row(
            result.video_id,
            f"{status_style}{status}[/]",
            fields_count,
            snapshot,
        )

    console.print(table)
