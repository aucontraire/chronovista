"""
Pydantic models for the Wayback Machine video recovery service.

Provides validated data models for CDX API snapshots, recovered video metadata,
recovery results, and CDX response caching.

Models
------
CdxSnapshot
    Represents a single archived capture from the Wayback Machine CDX API.
RecoveredVideoData
    Metadata extracted from an archived YouTube page.
RecoveryResult
    Outcome of a single video recovery attempt.
CdxCacheEntry
    File-based cache entry for CDX responses.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from chronovista.models.youtube_types import VideoId


class CdxSnapshot(BaseModel):
    """
    Represents a single archived capture from the Wayback Machine CDX API.

    Each snapshot corresponds to one Wayback Machine capture, including the
    timestamp, original URL, MIME type, HTTP status, content digest, and
    response size. Provides computed properties for Wayback Machine URLs
    and parsed datetime.

    Attributes
    ----------
    timestamp : str
        CDX timestamp, exactly 14 digits (YYYYMMDDHHmmss format).
    original : str
        The original URL that was archived.
    mimetype : str
        Content MIME type of the archived response.
    statuscode : int
        HTTP status code of the archived response.
    digest : str
        Content hash (SHA-1 digest) of the archived response body.
    length : int
        Response body size in bytes. Must be greater than 0.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: str
    original: str
    mimetype: str
    statuscode: int
    digest: str
    length: int

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """
        Validate that timestamp is exactly 14 digits.

        Parameters
        ----------
        v : str
            The timestamp string to validate.

        Returns
        -------
        str
            The validated timestamp.

        Raises
        ------
        ValueError
            If timestamp is not exactly 14 digits.
        """
        if not re.match(r"^\d{14}$", v):
            raise ValueError(
                f"timestamp must be exactly 14 digits, got '{v}'"
            )
        return v

    @field_validator("length")
    @classmethod
    def validate_length(cls, v: int) -> int:
        """
        Validate that length is positive (greater than 0).

        Parameters
        ----------
        v : int
            The length value to validate.

        Returns
        -------
        int
            The validated length.

        Raises
        ------
        ValueError
            If length is not greater than 0.
        """
        if v <= 0:
            raise ValueError(f"length must be greater than 0, got {v}")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wayback_url(self) -> str:
        """
        Wayback Machine raw URL (no toolbar) for this snapshot.

        Returns
        -------
        str
            URL in the format ``https://web.archive.org/web/{timestamp}id_/{original}``.
        """
        return f"https://web.archive.org/web/{self.timestamp}id_/{self.original}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wayback_url_rendered(self) -> str:
        """
        Wayback Machine rendered URL (with iframe) for this snapshot.

        Returns
        -------
        str
            URL in the format ``https://web.archive.org/web/{timestamp}if_/{original}``.
        """
        return f"https://web.archive.org/web/{self.timestamp}if_/{self.original}"

    @computed_field(return_type=_dt.datetime)  # type: ignore[prop-decorator]
    @property
    def datetime(self) -> _dt.datetime:
        """
        Parse the CDX timestamp into a timezone-aware Python datetime object.

        Returns
        -------
        datetime.datetime
            UTC-aware datetime parsed from the 14-digit timestamp.
        """
        return _dt.datetime.strptime(self.timestamp, "%Y%m%d%H%M%S").replace(
            tzinfo=_dt.timezone.utc
        )


