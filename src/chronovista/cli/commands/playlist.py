"""
Playlist CLI commands for chronovista.

This module provides commands for managing playlists:
- `list`: Display playlists with link status
- `show`: Show detailed playlist information

Note: The `link`, `unlink`, and `resolve` commands have been removed.
Playlists are now identified directly by their YouTube ID (PL prefix) or
internal ID (int_ prefix) in the `playlist_id` field. To link playlists
to YouTube IDs, re-import from Takeout with playlists.csv.

All commands support proper exit codes, confirmation prompts, and error handling.
"""

from __future__ import annotations

import asyncio
import builtins
import json
import sys
from enum import Enum

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.cli.constants import (
    EXIT_CANCELLED,
    EXIT_SUCCESS,
    EXIT_SYSTEM_ERROR,
    EXIT_USER_ERROR,
)
from chronovista.cli.errors import format_not_found_error
from chronovista.config.database import DatabaseManager
from chronovista.db.models import Playlist as PlaylistDB
from chronovista.models.enums import PlaylistType, classify_playlist_type
from chronovista.repositories.playlist_repository import PlaylistRepository

console = Console()


class OutputFormat(str, Enum):
    """Output format options for playlist commands."""

    TABLE = "table"
    JSON = "json"
    CSV = "csv"


class PlaylistListSortField(str, Enum):
    """Sort key for `playlist list`.

    Named a *field*, not an *order*, to match the convention the API layer
    already uses: ``SortOrder`` means direction (``ASC``/``DESC``) and lives in
    ``api/schemas/sorting.py``, while the key to sort by is a
    ``<Thing>SortField`` (``PlaylistSortField``, ``VideoSortField``,
    ``ChannelVideoSortField``). This enum holds keys, so it was the odd one out.

    Not merged into the API's ``PlaylistSortField``: that one offers
    ``CREATED_AT``/``VIDEO_COUNT`` where this offers ``VIDEOS``/``STATUS``, and
    reconciling them would change values a shipped endpoint accepts.
    """

    TITLE = "title"
    VIDEOS = "videos"
    STATUS = "status"


# Create the playlist Typer app
playlist_app = typer.Typer(
    name="playlist",
    help="Playlist management commands",
    no_args_is_help=True,
)


@playlist_app.command()
def list(
    linked: bool = typer.Option(
        False,
        "--linked",
        help="Show only linked playlists",
    ),
    unlinked: bool = typer.Option(
        False,
        "--unlinked",
        help="Show only unlinked playlists",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-n",
        help="Maximum playlists to show",
        min=1,
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.TABLE,
        "--format",
        help="Output format",
    ),
    sort: PlaylistListSortField = typer.Option(
        PlaylistListSortField.TITLE,
        "--sort",
        help="Sort order: title (alphabetical), videos (by count), status (linked first)",
    ),
) -> None:
    """
    List playlists with link status.

    Shows playlists with their internal ID, title, video count, and link status.
    By default, shows all playlists sorted alphabetically by title.

    Examples:
        chronovista playlist list
        chronovista playlist list --linked
        chronovista playlist list --unlinked --limit 100
        chronovista playlist list --format json
        chronovista playlist list --sort videos

    Exit Codes:
        0: Success - playlists listed successfully
        2: System error - database failure
        3: Cancelled - Ctrl+C pressed
    """

    async def list_playlists_async() -> None:
        """Async implementation of playlist listing."""
        repository = PlaylistRepository()
        db_manager = DatabaseManager()

        try:
            async for session in db_manager.get_session(echo=False):
                # Determine which playlists to fetch
                if linked and unlinked:
                    # If both flags are set, show all playlists
                    playlists = await repository.get_recent_playlists(
                        session, limit=limit
                    )
                elif linked:
                    playlists = await repository.get_linked_playlists(
                        session, skip=0, limit=limit
                    )
                elif unlinked:
                    playlists = await repository.get_unlinked_playlists(
                        session, skip=0, limit=limit
                    )
                else:
                    # Default: show all playlists
                    playlists = await repository.get_recent_playlists(
                        session, limit=limit
                    )

                # Get statistics for summary
                stats = await repository.get_link_statistics(session)

                # Apply sorting based on --sort flag
                if sort == PlaylistListSortField.TITLE:
                    # Alphabetical by title (A-Z)
                    playlists = sorted(playlists, key=lambda p: p.title.lower())
                elif sort == PlaylistListSortField.VIDEOS:
                    # By video count (descending)
                    playlists = sorted(
                        playlists, key=lambda p: p.video_count, reverse=True
                    )
                elif sort == PlaylistListSortField.STATUS:
                    # Linked first, then unlinked, then alphabetical within each group
                    # A playlist is "linked" if playlist_id starts with "PL" or is a system ID
                    playlists = sorted(
                        playlists,
                        key=lambda p: (
                            not (
                                p.playlist_id.startswith("PL")
                                or p.playlist_id in ("LL", "WL", "HL")
                            ),
                            p.title.lower(),
                        ),
                    )

                # Format output
                if format == OutputFormat.JSON:
                    _output_json(playlists, stats)
                elif format == OutputFormat.CSV:
                    _output_csv(playlists, stats)
                else:
                    _output_table(playlists, stats, limit)

                sys.exit(EXIT_SUCCESS)

        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
            sys.exit(EXIT_CANCELLED)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Database error:[/red]\n{str(e)}",
                    title="List Failed",
                    border_style="red",
                )
            )
            sys.exit(EXIT_SYSTEM_ERROR)

    # Run the async function
    asyncio.run(list_playlists_async())


