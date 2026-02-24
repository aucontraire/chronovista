"""Filter schemas for video classification filtering (Feature 020).

This module provides Pydantic V2 models for filter validation, RFC 7807
error responses, and partial success handling per FR-034, FR-049-052.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FilterWarningCode(str, Enum):
    """Warning codes for partial filter failures (FR-050).

    These codes provide machine-readable identification for filter-related
    warnings that occur during partial success scenarios.

    Attributes
    ----------
    FILTER_PARTIAL_FAILURE : str
        Some filters could not be applied but the request continued.
    FILTER_INVALID_VALUE : str
        A filter value was invalid and was ignored.
    FILTER_TIMEOUT : str
        A filter operation timed out but partial results were returned.
    """

    FILTER_PARTIAL_FAILURE = "FILTER_PARTIAL_FAILURE"
    FILTER_INVALID_VALUE = "FILTER_INVALID_VALUE"
    FILTER_TIMEOUT = "FILTER_TIMEOUT"


class FilterType(str, Enum):
    """Filter type identifiers.

    Used to identify which type of filter caused an issue in warnings
    and error responses.

    Attributes
    ----------
    TAG : str
        Tag-based filtering.
    CANONICAL_TAG : str
        Canonical tag-based filtering (normalized tag groups).
    CATEGORY : str
        Category-based filtering.
    TOPIC : str
        Topic-based filtering.
    """

    TAG = "tag"
    CANONICAL_TAG = "canonical_tag"
    CATEGORY = "category"
    TOPIC = "topic"


class VideoFilterParams(BaseModel):
    """Query parameters for filtering videos (FR-034).

    Validates filter limits: max 10 tags, max 10 canonical tags,
    max 10 topics, 1 category, 15 total.

    Attributes
    ----------
    tags : List[str]
        Filter by tag(s) with OR logic between multiple values. Max 10.
    canonical_tags : List[str]
        Filter by canonical tag(s) with AND logic between multiple values. Max 10.
    category : Optional[str]
        Filter by category ID (single value only).
    topic_ids : List[str]
        Filter by topic ID(s) with OR logic between multiple values. Max 10.

    Examples
    --------
    >>> params = VideoFilterParams(
    ...     tags=["music", "rock"],
    ...     category="10",
    ...     topic_ids=["/m/04rlf"]
    ... )
    >>> params.total_filter_count()
    4
    """

    model_config = ConfigDict(from_attributes=True, strict=True)

    tags: List[str] = Field(
        default_factory=list,
        description="Filter by tag(s) - OR logic between multiple",
    )
    canonical_tags: List[str] = Field(
        default_factory=list,
        description="Filter by canonical tag(s) - AND logic between multiple",
    )
    category: Optional[str] = Field(
        None,
        description="Filter by category ID (single value)",
    )
    topic_ids: List[str] = Field(
        default_factory=list,
        description="Filter by topic ID(s) - OR logic between multiple",
    )

    @field_validator("tags")
    @classmethod
    def validate_tags_limit(cls, v: List[str]) -> List[str]:
        """Validate maximum 10 tags per FR-034.

        Parameters
        ----------
        v : List[str]
            The list of tags to validate.

        Returns
        -------
        List[str]
            The validated list of tags.

        Raises
        ------
        ValueError
            If more than 10 tags are provided.
        """
        if len(v) > 10:
            raise ValueError(
                f"Maximum 10 tags allowed, received {len(v)}. "
                f"Remove {len(v) - 10} tags to continue."
            )
        return v

    @field_validator("canonical_tags")
    @classmethod
    def validate_canonical_tags_limit(cls, v: List[str]) -> List[str]:
        """Validate maximum 10 canonical tags.

        Parameters
        ----------
        v : List[str]
            The list of canonical tag normalized forms to validate.

        Returns
        -------
        List[str]
            The validated list of canonical tags.

        Raises
        ------
        ValueError
            If more than 10 canonical tags are provided.
        """
        if len(v) > 10:
            raise ValueError(
                f"Maximum 10 canonical tags allowed, received {len(v)}. "
                f"Remove {len(v) - 10} canonical tags to continue."
            )
        return v

    @field_validator("topic_ids")
    @classmethod
    def validate_topics_limit(cls, v: List[str]) -> List[str]:
        """Validate maximum 10 topics per FR-034.

        Parameters
        ----------
        v : List[str]
            The list of topic IDs to validate.

        Returns
        -------
        List[str]
            The validated list of topic IDs.

        Raises
        ------
        ValueError
            If more than 10 topics are provided.
        """
        if len(v) > 10:
            raise ValueError(
                f"Maximum 10 topics allowed, received {len(v)}. "
                f"Remove {len(v) - 10} topics to continue."
            )
        return v

    def total_filter_count(self) -> int:
        """Calculate total number of filter values.

        Returns
        -------
        int
            Total count of all filter values (tags + topics + category if set).
        """
        count = len(self.tags) + len(self.canonical_tags) + len(self.topic_ids)
        if self.category:
            count += 1
        return count

    def validate_total_limit(self) -> None:
        """Validate total filter count does not exceed 15 (FR-034).

        This method should be called after instantiation to validate
        the combined limit across all filter types.

        Raises
        ------
        ValueError
            If total filter count exceeds 15.
        """
        total = self.total_filter_count()
        if total > 15:
            raise ValueError(
                f"Maximum 15 total filter values allowed, received {total}. "
                f"Remove {total - 15} filters to continue."
            )


class ProblemDetails(BaseModel):
    """RFC 7807 Problem Details for HTTP API error responses (FR-052).

    Used for filter validation errors, rate limiting, and timeouts.
    This follows the RFC 7807 specification for problem details.

    Attributes
    ----------
    type : str
        URI identifying the error type.
    title : str
        Human-readable error summary.
    status : int
        HTTP status code (400, 429, 504, etc.).
    detail : str
        Specific error description with context.
    instance : str
        Request URI that caused the error.

    Examples
    --------
    >>> problem = ProblemDetails(
    ...     type="urn:chronovista:error:filter-limit-exceeded",
    ...     title="Filter Limit Exceeded",
    ...     status=400,
    ...     detail="Maximum 10 tags allowed, received 12.",
    ...     instance="/api/v1/videos?tag=a&tag=b&..."
    ... )
    """

    model_config = ConfigDict(from_attributes=True)

    type: str = Field(
        ...,
        description="URI identifying the error type",
        examples=["urn:chronovista:error:filter-limit-exceeded"],
    )
    title: str = Field(
        ...,
        description="Human-readable error summary",
        examples=["Filter Limit Exceeded"],
    )
    status: int = Field(
        ...,
        ge=400,
        le=599,
        description="HTTP status code",
        examples=[400, 429, 504],
    )
    detail: str = Field(
        ...,
        description="Specific error description with context",
        examples=["Maximum 10 tags allowed, received 12. Remove 2 tags to continue."],
    )
    instance: str = Field(
        ...,
        description="Request URI that caused the error",
        examples=["/api/v1/videos?tag=a&tag=b&..."],
    )


class FilterWarning(BaseModel):
    """Warning for partial filter failures (FR-049, FR-050).

    Included in responses when some filters succeed but others fail.

    Attributes
    ----------
    code : FilterWarningCode
        Warning code for programmatic handling.
    filter_type : FilterType
        Which filter type had the issue.
    message : str
        Human-readable warning message.

    Examples
    --------
    >>> warning = FilterWarning(
    ...     code=FilterWarningCode.FILTER_PARTIAL_FAILURE,
    ...     filter_type=FilterType.TOPIC,
    ...     message="Topic filter could not be applied due to database error"
    ... )
    """

    model_config = ConfigDict(from_attributes=True)

    code: FilterWarningCode = Field(
        ...,
        description="Warning code for programmatic handling",
    )
    filter_type: FilterType = Field(
        ...,
        description="Which filter type had the issue",
    )
    message: str = Field(
        ...,
        description="Human-readable warning message",
        examples=["Topic filter could not be applied due to database error"],
    )


class ErrorTypeURI:
    """RFC 7807 error type URI constants.

    Provides standardized URN-based error type identifiers per data-model.md section 8.

    Attributes
    ----------
    BASE : str
        Base URN prefix for all chronovista errors.
    FILTER_LIMIT_EXCEEDED : str
        Error type for max filter limits exceeded (FR-034).
    INVALID_FILTER_VALUE : str
        Error type for invalid filter values.
    FILTER_TIMEOUT : str
        Error type for filter query timeout (FR-036).
    RATE_LIMIT_EXCEEDED : str
        Error type for rate limiting (NFR-005, NFR-006).

    Examples
    --------
    >>> problem = ProblemDetails(
    ...     type=ErrorTypeURI.FILTER_LIMIT_EXCEEDED,
    ...     title="Filter Limit Exceeded",
    ...     status=400,
    ...     detail="Maximum 10 tags allowed",
    ...     instance="/api/v1/videos"
    ... )
    """

    BASE: str = "urn:chronovista:error"
    FILTER_LIMIT_EXCEEDED: str = f"{BASE}:filter-limit-exceeded"
    INVALID_FILTER_VALUE: str = f"{BASE}:invalid-filter-value"
    FILTER_TIMEOUT: str = f"{BASE}:filter-timeout"
    RATE_LIMIT_EXCEEDED: str = f"{BASE}:rate-limit-exceeded"


# Filter validation limits (FR-034)
FILTER_LIMITS = {
    "MAX_TAGS": 10,
    "MAX_CANONICAL_TAGS": 10,
    "MAX_TOPICS": 10,
    "MAX_CATEGORIES": 1,
    "MAX_TOTAL": 15,
}
"""Filter validation limits as defined in FR-034."""
