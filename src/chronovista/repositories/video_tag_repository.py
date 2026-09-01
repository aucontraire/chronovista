"""
Video tag repository implementation.

Provides data access layer for video tags with full CRUD operations,
tag analytics, and video-tag relationship management.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, delete, desc, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.models.enums import AvailabilityStatus
from chronovista.models.video_tag import (
    VideoTagCreate,
    VideoTagSearchFilters,
    VideoTagStatistics,
    VideoTagUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository


class VideoTagRepository(
    BaseSQLAlchemyRepository[
        VideoTagDB, VideoTagCreate, VideoTagUpdate, tuple[str, str]
    ]
):
    """Repository for video tag operations."""

    def __init__(self) -> None:
        super().__init__(VideoTagDB)

    async def get(
        self, session: AsyncSession, id: tuple[str, str]
    ) -> VideoTagDB | None:
        """Get video tag by composite key tuple (video_id, tag)."""
        video_id, tag = id
        return await self.get_by_composite_key(session, video_id, tag)

    async def exists(self, session: AsyncSession, id: tuple[str, str]) -> bool:
        """Check if video tag exists by composite key tuple (video_id, tag)."""
        video_id, tag = id
        return await self.exists_by_composite_key(session, video_id, tag)

    async def get_by_composite_key(
        self, session: AsyncSession, video_id: str, tag: str
    ) -> VideoTagDB | None:
        """Get video tag by composite key (video_id, tag)."""
        result = await session.execute(
            select(VideoTagDB).where(
                and_(VideoTagDB.video_id == video_id, VideoTagDB.tag == tag)
            )
        )
        return result.scalar_one_or_none()

    async def exists_by_composite_key(
        self, session: AsyncSession, video_id: str, tag: str
    ) -> bool:
        """Check if video tag exists by composite key."""
        result = await session.execute(
            select(VideoTagDB.video_id).where(
                and_(VideoTagDB.video_id == video_id, VideoTagDB.tag == tag)
            )
        )
        return result.first() is not None

    async def get_by_video_id(
        self, session: AsyncSession, video_id: str
    ) -> list[VideoTagDB]:
        """Get all tags for a specific video."""
        result = await session.execute(
            select(VideoTagDB)
            .where(VideoTagDB.video_id == video_id)
            .order_by(VideoTagDB.tag_order.nulls_last(), VideoTagDB.tag)
        )
        return list(result.scalars().all())

    async def get_by_tag(self, session: AsyncSession, tag: str) -> list[VideoTagDB]:
        """Get all videos with a specific tag."""
        result = await session.execute(
            select(VideoTagDB)
            .where(VideoTagDB.tag == tag)
            .order_by(VideoTagDB.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_existing_tags(
        self, session: AsyncSession, tags: list[str]
    ) -> set[str]:
        """Return which of the given tag strings exist in any video's tags.

        Used to validate the ``tag`` filter values on the video list endpoint;
        unrecognized tags are dropped with a warning by the caller.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        tags : list[str]
            Candidate tag values.

        Returns
        -------
        set[str]
            The subset of ``tags`` present on at least one video. Empty when
            ``tags`` is empty.
        """
        if not tags:
            return set()
        result = await session.execute(
            select(VideoTagDB.tag).where(VideoTagDB.tag.in_(tags)).distinct()
        )
        return {row[0] for row in result.all()}

    async def list_tags_with_counts(
        self,
        session: AsyncSession,
        *,
        include_unavailable: bool,
        query: str | None,
        offset: int,
        limit: int,
    ) -> tuple[int, list[tuple[str, int]]]:
        """List tags with their video counts, ordered by count descending.

        Aggregates the ``video_tags`` junction joined to ``videos``. When
        ``include_unavailable`` is False, only available videos count. An
        optional ``query`` restricts to tags with a case-insensitive prefix
        match (autocomplete). The total is the distinct-tag count under the same
        filters.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        include_unavailable : bool
            When False, restrict to ``availability_status == AVAILABLE`` videos.
        query : str | None
            Case-insensitive tag prefix filter, or None.
        offset, limit : int
            Pagination window.

        Returns
        -------
        tuple[int, list[tuple[str, int]]]
            The distinct-tag total and the page of ``(tag, video_count)`` rows.
        """
        base = select(
            VideoTagDB.tag,
            func.count(VideoTagDB.video_id).label("video_count"),
        ).join(VideoDB, VideoTagDB.video_id == VideoDB.video_id)
        count_base = (
            select(func.count(func.distinct(VideoTagDB.tag)))
            .select_from(VideoTagDB)
            .join(VideoDB, VideoTagDB.video_id == VideoDB.video_id)
        )
        if not include_unavailable:
            base = base.where(
                VideoDB.availability_status == AvailabilityStatus.AVAILABLE
            )
            count_base = count_base.where(
                VideoDB.availability_status == AvailabilityStatus.AVAILABLE
            )
        if query is not None:
            base = base.where(VideoTagDB.tag.ilike(f"{query}%"))
            count_base = count_base.where(VideoTagDB.tag.ilike(f"{query}%"))

        total = (await session.execute(count_base)).scalar() or 0

        paginated = (
            base.group_by(VideoTagDB.tag)
            .order_by(func.count(VideoTagDB.video_id).desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await session.execute(paginated)).all()
        return total, [(row.tag, row.video_count) for row in rows]

    async def find_fuzzy_candidates(
        self,
        session: AsyncSession,
        *,
        prefix: str,
        substring: str,
        min_len: int,
        max_len: int,
        limit: int,
    ) -> list[str]:
        """Return distinct candidate tags for fuzzy (typo-tolerant) suggestions.

        Narrows to tags of similar length that either share the given prefix or
        contain the substring (both matched case-insensitively), so a Levenshtein
        pass in the caller has a small candidate set to score.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        prefix : str
            Lowercased leading fragment to prefix-match.
        substring : str
            Lowercased fragment to substring-match.
        min_len, max_len : int
            Inclusive tag-length bounds.
        limit : int
            Maximum candidates to return.

        Returns
        -------
        list[str]
            Distinct candidate tag strings.
        """
        result = await session.execute(
            select(VideoTagDB.tag)
            .where(func.length(VideoTagDB.tag) >= min_len)
            .where(func.length(VideoTagDB.tag) <= max_len)
            .where(
                func.lower(VideoTagDB.tag).like(f"{prefix}%")
                | func.lower(VideoTagDB.tag).like(f"%{substring}%")
            )
            .distinct()
            .limit(limit)
        )
        return [row[0] for row in result.all()]

    async def tag_exists(
        self, session: AsyncSession, tag: str, *, include_unavailable: bool
    ) -> bool:
        """Check whether a tag is present on at least one (visible) video.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        tag : str
            Exact tag string.
        include_unavailable : bool
            When False, only available videos count toward existence.

        Returns
        -------
        bool
            True if the tag exists under the filter.
        """
        query = (
            select(VideoTagDB.tag)
            .join(VideoDB, VideoTagDB.video_id == VideoDB.video_id)
            .where(VideoTagDB.tag == tag)
            .limit(1)
        )
        if not include_unavailable:
            query = query.where(
                VideoDB.availability_status == AvailabilityStatus.AVAILABLE
            )
        result = await session.execute(query)
        return result.scalar_one_or_none() is not None

    async def get_tag_with_count(
        self, session: AsyncSession, tag: str, *, include_unavailable: bool
    ) -> tuple[str, int] | None:
        """Get one tag with its video count, or None if absent.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        tag : str
            Exact tag string.
        include_unavailable : bool
            When False, only available videos count.

        Returns
        -------
        tuple[str, int] | None
            ``(tag, video_count)`` or None when the tag has no matching videos.
        """
        query = (
            select(
                VideoTagDB.tag,
                func.count(VideoTagDB.video_id).label("video_count"),
            )
            .join(VideoDB, VideoTagDB.video_id == VideoDB.video_id)
            .where(VideoTagDB.tag == tag)
            .group_by(VideoTagDB.tag)
        )
        if not include_unavailable:
            query = query.where(
                VideoDB.availability_status == AvailabilityStatus.AVAILABLE
            )
        row = (await session.execute(query)).one_or_none()
        if row is None:
            return None
        return row.tag, row.video_count

    async def create_or_update(
        self, session: AsyncSession, tag_create: VideoTagCreate
    ) -> VideoTagDB:
        """Create new video tag or update existing one."""
        existing = await self.get_by_composite_key(
            session, tag_create.video_id, tag_create.tag
        )

        if existing:
            # Update existing tag
            update_data = VideoTagUpdate(tag_order=tag_create.tag_order)
            return await self.update(session, db_obj=existing, obj_in=update_data)
        else:
            # Create new tag
            return await self.create(session, obj_in=tag_create)

    async def bulk_create_video_tags(
        self,
        session: AsyncSession,
        video_id: str,
        tags: list[str],
        tag_orders: list[int] | None = None,
    ) -> list[VideoTagDB]:
        """Create multiple tags for a video efficiently."""
        created_tags = []

        for i, tag in enumerate(tags):
            tag_order = tag_orders[i] if tag_orders and i < len(tag_orders) else None

            # Check if tag already exists
            existing = await self.get_by_composite_key(session, video_id, tag)
            if not existing:
                tag_create = VideoTagCreate(
                    video_id=video_id, tag=tag, tag_order=tag_order
                )
                created_tag = await self.create(session, obj_in=tag_create)
                created_tags.append(created_tag)
            else:
                created_tags.append(existing)

        return created_tags

    async def replace_video_tags(
        self,
        session: AsyncSession,
        video_id: str,
        tags: list[str],
        tag_orders: list[int] | None = None,
    ) -> list[VideoTagDB]:
        """Replace all tags for a video with new ones."""
        # Delete existing tags for this video
        await session.execute(delete(VideoTagDB).where(VideoTagDB.video_id == video_id))

        # Create new tags
        return await self.bulk_create_video_tags(session, video_id, tags, tag_orders)

    async def delete_by_video_id(self, session: AsyncSession, video_id: str) -> int:
        """Delete all tags for a specific video."""
        result = await session.execute(
            select(func.count(VideoTagDB.video_id)).where(
                VideoTagDB.video_id == video_id
            )
        )
        count = result.scalar() or 0

        await session.execute(delete(VideoTagDB).where(VideoTagDB.video_id == video_id))
        await session.flush()

        return count

    async def delete_by_tag(self, session: AsyncSession, tag: str) -> int:
        """Delete all instances of a specific tag across all videos."""
        result = await session.execute(
            select(func.count()).where(VideoTagDB.tag == tag)
        )
        count = result.scalar() or 0

        await session.execute(delete(VideoTagDB).where(VideoTagDB.tag == tag))
        await session.flush()

        return count

    async def search_tags(
        self, session: AsyncSession, filters: VideoTagSearchFilters
    ) -> list[VideoTagDB]:
        """Search video tags with advanced filters."""
        query = select(VideoTagDB)

        # Apply filters
        conditions: list[Any] = []

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

        query = query.order_by(
            VideoTagDB.video_id, VideoTagDB.tag_order.nulls_last(), VideoTagDB.tag
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_popular_tags(
        self, session: AsyncSession, limit: int = 50
    ) -> list[tuple[str, int]]:
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
    ) -> list[tuple[str, int]]:
        """Get tags that frequently appear with the given tag."""
        # Find videos that have the specified tag
        videos_with_tag = select(VideoTagDB.video_id).where(VideoTagDB.tag == tag)

        # Find other tags in those videos
        result = await session.execute(
            select(
                VideoTagDB.tag, func.count(VideoTagDB.video_id).label("co_occurrence")
            )
            .where(
                and_(VideoTagDB.video_id.in_(videos_with_tag), VideoTagDB.tag != tag)
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
        total_result = await session.execute(
            select(func.count()).select_from(VideoTagDB)
        )
        total_tags = total_result.scalar() or 0

        # Unique tags
        unique_result = await session.execute(
            select(func.count(func.distinct(VideoTagDB.tag)))
        )
        unique_tags = unique_result.scalar() or 0

        # Average tags per video - use subquery to avoid nested aggregates
        tag_counts_subquery = (
            select(func.count(VideoTagDB.tag).label("tag_count"))
            .group_by(VideoTagDB.video_id)
            .subquery()
        )
        avg_result = await session.execute(
            select(func.avg(tag_counts_subquery.c.tag_count))
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
        tag_distribution = dict(most_common_tags[:10])

        return VideoTagStatistics(
            total_tags=total_tags,
            unique_tags=unique_tags,
            avg_tags_per_video=avg_tags_per_video,
            most_common_tags=most_common_tags,
            tag_distribution=tag_distribution,
        )

    async def find_videos_by_tags(
        self, session: AsyncSession, tags: list[str], match_all: bool = False
    ) -> list[str]:
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
                select(func.distinct(VideoTagDB.video_id)).where(
                    VideoTagDB.tag.in_(tags)
                )
            )
            return [row[0] for row in result]

    async def get_tag_video_count(self, session: AsyncSession, tag: str) -> int:
        """Get the number of videos that have a specific tag."""
        result = await session.execute(
            select(func.count(func.distinct(VideoTagDB.video_id))).where(
                VideoTagDB.tag == tag
            )
        )
        return result.scalar() or 0

    async def get_video_count_by_tags(
        self, session: AsyncSession, tags: list[str]
    ) -> dict[str, int]:
        """Get video counts for multiple tags efficiently."""
        if not tags:
            return {}

        result = await session.execute(
            select(VideoTagDB.tag, func.count(func.distinct(VideoTagDB.video_id)))
            .where(VideoTagDB.tag.in_(tags))
            .group_by(VideoTagDB.tag)
        )

        return {row[0]: row[1] for row in result}

    async def cleanup_orphaned_tags(self, session: AsyncSession) -> int:
        """Remove tags for videos that no longer exist."""
        # This would require a join with the videos table
        # For now, return 0 as a placeholder
        # In a real implementation, you'd join with the videos table
        # and delete tags where video_id doesn't exist in videos
        return 0

    async def get_distinct_tags_with_counts(
        self, session: AsyncSession
    ) -> list[tuple[str, int]]:
        """
        Retrieve all distinct tags with their occurrence counts.

        Returns all distinct non-NULL tags from the video_tags table,
        grouped and ordered alphabetically by tag value.

        Parameters
        ----------
        session : AsyncSession
            The database session.

        Returns
        -------
        list[tuple[str, int]]
            List of (tag, occurrence_count) tuples ordered by tag.
        """
        result = await session.execute(
            select(
                VideoTagDB.tag,
                func.count(VideoTagDB.tag).label("occurrence_count"),
            )
            .where(VideoTagDB.tag.is_not(None))
            .group_by(VideoTagDB.tag)
            .order_by(VideoTagDB.tag)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_unresolved_tags_with_counts(
        self, session: AsyncSession
    ) -> list[tuple[str, int]]:
        """
        Retrieve tags that have no corresponding entry in ``tag_aliases``.

        Uses a LEFT JOIN anti-pattern: joins ``video_tags`` to ``tag_aliases``
        on ``vt.tag = ta.raw_form`` and filters for rows where the join
        produces NULL (i.e., no alias exists for that tag).

        Parameters
        ----------
        session : AsyncSession
            The database session.

        Returns
        -------
        list[tuple[str, int]]
            List of (tag, occurrence_count) tuples ordered by tag,
            where occurrence_count is the number of distinct video_ids
            with that tag.
        """
        result = await session.execute(
            select(
                VideoTagDB.tag,
                func.count(func.distinct(VideoTagDB.video_id)).label(
                    "occurrence_count"
                ),
            )
            .outerjoin(TagAliasDB, VideoTagDB.tag == TagAliasDB.raw_form)
            .where(TagAliasDB.raw_form.is_(None))
            .group_by(VideoTagDB.tag)
            .order_by(VideoTagDB.tag)
        )
        return [(row[0], row[1]) for row in result.all()]
