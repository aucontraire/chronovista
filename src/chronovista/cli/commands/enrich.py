"""
Enrich CLI commands for metadata enrichment from YouTube API.

This module provides CLI commands for enriching video metadata using
the YouTube Data API, including options for dry-run mode, limiting
the number of videos processed, and priority-based selection.

Supports generating detailed JSON reports of enrichment operations
and logging to file for auditing purposes.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table

from chronovista.exceptions import (
    EXIT_CODE_INTERRUPTED,
    EXIT_CODE_PREREQUISITES_MISSING,
    EXIT_CODE_QUOTA_EXCEEDED,
    AuthenticationError,
    GracefulShutdownException,
    NetworkError,
    PrerequisiteError,
    QuotaExceededException,
)
from chronovista.models.enrichment_report import EnrichmentReport
from chronovista.services.enrichment.enrichment_service import (
    BATCH_SIZE,
    EXIT_CODE_LOCK_FAILED,
    EXIT_CODE_NO_CREDENTIALS,
    ChannelEnrichmentResult,
    EnrichmentStatus,
    LockAcquisitionError,
    estimate_quota_cost,
)
from chronovista.services.enrichment.shutdown_handler import get_shutdown_handler

# Export symbols used by tests
__all__ = ["BATCH_SIZE", "estimate_quota_cost", "app"]

app = typer.Typer(help="Enrich video metadata from YouTube API")
console = Console()


# Valid priority levels
VALID_PRIORITIES = {"high", "medium", "low", "all"}

# Exit codes for enrichment
EXIT_CODE_SUCCESS = 0
EXIT_CODE_API_ERROR = 2
EXIT_CODE_NETWORK_ERROR = 3
EXIT_CODE_PARTIAL_SUCCESS = 4
EXIT_CODE_DATABASE_ERROR = 5


def validate_priority(value: str) -> str:
    """
    Validate priority value.

    Parameters
    ----------
    value : str
        Priority value to validate

    Returns
    -------
    str
        Validated lowercase priority value

    Raises
    ------
    typer.BadParameter
        If priority value is invalid
    """
    value_lower = value.lower()
    if value_lower not in VALID_PRIORITIES:
        raise typer.BadParameter(
            f"Invalid priority '{value}'. Must be one of: {', '.join(sorted(VALID_PRIORITIES))}"
        )
    return value_lower


def _generate_timestamp() -> str:
    """
    Generate timestamp string for file names.

    Returns
    -------
    str
        Timestamp in YYYYMMDD-HHMMSS format
    """
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _get_default_report_path() -> Path:
    """
    Get default path for enrichment report.

    Returns
    -------
    Path
        Default report path in ./exports/enrichment-{timestamp}.json format
    """
    timestamp = _generate_timestamp()
    return Path(f"./exports/enrichment-{timestamp}.json")


def _setup_enrichment_logging(
    timestamp: Optional[str] = None, verbose: bool = False
) -> Path:
    """
    Set up file logging for enrichment operation.

    Creates a log file at ./logs/enrichment-{timestamp}.log with INFO level
    logging. Creates the logs directory if it doesn't exist.

    Parameters
    ----------
    timestamp : str, optional
        Timestamp to use for log file name. If None, generates new timestamp.
    verbose : bool, optional
        If True, set logging level to DEBUG for detailed output (default False).

    Returns
    -------
    Path
        Path to the created log file
    """
    if timestamp is None:
        timestamp = _generate_timestamp()

    log_dir = Path("./logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"enrichment-{timestamp}.log"

    # T097: Set log level based on verbose flag
    log_level = logging.DEBUG if verbose else logging.INFO

    # Get the enrichment logger
    enrichment_logger = logging.getLogger("chronovista.services.enrichment")

    # Create file handler
    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(log_level)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    # Add handler to logger
    enrichment_logger.addHandler(file_handler)
    enrichment_logger.setLevel(log_level)

    # Also log to the root chronovista logger for broader coverage
    root_logger = logging.getLogger("chronovista")
    root_logger.addHandler(file_handler)
    root_logger.setLevel(log_level)

    # T097: If verbose, also add console handler for DEBUG output
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        enrichment_logger.addHandler(console_handler)
        root_logger.addHandler(console_handler)

    return log_file


def _save_report(report: "EnrichmentReport", output_path: Path) -> None:
    """
    Save enrichment report to JSON file.

    Creates parent directories if they don't exist.

    Parameters
    ----------
    report : EnrichmentReport
        The enrichment report to save
    output_path : Path
        Path to save the JSON report
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2))


