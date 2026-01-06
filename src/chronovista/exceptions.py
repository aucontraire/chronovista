"""
Custom exceptions for the chronovista application.

This module defines domain-specific exceptions for error handling
throughout the application, including API errors, network failures,
and validation errors.
"""

from __future__ import annotations


class ChronovistaError(Exception):
    """Base exception for all chronovista errors."""

    def __init__(self, message: str) -> None:
        """
        Initialize ChronovistaError.

        Parameters
        ----------
        message : str
            Human-readable error message.
        """
        self.message = message
        super().__init__(message)


class QuotaExceededException(ChronovistaError):
    """
    Exception raised when YouTube API quota is exceeded.

    This exception is raised when the YouTube Data API returns a 403 error
    with quota exceeded reason. The enrichment process should catch this
    exception, commit the current batch, and exit with code 3.

    Attributes
    ----------
    message : str
        Human-readable error message.
    daily_quota_exceeded : bool
        Whether this is a daily quota exhaustion (vs per-user quota).
    videos_processed : int
        Number of videos processed before quota was exceeded.

    Examples
    --------
    >>> try:
    ...     await youtube_service.fetch_videos_batched(video_ids)
    ... except QuotaExceededException as e:
    ...     print(f"Quota exceeded after processing {e.videos_processed} videos")
    ...     raise typer.Exit(3)
    """

    def __init__(
        self,
        message: str = "YouTube API quota exceeded",
        daily_quota_exceeded: bool = True,
        videos_processed: int = 0,
    ) -> None:
        """
        Initialize QuotaExceededException.

        Parameters
        ----------
        message : str, optional
            Human-readable error message (default: "YouTube API quota exceeded").
        daily_quota_exceeded : bool, optional
            Whether this is a daily quota exhaustion (default: True).
        videos_processed : int, optional
            Number of videos processed before quota was exceeded (default: 0).
        """
        self.daily_quota_exceeded = daily_quota_exceeded
        self.videos_processed = videos_processed
        super().__init__(message)


class NetworkError(ChronovistaError):
    """
    Exception raised for network-related failures.

    This exception wraps transient network errors such as connection
    timeouts, DNS failures, and server errors (5xx). The application
    should retry these errors with exponential backoff.

    Attributes
    ----------
    message : str
        Human-readable error message.
    original_error : Exception | None
        The original exception that caused this error.
    retry_count : int
        Number of retry attempts made before raising this exception.

    Examples
    --------
    >>> try:
    ...     response = await http_client.get(url)
    ... except NetworkError as e:
    ...     print(f"Network error after {e.retry_count} retries: {e.message}")
    """

    def __init__(
        self,
        message: str = "Network error occurred",
        original_error: Exception | None = None,
        retry_count: int = 0,
    ) -> None:
        """
        Initialize NetworkError.

        Parameters
        ----------
        message : str, optional
            Human-readable error message (default: "Network error occurred").
        original_error : Exception | None, optional
            The original exception that caused this error (default: None).
        retry_count : int, optional
            Number of retry attempts made (default: 0).
        """
        self.original_error = original_error
        self.retry_count = retry_count
        super().__init__(message)


class GracefulShutdownException(ChronovistaError):
    """
    Exception raised when graceful shutdown is requested.

    This exception is raised when the application receives SIGINT (Ctrl+C)
    or SIGTERM signal. It allows in-flight operations to complete gracefully
    before exiting.

    Attributes
    ----------
    message : str
        Human-readable error message.
    signal_received : str
        The signal that triggered the shutdown (e.g., "SIGINT", "SIGTERM").

    Examples
    --------
    >>> try:
    ...     await enrich_videos(session)
    ... except GracefulShutdownException as e:
    ...     print(f"Shutdown requested via {e.signal_received}")
    ...     await session.commit()  # Commit current batch
    ...     raise typer.Exit(130)
    """

    def __init__(
        self,
        message: str = "Graceful shutdown requested",
        signal_received: str = "SIGINT",
    ) -> None:
        """
        Initialize GracefulShutdownException.

        Parameters
        ----------
        message : str, optional
            Human-readable error message (default: "Graceful shutdown requested").
        signal_received : str, optional
            The signal that triggered the shutdown (default: "SIGINT").
        """
        self.signal_received = signal_received
        super().__init__(message)


class PrerequisiteError(ChronovistaError):
    """
    Exception raised when prerequisite data is missing.

    This exception is raised when required seeding data (topic_categories,
    video_categories) is missing from the database. The enrichment process
    should exit with code 4.

    Attributes
    ----------
    message : str
        Human-readable error message.
    missing_tables : list[str]
        List of table names that are missing data.

    Examples
    --------
    >>> try:
    ...     await check_prerequisites(session)
    ... except PrerequisiteError as e:
    ...     print(f"Missing data in: {', '.join(e.missing_tables)}")
    ...     raise typer.Exit(4)
    """

    def __init__(
        self,
        message: str = "Prerequisite data is missing",
        missing_tables: list[str] | None = None,
    ) -> None:
        """
        Initialize PrerequisiteError.

        Parameters
        ----------
        message : str, optional
            Human-readable error message (default: "Prerequisite data is missing").
        missing_tables : list[str] | None, optional
            List of table names that are missing data (default: None).
        """
        self.missing_tables = missing_tables or []
        super().__init__(message)


# Exit codes for CLI integration
EXIT_CODE_SUCCESS = 0
EXIT_CODE_GENERAL_ERROR = 1
EXIT_CODE_INVALID_ARGS = 2
EXIT_CODE_QUOTA_EXCEEDED = 3
EXIT_CODE_PREREQUISITES_MISSING = 4
EXIT_CODE_INTERRUPTED = 130  # Standard Unix signal interrupt exit code
