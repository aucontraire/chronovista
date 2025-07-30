"""
Video topic repository implementation.

Provides data access layer for video topics with full CRUD operations,
topic analytics, and video-topic relationship management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, desc, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import VideoTopic as VideoTopicDB
from chronovista.models.video_topic import (
    VideoTopic,
    VideoTopicCreate,
    VideoTopicSearchFilters,
    VideoTopicStatistics,
    VideoTopicUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository


class VideoTopicRepository(
    BaseSQLAlchemyRepository[VideoTopicDB, VideoTopicCreate, VideoTopicUpdate]
):
    """Repository for video topic operations."""

    def __init__(self) -> None:
        super().__init__(VideoTopicDB)

    async def get(self, session: AsyncSession, id: Any) -> Optional[VideoTopicDB]:
        """Get video topic by composite key tuple (video_id, topic_id)."""
        if isinstance(id, tuple) and len(id) == 2:
            video_id, topic_id = id
            return await self.get_by_composite_key(session, video_id, topic_id)
        return None

    async def exists(self, session: AsyncSession, id: Any) -> bool:
        """Check if video topic exists by composite key tuple (video_id, topic_id)."""
        if isinstance(id, tuple) and len(id) == 2:
            video_id, topic_id = id
            return await self.exists_by_composite_key(session, video_id, topic_id)
        return False

    async def get_by_composite_key(
        self, session: AsyncSession, video_id: str, topic_id: str
    ) -> Optional[VideoTopicDB]:
        """Get video topic by composite key (video_id, topic_id)."""
        result = await session.execute(
            select(VideoTopicDB).where(
                and_(
                    VideoTopicDB.video_id == video_id, VideoTopicDB.topic_id == topic_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def exists_by_composite_key(
        self, session: AsyncSession, video_id: str, topic_id: str
    ) -> bool:
        """Check if video topic exists by composite key."""
        result = await session.execute(
            select(VideoTopicDB.video_id).where(
                and_(
                    VideoTopicDB.video_id == video_id, VideoTopicDB.topic_id == topic_id
                )
            )
        )
        return result.first() is not None

    async def get_topics_by_video_id(
        self, session: AsyncSession, video_id: str
    ) -> List[VideoTopicDB]:
        """Get all topics for a specific video."""
        result = await session.execute(
            select(VideoTopicDB)
            .where(VideoTopicDB.video_id == video_id)
            .order_by(VideoTopicDB.relevance_type, VideoTopicDB.topic_id)
        )
        return list(result.scalars().all())

    async def get_videos_by_topic_id(
        self, session: AsyncSession, topic_id: str
    ) -> List[VideoTopicDB]:
        """Get all videos with a specific topic."""
        result = await session.execute(
            select(VideoTopicDB)
            .where(VideoTopicDB.topic_id == topic_id)
            .order_by(VideoTopicDB.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_or_update(
        self, session: AsyncSession, topic_create: VideoTopicCreate
    ) -> VideoTopicDB:
        """Create new video topic or update existing one."""
        existing = await self.get_by_composite_key(
            session, topic_create.video_id, topic_create.topic_id
        )

        if existing:
            # Update existing topic
            update_data = VideoTopicUpdate(relevance_type=topic_create.relevance_type)
            return await self.update(session, db_obj=existing, obj_in=update_data)
        else:
            # Create new topic
            return await self.create(session, obj_in=topic_create)

    async def bulk_create_video_topics(
        self,
        session: AsyncSession,
        video_id: str,
        topic_ids: List[str],
        relevance_types: Optional[List[str]] = None,
    ) -> List[VideoTopicDB]:
        """Create multiple topics for a video efficiently."""
        created_topics = []

        for i, topic_id in enumerate(topic_ids):
            relevance_type = (
                relevance_types[i]
                if relevance_types and i < len(relevance_types)
                else "primary"
            )

            # Check if topic already exists
            existing = await self.get_by_composite_key(session, video_id, topic_id)
            if not existing:
                topic_create = VideoTopicCreate(
                    video_id=video_id, topic_id=topic_id, relevance_type=relevance_type
                )
                created_topic = await self.create(session, obj_in=topic_create)
                created_topics.append(created_topic)
            else:
                created_topics.append(existing)

        return created_topics

    async def replace_video_topics(
        self,
        session: AsyncSession,
        video_id: str,
        topic_ids: List[str],
        relevance_types: Optional[List[str]] = None,
    ) -> List[VideoTopicDB]:
        """Replace all topics for a video with new ones."""
        # Delete existing topics for this video
        await session.execute(
            delete(VideoTopicDB).where(VideoTopicDB.video_id == video_id)
        )

        # Create new topics
        return await self.bulk_create_video_topics(
            session, video_id, topic_ids, relevance_types
        )

    async def delete_by_video_id(self, session: AsyncSession, video_id: str) -> int:
        """Delete all topics for a specific video."""
        result = await session.execute(
            select(func.count(VideoTopicDB.video_id)).where(
                VideoTopicDB.video_id == video_id
            )
        )
        count = result.scalar() or 0

        await session.execute(
            delete(VideoTopicDB).where(VideoTopicDB.video_id == video_id)
        )
        await session.flush()

        return count

    async def delete_by_topic_id(self, session: AsyncSession, topic_id: str) -> int:
        """Delete all instances of a specific topic across all videos."""
        result = await session.execute(
            select(func.count()).where(VideoTopicDB.topic_id == topic_id)
        )
        count = result.scalar() or 0

        await session.execute(
            delete(VideoTopicDB).where(VideoTopicDB.topic_id == topic_id)
        )
        await session.flush()

        return count

    async def search_video_topics(
        self, session: AsyncSession, filters: VideoTopicSearchFilters
    ) -> List[VideoTopicDB]:
        """Search video topics with advanced filters."""
        query = select(VideoTopicDB)

        # Apply filters
        conditions: List[Any] = []

        if filters.video_ids:
            conditions.append(VideoTopicDB.video_id.in_(filters.video_ids))

        if filters.topic_ids:
            conditions.append(VideoTopicDB.topic_id.in_(filters.topic_ids))

        if filters.relevance_types:
            conditions.append(VideoTopicDB.relevance_type.in_(filters.relevance_types))

        if filters.created_after:
            conditions.append(VideoTopicDB.created_at >= filters.created_after)

        if filters.created_before:
            conditions.append(VideoTopicDB.created_at <= filters.created_before)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(
            VideoTopicDB.video_id, VideoTopicDB.relevance_type, VideoTopicDB.topic_id
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_popular_topics(
        self, session: AsyncSession, limit: int = 50
    ) -> List[Tuple[str, int]]:
        """Get most popular topics by video count."""
        result = await session.execute(
            select(
                VideoTopicDB.topic_id,
                func.count(VideoTopicDB.video_id).label("video_count"),
            )
            .group_by(VideoTopicDB.topic_id)
            .order_by(desc("video_count"))
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result]

    async def get_related_topics(
        self, session: AsyncSession, topic_id: str, limit: int = 20
    ) -> List[Tuple[str, int]]:
        """Get topics that frequently appear with the given topic."""
        # Find videos that have the specified topic
        videos_with_topic = select(VideoTopicDB.video_id).where(
            VideoTopicDB.topic_id == topic_id
        )

        # Find other topics in those videos
        result = await session.execute(
            select(
                VideoTopicDB.topic_id,
                func.count(VideoTopicDB.video_id).label("co_occurrence"),
            )
            .where(
                and_(
                    VideoTopicDB.video_id.in_(videos_with_topic),
                    VideoTopicDB.topic_id != topic_id,
                )
            )
            .group_by(VideoTopicDB.topic_id)
            .order_by(desc("co_occurrence"))
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result]

    async def get_video_topic_statistics(
        self, session: AsyncSession
    ) -> VideoTopicStatistics:
        """Get comprehensive video topic statistics."""
        # Total video topics
        total_result = await session.execute(
            select(func.count()).select_from(VideoTopicDB)
        )
        total_video_topics = total_result.scalar() or 0

        # Unique topics
        unique_topics_result = await session.execute(
            select(func.count(func.distinct(VideoTopicDB.topic_id)))
        )
        unique_topics = unique_topics_result.scalar() or 0

        # Unique videos
        unique_videos_result = await session.execute(
            select(func.count(func.distinct(VideoTopicDB.video_id)))
        )
        unique_videos = unique_videos_result.scalar() or 0

        # Average topics per video
        avg_result = await session.execute(
            select(func.avg(func.count(VideoTopicDB.topic_id))).group_by(
                VideoTopicDB.video_id
            )
        )
        avg_topics_per_video = float(avg_result.scalar() or 0.0)

        # Most common topics
        common_result = await session.execute(
            select(VideoTopicDB.topic_id, func.count(VideoTopicDB.video_id))
            .group_by(VideoTopicDB.topic_id)
            .order_by(desc(func.count(VideoTopicDB.video_id)))
            .limit(20)
        )
        most_common_topics = [(row[0], row[1]) for row in common_result]

        # Relevance type distribution
        relevance_result = await session.execute(
            select(VideoTopicDB.relevance_type, func.count()).group_by(
                VideoTopicDB.relevance_type
            )
        )
        relevance_type_distribution = {row[0]: row[1] for row in relevance_result}

        return VideoTopicStatistics(
            total_video_topics=total_video_topics,
            unique_topics=unique_topics,
            unique_videos=unique_videos,
            avg_topics_per_video=avg_topics_per_video,
            most_common_topics=most_common_topics,
            relevance_type_distribution=relevance_type_distribution,
        )

    async def find_videos_by_topics(
        self, session: AsyncSession, topic_ids: List[str], match_all: bool = False
    ) -> List[str]:
        """Find video IDs that have specific topics."""
        if not topic_ids:
            return []

        if match_all:
            # Videos must have ALL the specified topics
            result = await session.execute(
                select(VideoTopicDB.video_id)
                .where(VideoTopicDB.topic_id.in_(topic_ids))
                .group_by(VideoTopicDB.video_id)
                .having(
                    func.count(func.distinct(VideoTopicDB.topic_id))
                    == literal(len(topic_ids))
                )
            )
            return [row[0] for row in result]
        else:
            # Videos that have ANY of the specified topics
            result = await session.execute(
                select(func.distinct(VideoTopicDB.video_id)).where(
                    VideoTopicDB.topic_id.in_(topic_ids)
                )
            )
            return [row[0] for row in result]

    async def get_topic_video_count(self, session: AsyncSession, topic_id: str) -> int:
        """Get the number of videos that have a specific topic."""
        result = await session.execute(
            select(func.count(func.distinct(VideoTopicDB.video_id))).where(
                VideoTopicDB.topic_id == topic_id
            )
        )
        return result.scalar() or 0

    async def get_video_count_by_topics(
        self, session: AsyncSession, topic_ids: List[str]
    ) -> Dict[str, int]:
        """Get video counts for multiple topics efficiently."""
        if not topic_ids:
            return {}

        result = await session.execute(
            select(
                VideoTopicDB.topic_id, func.count(func.distinct(VideoTopicDB.video_id))
            )
            .where(VideoTopicDB.topic_id.in_(topic_ids))
            .group_by(VideoTopicDB.topic_id)
        )

        return {row[0]: row[1] for row in result}

    async def get_topics_by_relevance_type(
        self, session: AsyncSession, relevance_type: str
    ) -> List[VideoTopicDB]:
        """Get all video topics with specific relevance type."""
        result = await session.execute(
            select(VideoTopicDB)
            .where(VideoTopicDB.relevance_type == relevance_type)
            .order_by(VideoTopicDB.created_at.desc())
        )
        return list(result.scalars().all())

    async def cleanup_orphaned_topics(self, session: AsyncSession) -> int:
        """Remove topics for videos that no longer exist."""
        # This would require a join with the videos table
        # For now, return 0 as a placeholder
        # In a real implementation, you'd join with the videos table
        # and delete topics where video_id doesn't exist in videos
        return 0
