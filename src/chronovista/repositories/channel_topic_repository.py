"""
Channel topic repository implementation.

Provides data access layer for channel topics with full CRUD operations,
topic analytics, and channel-topic relationship management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, desc, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import ChannelTopic as ChannelTopicDB
from chronovista.models.channel_topic import (
    ChannelTopic,
    ChannelTopicCreate,
    ChannelTopicSearchFilters,
    ChannelTopicStatistics,
    ChannelTopicUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository


class ChannelTopicRepository(
    BaseSQLAlchemyRepository[ChannelTopicDB, ChannelTopicCreate, ChannelTopicUpdate]
):
    """Repository for channel topic operations."""

    def __init__(self) -> None:
        super().__init__(ChannelTopicDB)

    async def get(self, session: AsyncSession, id: Any) -> Optional[ChannelTopicDB]:
        """Get channel topic by composite key tuple (channel_id, topic_id)."""
        if isinstance(id, tuple) and len(id) == 2:
            channel_id, topic_id = id
            return await self.get_by_composite_key(session, channel_id, topic_id)
        return None

    async def exists(self, session: AsyncSession, id: Any) -> bool:
        """Check if channel topic exists by composite key tuple (channel_id, topic_id)."""
        if isinstance(id, tuple) and len(id) == 2:
            channel_id, topic_id = id
            return await self.exists_by_composite_key(session, channel_id, topic_id)
        return False

    async def get_by_composite_key(
        self, session: AsyncSession, channel_id: str, topic_id: str
    ) -> Optional[ChannelTopicDB]:
        """Get channel topic by composite key (channel_id, topic_id)."""
        result = await session.execute(
            select(ChannelTopicDB).where(
                and_(
                    ChannelTopicDB.channel_id == channel_id,
                    ChannelTopicDB.topic_id == topic_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def exists_by_composite_key(
        self, session: AsyncSession, channel_id: str, topic_id: str
    ) -> bool:
        """Check if channel topic exists by composite key."""
        result = await session.execute(
            select(ChannelTopicDB.channel_id).where(
                and_(
                    ChannelTopicDB.channel_id == channel_id,
                    ChannelTopicDB.topic_id == topic_id,
                )
            )
        )
        return result.first() is not None

    async def get_topics_by_channel_id(
        self, session: AsyncSession, channel_id: str
    ) -> List[ChannelTopicDB]:
        """Get all topics for a specific channel."""
        result = await session.execute(
            select(ChannelTopicDB)
            .where(ChannelTopicDB.channel_id == channel_id)
            .order_by(ChannelTopicDB.topic_id)
        )
        return list(result.scalars().all())

    async def get_channels_by_topic_id(
        self, session: AsyncSession, topic_id: str
    ) -> List[ChannelTopicDB]:
        """Get all channels with a specific topic."""
        result = await session.execute(
            select(ChannelTopicDB)
            .where(ChannelTopicDB.topic_id == topic_id)
            .order_by(ChannelTopicDB.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_or_update(
        self, session: AsyncSession, topic_create: ChannelTopicCreate
    ) -> ChannelTopicDB:
        """Create new channel topic or update existing one."""
        existing = await self.get_by_composite_key(
            session, topic_create.channel_id, topic_create.topic_id
        )

        if existing:
            # Channel topics are typically static, so return existing
            return existing
        else:
            # Create new topic
            return await self.create(session, obj_in=topic_create)

    async def bulk_create_channel_topics(
        self,
        session: AsyncSession,
        channel_id: str,
        topic_ids: List[str],
    ) -> List[ChannelTopicDB]:
        """Create multiple topics for a channel efficiently."""
        created_topics = []

        for topic_id in topic_ids:
            # Check if topic already exists
            existing = await self.get_by_composite_key(session, channel_id, topic_id)
            if not existing:
                topic_create = ChannelTopicCreate(
                    channel_id=channel_id, topic_id=topic_id
                )
                created_topic = await self.create(session, obj_in=topic_create)
                created_topics.append(created_topic)
            else:
                created_topics.append(existing)

        return created_topics

    async def replace_channel_topics(
        self,
        session: AsyncSession,
        channel_id: str,
        topic_ids: List[str],
    ) -> List[ChannelTopicDB]:
        """Replace all topics for a channel with new ones."""
        # Delete existing topics for this channel
        await session.execute(
            delete(ChannelTopicDB).where(ChannelTopicDB.channel_id == channel_id)
        )

        # Create new topics
        return await self.bulk_create_channel_topics(session, channel_id, topic_ids)

    async def delete_by_channel_id(self, session: AsyncSession, channel_id: str) -> int:
        """Delete all topics for a specific channel."""
        result = await session.execute(
            select(func.count(ChannelTopicDB.channel_id)).where(
                ChannelTopicDB.channel_id == channel_id
            )
        )
        count = result.scalar() or 0

        await session.execute(
            delete(ChannelTopicDB).where(ChannelTopicDB.channel_id == channel_id)
        )
        await session.flush()

        return count

    async def delete_by_topic_id(self, session: AsyncSession, topic_id: str) -> int:
        """Delete all instances of a specific topic across all channels."""
        result = await session.execute(
            select(func.count()).where(ChannelTopicDB.topic_id == topic_id)
        )
        count = result.scalar() or 0

        await session.execute(
            delete(ChannelTopicDB).where(ChannelTopicDB.topic_id == topic_id)
        )
        await session.flush()

        return count

    async def search_channel_topics(
        self, session: AsyncSession, filters: ChannelTopicSearchFilters
    ) -> List[ChannelTopicDB]:
        """Search channel topics with advanced filters."""
        query = select(ChannelTopicDB)

        # Apply filters
        conditions: List[Any] = []

        if filters.channel_ids:
            conditions.append(ChannelTopicDB.channel_id.in_(filters.channel_ids))

        if filters.topic_ids:
            conditions.append(ChannelTopicDB.topic_id.in_(filters.topic_ids))

        if filters.created_after:
            conditions.append(ChannelTopicDB.created_at >= filters.created_after)

        if filters.created_before:
            conditions.append(ChannelTopicDB.created_at <= filters.created_before)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(ChannelTopicDB.channel_id, ChannelTopicDB.topic_id)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_popular_topics(
        self, session: AsyncSession, limit: int = 50
    ) -> List[Tuple[str, int]]:
        """Get most popular topics by channel count."""
        result = await session.execute(
            select(
                ChannelTopicDB.topic_id,
                func.count(ChannelTopicDB.channel_id).label("channel_count"),
            )
            .group_by(ChannelTopicDB.topic_id)
            .order_by(desc("channel_count"))
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result]

    async def get_related_topics(
        self, session: AsyncSession, topic_id: str, limit: int = 20
    ) -> List[Tuple[str, int]]:
        """Get topics that frequently appear with the given topic."""
        # Find channels that have the specified topic
        channels_with_topic = select(ChannelTopicDB.channel_id).where(
            ChannelTopicDB.topic_id == topic_id
        )

        # Find other topics in those channels
        result = await session.execute(
            select(
                ChannelTopicDB.topic_id,
                func.count(ChannelTopicDB.channel_id).label("co_occurrence"),
            )
            .where(
                and_(
                    ChannelTopicDB.channel_id.in_(channels_with_topic),
                    ChannelTopicDB.topic_id != topic_id,
                )
            )
            .group_by(ChannelTopicDB.topic_id)
            .order_by(desc("co_occurrence"))
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result]

    async def get_channel_topic_statistics(
        self, session: AsyncSession
    ) -> ChannelTopicStatistics:
        """Get comprehensive channel topic statistics."""
        # Total channel topics
        total_result = await session.execute(
            select(func.count()).select_from(ChannelTopicDB)
        )
        total_channel_topics = total_result.scalar() or 0

        # Unique topics
        unique_topics_result = await session.execute(
            select(func.count(func.distinct(ChannelTopicDB.topic_id)))
        )
        unique_topics = unique_topics_result.scalar() or 0

        # Unique channels
        unique_channels_result = await session.execute(
            select(func.count(func.distinct(ChannelTopicDB.channel_id)))
        )
        unique_channels = unique_channels_result.scalar() or 0

        # Average topics per channel
        avg_result = await session.execute(
            select(func.avg(func.count(ChannelTopicDB.topic_id))).group_by(
                ChannelTopicDB.channel_id
            )
        )
        avg_topics_per_channel = float(avg_result.scalar() or 0.0)

        # Most common topics
        common_result = await session.execute(
            select(ChannelTopicDB.topic_id, func.count(ChannelTopicDB.channel_id))
            .group_by(ChannelTopicDB.topic_id)
            .order_by(desc(func.count(ChannelTopicDB.channel_id)))
            .limit(20)
        )
        most_common_topics = [(row[0], row[1]) for row in common_result]

        # Topic distribution (simplified - could be enhanced)
        topic_distribution = {topic: count for topic, count in most_common_topics[:10]}

        return ChannelTopicStatistics(
            total_channel_topics=total_channel_topics,
            unique_topics=unique_topics,
            unique_channels=unique_channels,
            avg_topics_per_channel=avg_topics_per_channel,
            most_common_topics=most_common_topics,
            topic_distribution=topic_distribution,
        )

    async def find_channels_by_topics(
        self, session: AsyncSession, topic_ids: List[str], match_all: bool = False
    ) -> List[str]:
        """Find channel IDs that have specific topics."""
        if not topic_ids:
            return []

        if match_all:
            # Channels must have ALL the specified topics
            result = await session.execute(
                select(ChannelTopicDB.channel_id)
                .where(ChannelTopicDB.topic_id.in_(topic_ids))
                .group_by(ChannelTopicDB.channel_id)
                .having(
                    func.count(func.distinct(ChannelTopicDB.topic_id))
                    == literal(len(topic_ids))
                )
            )
            return [row[0] for row in result]
        else:
            # Channels that have ANY of the specified topics
            result = await session.execute(
                select(func.distinct(ChannelTopicDB.channel_id)).where(
                    ChannelTopicDB.topic_id.in_(topic_ids)
                )
            )
            return [row[0] for row in result]

    async def get_topic_channel_count(
        self, session: AsyncSession, topic_id: str
    ) -> int:
        """Get the number of channels that have a specific topic."""
        result = await session.execute(
            select(func.count(func.distinct(ChannelTopicDB.channel_id))).where(
                ChannelTopicDB.topic_id == topic_id
            )
        )
        return result.scalar() or 0

    async def get_channel_count_by_topics(
        self, session: AsyncSession, topic_ids: List[str]
    ) -> Dict[str, int]:
        """Get channel counts for multiple topics efficiently."""
        if not topic_ids:
            return {}

        result = await session.execute(
            select(
                ChannelTopicDB.topic_id,
                func.count(func.distinct(ChannelTopicDB.channel_id)),
            )
            .where(ChannelTopicDB.topic_id.in_(topic_ids))
            .group_by(ChannelTopicDB.topic_id)
        )

        return {row[0]: row[1] for row in result}

    async def get_channel_topic_overlap(
        self, session: AsyncSession, channel_id_1: str, channel_id_2: str
    ) -> List[str]:
        """Get common topics between two channels."""
        topics_1 = select(ChannelTopicDB.topic_id).where(
            ChannelTopicDB.channel_id == channel_id_1
        )
        topics_2 = select(ChannelTopicDB.topic_id).where(
            ChannelTopicDB.channel_id == channel_id_2
        )

        result = await session.execute(
            select(ChannelTopicDB.topic_id)
            .where(ChannelTopicDB.topic_id.in_(topics_1))
            .where(ChannelTopicDB.topic_id.in_(topics_2))
            .distinct()
        )
        return [row[0] for row in result]

    async def cleanup_orphaned_topics(self, session: AsyncSession) -> int:
        """Remove topics for channels that no longer exist."""
        # This would require a join with the channels table
        # For now, return 0 as a placeholder
        # In a real implementation, you'd join with the channels table
        # and delete topics where channel_id doesn't exist in channels
        return 0
