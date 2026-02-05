"""
Custom exceptions for the chronovista application.

This module defines domain-specific exceptions for error handling
throughout the application, including API errors, network failures,
and validation errors.
"""

from __future__ import annotations

from typing import Any

from chronovista.api.schemas.responses import (
    ApiError,
    ERROR_TITLES,
    ErrorCode,
    get_error_type_uri,
)


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


class ChannelEnrichmentError(ChronovistaError):
    """
    Exception raised for channel-specific enrichment failures.

    This exception is raised when channel enrichment fails for a specific
    channel, such as when the channel is not found on YouTube, access is
    forbidden, or channel data is incomplete.

    Attributes
    ----------
    message : str
        Human-readable error message.
    channel_id : str | None
        The channel ID that caused the error.
    error_reason : str | None
        The specific error reason (e.g., "channelNotFound", "forbidden").

    Examples
    --------
    >>> try:
    ...     await enrichment_service.enrich_channel(channel_id)
    ... except ChannelEnrichmentError as e:
    ...     if e.error_reason == "channelNotFound":
    ...         print(f"Channel {e.channel_id} not found on YouTube")
    """

    def __init__(
        self,
        message: str = "Channel enrichment failed",
        channel_id: str | None = None,
        error_reason: str | None = None,
    ) -> None:
        """
        Initialize ChannelEnrichmentError.

        Parameters
        ----------
        message : str, optional
            Human-readable error message (default: "Channel enrichment failed").
        channel_id : str | None, optional
            The channel ID that caused the error (default: None).
        error_reason : str | None, optional
            The specific error reason (default: None).
        """
        self.channel_id: str | None = channel_id
        self.error_reason: str | None = error_reason
        super().__init__(message)


class LockAcquisitionError(ChronovistaError):
    """
    Exception raised when lock acquisition fails.

    This exception is raised when another enrichment process is already
    running and holds the advisory lock, preventing concurrent execution.

    Attributes
    ----------
    message : str
        Human-readable error message.
    lock_holder_pid : int | None
        The PID of the process holding the lock, if available.

    Examples
    --------
    >>> try:
    ...     await enrichment_service.acquire_lock()
    ... except LockAcquisitionError as e:
    ...     print(f"Lock held by PID: {e.lock_holder_pid}")
    ...     raise typer.Exit(4)
    """

    def __init__(
        self,
        message: str = "Failed to acquire enrichment lock",
        lock_holder_pid: int | None = None,
    ) -> None:
        """
        Initialize LockAcquisitionError.

        Parameters
        ----------
        message : str, optional
            Human-readable error message (default: "Failed to acquire enrichment lock").
        lock_holder_pid : int | None, optional
            The PID of the process holding the lock (default: None).
        """
        self.lock_holder_pid: int | None = lock_holder_pid
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


# =============================================================================
# API Layer Exceptions
# =============================================================================


