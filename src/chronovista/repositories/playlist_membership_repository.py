"""
Repository for playlist membership operations.

Handles CRUD operations and specialized queries for playlist-video relationships.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db.models import PlaylistMembership as DBPlaylistMembership
from ..models.playlist_membership import (
    PlaylistMembershipCreate,
    PlaylistMembershipRead,
    PlaylistMembershipUpdate,
)
from .base import BaseSQLAlchemyRepository


class PlaylistMembershipRepository(
    BaseSQLAlchemyRepository[
        DBPlaylistMembership,
        PlaylistMembershipCreate,
        PlaylistMembershipUpdate,
        Tuple[str, str],
    ]
):
    """Repository for playlist membership operations with specialized queries."""

    def __init__(self) -> None:
        super().__init__(DBPlaylistMembership)

    async def get_playlist_videos(
        self, session: AsyncSession, playlist_id: str
    ) -> List[DBPlaylistMembership]:
        """
        Get all videos in a playlist, ordered by position.

        Args:
            session: Database session
            playlist_id: YouTube playlist ID

        Returns:
            List of playlist memberships with video details loaded
        """
        stmt = (
            select(self.model)
            .where(self.model.playlist_id == playlist_id)
            .order_by(self.model.position)
            .options(selectinload(self.model.video))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_video_playlists(
        self, session: AsyncSession, video_id: str
    ) -> List[DBPlaylistMembership]:
        """
        Get all playlists containing a video.

        Args:
            session: Database session
            video_id: YouTube video ID

        Returns:
            List of playlist memberships with playlist details loaded
        """
        stmt = (
            select(self.model)
            .where(self.model.video_id == video_id)
            .options(selectinload(self.model.playlist))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def clear_playlist_videos(
        self, session: AsyncSession, playlist_id: str
    ) -> int:
        """
        Remove all videos from a playlist.

        Args:
            session: Database session
            playlist_id: YouTube playlist ID

        Returns:
            Number of memberships removed
        """
        stmt = delete(self.model).where(self.model.playlist_id == playlist_id)
        result = await session.execute(stmt)
        return result.rowcount or 0

    async def membership_exists(
        self, session: AsyncSession, playlist_id: str, video_id: str
    ) -> bool:
        """
        Check if video is already in playlist.

        Args:
            session: Database session
            playlist_id: YouTube playlist ID
            video_id: YouTube video ID

        Returns:
            True if membership exists, False otherwise
        """
        stmt = select(self.model).where(
            self.model.playlist_id == playlist_id, self.model.video_id == video_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_membership(
        self, session: AsyncSession, playlist_id: str, video_id: str
    ) -> Optional[DBPlaylistMembership]:
        """
        Get specific playlist membership.

        Args:
            session: Database session
            playlist_id: YouTube playlist ID
            video_id: YouTube video ID

        Returns:
            Playlist membership if exists, None otherwise
        """
        stmt = select(self.model).where(
            self.model.playlist_id == playlist_id, self.model.video_id == video_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_video_position(
        self, session: AsyncSession, playlist_id: str, video_id: str, new_position: int
    ) -> Optional[DBPlaylistMembership]:
        """
        Update the position of a video in a playlist.

        Args:
            session: Database session
            playlist_id: YouTube playlist ID
            video_id: YouTube video ID
            new_position: New position (0-based)

        Returns:
            Updated membership if exists, None otherwise
        """
        membership = await self.get_membership(session, playlist_id, video_id)
        if membership:
            membership.position = new_position
            await session.flush()
            await session.refresh(membership)
            return membership
        return None

    async def get_playlist_count(self, session: AsyncSession, playlist_id: str) -> int:
        """
        Get the number of videos in a playlist.

        Args:
            session: Database session
            playlist_id: YouTube playlist ID

        Returns:
            Number of videos in playlist
        """
        from sqlalchemy import func

        stmt = select(func.count(self.model.video_id)).where(
            self.model.playlist_id == playlist_id
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    async def get_next_position(self, session: AsyncSession, playlist_id: str) -> int:
        """
        Get the next available position in a playlist.

        Args:
            session: Database session
            playlist_id: YouTube playlist ID

        Returns:
            Next position (0-based) for adding a video
        """
        from sqlalchemy import func

        stmt = select(func.max(self.model.position)).where(
            self.model.playlist_id == playlist_id
        )
        result = await session.execute(stmt)
        max_position = result.scalar()

        # Return 0 for empty playlist, or max_position + 1
        return 0 if max_position is None else max_position + 1

    async def create_or_update(
        self, session: AsyncSession, membership_create: PlaylistMembershipCreate
    ) -> DBPlaylistMembership:
        """
        Create new playlist membership or update existing one.

        Args:
            session: Database session
            membership_create: Playlist membership data

        Returns:
            Created or updated playlist membership
        """
        # Check if membership already exists
        existing = await self.get_membership(
            session, membership_create.playlist_id, membership_create.video_id
        )

        if existing:
            # Update existing membership
            existing.position = membership_create.position
            if membership_create.added_at is not None:
                existing.added_at = membership_create.added_at
            await session.flush()
            await session.refresh(existing)
            return existing
        else:
            # Create new membership
            return await self.create(session, obj_in=membership_create)
