"""
CLI constants for chronovista.

This module provides shared constants for CLI commands including:
- Exit codes following Unix conventions
- Batch sizes for sync/seed operations
- Default region codes and configuration values
- Table display limits for consistent output
- Format strings for CLI output formatting

NOTE: Domain constants should remain in their domain modules.
Command-specific constants should stay in their command files.
This module is for CLI-wide shared values only.
"""

from __future__ import annotations

from typing import Final

# =============================================================================
# Exit Codes
# =============================================================================
# Following Unix conventions and POSIX standards for exit codes.
# These are CLI-specific exit codes that map to user-facing error categories.

EXIT_SUCCESS: Final[int] = 0
"""Operation completed normally."""

EXIT_USER_ERROR: Final[int] = 1
"""
User error: invalid input, resource not found, validation failure.

Examples:
- Invalid command arguments
- Resource not found (playlist, video, channel)
- Validation failure (invalid region code, invalid topic ID)
"""

EXIT_SYSTEM_ERROR: Final[int] = 2
"""
System error: database error, connection failed, internal error.

Examples:
- Database connection failure
- File system errors
- Unexpected internal exceptions
"""

EXIT_CANCELLED: Final[int] = 3
"""
User cancelled: operation cancelled via Ctrl+C or declined confirmation.

This follows the convention of using exit code 3 for user-initiated
cancellations that are not errors.
"""

# =============================================================================
# Batch Sizes
# =============================================================================
# Default batch sizes for sync and seed operations.
# These balance API quota usage with processing efficiency.

DEFAULT_BATCH_SIZE: Final[int] = 1000
"""Default batch size for processing large datasets (e.g., watch history)."""

YOUTUBE_API_BATCH_SIZE: Final[int] = 50
"""
Maximum batch size for YouTube Data API requests.

YouTube API limits most batch requests to 50 items per call.
This is enforced by the API and cannot be exceeded.
"""

# =============================================================================
# Default Region and Locale
# =============================================================================

DEFAULT_REGION_CODE: Final[str] = "US"
"""
Default two-character country code for YouTube API requests.

Used for fetching video categories and region-specific content.
Valid codes follow ISO 3166-1 alpha-2 standard.
"""

# =============================================================================
# Table Display Limits
# =============================================================================
# Limits for Rich table output to keep CLI output readable.

MAX_TABLE_ROWS: Final[int] = 10
"""
Maximum rows to display in summary tables.

When displaying lists of items (playlists, videos, etc.),
show at most this many rows with a "... and N more" footer.
"""

MAX_TITLE_WIDTH: Final[int] = 40
"""Maximum width for title columns in tables (characters)."""

MAX_DESCRIPTION_WIDTH: Final[int] = 60
"""Maximum width for description columns in tables (characters)."""

MAX_CHANNEL_WIDTH: Final[int] = 25
"""Maximum width for channel name columns in tables (characters)."""

# =============================================================================
# Format Strings
# =============================================================================
# Consistent format strings for CLI output.

DATETIME_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S UTC"
"""Standard datetime format for CLI output."""

DATE_FORMAT: Final[str] = "%Y-%m-%d"
"""Standard date format for CLI output."""

TIMESTAMP_FILE_FORMAT: Final[str] = "%Y%m%d-%H%M%S"
"""Timestamp format for file names (no special characters)."""

# =============================================================================
# Progress and Status Indicators
# =============================================================================
# Consistent status indicators for CLI output.
# Note: Actual emoji usage depends on the Rich console capabilities.

STATUS_SUCCESS: Final[str] = "[green]Success[/green]"
"""Rich markup for success status."""

STATUS_FAILED: Final[str] = "[red]Failed[/red]"
"""Rich markup for failed status."""

STATUS_PENDING: Final[str] = "[yellow]Pending[/yellow]"
"""Rich markup for pending status."""

STATUS_SKIPPED: Final[str] = "[dim]Skipped[/dim]"
"""Rich markup for skipped status."""

# =============================================================================
# Error Display Limits
# =============================================================================

MAX_ERRORS_DISPLAYED: Final[int] = 10
"""Maximum number of error messages to display in error summaries."""
