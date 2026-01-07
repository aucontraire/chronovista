"""
User video repository.

Provides data access layer for user-video interactions with Google Takeout
integration, watch history tracking, and specialized analytics queries.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import PlaylistMembership as PlaylistMembershipDB
from ..db.models import UserVideo as UserVideoDB
from ..models.user_video import (
    GoogleTakeoutWatchHistoryItem,
    UserVideoCreate,
    UserVideoSearchFilters,
    UserVideoStatistics,
    UserVideoUpdate,
)
from ..models.youtube_types import UserId, VideoId
from .base import BaseSQLAlchemyRepository


class UserVideoRepository(
    BaseSQLAlchemyRepository[
        UserVideoDB,
        UserVideoCreate,
        UserVideoUpdate,
    ]
):
    """Repository for user-video interactions with Google Takeout support."""

    def __init__(self) -> None:
        """Initialize repository with UserVideo model."""
        super().__init__(UserVideoDB)

    async def get(
        self, session: AsyncSession, id: Tuple[str, str]
    ) -> Optional[UserVideoDB]:
        """
        Get user video interaction by composite primary key.

        Parameters
        ----------
        session : AsyncSession
            Database session
        id : Tuple[str, str]
            Composite key (user_id, video_id)

        Returns
        -------
        Optional[UserVideoDB]
            User video interaction if found, None otherwise
        """
        user_id, video_id = id
        result = await session.execute(
            select(UserVideoDB).where(
                and_(
                    UserVideoDB.user_id == user_id,
                    UserVideoDB.video_id == video_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_composite_key(
        self, session: AsyncSession, user_id: UserId, video_id: VideoId
    ) -> Optional[UserVideoDB]:
        """
        Get user video interaction by composite primary key (convenience method).

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        video_id : str
            YouTube video identifier

        Returns
        -------
        Optional[UserVideoDB]
            User video interaction if found, None otherwise
        """
        return await self.get(session, (user_id, video_id))

    async def exists(self, session: AsyncSession, id: Tuple[str, str]) -> bool:
        """
        Check if user video interaction exists.

        Parameters
        ----------
        session : AsyncSession
            Database session
        id : Tuple[str, str]
            Composite key (user_id, video_id)

        Returns
        -------
        bool
            True if interaction exists, False otherwise
        """
        user_id, video_id = id
        result = await session.execute(
            select(UserVideoDB.user_id).where(
                and_(
                    UserVideoDB.user_id == user_id,
                    UserVideoDB.video_id == video_id,
                )
            )
        )
        return result.first() is not None

    async def exists_by_composite_key(
        self, session: AsyncSession, user_id: UserId, video_id: VideoId
    ) -> bool:
        """
        Check if user video interaction exists (convenience method).

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        video_id : str
            YouTube video identifier

        Returns
        -------
        bool
            True if interaction exists, False otherwise
        """
        return await self.exists(session, (user_id, video_id))

    async def get_user_watch_history(
        self,
        session: AsyncSession,
        user_id: UserId,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[UserVideoDB]:
        """
        Get user's watch history ordered by most recent.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        limit : Optional[int]
            Maximum number of results to return
        offset : int
            Number of results to skip

        Returns
        -------
        List[UserVideoDB]
            List of user video interactions ordered by most recent
        """
        query = (
            select(UserVideoDB)
            .where(UserVideoDB.user_id == user_id)
            .order_by(
                UserVideoDB.watched_at.desc().nulls_last(),
                UserVideoDB.created_at.desc(),
            )
            .offset(offset)
        )

        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_user_liked_videos(
        self, session: AsyncSession, user_id: UserId, limit: Optional[int] = None
    ) -> List[UserVideoDB]:
        """
        Get user's liked videos.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        limit : Optional[int]
            Maximum number of results to return

        Returns
        -------
        List[UserVideoDB]
            List of liked video interactions
        """
        query = (
            select(UserVideoDB)
            .where(
                and_(
                    UserVideoDB.user_id == user_id,
                    UserVideoDB.liked.is_(True),
                )
            )
            .order_by(UserVideoDB.watched_at.desc().nulls_last())
        )

        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_most_watched_videos(
        self, session: AsyncSession, user_id: UserId, limit: int = 10
    ) -> List[UserVideoDB]:
        """
        Get user's most watched videos (highest rewatch count).

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        limit : int
            Maximum number of results to return

        Returns
        -------
        List[UserVideoDB]
            List of most watched videos ordered by rewatch count
        """
        result = await session.execute(
            select(UserVideoDB)
            .where(UserVideoDB.user_id == user_id)
            .order_by(
                UserVideoDB.rewatch_count.desc(),
                UserVideoDB.watched_at.desc().nulls_last(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search_user_videos(
        self, session: AsyncSession, filters: UserVideoSearchFilters
    ) -> List[UserVideoDB]:
        """
        Search user video interactions with advanced filtering.

        Parameters
        ----------
        session : AsyncSession
            Database session
        filters : UserVideoSearchFilters
            Search filters to apply

        Returns
        -------
        List[UserVideoDB]
            List of matching user video interactions
        """
        query = select(UserVideoDB)
        conditions: List[Any] = []

        # User ID filters
        if filters.user_ids:
            conditions.append(UserVideoDB.user_id.in_(filters.user_ids))

        # Video ID filters
        if filters.video_ids:
            conditions.append(UserVideoDB.video_id.in_(filters.video_ids))

        # Watch date filters
        if filters.watched_after:
            conditions.append(UserVideoDB.watched_at >= filters.watched_after)

        if filters.watched_before:
            conditions.append(UserVideoDB.watched_at <= filters.watched_before)

        # Action filters
        if filters.liked_only:
            conditions.append(UserVideoDB.liked.is_(True))

        if filters.disliked_only:
            conditions.append(UserVideoDB.disliked.is_(True))

        if filters.playlist_saved_only:
            conditions.append(UserVideoDB.saved_to_playlist.is_(True))

        # Rewatch filters
        if filters.min_rewatch_count is not None:
            conditions.append(UserVideoDB.rewatch_count >= filters.min_rewatch_count)

        # Creation date filters
        if filters.created_after:
            conditions.append(UserVideoDB.created_at >= filters.created_after)

        if filters.created_before:
            conditions.append(UserVideoDB.created_at <= filters.created_before)

        # Apply all conditions
        if conditions:
            query = query.where(and_(*conditions))

        # Default ordering by most recent watch
        query = query.order_by(
            UserVideoDB.watched_at.desc().nulls_last(),
            UserVideoDB.created_at.desc(),
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_user_statistics(
        self, session: AsyncSession, user_id: UserId
    ) -> UserVideoStatistics:
        """
        Get comprehensive statistics for a user's video interactions.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)

        Returns
        -------
        UserVideoStatistics
            User video interaction statistics
        """
        # Get basic counts and aggregates
        result = await session.execute(
            select(
                func.count(UserVideoDB.video_id).label("total_videos"),
                func.sum(func.case((UserVideoDB.liked.is_(True), 1), else_=0)).label(
                    "liked_count"
                ),
                func.sum(func.case((UserVideoDB.disliked.is_(True), 1), else_=0)).label(
                    "disliked_count"
                ),
                func.sum(
                    func.case((UserVideoDB.saved_to_playlist.is_(True), 1), else_=0)
                ).label("playlist_saved_count"),
                func.sum(func.case((UserVideoDB.rewatch_count > 0, 1), else_=0)).label(
                    "rewatch_count"
                ),
                func.count(func.distinct(UserVideoDB.video_id)).label("unique_videos"),
            ).where(UserVideoDB.user_id == user_id)
        )

        stats_row = result.first()
        if not stats_row:
            return UserVideoStatistics(
                total_videos=0,
                liked_count=0,
                disliked_count=0,
                playlist_saved_count=0,
                rewatch_count=0,
                unique_videos=0,
            )

        # Get most active date
        most_watched_result = await session.execute(
            select(
                func.date(UserVideoDB.watched_at).label("watch_date"),
                func.count().label("count"),
            )
            .where(
                and_(
                    UserVideoDB.user_id == user_id, UserVideoDB.watched_at.is_not(None)
                )
            )
            .group_by(func.date(UserVideoDB.watched_at))
            .order_by(desc("count"))
            .limit(1)
        )

        most_watched_row = most_watched_result.first()
        most_watched_date = most_watched_row[0] if most_watched_row else None

        # Calculate watch streak (simplified - consecutive days with activity)
        streak = await self._calculate_watch_streak(session, user_id)

        return UserVideoStatistics(
            total_videos=int(stats_row.total_videos or 0),
            liked_count=int(stats_row.liked_count or 0),
            disliked_count=int(stats_row.disliked_count or 0),
            playlist_saved_count=int(stats_row.playlist_saved_count or 0),
            rewatch_count=int(stats_row.rewatch_count or 0),
            unique_videos=int(stats_row.unique_videos or 0),
            most_watched_date=most_watched_date,
            watch_streak_days=streak,
        )

    async def _calculate_watch_streak(
        self, session: AsyncSession, user_id: UserId
    ) -> int:
        """
        Calculate current consecutive days watching streak.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)

        Returns
        -------
        int
            Number of consecutive days with watch activity
        """
        # Get distinct watch dates for the user, ordered by most recent
        result = await session.execute(
            select(func.date(UserVideoDB.watched_at).label("watch_date"))
            .where(
                and_(
                    UserVideoDB.user_id == user_id, UserVideoDB.watched_at.is_not(None)
                )
            )
            .distinct()
            .order_by(desc("watch_date"))
            .limit(365)  # Look at last year max
        )

        watch_dates = [row.watch_date for row in result]
        if not watch_dates:
            return 0

        # Calculate streak from most recent date
        today = datetime.now().date()
        streak = 0
        current_date = today

        # Start from today or most recent watch date, whichever is earlier
        if watch_dates[0] < today:
            current_date = watch_dates[0]

        for watch_date in watch_dates:
            if watch_date == current_date:
                streak += 1
                current_date = current_date - timedelta(days=1)
            else:
                break

        return streak

    async def import_from_takeout_batch(
        self,
        session: AsyncSession,
        user_id: UserId,
        takeout_items: List[GoogleTakeoutWatchHistoryItem],
    ) -> Dict[str, int]:
        """
        Import watch history from Google Takeout data in batch.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        takeout_items : List[GoogleTakeoutWatchHistoryItem]
            List of Takeout watch history items

        Returns
        -------
        Dict[str, int]
            Import statistics: created, updated, skipped, errors
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
        video_counts: Dict[str, int] = defaultdict(int)

        for item in takeout_items:
            try:
                user_video_create = item.to_user_video_create(user_id)
                if not user_video_create:
                    stats["skipped"] += 1
                    continue

                video_id = user_video_create.video_id
                video_counts[video_id] += 1

                # Check if interaction already exists
                existing = await self.get_by_composite_key(session, user_id, video_id)

                if existing:
                    # Update rewatch count and latest watch time
                    if user_video_create.watched_at and (
                        not existing.watched_at
                        or user_video_create.watched_at > existing.watched_at
                    ):
                        existing.watched_at = user_video_create.watched_at

                    existing.rewatch_count = video_counts[video_id] - 1
                    session.add(existing)
                    stats["updated"] += 1
                else:
                    # Create new interaction
                    # Set rewatch count based on how many times we've seen this video
                    user_video_create.rewatch_count = video_counts[video_id] - 1
                    new_interaction = await self.create(
                        session, obj_in=user_video_create
                    )
                    stats["created"] += 1

            except Exception:
                stats["errors"] += 1
                continue

        return stats

    async def record_watch(
        self,
        session: AsyncSession,
        user_id: UserId,
        video_id: VideoId,
        watched_at: Optional[datetime] = None,
    ) -> UserVideoDB:
        """
        Record or update a watch interaction.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        video_id : str
            YouTube video identifier
        watched_at : Optional[datetime]
            When the video was watched

        Returns
        -------
        UserVideoDB
            Created or updated interaction
        """
        existing = await self.get_by_composite_key(session, user_id, video_id)

        if existing:
            # Update existing interaction
            if watched_at:
                existing.watched_at = watched_at

            # Increment rewatch count if this is a repeat watch
            existing.rewatch_count += 1
            session.add(existing)
            await session.flush()
            await session.refresh(existing)
            return existing
        else:
            # Create new interaction
            new_interaction = UserVideoCreate(
                user_id=user_id,
                video_id=video_id,
                watched_at=watched_at or datetime.now(timezone.utc),
                rewatch_count=0,
            )
            return await self.create(session, obj_in=new_interaction)

    async def delete_user_interactions(
        self, session: AsyncSession, user_id: UserId
    ) -> int:
        """
        Delete all video interactions for a user.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)

        Returns
        -------
        int
            Number of interactions deleted
        """
        result = await session.execute(
            delete(UserVideoDB).where(UserVideoDB.user_id == user_id)
        )
        return result.rowcount

    async def get_watch_count_by_date_range(
        self,
        session: AsyncSession,
        user_id: UserId,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, int]:
        """
        Get watch count aggregated by date within a range.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        start_date : datetime
            Start of date range
        end_date : datetime
            End of date range

        Returns
        -------
        Dict[str, int]
            Video watch count by date (YYYY-MM-DD format)
        """
        result = await session.execute(
            select(
                func.date(UserVideoDB.watched_at).label("watch_date"),
                func.count(UserVideoDB.video_id).label("video_count"),
            )
            .where(
                and_(
                    UserVideoDB.user_id == user_id,
                    UserVideoDB.watched_at >= start_date,
                    UserVideoDB.watched_at <= end_date,
                )
            )
            .group_by(func.date(UserVideoDB.watched_at))
            .order_by("watch_date")
        )

        return {str(row.watch_date): int(row.video_count or 0) for row in result}

    async def sync_saved_to_playlist_flags(self, session: AsyncSession) -> int:
        """
        Sync saved_to_playlist flags based on playlist_memberships table.

        Updates all user_videos records where the video_id exists in
        playlist_memberships to have saved_to_playlist=True.

        Parameters
        ----------
        session : AsyncSession
            Database session

        Returns
        -------
        int
            Number of records updated
        """
        # Subquery to get all video_ids that are in playlists
        videos_in_playlists = (
            select(PlaylistMembershipDB.video_id).distinct().subquery()
        )

        # Update user_videos where video_id is in a playlist
        result = await session.execute(
            update(UserVideoDB)
            .where(
                and_(
                    UserVideoDB.video_id.in_(select(videos_in_playlists)),
                    UserVideoDB.saved_to_playlist.is_(False),
                )
            )
            .values(saved_to_playlist=True)
        )

        return result.rowcount
