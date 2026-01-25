"""
Playlist seeder - creates playlists from takeout data.

User playlists imported from Google Takeout have channel_id=None since the user's
YouTube channel ID is not available during offline Takeout imports. After OAuth
authentication, the channel_id can be populated with the user's actual channel ID.

This aligns with the approach used in video_seeder.py where videos can have
channel_id=None with channel_name_hint for future resolution.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.enums import LanguageCode, PrivacyStatus
from ...models.playlist import PlaylistCreate
from ...models.takeout.takeout_data import TakeoutData, TakeoutPlaylist
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


class PlaylistSeeder(BaseSeeder):
    """Seeder for playlists from takeout data."""

    def __init__(
        self, playlist_repo: PlaylistRepository, user_id: str = "takeout_user"
    ):
        super().__init__(dependencies=set())
        self.playlist_repo = playlist_repo
        self.user_id = user_id

    def get_data_type(self) -> str:
        return "playlists"

    async def clear_existing_user_playlists(
        self, session: AsyncSession
    ) -> int:
        """
        Clear all user playlists (those with channel_id=NULL).

        This is used during re-seeding to delete existing user playlists before
        importing fresh data with new INT_ IDs. Playlist memberships are
        automatically deleted via CASCADE.

        Parameters
        ----------
        session : AsyncSession
            Database session

        Returns
        -------
        int
            Number of playlists deleted
        """
        try:
            deleted_count = await self.playlist_repo.delete_by_null_channel_id(session)
            logger.info(
                f"🗑️ Cleared {deleted_count} existing user playlists (memberships cascaded)"
            )
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to clear existing user playlists: {e}")
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

        # Clear existing user playlists if re-seeding
        if clear_existing:
            try:
                deleted_count = await self.clear_existing_user_playlists(session)
                logger.info(
                    f"🔄 Re-seed mode: Cleared {deleted_count} user playlists "
                    f"(memberships cascaded automatically)"
                )
            except Exception as e:
                logger.error(f"Failed to clear existing playlists during re-seed: {e}")
                # Rollback the transaction on failure
                await session.rollback()
                raise

        logger.info(f"📋 Seeding {len(takeout_data.playlists)} playlists...")

        for i, playlist in enumerate(takeout_data.playlists):
            try:
                # Transform playlist to create model (channel_id=None for Takeout imports)
                playlist_create = self._transform_playlist_to_create(playlist)

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
        self, takeout_playlist: TakeoutPlaylist
    ) -> PlaylistCreate:
        """
        Transform takeout playlist to PlaylistCreate model.

        If the TakeoutPlaylist has a youtube_id (from playlists.csv), use it as
        the playlist_id directly.

        If no youtube_id is available, generate an internal ID with int_ prefix.
        The link status can be derived from the playlist_id prefix:
        - PL/LL/WL/HL prefixes indicate linked YouTube playlists
        - int_ prefix indicates pending/internal playlists

        Maps takeout visibility to privacy_status:
        - "Private" -> PrivacyStatus.PRIVATE
        - "Public" -> PrivacyStatus.PUBLIC
        - "Unlisted" -> PrivacyStatus.UNLISTED
        - None/unknown -> PrivacyStatus.PRIVATE (default)

        Note: channel_id is set to None for Takeout imports since the user's
        YouTube channel ID is not available during offline imports. It can be
        populated later after OAuth authentication.
        """
        # Use YouTube ID directly if available from playlists.csv
        if takeout_playlist.youtube_id:
            playlist_id = takeout_playlist.youtube_id
        else:
            # Fallback: Generate internal playlist ID with int_ prefix
            playlist_id = generate_internal_playlist_id(takeout_playlist.name)

        # Map visibility string to PrivacyStatus enum
        privacy_status = self._map_visibility_to_privacy_status(
            takeout_playlist.visibility
        )

        return PlaylistCreate(
            playlist_id=playlist_id,
            title=takeout_playlist.name,
            description="Playlist imported from Google Takeout",
            channel_id=None,  # User's channel ID not known during Takeout import
            video_count=len(takeout_playlist.videos),
            default_language=LanguageCode.ENGLISH,  # Default fallback
            privacy_status=privacy_status,
            published_at=takeout_playlist.created_at,
        )

    def _map_visibility_to_privacy_status(
        self, visibility: Optional[str]
    ) -> PrivacyStatus:
        """
        Map takeout visibility string to PrivacyStatus enum.

        Parameters
        ----------
        visibility : Optional[str]
            Visibility string from playlists.csv ("Private", "Public", "Unlisted")

        Returns
        -------
        PrivacyStatus
            The corresponding privacy status enum value
        """
        if visibility is None:
            return PrivacyStatus.PRIVATE

        visibility_lower = visibility.lower()
        if visibility_lower == "public":
            return PrivacyStatus.PUBLIC
        elif visibility_lower == "unlisted":
            return PrivacyStatus.UNLISTED
        else:
            # Default to PRIVATE for "Private" or any unknown value
            return PrivacyStatus.PRIVATE

