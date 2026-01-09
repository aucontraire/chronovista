"""
UserVideo seeder - creates user-video relationships from watch history.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.takeout.takeout_data import TakeoutData
from ...models.user_video import UserVideoCreate
from ...repositories.user_video_repository import UserVideoRepository
from .base_seeder import BaseSeeder, ProgressCallback, SeedResult

logger = logging.getLogger(__name__)


class UserVideoSeeder(BaseSeeder):
    """Seeder for user-video relationships."""

    def __init__(
        self, user_video_repo: UserVideoRepository, user_id: str = "takeout_user"
    ):
        super().__init__(dependencies={"videos"})  # Depends on videos existing
        self.user_video_repo = user_video_repo
        self.user_id = user_id

    def get_data_type(self) -> str:
        return "user_videos"

    async def seed(
        self,
        session: AsyncSession,
        takeout_data: TakeoutData,
        progress: Optional[ProgressCallback] = None,
    ) -> SeedResult:
        """Seed user-video relationships from watch history."""
        start_time = datetime.now()
        result = SeedResult()

        # Filter watch entries with timestamps
        watch_entries = [
            entry for entry in takeout_data.watch_history if entry.watched_at
        ]

        logger.info(f"👤 Seeding {len(watch_entries)} user-video relationships...")

        for i, entry in enumerate(watch_entries):
            try:
                # Transform entry to user video
                user_video_create = self._transform_entry(entry)

                if user_video_create:
                    # Check if relationship already exists
                    existing = await self.user_video_repo.get_by_composite_key(
                        session, self.user_id, user_video_create.video_id
                    )

                    if existing:
                        result.updated += 1
                    else:
                        # Create new relationship
                        await self.user_video_repo.create(
                            session, obj_in=user_video_create
                        )
                        result.created += 1

                    # Update visual progress (no numbers)
                    if progress:
                        progress.update("user_videos")

                # Commit every 1000 entries for performance
                if (i + 1) % 1000 == 0:
                    await session.commit()
                    logger.info(
                        f"Processed {i + 1:,}/{len(watch_entries):,} entries "
                        f"({result.created:,} created, {result.updated:,} updated)"
                    )

            except Exception as e:
                logger.error(f"Failed to process user video for entry {i}: {e}")
                result.failed += 1
                result.errors.append(f"Entry {i}: {str(e)}")

        # Final commit
        await session.commit()

        # Calculate duration
        result.duration_seconds = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"👤 UserVideo seeding complete: {result.created} created, "
            f"{result.updated} updated, {result.failed} failed "
            f"in {result.duration_seconds:.1f}s"
        )

        return result

    def _transform_entry(self, entry: Any) -> Optional[UserVideoCreate]:
        """Transform watch entry into UserVideo create model.

        IMPORTANT: Only process entries with real video IDs.
        Entries without video_id are skipped in video_seeder, so we must skip
        them here too to avoid FK violations.
        """
        if not entry.watched_at:
            return None

        # Skip entries without real video IDs
        # video_seeder skips these, so there's no video record to reference
        if not entry.video_id:
            return None

        return UserVideoCreate(
            user_id=self.user_id,
            video_id=entry.video_id,
            watched_at=entry.watched_at,
            rewatch_count=0,  # Default value
            liked=False,  # Will be enriched via API
            saved_to_playlist=False,  # Will be determined from playlist data
        )
