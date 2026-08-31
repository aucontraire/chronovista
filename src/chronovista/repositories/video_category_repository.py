"""
Video category repository implementation.

Provides data access layer for YouTube video categories with full CRUD operations
and bulk creation support for seeding.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Video
from chronovista.db.models import VideoCategory as VideoCategoryDB
from chronovista.models.enums import AvailabilityStatus
from chronovista.models.video_category import (
    CategoryVideoCount,
    VideoCategoryCreate,
    VideoCategoryUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository


class VideoCategoryRepository(
    BaseSQLAlchemyRepository[
        VideoCategoryDB, VideoCategoryCreate, VideoCategoryUpdate, str
    ]
):
    """Repository for video category operations."""

    def __init__(self) -> None:
        super().__init__(VideoCategoryDB)

    async def get(
        self, session: AsyncSession, category_id: str
    ) -> VideoCategoryDB | None:
        """
        Get video category by category ID.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        category_id : str
            The YouTube category ID.

        Returns
        -------
        Optional[VideoCategoryDB]
            The video category if found, None otherwise.
        """
        result = await session.execute(
            select(VideoCategoryDB).where(VideoCategoryDB.category_id == category_id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, category_id: str) -> bool:
        """
        Check if video category exists by category ID.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        category_id : str
            The YouTube category ID.

        Returns
        -------
        bool
            True if the category exists, False otherwise.
        """
        result = await session.execute(
            select(VideoCategoryDB.category_id).where(
                VideoCategoryDB.category_id == category_id
            )
        )
        return result.first() is not None

    async def get_all(self, session: AsyncSession) -> list[VideoCategoryDB]:
        """
        Get all video categories.

        Parameters
        ----------
        session : AsyncSession
            The database session.

        Returns
        -------
        List[VideoCategoryDB]
            List of all video categories ordered by name.
        """
        result = await session.execute(
            select(VideoCategoryDB).order_by(VideoCategoryDB.name)
        )
        return list(result.scalars().all())

    @staticmethod
    def _video_count_expr(include_unavailable: bool) -> ColumnElement[int]:
        """Build the FILTERed COUNT of a category's videos (issue #256).

        Counts videos per category with a FILTERed aggregate over a LEFT JOIN
        rather than a per-row correlated subquery: on production data this is
        ~7-13x cheaper (a single hash join + aggregate vs. a subplan re-executed
        per category), and it matches the query shape get_channel_entity_rankings
        deliberately adopted for the same reason. The FILTER — not a WHERE — is
        what lets a LEFT JOIN keep categories whose only videos are unavailable
        (their count becomes 0) rather than dropping them entirely.
        """
        base_count = func.count(Video.video_id)
        if include_unavailable:
            return base_count
        return base_count.filter(
            Video.availability_status == AvailabilityStatus.AVAILABLE
        )

    async def get_with_video_counts(
        self,
        session: AsyncSession,
        *,
        include_unavailable: bool = False,
        only_with_videos: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CategoryVideoCount]:
        """
        Get categories paired with their associated video counts.

        Encapsulates the video-count aggregate that the sidebar and
        category-list endpoints previously built inline (issue #256). The count
        per category comes from a LEFT JOIN over ``Video`` with a FILTERed
        aggregate (see :meth:`_video_count_expr`); results are ordered by video
        count descending (most populated first).

        Parameters
        ----------
        session : AsyncSession
            The database session.
        include_unavailable : bool, optional
            When False (default), only videos with availability status
            AVAILABLE are counted; when True, all videos count.
        only_with_videos : bool, optional
            When True, categories whose count is zero are excluded (the sidebar
            behavior); when False (default), every category is returned.
        limit : int | None, optional
            Maximum number of categories to return; None (default) returns all.
        offset : int, optional
            Number of leading categories to skip (pagination); default 0.

        Returns
        -------
        list[CategoryVideoCount]
            Categories with their video counts, ordered by count descending.
        """
        count_expr = self._video_count_expr(include_unavailable)

        query = (
            select(
                VideoCategoryDB.category_id,
                VideoCategoryDB.name,
                VideoCategoryDB.assignable,
                count_expr.label("video_count"),
            )
            .select_from(VideoCategoryDB)
            .outerjoin(Video, Video.category_id == VideoCategoryDB.category_id)
            .group_by(
                VideoCategoryDB.category_id,
                VideoCategoryDB.name,
                VideoCategoryDB.assignable,
            )
        )
        if only_with_videos:
            query = query.having(count_expr > 0)
        # category_id is a deterministic tiebreak so pagination stays stable when
        # several categories share the same video count (#256).
        query = query.order_by(count_expr.desc(), VideoCategoryDB.category_id)
        if limit is not None:
            # limit/offset paginate AFTER the group-by aggregate: the full LEFT
            # JOIN + aggregate runs before LIMIT. Fine for the small
            # video_categories table; revisit if this shape is copied for a
            # dimension table with many rows (#256).
            query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        return [
            CategoryVideoCount(
                category_id=row.category_id,
                name=row.name,
                assignable=row.assignable,
                video_count=row.video_count or 0,
            )
            for row in result.all()
        ]

    async def get_video_count(
        self,
        session: AsyncSession,
        category_id: str,
        *,
        include_unavailable: bool = False,
    ) -> int:
        """
        Count the videos in a single category (issue #256).

        A single-table aggregate over the indexed ``videos.category_id`` — used
        by the category-detail endpoint, which fetches the category metadata via
        :meth:`get` separately.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        category_id : str
            The YouTube category ID.
        include_unavailable : bool, optional
            When False (default), only AVAILABLE videos are counted.

        Returns
        -------
        int
            The number of videos in the category.
        """
        conditions = [Video.category_id == category_id]
        if not include_unavailable:
            conditions.append(Video.availability_status == AvailabilityStatus.AVAILABLE)
        result = await session.execute(
            select(func.count(Video.video_id)).where(*conditions)
        )
        return result.scalar_one()

    async def get_assignable(self, session: AsyncSession) -> list[VideoCategoryDB]:
        """
        Get only assignable video categories.

        These are categories that creators can assign to their videos.

        Parameters
        ----------
        session : AsyncSession
            The database session.

        Returns
        -------
        List[VideoCategoryDB]
            List of assignable video categories ordered by name.
        """
        result = await session.execute(
            select(VideoCategoryDB)
            .where(VideoCategoryDB.assignable.is_(True))
            .order_by(VideoCategoryDB.name)
        )
        return list(result.scalars().all())

    async def bulk_create(
        self, session: AsyncSession, categories: list[VideoCategoryCreate]
    ) -> list[VideoCategoryDB]:
        """
        Create multiple video categories efficiently.

        This method is primarily used for seeding the database with
        YouTube's predefined video categories. It skips categories
        that already exist.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        categories : List[VideoCategoryCreate]
            List of video category creation objects.

        Returns
        -------
        List[VideoCategoryDB]
            List of created or existing video categories.
        """
        created_categories: list[VideoCategoryDB] = []

        for category_create in categories:
            # Check if category already exists
            existing = await self.get(session, category_create.category_id)
            if not existing:
                category = await self.create(session, obj_in=category_create)
                created_categories.append(category)
            else:
                created_categories.append(existing)

        return created_categories

    async def get_by_category_id(
        self, session: AsyncSession, category_id: str
    ) -> VideoCategoryDB | None:
        """
        Get video category by category ID (alias for get method).

        Parameters
        ----------
        session : AsyncSession
            The database session.
        category_id : str
            The YouTube category ID.

        Returns
        -------
        Optional[VideoCategoryDB]
            The video category if found, None otherwise.
        """
        return await self.get(session, category_id)

    async def create_or_update(
        self, session: AsyncSession, category_create: VideoCategoryCreate
    ) -> VideoCategoryDB:
        """
        Create new video category or update existing one.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        category_create : VideoCategoryCreate
            The video category creation object.

        Returns
        -------
        VideoCategoryDB
            The created or updated video category.
        """
        existing = await self.get(session, category_create.category_id)

        if existing:
            # Update existing category
            update_data = VideoCategoryUpdate(
                name=category_create.name,
                assignable=category_create.assignable,
            )
            return await self.update(session, db_obj=existing, obj_in=update_data)
        else:
            # Create new category
            return await self.create(session, obj_in=category_create)

    async def delete_by_category_id(
        self, session: AsyncSession, category_id: str
    ) -> VideoCategoryDB | None:
        """
        Delete video category by category ID.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        category_id : str
            The YouTube category ID.

        Returns
        -------
        Optional[VideoCategoryDB]
            The deleted video category if found, None otherwise.
        """
        category = await self.get(session, category_id)
        if category:
            await session.delete(category)
            await session.flush()
        return category

    async def find_by_name(
        self, session: AsyncSession, name_query: str
    ) -> list[VideoCategoryDB]:
        """
        Find categories by name (case-insensitive partial match).

        Parameters
        ----------
        session : AsyncSession
            The database session.
        name_query : str
            The partial name to search for.

        Returns
        -------
        List[VideoCategoryDB]
            List of matching video categories ordered by name.
        """
        result = await session.execute(
            select(VideoCategoryDB)
            .where(VideoCategoryDB.name.ilike(f"%{name_query}%"))
            .order_by(VideoCategoryDB.name)
        )
        return list(result.scalars().all())
