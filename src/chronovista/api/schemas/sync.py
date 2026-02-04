"""Sync API schemas for synchronization operations.

Defines schemas for sync operations including starting syncs,
tracking progress, and reporting status.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SyncOperationType(str, Enum):
    """Types of sync operations available.

    Each operation type corresponds to a specific data synchronization
    with the YouTube API.
    """

    SUBSCRIPTIONS = "subscriptions"
    VIDEOS = "videos"
    TRANSCRIPTS = "transcripts"
    PLAYLISTS = "playlists"
    TOPICS = "topics"
    CHANNEL = "channel"
    LIKED = "liked"


class SyncOperationStatus(str, Enum):
    """Status of a sync operation.

    Represents the current state of a sync operation lifecycle.
    """

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncStarted(BaseModel):
    """Response data when a sync operation is triggered.

    Contains information about the newly started sync operation
    including its unique identifier and timestamp.
    """

    model_config = ConfigDict(strict=True)

    operation_id: str = Field(
        ...,
        description="Unique operation ID in format: {type}_{timestamp}_{random}",
        examples=["subscriptions_1706900000_a1b2c3"],
    )
    operation_type: SyncOperationType
    started_at: datetime
    message: str = Field(..., description="Human-readable status message")

    @field_validator("operation_id")
    @classmethod
    def validate_operation_id_format(cls, v: str) -> str:
        """Validate operation_id follows the expected format.

        Format: {type}_{timestamp}_{random}
        - Timestamp: YYYYMMDDTHHMMSSZ (ISO basic format, UTC)
        - Random: 4-6 character alphanumeric suffix
        Example: subscriptions_20260201T143052Z_a7b3c9

        Parameters
        ----------
        v : str
            The operation_id value to validate.

        Returns
        -------
        str
            The validated operation_id.

        Raises
        ------
        ValueError
            If the format is invalid.
        """
        # Pattern matches: {type}_{YYYYMMDDTHHMMSSZ}_{random}
        # Type: lowercase letters
        # Timestamp: 8 digits, T, 6 digits, Z
        # Random: 4-6 alphanumeric characters
        pattern = r"^[a-z]+_\d{8}T\d{6}Z_[a-zA-Z0-9]{4,6}$"
        if not re.match(pattern, v):
            raise ValueError(
                f"operation_id must match format '{{type}}_{{YYYYMMDDTHHMMSSZ}}_{{random}}', "
                f"got '{v}'"
            )
        return v


class SyncStartedResponse(BaseModel):
    """Wrapped response for sync started."""

    model_config = ConfigDict(strict=True)

    data: SyncStarted


class SyncProgress(BaseModel):
    """Progress information for an ongoing sync operation.

    Tracks the progress of a sync operation including item counts
    and time estimates.
    """

    model_config = ConfigDict(strict=True)

    total_items: Optional[int] = Field(
        None, description="Total items to process (None if unknown)"
    )
    processed_items: int = Field(0, ge=0, description="Number of items processed so far")
    current_item: Optional[str] = Field(
        None, description="Identifier of the item currently being processed"
    )
    estimated_remaining: Optional[int] = Field(
        None, ge=0, description="Estimated seconds remaining (None if unknown)"
    )


class SyncStatus(BaseModel):
    """Current sync status information.

    Provides comprehensive status information about sync operations
    including current state, progress, and history.
    """

    model_config = ConfigDict(strict=True)

    status: SyncOperationStatus
    operation_type: Optional[SyncOperationType] = Field(
        None, description="Type of current/last operation"
    )
    operation_id: Optional[str] = Field(
        None, description="ID of current/last operation"
    )
    progress: Optional[SyncProgress] = Field(
        None, description="Progress info (only when running)"
    )
    last_successful_sync: Optional[datetime] = Field(
        None, description="Timestamp of last successful sync"
    )
    error_message: Optional[str] = Field(
        None, description="Error message if status is failed"
    )
    started_at: Optional[datetime] = Field(
        None, description="When the current/last operation started"
    )
    completed_at: Optional[datetime] = Field(
        None, description="When the current/last operation completed"
    )

    @field_validator("operation_id")
    @classmethod
    def validate_operation_id_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate operation_id follows the expected format if provided.

        Format: {type}_{timestamp}_{random}
        - Timestamp: YYYYMMDDTHHMMSSZ (ISO basic format, UTC)
        - Random: 4-6 character alphanumeric suffix

        Parameters
        ----------
        v : Optional[str]
            The operation_id value to validate.

        Returns
        -------
        Optional[str]
            The validated operation_id or None.

        Raises
        ------
        ValueError
            If the format is invalid.
        """
        if v is None:
            return v
        # Pattern matches: {type}_{YYYYMMDDTHHMMSSZ}_{random}
        pattern = r"^[a-z]+_\d{8}T\d{6}Z_[a-zA-Z0-9]{4,6}$"
        if not re.match(pattern, v):
            raise ValueError(
                f"operation_id must match format '{{type}}_{{YYYYMMDDTHHMMSSZ}}_{{random}}', "
                f"got '{v}'"
            )
        return v


class SyncStatusResponse(BaseModel):
    """Wrapped response for sync status."""

    model_config = ConfigDict(strict=True)

    data: SyncStatus


class TranscriptSyncRequest(BaseModel):
    """Request body for transcript synchronization.

    Configures which videos and languages to sync transcripts for.
    """

    model_config = ConfigDict(strict=True)

    video_ids: Optional[list[str]] = Field(
        None,
        description="Video IDs to sync transcripts for. "
        "If None, syncs all videos without transcripts.",
    )
    languages: list[str] = Field(
        default=["en"],
        description="BCP-47 language codes to prioritize for transcript download",
    )
    force: bool = Field(
        default=False,
        description="If True, re-download transcripts even if they already exist",
    )

    @field_validator("video_ids")
    @classmethod
    def validate_video_ids(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """Validate video IDs are non-empty strings if provided.

        Parameters
        ----------
        v : Optional[list[str]]
            The list of video IDs to validate.

        Returns
        -------
        Optional[list[str]]
            The validated list or None.

        Raises
        ------
        ValueError
            If any video ID is empty or invalid.
        """
        if v is None:
            return v
        if len(v) == 0:
            return None  # Treat empty list as None (sync all)
        for video_id in v:
            if not video_id or not video_id.strip():
                raise ValueError("Video IDs cannot be empty strings")
        return v

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, v: list[str]) -> list[str]:
        """Validate languages list is not empty and contains valid codes.

        Parameters
        ----------
        v : list[str]
            The list of language codes to validate.

        Returns
        -------
        list[str]
            The validated list of language codes.

        Raises
        ------
        ValueError
            If the list is empty or contains invalid codes.
        """
        if not v:
            raise ValueError("At least one language code must be provided")
        for lang in v:
            if not lang or not lang.strip():
                raise ValueError("Language codes cannot be empty strings")
            # Basic BCP-47 format validation (2-3 letter base, optional region)
            if not re.match(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?$", lang):
                raise ValueError(
                    f"Invalid BCP-47 language code format: '{lang}'. "
                    f"Expected format like 'en', 'en-US', 'zh-CN'"
                )
        return v
