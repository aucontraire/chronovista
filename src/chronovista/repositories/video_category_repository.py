"""
Video category repository implementation.

Provides data access layer for YouTube video categories with full CRUD operations
and bulk creation support for seeding.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import VideoCategory as VideoCategoryDB
from chronovista.models.video_category import (
    VideoCategoryCreate,
    VideoCategoryUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository


class VideoCategoryRepository(
    BaseSQLAlchemyRepository[VideoCategoryDB, VideoCategoryCreate, VideoCategoryUpdate, str]
):
    """Repository for video category operations."""

    def __init__(self) -> None:
        super().__init__(VideoCategoryDB)

    async def get(
        self, session: AsyncSession, category_id: str
    ) -> Optional[VideoCategoryDB]:
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

    async def get_all(self, session: AsyncSession) -> List[VideoCategoryDB]:
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

    async def get_assignable(self, session: AsyncSession) -> List[VideoCategoryDB]:
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
        self, session: AsyncSession, categories: List[VideoCategoryCreate]
    ) -> List[VideoCategoryDB]:
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
        created_categories: List[VideoCategoryDB] = []

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
    ) -> Optional[VideoCategoryDB]:
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
    ) -> Optional[VideoCategoryDB]:
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
    ) -> List[VideoCategoryDB]:
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