class APIError(ChronovistaError):
    """Base exception for API layer errors.

    This exception provides a standardized way to return HTTP errors from
    the API layer with machine-readable error codes and detailed context.

    Attributes
    ----------
    status_code : int
        HTTP status code for the error response (default: 500).
    error_code : ErrorCode
        Machine-readable error code for API consumers.
    message : str
        Human-readable error message.
    details : dict[str, Any] | None
        Additional error context (e.g., resource_type, identifier).

    Examples
    --------
    >>> raise APIError(message="Something went wrong", details={"context": "example"})
    """

    status_code: int = 500
    _error_code_value: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize APIError.

        Parameters
        ----------
        message : str
            Human-readable error message.
        details : dict[str, Any] | None, optional
            Additional error context (default: None).
        """
        self.message = message
        self.details = details
        super().__init__(message)

    @property
    def error_code(self) -> ErrorCode:
        """Get the error code as an ErrorCode enum."""
        from chronovista.api.schemas.responses import ErrorCode

        return ErrorCode(self._error_code_value)

    def to_api_error(self) -> ApiError:
        """Convert to API response schema.

        Returns
        -------
        ApiError
            Pydantic model suitable for JSON serialization.
        """
        from chronovista.api.schemas.responses import ApiError

        return ApiError(
            code=self.error_code.value,
            message=self.message,
            details=self.details,
        )

    def to_problem_detail(self, instance: str, request_id: str) -> dict[str, Any]:
        """Convert to RFC 7807 Problem Detail dictionary.

        Creates a dictionary suitable for use with ProblemDetail or
        ProblemJSONResponse for RFC 7807 compliant error responses.

        Parameters
        ----------
        instance : str
            URI reference of the specific occurrence (e.g., "/api/v1/videos/xyz123").
        request_id : str
            Unique request identifier for correlation and debugging.

        Returns
        -------
        dict[str, Any]
            Dictionary with RFC 7807 fields suitable for ProblemDetail model.

        Examples
        --------
        >>> error = NotFoundError(resource_type="Video", identifier="xyz123")
        >>> problem = error.to_problem_detail(
        ...     instance="/api/v1/videos/xyz123",
        ...     request_id="550e8400-e29b-41d4-a716-446655440000"
        ... )
        >>> problem["type"]
        'https://api.chronovista.com/errors/NOT_FOUND'
        """
        return {
            "type": get_error_type_uri(self.error_code),
            "title": ERROR_TITLES.get(self.error_code, "Error"),
            "status": self.status_code,
            "detail": self.message,
            "instance": instance,
            "code": self.error_code.value,
            "request_id": request_id,
        }


class NotFoundError(APIError):
    """Resource not found (404).

    This exception is raised when a requested resource does not exist
    in the database.

    Attributes
    ----------
    status_code : int
        Always 404 for this exception.
    error_code : ErrorCode
        Always NOT_FOUND for this exception.
    resource_type : str
        The type of resource that was not found (e.g., "Channel", "Video").
    identifier : str
        The identifier used to look up the resource.

    Examples
    --------
    >>> raise NotFoundError(
    ...     resource_type="Channel",
    ...     identifier="UCxyz123456789",
    ...     hint="Verify the channel ID or run a sync."
    ... )
    """

    status_code: int = 404
    _error_code_value: str = "NOT_FOUND"

    def __init__(
        self,
        resource_type: str,
        identifier: str,
        hint: str | None = None,
    ) -> None:
        """
        Initialize NotFoundError.

        Parameters
        ----------
        resource_type : str
            The type of resource that was not found (e.g., "Channel", "Video").
        identifier : str
            The identifier used to look up the resource.
        hint : str | None, optional
            Additional hint for the user (default: None).
        """
        self.resource_type = resource_type
        self.identifier = identifier
        message = f"{resource_type} '{identifier}' not found"
        if hint:
            message += f". {hint}"
        super().__init__(
            message=message,
            details={"resource_type": resource_type, "identifier": identifier},
        )


class BadRequestError(APIError):
    """Invalid request parameters (400).

    This exception is raised when the request contains invalid parameters
    that cannot be processed.

    Attributes
    ----------
    status_code : int
        Always 400 for this exception.
    error_code : ErrorCode
        Either BAD_REQUEST or MUTUALLY_EXCLUSIVE.

    Examples
    --------
    >>> raise BadRequestError(
    ...     message="Cannot specify both 'linked=true' and 'unlinked=true'.",
    ...     details={"field": "linked,unlinked", "constraint": "mutually_exclusive"}
    ... )
    """

    status_code: int = 400
    _error_code_value: str = "BAD_REQUEST"

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        mutually_exclusive: bool = False,
    ) -> None:
        """
        Initialize BadRequestError.

        Parameters
        ----------
        message : str
            Human-readable error message.
        details : dict[str, Any] | None, optional
            Additional error context (default: None).
        mutually_exclusive : bool, optional
            If True, uses MUTUALLY_EXCLUSIVE error code (default: False).
        """
        if mutually_exclusive:
            self._error_code_value = "MUTUALLY_EXCLUSIVE"
        super().__init__(message=message, details=details)


class APIValidationError(APIError):
    """Request validation failed (422).

    This exception is raised when Pydantic validation fails on the request
    body or when custom validation logic fails.

    Attributes
    ----------
    status_code : int
        Always 422 for this exception.
    error_code : ErrorCode
        Always VALIDATION_ERROR for this exception.

    Examples
    --------
    >>> raise APIValidationError(
    ...     message="Request validation failed",
    ...     details={"errors": [{"loc": ["body", "title"], "msg": "field required"}]}
    ... )
    """

    status_code: int = 422
    _error_code_value: str = "VALIDATION_ERROR"


class ConflictError(APIError):
    """Resource conflict (409).

    This exception is raised when the request would create a conflict
    with existing data (e.g., duplicate resource creation).

    Attributes
    ----------
    status_code : int
        Always 409 for this exception.
    error_code : ErrorCode
        Always CONFLICT for this exception.

    Examples
    --------
    >>> raise ConflictError(
    ...     message="Channel already exists",
    ...     details={"channel_id": "UCxyz123456789"}
    ... )
    """

    status_code: int = 409
    _error_code_value: str = "CONFLICT"


class AuthorizationError(APIError):
    """Authorization denied (403).

    This exception is raised when the authenticated user does not have
    sufficient permissions to perform the requested operation.

    Attributes
    ----------
    status_code : int
        Always 403 for this exception.
    error_code : ErrorCode
        Always NOT_AUTHORIZED for this exception.

    Examples
    --------
    >>> raise AuthorizationError(
    ...     message="Insufficient permissions for this operation",
    ...     details={"required_scope": "admin"}
    ... )
    """

    status_code: int = 403
    _error_code_value: str = "NOT_AUTHORIZED"


class RateLimitError(APIError):
    """Rate limit exceeded (429).

    This exception is raised when the client has exceeded the allowed
    rate of requests. The optional retry_after attribute indicates how
    many seconds the client should wait before retrying.

    Attributes
    ----------
    status_code : int
        Always 429 for this exception.
    error_code : ErrorCode
        Always RATE_LIMITED for this exception.
    retry_after : int | None
        Number of seconds to wait before retrying, if available.

    Examples
    --------
    >>> raise RateLimitError(
    ...     message="API rate limit exceeded. Please retry after 60 seconds.",
    ...     retry_after=60
    ... )
    """

    status_code: int = 429
    _error_code_value: str = "RATE_LIMITED"

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        """
        Initialize RateLimitError.

        Parameters
        ----------
        message : str
            Human-readable error message.
        details : dict[str, Any] | None, optional
            Additional error context (default: None).
        retry_after : int | None, optional
            Number of seconds to wait before retrying (default: None).
        """
        self.retry_after = retry_after
        super().__init__(message=message, details=details)


class ExternalServiceError(APIError):
    """External service unavailable (502).

    This exception is raised when an external service (e.g., YouTube API)
    fails to respond or returns an error that prevents the operation
    from completing.

    Attributes
    ----------
    status_code : int
        Always 502 for this exception.
    error_code : ErrorCode
        Always EXTERNAL_SERVICE_ERROR for this exception.

    Examples
    --------
    >>> raise ExternalServiceError(
    ...     message="External service unavailable",
    ...     details={"service": "YouTube API", "reason": "timeout"}
    ... )
    """

    status_code: int = 502
    _error_code_value: str = "EXTERNAL_SERVICE_ERROR"


# Exit codes for CLI integration
EXIT_CODE_SUCCESS = 0
EXIT_CODE_GENERAL_ERROR = 1
EXIT_CODE_INVALID_ARGS = 2
EXIT_CODE_QUOTA_EXCEEDED = 3
EXIT_CODE_PREREQUISITES_MISSING = 4  # Also used for lock acquisition failure
EXIT_CODE_AUTHENTICATION_FAILED = 5
EXIT_CODE_LOCK_HELD = 4  # Alias for prerequisites - another process is running
EXIT_CODE_INTERRUPTED = 130  # Standard Unix signal interrupt exit code