@app.command("run")
def enrich_videos(
    limit: int = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of videos to process (default: all)",
    ),
    priority: str = typer.Option(
        "high",
        "--priority",
        "-p",
        help="Priority level: high, medium, low, all (default: high)",
        callback=validate_priority,
    ),
    include_deleted: bool = typer.Option(
        False,
        "--include-deleted",
        help="Include videos previously marked as deleted",
    ),
    include_playlists: bool = typer.Option(
        False,
        "--include-playlists",
        help="Also enrich playlist metadata from YouTube API",
    ),
    no_auto_resolve: bool = typer.Option(
        False,
        "--no-auto-resolve",
        help="[Deprecated] Auto-resolution removed. Playlists are linked from playlists.csv during seeding.",
        hidden=True,
    ),
    skip_unresolved: bool = typer.Option(
        False,
        "--skip-unresolved",
        help="[Deprecated] Auto-resolution removed. This flag no longer has any effect.",
        hidden=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Preview what would be enriched without making changes",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Override any existing enrichment lock",
    ),
    auto_seed: bool = typer.Option(
        False,
        "--auto-seed",
        help="Automatically seed topics and categories if missing (T096)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable detailed debug logging (T097)",
    ),
    refresh_topics: bool = typer.Option(
        False,
        "--refresh-topics",
        help="Re-enrich ALL videos to refresh topic associations (ignores priority filters)",
    ),
    sync_likes: bool = typer.Option(
        False,
        "--sync-likes",
        help="After enrichment, sync liked status for existing videos from YouTube API (~2 extra quota units)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save JSON report to file (default: ./exports/enrichment-{timestamp}.json)",
    ),
) -> None:
    """
    Enrich video metadata from YouTube Data API.

    Fetches current video metadata from YouTube and updates the local database.
    Videos are processed in batches of 50 (YouTube API limit) with automatic
    transaction management.

    Priority levels (cumulative):
    - high: Videos with placeholder titles AND placeholder channels
    - medium: high + any video with placeholder title
    - low: medium + any video with partial data
    - all: low + videos previously marked as deleted

    Exit codes:
    - 0: Success (all operations completed successfully)
    - 1: Ambiguous playlist matches detected (use --skip-unresolved or resolve manually)
    - 2: API error during playlist resolution (quota exhaustion or authentication)
    - 3: Network error during playlist resolution or video enrichment quota exceeded
    - 4: Partial success with --skip-unresolved or prerequisites missing
    - 5: Database error during playlist linking
    - 130: Interrupted by user (SIGINT/SIGTERM)

    Examples:
        chronovista enrich run
        chronovista enrich run --limit 100
        chronovista enrich run --priority medium --dry-run
        chronovista enrich run --include-deleted
        chronovista enrich run --include-playlists
        chronovista enrich run --include-playlists --no-auto-resolve
        chronovista enrich run --include-playlists --skip-unresolved
        chronovista enrich run --auto-seed
        chronovista enrich run --verbose
        chronovista enrich run --refresh-topics
        chronovista enrich run --sync-likes
        chronovista enrich run --output ./my-report.json
        chronovista enrich run -o ./exports/enrichment.json
    """
    import asyncio

    from chronovista.config.database import db_manager

    # Generate timestamp for consistent naming across log and report files
    timestamp = _generate_timestamp()

    # T097: Set up file logging for enrichment operations with verbose support
    log_file = _setup_enrichment_logging(timestamp, verbose=verbose)
    console.print(f"[dim]Logging to: {log_file}[/dim]")
    if verbose:
        console.print("[dim]Verbose logging enabled (DEBUG level)[/dim]")
    console.print()

    # Determine output path for JSON report (T056, T059)
    report_output_path: Optional[Path] = None
    if output is not None:
        # If output is specified as empty string or as flag without value,
        # use default path; otherwise use the provided path
        if str(output) == "" or str(output) == ".":
            report_output_path = _get_default_report_path()
        else:
            report_output_path = output

    async def run_enrichment() -> tuple[EnrichmentReport, bool]:
        # T093: Install shutdown handler for graceful shutdown
        shutdown = get_shutdown_handler()
        shutdown.install()

        try:
            return await _run_enrichment_inner()
        finally:
            # T093: Uninstall shutdown handler
            shutdown.uninstall()

    async def _run_enrichment_inner() -> tuple[EnrichmentReport, bool]:
        # Track partial success state for exit code (T055: Exit code 4 for partial success)
        has_partial_success = False

        # Check credentials first
        from chronovista.container import container

        youtube_service = container.youtube_service
        if not youtube_service.check_credentials():
            console.print(
                Panel(
                    "[red]YouTube API credentials not configured![/red]\n\n"
                    "Run [cyan]chronovista auth setup[/cyan] to configure OAuth credentials.",
                    title="Authentication Required",
                    border_style="red",
                )
            )
            raise typer.Exit(EXIT_CODE_NO_CREDENTIALS)

        # Create enrichment service using container
        service = container.create_enrichment_service(include_playlists=include_playlists)

        async for session in db_manager.get_session(echo=False):
            # Acquire lock
            try:
                await service.lock.acquire(session, force=force)
            except LockAcquisitionError as e:
                console.print(
                    Panel(
                        f"[red]{e}[/red]\n\n"
                        "Use [cyan]--force[/cyan] to override the lock.",
                        title="Lock Acquisition Failed",
                        border_style="red",
                    )
                )
                raise typer.Exit(EXIT_CODE_LOCK_FAILED)

            try:
                # T096: Handle auto-seed for missing prerequisites
                if auto_seed and not dry_run:
                    try:
                        await service.check_prerequisites(session)
                    except PrerequisiteError as e:
                        console.print(
                            f"[yellow]Prerequisites missing: {', '.join(e.missing_tables)}[/yellow]"
                        )
                        console.print("[cyan]Auto-seeding required data...[/cyan]")

                        # Import container for seeder creation
                        from chronovista.container import container

                        if "topic_categories" in e.missing_tables:
                            topic_seeder = container.create_topic_seeder()
                            topic_result = await topic_seeder.seed(session)
                            console.print(
                                f"[green]Seeded {topic_result.created} topics[/green]"
                            )

                        if "video_categories" in e.missing_tables:
                            category_seeder = container.create_category_seeder()
                            category_result = await category_seeder.seed(session)
                            console.print(
                                f"[green]Seeded {category_result.created} categories[/green]"
                            )

                        await session.commit()
                        console.print("[green]Auto-seeding complete![/green]\n")

                # Show configuration
                config_table = Table(
                    title="Enrichment Configuration", show_header=False
                )
                config_table.add_column("Setting", style="cyan")
                config_table.add_column("Value", style="green")
                config_table.add_row("Priority", priority.upper())
                config_table.add_row("Limit", str(limit) if limit else "No limit")
                config_table.add_row(
                    "Include Deleted", "Yes" if include_deleted else "No"
                )
                config_table.add_row(
                    "Include Playlists", "Yes" if include_playlists else "No"
                )
                config_table.add_row("Auto-Seed", "Yes" if auto_seed else "No")
                config_table.add_row("Refresh Topics", "Yes" if refresh_topics else "No")
                config_table.add_row("Sync Likes", "Yes" if sync_likes else "No")
                config_table.add_row("Verbose", "Yes" if verbose else "No")
                config_table.add_row("Dry Run", "Yes" if dry_run else "No")
                console.print(config_table)
                console.print()

                # Display priority tier counts before processing (T048)
                tier_counts = await service.get_priority_tier_counts(session)
                tier_table = Table(title="Priority Tier Counts", show_header=True)
                tier_table.add_column("Tier", style="cyan")
                tier_table.add_column("Videos", style="green", justify="right")
                tier_table.add_column("Quota Est.", style="yellow", justify="right")

                tier_table.add_row(
                    "HIGH",
                    str(tier_counts["high"]),
                    f"~{estimate_quota_cost(tier_counts['high'])} units",
                )
                tier_table.add_row(
                    "MEDIUM",
                    str(tier_counts["medium"]),
                    f"~{estimate_quota_cost(tier_counts['medium'])} units",
                )
                tier_table.add_row(
                    "LOW",
                    str(tier_counts["low"]),
                    f"~{estimate_quota_cost(tier_counts['low'])} units",
                )
                tier_table.add_row(
                    f"ALL (includes {tier_counts['deleted']} deleted)",
                    str(tier_counts["all"]),
                    f"~{estimate_quota_cost(tier_counts['all'])} units",
                )

                console.print(tier_table)
                console.print()

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task("Enriching videos...", total=None)

                    try:
                        # Run video enrichment with error handling
                        # T095: Skip prerequisites check if auto_seed already ran
                        check_prereqs = not auto_seed
                        report = await service.enrich_videos(
                            session,
                            priority=priority,
                            limit=limit,
                            include_deleted=include_deleted,
                            dry_run=dry_run,
                            check_prerequisites=check_prereqs,
                            refresh_topics=refresh_topics,
                        )

                    except PrerequisiteError as e:
                        # T095: Prerequisites missing and no auto-seed
                        progress.stop()
                        console.print(
                            Panel(
                                f"[red]Prerequisites missing![/red]\n\n"
                                f"Missing data in: [yellow]{', '.join(e.missing_tables)}[/yellow]\n\n"
                                f"Run the following commands first:\n"
                                f"  [cyan]chronovista seed topics[/cyan]\n"
                                f"  [cyan]chronovista seed categories[/cyan]\n\n"
                                f"Or use [cyan]--auto-seed[/cyan] to seed automatically.",
                                title="Prerequisites Missing",
                                border_style="red",
                            )
                        )
                        raise typer.Exit(EXIT_CODE_PREREQUISITES_MISSING)

                    except QuotaExceededException as e:
                        # T091: Quota exceeded - show partial progress
                        progress.stop()
                        console.print(
                            Panel(
                                f"[red]YouTube API quota exceeded![/red]\n\n"
                                f"Processed [cyan]{e.videos_processed}[/cyan] videos "
                                f"before quota was exhausted.\n\n"
                                f"The current batch has been committed.\n"
                                f"Wait until tomorrow for quota reset, then run again.",
                                title="Quota Exceeded",
                                border_style="red",
                            )
                        )
                        raise typer.Exit(EXIT_CODE_QUOTA_EXCEEDED)

                    except GracefulShutdownException as e:
                        # T093: Graceful shutdown requested
                        progress.stop()
                        console.print(
                            Panel(
                                f"[yellow]Shutdown requested via {e.signal_received}[/yellow]\n\n"
                                f"Current batch has been committed.\n"
                                f"Run again to continue from where you left off.",
                                title="Graceful Shutdown",
                                border_style="yellow",
                            )
                        )
                        raise typer.Exit(EXIT_CODE_INTERRUPTED)

                    # Note: Auto-resolution has been removed. Playlists are now linked
                    # directly from Google Takeout's playlists.csv during seeding.
                    # Unlinked playlists (int_ prefix) can be resolved by re-importing from Takeout.
                    if include_playlists and not dry_run:
                        # Check for unlinked playlists and inform user
                        from chronovista.repositories.playlist_repository import (
                            PlaylistRepository as PR,
                        )
                        temp_repo = PR()
                        unlinked_playlists = await temp_repo.get_unlinked_playlists(session, limit=500)
                        unlinked_count = len(unlinked_playlists)

                        if unlinked_count > 0:
                            console.print(
                                f"[dim][Info] {unlinked_count} playlists have internal IDs (int_ prefix). "
                                f"To link to YouTube IDs, re-import from Takeout with playlists.csv.[/dim]"
                            )

                    # Run playlist enrichment if enabled
                    if include_playlists:
                        progress.update(task, description="Enriching playlists...")
                        try:
                            (
                                playlists_processed,
                                playlists_updated,
                                playlists_deleted,
                            ) = await service.enrich_playlists(
                                session,
                                limit=limit,
                                dry_run=dry_run,
                            )
                            # Update the report summary with playlist stats
                            report.summary.playlists_processed = playlists_processed
                            report.summary.playlists_updated = playlists_updated
                            report.summary.playlists_deleted = playlists_deleted

                        except QuotaExceededException:
                            progress.stop()
                            console.print(
                                Panel(
                                    "[red]Quota exceeded during playlist enrichment![/red]\n\n"
                                    "Video enrichment completed successfully.\n"
                                    "Partial playlist data may have been saved.",
                                    title="Quota Exceeded",
                                    border_style="red",
                                )
                            )
                            raise typer.Exit(EXIT_CODE_QUOTA_EXCEEDED)

                        except GracefulShutdownException:
                            progress.stop()
                            console.print(
                                Panel(
                                    "[yellow]Shutdown during playlist enrichment[/yellow]\n\n"
                                    "Video enrichment completed. Playlist enrichment partial.",
                                    title="Graceful Shutdown",
                                    border_style="yellow",
                                )
                            )
                            raise typer.Exit(EXIT_CODE_INTERRUPTED)

                    # Sync liked videos if enabled
                    likes_synced = 0
                    likes_skipped = 0
                    if sync_likes and not dry_run:
                        progress.update(task, description="Syncing liked videos...")
                        try:
                            from chronovista.repositories.user_video_repository import (
                                UserVideoRepository,
                            )
                            from chronovista.repositories.video_repository import (
                                VideoRepository as VR,
                            )

                            user_video_repo = UserVideoRepository()
                            video_repo_for_likes = VR()

                            # Get user's channel ID
                            my_channel = await youtube_service.get_my_channel()
                            if my_channel:
                                user_id = my_channel.id

                                # Fetch all liked videos from YouTube API (no artificial limit)
                                liked_videos = await youtube_service.get_liked_videos()

                                if liked_videos:
                                    # Categorize into existing vs missing
                                    existing_video_ids = []
                                    for video in liked_videos:
                                        if await video_repo_for_likes.exists(
                                            session, video.id
                                        ):
                                            existing_video_ids.append(video.id)
                                        else:
                                            likes_skipped += 1

                                    # Batch update liked status for existing videos
                                    if existing_video_ids:
                                        likes_synced = (
                                            await user_video_repo.update_like_status_batch(
                                                session,
                                                user_id,
                                                existing_video_ids,
                                                liked=True,
                                            )
                                        )
                                        await session.commit()

                        except QuotaExceededException:
                            progress.stop()
                            console.print(
                                Panel(
                                    "[red]Quota exceeded during liked video sync![/red]\n\n"
                                    "Video enrichment completed successfully.\n"
                                    "Liked video sync was partial.",
                                    title="Quota Exceeded",
                                    border_style="red",
                                )
                            )
                            raise typer.Exit(EXIT_CODE_QUOTA_EXCEEDED)

                        except GracefulShutdownException:
                            progress.stop()
                            console.print(
                                Panel(
                                    "[yellow]Shutdown during liked video sync[/yellow]\n\n"
                                    "Video enrichment completed. Liked sync was partial.",
                                    title="Graceful Shutdown",
                                    border_style="yellow",
                                )
                            )
                            raise typer.Exit(EXIT_CODE_INTERRUPTED)

                        except Exception as e:
                            # Non-fatal error - log and continue
                            console.print(
                                f"[yellow]Warning: Could not sync liked videos: {e}[/yellow]"
                            )

                    progress.update(task, description="Enrichment complete!")

                # Display results
                summary = report.summary

                if dry_run:
                    console.print(
                        Panel(
                            f"[yellow]DRY RUN[/yellow] - No changes were made\n\n"
                            f"Videos that would be processed: [cyan]{summary.videos_processed}[/cyan]\n"
                            f"Estimated quota cost: [cyan]{estimate_quota_cost(summary.videos_processed)}[/cyan] units",
                            title="Dry Run Summary",
                            border_style="yellow",
                        )
                    )
                else:
                    # Build summary panel
                    summary_lines = [
                        f"Videos Processed: [cyan]{summary.videos_processed}[/cyan]",
                        f"Videos Updated: [green]{summary.videos_updated}[/green]",
                        f"Videos Deleted: [red]{summary.videos_deleted}[/red]",
                        f"Channels Created: [cyan]{summary.channels_created}[/cyan]",
                    ]
                    # T045-T049: Show auto-resolved channels if any
                    if summary.channels_auto_resolved > 0:
                        summary_lines.append(
                            f"Channels Auto-Resolved: [green]{summary.channels_auto_resolved}[/green]"
                        )

                    # Add playlist stats if playlists were enriched
                    if include_playlists:
                        summary_lines.extend(
                            [
                                "",  # Blank line for visual separation
                                f"Playlists Processed: [cyan]{summary.playlists_processed}[/cyan]",
                                f"Playlists Updated: [green]{summary.playlists_updated}[/green]",
                                f"Playlists Deleted: [red]{summary.playlists_deleted}[/red]",
                            ]
                        )

                    # Add liked video sync stats if sync was performed
                    if sync_likes and (likes_synced > 0 or likes_skipped > 0):
                        summary_lines.extend(
                            [
                                "",  # Blank line for visual separation
                                f"Liked Videos Synced: [green]{likes_synced}[/green]",
                                f"Liked Videos Skipped (not in DB): [dim]{likes_skipped}[/dim]",
                            ]
                        )

                    summary_lines.extend(
                        [
                            f"Errors: [red]{summary.errors}[/red]",
                            f"Quota Used: [yellow]{summary.quota_used}[/yellow] units",
                        ]
                    )

                    status_color = "green" if summary.errors == 0 else "yellow"
                    console.print(
                        Panel(
                            "\n".join(summary_lines),
                            title="Enrichment Complete",
                            border_style=status_color,
                        )
                    )

                # Show error details if any
                if summary.errors > 0:
                    error_table = Table(title="Errors", show_header=True)
                    error_table.add_column("Video ID", style="cyan")
                    error_table.add_column("Error", style="red")

                    for detail in report.details:
                        if detail.status == "error" and detail.error:
                            error_table.add_row(detail.video_id, detail.error)

                    console.print(error_table)

                return report, has_partial_success

            finally:
                # Release lock
                await service.lock.release(session)

        # Return empty report if we exit early (e.g., due to lock issues)
        from datetime import timezone

        from chronovista.models.enrichment_report import EnrichmentSummary

        return (
            EnrichmentReport(
                timestamp=datetime.now(timezone.utc),
                priority=priority,
                summary=EnrichmentSummary(
                    videos_processed=0,
                    videos_updated=0,
                    videos_deleted=0,
                    channels_created=0,
                    tags_created=0,
                    topic_associations=0,
                    categories_assigned=0,
                    errors=0,
                    quota_used=0,
                ),
                details=[],
            ),
            False,  # No partial success if we exit early
        )

    # Run the enrichment and get the report
    report, has_partial_success = asyncio.run(run_enrichment())

    # Save JSON report if output path specified (T056)
    if report_output_path is not None:
        _save_report(report, report_output_path)
        console.print(f"\n[green]Report saved to:[/green] {report_output_path}")

    # T055: Exit with code 4 if we had partial success with --skip-unresolved (FR-010)
    if has_partial_success:
        raise typer.Exit(EXIT_CODE_PARTIAL_SUCCESS)


