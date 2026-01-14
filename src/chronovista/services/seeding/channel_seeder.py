"""
Channel seeder - creates channels from subscriptions and watch history.

NOTE: This seeder ONLY creates channels with real YouTube channel IDs.
Entries without valid channel IDs are skipped - videos referencing unknown
channels will use channel_id=None with channel_name_hint for future resolution.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.channel import ChannelCreate
from ...models.enums import LanguageCode
from ...models.takeout.takeout_data import (
    TakeoutData,
    TakeoutSubscription,
    TakeoutWatchEntry,
)
from ...repositories.channel_repository import ChannelRepository
from .base_seeder import BaseSeeder, ProgressCallback, SeedResult

logger = logging.getLogger(__name__)


class ChannelSeeder(BaseSeeder):
    """Seeder for channels from subscriptions and watch history."""

    def __init__(self, channel_repo: ChannelRepository):
        super().__init__(dependencies=set())  # Foundation data - no dependencies
        self.channel_repo = channel_repo

    def get_data_type(self) -> str:
        return "channels"

    async def seed(
        self,
        session: AsyncSession,
        takeout_data: TakeoutData,
        progress: Optional[ProgressCallback] = None,
    ) -> SeedResult:
        """Seed channels from subscriptions and watch history."""
        start_time = datetime.now()
        result = SeedResult()

        logger.info("📺 Starting channel seeding...")

        # Phase 1: Process subscription channels (authoritative data)
        subscription_result = await self._seed_subscription_channels(
            session, takeout_data.subscriptions, progress
        )
        result.created += subscription_result.created
        result.updated += subscription_result.updated
        result.failed += subscription_result.failed
        result.errors.extend(subscription_result.errors)

        # Phase 2: Process channels from watch history (additional channels)
        watch_history_result = await self._seed_watch_history_channels(
            session, takeout_data.watch_history, progress
        )
        result.created += watch_history_result.created
        result.updated += watch_history_result.updated
        result.failed += watch_history_result.failed
        result.errors.extend(watch_history_result.errors)

        # Calculate final duration
        result.duration_seconds = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"📺 Channel seeding complete: {result.created} created, "
            f"{result.updated} updated, {result.failed} failed "
            f"in {result.duration_seconds:.1f}s"
        )

        return result

    async def _seed_subscription_channels(
        self,
        session: AsyncSession,
        subscriptions: list[TakeoutSubscription],
        progress: Optional[ProgressCallback],
    ) -> SeedResult:
        """Seed channels from subscription data (Phase 1).

        NOTE: Only processes subscriptions with real channel_id values.
        Subscriptions without channel_id are skipped (we don't generate fake IDs).
        """
        result = SeedResult()
        skipped_no_channel_id = 0

        logger.info(
            f"📺 Phase 1: Processing {len(subscriptions)} subscription channels..."
        )

        for i, subscription in enumerate(subscriptions):
            try:
                channel_create = self._transform_subscription_to_channel(subscription)

                # Skip subscriptions without real channel_id
                if channel_create is None:
                    skipped_no_channel_id += 1
                    continue

                # Check if channel already exists
                existing_channel = await self.channel_repo.get_by_channel_id(
                    session, channel_create.channel_id
                )

                if existing_channel:
                    result.updated += 1
                else:
                    await self.channel_repo.create(session, obj_in=channel_create)
                    result.created += 1

                # Update visual progress
                if progress:
                    progress.update("channels")

                # Commit every 100 channels for performance
                if (i + 1) % 100 == 0:
                    await session.commit()
                    logger.info(
                        f"Subscription progress: {i + 1:,}/{len(subscriptions):,} "
                        f"({result.created:,} created, {result.updated:,} updated)"
                    )

            except Exception as e:
                logger.error(
                    f"Failed to process subscription channel {subscription.channel_title}: {e}"
                )
                result.failed += 1
                result.errors.append(
                    f"Subscription {subscription.channel_title}: {str(e)}"
                )

        # Final commit
        await session.commit()

        if skipped_no_channel_id > 0:
            logger.info(
                f"⏭️  Skipped {skipped_no_channel_id} subscriptions without channel IDs "
                "(will not generate fake IDs)"
            )

        logger.info(
            f"📺 Phase 1 complete: {result.created} created, {result.updated} updated"
        )
        return result

    async def _seed_watch_history_channels(
        self,
        session: AsyncSession,
        watch_history: list[TakeoutWatchEntry],
        progress: Optional[ProgressCallback],
    ) -> SeedResult:
        """Seed additional channels from watch history (Phase 2).

        NOTE: Only processes entries with real channel_id values.
        Entries without channel_id are skipped - their videos will use
        channel_id=None with channel_name_hint for future resolution.
        """
        result = SeedResult()

        # Get unique channels from watch history - ONLY those with real channel IDs
        unique_channels: dict[str, TakeoutWatchEntry] = {}
        skipped_no_channel_id = 0
        for entry in watch_history:
            if entry.channel_id:
                # Real channel ID from Takeout
                if entry.channel_id not in unique_channels:
                    unique_channels[entry.channel_id] = entry
            elif entry.channel_name:
                # Has channel name but no channel ID - skip (don't generate fake ID)
                skipped_no_channel_id += 1

        if skipped_no_channel_id > 0:
            logger.info(
                f"⏭️  Skipped {skipped_no_channel_id} watch history entries without channel IDs "
                "(will not generate fake IDs - videos will use channel_name_hint)"
            )

        logger.info(
            f"📺 Phase 2: Processing {len(unique_channels)} additional channels from watch history..."
        )

        channel_items = list(unique_channels.items())
        for i, (channel_id, entry) in enumerate(channel_items):
            try:
                # Check if channel already exists (might be from subscriptions)
                existing_channel = await self.channel_repo.get_by_channel_id(
                    session, channel_id
                )

                if existing_channel:
                    result.updated += 1
                else:
                    # Create channel from watch entry
                    channel_create = self._transform_watch_entry_to_channel(entry)
                    if channel_create:
                        await self.channel_repo.create(session, obj_in=channel_create)
                        result.created += 1
                    else:
                        # This shouldn't happen since we already filtered for channel_id
                        result.failed += 1
                        result.errors.append(
                            f"Could not transform watch entry to channel: {entry.channel_name}"
                        )

                # Update visual progress
                if progress:
                    progress.update("channels")

                # Commit every 100 channels for performance
                if (i + 1) % 100 == 0:
                    await session.commit()
                    logger.info(
                        f"Watch history progress: {i + 1:,}/{len(channel_items):,} "
                        f"({result.created:,} created, {result.updated:,} updated)"
                    )

            except Exception as e:
                logger.error(
                    f"Failed to process watch history channel {entry.channel_name}: {e}"
                )
                result.failed += 1
                result.errors.append(f"Watch entry {entry.channel_name}: {str(e)}")

        # Final commit
        await session.commit()

        logger.info(
            f"📺 Phase 2 complete: {result.created} created, {result.updated} updated"
        )
        return result

    def _transform_subscription_to_channel(
        self, subscription: TakeoutSubscription
    ) -> Optional[ChannelCreate]:
        """Transform subscription data to ChannelCreate model.

        Returns None if subscription has no real channel_id (we don't generate fake IDs).
        """
        # Require real channel ID - don't generate fake ones
        if not subscription.channel_id:
            logger.debug(
                f"Skipping subscription '{subscription.channel_title}' - no channel_id"
            )
            return None

        return ChannelCreate(
            channel_id=subscription.channel_id,
            title=subscription.channel_title,
            description="",  # Not available in Takeout
            default_language=LanguageCode.ENGLISH,  # Default fallback
            country=None,  # Not available in Takeout
            subscriber_count=None,  # Will be enriched via API
            video_count=None,  # Will be enriched via API
            thumbnail_url=None,  # Will be enriched via API
        )

    def _transform_watch_entry_to_channel(
        self, entry: TakeoutWatchEntry
    ) -> Optional[ChannelCreate]:
        """Transform watch entry to ChannelCreate model.

        Returns None if entry has no real channel_id (we don't generate fake IDs).
        """
        # Require real channel ID - don't generate fake ones
        if not entry.channel_id:
            return None

        # Use channel_name if available, otherwise create placeholder title from channel_id
        title = entry.channel_name or f"[Channel] {entry.channel_id}"

        return ChannelCreate(
            channel_id=entry.channel_id,
            title=title,
            description="",  # Not available in Takeout
            default_language=LanguageCode.ENGLISH,  # Default fallback
            country=None,  # Not available in Takeout
            subscriber_count=None,  # Will be enriched via API
            video_count=None,  # Will be enriched via API
            thumbnail_url=None,  # Will be enriched via API
        )
