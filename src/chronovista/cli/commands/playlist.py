"""
Playlist CLI commands for chronovista.

This module provides commands for managing playlist YouTube ID linking:
- `link`: Link internal playlist to YouTube playlist ID
- `unlink`: Remove YouTube ID link from playlist
- `list`: Display playlists with link status
- `show`: Show detailed playlist information

All commands support proper exit codes, confirmation prompts, and error handling.
"""

from __future__ import annotations

import asyncio
import json
import sys
from enum import Enum
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from chronovista.cli.constants import (
    EXIT_CANCELLED,
    EXIT_SUCCESS,
    EXIT_SYSTEM_ERROR,
    EXIT_USER_ERROR,
)
from chronovista.cli.errors import (
    ErrorCategory,
    display_error_panel,
    display_success_panel,
    format_conflict_error,
    format_not_found_error,
    format_validation_error,
    get_exit_code_for_category,
)
from chronovista.config.database import DatabaseManager
from chronovista.db.models import Playlist as PlaylistDB
from chronovista.models.youtube_types import (
    is_internal_playlist_id,
    validate_playlist_id,
    validate_youtube_id_format,
)
from chronovista.repositories.playlist_repository import PlaylistRepository

console = Console()


class OutputFormat(str, Enum):
    """Output format options for playlist commands."""
    TABLE = "table"
    JSON = "json"
    CSV = "csv"


class SortOrder(str, Enum):
    """Sort order options for playlist list command."""
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
def link(
    internal_id: str = typer.Argument(
        ...,
        help="Internal playlist ID (INT_ prefix)",
    ),
    youtube_id: str = typer.Argument(
        ...,
        help="YouTube playlist ID (PL prefix)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing link if YouTube ID already linked to another playlist",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
) -> None:
    """
    Link internal playlist to YouTube playlist ID.

    Associates a local playlist (from Takeout) with its real YouTube playlist ID.
    This enables two-way lookup and proper attribution.

    Examples:
        chronovista playlist link INT_7f37ed8c... PLdU2XMVb99x...
        chronovista playlist link INT_7f37ed8c... PLdU2XMVb99x... --force
        chronovista playlist link INT_7f37ed8c... PLdU2XMVb99x... --yes

    Exit Codes:
        0: Success - playlist linked successfully
        1: User error - invalid ID format, playlist not found, or conflict
        2: System error - database failure
        3: Cancelled - user cancelled operation or Ctrl+C pressed
    """

    async def link_playlist_async() -> None:
        """Async implementation of playlist linking."""
        repository = PlaylistRepository()
        db_manager = DatabaseManager()

        try:
            # Step 1: Validate internal_id format (cheapest check first)
            try:
                validate_playlist_id(internal_id)
                if not is_internal_playlist_id(internal_id):
                    error_msg = format_validation_error(
                        "internal_id",
                        "Must be internal playlist ID",
                        expected="INT_ prefix followed by 32 lowercase hex characters",
                        got=internal_id,
                    )
                    console.print(f"[red]{error_msg}[/red]")
                    sys.exit(EXIT_USER_ERROR)
            except (ValueError, TypeError) as e:
                error_msg = format_validation_error(
                    "internal_id",
                    str(e),
                    expected="INT_ prefix followed by 32 lowercase hex characters",
                    got=internal_id,
                )
                console.print(f"[red]{error_msg}[/red]")
                sys.exit(EXIT_USER_ERROR)

            # Step 2: Validate youtube_id format
            try:
                validate_youtube_id_format(youtube_id)
            except (ValueError, TypeError) as e:
                error_msg = format_validation_error(
                    "youtube_id",
                    str(e),
                    expected="PL prefix followed by 28-48 alphanumeric characters",
                    got=youtube_id,
                )
                console.print(f"[red]{error_msg}[/red]")
                sys.exit(EXIT_USER_ERROR)

            # Step 3: Check playlist existence and get details for confirmation
            async for session in db_manager.get_session(echo=False):
                playlist = await repository.get(session, internal_id)

                if not playlist:
                    error_msg = format_not_found_error("Playlist", internal_id)
                    console.print(f"[red]{error_msg}[/red]")
                    sys.exit(EXIT_USER_ERROR)

                # Step 4: Check for conflicts (youtube_id already linked)
                existing_linked = await repository.get_by_youtube_id(session, youtube_id)
                if (
                    existing_linked
                    and existing_linked.playlist_id != internal_id
                    and not force
                ):
                    error_msg = format_conflict_error(
                        f'YouTube ID {youtube_id} is already linked to playlist "{existing_linked.title}" ({existing_linked.playlist_id})',
                        hint="Use --force to update the link, or unlink from the other playlist first.",
                    )
                    console.print(f"[red]{error_msg}[/red]")
                    sys.exit(EXIT_USER_ERROR)

                # Step 5: Show confirmation prompt (unless --yes)
                if not yes:
                    # Display playlist details in a panel
                    details = (
                        f'[cyan]Playlist:[/cyan]   "{playlist.title}"\n'
                        f"[cyan]Internal ID:[/cyan] {playlist.playlist_id}\n"
                        f"[cyan]YouTube ID:[/cyan]  {youtube_id}\n"
                        f"[cyan]Videos:[/cyan]      {playlist.video_count}"
                    )

                    console.print(
                        Panel(
                            details,
                            title="Link Playlist",
                            border_style="blue",
                        )
                    )

                    # Ask for confirmation
                    confirmed = Confirm.ask(
                        "Link this playlist to the YouTube ID?", default=False
                    )

                    if not confirmed:
                        console.print("[yellow]Operation cancelled[/yellow]")
                        sys.exit(EXIT_CANCELLED)

                # Step 6: Perform the linking
                try:
                    await repository.link_youtube_id(
                        session, internal_id, youtube_id, force=force
                    )
                    await session.commit()

                    # Step 7: Display success message
                    success_info = (
                        f"[dim]Internal ID:[/dim] {internal_id}\n"
                        f"[dim]YouTube ID:[/dim]  {youtube_id}"
                    )

                    display_success_panel(
                        f'Linked playlist "{playlist.title}"',
                        title="Link Complete",
                        extra_info=success_info,
                    )

                    sys.exit(EXIT_SUCCESS)

                except ValueError as e:
                    # Handle repository-level errors
                    error_msg = format_validation_error("link_operation", str(e))
                    console.print(f"[red]{error_msg}[/red]")
                    sys.exit(EXIT_USER_ERROR)

        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
            sys.exit(EXIT_CANCELLED)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Database error:[/red]\n{str(e)}",
                    title="Link Failed",
                    border_style="red",
                )
            )
            sys.exit(EXIT_SYSTEM_ERROR)

    # Run the async function
    asyncio.run(link_playlist_async())


