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
from rich.table import Table

from chronovista.exceptions import (
    EXIT_CODE_INTERRUPTED,
    EXIT_CODE_PREREQUISITES_MISSING,
    EXIT_CODE_QUOTA_EXCEEDED,
    GracefulShutdownException,
    PrerequisiteError,
    QuotaExceededException,
)
from chronovista.models.enrichment_report import EnrichmentReport
from chronovista.services.enrichment.enrichment_service import (
    BATCH_SIZE,
    EXIT_CODE_LOCK_FAILED,
    EXIT_CODE_NO_CREDENTIALS,
    EnrichmentStatus,
    LockAcquisitionError,
    estimate_quota_cost,
)
from chronovista.services.enrichment.shutdown_handler import get_shutdown_handler

app = typer.Typer(help="Enrich video metadata from YouTube API")
console = Console()


# Valid priority levels
VALID_PRIORITIES = {"high", "medium", "low", "all"}


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
    - 0: Success
    - 3: YouTube API quota exceeded
    - 4: Prerequisites missing (run seed commands first or use --auto-seed)
    - 130: Interrupted by user (SIGINT/SIGTERM)

    Examples:
        chronovista enrich run
        chronovista enrich run --limit 100
        chronovista enrich run --priority medium --dry-run
        chronovista enrich run --include-deleted
        chronovista enrich run --include-playlists
        chronovista enrich run --auto-seed
        chronovista enrich run --verbose
        chronovista enrich run --output ./my-report.json
        chronovista enrich run -o ./exports/enrichment.json
    """
    import asyncio

    from chronovista.config.database import db_manager
    from chronovista.repositories.channel_repository import ChannelRepository
    from chronovista.repositories.playlist_repository import PlaylistRepository
    from chronovista.repositories.topic_category_repository import (
        TopicCategoryRepository,
    )
    from chronovista.repositories.video_category_repository import (
        VideoCategoryRepository,
    )
    from chronovista.repositories.video_repository import VideoRepository
    from chronovista.repositories.video_tag_repository import VideoTagRepository
    from chronovista.repositories.video_topic_repository import VideoTopicRepository
    from chronovista.services.enrichment.enrichment_service import EnrichmentService
    from chronovista.services.youtube_service import YouTubeService

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

    async def run_enrichment() -> EnrichmentReport:
        # T093: Install shutdown handler for graceful shutdown
        shutdown = get_shutdown_handler()
        shutdown.install()

        try:
            return await _run_enrichment_inner()
        finally:
            # T093: Uninstall shutdown handler
            shutdown.uninstall()

    async def _run_enrichment_inner() -> EnrichmentReport:
        # Check credentials first
        youtube_service = YouTubeService()
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

        # Initialize repositories
        video_repo = VideoRepository()
        channel_repo = ChannelRepository()
        tag_repo = VideoTagRepository()
        topic_repo = VideoTopicRepository()
        category_repo = VideoCategoryRepository()
        topic_cat_repo = TopicCategoryRepository()
        playlist_repo = PlaylistRepository() if include_playlists else None

        # Create enrichment service
        service = EnrichmentService(
            video_repository=video_repo,
            channel_repository=channel_repo,
            video_tag_repository=tag_repo,
            video_topic_repository=topic_repo,
            video_category_repository=category_repo,
            topic_category_repository=topic_cat_repo,
            youtube_service=youtube_service,
            playlist_repository=playlist_repo,
        )

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

                        # Import and run seeders
                        from chronovista.services.enrichment.seeders import (
                            CategorySeeder,
                            TopicSeeder,
                        )

                        if "topic_categories" in e.missing_tables:
                            topic_seeder = TopicSeeder(topic_cat_repo)
                            topic_result = await topic_seeder.seed(session)
                            console.print(
                                f"[green]Seeded {topic_result.created} topics[/green]"
                            )

                        if "video_categories" in e.missing_tables:
                            category_seeder = CategorySeeder(
                                category_repo, youtube_service
                            )
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

                return report

            finally:
                # Release lock
                await service.lock.release(session)

        # Return empty report if we exit early (e.g., due to lock issues)
        from datetime import timezone

        from chronovista.models.enrichment_report import EnrichmentSummary

        return EnrichmentReport(
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
        )

    # Run the enrichment and get the report
    report = asyncio.run(run_enrichment())

    # Save JSON report if output path specified (T056)
    if report_output_path is not None:
        _save_report(report, report_output_path)
        console.print(f"\n[green]Report saved to:[/green] {report_output_path}")


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
    from chronovista.repositories.channel_repository import ChannelRepository
    from chronovista.repositories.topic_category_repository import (
        TopicCategoryRepository,
    )
    from chronovista.repositories.video_category_repository import (
        VideoCategoryRepository,
    )
    from chronovista.repositories.video_repository import VideoRepository
    from chronovista.repositories.video_tag_repository import VideoTagRepository
    from chronovista.repositories.video_topic_repository import VideoTopicRepository
    from chronovista.services.enrichment.enrichment_service import EnrichmentService

    async def fetch_and_display_status() -> None:
        # Initialize repositories (no YouTube service needed for status)
        video_repo = VideoRepository()
        channel_repo = ChannelRepository()
        tag_repo = VideoTagRepository()
        topic_repo = VideoTopicRepository()
        category_repo = VideoCategoryRepository()
        topic_cat_repo = TopicCategoryRepository()

        # Create enrichment service with a mock YouTube service
        # (not needed for status, but required by the constructor)
        from unittest.mock import MagicMock

        mock_youtube = MagicMock()

        service = EnrichmentService(
            video_repository=video_repo,
            channel_repository=channel_repo,
            video_tag_repository=tag_repo,
            video_topic_repository=topic_repo,
            video_category_repository=category_repo,
            topic_category_repository=topic_cat_repo,
            youtube_service=mock_youtube,
        )

        async for session in db_manager.get_session(echo=False):
            # Fetch status - no lock required (read-only operation)
            status = await service.get_status(session)

            # Render the status panel
            _render_status_panel(status)

    asyncio.run(fetch_and_display_status())


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
