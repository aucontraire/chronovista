"""
Recovery orchestrator for deleted YouTube videos and channels.

Coordinates CDX API queries, page parsing, database updates, and tag persistence
to recover metadata for unavailable YouTube videos and channels using Wayback
Machine snapshots.

Functions
---------
recover_video
    Main orchestration function for recovering a single video's metadata.
    Includes best-effort auto-channel recovery when the video's channel
    is unavailable.
recover_channel
    Standalone orchestration function for recovering a single channel's metadata.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.exceptions import CDXError
from chronovista.models.channel import ChannelCreate, ChannelUpdate
from chronovista.models.enums import AvailabilityStatus
from chronovista.models.video import VideoUpdate
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_tag_repository import VideoTagRepository
from chronovista.services.recovery.cdx_client import CDXClient, RateLimiter
from chronovista.services.recovery.models import (
    ChannelRecoveryResult,
    RecoveredChannelData,
    RecoveredVideoData,
    RecoveryResult,
)
from chronovista.services.recovery.page_parser import PageParser

logger = logging.getLogger(__name__)

# Recovery configuration constants
_MAX_SNAPSHOTS_TO_TRY = 20
_RECOVERY_TIMEOUT_SECONDS = 600.0

# Immutable fields that are only filled when NULL (never overwrite existing values)
_IMMUTABLE_FIELDS = frozenset(["channel_id", "category_id"])

# Mutable fields that can be overwritten if snapshot is newer than existing recovery_source
_MUTABLE_FIELDS = frozenset(
    ["title", "description", "upload_date", "view_count", "like_count", "channel_name_hint", "thumbnail_url"]
)

# Channel mutable fields (channels have NO immutable fields — all are mutable overwrite-if-newer)
_CHANNEL_MUTABLE_FIELDS = frozenset(
    ["title", "description", "subscriber_count", "video_count", "thumbnail_url", "country", "default_language"]
)


async def recover_video(
    session: AsyncSession,
    video_id: str,
    cdx_client: CDXClient,
    page_parser: PageParser,
    rate_limiter: RateLimiter,
    dry_run: bool = False,
    from_year: int | None = None,
    to_year: int | None = None,
) -> RecoveryResult:
    """
    Recover metadata for a deleted YouTube video using Wayback Machine snapshots.

    This function coordinates the full recovery process:
    1. Fetch video from database and check eligibility (availability_status != AVAILABLE)
    2. Query CDX API for archived snapshots
    3. Iterate snapshots newest-first (max 20, 600s timeout)
    4. Extract metadata via PageParser
    5. Apply three-tier overwrite policy (immutable, mutable, NULL protection)
    6. Update database and persist recovered tags
    7. Return RecoveryResult with success/failure status

    Parameters
    ----------
    session : AsyncSession
        Database session for querying and updating video records.
    video_id : str
        YouTube video ID to recover (e.g., "dQw4w9WgXcQ").
    cdx_client : CDXClient
        CDX API client for fetching Wayback Machine snapshots.
    page_parser : PageParser
        Page parser for extracting metadata from archived pages.
    rate_limiter : RateLimiter
        Rate limiter for throttling page fetch requests.
    dry_run : bool, optional
        If True, skips page fetching and DB writes but queries CDX (default: False).
    from_year : int | None, optional
        Only search Wayback snapshots from this year onward (default: None).
    to_year : int | None, optional
        Only search Wayback snapshots up to this year (default: None).

    Returns
    -------
    RecoveryResult
        Result object containing success status, fields recovered/skipped,
        snapshot information, failure reason (if applicable), and duration.

    Examples
    --------
    >>> from pathlib import Path
    >>> from chronovista.services.recovery.cdx_client import CDXClient, RateLimiter
    >>> from chronovista.services.recovery.page_parser import PageParser
    >>> cdx_client = CDXClient(cache_dir=Path("/tmp/cdx_cache"))
    >>> rate_limiter = RateLimiter(rate=40.0)
    >>> page_parser = PageParser(rate_limiter=rate_limiter)
    >>> result = await recover_video(
    ...     session=session,
    ...     video_id="dQw4w9WgXcQ",
    ...     cdx_client=cdx_client,
    ...     page_parser=page_parser,
    ...     rate_limiter=rate_limiter,
    ...     dry_run=False,
    ... )
    >>> if result.success:
    ...     print(f"Recovered {len(result.fields_recovered)} fields")
    """
    start_time = datetime.now(timezone.utc)

    # Initialize repositories
    video_repo = VideoRepository()
    tag_repo = VideoTagRepository()
    channel_repo = ChannelRepository()

    try:
        # Fetch video from database
        video = await video_repo.get_by_video_id(session, video_id)

        # Check eligibility: video must exist
        if video is None:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return RecoveryResult(
                video_id=video_id,
                success=False,
                failure_reason="video_not_found",
                duration_seconds=duration,
            )

        # Check eligibility: video must not be AVAILABLE
        if video.availability_status == AvailabilityStatus.AVAILABLE.value:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return RecoveryResult(
                video_id=video_id,
                success=False,
                failure_reason="video_available",
                duration_seconds=duration,
            )

        # Query CDX API for snapshots
        try:
            snapshots = await asyncio.wait_for(
                cdx_client.fetch_snapshots(
                    video_id, from_year=from_year, to_year=to_year
                ),
                timeout=_RECOVERY_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return RecoveryResult(
                video_id=video_id,
                success=False,
                failure_reason="cdx_query_timeout",
                duration_seconds=duration,
            )
        except CDXError as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.warning("CDX error for video %s: %s", video_id, e.message)
            return RecoveryResult(
                video_id=video_id,
                success=False,
                failure_reason="cdx_connection_error",
                duration_seconds=duration,
            )

        snapshots_available = len(snapshots)

        # No snapshots available
        if snapshots_available == 0:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return RecoveryResult(
                video_id=video_id,
                success=False,
                failure_reason="no_snapshots_found",
                snapshots_available=0,
                snapshots_tried=0,
                duration_seconds=duration,
            )

        # Iterate snapshots newest-first (already sorted by CDXClient)
        snapshots_tried = 0
        recovered_data: RecoveredVideoData | None = None

        for snapshot in snapshots[: _MAX_SNAPSHOTS_TO_TRY]:
            snapshots_tried += 1

            # Skip page fetching in dry-run mode
            if dry_run:
                recovered_data = RecoveredVideoData(
                    snapshot_timestamp=snapshot.timestamp
                )
                break

            # Extract metadata from snapshot
            try:
                extracted_data = await page_parser.extract_metadata(snapshot)
            except asyncio.TimeoutError:
                logger.warning(
                    "Timeout extracting metadata from snapshot %s for video %s",
                    snapshot.timestamp,
                    video_id,
                )
                continue
            except Exception as e:
                logger.warning(
                    "Error extracting metadata from snapshot %s for video %s: %s",
                    snapshot.timestamp,
                    video_id,
                    e,
                )
                continue

            # Check if we got usable data
            if extracted_data is None or not extracted_data.has_data:
                # Removal notice or no data - try next snapshot
                continue

            # Found usable data - stop iteration
            recovered_data = extracted_data
            break

        # No usable data found after trying all snapshots
        if recovered_data is None or (not dry_run and not recovered_data.has_data):
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return RecoveryResult(
                video_id=video_id,
                success=False,
                failure_reason="all_snapshots_failed",
                snapshots_available=snapshots_available,
                snapshots_tried=snapshots_tried,
                duration_seconds=duration,
            )

        # Build update dictionary with overwrite policy
        update_dict, fields_recovered, fields_skipped = _build_video_update(
            video, recovered_data
        )

        # Add recovery metadata (always set on success)
        update_dict["recovered_at"] = datetime.now(timezone.utc)
        update_dict["recovery_source"] = recovered_data.recovery_source

        # Skip database write in dry-run mode
        if not dry_run:
            # Ensure channel exists before setting channel_id (FK constraint)
            if "channel_id" in update_dict:
                channel_exists = await channel_repo.exists(
                    session, update_dict["channel_id"]
                )
                if not channel_exists:
                    stub_title = (
                        recovered_data.channel_name_hint
                        or update_dict["channel_id"]
                    )
                    try:
                        stub_channel = ChannelCreate(
                            channel_id=update_dict["channel_id"],
                            title=stub_title,
                            availability_status=AvailabilityStatus.UNAVAILABLE,
                        )
                        await channel_repo.create(session, obj_in=stub_channel)
                        logger.info(
                            "Created stub channel %s (%s) for video %s",
                            update_dict["channel_id"],
                            stub_title,
                            video_id,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to create stub channel %s for video %s: %s",
                            update_dict["channel_id"],
                            video_id,
                            e,
                        )
                        # Remove channel_id from update to avoid FK violation
                        del update_dict["channel_id"]
                        if "channel_id" in fields_recovered:
                            fields_recovered.remove("channel_id")
                            fields_skipped.append("channel_id")

            # Update video in database
            video_update = VideoUpdate(**update_dict)
            await video_repo.update(session, db_obj=video, obj_in=video_update)

            # Persist tags if any were recovered
            if recovered_data.tags:
                try:
                    await tag_repo.bulk_create_video_tags(
                        session=session,
                        video_id=video_id,
                        tags=recovered_data.tags,
                        tag_orders=None,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to persist tags for video %s: %s", video_id, e
                    )
                    # Tag errors do not fail recovery

            # Commit changes
            await session.commit()

        # Auto-channel recovery (best-effort, never blocks video recovery)
        channel_recovery_candidates: list[str] = []
        channel_recovered = False
        channel_fields_recovered: list[str] = []
        channel_fields_skipped: list[str] = []
        channel_failure_reason: str | None = None

        if recovered_data.channel_id:
            # Check if this channel exists and is unavailable
            channel = await channel_repo.get(session, recovered_data.channel_id)
            if channel is not None and channel.availability_status != AvailabilityStatus.AVAILABLE.value:
                channel_recovery_candidates.append(recovered_data.channel_id)

                # Attempt auto-channel recovery with remaining time budget
                try:
                    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                    remaining_timeout = max(
                        _RECOVERY_TIMEOUT_SECONDS - elapsed, 30.0
                    )
                    channel_result = await recover_channel(
                        session=session,
                        channel_id=recovered_data.channel_id,
                        cdx_client=cdx_client,
                        page_parser=page_parser,
                        rate_limiter=rate_limiter,
                        from_year=from_year,
                        to_year=to_year,
                        timeout_seconds=remaining_timeout,
                    )
                    if channel_result.success:
                        channel_recovered = True
                        channel_fields_recovered = channel_result.fields_recovered
                        channel_fields_skipped = channel_result.fields_skipped
                    else:
                        channel_failure_reason = channel_result.failure_reason
                except Exception as e:
                    logger.warning(
                        "Auto-channel recovery failed for channel %s "
                        "(video %s): %s",
                        recovered_data.channel_id,
                        video_id,
                        e,
                    )
                    channel_failure_reason = f"exception: {e}"

        # Build success result
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        return RecoveryResult(
            video_id=video_id,
            success=True,
            snapshot_used=recovered_data.snapshot_timestamp,
            fields_recovered=fields_recovered,
            fields_skipped=fields_skipped,
            snapshots_available=snapshots_available,
            snapshots_tried=snapshots_tried,
            duration_seconds=duration,
            channel_recovery_candidates=channel_recovery_candidates,
            channel_recovered=channel_recovered,
            channel_fields_recovered=channel_fields_recovered,
            channel_fields_skipped=channel_fields_skipped,
            channel_failure_reason=channel_failure_reason,
        )

    except Exception as e:
        # Unexpected error during recovery
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.error("Unexpected error recovering video %s: %s", video_id, e)
        return RecoveryResult(
            video_id=video_id,
            success=False,
            failure_reason="unexpected_error",
            duration_seconds=duration,
        )


def _build_video_update(
    existing_video: Any, recovered_data: RecoveredVideoData
) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Build video update dictionary with three-tier overwrite policy.

    Applies the following policy:
    1. **Immutable fields** (upload_date, channel_id, category_id):
       Fill-if-NULL only. Never overwrite existing values.
    2. **Mutable fields** (title, description, view_count, like_count, channel_name_hint):
       - Fill-if-NULL always
       - Overwrite existing values only if incoming snapshot is newer than
         existing recovery_source
    3. **NULL protection**: Never blank existing values with None/NULL from
       recovered data.

    Parameters
    ----------
    existing_video : Any
        SQLAlchemy Video model instance from database.
    recovered_data : RecoveredVideoData
        Metadata extracted from Wayback Machine snapshot.

    Returns
    -------
    tuple[dict[str, Any], list[str], list[str]]
        A 3-tuple containing:
        - update_dict: Dictionary of field updates to apply
        - fields_recovered: List of field names successfully recovered
        - fields_skipped: List of field names that were skipped
    """
    update_dict: dict[str, Any] = {}
    fields_recovered: list[str] = []
    fields_skipped: list[str] = []

    # Extract existing recovery_source timestamp (if any)
    existing_recovery_timestamp: str | None = None
    if existing_video.recovery_source:
        # Format: "wayback:20220106075526"
        parts = existing_video.recovery_source.split(":")
        if len(parts) == 2 and parts[0] == "wayback":
            existing_recovery_timestamp = parts[1]

    # Determine if incoming snapshot is newer than existing recovery
    incoming_is_newer = False
    if existing_recovery_timestamp is None:
        # No existing recovery - incoming is considered "newer"
        incoming_is_newer = True
    elif recovered_data.snapshot_timestamp >= existing_recovery_timestamp:
        # Incoming snapshot has same or later timestamp
        incoming_is_newer = True

    # Map RecoveredVideoData fields to Video model fields
    field_mapping = {
        "title": "title",
        "description": "description",
        "channel_id": "channel_id",
        "channel_name_hint": "channel_name_hint",
        "view_count": "view_count",
        "like_count": "like_count",
        "upload_date": "upload_date",
        "thumbnail_url": "thumbnail_url",
        "category_id": "category_id",
    }

    for recovered_field, db_field in field_mapping.items():
        recovered_value = getattr(recovered_data, recovered_field, None)
        existing_value = getattr(existing_video, db_field, None)

        # NULL protection: never blank existing values
        if recovered_value is None:
            if existing_value is not None:
                # Skip: incoming is NULL, existing has value
                fields_skipped.append(db_field)
            # If both are NULL, do nothing (not recovered, not skipped)
            continue

        # Immutable fields: fill-if-NULL only
        if db_field in _IMMUTABLE_FIELDS:
            if existing_value is None:
                # Fill NULL immutable field
                update_dict[db_field] = recovered_value
                fields_recovered.append(db_field)
            else:
                # Skip: immutable field already has value
                fields_skipped.append(db_field)
            continue

        # Mutable fields: fill-if-NULL always, overwrite if newer
        if db_field in _MUTABLE_FIELDS:
            if existing_value is None:
                # Fill NULL mutable field
                update_dict[db_field] = recovered_value
                fields_recovered.append(db_field)
            elif incoming_is_newer:
                # Overwrite existing value with newer snapshot data
                update_dict[db_field] = recovered_value
                fields_recovered.append(db_field)
            else:
                # Skip: existing value is from newer or same snapshot
                fields_skipped.append(db_field)
            continue

    return update_dict, fields_recovered, fields_skipped


