"""
Video seeder - creates videos from watch history.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.channel import ChannelCreate
from ...models.enums import LanguageCode
from ...models.takeout.takeout_data import TakeoutData, TakeoutWatchEntry
from ...models.video import VideoCreate
from ...repositories.channel_repository import ChannelRepository
from ...repositories.video_repository import VideoRepository
from .base_seeder import BaseSeeder, ProgressCallback, SeedResult

logger = logging.getLogger(__name__)


def generate_valid_video_id(seed: str) -> str:
    """Generate a valid 11-character YouTube video ID."""
    return hashlib.md5(seed.encode()).hexdigest()[:11]


def generate_valid_channel_id(seed: str) -> str:
    """Generate a valid 24-character YouTube channel ID starting with 'UC'."""
    hash_suffix = hashlib.md5(seed.encode()).hexdigest()[:22]
    return f"UC{hash_suffix}"


class VideoSeeder(BaseSeeder):
    """Seeder for videos from watch history."""

    def __init__(self, video_repo: VideoRepository, channel_repo: Optional[ChannelRepository] = None):
        super().__init__(dependencies={"channels"})  # Depends on channels existing
        self.video_repo = video_repo
        self.channel_repo = channel_repo or ChannelRepository()
        self._created_placeholder_channels: set[str] = set()  # Track created placeholders

    def get_data_type(self) -> str:
        return "videos"

    async def seed(
        self,
        session: AsyncSession,
        takeout_data: TakeoutData,
        progress: Optional[ProgressCallback] = None,
    ) -> SeedResult:
        """Seed videos from watch history."""
        start_time = datetime.now()
        result = SeedResult()

        # Get unique videos from watch history
        # IMPORTANT: Only include entries with real video IDs - never generate fake ones
        unique_videos: dict[str, TakeoutWatchEntry] = {}
        skipped_no_video_id = 0
        for entry in takeout_data.watch_history:
            if entry.video_id:
                # Real video ID from Takeout
                if entry.video_id not in unique_videos:
                    unique_videos[entry.video_id] = entry
            else:
                # No video ID - skip this entry (don't generate fake ID)
                skipped_no_video_id += 1

        if skipped_no_video_id > 0:
            logger.warning(
                f"⏭️  Skipped {skipped_no_video_id} entries without video IDs "
                "(will not generate fake IDs)"
            )

        logger.info(
            f"🎥 Seeding {len(unique_videos)} unique videos from watch history..."
        )

        video_items = list(unique_videos.items())
        for i, (video_id, entry) in enumerate(video_items):
            try:
                # Check if video already exists
                existing_video = await self.video_repo.get_by_video_id(
                    session, video_id
                )

                if existing_video:
                    result.updated += 1
                else:
                    # Create new video
                    video_create = self._transform_entry_to_video(entry)

                    # Ensure channel exists before creating video (handles orphan videos)
                    await self._ensure_channel_exists(
                        session, video_create.channel_id, entry.channel_name
                    )

                    await self.video_repo.create(session, obj_in=video_create)
                    result.created += 1

                # Update visual progress
                if progress:
                    progress.update("videos")

                # Commit every 500 videos for performance
                if (i + 1) % 500 == 0:
                    await session.commit()
                    logger.info(
                        f"Video progress: {i + 1:,}/{len(video_items):,} "
                        f"({result.created:,} created, {result.updated:,} updated)"
                    )

            except Exception as e:
                logger.error(f"Failed to process video {video_id}: {e}")
                result.failed += 1
                result.errors.append(f"Video {video_id}: {str(e)}")

        # Final commit
        await session.commit()

        # Calculate duration
        result.duration_seconds = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"🎥 Video seeding complete: {result.created} created, "
            f"{result.updated} updated, {result.failed} failed "
            f"in {result.duration_seconds:.1f}s"
        )

        return result

    def _transform_entry_to_video(self, entry: TakeoutWatchEntry) -> VideoCreate:
        """Transform watch entry to VideoCreate model.

        IMPORTANT: This method expects entry.video_id to be populated.
        Entries without video_id should be filtered out before calling this.

        Note on deleted_flag:
        - We do NOT auto-mark videos as deleted based on missing channel info
        - Missing channel info often just means incomplete Takeout data
        - deleted_flag should only be set True after YouTube API verification
        - See: docs/takeout-data-quality.md for full explanation
        """
        # video_id is guaranteed by seed() method - entries without are skipped
        assert entry.video_id is not None, "video_id must be present (filtered in seed())"
        video_id = entry.video_id

        # Handle missing channel ID - generate placeholder if needed
        # This is OK because we can later update with real channel ID via API
        channel_id = entry.channel_id or generate_valid_channel_id(
            entry.channel_name or "Unknown"
        )

        # Use actual title, or placeholder if URL-as-title (indicates Takeout data issue)
        title = entry.title or ""
        if title.startswith("http"):
            # URL-as-title means we only have the watch URL, not the real title
            # This does NOT mean the video is deleted - just incomplete data
            title = f"[Placeholder] Video {video_id}"

        return VideoCreate(
            video_id=video_id,
            channel_id=channel_id,
            title=title or f"[Placeholder] Video {video_id}",
            description="",  # Not available in Takeout
            upload_date=entry.watched_at or datetime.now(timezone.utc),
            duration=0,  # Will be enriched via API
            deleted_flag=False,  # Only set True after API verification - see docs
            made_for_kids=False,  # Will be enriched via API
            self_declared_made_for_kids=False,  # Will be enriched via API
            default_language=LanguageCode.ENGLISH,  # Default fallback
            default_audio_language=None,  # Will be enriched via API
            available_languages=None,  # Will be enriched via API
            region_restriction=None,  # Will be enriched via API
            content_rating=None,  # Will be enriched via API
            like_count=None,  # Will be enriched via API
            view_count=None,  # Will be enriched via API
            comment_count=None,  # Will be enriched via API
        )

    async def _ensure_channel_exists(
        self,
        session: AsyncSession,
        channel_id: str,
        channel_name: Optional[str],
    ) -> None:
        """
        Ensure a channel exists before creating a video that references it.

        This handles edge cases where watch history entries have no channel info
        (deleted/private videos). Creates a placeholder channel if needed.
        """
        # Skip if we already created this placeholder in this session
        if channel_id in self._created_placeholder_channels:
            return

        # Check if channel exists
        existing = await self.channel_repo.get_by_channel_id(session, channel_id)
        if existing:
            return

        # Create placeholder channel
        title = channel_name or f"[Unknown Channel] {channel_id}"
        placeholder = ChannelCreate(
            channel_id=channel_id,
            title=title,
            description="",
            default_language=LanguageCode.ENGLISH,
            country=None,
            subscriber_count=None,
            video_count=None,
            thumbnail_url=None,
        )

        await self.channel_repo.create(session, obj_in=placeholder)
        self._created_placeholder_channels.add(channel_id)
        logger.debug(f"Created placeholder channel: {channel_id} ({title})")
