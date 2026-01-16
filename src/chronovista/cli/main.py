"""
Main CLI entry point for chronovista.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

from chronovista import __version__
from chronovista.cli.auth_commands import auth_app
from chronovista.cli.category_commands import category_app
from chronovista.cli.commands.enrich import app as enrich_app
from chronovista.cli.commands.playlist import playlist_app
from chronovista.cli.commands.seed import seed_app
from chronovista.cli.commands.takeout import takeout_app
from chronovista.cli.sync_commands import sync_app
from chronovista.cli.tag_commands import tag_app
from chronovista.cli.topic_commands import topic_app

console = Console()

app = typer.Typer(
    name="chronovista",
    help="Personal YouTube data analytics tool",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Add subcommands
app.add_typer(auth_app, name="auth", help="Authentication commands")
app.add_typer(
    category_app, name="categories", help="📂 Video category exploration (creator-assigned)"
)
app.add_typer(enrich_app, name="enrich", help="🔄 Enrich video metadata from YouTube API")
app.add_typer(playlist_app, name="playlist", help="📋 Playlist management commands")
app.add_typer(sync_app, name="sync", help="Data synchronization commands")
app.add_typer(seed_app, name="seed", help="🌱 Seed reference data into the database")
app.add_typer(tag_app, name="tags", help="🏷️ Video tag exploration and analytics")
app.add_typer(
    takeout_app, name="takeout", help="📁 Explore Google Takeout data locally"
)
app.add_typer(topic_app, name="topics", help="📂 Topic exploration and analytics")


@app.command()
def version() -> None:
    """Show version information."""
    console.print(
        Panel(
            f"[bold blue]chronovista[/bold blue] v{__version__}",
            title="Version",
            border_style="blue",
        )
    )


@app.command()
def status() -> None:
    """Show application status."""
    console.print(
        Panel(
            "[green]✓[/green] chronovista is ready to use\n"
            "[yellow]![/yellow] Use 'chronovista auth login' to authenticate\n"
            "[blue]i[/blue] Use 'chronovista --help' for available commands",
            title="Status",
            border_style="green",
        )
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit"
    ),
) -> None:
    """
    chronovista - Personal YouTube data analytics tool.

    Access, analyze, and export your personal YouTube data including
    watch history, playlists, transcripts, and engagement metrics.
    """
    if version:
        console.print(f"chronovista v{__version__}")
        raise typer.Exit(code=0)

    if ctx.invoked_subcommand is None:
        console.print(
            "[yellow]Use 'chronovista --help' for available commands[/yellow]"
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
