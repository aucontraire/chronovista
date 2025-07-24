"""
Video tag repository implementation.

Provides data access layer for video tags with full CRUD operations,
tag analytics, and video-tag relationship management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, desc, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.models.video_tag import (
    VideoTag,
    VideoTagCreate,
    VideoTagSearchFilters,
    VideoTagStatistics,
    VideoTagUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository


class VideoTagRepository(
    BaseSQLAlchemyRepository[VideoTagDB, VideoTagCreate, VideoTagUpdate]
):
    """Repository for video tag operations."""

    def __init__(self) -> None:
        super().__init__(VideoTagDB)

    async def get(self, session: AsyncSession, id: Any) -> Optional[VideoTagDB]:
        """Get video tag by composite key tuple (video_id, tag)."""
        if isinstance(id, tuple) and len(id) == 2:
            video_id, tag = id
            return await self.get_by_composite_key(session, video_id, tag)
        return None

    async def exists(self, session: AsyncSession, id: Any) -> bool:
        """Check if video tag exists by composite key tuple (video_id, tag)."""
        if isinstance(id, tuple) and len(id) == 2:
            video_id, tag = id
            return await self.exists_by_composite_key(session, video_id, tag)
        return False

    async def get_by_composite_key(
        self, session: AsyncSession, video_id: str, tag: str
    ) -> Optional[VideoTagDB]:
        """Get video tag by composite key (video_id, tag)."""
        result = await session.execute(
            select(VideoTagDB).where(
                and_(VideoTagDB.video_id == video_id, VideoTagDB.tag == tag)
            )
        )
        return result.scalar_one_or_none()

    async def exists_by_composite_key(self, session: AsyncSession, video_id: str, tag: str) -> bool:
        """Check if video tag exists by composite key."""
        result = await session.execute(
            select(VideoTagDB.video_id).where(
                and_(VideoTagDB.video_id == video_id, VideoTagDB.tag == tag)
            )
        )
        return result.first() is not None

    async def get_by_video_id(
        self, session: AsyncSession, video_id: str
    ) -> List[VideoTagDB]:
        """Get all tags for a specific video."""
        result = await session.execute(
            select(VideoTagDB)
            .where(VideoTagDB.video_id == video_id)
            .order_by(VideoTagDB.tag_order.nulls_last(), VideoTagDB.tag)
        )
        return list(result.scalars().all())

    async def get_by_tag(
        self, session: AsyncSession, tag: str
    ) -> List[VideoTagDB]:
        """Get all videos with a specific tag."""
        result = await session.execute(
            select(VideoTagDB)
            .where(VideoTagDB.tag == tag)
            .order_by(VideoTagDB.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_or_update(
        self, session: AsyncSession, tag_create: VideoTagCreate
    ) -> VideoTagDB:
        """Create new video tag or update existing one."""
        existing = await self.get_by_composite_key(session, tag_create.video_id, tag_create.tag)
        
        if existing:
            # Update existing tag
            update_data = VideoTagUpdate(tag_order=tag_create.tag_order)
            return await self.update(session, db_obj=existing, obj_in=update_data)
        else:
            # Create new tag
            return await self.create(session, obj_in=tag_create)

    async def bulk_create_video_tags(
        self, session: AsyncSession, video_id: str, tags: List[str], tag_orders: Optional[List[int]] = None
    ) -> List[VideoTagDB]:
        """Create multiple tags for a video efficiently."""
        created_tags = []
        
        for i, tag in enumerate(tags):
            tag_order = tag_orders[i] if tag_orders and i < len(tag_orders) else None
            
            # Check if tag already exists
            existing = await self.get_by_composite_key(session, video_id, tag)
            if not existing:
                tag_create = VideoTagCreate(
                    video_id=video_id,
                    tag=tag,
                    tag_order=tag_order
                )
                created_tag = await self.create(session, obj_in=tag_create)
                created_tags.append(created_tag)
            else:
                created_tags.append(existing)
        
        return created_tags

    async def replace_video_tags(
        self, session: AsyncSession, video_id: str, tags: List[str], tag_orders: Optional[List[int]] = None
    ) -> List[VideoTagDB]:
        """Replace all tags for a video with new ones."""
        # Delete existing tags for this video
        await session.execute(
            delete(VideoTagDB).where(VideoTagDB.video_id == video_id)
        )
        
        # Create new tags
        return await self.bulk_create_video_tags(session, video_id, tags, tag_orders)

    async def delete_by_video_id(
        self, session: AsyncSession, video_id: str
    ) -> int:
        """Delete all tags for a specific video."""
        result = await session.execute(
            select(func.count(VideoTagDB.video_id)).where(VideoTagDB.video_id == video_id)
        )
        count = result.scalar() or 0
        
        await session.execute(
            delete(VideoTagDB).where(VideoTagDB.video_id == video_id)
        )
        await session.flush()
        
        return count

    async def delete_by_tag(
        self, session: AsyncSession, tag: str
    ) -> int:
        """Delete all instances of a specific tag across all videos."""
        result = await session.execute(
            select(func.count()).where(VideoTagDB.tag == tag)
        )
        count = result.scalar() or 0
        
        await session.execute(
            delete(VideoTagDB).where(VideoTagDB.tag == tag)
        )
        await session.flush()
        
        return count

    async def search_tags(
        self, session: AsyncSession, filters: VideoTagSearchFilters
    ) -> List[VideoTagDB]:
        """Search video tags with advanced filters."""
        query = select(VideoTagDB)
        
        # Apply filters
        conditions: List[Any] = []
        
        if filters.video_ids:
            conditions.append(VideoTagDB.video_id.in_(filters.video_ids))
        
        if filters.tags:
            conditions.append(VideoTagDB.tag.in_(filters.tags))
        
        if filters.tag_pattern:
            conditions.append(VideoTagDB.tag.ilike(f"%{filters.tag_pattern}%"))
        
        if filters.min_tag_order is not None:
            conditions.append(VideoTagDB.tag_order >= filters.min_tag_order)
        
        if filters.max_tag_order is not None:
            conditions.append(VideoTagDB.tag_order <= filters.max_tag_order)
        
        if filters.created_after:
            conditions.append(VideoTagDB.created_at >= filters.created_after)
        
        if filters.created_before:
            conditions.append(VideoTagDB.created_at <= filters.created_before)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(VideoTagDB.video_id, VideoTagDB.tag_order.nulls_last(), VideoTagDB.tag)
        
        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_popular_tags(
        self, session: AsyncSession, limit: int = 50
    ) -> List[Tuple[str, int]]:
        """Get most popular tags by video count."""
        result = await session.execute(
            select(VideoTagDB.tag, func.count(VideoTagDB.video_id).label("video_count"))
            .group_by(VideoTagDB.tag)
            .order_by(desc("video_count"))
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result]

    async def get_related_tags(
        self, session: AsyncSession, tag: str, limit: int = 20
    ) -> List[Tuple[str, int]]:
        """Get tags that frequently appear with the given tag."""
        # Find videos that have the specified tag
        videos_with_tag = select(VideoTagDB.video_id).where(VideoTagDB.tag == tag)
        
        # Find other tags in those videos
        result = await session.execute(
            select(VideoTagDB.tag, func.count(VideoTagDB.video_id).label("co_occurrence"))
            .where(
                and_(
                    VideoTagDB.video_id.in_(videos_with_tag),
                    VideoTagDB.tag != tag
                )
            )
            .group_by(VideoTagDB.tag)
            .order_by(desc("co_occurrence"))
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result]

    async def get_video_tag_statistics(
        self, session: AsyncSession
    ) -> VideoTagStatistics:
        """Get comprehensive video tag statistics."""
        # Total tags
        total_result = await session.execute(select(func.count()).select_from(VideoTagDB))
        total_tags = total_result.scalar() or 0
        
        # Unique tags
        unique_result = await session.execute(
            select(func.count(func.distinct(VideoTagDB.tag)))
        )
        unique_tags = unique_result.scalar() or 0
        
        # Average tags per video
        avg_result = await session.execute(
            select(func.avg(func.count(VideoTagDB.tag)))
            .group_by(VideoTagDB.video_id)
        )
        avg_tags_per_video = float(avg_result.scalar() or 0.0)
        
        # Most common tags
        common_result = await session.execute(
            select(VideoTagDB.tag, func.count(VideoTagDB.video_id))
            .group_by(VideoTagDB.tag)
            .order_by(desc(func.count(VideoTagDB.video_id)))
            .limit(20)
        )
        most_common_tags = [(row[0], row[1]) for row in common_result]
        
        # Tag distribution (simplified - could be enhanced)
        tag_distribution = {tag: count for tag, count in most_common_tags[:10]}
        
        return VideoTagStatistics(
            total_tags=total_tags,
            unique_tags=unique_tags,
            avg_tags_per_video=avg_tags_per_video,
            most_common_tags=most_common_tags,
            tag_distribution=tag_distribution
        )

    async def find_videos_by_tags(
        self, session: AsyncSession, tags: List[str], match_all: bool = False
    ) -> List[str]:
        """Find video IDs that have specific tags."""
        if not tags:
            return []
        
        if match_all:
            # Videos must have ALL the specified tags
            # Use a count-based approach: videos that have exactly len(tags) matching tags
            result = await session.execute(
                select(VideoTagDB.video_id)
                .where(VideoTagDB.tag.in_(tags))
                .group_by(VideoTagDB.video_id)
                .having(func.count(func.distinct(VideoTagDB.tag)) == literal(len(tags)))
            )
            return [row[0] for row in result]
        else:
            # Videos that have ANY of the specified tags
            result = await session.execute(
                select(func.distinct(VideoTagDB.video_id))
                .where(VideoTagDB.tag.in_(tags))
            )
            return [row[0] for row in result]

    async def get_tag_video_count(
        self, session: AsyncSession, tag: str
    ) -> int:
        """Get the number of videos that have a specific tag."""
        result = await session.execute(
            select(func.count(func.distinct(VideoTagDB.video_id)))
            .where(VideoTagDB.tag == tag)
        )
        return result.scalar() or 0

    async def get_video_count_by_tags(
        self, session: AsyncSession, tags: List[str]
    ) -> Dict[str, int]:
        """Get video counts for multiple tags efficiently."""
        if not tags:
            return {}
        
        result = await session.execute(
            select(VideoTagDB.tag, func.count(func.distinct(VideoTagDB.video_id)))
            .where(VideoTagDB.tag.in_(tags))
            .group_by(VideoTagDB.tag)
        )
        
        return {row[0]: row[1] for row in result}

    async def cleanup_orphaned_tags(
        self, session: AsyncSession
    ) -> int:
        """Remove tags for videos that no longer exist."""
        # This would require a join with the videos table
        # For now, return 0 as a placeholder
        # In a real implementation, you'd join with the videos table
        # and delete tags where video_id doesn't exist in videos
        return 0