@playlist_app.command()
def unlink(
    playlist_id: str = typer.Argument(
        ...,
        help="Internal playlist ID (INT_ prefix)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
) -> None:
    """
    Remove YouTube ID link from playlist.

    Unlinks a playlist from its YouTube ID, keeping only the internal ID.
    This does not delete the playlist, only removes the YouTube ID reference.

    Examples:
        chronovista playlist unlink INT_7f37ed8c...
        chronovista playlist unlink INT_7f37ed8c... --yes

    Exit Codes:
        0: Success - playlist unlinked successfully or already unlinked
        1: User error - invalid ID format or playlist not found
        2: System error - database failure
        3: Cancelled - user cancelled operation or Ctrl+C pressed
    """

    async def unlink_playlist_async() -> None:
        """Async implementation of playlist unlinking."""
        repository = PlaylistRepository()
        db_manager = DatabaseManager()

        try:
            # Step 1: Validate playlist_id format
            try:
                validate_playlist_id(playlist_id)
                if not is_internal_playlist_id(playlist_id):
                    error_msg = format_validation_error(
                        "playlist_id",
                        "Must be internal playlist ID",
                        expected="INT_ prefix followed by 32 lowercase hex characters",
                        got=playlist_id,
                    )
                    console.print(f"[red]{error_msg}[/red]")
                    sys.exit(EXIT_USER_ERROR)
            except (ValueError, TypeError) as e:
                error_msg = format_validation_error(
                    "playlist_id",
                    str(e),
                    expected="INT_ prefix followed by 32 lowercase hex characters",
                    got=playlist_id,
                )
                console.print(f"[red]{error_msg}[/red]")
                sys.exit(EXIT_USER_ERROR)

            # Step 2: Get playlist details
            async for session in db_manager.get_session(echo=False):
                playlist = await repository.get(session, playlist_id)

                if not playlist:
                    error_msg = format_not_found_error("Playlist", playlist_id)
                    console.print(f"[red]{error_msg}[/red]")
                    sys.exit(EXIT_USER_ERROR)

                # Check if playlist has a YouTube ID to unlink
                if not playlist.youtube_id:
                    console.print(
                        f'[yellow]Playlist "{playlist.title}" is not linked to a YouTube ID[/yellow]'
                    )
                    sys.exit(EXIT_SUCCESS)

                # Store youtube_id for display after unlinking
                current_youtube_id = playlist.youtube_id

                # Step 3: Show confirmation prompt (unless --yes)
                if not yes:
                    details = (
                        f'[cyan]Playlist:[/cyan]   "{playlist.title}"\n'
                        f"[cyan]Internal ID:[/cyan] {playlist.playlist_id}\n"
                        f"[cyan]Current YouTube ID:[/cyan] {playlist.youtube_id}"
                    )

                    console.print(
                        Panel(
                            details,
                            title="Unlink Playlist",
                            border_style="yellow",
                        )
                    )

                    confirmed = Confirm.ask(
                        "Remove the YouTube ID link from this playlist?", default=False
                    )

                    if not confirmed:
                        console.print("[yellow]Operation cancelled[/yellow]")
                        sys.exit(EXIT_CANCELLED)

                # Step 4: Perform the unlinking
                try:
                    await repository.unlink_youtube_id(session, playlist_id)
                    await session.commit()

                    # Step 5: Display success message
                    display_success_panel(
                        f'Unlinked playlist "{playlist.title}" from YouTube ID {current_youtube_id}',
                        title="Unlink Complete",
                    )

                    sys.exit(EXIT_SUCCESS)

                except ValueError as e:
                    error_msg = format_validation_error("unlink_operation", str(e))
                    console.print(f"[red]{error_msg}[/red]")
                    sys.exit(EXIT_USER_ERROR)

        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
            sys.exit(EXIT_CANCELLED)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Database error:[/red]\n{str(e)}",
                    title="Unlink Failed",
                    border_style="red",
                )
            )
            sys.exit(EXIT_SYSTEM_ERROR)

    # Run the async function
    asyncio.run(unlink_playlist_async())


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
    sort: SortOrder = typer.Option(
        SortOrder.TITLE,
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
                    playlists = await repository.get_recent_playlists(session, limit=limit)
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
                    playlists = await repository.get_recent_playlists(session, limit=limit)

                # Get statistics for summary
                stats = await repository.get_link_statistics(session)

                # Apply sorting based on --sort flag
                if sort == SortOrder.TITLE:
                    # Alphabetical by title (A-Z)
                    playlists = sorted(playlists, key=lambda p: p.title.lower())
                elif sort == SortOrder.VIDEOS:
                    # By video count (descending)
                    playlists = sorted(playlists, key=lambda p: p.video_count, reverse=True)
                elif sort == SortOrder.STATUS:
                    # Linked first, then unlinked, then alphabetical within each group
                    playlists = sorted(
                        playlists,
                        key=lambda p: (p.youtube_id is None, p.title.lower())
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

                # Check if it's an internal ID
                if is_internal_playlist_id(playlist_id):
                    playlist = await repository.get_with_channel(session, playlist_id)
                else:
                    # Try as YouTube ID
                    try:
                        validate_youtube_id_format(playlist_id)
                        playlist = await repository.get_by_youtube_id(session, playlist_id)
                        if playlist:
                            # Load channel relationship
                            await session.refresh(playlist, ["channel"])
                    except (ValueError, TypeError):
                        # Not a valid YouTube ID format, fall through to error
                        pass

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
    return playlist_id[:max_length - 3] + "..."


def _output_table(playlists: List[PlaylistDB], stats: Dict[str, int], limit: int) -> None:
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

        # Status with emoji
        status = "✅ Linked" if playlist.youtube_id else "❌ Unlinked"

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


def _output_json(playlists: List[PlaylistDB], stats: Dict[str, int]) -> None:
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
                "youtube_id": p.youtube_id,
                "title": p.title,
                "video_count": p.video_count,
                "linked": p.youtube_id is not None,
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


def _output_csv(playlists: List[PlaylistDB], stats: Dict[str, int]) -> None:
    """
    Output playlists in CSV format.

    Args:
        playlists: List of playlist database objects
        stats: Dictionary with total/linked/unlinked counts
    """
    # CSV header
    console.print("playlist_id,youtube_id,title,video_count,linked")

    # CSV rows
    for p in playlists:
        youtube_id = p.youtube_id if p.youtube_id else ""
        linked = "true" if p.youtube_id else "false"
        # Escape title for CSV (quote if contains comma)
        title = f'"{p.title}"' if "," in p.title else p.title
        console.print(f"{p.playlist_id},{youtube_id},{title},{p.video_count},{linked}")

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

    # Build details string
    details_lines = [
        "Playlist Details",
        "─" * 40,
        f"Internal ID:    {playlist.playlist_id}",
    ]

    # YouTube ID (if linked)
    if playlist.youtube_id:
        details_lines.append(f"YouTube ID:     {playlist.youtube_id}")
    else:
        details_lines.append("YouTube ID:     [dim](not linked)[/dim]")

    details_lines.extend([
        f"Title:          {playlist.title}",
    ])

    # Description (if present)
    if playlist.description:
        # Truncate long descriptions
        desc = playlist.description[:200]
        if len(playlist.description) > 200:
            desc += "..."
        details_lines.append(f"Description:    {desc}")
    else:
        details_lines.append("Description:    [dim](none)[/dim]")

    details_lines.extend([
        f"Videos:         {playlist.video_count}",
        f"Privacy:        {playlist.privacy_status}",
    ])

    # Channel info (if available)
    if hasattr(playlist, "channel") and playlist.channel:
        channel_info = f"{playlist.channel_id} ({playlist.channel.title})"
        details_lines.append(f"Channel:        {channel_info}")
    else:
        details_lines.append(f"Channel:        {playlist.channel_id}")

    details_lines.extend([
        f"Created:        {created_str}",
        "─" * 40,
    ])

    # Print all details
    for line in details_lines:
        console.print(line)
