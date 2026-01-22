"""
Standardized error message helpers for CLI commands.

Provides:
- Error display formatters with consistent 4-part format
- Rich panel wrappers for error/warning/success display
- CLI exit code mappings
- Authentication error display helpers

Error Format (contracts/cli-commands.md):
    Title -> Problem -> Expected -> Example

Examples:
    >>> format_error("Not Found", "Playlist INT_7f37... does not exist")
    '... Error: Not Found: Playlist INT_7f37... does not exist'

    >>> format_error(
    ...     "Validation",
    ...     "Invalid YouTube ID format",
    ...     expected="PL prefix followed by 28-48 alphanumeric characters",
    ...     got="INVALID123"
    ... )
    '... Error: Validation: Invalid YouTube ID format
       Expected: PL prefix followed by 28-48 alphanumeric characters
       Got: INVALID123'
"""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel

# Module-level console for CLI error display
console = Console()


# =============================================================================
# Error Categories (from contracts/cli-commands.md)
# =============================================================================

class ErrorCategory:
    """
    Standard error categories for CLI commands.

    Categories map to specific error types:
    - NOT_FOUND: Resource does not exist in database
    - VALIDATION: Input format or value validation failed
    - CONFLICT: Operation conflicts with existing state
    - DATABASE: Database operation failed
    """

    NOT_FOUND = "Not Found"
    VALIDATION = "Validation"
    CONFLICT = "Conflict"
    DATABASE = "Database"


# =============================================================================
# Exit Code Mappings
# =============================================================================

# These will be imported from cli/constants.py when it exists.
# For now, define locally for self-contained usage.
# Note: These mirror the values that will be in constants.py (T002)
EXIT_SUCCESS = 0
EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_CANCELLED = 3


def get_exit_code_for_category(category: str) -> int:
    """
    Map error category to appropriate exit code.

    Parameters
    ----------
    category : str
        Error category from ErrorCategory.

    Returns
    -------
    int
        Exit code appropriate for the error type.

    Examples
    --------
    >>> get_exit_code_for_category(ErrorCategory.NOT_FOUND)
    1
    >>> get_exit_code_for_category(ErrorCategory.DATABASE)
    2
    """
    category_to_exit_code = {
        ErrorCategory.NOT_FOUND: EXIT_USER_ERROR,
        ErrorCategory.VALIDATION: EXIT_USER_ERROR,
        ErrorCategory.CONFLICT: EXIT_USER_ERROR,
        ErrorCategory.DATABASE: EXIT_SYSTEM_ERROR,
    }
    return category_to_exit_code.get(category, EXIT_USER_ERROR)


# =============================================================================
# Error Formatting Functions
# =============================================================================

def format_error(
    category: str,
    message: str,
    expected: Optional[str] = None,
    got: Optional[str] = None,
    hint: Optional[str] = None,
) -> str:
    """
    Format error message in standardized 4-part format.

    Format follows contracts/cli-commands.md specification:
        Title -> Problem -> Expected (optional) -> Got (optional) -> Hint (optional)

    Parameters
    ----------
    category : str
        Error category (e.g., "Not Found", "Validation", "Conflict", "Database").
        Use ErrorCategory constants for consistency.
    message : str
        Human-readable error description.
    expected : Optional[str]
        Description of expected format/value (optional).
    got : Optional[str]
        Actual value that was received (optional).
    hint : Optional[str]
        Actionable suggestion for resolving the error (optional).

    Returns
    -------
    str
        Formatted error message string.

    Examples
    --------
    >>> format_error("Not Found", "Playlist INT_7f37... does not exist")
    '... Error: Not Found: Playlist INT_7f37... does not exist'

    >>> format_error(
    ...     "Validation",
    ...     "Invalid YouTube ID format",
    ...     expected="PL prefix followed by 28-48 alphanumeric characters",
    ...     got="INVALID123"
    ... )
    '... Error: Validation: Invalid YouTube ID format
       Expected: PL prefix followed by 28-48 alphanumeric characters
       Got: INVALID123'

    >>> format_error(
    ...     "Conflict",
    ...     'YouTube ID PLdU2X... is already linked to playlist "Another" (INT_abc...)',
    ...     hint="Use --force to update the link, or unlink from the other playlist first."
    ... )
    '... Error: Conflict: YouTube ID PLdU2X... is already linked...
       Hint: Use --force to update the link, or unlink from the other playlist first.'
    """
    lines = [f"Error: {category}: {message}"]

    if expected is not None:
        lines.append(f"   Expected: {expected}")

    if got is not None:
        lines.append(f"   Got: {got}")

    if hint is not None:
        lines.append(f"   Hint: {hint}")

    return "\n".join(lines)