@playlist_app.command()
def show(
    playlist_id: str = typer.Argument(
        ...,
        help="Internal or YouTube playlist ID",
    ),
) -> None:
    """
    Show detailed playlist information.

    Displays comprehensive information about a playlist including internal ID,
    YouTube ID (if linked), title, description, video count, privacy status,
    channel, and timestamps.

    Accepts both internal IDs (INT_ prefix) and YouTube IDs (PL prefix).

    Examples:
        chronovista playlist show INT_7f37ed8c...
        chronovista playlist show PLdU2XMVb99x...

    Exit Codes:
        0: Success - playlist details displayed
        1: User error - invalid ID format or playlist not found
        2: System error - database failure
        3: Cancelled - Ctrl+C pressed
    """

    async def show_playlist_async() -> None:
        """Async implementation of playlist show."""
        repository = PlaylistRepository()
        db_manager = DatabaseManager()

        try:
            async for session in db_manager.get_session(echo=False):
                # Try to look up playlist by internal ID or YouTube ID
                playlist = None

                # Look up playlist by ID (could be internal ID or YouTube ID)
                # Since playlist_id is now the primary key, just look it up directly
                playlist = await repository.get_with_channel(session, playlist_id)

                if not playlist:
                    error_msg = format_not_found_error("Playlist", playlist_id)
                    console.print(f"[red]{error_msg}[/red]")
                    sys.exit(EXIT_USER_ERROR)

                # Display detailed information
                _display_playlist_details(playlist)

                sys.exit(EXIT_SUCCESS)

        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
            sys.exit(EXIT_CANCELLED)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Database error:[/red]\n{str(e)}",
                    title="Show Failed",
                    border_style="red",
                )
            )
            sys.exit(EXIT_SYSTEM_ERROR)

    # Run the async function
    asyncio.run(show_playlist_async())


# =============================================================================
# Helper Functions for List Command
# =============================================================================


def _truncate_id(playlist_id: str, max_length: int = 40) -> str:
    """
    Truncate playlist ID for table display.

    Args:
        playlist_id: Full playlist ID
        max_length: Maximum length to display

    Returns:
        Truncated ID with ellipsis if needed
    """
    if len(playlist_id) <= max_length:
        return playlist_id
    return playlist_id[: max_length - 3] + "..."


def _output_table(
    playlists: builtins.list[PlaylistDB], stats: dict[str, int], limit: int
) -> None:
    """
    Output playlists in table format.

    Args:
        playlists: List of playlist database objects
        stats: Dictionary with total/linked/unlinked counts
        limit: Maximum number of playlists shown
    """
    total = stats["total_playlists"]
    linked_count = stats["linked_playlists"]
    unlinked_count = stats["unlinked_playlists"]

    # Create table
    table = Table(title=f"Playlists (showing {len(playlists)} of {total})")
    table.add_column("Internal ID", style="cyan", no_wrap=False)
    table.add_column("Title", style="white")
    table.add_column("Videos", justify="right", style="green")
    table.add_column("Status", justify="center")

    for playlist in playlists:
        # Truncate internal ID for display
        truncated_id = _truncate_id(playlist.playlist_id)

        # Status with emoji - linked if playlist_id starts with PL or is a system ID
        is_linked = playlist.playlist_id.startswith("PL") or playlist.playlist_id in (
            "LL",
            "WL",
            "HL",
        )
        status = "✅ Linked" if is_linked else "❌ Unlinked"

        table.add_row(
            truncated_id,
            playlist.title,
            str(playlist.video_count),
            status,
        )

    console.print(table)

    # Summary footer
    console.print(
        f"\nSummary: {linked_count} linked, {unlinked_count} unlinked ({total} total)"
    )