def _format_count_with_percentage(count: int, total: int) -> str:
    """Format a count with percentage of total."""
    if total > 0:
        pct = (count / total) * 100
        return f"{count:,} ({pct:.1f}%)"
    return f"{count:,}"


def _render_status_panel(status: EnrichmentStatus) -> None:
    """
    Render the enrichment status as a Rich formatted panel.

    Creates a visually appealing display using Rich tables and panels
    per T054 requirements.

    Parameters
    ----------
    status : EnrichmentStatus
        The enrichment status data to display.
    """
    # Create main status table
    main_table = Table(
        show_header=False,
        box=None,
        padding=(0, 1),
        expand=True,
    )
    main_table.add_column("Label", style="cyan", width=25)
    main_table.add_column("Value", style="green", justify="right")

    # Video statistics
    main_table.add_row(
        "Total Videos:",
        f"{status.total_videos:,}",
    )
    main_table.add_row(
        "Fully Enriched:",
        _format_count_with_percentage(
            status.fully_enriched_videos, status.total_videos
        ),
    )
    main_table.add_row(
        "Placeholder Videos:",
        f"{status.placeholder_videos:,}",
    )
    main_table.add_row(
        "Deleted Videos:",
        f"{status.deleted_videos:,}",
    )
    main_table.add_row("", "")  # Separator

    # Channel statistics
    main_table.add_row(
        "Total Channels:",
        f"{status.total_channels:,}",
    )
    main_table.add_row(
        "Placeholder Channels:",
        f"{status.placeholder_channels:,}",
    )
    main_table.add_row("", "")  # Separator

    # Priority tier estimates
    main_table.add_row(
        "[bold]Priority Tier Estimates:[/bold]",
        "",
    )
    main_table.add_row(
        "  HIGH:",
        f"{status.tier_high.count:,} videos (~{status.tier_high.quota_units} units)",
    )
    main_table.add_row(
        "  MEDIUM:",
        f"{status.tier_medium.count:,} videos (~{status.tier_medium.quota_units} units)",
    )
    main_table.add_row(
        "  LOW:",
        f"{status.tier_low.count:,} videos (~{status.tier_low.quota_units} units)",
    )
    main_table.add_row(
        "  ALL:",
        f"{status.tier_all.count:,} videos (~{status.tier_all.quota_units} units)",
    )

    # Determine border color based on enrichment progress
    if status.enrichment_percentage >= 90:
        border_style = "green"
    elif status.enrichment_percentage >= 50:
        border_style = "yellow"
    else:
        border_style = "cyan"

    # Create panel with the table
    panel = Panel(
        main_table,
        title="Enrichment Status",
        border_style=border_style,
        padding=(1, 2),
    )

    console.print(panel)