class RecoveredVideoData(BaseModel):
    """
    Metadata extracted from an archived YouTube page.

    Contains optional fields for all recoverable video metadata. Only
    ``snapshot_timestamp`` is required. All other fields default to None
    or empty lists.

    Attributes
    ----------
    title : str | None
        Video title, if recovered.
    description : str | None
        Video description, if recovered.
    channel_name_hint : str | None
        Channel display name for future resolution (source: videoDetails.author).
    channel_id : str | None
        YouTube channel ID (must match UC[A-Za-z0-9_-]{22} if provided).
    view_count : int | None
        View count at the time of archival. Must be >= 0.
    like_count : int | None
        Like count at the time of archival. Must be >= 0.
    upload_date : datetime.datetime | None
        Original upload date, if recovered.
    thumbnail_url : str | None
        Thumbnail URL, if recovered.
    tags : list[str]
        Video tags extracted from the archived page.
    category_id : str | None
        YouTube category ID, if recovered.
    snapshot_timestamp : str
        CDX timestamp of the snapshot used for extraction. Must be 14 digits.
    """

    title: str | None = None
    description: str | None = None
    channel_name_hint: str | None = None
    channel_id: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    upload_date: _dt.datetime | None = None
    thumbnail_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    category_id: str | None = None
    snapshot_timestamp: str

    @field_validator("snapshot_timestamp")
    @classmethod
    def validate_snapshot_timestamp(cls, v: str) -> str:
        """
        Validate that snapshot_timestamp is exactly 14 digits.

        Parameters
        ----------
        v : str
            The snapshot timestamp to validate.

        Returns
        -------
        str
            The validated snapshot timestamp.

        Raises
        ------
        ValueError
            If snapshot_timestamp is not exactly 14 digits.
        """
        if not re.match(r"^\d{14}$", v):
            raise ValueError(
                f"snapshot_timestamp must be exactly 14 digits, got '{v}'"
            )
        return v

    @field_validator("channel_id", mode="before")
    @classmethod
    def validate_channel_id(cls, v: Any) -> str | None:
        """
        Validate channel_id matches YouTube channel ID format if provided.

        Parameters
        ----------
        v : Any
            The channel ID value to validate.

        Returns
        -------
        str | None
            The validated channel ID, or None.

        Raises
        ------
        ValueError
            If channel_id is provided but does not match ``UC[A-Za-z0-9_-]{22}``.
        """
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError(f"channel_id must be a string, got {type(v).__name__}")
        if not re.match(r"^UC[A-Za-z0-9_-]{22}$", v):
            raise ValueError(
                f"channel_id must match UC[A-Za-z0-9_-]{{22}}, got '{v}'"
            )
        return v

    @field_validator("view_count")
    @classmethod
    def validate_view_count(cls, v: int | None) -> int | None:
        """
        Validate that view_count is non-negative if provided.

        Parameters
        ----------
        v : int | None
            The view count to validate.

        Returns
        -------
        int | None
            The validated view count.

        Raises
        ------
        ValueError
            If view_count is negative.
        """
        if v is not None and v < 0:
            raise ValueError(f"view_count must be >= 0, got {v}")
        return v

    @field_validator("like_count")
    @classmethod
    def validate_like_count(cls, v: int | None) -> int | None:
        """
        Validate that like_count is non-negative if provided.

        Parameters
        ----------
        v : int | None
            The like count to validate.

        Returns
        -------
        int | None
            The validated like count.

        Raises
        ------
        ValueError
            If like_count is negative.
        """
        if v is not None and v < 0:
            raise ValueError(f"like_count must be >= 0, got {v}")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def recovery_source(self) -> str:
        """
        Recovery source identifier combining source type and timestamp.

        Returns
        -------
        str
            String in the format ``wayback:{snapshot_timestamp}``.
        """
        return f"wayback:{self.snapshot_timestamp}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def recovered_fields(self) -> list[str]:
        """
        List of field names that have non-None values.

        Excludes ``tags`` if the list is empty (no tags recovered).
        Always includes ``snapshot_timestamp`` since it is required.

        Returns
        -------
        list[str]
            List of field names with recovered (non-None) values.
        """
        _metadata_fields = [
            "title",
            "description",
            "channel_name_hint",
            "channel_id",
            "view_count",
            "like_count",
            "upload_date",
            "thumbnail_url",
            "category_id",
        ]
        fields: list[str] = ["snapshot_timestamp"]
        for field_name in _metadata_fields:
            if getattr(self, field_name) is not None:
                fields.append(field_name)
        if self.tags:
            fields.append("tags")
        return fields

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_data(self) -> bool:
        """
        Check if at least one metadata field has been recovered.

        Metadata fields are all optional fields except ``snapshot_timestamp``
        and ``tags`` (when empty).

        Returns
        -------
        bool
            True if at least one metadata field is non-None.
        """
        _metadata_fields = [
            "title",
            "description",
            "channel_name_hint",
            "channel_id",
            "view_count",
            "like_count",
            "upload_date",
            "thumbnail_url",
            "category_id",
        ]
        return any(getattr(self, f) is not None for f in _metadata_fields)


