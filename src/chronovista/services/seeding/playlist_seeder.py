"""
Playlist seeder - creates playlists from takeout data.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.channel import ChannelCreate
from ...models.enums import LanguageCode
from ...models.playlist import PlaylistCreate
from ...models.takeout.takeout_data import TakeoutData, TakeoutPlaylist
from ...repositories.channel_repository import ChannelRepository
from ...repositories.playlist_repository import PlaylistRepository
from .base_seeder import BaseSeeder, ProgressCallback, SeedResult

logger = logging.getLogger(__name__)


def generate_valid_playlist_id(seed: str) -> str:
    """Generate a valid 30-34 character YouTube playlist ID starting with 'PL'."""
    hash_suffix = hashlib.md5(seed.encode()).hexdigest()[:32]
    return f"PL{hash_suffix}"


def generate_valid_channel_id(seed: str) -> str:
    """Generate a valid 24-character YouTube channel ID starting with 'UC'."""
    hash_suffix = hashlib.md5(seed.encode()).hexdigest()[:22]
    return f"UC{hash_suffix}"


class PlaylistSeeder(BaseSeeder):
    """Seeder for playlists from takeout data."""

    def __init__(
        self, playlist_repo: PlaylistRepository, user_id: str = "takeout_user"
    ):
        super().__init__(
            dependencies=set()
        )  # Remove channel dependency - we'll create user channel ourselves
        self.playlist_repo = playlist_repo
        self.channel_repo = ChannelRepository()
        self.user_id = user_id
        self._user_channel_created = False

    def get_data_type(self) -> str:
        return "playlists"

    async def seed(
        self,
        session: AsyncSession,
        takeout_data: TakeoutData,
        progress: Optional[ProgressCallback] = None,
    ) -> SeedResult:
        """Seed playlists from takeout data."""
        start_time = datetime.now()
        result = SeedResult()

        if not takeout_data.playlists:
            logger.info("📋 No playlists found in takeout data")
            return result

        logger.info(f"📋 Seeding {len(takeout_data.playlists)} playlists...")

        # Generate user channel ID for playlist ownership
        user_channel_id = generate_valid_channel_id(self.user_id)

        # Ensure user channel exists (create if necessary)
        if not self._user_channel_created:
            await self._ensure_user_channel_exists(session, user_channel_id)
            self._user_channel_created = True

        for i, playlist in enumerate(takeout_data.playlists):
            try:
                # Transform playlist to create model
                playlist_create = self._transform_playlist_to_create(
                    playlist, user_channel_id
                )

                # Check if playlist already exists
                existing_playlist = await self.playlist_repo.get_by_playlist_id(
                    session, playlist_create.playlist_id
                )

                if existing_playlist:
                    result.updated += 1
                else:
                    await self.playlist_repo.create(session, obj_in=playlist_create)
                    result.created += 1

                # Update visual progress
                if progress:
                    progress.update("playlists")

                # Commit every 50 playlists for performance
                if (i + 1) % 50 == 0:
                    await session.commit()
                    logger.info(
                        f"Playlist progress: {i + 1:,}/{len(takeout_data.playlists):,} "
                        f"({result.created:,} created, {result.updated:,} updated)"
                    )

            except Exception as e:
                logger.error(f"Failed to process playlist {playlist.name}: {e}")
                result.failed += 1
                result.errors.append(f"Playlist {playlist.name}: {str(e)}")

        # Final commit
        await session.commit()

        # Calculate duration
        result.duration_seconds = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"📋 Playlist seeding complete: {result.created} created, "
            f"{result.updated} updated, {result.failed} failed "
            f"in {result.duration_seconds:.1f}s"
        )

        return result

    def _transform_playlist_to_create(
        self, takeout_playlist: TakeoutPlaylist, user_channel_id: str
    ) -> PlaylistCreate:
        """Transform takeout playlist to PlaylistCreate model."""
        # Generate valid playlist ID
        playlist_id = generate_valid_playlist_id(takeout_playlist.name)

        return PlaylistCreate(
            playlist_id=playlist_id,
            title=takeout_playlist.name,
            description=f"Playlist imported from Google Takeout",
            channel_id=user_channel_id,
            video_count=len(takeout_playlist.videos),
            default_language=LanguageCode.ENGLISH,  # Default fallback
            privacy_status="private",  # Takeout playlists are typically private
        )

    async def _ensure_user_channel_exists(
        self, session: AsyncSession, user_channel_id: str
    ) -> None:
        """Ensure the user channel exists, creating it if necessary."""
        try:
            # Check if user channel already exists
            existing_channel = await self.channel_repo.get_by_channel_id(
                session, user_channel_id
            )

            if not existing_channel:
                # Create user channel for playlist ownership
                user_channel = ChannelCreate(
                    channel_id=user_channel_id,
                    title=f"User Channel ({self.user_id})",
                    description="User channel created for Google Takeout playlist imports",
                    default_language=LanguageCode.ENGLISH,
                    country=None,
                    subscriber_count=0,
                    video_count=0,
                    thumbnail_url=None,
                )

                await self.channel_repo.create(session, obj_in=user_channel)
                logger.info(
                    f"📺 Created user channel {user_channel_id} for playlist ownership"
                )
            else:
                logger.info(f"📺 User channel {user_channel_id} already exists")

        except Exception as e:
            logger.error(f"Failed to ensure user channel exists: {e}")
            raise
