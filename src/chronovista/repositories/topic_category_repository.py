"""
Topic category repository implementation.

Provides data access layer for topic categories with full CRUD operations,
hierarchy management, and analytics support.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import ScalarSelect, and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import ChannelTopic, VideoTopic
from chronovista.db.models import TopicCategory as TopicCategoryDB
from chronovista.models.topic_category import (
    TopicCategoryCreate,
    TopicCategorySearchFilters,
    TopicCategoryStatistics,
    TopicCategoryUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository


class TopicCategoryRepository(
    BaseSQLAlchemyRepository[
        TopicCategoryDB, TopicCategoryCreate, TopicCategoryUpdate, str
    ]
):
    """Repository for topic category operations."""

    def __init__(self) -> None:
        super().__init__(TopicCategoryDB)

    async def get(self, session: AsyncSession, topic_id: str) -> TopicCategoryDB | None:
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
    ) -> TopicCategoryDB | None:
        """Get topic category by topic ID (alias for get method)."""
        return await self.get(session, topic_id)

    async def exists_by_topic_id(self, session: AsyncSession, topic_id: str) -> bool:
        """Check if topic category exists by topic ID (alias for exists method)."""
        return await self.exists(session, topic_id)

    async def get_by_topic_ids(
        self, session: AsyncSession, topic_ids: Iterable[str]
    ) -> list[TopicCategoryDB]:
        """Get topic categories for a set of topic IDs in one query.

        Used to bulk-load ancestor topics when assembling a topic's path.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        topic_ids : Iterable[str]
            Topic IDs to fetch.

        Returns
        -------
        list[TopicCategoryDB]
            Matching topic categories. Empty when ``topic_ids`` is empty.
        """
        ids = list(topic_ids)
        if not ids:
            return []
        result = await session.execute(
            select(TopicCategoryDB).where(TopicCategoryDB.topic_id.in_(ids))
        )
        return list(result.scalars().all())

    async def get_existing_topic_ids(
        self, session: AsyncSession, topic_ids: Iterable[str]
    ) -> set[str]:
        """Return which of the given topic IDs exist, in one query.

        Used to validate the ``topic_id`` filter values on the video list
        endpoint; unrecognized ids are dropped with a warning by the caller.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        topic_ids : Iterable[str]
            Candidate topic IDs.

        Returns
        -------
        set[str]
            The subset of ``topic_ids`` that exist. Empty when ``topic_ids``
            is empty.
        """
        ids = list(topic_ids)
        if not ids:
            return set()
        result = await session.execute(
            select(TopicCategoryDB.topic_id)
            .where(TopicCategoryDB.topic_id.in_(ids))
            .distinct()
        )
        return {row[0] for row in result.all()}

    @staticmethod
    def _video_count_subq() -> ScalarSelect[int]:
        """Per-topic video-count correlated scalar subquery.

        A correlated subquery (not a LEFT JOIN + GROUP BY) because each topic
        needs two INDEPENDENT aggregates — videos and channels — and joining
        both dimensions in one query would fan out the counts. TopicCategory is
        a small taxonomy table, so per-row subquery execution is cheap here.
        """
        return (
            select(func.count(VideoTopic.video_id))
            .where(VideoTopic.topic_id == TopicCategoryDB.topic_id)
            .correlate(TopicCategoryDB)
            .scalar_subquery()
        )

    @staticmethod
    def _channel_count_subq() -> ScalarSelect[int]:
        """Per-topic channel-count correlated scalar subquery.

        See :meth:`_video_count_subq` for why this is a correlated subquery.
        """
        return (
            select(func.count(ChannelTopic.channel_id))
            .where(ChannelTopic.topic_id == TopicCategoryDB.topic_id)
            .correlate(TopicCategoryDB)
            .scalar_subquery()
        )

    async def list_with_counts(
        self, session: AsyncSession, *, offset: int, limit: int
    ) -> tuple[int, list[tuple[TopicCategoryDB, int, int]]]:
        """List topics with per-topic video and channel counts.

        Ordered by video count descending. Returns ``(total, rows)`` where each
        row is ``(topic, video_count, channel_count)`` and ``total`` is the full
        topic count before pagination.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        offset, limit : int
            Pagination window.

        Returns
        -------
        tuple[int, list[tuple[TopicCategoryDB, int, int]]]
            The total topic count and the paginated rows.
        """
        video_count_subq = self._video_count_subq()
        channel_count_subq = self._channel_count_subq()

        total_result = await session.execute(
            select(func.count()).select_from(TopicCategoryDB)
        )
        total = total_result.scalar() or 0

        query = (
            select(
                TopicCategoryDB,
                video_count_subq.label("video_count"),
                channel_count_subq.label("channel_count"),
            )
            .order_by(video_count_subq.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(query)
        rows = [(row[0], row[1] or 0, row[2] or 0) for row in result.all()]
        return total, rows

    async def get_with_counts(
        self, session: AsyncSession, topic_id: str
    ) -> tuple[TopicCategoryDB, int, int] | None:
        """Get one topic with its video and channel counts.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        topic_id : str
            Topic identifier.

        Returns
        -------
        tuple[TopicCategoryDB, int, int] | None
            ``(topic, video_count, channel_count)`` or None if not found.
        """
        query = select(
            TopicCategoryDB,
            self._video_count_subq().label("video_count"),
            self._channel_count_subq().label("channel_count"),
        ).where(TopicCategoryDB.topic_id == topic_id)
        row = (await session.execute(query)).one_or_none()
        if row is None:
            return None
        return row[0], row[1] or 0, row[2] or 0

    async def list_hierarchy_with_counts(
        self,
        session: AsyncSession,
        *,
        min_video_count: int,
        include_empty: bool,
    ) -> list[tuple[TopicCategoryDB, int]]:
        """List topics with video counts for hierarchy building.

        Ordered by topic name (the caller computes depth/paths in Python).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        min_video_count : int
            Minimum video count to include a topic (0 disables the floor).
        include_empty : bool
            When False, topics with zero videos are excluded.

        Returns
        -------
        list[tuple[TopicCategoryDB, int]]
            ``(topic, video_count)`` rows ordered by ``category_name``.
        """
        video_count_subq = self._video_count_subq()
        query = select(TopicCategoryDB, video_count_subq.label("video_count"))
        if not include_empty:
            query = query.where(video_count_subq > 0)
        if min_video_count > 0:
            query = query.where(video_count_subq >= min_video_count)
        query = query.order_by(TopicCategoryDB.category_name)
        result = await session.execute(query)
        return [(row[0], row[1] or 0) for row in result.all()]

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

    async def get_root_topics(self, session: AsyncSession) -> list[TopicCategoryDB]:
        """Get all root topics (topics with no parent)."""
        result = await session.execute(
            select(TopicCategoryDB)
            .where(TopicCategoryDB.parent_topic_id.is_(None))
            .order_by(TopicCategoryDB.category_name)
        )
        return list(result.scalars().all())

    async def get_children(
        self, session: AsyncSession, parent_topic_id: str
    ) -> list[TopicCategoryDB]:
        """Get all child topics for a given parent topic."""
        result = await session.execute(
            select(TopicCategoryDB)
            .where(TopicCategoryDB.parent_topic_id == parent_topic_id)
            .order_by(TopicCategoryDB.category_name)
        )
        return list(result.scalars().all())

    async def get_topic_hierarchy(
        self, session: AsyncSession, topic_id: str, max_depth: int | None = None
    ) -> TopicCategoryDB | None:
        """Get topic with all its descendants loaded."""
        # For now, return the topic itself. Full hierarchy loading would require
        # recursive CTE or multiple queries
        return await self.get_by_topic_id(session, topic_id)

    async def find_by_name(
        self, session: AsyncSession, name_query: str
    ) -> list[TopicCategoryDB]:
        """Find topics by name (case-insensitive partial match)."""
        result = await session.execute(
            select(TopicCategoryDB)
            .where(TopicCategoryDB.category_name.ilike(f"%{name_query}%"))
            .order_by(TopicCategoryDB.category_name)
        )
        return list(result.scalars().all())

    async def find_by_type(
        self, session: AsyncSession, topic_type: str
    ) -> list[TopicCategoryDB]:
        """Find topics by type."""
        result = await session.execute(
            select(TopicCategoryDB)
            .where(TopicCategoryDB.topic_type == topic_type)
            .order_by(TopicCategoryDB.category_name)
        )
        return list(result.scalars().all())

    async def search_topics(
        self, session: AsyncSession, filters: TopicCategorySearchFilters
    ) -> list[TopicCategoryDB]:
        """Search topics with advanced filters."""
        query = select(TopicCategoryDB)

        # Apply filters
        conditions: list[Any] = []

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
    ) -> TopicCategoryDB | None:
        """Delete topic category by topic ID."""
        topic = await self.get_by_topic_id(session, topic_id)
        if topic:
            await session.delete(topic)
            await session.flush()
        return topic

    async def bulk_create(
        self, session: AsyncSession, topics: list[TopicCategoryCreate]
    ) -> list[TopicCategoryDB]:
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
    ) -> list[TopicCategoryDB]:
        """Get the path from root to the specified topic."""
        path: list[TopicCategoryDB] = []
        current_topic_id: str | None = topic_id

        # Traverse up the hierarchy
        while current_topic_id:
            topic = await self.get_by_topic_id(session, current_topic_id)
            if not topic:
                break
            path.insert(0, topic)  # Insert at beginning to build path from root
            current_topic_id = topic.parent_topic_id

        return path