class RecoveryResult(BaseModel):
    """
    Outcome of a single video recovery attempt.

    Captures the full context of a recovery operation, including whether it
    succeeded, which fields were recovered, which snapshot was used, and
    any failure reason.

    Attributes
    ----------
    video_id : VideoId
        YouTube video ID (11 characters, alphanumeric with hyphens/underscores).
    success : bool
        Whether the recovery attempt succeeded.
    snapshot_used : str | None
        CDX timestamp of the snapshot used for recovery.
    fields_recovered : list[str]
        Names of fields successfully recovered.
    fields_skipped : list[str]
        Names of fields that were skipped during recovery.
    snapshots_available : int
        Total number of CDX snapshots found.
    snapshots_tried : int
        Number of snapshots attempted before success or exhaustion.
    failure_reason : str | None
        Reason for failure, if ``success`` is False.
    duration_seconds : float
        Wall-clock time for the recovery operation.
    channel_recovery_candidates : list[str]
        Channel IDs discovered during recovery that may need their own recovery.
    """

    video_id: VideoId
    success: bool
    snapshot_used: str | None = None
    fields_recovered: list[str] = Field(default_factory=list)
    fields_skipped: list[str] = Field(default_factory=list)
    snapshots_available: int = 0
    snapshots_tried: int = 0
    failure_reason: str | None = None
    duration_seconds: float = 0.0
    channel_recovery_candidates: list[str] = Field(default_factory=list)


class CdxCacheEntry(BaseModel):
    """
    File-based cache entry for CDX API responses.

    Stores the result of a CDX API query along with metadata for
    cache invalidation. The ``is_valid`` method checks whether the
    cache entry is still fresh based on a configurable TTL.

    Attributes
    ----------
    video_id : str
        YouTube video ID (plain string, not validated as VideoId).
    fetched_at : datetime.datetime
        Timestamp when the CDX response was fetched. Must be timezone-aware (UTC).
    snapshots : list[CdxSnapshot]
        Filtered CDX snapshots from the API response.
    raw_count : int
        Total number of CDX entries before filtering.
    """

    video_id: str
    fetched_at: _dt.datetime
    snapshots: list[CdxSnapshot]
    raw_count: int

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, v: _dt.datetime) -> _dt.datetime:
        """
        Validate that fetched_at is timezone-aware.

        Parameters
        ----------
        v : datetime.datetime
            The datetime to validate.

        Returns
        -------
        datetime.datetime
            The validated timezone-aware datetime.

        Raises
        ------
        ValueError
            If fetched_at is a naive (timezone-unaware) datetime.
        """
        if v.tzinfo is None:
            raise ValueError(
                "fetched_at must be timezone-aware (has tzinfo), "
                "got naive datetime"
            )
        return v

    def is_valid(self, ttl_hours: int = 24) -> bool:
        """
        Check whether this cache entry is still valid.

        Parameters
        ----------
        ttl_hours : int, optional
            Time-to-live in hours (default is 24).

        Returns
        -------
        bool
            True if the cache entry age is less than ``ttl_hours``.
        """
        now = _dt.datetime.now(_dt.timezone.utc)
        age = now - self.fetched_at
        return age < _dt.timedelta(hours=ttl_hours)
