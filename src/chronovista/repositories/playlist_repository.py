"""
Playlist repository implementation.

Provides data access layer for playlists with full CRUD operations,
content organization analytics, and playlist management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.db.models import Playlist as PlaylistDB
from chronovista.models.playlist import (
    Playlist,
    PlaylistAnalytics,
    PlaylistCreate,
    PlaylistSearchFilters,
    PlaylistStatistics,
    PlaylistUpdate,
)
from chronovista.models.youtube_types import PlaylistId, is_youtube_playlist_id
from chronovista.repositories.base import BaseSQLAlchemyRepository


class PlaylistRepository(
    BaseSQLAlchemyRepository[PlaylistDB, PlaylistCreate, PlaylistUpdate, str]
):
    """Repository for playlist operations."""

    def __init__(self) -> None:
        super().__init__(PlaylistDB)

    async def get(
        self, session: AsyncSession, playlist_id: str
    ) -> Optional[PlaylistDB]:
        """Get playlist by playlist ID."""
        result = await session.execute(
            select(PlaylistDB).where(PlaylistDB.playlist_id == playlist_id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, playlist_id: str) -> bool:
        """Check if playlist exists by playlist ID."""
        result = await session.execute(
            select(PlaylistDB.playlist_id).where(PlaylistDB.playlist_id == playlist_id)
        )
        return result.first() is not None

    async def get_by_playlist_id(
        self, session: AsyncSession, playlist_id: str
    ) -> Optional[PlaylistDB]:
        """Get playlist by playlist ID (alias for get method)."""
        return await self.get(session, playlist_id)

    async def exists_by_playlist_id(
        self, session: AsyncSession, playlist_id: str
    ) -> bool:
        """Check if playlist exists by playlist ID (alias for exists method)."""
        return await self.exists(session, playlist_id)

    async def get_with_channel(
        self, session: AsyncSession, playlist_id: str
    ) -> Optional[PlaylistDB]:
        """Get playlist with channel information loaded."""
        result = await session.execute(
            select(PlaylistDB)
            .options(selectinload(PlaylistDB.channel))
            .where(PlaylistDB.playlist_id == playlist_id)
        )
        return result.scalar_one_or_none()

    async def create_or_update(
        self, session: AsyncSession, playlist_create: PlaylistCreate
    ) -> PlaylistDB:
        """Create new playlist or update existing one."""
        existing = await self.get_by_playlist_id(session, playlist_create.playlist_id)

        if existing:
            # Update existing playlist
            update_data = PlaylistUpdate(
                title=playlist_create.title,
                description=playlist_create.description,
                default_language=playlist_create.default_language,
                privacy_status=playlist_create.privacy_status,
                video_count=playlist_create.video_count,
            )
            return await self.update(session, db_obj=existing, obj_in=update_data)
        else:
            # Create new playlist
            return await self.create(session, obj_in=playlist_create)

    async def get_by_channel_id(
        self, session: AsyncSession, channel_id: str, skip: int = 0, limit: int = 100
    ) -> List[PlaylistDB]:
        """Get all playlists for a specific channel."""
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.channel_id == channel_id)
            .order_by(PlaylistDB.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_privacy_status(
        self,
        session: AsyncSession,
        privacy_status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PlaylistDB]:
        """Get playlists by privacy status."""
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.privacy_status == privacy_status)
            .order_by(PlaylistDB.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_language(
        self, session: AsyncSession, language_code: str, skip: int = 0, limit: int = 100
    ) -> List[PlaylistDB]:
        """Get playlists by default language."""
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.default_language == language_code)
            .order_by(PlaylistDB.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search_playlists(
        self, session: AsyncSession, filters: PlaylistSearchFilters
    ) -> List[PlaylistDB]:
        """Search playlists with advanced filters."""
        query = select(PlaylistDB)

        # Apply filters
        conditions: List[Any] = []

        if filters.playlist_ids:
            conditions.append(PlaylistDB.playlist_id.in_(filters.playlist_ids))

        if filters.channel_ids:
            conditions.append(PlaylistDB.channel_id.in_(filters.channel_ids))

        if filters.title_query:
            conditions.append(PlaylistDB.title.ilike(f"%{filters.title_query}%"))

        if filters.description_query:
            conditions.append(
                PlaylistDB.description.ilike(f"%{filters.description_query}%")
            )

        if filters.language_codes:
            conditions.append(PlaylistDB.default_language.in_(filters.language_codes))

        if filters.privacy_statuses:
            conditions.append(PlaylistDB.privacy_status.in_(filters.privacy_statuses))

        if filters.min_video_count is not None:
            conditions.append(PlaylistDB.video_count >= filters.min_video_count)

        if filters.max_video_count is not None:
            conditions.append(PlaylistDB.video_count <= filters.max_video_count)

        if filters.has_description is not None:
            if filters.has_description:
                conditions.append(PlaylistDB.description.is_not(None))
                conditions.append(PlaylistDB.description != "")
            else:
                conditions.append(
                    or_(
                        PlaylistDB.description.is_(None),
                        PlaylistDB.description == "",
                    )
                )

        if filters.created_after:
            conditions.append(PlaylistDB.created_at >= filters.created_after)

        if filters.created_before:
            conditions.append(PlaylistDB.created_at <= filters.created_before)

        if filters.updated_after:
            conditions.append(PlaylistDB.updated_at >= filters.updated_after)

        if filters.updated_before:
            conditions.append(PlaylistDB.updated_at <= filters.updated_before)

        # Apply linked_status filter (based on playlist_id prefix)
        # Linked = YouTube IDs (PL prefix or system: LL, WL, HL)
        # Unlinked = Internal IDs (int_ prefix)
        if filters.linked_status == "linked":
            conditions.append(
                or_(
                    PlaylistDB.playlist_id.startswith("PL"),
                    PlaylistDB.playlist_id.in_(["LL", "WL", "HL"]),
                )
            )
        elif filters.linked_status == "unlinked":
            conditions.append(PlaylistDB.playlist_id.startswith("int_"))
        # "all" (default) - no filter applied

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(PlaylistDB.created_at.desc())

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_popular_playlists(
        self, session: AsyncSession, limit: int = 50
    ) -> List[PlaylistDB]:
        """Get most popular playlists by video count."""
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.privacy_status == "public")
            .order_by(desc(PlaylistDB.video_count))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent_playlists(
        self, session: AsyncSession, limit: int = 50
    ) -> List[PlaylistDB]:
        """Get most recently created playlists."""
        result = await session.execute(
            select(PlaylistDB).order_by(desc(PlaylistDB.created_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def get_playlists_by_size_range(
        self, session: AsyncSession, min_videos: int, max_videos: int
    ) -> List[PlaylistDB]:
        """Get playlists within a specific video count range."""
        result = await session.execute(
            select(PlaylistDB)
            .where(
                and_(
                    PlaylistDB.video_count >= min_videos,
                    PlaylistDB.video_count <= max_videos,
                )
            )
            .order_by(desc(PlaylistDB.video_count))
        )
        return list(result.scalars().all())

    async def get_playlist_statistics(
        self, session: AsyncSession
    ) -> PlaylistStatistics:
        """Get comprehensive playlist statistics."""
        # Basic counts
        total_result = await session.execute(
            select(
                func.count(PlaylistDB.playlist_id).label("total_playlists"),
                func.sum(PlaylistDB.video_count).label("total_videos"),
                func.avg(PlaylistDB.video_count).label("avg_videos_per_playlist"),
                func.count(func.distinct(PlaylistDB.channel_id)).label(
                    "unique_channels"
                ),
                func.sum(
                    case(
                        (
                            and_(
                                PlaylistDB.description.is_not(None),
                                PlaylistDB.description != "",
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("playlists_with_descriptions"),
            )
        )

        stats = total_result.first()
        if not stats:
            return PlaylistStatistics(
                total_playlists=0,
                total_videos=0,
                avg_videos_per_playlist=0.0,
                unique_channels=0,
                playlists_with_descriptions=0,
            )

        # Privacy distribution
        privacy_result = await session.execute(
            select(
                PlaylistDB.privacy_status, func.count(PlaylistDB.playlist_id)
            ).group_by(PlaylistDB.privacy_status)
        )
        privacy_distribution = {row[0]: row[1] for row in privacy_result}

        # Language distribution
        language_result = await session.execute(
            select(PlaylistDB.default_language, func.count(PlaylistDB.playlist_id))
            .where(PlaylistDB.default_language.is_not(None))
            .group_by(PlaylistDB.default_language)
        )
        language_distribution = {str(row[0]): row[1] for row in language_result}

        # Top channels by playlist count
        channels_result = await session.execute(
            select(PlaylistDB.channel_id, func.count(PlaylistDB.playlist_id))
            .group_by(PlaylistDB.channel_id)
            .order_by(func.count(PlaylistDB.playlist_id).desc())
            .limit(10)
        )
        top_channels_by_playlists = [(row[0], row[1]) for row in channels_result]

        # Playlist size distribution
        size_distribution = {}
        size_ranges = [
            ("0-5", 0, 5),
            ("6-15", 6, 15),
            ("16-50", 16, 50),
            ("51-100", 51, 100),
            ("100+", 101, float("inf")),
        ]

        for range_name, min_size, max_size in size_ranges:
            if max_size == float("inf"):
                count_result = await session.execute(
                    select(func.count(PlaylistDB.playlist_id)).where(
                        PlaylistDB.video_count >= min_size
                    )
                )
            else:
                count_result = await session.execute(
                    select(func.count(PlaylistDB.playlist_id)).where(
                        and_(
                            PlaylistDB.video_count >= min_size,
                            PlaylistDB.video_count <= max_size,
                        )
                    )
                )
            size_distribution[range_name] = count_result.scalar() or 0

        return PlaylistStatistics(
            total_playlists=int(stats.total_playlists or 0),
            total_videos=int(stats.total_videos or 0),
            avg_videos_per_playlist=float(stats.avg_videos_per_playlist or 0.0),
            unique_channels=int(stats.unique_channels or 0),
            privacy_distribution=privacy_distribution,
            language_distribution=language_distribution,
            top_channels_by_playlists=top_channels_by_playlists,
            playlist_size_distribution=size_distribution,
            playlists_with_descriptions=int(stats.playlists_with_descriptions or 0),
        )

    async def get_channel_playlist_count(
        self, session: AsyncSession, channel_id: str
    ) -> int:
        """Get the number of playlists for a specific channel."""
        result = await session.execute(
            select(func.count(PlaylistDB.playlist_id)).where(
                PlaylistDB.channel_id == channel_id
            )
        )
        return result.scalar() or 0

    async def get_playlists_by_multiple_channels(
        self, session: AsyncSession, channel_ids: List[str]
    ) -> Dict[str, List[PlaylistDB]]:
        """Get playlists for multiple channels efficiently."""
        if not channel_ids:
            return {}

        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.channel_id.in_(channel_ids))
            .order_by(PlaylistDB.channel_id, PlaylistDB.created_at.desc())
        )

        # Group playlists by channel_id
        channel_playlists: Dict[str, List[PlaylistDB]] = {}
        for playlist in result.scalars().all():
            if playlist.channel_id not in channel_playlists:
                channel_playlists[playlist.channel_id] = []
            channel_playlists[playlist.channel_id].append(playlist)

        return channel_playlists

    async def bulk_create_playlists(
        self, session: AsyncSession, playlists: List[PlaylistCreate]
    ) -> List[PlaylistDB]:
        """Create multiple playlists efficiently."""
        created_playlists = []

        for playlist_create in playlists:
            # Check if playlist already exists
            existing = await self.get_by_playlist_id(
                session, playlist_create.playlist_id
            )
            if not existing:
                playlist = await self.create(session, obj_in=playlist_create)
                created_playlists.append(playlist)
            else:
                created_playlists.append(existing)

        return created_playlists

    async def bulk_update_video_counts(
        self, session: AsyncSession, playlist_counts: Dict[str, int]
    ) -> int:
        """Bulk update video counts for multiple playlists."""
        updated_count = 0

        for playlist_id, new_count in playlist_counts.items():
            playlist = await self.get_by_playlist_id(session, playlist_id)
            if playlist and playlist.video_count != new_count:
                update_data = PlaylistUpdate(
                    title=None,
                    description=None,
                    default_language=None,
                    privacy_status=None,
                    video_count=new_count,
                )
                await self.update(session, db_obj=playlist, obj_in=update_data)
                updated_count += 1

        return updated_count

    async def delete_by_playlist_id(
        self, session: AsyncSession, playlist_id: str
    ) -> Optional[PlaylistDB]:
        """Delete playlist by playlist ID."""
        playlist = await self.get_by_playlist_id(session, playlist_id)
        if playlist:
            await session.delete(playlist)
            await session.flush()
        return playlist

    async def delete_by_channel_id(self, session: AsyncSession, channel_id: str) -> int:
        """Delete all playlists for a specific channel."""
        # Get count first
        count_result = await session.execute(
            select(func.count(PlaylistDB.playlist_id)).where(
                PlaylistDB.channel_id == channel_id
            )
        )
        count = count_result.scalar() or 0

        # Delete playlists
        playlists = await self.get_by_channel_id(session, channel_id, limit=1000)
        for playlist in playlists:
            await session.delete(playlist)

        await session.flush()
        return count

    async def get_unlinked_playlists(
        self, session: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[PlaylistDB]:
        """
        Get playlists with internal IDs (not linked to YouTube).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        skip : int, optional
            Number of records to skip. Default 0.
        limit : int, optional
            Maximum records to return. Default 100.

        Returns
        -------
        List[PlaylistDB]
            Playlists with int_ prefix (internal IDs), ordered by title.
        """
        result = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.playlist_id.startswith("int_"))
            .order_by(PlaylistDB.title)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_linked_playlists(
        self, session: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[PlaylistDB]:
        """
        Get playlists with YouTube IDs (linked to YouTube).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        skip : int, optional
            Number of records to skip. Default 0.
        limit : int, optional
            Maximum records to return. Default 100.

        Returns
        -------
        List[PlaylistDB]
            Playlists with PL prefix or system IDs (LL, WL, HL), ordered by title.
        """
        result = await session.execute(
            select(PlaylistDB)
            .where(
                or_(
                    PlaylistDB.playlist_id.startswith("PL"),
                    PlaylistDB.playlist_id.in_(["LL", "WL", "HL"]),
                )
            )
            .order_by(PlaylistDB.title)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_link_statistics(self, session: AsyncSession) -> Dict[str, int]:
        """
        Get statistics about playlist linking.

        Parameters
        ----------
        session : AsyncSession
            Database session.

        Returns
        -------
        Dict[str, int]
            Statistics with keys:
            - total_playlists: Total number of playlists
            - linked_playlists: Playlists with YouTube IDs (PL, LL, WL, HL)
            - unlinked_playlists: Playlists with internal IDs (int_)
        """
        # Get total count
        total_result = await session.execute(
            select(func.count(PlaylistDB.playlist_id))
        )
        total_playlists = total_result.scalar() or 0

        # Get linked count (YouTube IDs)
        linked_result = await session.execute(
            select(func.count(PlaylistDB.playlist_id)).where(
                or_(
                    PlaylistDB.playlist_id.startswith("PL"),
                    PlaylistDB.playlist_id.in_(["LL", "WL", "HL"]),
                )
            )
        )
        linked_playlists = linked_result.scalar() or 0

        # Calculate unlinked
        unlinked_playlists = total_playlists - linked_playlists

        return {
            "total_playlists": total_playlists,
            "linked_playlists": linked_playlists,
            "unlinked_playlists": unlinked_playlists,
        }

    async def find_similar_playlists(
        self, session: AsyncSession, playlist_id: str, limit: int = 10
    ) -> List[Tuple[PlaylistDB, float]]:
        """Find playlists similar to the given playlist based on title and description."""
        target_playlist = await self.get_by_playlist_id(session, playlist_id)
        if not target_playlist:
            return []

        # Simple similarity based on title words
        # In a real implementation, you'd use more sophisticated text similarity
        title_words = set(target_playlist.title.lower().split())

        if len(title_words) == 0:
            return []

        # Find playlists with similar titles
        all_playlists = await session.execute(
            select(PlaylistDB)
            .where(PlaylistDB.playlist_id != playlist_id)
            .limit(100)  # Limit search space for performance
        )

        similar_playlists = []
        for playlist in all_playlists.scalars().all():
            other_title_words = set(playlist.title.lower().split())
            if other_title_words:
                # Simple Jaccard similarity
                intersection = len(title_words.intersection(other_title_words))
                union = len(title_words.union(other_title_words))
                similarity = intersection / union if union > 0 else 0.0

                if similarity > 0.1:  # Minimum similarity threshold
                    similar_playlists.append((playlist, similarity))

        # Sort by similarity score and return top results
        similar_playlists.sort(key=lambda x: x[1], reverse=True)
        return similar_playlists[:limit]

    async def get_playlist_analytics(self, session: AsyncSession) -> PlaylistAnalytics:
        """Get advanced playlist analytics."""
        # Creation trends by month
        creation_trends_result = await session.execute(
            select(
                func.to_char(PlaylistDB.created_at, "YYYY-MM").label("month"),
                func.count(PlaylistDB.playlist_id).label("count"),
            )
            .group_by(func.to_char(PlaylistDB.created_at, "YYYY-MM"))
            .order_by(func.to_char(PlaylistDB.created_at, "YYYY-MM"))
        )

        creation_trends = {"monthly_counts": [row[1] for row in creation_trends_result]}

        # Content analysis - basic statistics
        content_analysis = {
            "avg_title_length": 0.0,
            "playlists_with_descriptions": 0,
            "most_common_words": [],
        }

        # Get average title length
        avg_title_result = await session.execute(
            select(func.avg(func.length(PlaylistDB.title)))
        )
        avg_title_length = avg_title_result.scalar()
        if avg_title_length:
            content_analysis["avg_title_length"] = float(avg_title_length)

        # Count playlists with descriptions
        desc_count_result = await session.execute(
            select(func.count(PlaylistDB.playlist_id)).where(
                and_(
                    PlaylistDB.description.is_not(None),
                    PlaylistDB.description != "",
                )
            )
        )
        content_analysis["playlists_with_descriptions"] = (
            desc_count_result.scalar() or 0
        )

        # Engagement metrics (simplified - would need actual engagement data)
        engagement_metrics = {
            "avg_videos_per_playlist": 0.0,
            "playlist_creation_rate": 0.0,
        }

        # Get average videos per playlist
        avg_videos_result = await session.execute(
            select(func.avg(PlaylistDB.video_count))
        )
        avg_videos = avg_videos_result.scalar()
        if avg_videos:
            engagement_metrics["avg_videos_per_playlist"] = float(avg_videos)

        # Simple similarity clusters (placeholder)
        similarity_clusters = [
            {
                "cluster_id": "music",
                "playlists": [],
                "common_themes": ["music", "songs", "playlist"],
            },
            {
                "cluster_id": "educational",
                "playlists": [],
                "common_themes": ["tutorial", "learn", "course"],
            },
        ]

        return PlaylistAnalytics(
            creation_trends=creation_trends,
            content_analysis=content_analysis,
            engagement_metrics=engagement_metrics,
            similarity_clusters=similarity_clusters,
        )