def _output_json(playlists: builtins.list[PlaylistDB], stats: dict[str, int]) -> None:
    """
    Output playlists in JSON format.

    Args:
        playlists: List of playlist database objects
        stats: Dictionary with total/linked/unlinked counts
    """
    output = {
        "playlists": [
            {
                "playlist_id": p.playlist_id,
                "title": p.title,
                "video_count": p.video_count,
                "linked": (
                    p.playlist_id.startswith("PL")
                    or p.playlist_id in ("LL", "WL", "HL")
                ),
            }
            for p in playlists
        ],
        "summary": {
            "total": stats["total_playlists"],
            "linked": stats["linked_playlists"],
            "unlinked": stats["unlinked_playlists"],
        },
    }

    console.print(json.dumps(output, indent=2))


def _output_csv(playlists: builtins.list[PlaylistDB], stats: dict[str, int]) -> None:
    """
    Output playlists in CSV format.

    Args:
        playlists: List of playlist database objects
        stats: Dictionary with total/linked/unlinked counts
    """
    # CSV header
    console.print("playlist_id,title,video_count,linked")

    # CSV rows
    for p in playlists:
        is_linked = p.playlist_id.startswith("PL") or p.playlist_id in (
            "LL",
            "WL",
            "HL",
        )
        linked = "true" if is_linked else "false"
        # Escape title for CSV (quote if contains comma)
        title = f'"{p.title}"' if "," in p.title else p.title
        console.print(f"{p.playlist_id},{title},{p.video_count},{linked}")

    # Summary as comment
    console.print(
        f"# Summary: {stats['linked_playlists']} linked, {stats['unlinked_playlists']} unlinked ({stats['total_playlists']} total)"
    )


# =============================================================================
# Helper Functions for Show Command
# =============================================================================


def _display_playlist_details(playlist: PlaylistDB) -> None:
    """
    Display detailed playlist information.

    Args:
        playlist: Playlist database object with channel loaded
    """
    # Format created_at timestamp
    created_str = playlist.created_at.strftime("%Y-%m-%d %H:%M:%S")

    # Determine if playlist is linked (has YouTube ID or is system playlist)
    is_linked = playlist.playlist_id.startswith("PL") or playlist.playlist_id in (
        "LL",
        "WL",
        "HL",
    )

    # Build details string
    details_lines = [
        "Playlist Details",
        "─" * 40,
        f"Playlist ID:    {playlist.playlist_id}",
        f"Status:         {'[green]Linked[/green]' if is_linked else '[yellow]Internal[/yellow]'}",
        f"Title:          {playlist.title}",
    ]

    # Description (if present)
    if playlist.description:
        # Truncate long descriptions
        desc = playlist.description[:200]
        if len(playlist.description) > 200:
            desc += "..."
        details_lines.append(f"Description:    {desc}")
    else:
        details_lines.append("Description:    [dim](none)[/dim]")

    details_lines.extend(
        [
            f"Videos:         {playlist.video_count}",
            f"Privacy:        {playlist.privacy_status}",
        ]
    )

    # Channel info (if available)
    if hasattr(playlist, "channel") and playlist.channel:
        channel_info = f"{playlist.channel_id} ({playlist.channel.title})"
        details_lines.append(f"Channel:        {channel_info}")
    elif playlist.channel_id:
        details_lines.append(f"Channel:        {playlist.channel_id}")
    else:
        details_lines.append(
            "Channel:        (not linked - user playlist from Takeout)"
        )

    details_lines.extend(
        [
            f"Created:        {created_str}",
            "─" * 40,
        ]
    )

    # Print all details
    for line in details_lines:
        console.print(line)


