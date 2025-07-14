"""
Data synchronization CLI commands for chronovista.
"""

from __future__ import annotations
import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.json import JSON

from chronovista.auth import youtube_oauth
from chronovista.services import youtube_service

console = Console()

sync_app = typer.Typer(
    name="sync",
    help="Data synchronization commands",
    no_args_is_help=True,
)


@sync_app.command()
def history() -> None:
    """Sync watch history from YouTube."""
    console.print(
        Panel(
            "[yellow]Watch history sync not yet implemented[/yellow]\n"
            "This will fetch and store your YouTube watch history.",
            title="Sync History",
            border_style="yellow",
        )
    )


@sync_app.command()
def playlists() -> None:
    """Sync playlists from YouTube."""
    console.print(
        Panel(
            "[yellow]Playlist sync not yet implemented[/yellow]\n"
            "This will fetch and store your YouTube playlists.",
            title="Sync Playlists",
            border_style="yellow",
        )
    )


@sync_app.command()
def transcripts() -> None:
    """Sync transcripts for videos."""
    console.print(
        Panel(
            "[yellow]Transcript sync not yet implemented[/yellow]\n"
            "This will download transcripts for your videos.",
            title="Sync Transcripts",
            border_style="yellow",
        )
    )


@sync_app.command()
def all() -> None:
    """Sync all data (full synchronization)."""
    console.print(
        Panel(
            "[yellow]Full sync not yet implemented[/yellow]\n"
            "This will perform a complete data synchronization.",
            title="Full Sync",
            border_style="yellow",
        )
    )


@sync_app.command()
def channel() -> None:
    """Test: Fetch your channel information from YouTube API."""
    try:
        # Check authentication
        if not youtube_oauth.is_authenticated():
            console.print(
                Panel(
                    "[red]❌ Not authenticated[/red]\n"
                    "Use [bold]chronovista auth login[/bold] to sign in first.",
                    title="Channel Sync",
                    border_style="red",
                )
            )
            return

        console.print("[blue]🔄 Fetching your YouTube channel information...[/blue]")
        
        # Fetch channel data
        channel_data = asyncio.run(youtube_service.get_my_channel())
        
        # Create channel info table
        table = Table(title="Your YouTube Channel")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        snippet = channel_data.get("snippet", {})
        statistics = channel_data.get("statistics", {})
        
        table.add_row("Channel ID", channel_data.get("id", "Unknown"))
        table.add_row("Title", snippet.get("title", "Unknown"))
        table.add_row("Description", snippet.get("description", "No description")[:100] + "..." if len(snippet.get("description", "")) > 100 else snippet.get("description", "No description"))
        table.add_row("Created", snippet.get("publishedAt", "Unknown"))
        table.add_row("Subscriber Count", statistics.get("subscriberCount", "Unknown"))
        table.add_row("Video Count", statistics.get("videoCount", "Unknown"))
        table.add_row("View Count", statistics.get("viewCount", "Unknown"))
        table.add_row("Country", snippet.get("country", "Unknown"))
        table.add_row("Default Language", snippet.get("defaultLanguage", "Unknown"))

        console.print(table)
        
        console.print(
            Panel(
                "[green]✅ Successfully fetched channel data![/green]\n"
                "YouTube API integration is working correctly.",
                title="Channel Sync Complete",
                border_style="green",
            )
        )

    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ Failed to fetch channel data:[/red]\n{str(e)}",
                title="Channel Sync Error",
                border_style="red",
            )
        )