@app.command("status")
def show_status() -> None:
    """
    Show current enrichment status and statistics.

    Displays counts of videos in each enrichment state and estimates
    quota costs for enriching each priority tier. This is a read-only
    operation that does not require authentication or lock acquisition.

    The display shows:
    - Total videos and channels in the database
    - Fully enriched vs placeholder counts
    - Deleted video count
    - Priority tier estimates with quota costs

    Examples:
        chronovista enrich status
    """
    import asyncio

    from chronovista.config.database import db_manager
    from chronovista.container import container

    async def fetch_and_display_status() -> None:
        # Create enrichment service using container
        service = container.create_enrichment_service()

        async for session in db_manager.get_session(echo=False):
            # Fetch status - no lock required (read-only operation)
            status = await service.get_status(session)

            # Render the status panel
            _render_status_panel(status)

    asyncio.run(fetch_and_display_status())


def _render_channel_status(
    total_channels: int,
    enriched: int,
    unenriched: int,
) -> None:
    """
    Render channel enrichment status as a Rich panel.

    Parameters
    ----------
    total_channels : int
        Total number of channels in database.
    enriched : int
        Number of fully enriched channels.
    unenriched : int
        Number of channels needing enrichment.
    """
    table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    table.add_column("Label", style="cyan", width=25)
    table.add_column("Value", style="green", justify="right")

    table.add_row("Total Channels:", f"{total_channels:,}")
    table.add_row(
        "Fully Enriched:",
        _format_count_with_percentage(enriched, total_channels),
    )
    table.add_row(
        "Needing Enrichment:",
        _format_count_with_percentage(unenriched, total_channels),
    )
    table.add_row("", "")  # Separator
    table.add_row(
        "Estimated Quota Cost:",
        f"~{(unenriched + BATCH_SIZE - 1) // BATCH_SIZE} units",
    )

    # Determine border color based on enrichment progress
    if total_channels > 0:
        pct = (enriched / total_channels) * 100
        if pct >= 90:
            border_style = "green"
        elif pct >= 50:
            border_style = "yellow"
        else:
            border_style = "cyan"
    else:
        border_style = "dim"

    panel = Panel(
        table,
        title="Channel Enrichment Status",
        border_style=border_style,
        padding=(1, 2),
    )
    console.print(panel)


