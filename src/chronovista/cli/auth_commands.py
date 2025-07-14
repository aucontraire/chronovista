"""
Authentication CLI commands for chronovista.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()

auth_app = typer.Typer(
    name="auth",
    help="Authentication commands",
    no_args_is_help=True,
)


@auth_app.command()
def login() -> None:
    """Login to your YouTube account."""
    console.print(
        Panel(
            "[yellow]Authentication not yet implemented[/yellow]\n"
            "This will start the OAuth 2.0 flow to authenticate with YouTube.",
            title="Login",
            border_style="yellow",
        )
    )


@auth_app.command()
def logout() -> None:
    """Logout and clear stored credentials."""
    console.print(
        Panel(
            "[yellow]Logout not yet implemented[/yellow]\n"
            "This will clear stored authentication credentials.",
            title="Logout",
            border_style="yellow",
        )
    )


@auth_app.command()
def status() -> None:
    """Check authentication status."""
    console.print(
        Panel(
            "[yellow]Authentication status check not yet implemented[/yellow]\n"
            "This will show whether you are currently authenticated.",
            title="Auth Status",
            border_style="yellow",
        )
    )


@auth_app.command()
def refresh() -> None:
    """Refresh authentication tokens."""
    console.print(
        Panel(
            "[yellow]Token refresh not yet implemented[/yellow]\n"
            "This will refresh your authentication tokens.",
            title="Refresh",
            border_style="yellow",
        )
    )
