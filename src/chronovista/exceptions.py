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


class YouTubeAPIError(ChronovistaError):
    """
    Exception raised for YouTube API errors.

    This exception wraps errors returned by the YouTube Data API,
    including client errors (4xx) and server errors (5xx) that are
    not specifically quota-related.

    Attributes
    ----------
    message : str
        Human-readable error message.
    status_code : int | None
        HTTP status code returned by the API.
    error_reason : str | None
        The error reason from the API response (e.g., "videoNotFound").

    Examples
    --------
    >>> try:
    ...     video = await youtube_service.get_video(video_id)
    ... except YouTubeAPIError as e:
    ...     if e.status_code == 404:
    ...         print(f"Video not found: {e.error_reason}")
    """

    def __init__(
        self,
        message: str = "YouTube API error occurred",
        status_code: int | None = None,
        error_reason: str | None = None,
    ) -> None:
        """
        Initialize YouTubeAPIError.

        Parameters
        ----------
        message : str, optional
            Human-readable error message (default: "YouTube API error occurred").
        status_code : int | None, optional
            HTTP status code returned by the API (default: None).
        error_reason : str | None, optional
            The error reason from the API response (default: None).
        """
        self.status_code: int | None = status_code
        self.error_reason: str | None = error_reason
        super().__init__(message)


class AuthenticationError(ChronovistaError):
    """
    Exception raised for authentication-related failures.

    This exception is raised when OAuth authentication fails,
    tokens are expired or invalid, or required scopes are missing.

    Attributes
    ----------
    message : str
        Human-readable error message.
    expired : bool
        Whether the authentication token has expired.
    scope : str | None
        The OAuth scope that caused the error, if applicable.

    Examples
    --------
    >>> try:
    ...     credentials = await oauth_service.get_credentials()
    ... except AuthenticationError as e:
    ...     if e.expired:
    ...         print("Token expired, please re-authenticate")
    ...     raise typer.Exit(5)
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        expired: bool = False,
        scope: str | None = None,
    ) -> None:
        """
        Initialize AuthenticationError.

        Parameters
        ----------
        message : str, optional
            Human-readable error message (default: "Authentication failed").
        expired : bool, optional
            Whether the authentication token has expired (default: False).
        scope : str | None, optional
            The OAuth scope that caused the error (default: None).
        """
        self.expired: bool = expired
        self.scope: str | None = scope
        super().__init__(message)


class ValidationError(ChronovistaError):
    """
    Exception raised for data validation failures.

    This exception is raised when input data fails validation,
    either from user input, API responses, or database constraints.

    Attributes
    ----------
    message : str
        Human-readable error message.
    field_name : str | None
        The name of the field that failed validation.
    invalid_value : object
        The value that failed validation.

    Examples
    --------
    >>> try:
    ...     video = VideoCreate.model_validate(data)
    ... except ValidationError as e:
    ...     print(f"Invalid {e.field_name}: {e.invalid_value}")
    """

    def __init__(
        self,
        message: str = "Validation failed",
        field_name: str | None = None,
        invalid_value: object = None,
    ) -> None:
        """
        Initialize ValidationError.

        Parameters
        ----------
        message : str, optional
            Human-readable error message (default: "Validation failed").
        field_name : str | None, optional
            The name of the field that failed validation (default: None).
        invalid_value : object, optional
            The value that failed validation (default: None).
        """
        self.field_name: str | None = field_name
        self.invalid_value: object = invalid_value
        super().__init__(message)


class RepositoryError(ChronovistaError):
    """
    Exception raised for repository/database operation failures.

    This exception wraps database-related errors such as connection
    failures, constraint violations, and query errors.

    Attributes
    ----------
    message : str
        Human-readable error message.
    operation : str | None
        The database operation that failed (e.g., "insert", "update", "delete").
    entity_type : str | None
        The type of entity involved (e.g., "Video", "Channel").
    original_error : Exception | None
        The original database exception that caused this error.

    Examples
    --------
    >>> try:
    ...     await video_repository.create(session, video_create)
    ... except RepositoryError as e:
    ...     print(f"Failed to {e.operation} {e.entity_type}: {e.message}")
    """

    def __init__(
        self,
        message: str = "Repository operation failed",
        operation: str | None = None,
        entity_type: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """
        Initialize RepositoryError.

        Parameters
        ----------
        message : str, optional
            Human-readable error message (default: "Repository operation failed").
        operation : str | None, optional
            The database operation that failed (default: None).
        entity_type : str | None, optional
            The type of entity involved (default: None).
        original_error : Exception | None, optional
            The original database exception (default: None).
        """
        self.operation: str | None = operation
        self.entity_type: str | None = entity_type
        self.original_error: Exception | None = original_error
        super().__init__(message)


# Exit codes for CLI integration
EXIT_CODE_SUCCESS = 0
EXIT_CODE_GENERAL_ERROR = 1
EXIT_CODE_INVALID_ARGS = 2
EXIT_CODE_QUOTA_EXCEEDED = 3
EXIT_CODE_PREREQUISITES_MISSING = 4
EXIT_CODE_AUTHENTICATION_FAILED = 5
EXIT_CODE_INTERRUPTED = 130  # Standard Unix signal interrupt exit code