async def _reclassify(
    session: AsyncSession,
    repository: PlaylistRepository,
    dry_run: bool,
) -> dict[str, int]:
    """Promote ``regular`` playlists to their classified system type.

    Promote-only (Feature 058, FR-006): only playlists currently typed
    ``regular`` are considered, so a playlist that already has a system type
    is never altered. Each promotion is an independent single-row update,
    making the operation interruption-safe (FR-009). Returns per-type counts
    of the rows that were (or, in dry-run, would be) promoted.

    Parameters
    ----------
    session : AsyncSession
        Database session.
    repository : PlaylistRepository
        Playlist repository.
    dry_run : bool
        When True, compute counts without writing.

    Returns
    -------
    dict[str, int]
        Mapping of resulting ``playlist_type`` value → number of playlists
        promoted to it.
    """
    regulars = await repository.get_playlists_by_type(session, PlaylistType.REGULAR)
    counts: dict[str, int] = {}
    for playlist in regulars:
        target = classify_playlist_type(playlist.playlist_id, playlist.title)
        if target is PlaylistType.REGULAR:
            continue
        counts[target.value] = counts.get(target.value, 0) + 1
        if not dry_run:
            await repository.promote_playlist_type(
                session, playlist.playlist_id, target
            )
    if not dry_run and counts:
        await session.commit()
    return counts


@playlist_app.command()
def hidden() -> None:
    """Show playlists hidden from the UI by ``deleted_flag``.

    Every other view filters these out, so without this command the only way
    to see them is a psql prompt. That is how an enrichment run once hid 288
    playlists for two months without anyone being able to name which ones.

    The "Hidden" column is approximate: it is the row's last-modified time,
    which for a hidden playlist is when it was hidden, because nothing writes
    to one afterwards.

    Examples:
        chronovista playlist hidden

    Exit Codes:
        0: Success
        2: System error - database failure
        3: Cancelled - Ctrl+C pressed
    """

    async def hidden_async() -> None:
        repository = PlaylistRepository()
        db_manager = DatabaseManager()

        try:
            async for session in db_manager.get_session(echo=False):
                playlists = await repository.get_hidden_playlists(session)

                if not playlists:
                    console.print("[green]No hidden playlists.[/green]")
                    sys.exit(EXIT_SUCCESS)

                table = Table(title=f"Hidden playlists ({len(playlists)})")
                table.add_column("Playlist ID", style="cyan", no_wrap=False)
                table.add_column("Title", style="white")
                table.add_column("Videos", justify="right", style="green")
                table.add_column("Hidden (approx)", style="dim")
                table.add_column("Privacy", justify="center")

                for playlist in playlists:
                    table.add_row(
                        _truncate_id(playlist.playlist_id),
                        playlist.title,
                        str(playlist.video_count),
                        playlist.updated_at.strftime("%Y-%m-%d"),
                        playlist.privacy_status,
                    )

                console.print(table)
                console.print(
                    "\n[dim]Restore with: chronovista playlist restore --all[/dim]"
                )
                sys.exit(EXIT_SUCCESS)

        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
            sys.exit(EXIT_CANCELLED)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Database error:[/red]\n{str(e)}",
                    title="Listing Failed",
                    border_style="red",
                )
            )
            sys.exit(EXIT_SYSTEM_ERROR)

    asyncio.run(hidden_async())


