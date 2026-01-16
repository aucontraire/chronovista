"""
Playlist membership seeder - creates playlist-video relationships from takeout data.

This seeder handles the critical gap in playlist seeding by creating the actual
playlist-video relationships that establish playlist membership with proper ordering.

NOTE: This seeder ONLY uses real YouTube IDs from the Takeout data.
- Videos not in the database are created as placeholders with channel_id=None
- No fake channel IDs are ever generated
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.playlist_membership import PlaylistMembershipCreate
from ...models.takeout.takeout_data import TakeoutData
from ...models.video import VideoCreate
from ...repositories.playlist_membership_repository import PlaylistMembershipRepository
from ...repositories.playlist_repository import PlaylistRepository
from ...repositories.video_repository import VideoRepository
from .base_seeder import BaseSeeder, ProgressCallback, SeedResult

logger = logging.getLogger(__name__)


class PlaylistMembershipSeeder(BaseSeeder):
    """
    Seeder for playlist-video relationships from takeout data.

    Creates the many-to-many relationships between playlists and videos,
    including position tracking and handling of missing videos through
    placeholder creation.

    NOTE: Placeholder videos are created with channel_id=None (no fake IDs).
    """

    def __init__(self) -> None:
        # Depends on playlists and videos being seeded first
        super().__init__(dependencies={"playlists", "videos"})
        self.membership_repo = PlaylistMembershipRepository()
        self.video_repo = VideoRepository()
        self.playlist_repo = PlaylistRepository()

    def get_data_type(self) -> str:
        return "playlist_memberships"

    async def seed(
        self,
        session: AsyncSession,
        takeout_data: TakeoutData,
        progress: Optional[ProgressCallback] = None,
    ) -> SeedResult:
        """
        Seed playlist memberships from takeout data.

        Args:
            session: Database session
            takeout_data: Parsed takeout data
            progress: Optional progress callback

        Returns:
            SeedResult with creation/update statistics
        """
        start_time = datetime.now()
        result = SeedResult()

        if not takeout_data.playlists:
            logger.info("📋 No playlists found for membership seeding")
            return result

        # Count total items for progress tracking
        total_items = sum(len(playlist.videos) for playlist in takeout_data.playlists)
        logger.info(
            f"🔗 Seeding {total_items} playlist memberships across {len(takeout_data.playlists)} playlists..."
        )

        processed_items = 0

        for playlist in takeout_data.playlists:
            try:
                # Generate playlist ID (must match PlaylistSeeder logic)
                playlist_id = self._generate_playlist_id(playlist.name)

                # Verify playlist exists
                db_playlist = await self.playlist_repo.get_by_playlist_id(
                    session, playlist_id
                )
                if not db_playlist:
                    logger.warning(
                        f"Playlist {playlist_id} not found, skipping memberships"
                    )
                    result.failed += len(playlist.videos)
                    continue

                # Process each video in the playlist
                for position, playlist_item in enumerate(playlist.videos):
                    processed_items += 1

                    try:
                        # Clean video ID (strip whitespace from takeout data)
                        clean_video_id = playlist_item.video_id.strip()

                        # Skip empty video IDs
                        if not clean_video_id:
                            logger.warning(
                                f"Skipping empty video ID in playlist {playlist.name}"
                            )
                            result.failed += 1
                            continue

                        # Check if video exists in database
                        video_exists = await self.video_repo.get_by_video_id(
                            session, clean_video_id
                        )

                        if not video_exists:
                            # Create placeholder video entry
                            await self._create_placeholder_video(
                                session, clean_video_id
                            )
                            logger.debug(f"Created placeholder video {clean_video_id}")

                        # Check if membership already exists
                        membership_exists = (
                            await self.membership_repo.membership_exists(
                                session, playlist_id, clean_video_id
                            )
                        )

                        if membership_exists:
                            result.updated += 1
                        else:
                            # Create membership
                            membership_create = PlaylistMembershipCreate(
                                playlist_id=playlist_id,
                                video_id=clean_video_id,
                                position=position,
                                added_at=playlist_item.creation_timestamp,
                            )

                            await self.membership_repo.create(
                                session, obj_in=membership_create
                            )
                            result.created += 1

                        # Update progress every 100 items
                        if progress and processed_items % 100 == 0:
                            progress.update("playlist_memberships")

                    except Exception as e:
                        # Use original video_id in error message for debugging
                        logger.error(
                            f"Failed to process membership {playlist_id}:{playlist_item.video_id}: {e}"
                        )
                        result.failed += 1
                        result.errors.append(
                            f"Membership {playlist_id}:{playlist_item.video_id}: {str(e)}"
                        )

                # Commit after each playlist for performance
                await session.commit()
                logger.debug(
                    f"Processed playlist {playlist.name}: {len(playlist.videos)} memberships"
                )

            except Exception as e:
                logger.error(f"Failed to process playlist {playlist.name}: {e}")
                # Rollback transaction on failure to maintain consistency
                await session.rollback()
                result.failed += len(playlist.videos)
                result.errors.append(f"Playlist {playlist.name}: {str(e)}")

        # Calculate duration
        result.duration_seconds = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"🔗 Playlist membership seeding complete: {result.created} created, "
            f"{result.updated} updated, {result.failed} failed "
            f"in {result.duration_seconds:.1f}s"
        )

        return result

    def _generate_playlist_id(self, playlist_name: str) -> str:
        """
        Generate playlist ID - must match PlaylistSeeder logic.

        Uses INT_ prefix for internal playlists to distinguish from real YouTube IDs.

        Args:
            playlist_name: Name of the playlist

        Returns:
            36-character internal playlist ID with INT_ prefix (INT_{32-char MD5 hash})
        """
        hash_suffix = hashlib.md5(playlist_name.encode()).hexdigest()  # 32 lowercase hex chars
        return f"int_{hash_suffix}"  # lowercase to match Pydantic validator normalization

    async def _create_placeholder_video(
        self, session: AsyncSession, video_id: str
    ) -> None:
        """
        Create placeholder video for playlist membership.

        When a video in a playlist doesn't exist in the database (possibly deleted
        or not yet processed), we create a placeholder entry to maintain referential
        integrity while marking it as potentially deleted.

        NOTE: We use channel_id=None for placeholder videos - NO fake channel IDs.
        The channel_name_hint field can be used for future resolution via YouTube API.

        Args:
            session: Database session
            video_id: YouTube video ID to create placeholder for
        """
        try:
            # Create placeholder video with channel_id=None
            # NOTE: deleted_flag=False because we can't know if video is deleted
            # just from playlist membership. Only API verification can determine this.
            # See docs/takeout-data-quality.md for full explanation.
            video_create = VideoCreate(
                video_id=video_id,
                channel_id=None,  # No fake channel IDs - use None
                channel_name_hint=None,  # Unknown channel - will be resolved via API
                title=f"[Placeholder] Video {video_id}",
                description="Placeholder video created during playlist import - original may be deleted or private",
                upload_date=datetime.now(timezone.utc),
                duration=0,
                made_for_kids=False,
                deleted_flag=False,  # Only set True after API verification - see docs
            )

            await self.video_repo.create(session, obj_in=video_create)

        except Exception as e:
            logger.error(f"Failed to create placeholder video {video_id}: {e}")
            raise
