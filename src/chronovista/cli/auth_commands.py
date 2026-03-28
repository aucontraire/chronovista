"""
Authentication CLI commands for chronovista.
"""

from __future__ import annotations

from datetime import UTC

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chronovista.auth import youtube_oauth

console = Console()

auth_app = typer.Typer(
    name="auth",
    help="Authentication commands",
    no_args_is_help=True,
)


@auth_app.command()
def login() -> None:
    """Login to your YouTube account."""
    try:
        # Check if already authenticated with valid token
        if youtube_oauth.is_authenticated():
            console.print(
                Panel(
                    "[green]✅ Already authenticated![/green]\n"
                    "Use [bold]chronovista auth status[/bold] to see details.\n"
                    "Use [bold]chronovista auth logout[/bold] to sign out.",
                    title="Authentication Status",
                    border_style="green",
                )
            )
            return

        # Check if we have expired credentials that might be refreshable
        try:
            token_info = youtube_oauth.get_token_info()
            if (
                token_info
                and not token_info["valid"]
                and token_info["has_refresh_token"]
            ):
                console.print(
                    "[yellow]🔄 Found expired token with refresh capability. Attempting to refresh...[/yellow]"
                )

                # Try to refresh the token
                try:
                    youtube_oauth.get_authenticated_service()  # This triggers refresh
                    console.print(
                        Panel(
                            "[green]✅ Token refreshed successfully![/green]\n"
                            "You are now authenticated and ready to use YouTube API commands.",
                            title="Login Complete",
                            border_style="green",
                        )
                    )
                    return
                except Exception as refresh_error:
                    console.print(
                        f"[yellow]⚠️ Token refresh failed: {refresh_error}[/yellow]\n"
                        "[blue]Proceeding with fresh authentication...[/blue]"
                    )
        except Exception:
            # If token info fails, just proceed with fresh auth
            pass

        console.print(
            Panel(
                "[blue]🔐 Starting YouTube OAuth authentication...[/blue]\n"
                "You will be redirected to Google to authorize chronovista.",
                title="YouTube Login",
                border_style="blue",
            )
        )

        # Perform interactive authentication
        token_info = youtube_oauth.authorize_interactive()

        # Format expiration time
        expires_str = "Unknown"
        if token_info.get("expires_in"):
            try:
                from datetime import datetime

                expires_timestamp = float(token_info["expires_in"])
                expires_dt = datetime.fromtimestamp(expires_timestamp, tz=UTC)
                expires_str = expires_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except (ValueError, TypeError):
                expires_str = str(token_info["expires_in"])

        console.print(
            Panel(
                "[green]✅ Authentication successful![/green]\n"
                f"Access token expires: {expires_str}\n"
                f"Scopes: {token_info.get('scope', 'Unknown')}\n\n"
                "You can now use YouTube API commands.",
                title="Login Complete",
                border_style="green",
            )
        )

    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ Authentication failed:[/red]\n{str(e)}",
                title="Login Error",
                border_style="red",
            )
        )


@auth_app.command()
def logout() -> None:
    """Logout and clear stored credentials."""
    try:
        if not youtube_oauth.is_authenticated():
            console.print(
                Panel(
                    "[yellow]ℹ️ Not currently authenticated[/yellow]\n"
                    "Use [bold]chronovista auth login[/bold] to sign in.",
                    title="Logout",
                    border_style="yellow",
                )
            )
            return

        # Confirm logout
        confirm = typer.confirm(
            "Are you sure you want to logout and delete stored credentials?"
        )
        if not confirm:
            console.print("[yellow]Logout cancelled.[/yellow]")
            return

        # Revoke credentials
        youtube_oauth.revoke_credentials()

        console.print(
            Panel(
                "[green]✅ Successfully logged out![/green]\n"
                "All stored credentials have been removed.\n"
                "Use [bold]chronovista auth login[/bold] to sign in again.",
                title="Logout Complete",
                border_style="green",
            )
        )

    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ Logout failed:[/red]\n{str(e)}",
                title="Logout Error",
                border_style="red",
            )
        )


@auth_app.command()
def status() -> None:
    """Check authentication status."""
    try:
        if not youtube_oauth.is_authenticated():
            console.print(
                Panel(
                    "[red]❌ Not authenticated[/red]\n"
                    "Use [bold]chronovista auth login[/bold] to sign in.",
                    title="Authentication Status",
                    border_style="red",
                )
            )
            return

        # Get detailed token info
        token_info = youtube_oauth.get_token_info()
        if not token_info:
            console.print(
                Panel(
                    "[red]❌ No token information available[/red]",
                    title="Authentication Status",
                    border_style="red",
                )
            )
            return

        # Create status table
        table = Table(title="Authentication Details")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        # Format expiration time
        expires_str = "Unknown"
        if token_info.get("expires_at"):
            try:
                from datetime import datetime

                expires_dt = datetime.fromisoformat(
                    token_info["expires_at"].replace("Z", "+00:00")
                )
                expires_str = expires_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except (ValueError, TypeError):
                expires_str = token_info["expires_at"]

        table.add_row(
            "Status", "✅ Authenticated" if token_info["valid"] else "⚠️ Token Expired"
        )
        table.add_row("Token Valid", "Yes" if token_info["valid"] else "No")
        table.add_row(
            "Has Refresh Token", "Yes" if token_info["has_refresh_token"] else "No"
        )
        table.add_row("Expires At", expires_str)
        table.add_row("Scopes", ", ".join(token_info.get("scopes", [])))

        console.print(table)

        if not token_info["valid"] and token_info["has_refresh_token"]:
            console.print(
                Panel(
                    "[yellow]⚠️ Token expired but may be refreshable[/yellow]\n"
                    "Use [bold]chronovista auth refresh[/bold] to attempt token refresh.\n"
                    "If refresh fails, use [bold]chronovista auth login[/bold] for fresh authentication.",
                    border_style="yellow",
                )
            )
        elif not token_info["valid"]:
            console.print(
                Panel(
                    "[red]❌ Token expired and cannot be refreshed[/red]\n"
                    "Use [bold]chronovista auth login[/bold] to authenticate again.",
                    border_style="red",
                )
            )

    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ Status check failed:[/red]\n{str(e)}",
                title="Status Error",
                border_style="red",
            )
        )


@auth_app.command()
def refresh() -> None:
    """Refresh authentication tokens."""
    try:
        if not youtube_oauth.is_authenticated():
            console.print(
                Panel(
                    "[red]❌ Not authenticated[/red]\n"
                    "Use [bold]chronovista auth login[/bold] to sign in first.",
                    title="Refresh Tokens",
                    border_style="red",
                )
            )
            return

        # Get authenticated service (this will trigger refresh if needed)
        console.print("[blue]🔄 Refreshing authentication tokens...[/blue]")
        youtube_oauth.get_authenticated_service()

        console.print(
            Panel(
                "[green]✅ Tokens refreshed successfully![/green]\n"
                "Your authentication is now up to date.",
                title="Refresh Complete",
                border_style="green",
            )
        )

    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ Token refresh failed:[/red]\n{str(e)}\n\n"
                "You may need to re-authenticate using [bold]chronovista auth login[/bold].",
                title="Refresh Error",
                border_style="red",
            )
        )