def _render_channel_enrichment_result(result: ChannelEnrichmentResult, dry_run: bool) -> None:
    """
    Render channel enrichment result as a Rich panel.

    Parameters
    ----------
    result : ChannelEnrichmentResult
        The enrichment result to display.
    dry_run : bool
        Whether this was a dry run.
    """
    if dry_run:
        console.print(
            Panel(
                f"[yellow]DRY RUN[/yellow] - No changes were made\n\n"
                f"Channels that would be processed: [cyan]{result.channels_processed:,}[/cyan]\n"
                f"Estimated quota cost: [cyan]~{(result.channels_processed + BATCH_SIZE - 1) // BATCH_SIZE}[/cyan] units",
                title="Dry Run Summary",
                border_style="yellow",
            )
        )
        return

    # Build summary lines
    summary_lines = [
        f"Channels Processed: [cyan]{result.channels_processed:,}[/cyan]",
        f"Channels Enriched: [green]{result.channels_enriched:,}[/green]",
        f"Channels Skipped: [dim]{result.channels_skipped:,}[/dim]",
        f"Channels Failed: [red]{result.channels_failed:,}[/red]",
        "",  # Separator
        f"Batches Processed: [cyan]{result.batches_processed:,}[/cyan]",
        f"Quota Used: [yellow]~{result.quota_used}[/yellow] units",
    ]

    if result.duration_seconds > 0:
        duration_min = result.duration_seconds / 60
        summary_lines.append(f"Duration: [dim]{duration_min:.1f} minutes[/dim]")

    if result.network_instability_warning:
        summary_lines.append("")
        summary_lines.append(
            "[yellow]⚠ Network instability detected (3+ consecutive batch failures)[/yellow]"
        )

    if result.was_interrupted:
        summary_lines.append("")
        summary_lines.append("[yellow]⚠ Operation was interrupted (SIGINT)[/yellow]")

    # Determine border color
    if result.channels_failed == 0 and not result.was_interrupted:
        border_style = "green"
    elif result.was_interrupted or result.network_instability_warning:
        border_style = "yellow"
    else:
        border_style = "red" if result.channels_failed > result.channels_enriched else "yellow"

    console.print(
        Panel(
            "\n".join(summary_lines),
            title="Channel Enrichment Complete",
            border_style=border_style,
        )
    )


