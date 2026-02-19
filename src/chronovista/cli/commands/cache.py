"""
CLI commands for managing the local image cache.

Provides the ``chronovista cache warm`` command for pre-downloading
channel avatar and video thumbnail images with rate limiting,
exponential backoff, dry-run mode, and graceful interrupt handling.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.config.database import db_manager
from chronovista.config.settings import settings
from chronovista.models.enums import ImageQuality
from chronovista.services.image_cache import (
    ImageCacheConfig,
    ImageCacheService,
    WarmResult,
)

console = Console()

# Valid --type values
_VALID_TYPES = {"channels", "videos", "all"}

# Valid --quality values (from ImageQuality enum)
_VALID_QUALITIES = {q.value for q in ImageQuality}

app = typer.Typer(
    name="cache",
    help="Manage the local image cache.",
    no_args_is_help=True,
)


def _build_cache_service() -> ImageCacheService:
    """Build an ImageCacheService from application settings.

    Returns
    -------
    ImageCacheService
        Configured image cache service.
    """
    config = ImageCacheConfig(
        cache_dir=settings.cache_dir,
        channels_dir=settings.cache_dir / "images" / "channels",
        videos_dir=settings.cache_dir / "images" / "videos",
    )
    return ImageCacheService(config=config)


@app.command(name="warm")
def warm(
    type_: str = typer.Option(
        "all",
        "--type",
        help='Image type to warm: "channels", "videos", or "all"',
    ),
    quality: str = typer.Option(
        "mqdefault",
        "--quality",
        help="Video thumbnail quality level",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of images to download",
    ),
    delay: float = typer.Option(
        0.5,
        "--delay",
        "-d",
        help="Seconds between requests",
        min=0.0,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview mode: show counts without downloading",
    ),
) -> None:
    """
    Pre-download missing images with rate-limited fetching.

    Re-attempts images with .missing markers (retries previously failed
    downloads). The command is implicitly resumable: when re-run after
    interruption it skips already-cached images.

    Examples:
        chronovista cache warm
        chronovista cache warm --type channels
        chronovista cache warm --type videos --quality hqdefault --limit 100
        chronovista cache warm --dry-run
    """
    # Validate --type
    if type_ not in _VALID_TYPES:
        console.print(
            f'[red]Error: Invalid --type "{type_}". '
            f"Must be one of: {', '.join(sorted(_VALID_TYPES))}[/red]"
        )
        raise typer.Exit(code=2)

    # Validate --quality
    if quality not in _VALID_QUALITIES:
        console.print(
            f'[red]Error: Invalid --quality "{quality}". '
            f"Must be one of: {', '.join(sorted(_VALID_QUALITIES))}[/red]"
        )
        raise typer.Exit(code=2)

    # Validate --limit
    if limit is not None and limit <= 0:
        console.print("[red]Error: --limit must be a positive integer[/red]")
        raise typer.Exit(code=2)

    # Validate --delay
    if delay < 0:
        console.print("[red]Error: --delay must be non-negative[/red]")
        raise typer.Exit(code=2)

    try:
        asyncio.run(
            _warm_async(
                type_=type_,
                quality=quality,
                limit=limit,
                delay=delay,
                dry_run=dry_run,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Cache warming interrupted by user[/yellow]")
        raise typer.Exit(code=130)


async def _warm_async(
    *,
    type_: str,
    quality: str,
    limit: int | None,
    delay: float,
    dry_run: bool,
) -> None:
    """Async implementation of the cache warm command.

    Parameters
    ----------
    type_ : str
        Image type to warm (``"channels"``, ``"videos"``, or ``"all"``).
    quality : str
        Video thumbnail quality level.
    limit : int | None
        Maximum number of images to download per entity type.
    delay : float
        Seconds to sleep between downloads.
    dry_run : bool
        If ``True``, only report counts without downloading.
    """
    service = _build_cache_service()

    channel_result: WarmResult | None = None
    video_result: WarmResult | None = None
    had_errors = False

    if dry_run:
        console.print(
            "[yellow]Dry run - no images will be downloaded.[/yellow]\n"
        )

    async for session in db_manager.get_session(echo=False):
        # --- Warm channels ---
        if type_ in ("channels", "all"):
            channel_result = await _warm_channels(
                service=service,
                session=session,
                delay=delay,
                limit=limit,
                dry_run=dry_run,
            )
            if channel_result.failed > 0:
                had_errors = True

        # --- Warm videos ---
        if type_ in ("videos", "all"):
            video_result = await _warm_videos(
                service=service,
                session=session,
                quality=quality,
                delay=delay,
                limit=limit,
                dry_run=dry_run,
            )
            if video_result.failed > 0:
                had_errors = True

    # Display summary
    _display_summary(
        channel_result=channel_result,
        video_result=video_result,
        dry_run=dry_run,
    )

    # Exit code: 0 = success, 1 = partial/errors
    if had_errors:
        raise typer.Exit(code=1)


async def _warm_channels(
    *,
    service: ImageCacheService,
    session: AsyncSession,
    delay: float,
    limit: int | None,
    dry_run: bool,
) -> WarmResult:
    """Warm channel avatars with Rich progress display.

    Parameters
    ----------
    service : ImageCacheService
        The image cache service.
    session : AsyncSession
        Database session.
    delay : float
        Inter-request delay.
    limit : int | None
        Download limit.
    dry_run : bool
        Dry-run flag.

    Returns
    -------
    WarmResult
        Channel warming result.
    """
    if dry_run:
        console.print("[cyan]Scanning channel avatars...[/cyan]")
    else:
        console.print("[cyan]Warming channel avatars...[/cyan]")

    downloaded_count = 0
    skipped_count = 0
    failed_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Channels", total=None)

        def channel_callback(entity_id: str, status: str) -> None:
            nonlocal downloaded_count, skipped_count, failed_count
            if status == "downloaded" or status == "dry_run":
                downloaded_count += 1
            elif status == "skipped" or status == "limit_reached":
                skipped_count += 1
            elif status.startswith("failed"):
                failed_count += 1

            if status == "__backoff__":
                # Don't update progress for backoff notifications
                return

            progress.update(
                task,
                advance=1 if status != "__backoff__" else 0,
                description=(
                    f"Channels ({downloaded_count} "
                    f"{'to download' if dry_run else 'downloaded'}, "
                    f"{skipped_count} cached)"
                ),
            )

            # Log 429 backoffs to console
            if entity_id == "__backoff__":
                console.print(f"  [yellow]Warning: {status}[/yellow]")

        result = await service.warm_channels(
            session=session,
            delay=delay,
            limit=limit,
            dry_run=dry_run,
            progress_callback=channel_callback,
        )

        progress.update(task, total=result.total, completed=result.total)

    return result


async def _warm_videos(
    *,
    service: ImageCacheService,
    session: AsyncSession,
    quality: str,
    delay: float,
    limit: int | None,
    dry_run: bool,
) -> WarmResult:
    """Warm video thumbnails with Rich progress display.

    Parameters
    ----------
    service : ImageCacheService
        The image cache service.
    session : AsyncSession
        Database session.
    quality : str
        Thumbnail quality level.
    delay : float
        Inter-request delay.
    limit : int | None
        Download limit.
    dry_run : bool
        Dry-run flag.

    Returns
    -------
    WarmResult
        Video warming result.
    """
    if dry_run:
        console.print(f"\n[cyan]Scanning video thumbnails ({quality})...[/cyan]")
    else:
        console.print(f"\n[cyan]Warming video thumbnails ({quality})...[/cyan]")

    downloaded_count = 0
    skipped_count = 0
    failed_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Videos", total=None)

        def video_callback(entity_id: str, status: str) -> None:
            nonlocal downloaded_count, skipped_count, failed_count
            if status == "downloaded" or status == "dry_run":
                downloaded_count += 1
            elif status == "skipped" or status == "limit_reached":
                skipped_count += 1
            elif status.startswith("failed"):
                failed_count += 1

            if status == "__backoff__":
                return

            progress.update(
                task,
                advance=1 if status != "__backoff__" else 0,
                description=(
                    f"Videos ({downloaded_count} "
                    f"{'to download' if dry_run else 'downloaded'}, "
                    f"{skipped_count} cached)"
                ),
            )

            # Log 429 backoffs to console
            if entity_id == "__backoff__":
                console.print(f"  [yellow]Warning: {status}[/yellow]")

        result = await service.warm_videos(
            session=session,
            quality=quality,
            delay=delay,
            limit=limit,
            dry_run=dry_run,
            progress_callback=video_callback,
        )

        progress.update(task, total=result.total, completed=result.total)

    return result


def _display_summary(
    *,
    channel_result: WarmResult | None,
    video_result: WarmResult | None,
    dry_run: bool,
) -> None:
    """Display a summary table of warming results.

    Parameters
    ----------
    channel_result : WarmResult | None
        Result from channel warming, or ``None`` if not performed.
    video_result : WarmResult | None
        Result from video warming, or ``None`` if not performed.
    dry_run : bool
        Whether this was a dry-run operation.
    """
    console.print()

    table = Table(title="Cache Warm Summary")
    dl_label = "To Download" if dry_run else "Downloaded"
    table.add_column("Type", style="cyan")
    table.add_column(dl_label, style="green", justify="right")
    table.add_column("Cached", style="blue", justify="right")
    table.add_column("Failed", style="red", justify="right")
    table.add_column("No URL", style="yellow", justify="right")
    table.add_column("Total", style="bold", justify="right")

    if channel_result is not None:
        table.add_row(
            "Channels",
            str(channel_result.downloaded),
            str(channel_result.skipped),
            str(channel_result.failed),
            str(channel_result.no_url),
            str(channel_result.total),
        )

    if video_result is not None:
        table.add_row(
            "Videos",
            str(video_result.downloaded),
            str(video_result.skipped),
            str(video_result.failed),
            str(video_result.no_url),
            str(video_result.total),
        )

    console.print(table)

    if dry_run:
        # Estimate download sizes
        ch_dl = channel_result.downloaded if channel_result else 0
        vid_dl = video_result.downloaded if video_result else 0
        ch_est_mb = ch_dl * 100 / 1024  # ~100 KB per channel avatar
        vid_est_mb = vid_dl * 12 / 1024  # ~12 KB per video thumbnail
        total_est_mb = ch_est_mb + vid_est_mb
        console.print(
            f"\n  Estimated download: "
            f"~{ch_est_mb:.1f} MB (channels, ~100 KB each) + "
            f"~{vid_est_mb:.1f} MB (videos, ~12 KB each) = "
            f"~{total_est_mb:.1f} MB"
        )


@app.command(name="status")
def status() -> None:
    """
    Display cache statistics.

    Shows counts of cached images, missing markers, total size, and file ages.

    Examples:
        chronovista cache status
    """
    try:
        asyncio.run(_status_async())
    except KeyboardInterrupt:
        console.print("\n[yellow]Status check interrupted by user[/yellow]")
        raise typer.Exit(code=130)


async def _status_async() -> None:
    """Async implementation of the cache status command."""
    service = _build_cache_service()
    stats = await service.get_stats()

    # Format human-readable size
    def format_size(size_bytes: int) -> str:
        """Convert bytes to human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    # Build statistics table
    table = Table(title="Image Cache Status")
    table.add_column("Type", style="cyan")
    table.add_column("Cached", style="green", justify="right")
    table.add_column("Missing", style="yellow", justify="right")
    table.add_column("Size", style="blue", justify="right")

    # Calculate sizes (approximate since we don't track per-type)
    total_cached = stats.channel_count + stats.video_count
    channel_size_bytes = 0
    video_size_bytes = 0
    if total_cached > 0:
        # Approximate split based on counts
        channel_size_bytes = int(
            stats.total_size_bytes * (stats.channel_count / total_cached)
        )
        video_size_bytes = stats.total_size_bytes - channel_size_bytes

    # Add rows
    table.add_row(
        "Channels",
        f"{stats.channel_count:,}",
        str(stats.channel_missing_count),
        format_size(channel_size_bytes),
    )
    table.add_row(
        "Videos",
        f"{stats.video_count:,}",
        str(stats.video_missing_count),
        format_size(video_size_bytes),
    )

    # Add total row
    total_missing = stats.channel_missing_count + stats.video_missing_count
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_cached:,}[/bold]",
        f"[bold]{total_missing}[/bold]",
        f"[bold]{format_size(stats.total_size_bytes)}[/bold]",
    )

    console.print()
    console.print(table)
    console.print()

    # Display cache directory and file ages
    console.print(f"  Cache directory: {settings.cache_dir / 'images'}")
    if stats.oldest_file is not None:
        console.print(f"  Oldest file:     {stats.oldest_file.strftime('%Y-%m-%d')}")
    if stats.newest_file is not None:
        console.print(f"  Newest file:     {stats.newest_file.strftime('%Y-%m-%d')}")
    console.print()


