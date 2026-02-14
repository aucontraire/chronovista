"""
Video seeder - creates videos from watch history.

NOTE: This seeder ONLY uses real YouTube IDs from the Takeout data.
- Videos without video_id are skipped entirely
- Videos without channel_id use channel_id=None with channel_name_hint for future resolution
- No fake IDs are ever generated
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.enums import AvailabilityStatus, LanguageCode
from ...models.takeout.takeout_data import TakeoutData, TakeoutWatchEntry
from ...models.video import VideoCreate, VideoUpdate
from ...repositories.channel_repository import ChannelRepository
from ...repositories.video_repository import VideoRepository
from .base_seeder import BaseSeeder, ProgressCallback, SeedResult

logger = logging.getLogger(__name__)


class VideoSeeder(BaseSeeder):
    """Seeder for videos from watch history.

    NOTE: Videos without channel_id will have channel_id=None and use
    channel_name_hint for future resolution via YouTube API enrichment.
    No placeholder channels are created.
    """

    def __init__(self, video_repo: VideoRepository, channel_repo: Optional[ChannelRepository] = None):
        super().__init__(dependencies={"channels"})  # Depends on channels existing
        self.video_repo = video_repo
        self.channel_repo = channel_repo or ChannelRepository()

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

        # Count how many entries have channel_id
        entries_with_channel_id = sum(1 for v in unique_videos.values() if v.channel_id)
        logger.info(
            f"🎥 Seeding {len(unique_videos)} unique videos from watch history "
            f"({entries_with_channel_id} have channel_id)"
        )

        video_items = list(unique_videos.items())
        for i, (video_id, entry) in enumerate(video_items):
            try:
                # Check if video already exists
                existing_video = await self.video_repo.get_by_video_id(
                    session, video_id
                )

                if existing_video:
                    # Check if we have better data from takeout that should be updated
                    needs_update = False
                    update_data: dict[str, Any] = {}

                    # Update channel_id if existing is NULL but entry has one
                    if existing_video.channel_id is None and entry.channel_id:
                        update_data["channel_id"] = entry.channel_id
                        needs_update = True
                        logger.debug(
                            f"🔄 Will update video {video_id} with channel_id={entry.channel_id}"
                        )

                    # Update channel_name_hint if we don't have channel_id but have a name hint
                    if (
                        existing_video.channel_id is None
                        and existing_video.channel_name_hint is None
                        and entry.channel_name
                        and not entry.channel_id
                    ):
                        update_data["channel_name_hint"] = entry.channel_name
                        needs_update = True

                    # Update placeholder title if we now have real title
                    if (
                        existing_video.title.startswith("[Placeholder]")
                        and entry.title
                        and not entry.title.startswith("http")
                    ):
                        update_data["title"] = entry.title
                        needs_update = True

                    if needs_update:
                        await self.video_repo.update(
                            session,
                            db_obj=existing_video,
                            obj_in=VideoUpdate(**update_data),
                        )
                        result.updated += 1
                    # Note: if no update needed, we don't increment any counter
                    # (already existed with complete data)
                else:
                    # Create new video
                    # NOTE: Videos without channel_id will have channel_id=None
                    # with channel_name_hint for future resolution
                    video_create = self._transform_entry_to_video(entry)

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

        # Add debug info about potential updates that didn't happen
        logger.debug(
            f"📊 Debug: {len(video_items)} videos processed"
        )

        return result

    def _transform_entry_to_video(self, entry: TakeoutWatchEntry) -> VideoCreate:
        """Transform watch entry to VideoCreate model.

        IMPORTANT: This method expects entry.video_id to be populated.
        Entries without video_id should be filtered out before calling this.

        Channel handling:
        - If entry.channel_id exists: Use it (real YouTube channel ID)
        - If entry.channel_id is None: Set channel_id=None and populate channel_name_hint
        - We NEVER generate fake channel IDs

        Note on availability_status:
        - We do NOT auto-mark videos as unavailable based on missing channel info
        - Missing channel info often just means incomplete Takeout data
        - availability_status should only be set to non-AVAILABLE after YouTube API verification
        - See: docs/takeout-data-quality.md for full explanation
        """
        # video_id is guaranteed by seed() method - entries without are skipped
        assert entry.video_id is not None, "video_id must be present (filtered in seed())"
        video_id = entry.video_id

        # Use real channel_id if available, otherwise None
        # We NEVER generate fake channel IDs
        channel_id = entry.channel_id  # May be None - that's OK

        # Store channel name as hint for future resolution when channel_id is None
        channel_name_hint = entry.channel_name if not entry.channel_id else None

        # Use actual title, or placeholder if URL-as-title (indicates Takeout data issue)
        title = entry.title or ""
        if title.startswith("http"):
            # URL-as-title means we only have the watch URL, not the real title
            # This does NOT mean the video is deleted - just incomplete data
            title = f"[Placeholder] Video {video_id}"

        return VideoCreate(
            video_id=video_id,
            channel_id=channel_id,
            channel_name_hint=channel_name_hint,
            title=title or f"[Placeholder] Video {video_id}",
            description="",  # Not available in Takeout
            upload_date=entry.watched_at or datetime.now(timezone.utc),
            duration=0,  # Will be enriched via API
            availability_status=AvailabilityStatus.AVAILABLE,  # Only set to non-AVAILABLE after API verification - see docs
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