def format_success(message: str) -> str:
    """
    Format success message.

    Parameters
    ----------
    message : str
        Success message to display.

    Returns
    -------
    str
        Formatted success message.

    Examples
    --------
    >>> format_success('Linked playlist "My Favorite Videos"')
    '... Linked playlist "My Favorite Videos"'
    """
    return message


def format_warning(message: str) -> str:
    """
    Format warning message.

    Parameters
    ----------
    message : str
        Warning message to display.

    Returns
    -------
    str
        Formatted warning message.

    Examples
    --------
    >>> format_warning("Some videos could not be processed")
    '... Some videos could not be processed'
    """
    return message


# =============================================================================
# Rich Panel Display Functions
# =============================================================================

def display_error_panel(
    category: str,
    message: str,
    expected: Optional[str] = None,
    got: Optional[str] = None,
    hint: Optional[str] = None,
    title: str = "Error",
) -> None:
    """
    Display formatted error in a Rich panel.

    Parameters
    ----------
    category : str
        Error category from ErrorCategory.
    message : str
        Human-readable error description.
    expected : Optional[str]
        Description of expected format/value.
    got : Optional[str]
        Actual value received.
    hint : Optional[str]
        Actionable suggestion for resolution.
    title : str
        Panel title (default: "Error").

    Examples
    --------
    >>> display_error_panel(
    ...     ErrorCategory.VALIDATION,
    ...     "Invalid YouTube ID format",
    ...     expected="PL prefix followed by 28-48 alphanumeric characters",
    ...     got="INVALID123"
    ... )
    # Displays a red-bordered panel with formatted error
    """
    formatted = format_error(category, message, expected, got, hint)
    console.print(
        Panel(
            f"[red]{formatted}[/red]",
            title=title,
            border_style="red",
        )
    )


def display_success_panel(
    message: str,
    title: str = "Success",
    extra_info: Optional[str] = None,
) -> None:
    """
    Display success message in a Rich panel.

    Parameters
    ----------
    message : str
        Success message to display.
    title : str
        Panel title (default: "Success").
    extra_info : Optional[str]
        Additional information to display below the message.

    Examples
    --------
    >>> display_success_panel(
    ...     'Linked playlist "My Favorite Videos"',
    ...     title="Link Complete",
    ...     extra_info="Internal ID: INT_7f37...\\nYouTube ID: PLdU2X..."
    ... )
    """
    content = f"[green]{message}[/green]"
    if extra_info:
        content += f"\n\n{extra_info}"

    console.print(
        Panel(
            content,
            title=title,
            border_style="green",
        )
    )


def display_warning_panel(
    message: str,
    title: str = "Warning",
    extra_info: Optional[str] = None,
) -> None:
    """
    Display warning message in a Rich panel.

    Parameters
    ----------
    message : str
        Warning message to display.
    title : str
        Panel title (default: "Warning").
    extra_info : Optional[str]
        Additional information to display below the message.

    Examples
    --------
    >>> display_warning_panel(
    ...     "Some videos were skipped",
    ...     extra_info="3 videos not found in database"
    ... )
    """
    content = f"[yellow]{message}[/yellow]"
    if extra_info:
        content += f"\n\n{extra_info}"

    console.print(
        Panel(
            content,
            title=title,
            border_style="yellow",
        )
    )


def display_info_panel(
    message: str,
    title: str = "Info",
    extra_info: Optional[str] = None,
) -> None:
    """
    Display informational message in a Rich panel.

    Parameters
    ----------
    message : str
        Info message to display.
    title : str
        Panel title (default: "Info").
    extra_info : Optional[str]
        Additional information to display below the message.

    Examples
    --------
    >>> display_info_panel(
    ...     "Processing playlists...",
    ...     title="Sync Progress"
    ... )
    """
    content = f"[blue]{message}[/blue]"
    if extra_info:
        content += f"\n\n{extra_info}"

    console.print(
        Panel(
            content,
            title=title,
            border_style="blue",
        )
    )


# =============================================================================
# Simple Display Functions (No Panel)
# =============================================================================

def print_error(message: str) -> None:
    """
    Print error message without panel.

    Parameters
    ----------
    message : str
        Error message to display.
    """
    console.print(f"[red]{message}[/red]")


def print_success(message: str) -> None:
    """
    Print success message without panel.

    Parameters
    ----------
    message : str
        Success message to display.
    """
    console.print(f"[green]{message}[/green]")