@app.command(name="purge")
def purge(
    type_: str = typer.Option(
        "all",
        "--type",
        help='Image type to purge: "channels", "videos", or "all"',
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Skip confirmation prompt",
    ),
) -> None:
    """
    Delete cached images selectively or entirely.

    Warns about unavailable content that cannot be re-downloaded before
    prompting for confirmation. Use --force to skip the confirmation prompt.

    Examples:
        chronovista cache purge
        chronovista cache purge --type channels
        chronovista cache purge --type videos --force
    """
    # Validate --type
    if type_ not in _VALID_TYPES:
        console.print(
            f'[red]Error: Invalid --type "{type_}". '
            f"Must be one of: {', '.join(sorted(_VALID_TYPES))}[/red]"
        )
        raise typer.Exit(code=2)

    try:
        asyncio.run(_purge_async(type_=type_, force=force))
    except KeyboardInterrupt:
        console.print("\n[yellow]Purge interrupted by user[/yellow]")
        raise typer.Exit(code=130)


async def _purge_async(*, type_: str, force: bool) -> None:
    """Async implementation of the cache purge command.

    Parameters
    ----------
    type_ : str
        Image type to purge (``"channels"``, ``"videos"``, or ``"all"``).
    force : bool
        If ``True``, skip confirmation prompt.
    """
    service = _build_cache_service()

    # Check for unavailable content warning
    unavailable_count = 0
    async for session in db_manager.get_session(echo=False):
        unavailable_count = await service.count_unavailable_cached(
            session=session,
            type_=type_,
        )

    # Display warning if unavailable content exists
    if unavailable_count > 0:
        console.print(
            f"\n[yellow]Warning: {unavailable_count} cached image(s) belong to "
            f"unavailable content that CANNOT be re-downloaded from YouTube.[/yellow]\n"
        )

    # Confirmation prompt unless --force
    if not force:
        type_label = {
            "channels": "channel images",
            "videos": "video thumbnails",
            "all": "all cached images",
        }[type_]

        confirmation = typer.confirm(
            f"Are you sure you want to purge {type_label}?",
            default=False,
        )

        if not confirmation:
            console.print("[yellow]Purge cancelled by user[/yellow]")
            raise typer.Exit(code=1)

    # Perform purge
    bytes_freed = await service.purge(type_=type_)

    # Format human-readable size
    def format_size(size_bytes: int) -> str:
        """Convert bytes to human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    # Display result
    console.print()
    console.print(f"[green]Purge complete: freed {format_size(bytes_freed)}[/green]")
    console.print()
