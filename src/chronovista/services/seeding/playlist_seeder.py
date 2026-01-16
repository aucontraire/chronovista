"""
Playlist seeder - creates playlists from takeout data.

NOTE: This seeder currently generates a fake "user channel" ID to own playlists
because the Playlist model requires channel_id (not nullable).

TODO: Consider making Playlist.channel_id nullable to avoid fake channel IDs.
This would align with the approach used in video_seeder.py where videos can have
channel_id=None with channel_name_hint for future resolution.

For now, we use a consistent fake ID based on user_id so:
1. All user's playlists are grouped under one fake channel
2. The fake channel is easily identifiable by title "[User Channel]"
3. It can be replaced with a real channel ID if the user authenticates
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.channel import ChannelCreate
from ...models.enums import LanguageCode, PrivacyStatus
from ...models.playlist import PlaylistCreate
from ...models.takeout.takeout_data import TakeoutData, TakeoutPlaylist
from ...repositories.channel_repository import ChannelRepository
from ...repositories.playlist_repository import PlaylistRepository
from .base_seeder import BaseSeeder, ProgressCallback, SeedResult

logger = logging.getLogger(__name__)


def generate_internal_playlist_id(seed: str) -> str:
    """
    Generate internal playlist ID with INT_ prefix (36 chars total).

    This function generates deterministic, idempotent playlist IDs for internally
    created playlists (e.g., from Google Takeout imports). The INT_ prefix makes
    these IDs immediately identifiable as internal/synthetic rather than real
    YouTube playlist IDs.

    Parameters
    ----------
    seed : str
        A string to use as the seed for ID generation. Same seed always
        produces the same ID (deterministic/idempotent).

    Returns
    -------
    str
        A 36-character ID in format: INT_{32-char lowercase hex MD5 hash}
        Example: INT_5d41402abc4b2a76b9719d911017c592
    """
    hash_suffix = hashlib.md5(seed.encode()).hexdigest()  # 32 lowercase hex chars
    return f"int_{hash_suffix}"  # lowercase to match Pydantic validator normalization


def generate_user_channel_id(user_id: str) -> str:
    """
    Generate a channel ID for the user's own playlists.

    NOTE: This generates a fake channel ID because Playlist.channel_id is required.
    The ID is based on user_id for consistency, so all user playlists are grouped.

    TODO: When Playlist.channel_id becomes nullable, remove this function
    and use channel_id=None with the user's actual channel ID from YouTube API.
    """
    hash_suffix = hashlib.md5(user_id.encode()).hexdigest()[:22]
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

    async def clear_existing_playlists(
        self, session: AsyncSession, user_channel_id: str
    ) -> int:
        """
        Clear all playlists owned by the user channel.

        This is used during re-seeding to delete existing playlists before
        importing fresh data with new INT_ IDs. Playlist memberships are
        automatically deleted via CASCADE.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_channel_id : str
            The user channel ID that owns the playlists

        Returns
        -------
        int
            Number of playlists deleted
        """
        try:
            deleted_count = await self.playlist_repo.delete_by_channel_id(
                session, user_channel_id
            )
            logger.info(
                f"🗑️ Cleared {deleted_count} existing playlists (memberships cascaded)"
            )
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to clear existing playlists: {e}")
            raise

    async def seed(
        self,
        session: AsyncSession,
        takeout_data: TakeoutData,
        progress: Optional[ProgressCallback] = None,
        clear_existing: bool = False,
    ) -> SeedResult:
        """
        Seed playlists from takeout data.

        Parameters
        ----------
        session : AsyncSession
            Database session
        takeout_data : TakeoutData
            Parsed takeout data
        progress : Optional[ProgressCallback]
            Progress callback for visual updates
        clear_existing : bool
            If True, delete all existing user playlists before seeding.
            This enables re-seeding with new INT_ IDs. Memberships are
            automatically deleted via CASCADE.

        Returns
        -------
        SeedResult
            Seeding result with statistics
        """
        start_time = datetime.now()
        result = SeedResult()

        if not takeout_data.playlists:
            logger.info("📋 No playlists found in takeout data")
            return result

        # Generate user channel ID for playlist ownership
        user_channel_id = generate_user_channel_id(self.user_id)

        # Clear existing playlists if re-seeding
        if clear_existing:
            try:
                deleted_count = await self.clear_existing_playlists(
                    session, user_channel_id
                )
                logger.info(
                    f"🔄 Re-seed mode: Cleared {deleted_count} playlists "
                    f"(memberships cascaded automatically)"
                )
            except Exception as e:
                logger.error(f"Failed to clear existing playlists during re-seed: {e}")
                # Rollback the transaction on failure
                await session.rollback()
                raise

        logger.info(f"📋 Seeding {len(takeout_data.playlists)} playlists...")

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
                # Rollback batch on failure
                await session.rollback()
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
        # Generate internal playlist ID with INT_ prefix
        playlist_id = generate_internal_playlist_id(takeout_playlist.name)

        return PlaylistCreate(
            playlist_id=playlist_id,
            title=takeout_playlist.name,
            description=f"Playlist imported from Google Takeout",
            channel_id=user_channel_id,
            video_count=len(takeout_playlist.videos),
            default_language=LanguageCode.ENGLISH,  # Default fallback
            privacy_status=PrivacyStatus.PRIVATE,  # Takeout playlists are typically private
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
                # NOTE: This is a placeholder channel - will be replaced when user authenticates
                user_channel = ChannelCreate(
                    channel_id=user_channel_id,
                    title=f"[User Channel] {self.user_id}",
                    description="Placeholder user channel for Google Takeout playlist imports. "
                    "Will be replaced with real channel ID after YouTube API authentication.",
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
