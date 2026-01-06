"""
Enrichment service for video metadata enrichment operations.

This module provides the main orchestrator for enriching video metadata from
the YouTube Data API, including the EnrichmentLock class for preventing
concurrent enrichment runs.

The EnrichmentService is the main entry point for all enrichment operations,
coordinating between repositories and the YouTube API to enrich video metadata
with tags, topics, and categories.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from urllib.parse import unquote

from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.exceptions import (
    GracefulShutdownException,
    PrerequisiteError,
    QuotaExceededException,
)
from chronovista.models.enrichment_report import (
    EnrichmentDetail,
    EnrichmentReport,
    EnrichmentSummary,
)
from chronovista.services.enrichment.shutdown_handler import get_shutdown_handler

if TYPE_CHECKING:
    from chronovista.repositories.channel_repository import ChannelRepository
    from chronovista.repositories.playlist_repository import PlaylistRepository
    from chronovista.repositories.topic_category_repository import (
        TopicCategoryRepository,
    )
    from chronovista.repositories.video_category_repository import (
        VideoCategoryRepository,
    )
    from chronovista.repositories.video_repository import VideoRepository
    from chronovista.repositories.video_tag_repository import VideoTagRepository
    from chronovista.repositories.video_topic_repository import VideoTopicRepository
    from chronovista.services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)


# Constants for placeholder detection
VIDEO_PLACEHOLDER_PREFIX = "[Placeholder] Video "
CHANNEL_PLACEHOLDER_PREFIXES = ("[Placeholder]", "[Unknown")
PLAYLIST_PLACEHOLDER_PREFIXES = ("[Placeholder]", "[Takeout Playlist]")

# Wikipedia URL pattern for topic extraction (FR-034)
# Pattern: https://en.wikipedia.org/wiki/Topic_Name
# Only process en.wikipedia.org URLs; skip non-English with warning
WIKIPEDIA_URL_PATTERN = re.compile(
    r"^https?://([a-z]{2})\.wikipedia\.org/wiki/([^#?]+)(?:[#?].*)?$"
)

# Exit codes for CLI integration (per cli-commands.md contract)
# 0: Success
# 1: Database error / general error
# 2: API error (credentials missing)
# 3: Quota exceeded
# 4: Concurrent execution lock failed
# 130: Interrupted (SIGINT/SIGTERM)
EXIT_CODE_NO_CREDENTIALS = 2
EXIT_CODE_LOCK_FAILED = 4

# Batch size for API calls
BATCH_SIZE = 50


def sanitize_text(text: str | None) -> str | None:
    """
    Sanitize text by removing NULL bytes and other invalid characters.

    PostgreSQL UTF-8 encoding doesn't allow NULL bytes (0x00) in text fields.
    The YouTube API occasionally returns descriptions or titles containing
    NULL bytes, which causes database write errors.

    Parameters
    ----------
    text : str | None
        Text to sanitize. If None, returns None.

    Returns
    -------
    str | None
        Sanitized text with NULL bytes removed, or None if input was None.

    Examples
    --------
    >>> sanitize_text("Hello\\x00World")
    'HelloWorld'
    >>> sanitize_text(None)
    None
    """
    if text is None:
        return None
    # Remove NULL bytes (0x00) which PostgreSQL UTF-8 doesn't allow
    return text.replace("\x00", "")


# Maximum tag length for database schema (matches video_tags.tag column)
# YouTube's total tag limit is 500 characters combined, so individual tags
# could theoretically approach this limit.
MAX_TAG_LENGTH = 500


def truncate_tag(tag: str) -> str:
    """
    Truncate a tag to the maximum allowed length.

    YouTube's total tag limit is 500 characters combined for all tags.
    Individual tags exceeding this limit are truncated as a safety measure.

    Parameters
    ----------
    tag : str
        Tag string to truncate.

    Returns
    -------
    str
        Tag truncated to MAX_TAG_LENGTH characters if necessary.

    Examples
    --------
    >>> truncate_tag("short tag")
    'short tag'
    >>> truncate_tag("a" * 600)
    'aaaa...' (500 characters)
    """
    if len(tag) > MAX_TAG_LENGTH:
        logger.warning(
            f"Truncating tag from {len(tag)} to {MAX_TAG_LENGTH} chars: '{tag[:50]}...'"
        )
        return tag[:MAX_TAG_LENGTH]
    return tag


def parse_iso8601_duration(duration_str: str) -> int:
    """
    Parse ISO 8601 duration string to seconds.

    YouTube API returns duration in ISO 8601 format like:
    - PT1H2M3S (1 hour, 2 minutes, 3 seconds)
    - PT5M30S (5 minutes, 30 seconds)
    - PT45S (45 seconds)
    - P1DT2H (1 day, 2 hours)

    Parameters
    ----------
    duration_str : str
        ISO 8601 duration string (e.g., "PT1H2M3S")

    Returns
    -------
    int
        Duration in seconds

    Examples
    --------
    >>> parse_iso8601_duration("PT1H2M3S")
    3723
    >>> parse_iso8601_duration("PT5M30S")
    330
    >>> parse_iso8601_duration("PT45S")
    45
    """
    if not duration_str:
        return 0

    # Handle cases like "P0D" (zero duration)
    if duration_str in ("P0D", "PT0S", "P"):
        return 0

    # Pattern to match ISO 8601 duration components
    pattern = r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
    match = re.match(pattern, duration_str)

    if not match:
        logger.warning(f"Could not parse duration: {duration_str}")
        return 0

    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def is_placeholder_video_title(title: str) -> bool:
    """Check if a video title is a placeholder."""
    return title.startswith(VIDEO_PLACEHOLDER_PREFIX)


def is_placeholder_channel_name(name: str) -> bool:
    """Check if a channel name is a placeholder."""
    return any(name.startswith(prefix) for prefix in CHANNEL_PLACEHOLDER_PREFIXES)


def estimate_quota_cost(video_count: int, batch_size: int = BATCH_SIZE) -> int:
    """
    Estimate YouTube API quota cost for enriching videos.

    The videos.list API costs 1 quota unit per request, and we can
    batch up to 50 video IDs per request.

    Parameters
    ----------
    video_count : int
        Number of videos to enrich
    batch_size : int
        Videos per API request (max 50)

    Returns
    -------
    int
        Estimated quota units to be used
    """
    if video_count <= 0:
        return 0
    return (video_count + batch_size - 1) // batch_size  # Ceiling division


class LockAcquisitionError(Exception):
    """
    Exception raised when enrichment lock cannot be acquired.

    This exception is raised when another enrichment process is already running
    and the lock cannot be acquired. It includes the PID of the process holding
    the lock (if available) for diagnostic purposes.

    Attributes
    ----------
    pid : int | None
        The process ID of the lock holder (for file-based locks).
    message : str
        Human-readable error message.

    Examples
    --------
    >>> try:
    ...     await lock.acquire(session)
    ... except LockAcquisitionError as e:
    ...     print(f"Lock held by PID: {e.pid}")
    ...     print(e.message)
    """

    def __init__(self, message: str, pid: int | None = None) -> None:
        """
        Initialize LockAcquisitionError.

        Parameters
        ----------
        message : str
            Human-readable error message.
        pid : int | None, optional
            The process ID of the lock holder (default None).
        """
        self.message = message
        self.pid = pid
        super().__init__(message)

    def __str__(self) -> str:
        """Return string representation with PID info if available."""
        if self.pid is not None:
            return f"{self.message} (PID: {self.pid})"
        return self.message


class LockInfo(BaseModel):
    """Information about an acquired lock."""

    lock_type: str = Field(..., description="Type of lock: 'postgresql' or 'file'")
    acquired_at: datetime = Field(
        default_factory=datetime.now, description="When the lock was acquired"
    )
    pid: int = Field(
        default_factory=os.getpid, description="Process ID that holds the lock"
    )


class PriorityTierEstimate(BaseModel):
    """Quota estimate for a priority tier."""

    count: int = Field(..., description="Number of videos in this tier")
    quota_units: int = Field(..., description="Estimated quota units to enrich")


class EnrichmentStatus(BaseModel):
    """
    Current enrichment status and statistics.

    This model captures the complete state of video enrichment progress,
    including video/channel counts, enrichment progress, and quota estimates
    for each priority tier.
    """

    # Video counts
    total_videos: int = Field(..., description="Total videos in database")
    placeholder_videos: int = Field(..., description="Videos with placeholder titles")
    deleted_videos: int = Field(..., description="Videos marked as deleted")
    fully_enriched_videos: int = Field(..., description="Videos with complete metadata")

    # T075: Videos missing tags count
    videos_missing_tags: int = Field(
        default=0,
        description="Videos that have no tags associated (non-deleted only)",
    )

    # T084: Videos missing topics count
    videos_missing_topics: int = Field(
        default=0,
        description="Videos that have no topics associated (non-deleted only)",
    )

    # T090: Videos missing category count (FR-048)
    videos_missing_category: int = Field(
        default=0,
        description="Videos that have no category assigned (non-deleted only)",
    )

    # Channel counts
    total_channels: int = Field(..., description="Total channels in database")
    placeholder_channels: int = Field(
        ..., description="Channels with placeholder names"
    )

    # Enrichment progress
    enrichment_percentage: float = Field(
        ..., description="Percentage of videos fully enriched"
    )

    # Priority tier estimates
    tier_high: PriorityTierEstimate = Field(
        ..., description="HIGH priority tier estimate"
    )
    tier_medium: PriorityTierEstimate = Field(
        ..., description="MEDIUM priority tier estimate"
    )
    tier_low: PriorityTierEstimate = Field(
        ..., description="LOW priority tier estimate"
    )
    tier_all: PriorityTierEstimate = Field(
        ..., description="ALL priority tier estimate"
    )


class EnrichmentLock:
    """
    Advisory lock for preventing concurrent enrichment runs.

    This class implements a dual-strategy locking mechanism per FR-055 to FR-058:
    1. PostgreSQL advisory lock using pg_advisory_lock() - preferred when a
       database session is available
    2. File-based lock at ~/.chronovista/enrichment.lock - fallback when no
       session is available or for cross-process locking

    The lock ID is derived from a stable hash of 'chronovista.enrichment' to
    ensure consistent locking across processes.

    Attributes
    ----------
    LOCK_ID : int
        PostgreSQL advisory lock ID (32-bit signed integer).
    LOCK_FILE : Path
        Path to the file-based lock file.

    Examples
    --------
    >>> lock = EnrichmentLock()
    >>> async with session_maker() as session:
    ...     try:
    ...         await lock.acquire(session)
    ...         # Perform enrichment
    ...     finally:
    ...         await lock.release(session)

    >>> # With force flag
    >>> await lock.acquire(session, force=True)  # Overrides existing lock
    """

    # PostgreSQL advisory lock ID - derived from hash of 'chronovista.enrichment'
    # Masked to 32-bit signed integer range for PostgreSQL compatibility
    LOCK_ID: int = hash("chronovista.enrichment") & 0x7FFFFFFF

    # File-based lock location
    LOCK_FILE: Path = Path.home() / ".chronovista" / "enrichment.lock"

    def __init__(self) -> None:
        """Initialize EnrichmentLock."""
        self._lock_info: LockInfo | None = None
        self._has_pg_lock: bool = False
        self._has_file_lock: bool = False

    @property
    def is_locked(self) -> bool:
        """Check if this instance holds a lock."""
        return self._lock_info is not None

    async def acquire(
        self,
        session: AsyncSession | None = None,
        force: bool = False,
    ) -> bool:
        """
        Acquire the enrichment lock.

        Attempts to acquire a PostgreSQL advisory lock if a session is provided,
        otherwise falls back to file-based locking. If force=True, any existing
        lock will be released first.

        Per FR-055 to FR-058:
        - FR-055: Uses pg_advisory_lock() with stable lock ID, file fallback
        - FR-056: Returns lock holder PID in error message
        - FR-057: Raises LockAcquisitionError (CLI should exit with code 4)
        - FR-058: force=True overrides existing lock with warning

        Parameters
        ----------
        session : AsyncSession | None, optional
            Database session for PostgreSQL advisory lock (default None).
            If None, uses file-based locking only.
        force : bool, optional
            If True, override any existing lock with a warning (default False).

        Returns
        -------
        bool
            True if lock was acquired successfully.

        Raises
        ------
        LockAcquisitionError
            If the lock cannot be acquired and force=False.
            Includes PID of lock holder for file-based locks.

        Examples
        --------
        >>> lock = EnrichmentLock()
        >>> acquired = await lock.acquire(session)
        >>> if acquired:
        ...     print("Lock acquired!")

        >>> # Force acquire (override existing lock)
        >>> acquired = await lock.acquire(session, force=True)
        """
        # If forcing, release any existing lock first
        if force:
            logger.warning("Force flag set - overriding any existing enrichment lock")
            await self._force_release(session)

        # Try PostgreSQL advisory lock first if session is available
        if session is not None:
            try:
                acquired = await self._acquire_pg_lock(session, force)
                if acquired:
                    self._lock_info = LockInfo(lock_type="postgresql")
                    self._has_pg_lock = True
                    logger.info(
                        f"Acquired PostgreSQL advisory lock (ID: {self.LOCK_ID})"
                    )
                    return True
            except Exception as e:
                logger.warning(
                    f"PostgreSQL advisory lock failed, falling back to file lock: {e}"
                )

        # Fall back to file-based lock
        acquired = await self._acquire_file_lock(force)
        if acquired:
            self._lock_info = LockInfo(lock_type="file")
            self._has_file_lock = True
            logger.info(f"Acquired file-based lock at {self.LOCK_FILE}")
            return True

        # Lock acquisition failed
        holder_pid = self.get_lock_holder_pid()
        message = (
            "Another enrichment process is running. "
            "Wait for completion or use --force to override."
        )
        raise LockAcquisitionError(message=message, pid=holder_pid)

    async def release(self, session: AsyncSession | None = None) -> None:
        """
        Release the enrichment lock.

        Releases both PostgreSQL advisory lock and file-based lock if held.
        Safe to call even if no lock is held.

        Parameters
        ----------
        session : AsyncSession | None, optional
            Database session for releasing PostgreSQL advisory lock.
            Required if PostgreSQL lock was acquired.

        Examples
        --------
        >>> lock = EnrichmentLock()
        >>> await lock.acquire(session)
        >>> # ... perform enrichment ...
        >>> await lock.release(session)
        """
        # Release PostgreSQL advisory lock
        if self._has_pg_lock:
            if session is not None:
                try:
                    await self._release_pg_lock(session)
                    logger.info(f"Released PostgreSQL advisory lock (ID: {self.LOCK_ID})")
                except Exception as e:
                    logger.warning(f"Failed to release PostgreSQL advisory lock: {e}")
            else:
                logger.warning("Cannot release PostgreSQL advisory lock without session")
            # Always mark as released, even if we couldn't actually release it
            self._has_pg_lock = False

        # Release file-based lock
        if self._has_file_lock:
            self._release_file_lock()
            logger.info(f"Released file-based lock at {self.LOCK_FILE}")
            self._has_file_lock = False

        self._lock_info = None

    def get_lock_holder_pid(self) -> int | None:
        """
        Get PID of process holding the file-based lock.

        Reads the PID from the lock file if it exists. Returns None if the
        lock file doesn't exist or cannot be read.

        Returns
        -------
        int | None
            Process ID of the lock holder, or None if unavailable.

        Examples
        --------
        >>> lock = EnrichmentLock()
        >>> pid = lock.get_lock_holder_pid()
        >>> if pid:
        ...     print(f"Lock held by process {pid}")
        """
        try:
            if self.LOCK_FILE.exists():
                content = self.LOCK_FILE.read_text().strip()
                if content:
                    return int(content)
        except (ValueError, OSError) as e:
            logger.debug(f"Could not read lock holder PID: {e}")
        return None

    async def _acquire_pg_lock(
        self, session: AsyncSession, force: bool = False
    ) -> bool:
        """
        Acquire PostgreSQL advisory lock.

        Uses pg_try_advisory_lock() for non-blocking acquisition attempt.
        If force=True and lock is held, uses pg_advisory_unlock() first.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        force : bool
            If True, try to force-unlock first.

        Returns
        -------
        bool
            True if lock was acquired.
        """
        if force:
            # Try to unlock first (will succeed if we hold the lock)
            try:
                await session.execute(
                    text(f"SELECT pg_advisory_unlock({self.LOCK_ID})")
                )
            except Exception:
                pass  # Ignore errors - we might not hold the lock

        # Try to acquire the lock (non-blocking)
        result = await session.execute(
            text(f"SELECT pg_try_advisory_lock({self.LOCK_ID})")
        )
        row = result.fetchone()
        return bool(row and row[0])

    async def _release_pg_lock(self, session: AsyncSession) -> None:
        """
        Release PostgreSQL advisory lock.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        """
        await session.execute(text(f"SELECT pg_advisory_unlock({self.LOCK_ID})"))

    async def _acquire_file_lock(self, force: bool = False) -> bool:
        """
        Acquire file-based lock.

        Creates the lock file and writes the current PID. If force=True,
        removes any existing lock file first.

        Parameters
        ----------
        force : bool
            If True, remove existing lock file first.

        Returns
        -------
        bool
            True if lock was acquired.
        """
        # Ensure directory exists
        self.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Handle force mode
        if force and self.LOCK_FILE.exists():
            try:
                self.LOCK_FILE.unlink()
                logger.warning(f"Force-removed existing lock file: {self.LOCK_FILE}")
            except OSError as e:
                logger.error(f"Failed to force-remove lock file: {e}")
                return False

        # Check if lock file already exists
        if self.LOCK_FILE.exists():
            # Check if the process is still running
            holder_pid = self.get_lock_holder_pid()
            if holder_pid is not None:
                try:
                    # Check if process exists (signal 0 doesn't send anything)
                    os.kill(holder_pid, 0)
                    # Process is still running, lock is valid
                    return False
                except OSError:
                    # Process is not running, stale lock file
                    logger.info(
                        f"Removing stale lock file (PID {holder_pid} no longer running)"
                    )
                    try:
                        self.LOCK_FILE.unlink()
                    except OSError:
                        return False

        # Try to create the lock file atomically
        try:
            # Use os.open with O_CREAT | O_EXCL for atomic creation
            fd = os.open(
                str(self.LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644
            )
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            # Another process created the file between our check and create
            return False
        except OSError as e:
            logger.error(f"Failed to create lock file: {e}")
            return False

    def _release_file_lock(self) -> None:
        """Release file-based lock by removing the lock file."""
        try:
            if self.LOCK_FILE.exists():
                # Only remove if we own the lock (PID matches)
                holder_pid = self.get_lock_holder_pid()
                if holder_pid == os.getpid():
                    self.LOCK_FILE.unlink()
                else:
                    logger.warning(
                        f"Not removing lock file - owned by different process "
                        f"(ours: {os.getpid()}, file: {holder_pid})"
                    )
        except OSError as e:
            logger.warning(f"Failed to remove lock file: {e}")

    async def _force_release(self, session: AsyncSession | None = None) -> None:
        """
        Force release all locks (used with --force flag).

        Parameters
        ----------
        session : AsyncSession | None
            Database session for PostgreSQL lock release.
        """
        # Force release PostgreSQL lock
        if session is not None:
            try:
                await session.execute(text(f"SELECT pg_advisory_unlock_all()"))
            except Exception as e:
                logger.debug(f"pg_advisory_unlock_all failed: {e}")

        # Force release file lock
        if self.LOCK_FILE.exists():
            try:
                self.LOCK_FILE.unlink()
                logger.info(f"Force-removed lock file: {self.LOCK_FILE}")
            except OSError as e:
                logger.warning(f"Failed to force-remove lock file: {e}")


class EnrichmentService:
    """
    Main orchestrator for video metadata enrichment.

    This service coordinates the enrichment of video metadata from the YouTube
    Data API, including tags, topics, and categories. It manages the enrichment
    lifecycle including lock acquisition, batch processing, and reporting.

    The service is designed to be used with dependency injection, accepting
    repositories and services as constructor arguments for testability.

    Attributes
    ----------
    video_repository : VideoRepository
        Repository for video CRUD operations.
    channel_repository : ChannelRepository
        Repository for channel CRUD operations.
    video_tag_repository : VideoTagRepository
        Repository for video tag operations.
    video_topic_repository : VideoTopicRepository
        Repository for video-topic associations.
    video_category_repository : VideoCategoryRepository
        Repository for video category assignments.
    topic_category_repository : TopicCategoryRepository
        Repository for topic category lookups.
    youtube_service : YouTubeService
        Service for YouTube Data API calls.

    Examples
    --------
    >>> service = EnrichmentService(
    ...     video_repository=video_repo,
    ...     channel_repository=channel_repo,
    ...     video_tag_repository=tag_repo,
    ...     video_topic_repository=topic_repo,
    ...     video_category_repository=category_repo,
    ...     topic_category_repository=topic_cat_repo,
    ...     youtube_service=yt_service,
    ... )
    >>> async with session_maker() as session:
    ...     report = await service.enrich_videos(session, priority="high")
    ...     print(f"Enriched {report.summary.videos_updated} videos")
    """

    def __init__(
        self,
        video_repository: VideoRepository,
        channel_repository: ChannelRepository,
        video_tag_repository: VideoTagRepository,
        video_topic_repository: VideoTopicRepository,
        video_category_repository: VideoCategoryRepository,
        topic_category_repository: TopicCategoryRepository,
        youtube_service: YouTubeService,
        playlist_repository: Optional[PlaylistRepository] = None,
    ) -> None:
        """
        Initialize EnrichmentService.

        Parameters
        ----------
        video_repository : VideoRepository
            Repository for video CRUD operations.
        channel_repository : ChannelRepository
            Repository for channel CRUD operations.
        video_tag_repository : VideoTagRepository
            Repository for video tag operations.
        video_topic_repository : VideoTopicRepository
            Repository for video-topic associations.
        video_category_repository : VideoCategoryRepository
            Repository for video category assignments.
        topic_category_repository : TopicCategoryRepository
            Repository for topic category lookups.
        youtube_service : YouTubeService
            Service for YouTube Data API calls.
        playlist_repository : PlaylistRepository, optional
            Repository for playlist CRUD operations (default None).
            Required for playlist enrichment functionality.
        """
        self.video_repository = video_repository
        self.channel_repository = channel_repository
        self.video_tag_repository = video_tag_repository
        self.video_topic_repository = video_topic_repository
        self.video_category_repository = video_category_repository
        self.topic_category_repository = topic_category_repository
        self.youtube_service = youtube_service
        self.playlist_repository = playlist_repository

        # Lock instance for this service
        self._lock = EnrichmentLock()

    @property
    def lock(self) -> EnrichmentLock:
        """Get the enrichment lock instance."""
        return self._lock

    async def check_prerequisites(self, session: AsyncSession) -> None:
        """
        Check that prerequisite seeding data exists.

        Verifies that topic_categories and video_categories tables have been
        seeded before running enrichment per FR-059 to FR-062.

        Parameters
        ----------
        session : AsyncSession
            Database session for operations.

        Raises
        ------
        PrerequisiteError
            If topic_categories or video_categories tables are empty.
        """
        from chronovista.db.models import TopicCategory as TopicCategoryDB
        from chronovista.db.models import VideoCategory as VideoCategoryDB

        missing_tables: List[str] = []

        # Check topic_categories (FR-059)
        topic_count_query = select(func.count(TopicCategoryDB.topic_id))
        topic_result = await session.execute(topic_count_query)
        topic_count = topic_result.scalar() or 0

        if topic_count == 0:
            missing_tables.append("topic_categories")
            logger.warning(
                "topic_categories table is empty - run 'chronovista seed topics' first"
            )

        # Check video_categories (FR-060)
        category_count_query = select(func.count(VideoCategoryDB.category_id))
        category_result = await session.execute(category_count_query)
        category_count = category_result.scalar() or 0

        if category_count == 0:
            missing_tables.append("video_categories")
            logger.warning(
                "video_categories table is empty - run 'chronovista seed categories' first"
            )

        if missing_tables:
            raise PrerequisiteError(
                message=(
                    f"Missing prerequisite data in: {', '.join(missing_tables)}. "
                    f"Run 'chronovista seed topics' and/or 'chronovista seed categories' "
                    f"first, or use --auto-seed flag to seed automatically."
                ),
                missing_tables=missing_tables,
            )

        logger.info(
            f"Prerequisites verified: {topic_count} topics, {category_count} categories"
        )

    async def enrich_videos(
        self,
        session: AsyncSession,
        priority: str = "high",
        limit: int | None = None,
        include_deleted: bool = False,
        dry_run: bool = False,
        check_prerequisites: bool = True,
    ) -> EnrichmentReport:
        """
        Main enrichment method for batch video processing.

        Fetches video metadata from YouTube Data API and updates local database.
        Processes videos in batches of 50 (API limit) with per-batch commits.

        Implements:
        - T091: Quota exceeded handling - commits current batch and reports
        - T093: Graceful shutdown - checks for signals between batches
        - T094: Partial API responses - handles mixed found/not-found
        - T095: Prerequisite checks for seeding tables

        Parameters
        ----------
        session : AsyncSession
            Database session for operations.
        priority : str, optional
            Priority level for video selection: "high", "medium", "low", "all"
            (default "high"). Higher priority = videos with more missing data.
        limit : int | None, optional
            Maximum number of videos to process (default None = no limit).
        include_deleted : bool, optional
            If True, include videos marked as deleted (default False).
        dry_run : bool, optional
            If True, simulate enrichment without persisting changes (default False).
        check_prerequisites : bool, optional
            If True, verify seeding data exists before enrichment (default True).

        Returns
        -------
        EnrichmentReport
            Detailed report of the enrichment operation.

        Raises
        ------
        PrerequisiteError
            If prerequisite seeding data is missing and check_prerequisites=True.
        QuotaExceededException
            If YouTube API quota is exceeded (partial report included).
        GracefulShutdownException
            If shutdown signal received (partial report included).
        """
        started_at = datetime.now(timezone.utc)
        details: List[EnrichmentDetail] = []

        # Initialize counters
        videos_processed = 0
        videos_updated = 0
        videos_deleted = 0
        channels_created = 0
        tags_created = 0  # T074: Track tags created during enrichment
        topics_created = 0  # T083: Track topic associations created during enrichment
        categories_assigned = 0  # T089: Track category assignments during enrichment
        errors = 0
        quota_used = 0

        # T093: Get shutdown handler for graceful shutdown support
        shutdown = get_shutdown_handler()
        shutdown.reset()  # Reset state for this run

        # T095: Check prerequisites if requested
        if check_prerequisites and not dry_run:
            await self.check_prerequisites(session)

        # Helper to create report (used for partial reports on interrupt/quota)
        def create_report() -> EnrichmentReport:
            return EnrichmentReport(
                timestamp=started_at,
                priority=priority,
                summary=EnrichmentSummary(
                    videos_processed=videos_processed,
                    videos_updated=videos_updated,
                    videos_deleted=videos_deleted,
                    channels_created=channels_created,
                    tags_created=tags_created,
                    topic_associations=topics_created,
                    categories_assigned=categories_assigned,
                    errors=errors,
                    quota_used=quota_used,
                ),
                details=details,
            )

        # Query videos needing enrichment based on priority
        videos_to_enrich = await self._get_videos_for_enrichment(
            session, priority, limit, include_deleted
        )

        if not videos_to_enrich:
            logger.info("No videos found needing enrichment")
            return EnrichmentReport(
                timestamp=started_at,
                priority=priority,
                summary=EnrichmentSummary(
                    videos_processed=0,
                    videos_updated=0,
                    videos_deleted=0,
                    channels_created=0,
                    tags_created=0,
                    topic_associations=0,
                    categories_assigned=0,
                    errors=0,
                    quota_used=0,
                ),
                details=[],
            )

        # Cache video data BEFORE the API call to avoid SQLAlchemy lazy-load issues
        # after long-running operations. The API call can take minutes, during which
        # the DB connection may become stale, causing MissingGreenlet errors.
        video_cache: Dict[str, Dict[str, Any]] = {
            v.video_id: {
                "video_id": v.video_id,
                "title": v.title,
                "channel_id": v.channel_id,
            }
            for v in videos_to_enrich
        }
        video_ids = list(video_cache.keys())
        logger.info(f"Found {len(video_ids)} videos to enrich (priority: {priority})")

        if dry_run:
            # In dry run mode, just report what would be done
            for vid, cached in video_cache.items():
                details.append(
                    EnrichmentDetail(
                        video_id=vid,
                        status="skipped",
                        old_title=cached["title"],
                    )
                )
            return EnrichmentReport(
                timestamp=started_at,
                priority=priority,
                summary=EnrichmentSummary(
                    videos_processed=len(video_ids),
                    videos_updated=0,
                    videos_deleted=0,
                    channels_created=0,
                    tags_created=0,
                    topic_associations=0,
                    categories_assigned=0,
                    errors=0,
                    quota_used=0,
                ),
                details=details,
            )

        # T093: Check for shutdown before API call
        shutdown.check_shutdown()

        try:
            # T091, T094: Fetch video details from YouTube API in batches
            # This handles quota exceeded and partial responses
            api_videos, not_found_ids = await self.youtube_service.fetch_videos_batched(
                video_ids, batch_size=BATCH_SIZE
            )
            quota_used = estimate_quota_cost(len(video_ids))

        except QuotaExceededException as e:
            # T091: Quota exceeded - commit what we have and re-raise
            logger.error(f"Quota exceeded: {e.message}")
            try:
                await session.commit()
                logger.info("Committed partial results before quota exceeded exit")
            except Exception as commit_error:
                logger.error(f"Error committing partial results: {commit_error}")
                await session.rollback()

            # Attach partial report to exception for CLI to use
            e.videos_processed = videos_processed
            raise

        # Create a map of video_id -> API data for quick lookup
        api_data_map: Dict[str, Dict[str, Any]] = {
            v.get("id", ""): v for v in api_videos
        }

        # Process each video using cached IDs (not ORM objects which may have stale connections)
        for video_id in video_ids:
            cached = video_cache[video_id]
            videos_processed += 1

            # T093: Check for shutdown between videos
            try:
                shutdown.check_shutdown()
            except GracefulShutdownException:
                # Commit current batch before shutdown
                logger.info("Shutdown requested - committing current batch")
                try:
                    await session.commit()
                except Exception as e:
                    logger.error(f"Error committing on shutdown: {e}")
                    await session.rollback()
                raise

            try:
                if video_id in not_found_ids:
                    # Video not found = deleted/private
                    # Fetch fresh video object for update
                    await self._mark_video_deleted_by_id(session, video_id, dry_run)
                    videos_deleted += 1
                    details.append(
                        EnrichmentDetail(
                            video_id=video_id,
                            status="deleted",
                            old_title=cached["title"],
                        )
                    )
                    continue

                api_data = api_data_map.get(video_id)
                if not api_data:
                    # Shouldn't happen, but handle gracefully
                    logger.warning(f"No API data for video {video_id}")
                    errors += 1
                    details.append(
                        EnrichmentDetail(
                            video_id=video_id,
                            status="error",
                            error="No API data returned",
                        )
                    )
                    continue

                # Extract video metadata from cached values (avoiding stale ORM objects)
                old_title = cached["title"]
                old_channel_id = cached["channel_id"]
                update_data = self._extract_video_update(api_data)

                # Fetch fresh video object from database for update
                video = await self.video_repository.get(session, video_id)
                if video is None:
                    logger.warning(f"Video {video_id} not found in database")
                    errors += 1
                    details.append(
                        EnrichmentDetail(
                            video_id=video_id,
                            status="error",
                            error="Video not found in database",
                        )
                    )
                    continue

                # Update the video
                for key, value in update_data.items():
                    setattr(video, key, value)

                # Handle channel creation/update
                snippet = api_data.get("snippet", {})
                channel_id = snippet.get("channelId")
                channel_title = snippet.get("channelTitle")

                if channel_id and channel_title:
                    channel_created = await self._ensure_channel_exists(
                        session, channel_id, channel_title
                    )
                    if channel_created:
                        channels_created += 1

                # T068-T073: Enrich tags from snippet.tags array
                # T069: Extract tags from snippet.tags (already a list of strings)
                # T073: Tags are preserved exactly as returned (Unicode/special chars)
                api_tags = snippet.get("tags", [])
                video_tags_count = await self.enrich_tags(session, video_id, api_tags)
                tags_created += video_tags_count

                # T076-T082: Enrich topics from topicDetails.topicCategories
                # T077: Parse Wikipedia URLs and extract topic names
                # T078: Match against pre-seeded topic_categories table
                topic_details = api_data.get("topicDetails", {})
                topic_urls = topic_details.get("topicCategories", [])
                video_topics_count = await self.enrich_topics(
                    session, video_id, topic_urls
                )
                topics_created += video_topics_count

                # T085-T088: Enrich category from snippet.categoryId
                # T086: Extract category ID from API response
                # T087: Match against pre-seeded video_categories table (FR-046)
                # T088: Log warning for unrecognized IDs (FR-047)
                api_category_id = snippet.get("categoryId")
                category_was_assigned = await self.enrich_categories(
                    session, video_id, api_category_id
                )
                if category_was_assigned:
                    categories_assigned += 1

                videos_updated += 1
                details.append(
                    EnrichmentDetail(
                        video_id=video_id,
                        status="updated",
                        old_title=old_title,
                        new_title=update_data.get("title", old_title),
                        old_channel=old_channel_id,
                        new_channel=channel_id,
                        category_id=update_data.get("category_id"),
                        tags_count=video_tags_count,  # T074: Report tags per video
                        topics_count=video_topics_count,  # T083: Report topics per video
                    )
                )

            except Exception as e:
                logger.error(f"Error enriching video {video_id}: {e}")
                errors += 1
                details.append(
                    EnrichmentDetail(
                        video_id=video_id,
                        status="error",
                        error=str(e),
                    )
                )
                # Database errors put the session in DEACTIVE state.
                # Try to rollback to recover, but if that fails (e.g., greenlet
                # context lost), break out of the loop and return partial results.
                try:
                    await session.rollback()
                    logger.info(f"Rolled back after error on video {video_id}, continuing")
                except Exception as rollback_error:
                    logger.error(
                        f"Rollback failed ({rollback_error}), stopping enrichment. "
                        f"Processed {videos_processed} videos before error."
                    )
                    # Return partial results - can't continue safely
                    return create_report()

            # Commit after each batch
            if videos_processed % BATCH_SIZE == 0:
                # T093: Check for shutdown at batch boundaries
                try:
                    shutdown.check_shutdown()
                except GracefulShutdownException:
                    logger.info("Shutdown requested at batch boundary")
                    try:
                        await session.commit()
                        logger.info(
                            f"Committed batch {videos_processed // BATCH_SIZE} "
                            f"before shutdown"
                        )
                    except Exception as e:
                        logger.error(f"Error committing on shutdown: {e}")
                        await session.rollback()
                    raise

                try:
                    await session.commit()
                    logger.info(f"Committed batch {videos_processed // BATCH_SIZE}")
                except Exception as e:
                    logger.error(f"Error committing batch: {e}")
                    await session.rollback()

        # Final commit for remaining videos
        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Error in final commit: {e}")
            await session.rollback()

        return create_report()

    async def _get_videos_for_enrichment(
        self,
        session: AsyncSession,
        priority: str,
        limit: int | None,
        include_deleted: bool,
    ) -> List:
        """
        Query videos that need enrichment based on priority level.

        Priority levels (CUMULATIVE - each tier includes all lower tiers):
        - HIGH: placeholder title AND placeholder channel
        - MEDIUM: HIGH + any placeholder title (regardless of channel)
        - LOW: MEDIUM + any partial data (missing duration, view_count, description)
        - ALL: LOW + deleted videos

        Parameters
        ----------
        session : AsyncSession
            Database session
        priority : str
            Priority level: "high", "medium", "low", or "all"
        limit : int | None
            Maximum videos to return
        include_deleted : bool
            Whether to include deleted videos

        Returns
        -------
        List[VideoDB]
            Videos needing enrichment
        """
        from chronovista.db.models import Channel as ChannelDB
        from chronovista.db.models import Video as VideoDB

        priority_lower = priority.lower()

        # Build base query with channel join for placeholder channel detection
        query = select(VideoDB).outerjoin(
            ChannelDB, VideoDB.channel_id == ChannelDB.channel_id
        )

        # Handle deleted video exclusion based on priority
        # "all" priority implicitly includes deleted, otherwise respect include_deleted
        if priority_lower == "all":
            # ALL priority includes deleted videos
            pass
        elif not include_deleted:
            query = query.where(VideoDB.deleted_flag == False)  # noqa: E712

        # Build priority filter based on cumulative semantics
        priority_filter = self._build_priority_filter(
            priority_lower, VideoDB, ChannelDB
        )
        if priority_filter is not None:
            query = query.where(priority_filter)

        # Order by upload date (newer first)
        query = query.order_by(VideoDB.upload_date.desc())

        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    def _build_priority_filter(
        self,
        priority: str,
        VideoDB: Any,
        ChannelDB: Any,
    ) -> Any:
        """
        Build SQLAlchemy filter clause for priority tier.

        Priority tiers are CUMULATIVE:
        - HIGH: placeholder title AND placeholder channel
        - MEDIUM: HIGH + any placeholder title
        - LOW: MEDIUM + any partial data
        - ALL: LOW + deleted videos (handled separately)

        Parameters
        ----------
        priority : str
            Priority level (lowercase): "high", "medium", "low", or "all"
        VideoDB : type
            Video database model class
        ChannelDB : type
            Channel database model class

        Returns
        -------
        Any
            SQLAlchemy filter clause, or None for "all" priority
        """
        # HIGH priority filter: placeholder title AND placeholder channel
        high_priority_filter = self._build_high_priority_filter(VideoDB, ChannelDB)

        # MEDIUM priority filter: placeholder title (includes HIGH)
        medium_priority_filter = self._build_medium_priority_filter(VideoDB)

        # LOW priority filter: partial data (includes MEDIUM)
        low_priority_filter = self._build_low_priority_filter(VideoDB)

        if priority == "high":
            return high_priority_filter
        elif priority == "medium":
            # MEDIUM = HIGH + any placeholder title (cumulative)
            return medium_priority_filter
        elif priority == "low":
            # LOW = MEDIUM + partial data (cumulative)
            return or_(medium_priority_filter, low_priority_filter)
        elif priority == "all":
            # ALL = everything (deleted videos handled in main query)
            # Return filter that includes LOW + we handle deleted separately
            return or_(medium_priority_filter, low_priority_filter)
        else:
            # Default to HIGH if invalid priority
            logger.warning(f"Invalid priority '{priority}', defaulting to 'high'")
            return high_priority_filter

    def _build_high_priority_filter(self, VideoDB: Any, ChannelDB: Any) -> Any:
        """
        Build filter for HIGH priority: placeholder title AND placeholder channel.

        Videos are HIGH priority when BOTH conditions are met:
        1. Title starts with "[Placeholder] Video "
        2. Channel title starts with "[Placeholder]" or "[Unknown"

        Parameters
        ----------
        VideoDB : type
            Video database model class
        ChannelDB : type
            Channel database model class

        Returns
        -------
        Any
            SQLAlchemy filter clause
        """
        # Placeholder title condition
        placeholder_title = VideoDB.title.like(f"{VIDEO_PLACEHOLDER_PREFIX}%")

        # Placeholder channel condition (any of the prefixes)
        placeholder_channel_conditions = [
            ChannelDB.title.like(f"{prefix}%")
            for prefix in CHANNEL_PLACEHOLDER_PREFIXES
        ]
        placeholder_channel = or_(*placeholder_channel_conditions)

        # HIGH = placeholder title AND placeholder channel
        return placeholder_title & placeholder_channel

    def _build_medium_priority_filter(self, VideoDB: Any) -> Any:
        """
        Build filter for MEDIUM priority: any placeholder title.

        MEDIUM priority includes all videos where:
        - Title starts with "[Placeholder] Video "

        This is cumulative and includes HIGH priority videos.

        Parameters
        ----------
        VideoDB : type
            Video database model class

        Returns
        -------
        Any
            SQLAlchemy filter clause
        """
        return VideoDB.title.like(f"{VIDEO_PLACEHOLDER_PREFIX}%")

    def _build_low_priority_filter(self, VideoDB: Any) -> Any:
        """
        Build filter for LOW priority additions: partial data.

        LOW priority adds videos with partial/missing data:
        - Missing duration (duration = 0 or NULL)
        - Missing view_count (NULL)
        - Missing description (NULL or empty)

        Note: This does NOT include placeholder titles - those are in MEDIUM.
        The cumulative logic combines this with MEDIUM in _build_priority_filter.

        Parameters
        ----------
        VideoDB : type
            Video database model class

        Returns
        -------
        Any
            SQLAlchemy filter clause
        """
        # Missing duration: 0 or NULL
        missing_duration = or_(
            VideoDB.duration == 0,
            VideoDB.duration.is_(None),
        )

        # Missing view_count: NULL
        missing_view_count = VideoDB.view_count.is_(None)

        # Missing description: NULL or empty string
        missing_description = or_(
            VideoDB.description.is_(None),
            VideoDB.description == "",
        )

        # LOW priority = any of these conditions
        return or_(missing_duration, missing_view_count, missing_description)

    async def get_priority_tier_counts(
        self,
        session: AsyncSession,
    ) -> Dict[str, int]:
        """
        Get count of videos in each priority tier.

        Returns counts for each tier to display before processing.
        Note that tiers are cumulative, so MEDIUM includes HIGH, etc.

        Parameters
        ----------
        session : AsyncSession
            Database session

        Returns
        -------
        Dict[str, int]
            Dictionary with keys: "high", "medium", "low", "all", "deleted"
        """
        from chronovista.db.models import Channel as ChannelDB
        from chronovista.db.models import Video as VideoDB

        # Build base query components
        high_filter = self._build_high_priority_filter(VideoDB, ChannelDB)
        medium_filter = self._build_medium_priority_filter(VideoDB)
        low_filter = self._build_low_priority_filter(VideoDB)

        # Count HIGH priority (placeholder title AND placeholder channel)
        high_query = (
            select(func.count(VideoDB.video_id))
            .outerjoin(ChannelDB, VideoDB.channel_id == ChannelDB.channel_id)
            .where(VideoDB.deleted_flag == False)  # noqa: E712
            .where(high_filter)
        )
        high_result = await session.execute(high_query)
        high_count = high_result.scalar() or 0

        # Count MEDIUM priority (all placeholder titles, includes HIGH)
        medium_query = (
            select(func.count(VideoDB.video_id))
            .where(VideoDB.deleted_flag == False)  # noqa: E712
            .where(medium_filter)
        )
        medium_result = await session.execute(medium_query)
        medium_count = medium_result.scalar() or 0

        # Count LOW priority (MEDIUM + partial data)
        low_query = (
            select(func.count(VideoDB.video_id))
            .where(VideoDB.deleted_flag == False)  # noqa: E712
            .where(or_(medium_filter, low_filter))
        )
        low_result = await session.execute(low_query)
        low_count = low_result.scalar() or 0

        # Count deleted videos
        deleted_query = select(func.count(VideoDB.video_id)).where(
            VideoDB.deleted_flag == True
        )  # noqa: E712
        deleted_result = await session.execute(deleted_query)
        deleted_count = deleted_result.scalar() or 0

        # ALL = LOW + deleted
        all_count = low_count + deleted_count

        return {
            "high": high_count,
            "medium": medium_count,
            "low": low_count,
            "all": all_count,
            "deleted": deleted_count,
        }

    async def _mark_video_deleted(
        self,
        session: AsyncSession,
        video: Any,
        dry_run: bool,
    ) -> None:
        """Mark a video as deleted."""
        if not dry_run:
            video.deleted_flag = True
            logger.info(f"Marked video {video.video_id} as deleted")

    async def _mark_video_deleted_by_id(
        self,
        session: AsyncSession,
        video_id: str,
        dry_run: bool,
    ) -> None:
        """Mark a video as deleted by fetching it fresh from the database."""
        if dry_run:
            return
        video = await self.video_repository.get(session, video_id)
        if video is not None:
            video.deleted_flag = True
            logger.info(f"Marked video {video_id} as deleted")
        else:
            logger.warning(f"Video {video_id} not found for deletion marking")

    def _extract_video_update(self, api_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract video update data from YouTube API response.

        Parameters
        ----------
        api_data : Dict[str, Any]
            YouTube API video resource

        Returns
        -------
        Dict[str, Any]
            Dictionary of fields to update
        """
        snippet = api_data.get("snippet", {})
        content_details = api_data.get("contentDetails", {})
        statistics = api_data.get("statistics", {})

        update_data: Dict[str, Any] = {}

        # Title and description (sanitize to remove NULL bytes)
        if snippet.get("title"):
            update_data["title"] = sanitize_text(snippet["title"])
        if "description" in snippet:
            update_data["description"] = sanitize_text(snippet.get("description", ""))

        # Duration
        duration_str = content_details.get("duration", "")
        if duration_str:
            update_data["duration"] = parse_iso8601_duration(duration_str)

        # Upload date
        published_at = snippet.get("publishedAt")
        if published_at:
            try:
                # Handle ISO 8601 format with Z suffix
                if published_at.endswith("Z"):
                    published_at = published_at[:-1] + "+00:00"
                update_data["upload_date"] = datetime.fromisoformat(published_at)
            except ValueError:
                logger.warning(f"Could not parse upload date: {published_at}")

        # Engagement metrics
        if "viewCount" in statistics:
            update_data["view_count"] = int(statistics["viewCount"])
        if "likeCount" in statistics:
            update_data["like_count"] = int(statistics["likeCount"])
        if "commentCount" in statistics:
            update_data["comment_count"] = int(statistics["commentCount"])

        # Category
        if snippet.get("categoryId"):
            update_data["category_id"] = snippet["categoryId"]

        # Content restrictions
        status = api_data.get("status", {})
        if "madeForKids" in status:
            update_data["made_for_kids"] = status["madeForKids"]
        if "selfDeclaredMadeForKids" in status:
            update_data["self_declared_made_for_kids"] = status[
                "selfDeclaredMadeForKids"
            ]

        # Language
        if snippet.get("defaultLanguage"):
            update_data["default_language"] = snippet["defaultLanguage"]
        if snippet.get("defaultAudioLanguage"):
            update_data["default_audio_language"] = snippet["defaultAudioLanguage"]

        # Region restriction
        if content_details.get("regionRestriction"):
            update_data["region_restriction"] = content_details["regionRestriction"]

        # Content rating
        if content_details.get("contentRating"):
            update_data["content_rating"] = content_details["contentRating"]

        return update_data

    async def _ensure_channel_exists(
        self,
        session: AsyncSession,
        channel_id: str,
        channel_title: str,
    ) -> bool:
        """
        Ensure a channel exists in the database, creating if necessary.

        Parameters
        ----------
        session : AsyncSession
            Database session
        channel_id : str
            YouTube channel ID
        channel_title : str
            Channel title from API

        Returns
        -------
        bool
            True if channel was created, False if it already existed
        """
        from chronovista.models.channel import ChannelCreate

        existing = await self.channel_repository.get(session, channel_id)

        if existing is None:
            # Create new channel
            try:
                channel_create = ChannelCreate(
                    channel_id=channel_id,
                    title=channel_title,
                )
                await self.channel_repository.create(session, channel_create)
                logger.info(f"Created channel: {channel_title} ({channel_id})")
                return True
            except Exception as e:
                logger.error(f"Failed to create channel {channel_id}: {e}")
                return False

        elif is_placeholder_channel_name(existing.title):
            # Update placeholder channel with real name
            try:
                existing.title = channel_title
                logger.info(f"Updated channel name: {channel_title} ({channel_id})")
                return False  # Not a new creation
            except Exception as e:
                logger.error(f"Failed to update channel {channel_id}: {e}")
                return False

        return False  # Channel already exists with real name

    async def get_status(self, session: AsyncSession) -> EnrichmentStatus:
        """
        Get current enrichment status and statistics.

        Performs efficient queries using COUNT(*) with indexed columns to
        gather enrichment statistics. Uses a single query with CASE/WHEN
        expressions to minimize database round-trips (T053).

        This is a read-only operation that does not require lock acquisition.

        Parameters
        ----------
        session : AsyncSession
            Database session for operations.

        Returns
        -------
        EnrichmentStatus
            Pydantic model containing enrichment status information including:
            - Video counts (total, placeholder, deleted, enriched)
            - Channel counts (total, placeholder)
            - Videos missing tags count (T075)
            - Videos missing topics count (T084)
            - Videos missing category count (T090)
            - Enrichment percentage
            - Priority tier estimates with quota costs
        """
        from chronovista.db.models import Channel as ChannelDB
        from chronovista.db.models import Video as VideoDB
        from chronovista.db.models import VideoTag as VideoTagDB
        from chronovista.db.models import VideoTopic as VideoTopicDB

        # Build placeholder detection expressions
        placeholder_video_condition = VideoDB.title.like(f"{VIDEO_PLACEHOLDER_PREFIX}%")

        # Build fully enriched condition:
        # Non-placeholder title, non-deleted, has duration > 0, has view_count
        fully_enriched_condition = (
            ~placeholder_video_condition
            & (VideoDB.deleted_flag == False)  # noqa: E712
            & (VideoDB.duration > 0)
            & (VideoDB.view_count.isnot(None))
        )

        # Single query with CASE/WHEN for multiple video counts (T053 - efficiency)
        video_counts_query = select(
            func.count(VideoDB.video_id).label("total"),
            func.count(case((placeholder_video_condition, 1))).label("placeholder"),
            func.count(case((VideoDB.deleted_flag == True, 1))).label(
                "deleted"
            ),  # noqa: E712
            func.count(case((fully_enriched_condition, 1))).label("enriched"),
        )

        video_result = await session.execute(video_counts_query)
        video_row = video_result.one()

        total_videos = video_row.total or 0
        placeholder_videos = video_row.placeholder or 0
        deleted_videos = video_row.deleted or 0
        fully_enriched_videos = video_row.enriched or 0

        # T075: Count videos missing tags (non-deleted videos with no associated tags)
        # Use a LEFT JOIN and check for NULL in tag table
        videos_with_tags_subquery = select(VideoTagDB.video_id).distinct().subquery()
        missing_tags_query = (
            select(func.count(VideoDB.video_id))
            .outerjoin(
                videos_with_tags_subquery,
                VideoDB.video_id == videos_with_tags_subquery.c.video_id,
            )
            .where(
                (VideoDB.deleted_flag == False)  # noqa: E712
                & (videos_with_tags_subquery.c.video_id.is_(None))
            )
        )
        missing_tags_result = await session.execute(missing_tags_query)
        videos_missing_tags = missing_tags_result.scalar() or 0

        # T084: Count videos missing topics (non-deleted videos with no associated topics)
        # Use a LEFT JOIN and check for NULL in topic table
        videos_with_topics_subquery = (
            select(VideoTopicDB.video_id).distinct().subquery()
        )
        missing_topics_query = (
            select(func.count(VideoDB.video_id))
            .outerjoin(
                videos_with_topics_subquery,
                VideoDB.video_id == videos_with_topics_subquery.c.video_id,
            )
            .where(
                (VideoDB.deleted_flag == False)  # noqa: E712
                & (videos_with_topics_subquery.c.video_id.is_(None))
            )
        )
        missing_topics_result = await session.execute(missing_topics_query)
        videos_missing_topics = missing_topics_result.scalar() or 0

        # T090: Count videos missing category (non-deleted videos with no category_id)
        # This is a simple NULL check on the category_id FK column (FR-048)
        missing_category_query = select(func.count(VideoDB.video_id)).where(
            (VideoDB.deleted_flag == False)  # noqa: E712
            & (VideoDB.category_id.is_(None))
        )
        missing_category_result = await session.execute(missing_category_query)
        videos_missing_category = missing_category_result.scalar() or 0

        # Build placeholder channel detection expression
        placeholder_channel_conditions = [
            ChannelDB.title.like(f"{prefix}%")
            for prefix in CHANNEL_PLACEHOLDER_PREFIXES
        ]
        placeholder_channel_expression = or_(*placeholder_channel_conditions)

        # Single query for channel counts
        channel_counts_query = select(
            func.count(ChannelDB.channel_id).label("total"),
            func.count(case((placeholder_channel_expression, 1))).label("placeholder"),
        )

        channel_result = await session.execute(channel_counts_query)
        channel_row = channel_result.one()

        total_channels = channel_row.total or 0
        placeholder_channels = channel_row.placeholder or 0

        # Calculate enrichment percentage
        if total_videos > 0:
            enrichment_percentage = (fully_enriched_videos / total_videos) * 100
        else:
            enrichment_percentage = 0.0

        # Get priority tier counts using existing method
        tier_counts = await self.get_priority_tier_counts(session)

        # Build the status response
        return EnrichmentStatus(
            total_videos=total_videos,
            placeholder_videos=placeholder_videos,
            deleted_videos=deleted_videos,
            fully_enriched_videos=fully_enriched_videos,
            videos_missing_tags=videos_missing_tags,  # T075: Include in status
            videos_missing_topics=videos_missing_topics,  # T084: Include in status
            videos_missing_category=videos_missing_category,  # T090: Include in status (FR-048)
            total_channels=total_channels,
            placeholder_channels=placeholder_channels,
            enrichment_percentage=round(enrichment_percentage, 1),
            tier_high=PriorityTierEstimate(
                count=tier_counts["high"],
                quota_units=estimate_quota_cost(tier_counts["high"]),
            ),
            tier_medium=PriorityTierEstimate(
                count=tier_counts["medium"],
                quota_units=estimate_quota_cost(tier_counts["medium"]),
            ),
            tier_low=PriorityTierEstimate(
                count=tier_counts["low"],
                quota_units=estimate_quota_cost(tier_counts["low"]),
            ),
            tier_all=PriorityTierEstimate(
                count=tier_counts["all"],
                quota_units=estimate_quota_cost(tier_counts["all"]),
            ),
        )

    async def enrich_tags(
        self, session: AsyncSession, video_id: str, tags: list[str]
    ) -> int:
        """
        Enrich tags for a specific video.

        Implements tag replacement strategy: deletes existing tags for the video
        and inserts new tags from the API response. Tags are stored with their
        original order (tag_order) to preserve the sequence from YouTube.

        This method handles:
        - T068: Tag extraction and storage from API response
        - T069: Extract tags from snippet.tags array
        - T070: Store with video_id, tag text, tag_order
        - T071: Replace old tags on re-enrichment (delete then insert)
        - T072: Handle videos with no tags gracefully (empty list = no-op)
        - T073: Preserve Unicode/special characters exactly as returned by API

        Parameters
        ----------
        session : AsyncSession
            Database session for operations.
        video_id : str
            YouTube video ID to enrich.
        tags : list[str]
            List of tags to associate with the video. Stored exactly as provided,
            preserving Unicode characters, emojis, and special symbols.

        Returns
        -------
        int
            Number of tags created. Returns 0 if tags list is empty or None.
        """
        # T072: Handle videos with no tags gracefully
        if not tags:
            # No tags to process - don't create placeholders
            return 0

        # T071: Replace existing tags (delete old, insert new)
        # T073: Tags are stored exactly as received, preserving Unicode
        # T070: Store with video_id, tag (text), tag_order (position in array)
        # Truncate tags that exceed MAX_TAG_LENGTH (100 chars) to fit DB schema
        truncated_tags = [truncate_tag(tag) for tag in tags]
        tag_orders = list(range(len(truncated_tags)))  # 0, 1, 2, ... preserves order

        created_tags = await self.video_tag_repository.replace_video_tags(
            session, video_id, truncated_tags, tag_orders
        )

        return len(created_tags)

    async def enrich_topics(
        self, session: AsyncSession, video_id: str, topic_urls: list[str] | None
    ) -> int:
        """
        Enrich topics for a specific video.

        Implements topic enrichment by matching YouTube API topic URLs (Wikipedia URLs)
        against pre-seeded topic_categories table. Uses a 5-step matching algorithm
        to find the best match for each topic.

        This method handles:
        - T076: Add enrich_topics() method to EnrichmentService
        - T077: Parse Wikipedia URL to extract topic name
        - T078: 5-step matching algorithm (FR-036)
        - T079: Create video_topics junction records for matched topics
        - T080: Replace old topics on re-enrichment (delete then insert)
        - T081: Log warning and skip unrecognized topics (no auto-create)
        - T082: Handle malformed topic URLs gracefully

        Parameters
        ----------
        session : AsyncSession
            Database session for operations.
        video_id : str
            YouTube video ID to enrich.
        topic_urls : list[str] | None
            List of Wikipedia topic URLs from YouTube API's
            topicDetails.topicCategories field.

        Returns
        -------
        int
            Number of topic associations created. Returns 0 if topic_urls
            is empty, None, or no topics matched.
        """
        # Handle videos with no topics gracefully
        if not topic_urls:
            return 0

        matched_topic_ids: list[str] = []

        for url in topic_urls:
            topic_id = await self._match_topic_from_url(session, url)
            if topic_id:
                matched_topic_ids.append(topic_id)

        # T079: Create video_topics junction records
        # T080: Replace old topics on re-enrichment (delete then insert)
        if matched_topic_ids:
            created_topics = await self.video_topic_repository.replace_video_topics(
                session, video_id, matched_topic_ids
            )
            return len(created_topics)

        return 0

    async def _match_topic_from_url(
        self, session: AsyncSession, url: str
    ) -> str | None:
        """
        Match a Wikipedia URL to a pre-seeded topic category.

        Implements the 5-step matching algorithm per FR-036:
        1. Validate URL format per FR-034
        2. Extract and normalize topic name
        3. Query topic_categories with case-insensitive match on category_name
        4. Fallback to match with underscores replaced by spaces
        5. Fallback to URL-decoded topic name

        Parameters
        ----------
        session : AsyncSession
            Database session for operations.
        url : str
            Wikipedia URL from YouTube API (e.g., https://en.wikipedia.org/wiki/Music)

        Returns
        -------
        str | None
            The matched topic_id (Freebase ID like /m/04rlf) or None if no match.
        """
        from chronovista.db.models import TopicCategory as TopicCategoryDB

        # T077, T082: Parse Wikipedia URL
        parsed = self._parse_wikipedia_url(url)
        if parsed is None:
            return None

        lang, raw_topic_name = parsed

        # T077: Only process en.wikipedia.org URLs; skip non-English with warning
        if lang != "en":
            logger.warning(f"Skipping non-English Wikipedia URL (lang={lang}): {url}")
            return None

        # T078: 5-step matching algorithm
        # Step 1: URL format already validated above

        # Step 2: Extract and normalize topic name
        # URL-decode the topic name (handles %20, %26, etc.)
        decoded_topic_name = unquote(raw_topic_name)

        # Step 3: Exact match on category_name (case-insensitive)
        # Also try with underscores converted to spaces
        topic_with_spaces = decoded_topic_name.replace("_", " ")

        # Query for matching topic
        # Try multiple variations in order of preference
        variations = [
            decoded_topic_name,  # Original (with underscores if present)
            topic_with_spaces,  # Underscores replaced with spaces
            decoded_topic_name.lower(),  # Lowercase original
            topic_with_spaces.lower(),  # Lowercase with spaces
        ]

        for variation in variations:
            # Case-insensitive search using ilike
            # Order by topic_id to prefer Freebase IDs (/m/...) over numeric IDs
            # Freebase IDs start with '/' which sorts before digits
            query = (
                select(TopicCategoryDB.topic_id)
                .where(TopicCategoryDB.category_name.ilike(variation))
                .order_by(TopicCategoryDB.topic_id)
                .limit(1)
            )
            result = await session.execute(query)
            row = result.first()
            if row:
                topic_id = row[0]
                logger.debug(f"Matched topic URL '{url}' to topic_id '{topic_id}'")
                return topic_id

        # T081: Log warning and skip unrecognized topics
        logger.warning(
            f"Unrecognized topic URL, skipping (no matching pre-seeded category): {url}"
        )
        return None

    def _parse_wikipedia_url(self, url: str) -> tuple[str, str] | None:
        """
        Parse a Wikipedia URL to extract language and topic name.

        Implements FR-034: Parse Wikipedia URLs using regex pattern.
        Extract topic name from capture group 2, handle percent-encoded characters.

        Parameters
        ----------
        url : str
            Wikipedia URL to parse (e.g., https://en.wikipedia.org/wiki/Rock_music)

        Returns
        -------
        tuple[str, str] | None
            Tuple of (language_code, topic_name) or None if URL is malformed.
            Language code is the subdomain (e.g., "en" for English).
            Topic name is the raw path component (may contain underscores and encoding).
        """
        # T082: Handle malformed URLs gracefully
        if not url or not isinstance(url, str):
            logger.warning(f"Invalid topic URL (empty or not string): {url}")
            return None

        match = WIKIPEDIA_URL_PATTERN.match(url)
        if not match:
            logger.warning(
                f"Malformed topic URL (doesn't match Wikipedia pattern): {url}"
            )
            return None

        language = match.group(1)
        topic_name = match.group(2)

        return (language, topic_name)

    async def enrich_categories(
        self, session: AsyncSession, video_id: str, category_id: str | None
    ) -> bool:
        """
        Enrich category for a specific video.

        Implements category enrichment by matching the YouTube API-provided
        category ID against the pre-seeded video_categories table. Updates
        the video's category_id field directly (FK relationship, not junction table).

        This method handles:
        - T085: Add enrich_categories() method to EnrichmentService
        - T086: Extract category ID from snippet.categoryId
        - T087: Match category ID against pre-seeded video_categories (FR-046)
        - T088: Log warning and leave null for unrecognized category IDs (FR-047)

        Parameters
        ----------
        session : AsyncSession
            Database session for operations.
        video_id : str
            YouTube video ID to enrich.
        category_id : str | None
            YouTube video category ID to assign. Can be None if video
            doesn't have a category in the API response.

        Returns
        -------
        bool
            True if category was successfully assigned, False otherwise.
            Returns False if:
            - category_id is None or empty
            - category_id doesn't exist in pre-seeded video_categories table
            - video doesn't exist in the database
        """
        # T086: Handle missing category ID gracefully
        if not category_id:
            logger.debug(f"No category ID provided for video {video_id}")
            return False

        # T087: Check if category exists in pre-seeded video_categories table (FR-046)
        category = await self.video_category_repository.get(session, category_id)

        if category is None:
            # T088: Log warning and leave null for unrecognized category IDs (FR-047)
            logger.warning(
                f"Unrecognized category ID '{category_id}' for video {video_id}, "
                f"category_id will remain null"
            )
            return False

        # Get the video to update
        video = await self.video_repository.get(session, video_id)
        if video is None:
            logger.warning(f"Video {video_id} not found for category enrichment")
            return False

        # Update the video's category_id field
        video.category_id = category_id
        logger.debug(
            f"Assigned category '{category.name}' (ID: {category_id}) to video {video_id}"
        )

        return True

    async def enrich_playlists(
        self,
        session: AsyncSession,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> tuple[int, int, int]:
        """
        Enrich playlist metadata from YouTube API.

        Fetches playlist metadata from YouTube Data API and updates local database.
        Playlists not found by the API are marked as deleted/private.

        Parameters
        ----------
        session : AsyncSession
            Database session for operations.
        limit : int | None, optional
            Maximum number of playlists to process (default None = all).
        dry_run : bool, optional
            If True, simulate enrichment without persisting changes (default False).

        Returns
        -------
        tuple[int, int, int]
            Tuple of (playlists_processed, playlists_updated, playlists_deleted)

        Raises
        ------
        RuntimeError
            If playlist_repository is not configured.
        """
        if self.playlist_repository is None:
            raise RuntimeError(
                "Playlist repository not configured. "
                "Pass playlist_repository to EnrichmentService constructor."
            )

        from chronovista.db.models import Playlist as PlaylistDB
        from chronovista.models.enums import PrivacyStatus

        # Query playlists that need enrichment
        # Include playlists that haven't been fully enriched (missing published_at)
        # or have placeholder-like titles
        query = select(PlaylistDB).where(PlaylistDB.deleted_flag == False)  # noqa: E712

        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        playlists_to_enrich = list(result.scalars().all())

        if not playlists_to_enrich:
            logger.info("No playlists found needing enrichment")
            return (0, 0, 0)

        playlist_ids = [p.playlist_id for p in playlists_to_enrich]
        logger.info(f"Found {len(playlist_ids)} playlists to enrich")

        if dry_run:
            logger.info("Dry run mode - no changes will be made")
            return (len(playlist_ids), 0, 0)

        # Fetch playlist details from YouTube API in batches
        api_playlists, not_found_ids = (
            await self.youtube_service.fetch_playlists_batched(
                playlist_ids, batch_size=BATCH_SIZE
            )
        )

        # Create a map of playlist_id -> API data for quick lookup
        api_data_map: Dict[str, Dict[str, Any]] = {
            p.get("id", ""): p for p in api_playlists
        }

        playlists_processed = 0
        playlists_updated = 0
        playlists_deleted = 0

        for playlist in playlists_to_enrich:
            playlist_id = playlist.playlist_id
            playlists_processed += 1

            try:
                if playlist_id in not_found_ids:
                    # Playlist not found = deleted/private
                    playlist.deleted_flag = True
                    playlists_deleted += 1
                    logger.info(f"Marked playlist {playlist_id} as deleted/private")
                    continue

                api_data = api_data_map.get(playlist_id)
                if not api_data:
                    # Shouldn't happen, but handle gracefully
                    logger.warning(f"No API data for playlist {playlist_id}")
                    continue

                # Extract and update playlist metadata
                snippet = api_data.get("snippet", {})
                status = api_data.get("status", {})
                content_details = api_data.get("contentDetails", {})

                # Update title
                if snippet.get("title"):
                    playlist.title = snippet["title"]

                # Update description
                if "description" in snippet:
                    playlist.description = snippet.get("description", "")

                # Update published_at
                published_at = snippet.get("publishedAt")
                if published_at:
                    try:
                        if published_at.endswith("Z"):
                            published_at = published_at[:-1] + "+00:00"
                        playlist.published_at = datetime.fromisoformat(published_at)
                    except ValueError:
                        logger.warning(f"Could not parse published_at: {published_at}")

                # Update privacy status
                privacy = status.get("privacyStatus", "").lower()
                if privacy:
                    try:
                        playlist.privacy_status = PrivacyStatus(privacy).value
                    except ValueError:
                        logger.warning(f"Unknown privacy status: {privacy}")

                # Update video count
                item_count = content_details.get("itemCount")
                if item_count is not None:
                    playlist.video_count = int(item_count)

                # Update default language
                default_language = snippet.get("defaultLanguage")
                if default_language:
                    playlist.default_language = default_language

                playlists_updated += 1
                logger.debug(f"Updated playlist {playlist_id}: {playlist.title}")

            except Exception as e:
                logger.error(f"Error enriching playlist {playlist_id}: {e}")

            # Commit after each batch
            if playlists_processed % BATCH_SIZE == 0:
                try:
                    await session.commit()
                    logger.info(
                        f"Committed playlist batch {playlists_processed // BATCH_SIZE}"
                    )
                except Exception as e:
                    logger.error(f"Error committing playlist batch: {e}")
                    await session.rollback()

        # Final commit for remaining playlists
        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Error in final playlist commit: {e}")
            await session.rollback()

        logger.info(
            f"Playlist enrichment complete: {playlists_processed} processed, "
            f"{playlists_updated} updated, {playlists_deleted} deleted"
        )

        return (playlists_processed, playlists_updated, playlists_deleted)
