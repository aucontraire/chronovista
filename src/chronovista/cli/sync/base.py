"""
Base infrastructure for sync commands.

Provides:
- SyncResult: Pydantic model for tracking sync operation results
- require_auth: Decorator/function for authentication checks
- run_sync_operation: Wrapper for asyncio.run with error handling
- Error handling for authentication, network, and database failures (Phase 9)
"""

from __future__ import annotations

import asyncio
import logging
from functools import wraps
from typing import Any, Awaitable, Callable, Coroutine, Optional, TypeVar, cast

import typer
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy.exc import SQLAlchemyError

from chronovista.auth import youtube_oauth

# Type variable for generic async function return type
T = TypeVar("T")

# Module-level console for sync commands
console = Console()

# Logger for sync operations
logger = logging.getLogger(__name__)

# =============================================================================
# Exit Codes (Phase 9 - T061-T064)
# =============================================================================
EXIT_SUCCESS = 0
EXIT_USER_ERROR = 1
EXIT_AUTH_FAILURE = 2  # T061: Authentication failure (401/403)
EXIT_NETWORK_ERROR = 3  # T062: Network errors (ConnectionError, TimeoutError)
EXIT_QUOTA_EXCEEDED = 3  # Quota exceeded uses same exit code as network
EXIT_DATABASE_ERROR = 5  # T063: Database errors (SQLAlchemy failures)


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
    Implements Phase 9 error handling (T061-T064) with appropriate exit codes:
    - Exit 2: Authentication failure (401/403)
    - Exit 3: Network errors
    - Exit 5: Database errors

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

    Raises
    ------
    typer.Exit
        With appropriate exit code based on error type.

    Examples
    --------
    >>> async def sync_data():
    ...     return await fetch_and_save()
    >>> result = run_sync_operation(sync_data, "Sync Topics")
    """
    try:
        coro = async_fn()
        # Cast to Coroutine for asyncio.run type compatibility
        coro_typed = cast(Coroutine[Any, Any, T], coro)

        # Check if we're already in an async context (e.g., pytest-asyncio tests)
        try:
            loop = asyncio.get_running_loop()
            # Event loop is already running, use nest_asyncio pattern
            # Create a new thread to run the coroutine
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro_typed)
                return future.result()
        except RuntimeError:
            # No running event loop, use asyncio.run normally
            return asyncio.run(coro_typed)

    except HttpError as e:
        # T061: Handle authentication failures (401/403)
        status_code = e.resp.status if e.resp else 0

        if status_code in (401, 403):
            # Check if it's a quota error (403 with quota reason)
            is_quota_error = False
            try:
                error_content = e.content.decode("utf-8") if e.content else ""
                quota_reasons = {"quotaExceeded", "userRateLimitExceeded", "rateLimitExceeded", "dailyLimitExceeded"}
                is_quota_error = any(reason in error_content for reason in quota_reasons)
            except (UnicodeDecodeError, AttributeError):
                pass

            if is_quota_error:
                # Quota exceeded - Exit 3
                console.print(
                    Panel(
                        "[red]YouTube API quota exceeded[/red]\n"
                        "The daily limit has been reached.\n"
                        "Please try again after midnight Pacific Time.",
                        title=f"{operation_name} - Quota Exceeded",
                        border_style="red",
                    )
                )
                logger.error(f"Quota exceeded during {operation_name}")
                raise typer.Exit(EXIT_QUOTA_EXCEEDED)
            else:
                # Authentication error - Exit 2
                display_auth_api_error(status_code, operation_name)
                logger.error(f"Authentication failed (HTTP {status_code}) during {operation_name}")
                raise typer.Exit(EXIT_AUTH_FAILURE)
        else:
            # Other HTTP errors
            console.print(
                Panel(
                    f"[red]YouTube API error (HTTP {status_code})[/red]\n{str(e)}",
                    title=f"{operation_name} - API Error",
                    border_style="red",
                )
            )
            logger.error(f"API error (HTTP {status_code}) during {operation_name}: {e}")
            raise typer.Exit(EXIT_USER_ERROR)

    except SQLAlchemyError as e:
        # T063: Handle database errors - Exit 5
        display_database_error(operation_name, str(e))
        logger.error(f"Database error during {operation_name}: {e}")
        raise typer.Exit(EXIT_DATABASE_ERROR)

    except (ConnectionError, TimeoutError, ConnectionResetError, BrokenPipeError) as e:
        # T062: Handle network errors - Exit 3
        display_network_failure(type(e).__name__, operation_name, str(e))
        logger.error(f"Network error ({type(e).__name__}) during {operation_name}: {e}")
        raise typer.Exit(EXIT_NETWORK_ERROR)

    except OSError as e:
        # Network-related OS errors (DNS failures, socket errors)
        if "getaddrinfo" in str(e) or "Name or service not known" in str(e):
            display_network_failure("DNS Resolution Error", operation_name, str(e))
            logger.error(f"DNS error during {operation_name}: {e}")
            raise typer.Exit(EXIT_NETWORK_ERROR)
        else:
            # Other OS errors
            console.print(
                Panel(
                    f"[red]{operation_name} failed:[/red]\n{str(e)}",
                    title=f"{operation_name} Error",
                    border_style="red",
                )
            )
            logger.error(f"OS error during {operation_name}: {e}")
            raise typer.Exit(EXIT_USER_ERROR)

    except Exception as e:
        console.print(
            Panel(
                f"[red]{operation_name} failed:[/red]\n{str(e)}",
                title=f"{operation_name} Error",
                border_style="red",
            )
        )
        logger.error(f"Unexpected error during {operation_name}: {e}")
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


# =============================================================================
# Phase 9 Error Display Functions (T061-T064)
# =============================================================================


def display_auth_api_error(status_code: int, command_name: str = "Command") -> None:
    """
    Display authentication failure error with re-auth guidance (T061, FR-019).

    Shows message: "Authentication expired - please run 'chronovista auth login'"

    Parameters
    ----------
    status_code : int
        HTTP status code from API response (401 or 403).
    command_name : str
        Name of the command that encountered the error.
    """
    if status_code == 401:
        error_title = "Unauthorized"
    elif status_code == 403:
        error_title = "Forbidden"
    else:
        error_title = "Authentication Error"

    console.print(
        Panel(
            "[red]Authentication expired - please run [bold]'chronovista auth login'[/bold][/red]",
            title=f"{command_name} - {error_title}",
            border_style="red",
        )
    )


def display_network_failure(
    error_type: str,
    command_name: str = "Command",
    details: Optional[str] = None,
) -> None:
    """
    Display network failure error with rollback confirmation (T062).

    Parameters
    ----------
    error_type : str
        Type of network error (e.g., "ConnectionError", "TimeoutError").
    command_name : str
        Name of the command that encountered the error.
    details : Optional[str]
        Additional error details.
    """
    message_lines = [
        f"[red]Network error: {error_type}[/red]",
        "",
        "Unable to connect to YouTube API.",
        "Any pending changes have been rolled back.",
    ]

    if details:
        # Truncate long details
        truncated = details[:200] + "..." if len(details) > 200 else details
        message_lines.append(f"\nDetails: {truncated}")

    message_lines.extend([
        "",
        "[yellow]What to try:[/yellow]",
        "1. Check your internet connection",
        "2. Try again in a few moments",
    ])

    console.print(
        Panel(
            "\n".join(message_lines),
            title=f"{command_name} - Network Error",
            border_style="red",
        )
    )


def display_database_error(
    command_name: str = "Command",
    details: Optional[str] = None,
) -> None:
    """
    Display database commit error with rollback confirmation (T063).

    Shows message: "Database error: failed to commit - transaction rolled back"

    Parameters
    ----------
    command_name : str
        Name of the command that encountered the error.
    details : Optional[str]
        Additional error details.
    """
    message_lines = [
        "[red]Database error: failed to commit - transaction rolled back[/red]",
        "",
        "Your data has been safely rolled back to the previous state.",
        "No partial changes were saved.",
    ]

    if details:
        # Truncate long details
        truncated = details[:200] + "..." if len(details) > 200 else details
        message_lines.append(f"\nDetails: {truncated}")

    message_lines.extend([
        "",
        "[yellow]What to try:[/yellow]",
        "1. Check database connectivity",
        "2. Try the operation again",
    ])

    console.print(
        Panel(
            "\n".join(message_lines),
            title=f"{command_name} - Database Error",
            border_style="red",
        )
    )
