"""
Base infrastructure for sync commands.

Provides:
- SyncResult: Pydantic model for tracking sync operation results
- require_auth: Decorator/function for authentication checks
- run_sync_operation: Wrapper for asyncio.run with error handling
"""

from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, Awaitable, Callable, Coroutine, Optional, TypeVar, cast

from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chronovista.auth import youtube_oauth

# Type variable for generic async function return type
T = TypeVar("T")

# Module-level console for sync commands
console = Console()


class SyncResult(BaseModel):
    """
    Result of a sync operation.

    Tracks created, updated, and failed counts along with error messages.
    Mirrors the pattern from seeding/base_seeder.py SeedResult.

    Attributes
    ----------
    created : int
        Number of items created.
    updated : int
        Number of items updated.
    skipped : int
        Number of items skipped (already up-to-date).
    failed : int
        Number of items that failed to process.
    errors : list[str]
        List of error messages.
    """

    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def total_processed(self) -> int:
        """Total items processed (excluding skipped)."""
        return self.created + self.updated + self.failed

    @property
    def total_successful(self) -> int:
        """Total items successfully processed."""
        return self.created + self.updated

    @property
    def success_rate(self) -> float:
        """
        Success rate as percentage.

        Returns
        -------
        float
            Percentage of successful operations (0-100).
        """
        if self.total_processed == 0:
            return 100.0
        return (self.total_successful / self.total_processed) * 100.0

    def merge(self, other: SyncResult) -> SyncResult:
        """
        Merge another SyncResult into this one.

        Parameters
        ----------
        other : SyncResult
            Another sync result to merge.

        Returns
        -------
        SyncResult
            A new SyncResult with combined counts.
        """
        return SyncResult(
            created=self.created + other.created,
            updated=self.updated + other.updated,
            skipped=self.skipped + other.skipped,
            failed=self.failed + other.failed,
            errors=self.errors + other.errors,
        )

    def add_error(self, error: str) -> None:
        """Add an error message and increment failed count."""
        self.errors.append(error)
        self.failed += 1


def check_authenticated() -> bool:
    """
    Check if the user is authenticated with YouTube.

    Returns
    -------
    bool
        True if authenticated, False otherwise.
    """
    return youtube_oauth.is_authenticated()


def display_auth_error(command_name: str = "Sync") -> None:
    """
    Display authentication error panel.

    Parameters
    ----------
    command_name : str
        Name of the command to display in the panel title.
    """
    console.print(
        Panel(
            "[red]❌ Not authenticated[/red]\n"
            "Use [bold]chronovista auth login[/bold] to sign in first.",
            title=f"{command_name} - Authentication Required",
            border_style="red",
        )
    )


def require_auth(command_name: str = "Sync") -> Callable[[Callable[..., T]], Callable[..., Optional[T]]]:
    """
    Decorator that checks authentication before running a sync command.

    Parameters
    ----------
    command_name : str
        Name of the command for error display.

    Returns
    -------
    Callable
        Decorated function that checks auth before execution.

    Examples
    --------
    >>> @require_auth("Sync Topics")
    ... async def sync_topics():
    ...     # This only runs if authenticated
    ...     pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Optional[T]:
            if not check_authenticated():
                display_auth_error(command_name)
                return None
            return func(*args, **kwargs)

        return wrapper

    return decorator


def run_sync_operation(
    async_fn: Callable[[], Awaitable[T]],
    operation_name: str = "Sync",
) -> Optional[T]:
    """
    Run an async sync operation with standardized error handling.

    Wraps asyncio.run() with consistent error handling and display.

    Parameters
    ----------
    async_fn : Callable[[], Awaitable[T]]
        Async function to run.
    operation_name : str
        Name of the operation for error messages.

    Returns
    -------
    Optional[T]
        Result of the async function, or None if an error occurred.

    Examples
    --------
    >>> async def sync_data():
    ...     return await fetch_and_save()
    >>> result = run_sync_operation(sync_data, "Sync Topics")
    """
    try:
        coro = async_fn()
        # Cast to Coroutine for asyncio.run type compatibility
        return asyncio.run(cast(Coroutine[Any, Any, T], coro))
    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ {operation_name} failed:[/red]\n{str(e)}",
                title=f"{operation_name} Error",
                border_style="red",
            )
        )
        return None


def display_sync_results(
    result: SyncResult,
    title: str = "Sync Results",
    show_table: bool = True,
    extra_info: Optional[str] = None,
) -> None:
    """
    Display sync results in a standardized format.

    Parameters
    ----------
    result : SyncResult
        The sync result to display.
    title : str
        Title for the results display.
    show_table : bool
        Whether to show the detailed table.
    extra_info : Optional[str]
        Additional info to show after the panel.
    """
    if show_table:
        table = Table(title=title)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green")

        table.add_row("Created", str(result.created))
        table.add_row("Updated", str(result.updated))
        if result.skipped > 0:
            table.add_row("Skipped", str(result.skipped))
        if result.failed > 0:
            table.add_row("Failed", str(result.failed))
        table.add_row("Total Processed", str(result.total_processed))

        console.print(table)

    # Display summary panel
    if result.failed == 0:
        panel_content = (
            f"[green]✅ {title} completed successfully![/green]\n"
            f"Created: {result.created} | Updated: {result.updated}"
        )
        if result.skipped > 0:
            panel_content += f" | Skipped: {result.skipped}"
        border_style = "green"
        panel_title = "Sync Complete"
    else:
        panel_content = (
            f"[yellow]⚠️ {title} completed with {result.failed} errors[/yellow]\n"
            f"Successfully processed: {result.total_successful} items"
        )
        border_style = "yellow"
        panel_title = "Sync Complete with Errors"

    if extra_info:
        panel_content += f"\n\n{extra_info}"

    console.print(
        Panel(
            panel_content,
            title=panel_title,
            border_style=border_style,
        )
    )

    # Show errors if any
    if result.errors:
        console.print("\n[red]Errors:[/red]")
        for i, error in enumerate(result.errors[:10], 1):  # Show first 10 errors
            console.print(f"  {i}. {error}")
        if len(result.errors) > 10:
            console.print(f"  ... and {len(result.errors) - 10} more errors")


def display_progress_start(message: str, title: str = "Sync") -> None:
    """
    Display a sync operation start message.

    Parameters
    ----------
    message : str
        The message to display.
    title : str
        Title for the panel.
    """
    console.print(
        Panel(
            f"[blue]🔄 {message}[/blue]",
            title=title,
            border_style="blue",
        )
    )


def display_error(message: str, title: str = "Error") -> None:
    """
    Display an error message panel.

    Parameters
    ----------
    message : str
        Error message to display.
    title : str
        Title for the panel.
    """
    console.print(
        Panel(
            f"[red]❌ {message}[/red]",
            title=title,
            border_style="red",
        )
    )


def display_warning(message: str, title: str = "Warning") -> None:
    """
    Display a warning message panel.

    Parameters
    ----------
    message : str
        Warning message to display.
    title : str
        Title for the panel.
    """
    console.print(
        Panel(
            f"[yellow]⚠️ {message}[/yellow]",
            title=title,
            border_style="yellow",
        )
    )


def display_success(message: str) -> None:
    """
    Display a success message (no panel).

    Parameters
    ----------
    message : str
        Success message to display.
    """
    console.print(f"[green]✅ {message}[/green]")
