"""
Takeout Recovery Service

Service for recovering metadata from historical Google Takeout exports.
Handles the gap-fill logic to update placeholder videos and channels
with real metadata from historical takeout data.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.channel import ChannelCreate, ChannelUpdate
from ..models.takeout import (
    ChannelRecoveryAction,
    HistoricalTakeout,
    RecoveredChannelMetadata,
    RecoveredVideoMetadata,
    RecoveryOptions,
    RecoveryResult,
    VideoRecoveryAction,
    is_placeholder_channel_name,
    is_placeholder_video_title,
)
from ..models.video import VideoUpdate
from ..repositories.channel_repository import ChannelRepository
from ..repositories.video_repository import VideoRepository
from .takeout_service import TakeoutService

logger = logging.getLogger(__name__)


class TakeoutRecoveryService:
    """
    Service for recovering video and channel metadata from historical takeouts.

    This service implements the gap-fill logic: it only updates videos
    and channels that currently have placeholder data, preserving any
    existing non-placeholder metadata.
    """

    def __init__(
        self,
        video_repository: Optional[VideoRepository] = None,
        channel_repository: Optional[ChannelRepository] = None,
    ) -> None:
        """
        Initialize the recovery service.

        Parameters
        ----------
        video_repository : Optional[VideoRepository]
            Repository for video operations (default: creates new instance)
        channel_repository : Optional[ChannelRepository]
            Repository for channel operations (default: creates new instance)
        """
        self.video_repository = video_repository or VideoRepository()
        self.channel_repository = channel_repository or ChannelRepository()

    async def recover_from_historical_takeouts(
        self,
        session: AsyncSession,
        takeout_base_path: Path,
        options: Optional[RecoveryOptions] = None,
    ) -> RecoveryResult:
        """
        Recover metadata from historical takeout directories.

        This is the main entry point for the recovery process.

        Parameters
        ----------
        session : AsyncSession
            Database session
        takeout_base_path : Path
            Base directory containing historical takeout directories
        options : Optional[RecoveryOptions]
            Recovery options (dry_run, verbose, etc.)

        Returns
        -------
        RecoveryResult
            Result of the recovery operation
        """
        options = options or RecoveryOptions()
        result = RecoveryResult(dry_run=options.dry_run)

        logger.info(
            f"Starting recovery from historical takeouts in {takeout_base_path}"
        )

        # Discover historical takeouts
        historical_takeouts = TakeoutService.discover_historical_takeouts(
            takeout_base_path, sort_oldest_first=options.process_oldest_first
        )

        if not historical_takeouts:
            logger.warning("No historical takeouts found")
            result.add_error(f"No historical takeouts found in {takeout_base_path}")
            result.mark_complete()
            return result

        result.takeouts_scanned = len(historical_takeouts)
        dates = [t.export_date for t in historical_takeouts]
        result.oldest_takeout_date = min(dates)
        result.newest_takeout_date = max(dates)

        logger.info(
            f"Found {len(historical_takeouts)} historical takeouts "
            f"({result.oldest_takeout_date.date()} to {result.newest_takeout_date.date()})"
        )

        # Build metadata maps from historical takeouts
        # We need a TakeoutService instance to parse the data
        # Use the first takeout's path parent to initialize (it just needs a valid path)
        first_takeout_parent = historical_takeouts[0].path.parent
        if not (first_takeout_parent / "YouTube and YouTube Music").exists():
            # The path might already be the YouTube folder
            first_takeout_parent = historical_takeouts[0].path.parent.parent

        try:
            takeout_service = TakeoutService(first_takeout_parent)
        except Exception:
            # Create a minimal instance for historical parsing
            takeout_service = object.__new__(TakeoutService)
            takeout_service.takeout_path = first_takeout_parent
            takeout_service.youtube_path = historical_takeouts[0].path

        video_metadata, channel_metadata = await takeout_service.build_recovery_metadata_map(
            historical_takeouts, process_oldest_first=options.process_oldest_first
        )

        logger.info(
            f"Built recovery map: {len(video_metadata)} videos, {len(channel_metadata)} channels"
        )

        # Find placeholder videos in database that can be recovered
        await self._recover_videos(
            session, video_metadata, result, options
        )

        # Create/update channels from historical data
        if options.update_channels:
            await self._recover_channels(
                session, channel_metadata, result, options
            )

        result.mark_complete()

        logger.info(
            f"Recovery complete: {result.videos_recovered} videos recovered, "
            f"{result.channels_created} channels created, "
            f"{result.videos_still_missing} still missing"
        )

        return result

    async def _recover_videos(
        self,
        session: AsyncSession,
        video_metadata: Dict[str, RecoveredVideoMetadata],
        result: RecoveryResult,
        options: RecoveryOptions,
    ) -> None:
        """
        Recover placeholder videos from historical metadata.

        This method handles two recovery scenarios:
        1. Videos with placeholder titles - updates title (and channel_id if NULL)
        2. Videos with NULL channel_id but real titles - updates channel_id only

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_metadata : Dict[str, RecoveredVideoMetadata]
            Map of video_id to recovered metadata
        result : RecoveryResult
            Result object to update
        options : RecoveryOptions
            Recovery options
        """
        logger.info("Scanning database for recoverable videos...")

        # Get all videos from database
        # Process in batches to handle large datasets
        skip = 0
        videos_checked = 0
        placeholder_count = 0
        null_channel_count = 0

        while True:
            videos = await self.video_repository.get_multi(
                session, skip=skip, limit=options.batch_size
            )

            if not videos:
                break

            for video in videos:
                videos_checked += 1
                is_placeholder_title = is_placeholder_video_title(video.title)
                has_null_channel = video.channel_id is None

                if is_placeholder_title:
                    placeholder_count += 1

                if has_null_channel:
                    null_channel_count += 1

                # Check if we have recovery metadata for this video
                if video.video_id not in video_metadata:
                    # No recovery data available
                    if is_placeholder_title:
                        result.videos_not_recovered.append(video.video_id)
                        result.videos_still_missing += 1
                    continue

                recovered = video_metadata[video.video_id]

                # Determine what needs to be updated
                needs_title_update = is_placeholder_title and recovered.title
                needs_channel_update = (
                    has_null_channel
                    and recovered.channel_id
                )

                if not needs_title_update and not needs_channel_update:
                    # Nothing to recover for this video
                    continue

                # Determine action type
                if needs_title_update and needs_channel_update:
                    action_type = "both"
                elif needs_title_update:
                    action_type = "update_title"
                else:
                    action_type = "update_channel"

                # Create recovery action
                action = VideoRecoveryAction(
                    video_id=video.video_id,
                    old_title=video.title,
                    new_title=recovered.title if needs_title_update else video.title,
                    old_channel_id=video.channel_id,
                    new_channel_id=recovered.channel_id if needs_channel_update else video.channel_id,
                    channel_name=recovered.channel_name,
                    source_date=recovered.source_date,
                    action_type=action_type,
                )

                result.video_actions.append(action)

                if not options.dry_run:
                    # Build update data based on what's needed
                    update_fields = {}

                    if needs_title_update:
                        update_fields["title"] = recovered.title

                    if needs_channel_update:
                        # Verify the channel exists before updating FK
                        channel = await self.channel_repository.get(
                            session, recovered.channel_id
                        )
                        if channel:
                            update_fields["channel_id"] = recovered.channel_id
                            # Clear channel_name_hint since we now have real channel_id
                            update_fields["channel_name_hint"] = None
                            logger.debug(
                                f"Recovering channel_id for video {video.video_id}: "
                                f"NULL -> '{recovered.channel_id}'"
                            )
                        else:
                            logger.debug(
                                f"Cannot update channel_id for video {video.video_id}: "
                                f"channel {recovered.channel_id} not found in database"
                            )

                    if update_fields:
                        update_data = VideoUpdate(**update_fields)
                        await self.video_repository.update(
                            session, db_obj=video, obj_in=update_data
                        )

                        if needs_title_update:
                            logger.debug(
                                f"Recovered video {video.video_id}: "
                                f"'{video.title}' -> '{recovered.title}'"
                            )

                result.videos_recovered += 1

            skip += options.batch_size

            if options.verbose:
                logger.info(
                    f"Processed {videos_checked} videos, "
                    f"found {placeholder_count} placeholders, "
                    f"{null_channel_count} with NULL channel_id"
                )

        if not options.dry_run:
            await session.commit()

        logger.info(
            f"Video recovery: {result.videos_recovered} recovered out of "
            f"{placeholder_count} placeholders + {null_channel_count} with NULL channel_id "
            f"({result.videos_still_missing} still missing)"
        )

    async def _recover_channels(
        self,
        session: AsyncSession,
        channel_metadata: Dict[str, RecoveredChannelMetadata],
        result: RecoveryResult,
        options: RecoveryOptions,
    ) -> None:
        """
        Create or update channels from historical metadata.

        Parameters
        ----------
        session : AsyncSession
            Database session
        channel_metadata : Dict[str, RecoveredChannelMetadata]
            Map of channel_id to recovered metadata
        result : RecoveryResult
            Result object to update
        options : RecoveryOptions
            Recovery options
        """
        logger.info(f"Processing {len(channel_metadata)} channels from historical data...")

        for channel_id, recovered in channel_metadata.items():
            # Check if channel exists
            existing_channel = await self.channel_repository.get(session, channel_id)

            if existing_channel is None:
                # Channel doesn't exist - create it
                action = ChannelRecoveryAction(
                    channel_id=channel_id,
                    channel_name=recovered.channel_name,
                    channel_url=recovered.channel_url,
                    action_type="create",
                    source_date=recovered.source_date,
                )
                result.channel_actions.append(action)

                if not options.dry_run:
                    try:
                        channel_create = ChannelCreate(
                            channel_id=channel_id,
                            title=recovered.channel_name,
                            description=None,
                        )
                        await self.channel_repository.create(
                            session, obj_in=channel_create
                        )
                        logger.debug(
                            f"Created channel {channel_id}: '{recovered.channel_name}'"
                        )
                        result.channels_created += 1
                    except Exception as e:
                        logger.error(f"Failed to create channel {channel_id}: {e}")
                        result.add_error(f"Failed to create channel {channel_id}: {e}")
                else:
                    result.channels_created += 1

            elif is_placeholder_channel_name(existing_channel.title):
                # Channel exists but has placeholder name - update it
                action = ChannelRecoveryAction(
                    channel_id=channel_id,
                    channel_name=recovered.channel_name,
                    channel_url=recovered.channel_url,
                    action_type="update_name",
                    source_date=recovered.source_date,
                )
                result.channel_actions.append(action)

                if not options.dry_run:
                    try:
                        channel_update = ChannelUpdate(title=recovered.channel_name)
                        await self.channel_repository.update(
                            session, db_obj=existing_channel, obj_in=channel_update
                        )
                        logger.debug(
                            f"Updated channel {channel_id}: "
                            f"'{existing_channel.title}' -> '{recovered.channel_name}'"
                        )
                        result.channels_updated += 1
                    except Exception as e:
                        logger.error(f"Failed to update channel {channel_id}: {e}")
                        result.add_error(f"Failed to update channel {channel_id}: {e}")
                else:
                    result.channels_updated += 1

        if not options.dry_run:
            await session.commit()

        logger.info(
            f"Channel recovery: {result.channels_created} created, "
            f"{result.channels_updated} updated"
        )

    async def get_recovery_preview(
        self,
        session: AsyncSession,
        takeout_base_path: Path,
    ) -> RecoveryResult:
        """
        Preview what would be recovered without making changes.

        Convenience method that runs recovery with dry_run=True.

        Parameters
        ----------
        session : AsyncSession
            Database session
        takeout_base_path : Path
            Base directory containing historical takeout directories

        Returns
        -------
        RecoveryResult
            Preview of what would be recovered
        """
        options = RecoveryOptions(dry_run=True, verbose=True)
        return await self.recover_from_historical_takeouts(
            session, takeout_base_path, options
        )

    async def count_placeholder_videos(self, session: AsyncSession) -> int:
        """
        Count how many placeholder videos are in the database.

        Parameters
        ----------
        session : AsyncSession
            Database session

        Returns
        -------
        int
            Number of placeholder videos
        """
        count = 0
        skip = 0
        batch_size = 100

        while True:
            videos = await self.video_repository.get_multi(
                session, skip=skip, limit=batch_size
            )

            if not videos:
                break

            for video in videos:
                if is_placeholder_video_title(video.title):
                    count += 1

            skip += batch_size

        return count

    async def count_placeholder_channels(self, session: AsyncSession) -> int:
        """
        Count how many placeholder channels are in the database.

        Parameters
        ----------
        session : AsyncSession
            Database session

        Returns
        -------
        int
            Number of placeholder channels
        """
        count = 0
        skip = 0
        batch_size = 100

        while True:
            channels = await self.channel_repository.get_multi(
                session, skip=skip, limit=batch_size
            )

            if not channels:
                break

            for channel in channels:
                if is_placeholder_channel_name(channel.title):
                    count += 1

            skip += batch_size

        return count