def _build_channel_update(
    existing_channel: Any, recovered_data: RecoveredChannelData
) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Build channel update dictionary with two-tier overwrite policy.

    Applies the following policy for channels (no immutable fields):
    1. **Mutable fields** (title, description, subscriber_count, video_count,
       thumbnail_url, country, default_language):
       - Fill-if-NULL always
       - Overwrite existing values only if incoming snapshot is newer than
         existing recovery_source
    2. **NULL protection**: Never blank existing values with None/NULL from
       recovered data.

    Parameters
    ----------
    existing_channel : Any
        SQLAlchemy Channel model instance from database.
    recovered_data : RecoveredChannelData
        Metadata extracted from Wayback Machine channel snapshot.

    Returns
    -------
    tuple[dict[str, Any], list[str], list[str]]
        A 3-tuple containing:
        - update_dict: Dictionary of field updates to apply
        - fields_recovered: List of field names successfully recovered
        - fields_skipped: List of field names that were skipped
    """
    update_dict: dict[str, Any] = {}
    fields_recovered: list[str] = []
    fields_skipped: list[str] = []

    # Extract existing recovery_source timestamp (if any)
    existing_recovery_timestamp: str | None = None
    if existing_channel.recovery_source:
        # Format: "wayback:20220106075526"
        parts = existing_channel.recovery_source.split(":")
        if len(parts) == 2 and parts[0] == "wayback":
            existing_recovery_timestamp = parts[1]

    # Determine if incoming snapshot is newer than existing recovery
    incoming_is_newer = False
    if existing_recovery_timestamp is None:
        # No existing recovery - incoming is considered "newer"
        incoming_is_newer = True
    elif recovered_data.snapshot_timestamp >= existing_recovery_timestamp:
        # Incoming snapshot has same or later timestamp
        incoming_is_newer = True

    # Map RecoveredChannelData fields to Channel model fields
    field_mapping = {
        "title": "title",
        "description": "description",
        "subscriber_count": "subscriber_count",
        "video_count": "video_count",
        "thumbnail_url": "thumbnail_url",
        "country": "country",
        "default_language": "default_language",
    }

    for recovered_field, db_field in field_mapping.items():
        recovered_value = getattr(recovered_data, recovered_field, None)
        existing_value = getattr(existing_channel, db_field, None)

        # NULL protection: never blank existing values
        if recovered_value is None:
            if existing_value is not None:
                # Skip: incoming is NULL, existing has value
                fields_skipped.append(db_field)
            # If both are NULL, do nothing (not recovered, not skipped)
            continue

        # All channel fields are mutable: fill-if-NULL always, overwrite if newer
        if db_field in _CHANNEL_MUTABLE_FIELDS:
            if existing_value is None:
                # Fill NULL mutable field
                update_dict[db_field] = recovered_value
                fields_recovered.append(db_field)
            elif incoming_is_newer:
                # Overwrite existing value with newer snapshot data
                update_dict[db_field] = recovered_value
                fields_recovered.append(db_field)
            else:
                # Skip: existing value is from newer or same snapshot
                fields_skipped.append(db_field)
            continue

    return update_dict, fields_recovered, fields_skipped


async def recover_channel(
    session: AsyncSession,
    channel_id: str,
    cdx_client: CDXClient,
    page_parser: PageParser,
    rate_limiter: RateLimiter,
    from_year: int | None = None,
    to_year: int | None = None,
    timeout_seconds: float = _RECOVERY_TIMEOUT_SECONDS,
) -> ChannelRecoveryResult:
    """
    Recover metadata for an unavailable YouTube channel using Wayback Machine snapshots.

    This function coordinates the full channel recovery process:
    1. Fetch channel from database and check eligibility (availability_status != AVAILABLE)
    2. Query CDX API for archived channel page snapshots
    3. Iterate snapshots newest-first (max 20, configurable timeout)
    4. Extract metadata via PageParser.extract_channel_metadata()
    5. Apply two-tier overwrite policy (mutable overwrite-if-newer, NULL protection)
    6. Update database with recovered metadata
    7. Return ChannelRecoveryResult with success/failure status

    Parameters
    ----------
    session : AsyncSession
        Database session for querying and updating channel records.
    channel_id : str
        YouTube channel ID to recover (e.g., "UCuAXFkgsw1L7xaCfnd5JJOw").
    cdx_client : CDXClient
        CDX API client for fetching Wayback Machine snapshots.
    page_parser : PageParser
        Page parser for extracting channel metadata from archived pages.
    rate_limiter : RateLimiter
        Rate limiter for throttling page fetch requests.
    from_year : int | None, optional
        Only search Wayback snapshots from this year onward (default: None).
    to_year : int | None, optional
        Only search Wayback snapshots up to this year (default: None).
    timeout_seconds : float, optional
        Maximum wall-clock seconds for the entire recovery (default: 600.0).
        When called from recover_video(), the remaining time budget is passed.

    Returns
    -------
    ChannelRecoveryResult
        Result object containing success status, fields recovered/skipped,
        snapshot information, failure reason (if applicable), and duration.

    Examples
    --------
    >>> from pathlib import Path
    >>> from chronovista.services.recovery.cdx_client import CDXClient, RateLimiter
    >>> from chronovista.services.recovery.page_parser import PageParser
    >>> cdx_client = CDXClient(cache_dir=Path("/tmp/cdx_cache"))
    >>> rate_limiter = RateLimiter(rate=40.0)
    >>> page_parser = PageParser(rate_limiter=rate_limiter)
    >>> result = await recover_channel(
    ...     session=session,
    ...     channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
    ...     cdx_client=cdx_client,
    ...     page_parser=page_parser,
    ...     rate_limiter=rate_limiter,
    ... )
    >>> if result.success:
    ...     print(f"Recovered {len(result.fields_recovered)} fields")
    """
    start_time = datetime.now(timezone.utc)

    # Initialize repository
    channel_repo = ChannelRepository()

    try:
        # Fetch channel from database
        channel = await channel_repo.get(session, channel_id)

        # Check eligibility: channel must exist
        if channel is None:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return ChannelRecoveryResult(
                channel_id=channel_id,
                success=False,
                failure_reason="channel_not_found",
                duration_seconds=duration,
            )

        # Check eligibility: channel must not be AVAILABLE
        if channel.availability_status == AvailabilityStatus.AVAILABLE.value:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return ChannelRecoveryResult(
                channel_id=channel_id,
                success=False,
                failure_reason="channel_available",
                duration_seconds=duration,
            )

        # Query CDX API for channel snapshots
        try:
            snapshots = await asyncio.wait_for(
                cdx_client.fetch_channel_snapshots(
                    channel_id, from_year=from_year, to_year=to_year
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return ChannelRecoveryResult(
                channel_id=channel_id,
                success=False,
                failure_reason="cdx_query_timeout",
                duration_seconds=duration,
            )
        except CDXError as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.warning("CDX error for channel %s: %s", channel_id, e.message)
            return ChannelRecoveryResult(
                channel_id=channel_id,
                success=False,
                failure_reason="cdx_connection_error",
                duration_seconds=duration,
            )

        snapshots_available = len(snapshots)

        # No snapshots available
        if snapshots_available == 0:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return ChannelRecoveryResult(
                channel_id=channel_id,
                success=False,
                failure_reason="no_snapshots_found",
                snapshots_available=0,
                snapshots_tried=0,
                duration_seconds=duration,
            )

        # Iterate snapshots newest-first (already sorted by CDXClient)
        snapshots_tried = 0
        recovered_data: RecoveredChannelData | None = None

        for snapshot in snapshots[: _MAX_SNAPSHOTS_TO_TRY]:
            snapshots_tried += 1

            # Check remaining time budget
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed >= timeout_seconds:
                logger.warning(
                    "Channel recovery timeout for %s after %d snapshots (%.1fs)",
                    channel_id,
                    snapshots_tried,
                    elapsed,
                )
                break

            # Extract metadata from snapshot
            try:
                extracted_data = await page_parser.extract_channel_metadata(
                    snapshot, channel_id
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Timeout extracting channel metadata from snapshot %s for channel %s",
                    snapshot.timestamp,
                    channel_id,
                )
                continue
            except Exception as e:
                logger.warning(
                    "Error extracting channel metadata from snapshot %s for channel %s: %s",
                    snapshot.timestamp,
                    channel_id,
                    e,
                )
                continue

            # Check if we got usable data
            if extracted_data is None or not extracted_data.has_data:
                continue

            # Found usable data - stop iteration
            recovered_data = extracted_data
            break

        # No usable data found after trying all snapshots
        if recovered_data is None:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return ChannelRecoveryResult(
                channel_id=channel_id,
                success=False,
                failure_reason="all_snapshots_failed",
                snapshots_available=snapshots_available,
                snapshots_tried=snapshots_tried,
                duration_seconds=duration,
            )

        # Build update dictionary with overwrite policy
        update_dict, fields_recovered, fields_skipped = _build_channel_update(
            channel, recovered_data
        )

        # Add recovery metadata (always set on success)
        update_dict["recovered_at"] = datetime.now(timezone.utc)
        update_dict["recovery_source"] = recovered_data.recovery_source

        # Update channel in database
        channel_update = ChannelUpdate(**update_dict)
        await channel_repo.update(session, db_obj=channel, obj_in=channel_update)

        # Commit changes
        await session.commit()

        # Build success result
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        return ChannelRecoveryResult(
            channel_id=channel_id,
            success=True,
            snapshot_used=recovered_data.snapshot_timestamp,
            fields_recovered=fields_recovered,
            fields_skipped=fields_skipped,
            snapshots_available=snapshots_available,
            snapshots_tried=snapshots_tried,
            duration_seconds=duration,
        )

    except Exception as e:
        # Unexpected error during recovery
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.error("Unexpected error recovering channel %s: %s", channel_id, e)
        return ChannelRecoveryResult(
            channel_id=channel_id,
            success=False,
            failure_reason="unexpected_error",
            duration_seconds=duration,
        )
