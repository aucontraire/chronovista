"""
Video seeder - creates videos from watch history.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .base_seeder import BaseSeeder, SeedResult, ProgressCallback
from ...models.takeout.takeout_data import TakeoutData, TakeoutWatchEntry
from ...models.video import VideoCreate
from ...models.enums import LanguageCode
from ...repositories.video_repository import VideoRepository


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
    
    def __init__(self, video_repo: VideoRepository):
        super().__init__(dependencies={"channels"})  # Depends on channels existing
        self.video_repo = video_repo
    
    def get_data_type(self) -> str:
        return "videos"
    
    async def seed(
        self, 
        session: AsyncSession, 
        takeout_data: TakeoutData,
        progress: Optional[ProgressCallback] = None
    ) -> SeedResult:
        """Seed videos from watch history."""
        start_time = datetime.now()
        result = SeedResult()
        
        # Get unique videos from watch history
        unique_videos: dict[str, TakeoutWatchEntry] = {}
        for entry in takeout_data.watch_history:
            video_id = entry.video_id or generate_valid_video_id(entry.title_url or "unknown")
            if video_id not in unique_videos:
                unique_videos[video_id] = entry
        
        logger.info(f"🎥 Seeding {len(unique_videos)} unique videos from watch history...")
        
        video_items = list(unique_videos.items())
        for i, (video_id, entry) in enumerate(video_items):
            try:
                # Check if video already exists
                existing_video = await self.video_repo.get_by_video_id(session, video_id)
                
                if existing_video:
                    result.updated += 1
                else:
                    # Create new video
                    video_create = self._transform_entry_to_video(entry)
                    await self.video_repo.create(session, obj_in=video_create)
                    result.created += 1
                
                # Update visual progress
                if progress:
                    progress.update("videos")
                
                # Commit every 500 videos for performance
                if (i + 1) % 500 == 0:
                    await session.commit()
                    logger.info(f"Video progress: {i + 1:,}/{len(video_items):,} "
                              f"({result.created:,} created, {result.updated:,} updated)")
                
            except Exception as e:
                logger.error(f"Failed to process video {video_id}: {e}")
                result.failed += 1
                result.errors.append(f"Video {video_id}: {str(e)}")
        
        # Final commit
        await session.commit()
        
        # Calculate duration
        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"🎥 Video seeding complete: {result.created} created, "
                   f"{result.updated} updated, {result.failed} failed "
                   f"in {result.duration_seconds:.1f}s")
        
        return result
    
    def _transform_entry_to_video(self, entry: TakeoutWatchEntry) -> VideoCreate:
        """Transform watch entry to VideoCreate model."""
        # Track if video ID was originally missing for deleted_flag logic
        originally_missing_video_id = not entry.video_id
        
        # Handle missing video ID
        video_id = entry.video_id or generate_valid_video_id(entry.title_url or "unknown")
        
        # Handle missing channel ID
        channel_id = entry.channel_id or generate_valid_channel_id(entry.channel_name or "Unknown")
        
        # Check for indicators of deleted videos
        is_likely_deleted = (
            originally_missing_video_id or 
            "deleted" in (entry.title or "").lower() or
            not entry.video_id
        )
        
        return VideoCreate(
            video_id=video_id,
            channel_id=channel_id,
            title=entry.title or f"[Deleted Video] {video_id}",
            description="",  # Not available in Takeout
            upload_date=entry.watched_at or datetime.now(timezone.utc),
            duration=0,  # Will be enriched via API
            deleted_flag=is_likely_deleted,
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