def print_warning(message: str) -> None:
    """
    Print warning message without panel.

    Parameters
    ----------
    message : str
        Warning message to display.
    """
    console.print(f"[yellow]{message}[/yellow]")


def print_info(message: str) -> None:
    """
    Print info message without panel.

    Parameters
    ----------
    message : str
        Info message to display.
    """
    console.print(f"[blue]{message}[/blue]")


# =============================================================================
# Authentication Error Helpers
# =============================================================================

def display_auth_required_error(command_name: str = "Command") -> None:
    """
    Display authentication required error panel.

    Parameters
    ----------
    command_name : str
        Name of the command that requires authentication.

    Examples
    --------
    >>> display_auth_required_error("Playlist Sync")
    # Displays panel with auth instructions
    """
    console.print(
        Panel(
            "[red]Not authenticated[/red]\n"
            "Use [bold]chronovista auth login[/bold] to sign in first.",
            title=f"{command_name} - Authentication Required",
            border_style="red",
        )
    )


def display_auth_expired_error(
    can_refresh: bool = False,
    command_name: str = "Command",
) -> None:
    """
    Display authentication expired error panel.

    Parameters
    ----------
    can_refresh : bool
        Whether the token can potentially be refreshed.
    command_name : str
        Name of the command that encountered the error.

    Examples
    --------
    >>> display_auth_expired_error(can_refresh=True)
    # Displays panel suggesting token refresh
    """
    if can_refresh:
        console.print(
            Panel(
                "[yellow]Authentication token expired[/yellow]\n"
                "Use [bold]chronovista auth refresh[/bold] to refresh your token.\n"
                "If refresh fails, use [bold]chronovista auth login[/bold] for fresh authentication.",
                title=f"{command_name} - Token Expired",
                border_style="yellow",
            )
        )
    else:
        console.print(
            Panel(
                "[red]Authentication token expired and cannot be refreshed[/red]\n"
                "Use [bold]chronovista auth login[/bold] to authenticate again.",
                title=f"{command_name} - Token Expired",
                border_style="red",
            )
        )


# =============================================================================
# Specialized Error Formatters
# =============================================================================

def format_not_found_error(resource_type: str, identifier: str) -> str:
    """
    Format a "Not Found" error message.

    Parameters
    ----------
    resource_type : str
        Type of resource (e.g., "Playlist", "Video", "Channel").
    identifier : str
        Identifier that was not found.

    Returns
    -------
    str
        Formatted error message.

    Examples
    --------
    >>> format_not_found_error("Playlist", "INT_7f37ed8c...")
    '... Error: Not Found: Playlist INT_7f37ed8c... does not exist'
    """
    return format_error(
        ErrorCategory.NOT_FOUND,
        f"{resource_type} {identifier} does not exist",
    )


def format_validation_error(
    field: str,
    message: str,
    expected: Optional[str] = None,
    got: Optional[str] = None,
) -> str:
    """
    Format a validation error message.

    Parameters
    ----------
    field : str
        Field that failed validation.
    message : str
        Validation error description.
    expected : Optional[str]
        Expected format description.
    got : Optional[str]
        Actual value received.

    Returns
    -------
    str
        Formatted error message.

    Examples
    --------
    >>> format_validation_error(
    ...     "youtube_id",
    ...     "Invalid YouTube ID format",
    ...     expected="PL prefix followed by 28-48 alphanumeric characters",
    ...     got="INVALID123"
    ... )
    '... Error: Validation: Invalid YouTube ID format...'
    """
    return format_error(
        ErrorCategory.VALIDATION,
        f"Invalid {field}: {message}",
        expected=expected,
        got=got,
    )


def format_conflict_error(
    message: str,
    hint: Optional[str] = None,
) -> str:
    """
    Format a conflict error message.

    Parameters
    ----------
    message : str
        Conflict description.
    hint : Optional[str]
        Actionable suggestion for resolution.

    Returns
    -------
    str
        Formatted error message.

    Examples
    --------
    >>> format_conflict_error(
    ...     'YouTube ID PLdU2X... is already linked to playlist "Another" (INT_abc...)',
    ...     hint="Use --force to update the link, or unlink from the other playlist first."
    ... )
    '... Error: Conflict: YouTube ID PLdU2X... is already linked...'
    """
    return format_error(
        ErrorCategory.CONFLICT,
        message,
        hint=hint,
    )