@app.command("channels")
def enrich_channels(
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of channels to process (default: all)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Preview what would be enriched without making changes",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Override any existing enrichment lock",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable detailed debug logging and track individual channel IDs",
    ),
) -> None:
    """
    Enrich channel metadata from YouTube Data API.

    Fetches current channel metadata (subscriber count, description, thumbnails,
    etc.) from YouTube and updates the local database. Channels are processed
    in batches of 50 (YouTube API limit) with automatic transaction management.

    Only channels without subscriber_count data are considered for enrichment.
    Use --dry-run to preview which channels would be enriched without making
    API calls.

    Exit codes:
    - 0: Success
    - 3: YouTube API quota exceeded
    - 4: Lock acquisition failed (use --force to override)
    - 5: Authentication failed
    - 130: Interrupted by user (SIGINT/SIGTERM)

    Examples:
        chronovista enrich channels
        chronovista enrich channels --limit 100
        chronovista enrich channels --dry-run
        chronovista enrich channels --force
        chronovista enrich channels --verbose
        chronovista enrich channels -l 50 -d
    """
    import asyncio

    from chronovista.config.database import db_manager
    from chronovista.container import container

    # Generate timestamp for logging
    timestamp = _generate_timestamp()

    # Set up file logging with verbose support
    log_file = _setup_enrichment_logging(timestamp, verbose=verbose)
    console.print(f"[dim]Logging to: {log_file}[/dim]")
    if verbose:
        console.print("[dim]Verbose logging enabled (DEBUG level)[/dim]")
    console.print()

    async def run_channel_enrichment() -> ChannelEnrichmentResult:
        # Install shutdown handler for graceful shutdown
        shutdown = get_shutdown_handler()
        shutdown.install()

        try:
            return await _run_channel_enrichment_inner()
        finally:
            # Uninstall shutdown handler
            shutdown.uninstall()

    async def _run_channel_enrichment_inner() -> ChannelEnrichmentResult:
        # T032: Check credentials first (FR-021)
        youtube_service = container.youtube_service
        if not youtube_service.check_credentials():
            console.print(
                Panel(
                    "[red]YouTube API credentials not configured![/red]\n\n"
                    "Run [cyan]chronovista auth setup[/cyan] to configure OAuth credentials.",
                    title="Authentication Required",
                    border_style="red",
                )
            )
            raise typer.Exit(EXIT_CODE_NO_CREDENTIALS)

        # Create enrichment service using container
        service = container.create_enrichment_service()

        async for session in db_manager.get_session(echo=False):
            # T028: Acquire lock with --force support (FR-016/017/019)
            try:
                await service.lock.acquire(session, force=force)
            except LockAcquisitionError as e:
                console.print(
                    Panel(
                        f"[red]{e}[/red]\n\n"
                        "Use [cyan]--force[/cyan] to override the lock.",
                        title="Lock Acquisition Failed",
                        border_style="red",
                    )
                )
                raise typer.Exit(EXIT_CODE_LOCK_FAILED)

            try:
                # Show configuration
                config_table = Table(
                    title="Channel Enrichment Configuration", show_header=False
                )
                config_table.add_column("Setting", style="cyan")
                config_table.add_column("Value", style="green")
                config_table.add_row("Limit", str(limit) if limit else "No limit")
                config_table.add_row("Verbose", "Yes" if verbose else "No")
                config_table.add_row("Dry Run", "Yes" if dry_run else "No")
                console.print(config_table)
                console.print()

                # Show channel status before processing
                status = await service.get_channel_enrichment_status(session)
                _render_channel_status(
                    total_channels=status["total_channels"],
                    enriched=status["enriched"],
                    unenriched=status["needs_enrichment"],
                )
                console.print()

                # Run channel enrichment with progress display
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task("Enriching channels...", total=None)

                    try:
                        # T023-T034: Run channel enrichment
                        result = await service.enrich_channels(
                            session,
                            limit=limit,
                            dry_run=dry_run,
                            verbose=verbose,
                        )

                    except QuotaExceededException as e:
                        # T042: Exit code 3 for quota exceeded
                        progress.stop()
                        console.print(
                            Panel(
                                f"[red]YouTube API quota exceeded![/red]\n\n"
                                f"Processed [cyan]{e.videos_processed}[/cyan] channels "
                                f"before quota was exhausted.\n\n"
                                f"The current batch has been committed.\n"
                                f"Wait until tomorrow for quota reset, then run again.",
                                title="Quota Exceeded",
                                border_style="red",
                            )
                        )
                        raise typer.Exit(EXIT_CODE_QUOTA_EXCEEDED)

                    except GracefulShutdownException as e:
                        # T030/T042: Exit code 130 for SIGINT
                        progress.stop()
                        console.print(
                            Panel(
                                f"[yellow]Shutdown requested via {e.signal_received}[/yellow]\n\n"
                                f"Current batch has been committed.\n"
                                f"Run again to continue from where you left off.",
                                title="Graceful Shutdown",
                                border_style="yellow",
                            )
                        )
                        raise typer.Exit(EXIT_CODE_INTERRUPTED)

                    except AuthenticationError as e:
                        # T033/T042: Exit code 5 for auth failure
                        progress.stop()
                        console.print(
                            Panel(
                                f"[red]Authentication failed![/red]\n\n"
                                f"{e.message}\n\n"
                                f"Run [cyan]chronovista auth setup[/cyan] to re-authenticate.",
                                title="Authentication Error",
                                border_style="red",
                            )
                        )
                        raise typer.Exit(EXIT_CODE_NO_CREDENTIALS)

                    except NetworkError as e:
                        # Network error - show warning but continue
                        progress.stop()
                        console.print(
                            Panel(
                                f"[red]Network error occurred![/red]\n\n"
                                f"{e.message}\n\n"
                                f"Check your internet connection and try again.",
                                title="Network Error",
                                border_style="red",
                            )
                        )
                        raise typer.Exit(1)

                    progress.update(task, description="Channel enrichment complete!")

                # T041: Display completion summary (NFR-028)
                _render_channel_enrichment_result(result, dry_run)

                return result

            finally:
                # Release lock
                await service.lock.release(session)

        # Return empty result if we exit early
        from datetime import timezone

        return ChannelEnrichmentResult(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )

    # Run the enrichment
    asyncio.run(run_channel_enrichment())


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """
    Enrich video metadata from YouTube API.

    Use 'chronovista enrich run' to start enrichment or
    'chronovista enrich status' to view current statistics.
    """
    if ctx.invoked_subcommand is None:
        console.print(
            "Use [cyan]chronovista enrich --help[/cyan] for usage information"
        )
        raise typer.Exit(0)
