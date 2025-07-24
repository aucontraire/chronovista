"""
Video localization repository implementation.

Provides data access layer for video localizations with full CRUD operations,
multi-language content management, and language analytics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.db.models import VideoLocalization as VideoLocalizationDB
from chronovista.models.enums import LanguageCode
from chronovista.models.video_localization import (
    VideoLocalization,
    VideoLocalizationCreate,
    VideoLocalizationSearchFilters,
    VideoLocalizationStatistics,
    VideoLocalizationUpdate,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository


class VideoLocalizationRepository(
    BaseSQLAlchemyRepository[VideoLocalizationDB, VideoLocalizationCreate, VideoLocalizationUpdate]
):
    """Repository for video localization operations."""

    def __init__(self) -> None:
        super().__init__(VideoLocalizationDB)

    async def get(self, session: AsyncSession, id: Any) -> Optional[VideoLocalizationDB]:
        """Get video localization by composite key tuple (video_id, language_code)."""
        if isinstance(id, tuple) and len(id) == 2:
            video_id, language_code = id
            return await self.get_by_composite_key(session, video_id, language_code)
        return None

    async def exists(self, session: AsyncSession, id: Any) -> bool:
        """Check if video localization exists by composite key tuple (video_id, language_code)."""
        if isinstance(id, tuple) and len(id) == 2:
            video_id, language_code = id
            return await self.exists_by_composite_key(session, video_id, language_code)
        return False

    async def get_by_composite_key(
        self, session: AsyncSession, video_id: str, language_code: str
    ) -> Optional[VideoLocalizationDB]:
        """Get video localization by composite key (video_id, language_code)."""
        result = await session.execute(
            select(VideoLocalizationDB).where(
                and_(
                    VideoLocalizationDB.video_id == video_id,
                    VideoLocalizationDB.language_code == language_code
                )
            )
        )
        return result.scalar_one_or_none()

    async def exists_by_composite_key(
        self, session: AsyncSession, video_id: str, language_code: str
    ) -> bool:
        """Check if video localization exists by composite key."""
        result = await session.execute(
            select(VideoLocalizationDB.video_id).where(
                and_(
                    VideoLocalizationDB.video_id == video_id,
                    VideoLocalizationDB.language_code == language_code
                )
            )
        )
        return result.first() is not None

    async def get_by_video_id(
        self, session: AsyncSession, video_id: str
    ) -> List[VideoLocalizationDB]:
        """Get all localizations for a specific video."""
        result = await session.execute(
            select(VideoLocalizationDB)
            .where(VideoLocalizationDB.video_id == video_id)
            .order_by(VideoLocalizationDB.language_code)
        )
        return list(result.scalars().all())

    async def get_by_language_code(
        self, session: AsyncSession, language_code: str, skip: int = 0, limit: int = 100
    ) -> List[VideoLocalizationDB]:
        """Get all localizations for a specific language."""
        result = await session.execute(
            select(VideoLocalizationDB)
            .where(VideoLocalizationDB.language_code == language_code)
            .order_by(VideoLocalizationDB.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_with_video(
        self, session: AsyncSession, video_id: str, language_code: str
    ) -> Optional[VideoLocalizationDB]:
        """Get video localization with video information loaded."""
        result = await session.execute(
            select(VideoLocalizationDB)
            .options(selectinload(VideoLocalizationDB.video))
            .where(
                and_(
                    VideoLocalizationDB.video_id == video_id,
                    VideoLocalizationDB.language_code == language_code
                )
            )
        )
        return result.scalar_one_or_none()

    async def create_or_update(
        self, session: AsyncSession, localization_create: VideoLocalizationCreate
    ) -> VideoLocalizationDB:
        """Create new video localization or update existing one."""
        existing = await self.get_by_composite_key(
            session, localization_create.video_id, localization_create.language_code
        )

        if existing:
            # Update existing localization
            update_data = VideoLocalizationUpdate(
                localized_title=localization_create.localized_title,
                localized_description=localization_create.localized_description,
            )
            return await self.update(session, db_obj=existing, obj_in=update_data)
        else:
            # Create new localization
            return await self.create(session, obj_in=localization_create)

    async def search_localizations(
        self, session: AsyncSession, filters: VideoLocalizationSearchFilters
    ) -> List[VideoLocalizationDB]:
        """Search video localizations with advanced filters."""
        query = select(VideoLocalizationDB)

        # Apply filters
        conditions: List[Any] = []

        if filters.video_ids:
            conditions.append(VideoLocalizationDB.video_id.in_(filters.video_ids))

        if filters.language_codes:
            conditions.append(VideoLocalizationDB.language_code.in_(filters.language_codes))

        if filters.title_query:
            conditions.append(
                VideoLocalizationDB.localized_title.ilike(f"%{filters.title_query}%")
            )

        if filters.description_query:
            conditions.append(
                VideoLocalizationDB.localized_description.ilike(f"%{filters.description_query}%")
            )

        if filters.has_description is not None:
            if filters.has_description:
                conditions.append(VideoLocalizationDB.localized_description.is_not(None))
                conditions.append(VideoLocalizationDB.localized_description != "")
            else:
                conditions.append(
                    or_(
                        VideoLocalizationDB.localized_description.is_(None),
                        VideoLocalizationDB.localized_description == "",
                    )
                )

        if filters.created_after:
            conditions.append(VideoLocalizationDB.created_at >= filters.created_after)

        if filters.created_before:
            conditions.append(VideoLocalizationDB.created_at <= filters.created_before)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(
            VideoLocalizationDB.video_id, VideoLocalizationDB.language_code
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_supported_languages(
        self, session: AsyncSession, video_id: str
    ) -> List[str]:
        """Get list of languages supported for a specific video."""
        result = await session.execute(
            select(VideoLocalizationDB.language_code)
            .where(VideoLocalizationDB.video_id == video_id)
            .order_by(VideoLocalizationDB.language_code)
        )
        return [row[0] for row in result]

    async def get_videos_by_language(
        self, session: AsyncSession, language_code: str, skip: int = 0, limit: int = 100
    ) -> List[str]:
        """Get list of video IDs that have localizations in a specific language."""
        result = await session.execute(
            select(VideoLocalizationDB.video_id)
            .where(VideoLocalizationDB.language_code == language_code)
            .order_by(VideoLocalizationDB.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return [row[0] for row in result]

    async def get_multilingual_videos(
        self, session: AsyncSession, min_languages: int = 2
    ) -> List[Tuple[str, int]]:
        """Get videos that have localizations in multiple languages."""
        result = await session.execute(
            select(
                VideoLocalizationDB.video_id,
                func.count(VideoLocalizationDB.language_code).label("language_count")
            )
            .group_by(VideoLocalizationDB.video_id)
            .having(func.count(VideoLocalizationDB.language_code) >= min_languages)
            .order_by(desc("language_count"))
        )
        return [(row[0], row[1]) for row in result]

    async def get_language_coverage(
        self, session: AsyncSession
    ) -> Dict[str, int]:
        """Get the number of videos available in each language."""
        result = await session.execute(
            select(
                VideoLocalizationDB.language_code,
                func.count(VideoLocalizationDB.video_id).label("video_count")
            )
            .group_by(VideoLocalizationDB.language_code)
            .order_by(desc("video_count"))
        )
        return {row[0]: row[1] for row in result}

    async def find_missing_localizations(
        self, session: AsyncSession, target_languages: List[str], video_ids: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """Find videos that are missing localizations in target languages."""
        query = select(VideoLocalizationDB.video_id, VideoLocalizationDB.language_code)
        
        if video_ids:
            query = query.where(VideoLocalizationDB.video_id.in_(video_ids))
        
        result = await session.execute(query)
        
        # Build a map of video_id -> available languages
        video_languages: Dict[str, set[str]] = {}
        for video_id, language_code in result:
            if video_id not in video_languages:
                video_languages[video_id] = set()
            video_languages[video_id].add(language_code)
        
        # Find missing languages for each video
        missing_localizations: Dict[str, List[str]] = {}
        for video_id, available_languages in video_languages.items():
            missing_languages = [
                lang for lang in target_languages if lang not in available_languages
            ]
            if missing_languages:
                missing_localizations[video_id] = missing_languages
        
        return missing_localizations

    async def get_localization_statistics(
        self, session: AsyncSession
    ) -> VideoLocalizationStatistics:
        """Get comprehensive video localization statistics."""
        # Basic counts
        total_result = await session.execute(
            select(
                func.count().label("total_localizations"),
                func.count(func.distinct(VideoLocalizationDB.video_id)).label("unique_videos"),
                func.count(func.distinct(VideoLocalizationDB.language_code)).label("unique_languages"),
                func.sum(
                    case(
                        (VideoLocalizationDB.localized_description.is_not(None), 1),
                        else_=0,
                    )
                ).label("videos_with_descriptions"),
            )
        )

        # Calculate average localizations per video separately using subquery
        # First get count of localizations per video, then average those counts
        localization_counts_subquery = (
            select(func.count(VideoLocalizationDB.language_code).label("localization_count"))
            .group_by(VideoLocalizationDB.video_id)
            .subquery()
        )
        
        avg_result = await session.execute(
            select(func.avg(localization_counts_subquery.c.localization_count))
        )

        stats = total_result.first()
        avg_localizations = avg_result.scalar() or 0.0
        
        if not stats:
            return VideoLocalizationStatistics(
                total_localizations=0,
                unique_videos=0,
                unique_languages=0,
                avg_localizations_per_video=0.0,
                videos_with_descriptions=0,
            )

        # Language distribution
        language_result = await session.execute(
            select(
                VideoLocalizationDB.language_code,
                func.count(VideoLocalizationDB.video_id)
            )
            .group_by(VideoLocalizationDB.language_code)
            .order_by(func.count(VideoLocalizationDB.video_id).desc())
            .limit(20)
        )
        top_languages = [(row[0], row[1]) for row in language_result]

        # Language coverage
        coverage_result = await session.execute(
            select(
                VideoLocalizationDB.language_code,
                func.count(VideoLocalizationDB.video_id)
            )
            .group_by(VideoLocalizationDB.language_code)
        )
        localization_coverage = {row[0]: row[1] for row in coverage_result}

        return VideoLocalizationStatistics(
            total_localizations=int(stats.total_localizations or 0),
            unique_videos=int(stats.unique_videos or 0),
            unique_languages=int(stats.unique_languages or 0),
            avg_localizations_per_video=float(avg_localizations),
            top_languages=top_languages,
            localization_coverage=localization_coverage,
            videos_with_descriptions=int(stats.videos_with_descriptions or 0),
        )

    async def bulk_create_localizations(
        self, session: AsyncSession, localizations: List[VideoLocalizationCreate]
    ) -> List[VideoLocalizationDB]:
        """Create multiple video localizations efficiently."""
        created_localizations = []

        for localization_create in localizations:
            # Check if localization already exists
            existing = await self.get_by_composite_key(
                session, localization_create.video_id, localization_create.language_code
            )
            if not existing:
                localization = await self.create(session, obj_in=localization_create)
                created_localizations.append(localization)
            else:
                created_localizations.append(existing)

        return created_localizations

    async def bulk_create_video_localizations(
        self, session: AsyncSession, video_id: str, localizations_data: Dict[str, Dict[str, str]]
    ) -> List[VideoLocalizationDB]:
        """Create multiple localizations for a single video efficiently."""
        created_localizations = []

        for language_code, content in localizations_data.items():
            # Check if localization already exists
            existing = await self.get_by_composite_key(session, video_id, language_code)
            if not existing:
                localization_create = VideoLocalizationCreate(
                    video_id=video_id,
                    language_code=LanguageCode(language_code),
                    localized_title=content.get("title", ""),
                    localized_description=content.get("description"),
                )
                localization = await self.create(session, obj_in=localization_create)
                created_localizations.append(localization)
            else:
                created_localizations.append(existing)

        return created_localizations

    async def delete_by_video_id(
        self, session: AsyncSession, video_id: str
    ) -> int:
        """Delete all localizations for a specific video."""
        # Get count first
        count_result = await session.execute(
            select(func.count()).where(VideoLocalizationDB.video_id == video_id)
        )
        count = count_result.scalar() or 0

        # Delete localizations
        localizations = await self.get_by_video_id(session, video_id)
        for localization in localizations:
            await session.delete(localization)

        await session.flush()
        return count

    async def delete_by_language_code(
        self, session: AsyncSession, language_code: str
    ) -> int:
        """Delete all localizations for a specific language."""
        # Get count first
        count_result = await session.execute(
            select(func.count()).where(VideoLocalizationDB.language_code == language_code)
        )
        count = count_result.scalar() or 0

        # Delete localizations
        localizations = await self.get_by_language_code(session, language_code, limit=1000)
        for localization in localizations:
            await session.delete(localization)

        await session.flush()
        return count

    async def delete_by_composite_key(
        self, session: AsyncSession, video_id: str, language_code: str
    ) -> Optional[VideoLocalizationDB]:
        """Delete video localization by composite key."""
        localization = await self.get_by_composite_key(session, video_id, language_code)
        if localization:
            await session.delete(localization)
            await session.flush()
        return localization

    async def get_preferred_localizations(
        self, session: AsyncSession, video_ids: List[str], preferred_languages: List[str]
    ) -> Dict[str, Optional[VideoLocalizationDB]]:
        """Get preferred localizations for videos based on language preference order."""
        if not video_ids or not preferred_languages:
            return {}

        # Get all localizations for the videos
        result = await session.execute(
            select(VideoLocalizationDB)
            .where(VideoLocalizationDB.video_id.in_(video_ids))
            .order_by(VideoLocalizationDB.video_id, VideoLocalizationDB.language_code)
        )

        # Group localizations by video_id
        video_localizations: Dict[str, List[VideoLocalizationDB]] = {}
        for localization in result.scalars().all():
            if localization.video_id not in video_localizations:
                video_localizations[localization.video_id] = []
            video_localizations[localization.video_id].append(localization)

        # Find preferred localization for each video
        preferred_localizations: Dict[str, Optional[VideoLocalizationDB]] = {}
        for video_id in video_ids:
            localizations = video_localizations.get(video_id, [])
            preferred_localization = None

            # Try to find localization in preferred language order
            for preferred_lang in preferred_languages:
                for localization in localizations:
                    if localization.language_code == preferred_lang:
                        preferred_localization = localization
                        break
                if preferred_localization:
                    break

            # If no preferred language found, use first available
            if not preferred_localization and localizations:
                preferred_localization = localizations[0]

            preferred_localizations[video_id] = preferred_localization

        return preferred_localizations

    async def find_similar_content(
        self, session: AsyncSession, video_id: str, language_code: str, limit: int = 10
    ) -> List[Tuple[VideoLocalizationDB, float]]:
        """Find localizations with similar content based on title similarity."""
        target_localization = await self.get_by_composite_key(session, video_id, language_code)
        if not target_localization:
            return []

        # Get other localizations in the same language
        other_localizations = await session.execute(
            select(VideoLocalizationDB)
            .where(
                and_(
                    VideoLocalizationDB.language_code == language_code,
                    VideoLocalizationDB.video_id != video_id
                )
            )
            .limit(100)  # Limit search space for performance
        )

        # Simple title word-based similarity
        target_words = set(target_localization.localized_title.lower().split())
        if not target_words:
            return []

        similar_localizations = []
        for localization in other_localizations.scalars().all():
            other_words = set(localization.localized_title.lower().split())
            if other_words:
                # Simple Jaccard similarity
                intersection = len(target_words.intersection(other_words))
                union = len(target_words.union(other_words))
                similarity = intersection / union if union > 0 else 0.0

                if similarity > 0.1:  # Minimum similarity threshold
                    similar_localizations.append((localization, similarity))

        # Sort by similarity score and return top results
        similar_localizations.sort(key=lambda x: x[1], reverse=True)
        return similar_localizations[:limit]

    async def get_localization_quality_metrics(
        self, session: AsyncSession
    ) -> Dict[str, Any]:
        """Get quality metrics for localizations (placeholder for future ML analysis)."""
        # Basic quality metrics based on content completeness
        metrics = {
            "completeness_score": 0.0,
            "description_coverage": 0.0,
            "average_title_length": 0.0,
            "language_consistency": {},
        }

        # Get average title length
        title_length_result = await session.execute(
            select(func.avg(func.length(VideoLocalizationDB.localized_title)))
        )
        avg_title_length = title_length_result.scalar()
        if avg_title_length:
            metrics["average_title_length"] = float(avg_title_length)

        # Get description coverage
        desc_coverage_result = await session.execute(
            select(
                func.count().label("total"),
                func.sum(
                    case(
                        (VideoLocalizationDB.localized_description.is_not(None), 1),
                        else_=0,
                    )
                ).label("with_description"),
            )
        )
        coverage_stats = desc_coverage_result.first()
        if coverage_stats and coverage_stats.total > 0:
            metrics["description_coverage"] = float(coverage_stats.with_description / coverage_stats.total)

        return metrics