def format_database_error(
    operation: str,
    details: Optional[str] = None,
) -> str:
    """
    Format a database error message.

    Parameters
    ----------
    operation : str
        Database operation that failed (e.g., "insert", "update", "query").
    details : Optional[str]
        Additional error details.

    Returns
    -------
    str
        Formatted error message.

    Examples
    --------
    >>> format_database_error("insert", "unique constraint violated")
    '... Error: Database: Failed to insert: unique constraint violated'
    """
    message = f"Failed to {operation}"
    if details:
        message += f": {details}"

    return format_error(ErrorCategory.DATABASE, message)


# =============================================================================
# Phase 9 Error Handling - Exit Codes (T061-T064)
# =============================================================================

# Exit codes per specification
EXIT_AUTH_FAILURE = 2  # Authentication failure (401/403)
EXIT_NETWORK_ERROR = 3  # Network errors (ConnectionError, TimeoutError)
EXIT_DATABASE_ERROR = 5  # Database errors (SQLAlchemy failures)


class ErrorCategory9:
    """
    Extended error categories for Phase 9.

    Categories map to specific exit codes:
    - AUTHENTICATION: OAuth/API authentication failures (exit code 2)
    - NETWORK: Network connectivity failures (exit code 3)
    - DATABASE_COMMIT: Database commit failures (exit code 5)
    """

    AUTHENTICATION = "Authentication"
    NETWORK = "Network"
    DATABASE_COMMIT = "Database Commit"


# =============================================================================
# T061: Authentication Failure Display (FR-019)
# =============================================================================


def display_auth_failure_error(
    status_code: int,
    command_name: str = "Command",
) -> None:
    """
    Display authentication failure error with re-auth guidance (T061, FR-019).

    Detects 401/403 from YouTube API and displays guidance message:
    "Authentication expired - please run 'chronovista auth login'"

    Parameters
    ----------
    status_code : int
        HTTP status code from API response (401 or 403).
    command_name : str
        Name of the command that encountered the error.

    Examples
    --------
    >>> display_auth_failure_error(401, "Playlist Sync")
    # Displays: "Authentication expired - please run 'chronovista auth login'"
    """
    if status_code == 401:
        error_type = "Unauthorized"
        message = (
            "Authentication expired - please run [bold]'chronovista auth login'[/bold]"
        )
    elif status_code == 403:
        error_type = "Forbidden"
        message = (
            "Access denied - your authentication may have expired.\n"
            "Please run [bold]'chronovista auth login'[/bold] to re-authenticate."
        )
    else:
        error_type = "Authentication Error"
        message = (
            "Authentication failed - please run [bold]'chronovista auth login'[/bold]"
        )

    console.print(
        Panel(
            f"[red]{message}[/red]",
            title=f"{command_name} - {error_type}",
            border_style="red",
        )
    )


def format_auth_failure_message(status_code: int) -> str:
    """
    Format authentication failure message with guidance.

    Parameters
    ----------
    status_code : int
        HTTP status code (401 or 403).

    Returns
    -------
    str
        Formatted error message with re-authentication guidance.

    Examples
    --------
    >>> format_auth_failure_message(401)
    "Authentication expired - please run 'chronovista auth login'"
    """
    return "Authentication expired - please run 'chronovista auth login'"


# =============================================================================
# T062: Network Failure Display
# =============================================================================


def display_network_error(
    error_type: str,
    command_name: str = "Command",
    details: Optional[str] = None,
) -> None:
    """
    Display network failure error with rollback confirmation (T062).

    Handles ConnectionError, TimeoutError, and other network-related failures.

    Parameters
    ----------
    error_type : str
        Type of network error (e.g., "ConnectionError", "TimeoutError").
    command_name : str
        Name of the command that encountered the error.
    details : Optional[str]
        Additional error details.

    Examples
    --------
    >>> display_network_error("ConnectionError", "Sync Playlists")
    # Displays network error with rollback message
    """
    message_lines = [
        f"[red]Network error: {error_type}[/red]",
        "",
        "Unable to connect to YouTube API.",
        "Any pending changes have been rolled back.",
    ]

    if details:
        message_lines.append(f"\nDetails: {details}")

    message_lines.extend([
        "",
        "[yellow]What to try:[/yellow]",
        "1. Check your internet connection",
        "2. Try again in a few moments",
        "3. If the problem persists, check YouTube API status",
    ])

    console.print(
        Panel(
            "\n".join(message_lines),
            title=f"{command_name} - Network Error",
            border_style="red",
        )
    )


def format_network_error_message(error_type: str) -> str:
    """
    Format network error message.

    Parameters
    ----------
    error_type : str
        Type of network error.

    Returns
    -------
    str
        Formatted error message.
    """
    return f"Network error: {error_type} - transaction rolled back"