@playlist_app.command()
def restore(
    playlist_id: builtins.list[str] = typer.Option(
        [],
        "--id",
        help="Restore a specific playlist. Repeatable.",
    ),
    all_hidden: bool = typer.Option(
        False,
        "--all",
        help="Restore every hidden playlist.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be restored without writing.",
    ),
) -> None:
    """Un-hide playlists that were marked deleted.

    A playlist hidden by ``deleted_flag`` never comes back on its own:
    enrichment selects only live rows, so a hidden playlist leaves the
    population permanently. Until this command the only route back was a
    hand-written UPDATE (#149).

    Requires either --all or at least one --id, so that a bare `restore`
    cannot un-hide the entire library by accident.

    Examples:
        chronovista playlist restore --all
        chronovista playlist restore --id PLxxxx --id PLyyyy
        chronovista playlist restore --all --dry-run

    Exit Codes:
        0: Success
        1: User error - neither --all nor --id given, or both
        2: System error - database failure
        3: Cancelled - Ctrl+C pressed
    """
    if all_hidden and playlist_id:
        console.print(
            "[red]Use either --all or --id, not both.[/red]\n"
            "[dim]--all restores everything hidden; --id restores only what "
            "you name.[/dim]"
        )
        raise typer.Exit(EXIT_USER_ERROR)

    if not all_hidden and not playlist_id:
        console.print(
            "[red]Nothing to restore.[/red]\n"
            "[dim]Pass --all to restore every hidden playlist, or --id to "
            "name specific ones. Run 'chronovista playlist hidden' to see "
            "what is hidden.[/dim]"
        )
        raise typer.Exit(EXIT_USER_ERROR)

    async def restore_async() -> None:
        repository = PlaylistRepository()
        db_manager = DatabaseManager()

        try:
            async for session in db_manager.get_session(echo=False):
                hidden_playlists = await repository.get_hidden_playlists(session)
                hidden_ids = {p.playlist_id for p in hidden_playlists}

                if all_hidden:
                    targets = sorted(hidden_ids)
                    unknown: builtins.list[str] = []
                else:
                    targets = [pid for pid in playlist_id if pid in hidden_ids]
                    unknown = [pid for pid in playlist_id if pid not in hidden_ids]

                for pid in unknown:
                    console.print(
                        f"[yellow]Skipping {pid}: not hidden "
                        f"(already visible, or no such playlist).[/yellow]"
                    )

                if not targets:
                    console.print("[dim]Nothing to restore.[/dim]")
                    sys.exit(EXIT_SUCCESS)

                if dry_run:
                    console.print(
                        Panel(
                            "[bold]Restore (dry-run)[/bold] — no changes written",
                            border_style="yellow",
                        )
                    )
                    for pid in targets:
                        console.print(f"  would restore {pid}")
                    console.print(
                        f"\n[bold]Would restore {len(targets)} playlist(s).[/bold]\n"
                        "[dim]Re-run without --dry-run to apply.[/dim]"
                    )
                    sys.exit(EXIT_SUCCESS)

                restored = await repository.restore_playlists(session, targets)
                await session.commit()

                console.print(
                    f"[green]Restored {restored} playlist(s).[/green]\n"
                    "[dim]They will reappear in the UI immediately. If an "
                    "enrichment run hid them in error, fix the cause before "
                    "re-running it.[/dim]"
                )
                sys.exit(EXIT_SUCCESS)

        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
            sys.exit(EXIT_CANCELLED)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Database error:[/red]\n{str(e)}",
                    title="Restore Failed",
                    border_style="red",
                )
            )
            sys.exit(EXIT_SYSTEM_ERROR)

    asyncio.run(restore_async())


@playlist_app.command()
def reclassify(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would change without writing to the database.",
    ),
) -> None:
    """Reclassify existing ``regular`` playlists into their system type.

    Detects Watch Later, History, Liked Videos, and Favorites among playlists
    currently stored as ``regular`` and promotes them. Promote-only: playlists
    that already have a system type are never changed. Idempotent and safe to
    re-run.
    """

    async def reclassify_async() -> None:
        repository = PlaylistRepository()
        db_manager = DatabaseManager()

        try:
            async for session in db_manager.get_session(echo=False):
                counts = await _reclassify(session, repository, dry_run=dry_run)
                total = sum(counts.values())

                if dry_run:
                    console.print(
                        Panel(
                            "[bold]Reclassify (dry-run)[/bold] — no changes written",
                            border_style="yellow",
                        )
                    )
                else:
                    console.print(
                        Panel(
                            "[bold]Reclassify[/bold] — applied",
                            border_style="green",
                        )
                    )

                if total == 0:
                    console.print(
                        "[dim]No regular playlists matched a system type — "
                        "nothing to reclassify.[/dim]"
                    )
                    return

                table = Table(show_header=True, header_style="bold")
                table.add_column("Resulting type")
                table.add_column("Count", justify="right")
                for type_value, count in sorted(counts.items()):
                    table.add_row(type_value, str(count))
                console.print(table)

                verb = "Would update" if dry_run else "Updated"
                console.print(f"[bold]{verb} {total} playlist(s).[/bold]")
                if dry_run:
                    console.print("[dim]Re-run without --dry-run to apply.[/dim]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
            sys.exit(1)

    asyncio.run(reclassify_async())
