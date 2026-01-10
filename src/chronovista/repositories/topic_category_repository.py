"""
Topic category repository implementation.

Provides data access layer for topic categories with full CRUD operations,
hierarchy management, and analytics support.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.db.models import TopicCategory as TopicCategoryDB
from chronovista.models.topic_category import (
    TopicCategory,
    TopicCategoryCreate,
    TopicCategorySearchFilters,
    TopicCategoryStatistics,
    TopicCategoryUpdate,
)
from chronovista.models.youtube_types import TopicId
from chronovista.repositories.base import BaseSQLAlchemyRepository


class TopicCategoryRepository(
    BaseSQLAlchemyRepository[TopicCategoryDB, TopicCategoryCreate, TopicCategoryUpdate, str]
):
    """Repository for topic category operations."""

    def __init__(self) -> None:
        super().__init__(TopicCategoryDB)

    async def get(
        self, session: AsyncSession, topic_id: str
    ) -> Optional[TopicCategoryDB]:
        """Get topic category by topic ID."""
        result = await session.execute(
            select(TopicCategoryDB).where(TopicCategoryDB.topic_id == topic_id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, topic_id: str) -> bool:
        """Check if topic category exists by topic ID."""
        result = await session.execute(
            select(TopicCategoryDB.topic_id).where(TopicCategoryDB.topic_id == topic_id)
        )
        return result.first() is not None

    async def get_by_topic_id(
        self, session: AsyncSession, topic_id: str
    ) -> Optional[TopicCategoryDB]:
        """Get topic category by topic ID (alias for get method)."""
        return await self.get(session, topic_id)

    async def exists_by_topic_id(self, session: AsyncSession, topic_id: str) -> bool:
        """Check if topic category exists by topic ID (alias for exists method)."""
        return await self.exists(session, topic_id)

    async def create_or_update(
        self, session: AsyncSession, topic_create: TopicCategoryCreate
    ) -> TopicCategoryDB:
        """Create new topic category or update existing one."""
        existing = await self.get_by_topic_id(session, topic_create.topic_id)

        if existing:
            # Update existing topic
            update_data = TopicCategoryUpdate(
                category_name=topic_create.category_name,
                parent_topic_id=topic_create.parent_topic_id,
                topic_type=topic_create.topic_type,
            )
            return await self.update(session, db_obj=existing, obj_in=update_data)
        else:
            # Create new topic
            return await self.create(session, obj_in=topic_create)

    async def get_root_topics(self, session: AsyncSession) -> List[TopicCategoryDB]:
        """Get all root topics (topics with no parent)."""
        result = await session.execute(
            select(TopicCategoryDB)
            .where(TopicCategoryDB.parent_topic_id.is_(None))
            .order_by(TopicCategoryDB.category_name)
        )
        return list(result.scalars().all())

    async def get_children(
        self, session: AsyncSession, parent_topic_id: str
    ) -> List[TopicCategoryDB]:
        """Get all child topics for a given parent topic."""
        result = await session.execute(
            select(TopicCategoryDB)
            .where(TopicCategoryDB.parent_topic_id == parent_topic_id)
            .order_by(TopicCategoryDB.category_name)
        )
        return list(result.scalars().all())

    async def get_topic_hierarchy(
        self, session: AsyncSession, topic_id: str, max_depth: Optional[int] = None
    ) -> Optional[TopicCategoryDB]:
        """Get topic with all its descendants loaded."""
        # For now, return the topic itself. Full hierarchy loading would require
        # recursive CTE or multiple queries
        return await self.get_by_topic_id(session, topic_id)

    async def find_by_name(
        self, session: AsyncSession, name_query: str
    ) -> List[TopicCategoryDB]:
        """Find topics by name (case-insensitive partial match)."""
        result = await session.execute(
            select(TopicCategoryDB)
            .where(TopicCategoryDB.category_name.ilike(f"%{name_query}%"))
            .order_by(TopicCategoryDB.category_name)
        )
        return list(result.scalars().all())

    async def find_by_type(
        self, session: AsyncSession, topic_type: str
    ) -> List[TopicCategoryDB]:
        """Find topics by type."""
        result = await session.execute(
            select(TopicCategoryDB)
            .where(TopicCategoryDB.topic_type == topic_type)
            .order_by(TopicCategoryDB.category_name)
        )
        return list(result.scalars().all())

    async def search_topics(
        self, session: AsyncSession, filters: TopicCategorySearchFilters
    ) -> List[TopicCategoryDB]:
        """Search topics with advanced filters."""
        query = select(TopicCategoryDB)

        # Apply filters
        conditions: List[Any] = []

        if filters.topic_ids:
            conditions.append(TopicCategoryDB.topic_id.in_(filters.topic_ids))

        if filters.category_name_query:
            conditions.append(
                TopicCategoryDB.category_name.ilike(f"%{filters.category_name_query}%")
            )

        if filters.parent_topic_ids:
            conditions.append(
                TopicCategoryDB.parent_topic_id.in_(filters.parent_topic_ids)
            )

        if filters.topic_types:
            conditions.append(TopicCategoryDB.topic_type.in_(filters.topic_types))

        if filters.is_root_topic is not None:
            if filters.is_root_topic:
                conditions.append(TopicCategoryDB.parent_topic_id.is_(None))
            else:
                conditions.append(TopicCategoryDB.parent_topic_id.is_not(None))

        if filters.created_after:
            conditions.append(TopicCategoryDB.created_at >= filters.created_after)

        if filters.created_before:
            conditions.append(TopicCategoryDB.created_at <= filters.created_before)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(TopicCategoryDB.category_name)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_topic_statistics(
        self, session: AsyncSession
    ) -> TopicCategoryStatistics:
        """Get comprehensive topic category statistics."""
        # Total topics
        total_result = await session.execute(
            select(func.count(TopicCategoryDB.topic_id))
        )
        total_topics = total_result.scalar() or 0

        # Root topics
        root_result = await session.execute(
            select(func.count(TopicCategoryDB.topic_id)).where(
                TopicCategoryDB.parent_topic_id.is_(None)
            )
        )
        root_topics = root_result.scalar() or 0

        # Topic type distribution
        type_result = await session.execute(
            select(
                TopicCategoryDB.topic_type, func.count(TopicCategoryDB.topic_id)
            ).group_by(TopicCategoryDB.topic_type)
        )
        topic_type_distribution = {row[0]: row[1] for row in type_result}

        # Most popular topics (by name for now - could be enhanced with usage counts)
        popular_result = await session.execute(
            select(TopicCategoryDB.category_name, func.count(TopicCategoryDB.topic_id))
            .group_by(TopicCategoryDB.category_name)
            .order_by(desc(func.count(TopicCategoryDB.topic_id)))
            .limit(10)
        )
        most_popular_topics = [(row[0], row[1]) for row in popular_result]

        # Calculate average children per parent topic
        # Count distinct parents (topics that have children)
        parent_count_result = await session.execute(
            select(func.count(func.distinct(TopicCategoryDB.parent_topic_id))).where(
                TopicCategoryDB.parent_topic_id.isnot(None)
            )
        )
        parent_count = parent_count_result.scalar() or 0

        # Total children (non-root topics)
        child_count = total_topics - root_topics

        # Average children per parent (avoid division by zero)
        avg_children = child_count / parent_count if parent_count > 0 else 0.0

        return TopicCategoryStatistics(
            total_topics=total_topics,
            root_topics=root_topics,
            # Note: Accurate max depth requires recursive CTE; YouTube topics are typically 1-2 levels
            max_hierarchy_depth=1 if child_count > 0 else 0,
            avg_children_per_topic=avg_children,
            topic_type_distribution=topic_type_distribution,
            most_popular_topics=most_popular_topics,
            hierarchy_distribution={0: root_topics, 1: child_count},
        )

    async def delete_by_topic_id(
        self, session: AsyncSession, topic_id: str
    ) -> Optional[TopicCategoryDB]:
        """Delete topic category by topic ID."""
        topic = await self.get_by_topic_id(session, topic_id)
        if topic:
            await session.delete(topic)
            await session.flush()
        return topic

    async def bulk_create(
        self, session: AsyncSession, topics: List[TopicCategoryCreate]
    ) -> List[TopicCategoryDB]:
        """Create multiple topics efficiently."""
        created_topics = []

        for topic_create in topics:
            # Check if topic already exists
            existing = await self.get_by_topic_id(session, topic_create.topic_id)
            if not existing:
                topic = await self.create(session, obj_in=topic_create)
                created_topics.append(topic)
            else:
                created_topics.append(existing)

        return created_topics

    async def get_topic_path(
        self, session: AsyncSession, topic_id: str
    ) -> List[TopicCategoryDB]:
        """Get the path from root to the specified topic."""
        path: List[TopicCategoryDB] = []
        current_topic_id: Optional[str] = topic_id

        # Traverse up the hierarchy
        while current_topic_id:
            topic = await self.get_by_topic_id(session, current_topic_id)
            if not topic:
                break
            path.insert(0, topic)  # Insert at beginning to build path from root
            current_topic_id = topic.parent_topic_id

        return path