# =============================================================================
# T063: Database Error Display with Exit 5
# =============================================================================


def display_database_commit_error(
    operation: str = "commit",
    command_name: str = "Command",
    details: Optional[str] = None,
) -> None:
    """
    Display database commit error with rollback confirmation (T063).

    Shows message: "Database error: failed to commit - transaction rolled back"

    Parameters
    ----------
    operation : str
        Database operation that failed (default: "commit").
    command_name : str
        Name of the command that encountered the error.
    details : Optional[str]
        Additional error details.

    Examples
    --------
    >>> display_database_commit_error("commit", "Sync Playlists")
    # Displays: "Database error: failed to commit - transaction rolled back"
    """
    message_lines = [
        f"[red]Database error: failed to {operation} - transaction rolled back[/red]",
    ]

    if details:
        message_lines.append(f"\nDetails: {details}")

    message_lines.extend([
        "",
        "Your data has been safely rolled back to the previous state.",
        "No partial changes were saved.",
        "",
        "[yellow]What to try:[/yellow]",
        "1. Check database connectivity",
        "2. Ensure sufficient disk space",
        "3. Try the operation again",
    ])

    console.print(
        Panel(
            "\n".join(message_lines),
            title=f"{command_name} - Database Error",
            border_style="red",
        )
    )


def format_database_commit_error_message() -> str:
    """
    Format database commit error message.

    Returns
    -------
    str
        Formatted error message for database commit failures.
    """
    return "Database error: failed to commit - transaction rolled back"


# =============================================================================
# T064: Transient API Failure Retry Display
# =============================================================================


def display_retry_message(
    attempt: int,
    max_retries: int,
    delay: float,
    error_type: str,
) -> None:
    """
    Display retry message for transient API failures (T064, NFR-004).

    Shows progress of exponential backoff retry attempts.

    Parameters
    ----------
    attempt : int
        Current retry attempt number (1-based).
    max_retries : int
        Maximum number of retries configured.
    delay : float
        Delay before next retry in seconds.
    error_type : str
        Type of error being retried.

    Examples
    --------
    >>> display_retry_message(1, 3, 1.0, "500 Internal Server Error")
    # Displays: "Retry 1/3 in 1.0s: 500 Internal Server Error"
    """
    console.print(
        f"[yellow]Retry {attempt}/{max_retries} in {delay:.1f}s: {error_type}[/yellow]"
    )


def display_retry_exhausted_error(
    max_retries: int,
    error_type: str,
    command_name: str = "Command",
) -> None:
    """
    Display error when all retry attempts are exhausted (T064).

    Parameters
    ----------
    max_retries : int
        Maximum retries that were attempted.
    error_type : str
        Type of persistent error.
    command_name : str
        Name of the command that encountered the error.

    Examples
    --------
    >>> display_retry_exhausted_error(3, "503 Service Unavailable", "Sync")
    # Displays error indicating all retries failed
    """
    console.print(
        Panel(
            f"[red]API request failed after {max_retries} retries[/red]\n"
            f"Last error: {error_type}\n"
            "\n"
            "[yellow]The YouTube API may be experiencing issues.[/yellow]\n"
            "Please try again later.",
            title=f"{command_name} - Retry Exhausted",
            border_style="red",
        )
    )


# =============================================================================
# Error Type Detection Helpers
# =============================================================================


def is_auth_error(status_code: int) -> bool:
    """
    Check if HTTP status code indicates authentication failure.

    Parameters
    ----------
    status_code : int
        HTTP status code from API response.

    Returns
    -------
    bool
        True if the error is an authentication failure (401 or 403).
    """
    return status_code in (401, 403)


def is_retryable_error(status_code: int) -> bool:
    """
    Check if HTTP status code indicates a retryable (transient) error.

    Parameters
    ----------
    status_code : int
        HTTP status code from API response.

    Returns
    -------
    bool
        True if the error is retryable (5xx server errors, 429 rate limit).
    """
    # 5xx server errors and 429 (rate limit) are retryable
    return status_code >= 500 or status_code == 429


def is_network_error(exception: Exception) -> bool:
    """
    Check if an exception is a network-related error.

    Parameters
    ----------
    exception : Exception
        The exception to check.

    Returns
    -------
    bool
        True if the exception is a network error.
    """
    network_error_types = (
        ConnectionError,
        TimeoutError,
        ConnectionResetError,
        BrokenPipeError,
        OSError,  # Includes socket errors, DNS failures
    )
    return isinstance(exception, network_error_types)
