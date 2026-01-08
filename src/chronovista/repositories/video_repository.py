"""
Video repository for enhanced video operations with language support.

Handles CRUD operations and queries for YouTube videos with multi-language
capabilities and content restrictions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chronovista.db.models import Channel
from chronovista.db.models import Video as VideoDB
from chronovista.models.video import (
    VideoCreate,
    VideoSearchFilters,
    VideoStatistics,
    VideoUpdate,
    VideoWithChannel,
)
from chronovista.models.youtube_types import ChannelId, VideoId
from chronovista.repositories.base import BaseSQLAlchemyRepository


class VideoRepository(
    BaseSQLAlchemyRepository[
        VideoDB,
        VideoCreate,
        VideoUpdate,
    ]
):
    """Repository for YouTube video management with multi-language support."""

    def __init__(self) -> None:
        """Initialize repository with Video model."""
        super().__init__(VideoDB)

    async def get(self, session: AsyncSession, id: VideoId) -> Optional[VideoDB]:
        """Get video by video_id (primary key)."""
        return await self.get_by_video_id(session, id)

    async def exists(self, session: AsyncSession, id: VideoId) -> bool:
        """Check if video exists by video_id."""
        return await self.exists_by_video_id(session, id)

    async def get_by_video_id(
        self, session: AsyncSession, video_id: VideoId
    ) -> Optional[VideoDB]:
        """
        Get video by YouTube video ID.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier

        Returns
        -------
        Optional[VideoDB]
            Video if found, None otherwise
        """
        result = await session.execute(
            select(VideoDB).where(VideoDB.video_id == video_id)
        )
        return result.scalar_one_or_none()

    async def exists_by_video_id(
        self, session: AsyncSession, video_id: VideoId
    ) -> bool:
        """
        Check if video exists by video ID.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier

        Returns
        -------
        bool
            True if video exists, False otherwise
        """
        result = await session.execute(
            select(VideoDB.video_id).where(VideoDB.video_id == video_id)
        )
        return result.first() is not None

    async def get_multi(
        self, session: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> List[VideoDB]:
        """
        Get multiple videos with pagination, excluding deleted videos.

        Parameters
        ----------
        session : AsyncSession
            Database session
        skip : int
            Number of results to skip
        limit : int
            Maximum number of results to return

        Returns
        -------
        List[VideoDB]
            List of videos ordered by upload date
        """
        result = await session.execute(
            select(VideoDB)
            .where(VideoDB.deleted_flag.is_(False))
            .order_by(VideoDB.upload_date.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find_by_channel(
        self,
        session: AsyncSession,
        channel_id: ChannelId,
        skip: int = 0,
        limit: int = 50,
    ) -> List[VideoDB]:
        """
        Find videos by channel with pagination.

        Parameters
        ----------
        session : AsyncSession
            Database session
        channel_id : str
            Channel identifier
        skip : int
            Number of results to skip
        limit : int
            Maximum number of results to return

        Returns
        -------
        List[VideoDB]
            List of videos from the channel
        """
        result = await session.execute(
            select(VideoDB)
            .where(
                and_(VideoDB.channel_id == channel_id, VideoDB.deleted_flag.is_(False))
            )
            .order_by(VideoDB.upload_date.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find_by_language(
        self, session: AsyncSession, language: str
    ) -> List[VideoDB]:
        """
        Find videos by default language.

        Parameters
        ----------
        session : AsyncSession
            Database session
        language : str
            Language code (BCP-47)

        Returns
        -------
        List[VideoDB]
            List of videos in the specified language
        """
        language_normalized = language.lower()
        result = await session.execute(
            select(VideoDB)
            .where(
                and_(
                    or_(
                        VideoDB.default_language == language_normalized,
                        VideoDB.default_audio_language == language_normalized,
                    ),
                    VideoDB.deleted_flag.is_(False),
                )
            )
            .order_by(VideoDB.upload_date.desc())
        )
        return list(result.scalars().all())

    async def find_available_in_language(
        self, session: AsyncSession, language: str
    ) -> List[VideoDB]:
        """
        Find videos that have content available in specified language.

        Parameters
        ----------
        session : AsyncSession
            Database session
        language : str
            Language code (BCP-47)

        Returns
        -------
        List[VideoDB]
            List of videos available in the language
        """
        result = await session.execute(
            select(VideoDB)
            .where(
                and_(
                    VideoDB.available_languages.op("@>")([language.lower()]),
                    VideoDB.deleted_flag.is_(False),
                )
            )
            .order_by(VideoDB.upload_date.desc())
        )
        return list(result.scalars().all())

    async def find_made_for_kids(
        self, session: AsyncSession, made_for_kids: bool = True
    ) -> List[VideoDB]:
        """
        Find videos filtered by made-for-kids status.

        Parameters
        ----------
        session : AsyncSession
            Database session
        made_for_kids : bool
            Whether to find kids-friendly videos

        Returns
        -------
        List[VideoDB]
            List of videos matching kids-friendly criteria
        """
        result = await session.execute(
            select(VideoDB)
            .where(
                and_(
                    or_(
                        VideoDB.made_for_kids.is_(made_for_kids),
                        VideoDB.self_declared_made_for_kids.is_(made_for_kids),
                    ),
                    VideoDB.deleted_flag.is_(False),
                )
            )
            .order_by(VideoDB.upload_date.desc())
        )
        return list(result.scalars().all())

    async def find_by_date_range(
        self,
        session: AsyncSession,
        start_date: datetime,
        end_date: datetime,
    ) -> List[VideoDB]:
        """
        Find videos uploaded within date range.

        Parameters
        ----------
        session : AsyncSession
            Database session
        start_date : datetime
            Start of date range
        end_date : datetime
            End of date range

        Returns
        -------
        List[VideoDB]
            List of videos uploaded in the date range
        """
        result = await session.execute(
            select(VideoDB)
            .where(
                and_(
                    VideoDB.upload_date >= start_date,
                    VideoDB.upload_date <= end_date,
                    VideoDB.deleted_flag.is_(False),
                )
            )
            .order_by(VideoDB.upload_date.desc())
        )
        return list(result.scalars().all())

    async def get_with_transcripts(
        self, session: AsyncSession, video_id: VideoId
    ) -> Optional[VideoDB]:
        """
        Get video with all transcripts loaded.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier

        Returns
        -------
        Optional[VideoDB]
            Video with transcripts loaded if found
        """
        result = await session.execute(
            select(VideoDB)
            .options(selectinload(VideoDB.transcripts))
            .where(VideoDB.video_id == video_id)
        )
        return result.scalar_one_or_none()

    async def get_with_channel(
        self, session: AsyncSession, video_id: VideoId
    ) -> Optional[VideoDB]:
        """
        Get video with channel information loaded.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            YouTube video identifier

        Returns
        -------
        Optional[VideoDB]
            Video with channel loaded if found
        """
        result = await session.execute(
            select(VideoDB)
            .options(selectinload(VideoDB.channel))
            .where(VideoDB.video_id == video_id)
        )
        return result.scalar_one_or_none()

    async def search_videos(
        self, session: AsyncSession, filters: VideoSearchFilters
    ) -> List[VideoDB]:
        """
        Search videos with advanced filtering.

        Parameters
        ----------
        session : AsyncSession
            Database session
        filters : VideoSearchFilters
            Search filters to apply

        Returns
        -------
        List[VideoDB]
            List of matching videos
        """
        query = select(VideoDB)
        conditions: List[Any] = []

        # Exclude deleted videos by default
        if filters.exclude_deleted:
            conditions.append(VideoDB.deleted_flag.is_(False))

        # Channel filters
        if filters.channel_ids:
            conditions.append(VideoDB.channel_id.in_(filters.channel_ids))

        # Text search in title
        if filters.title_query:
            conditions.append(VideoDB.title.ilike(f"%{filters.title_query}%"))

        # Text search in description
        if filters.description_query:
            conditions.append(
                VideoDB.description.ilike(f"%{filters.description_query}%")
            )

        # Language filters
        if filters.language_codes:
            language_conditions = []
            for lang in filters.language_codes:
                lang_normalized = lang.lower()
                language_conditions.extend(
                    [
                        VideoDB.default_language == lang_normalized,
                        VideoDB.default_audio_language == lang_normalized,
                        VideoDB.available_languages.op("@>")([lang_normalized]),
                    ]
                )
            conditions.append(or_(*language_conditions))

        # Date filters
        if filters.upload_after:
            conditions.append(VideoDB.upload_date >= filters.upload_after)

        if filters.upload_before:
            conditions.append(VideoDB.upload_date <= filters.upload_before)

        # Duration filters
        if filters.min_duration is not None:
            conditions.append(VideoDB.duration >= filters.min_duration)

        if filters.max_duration is not None:
            conditions.append(VideoDB.duration <= filters.max_duration)

        # View count filters
        if filters.min_view_count is not None:
            conditions.append(VideoDB.view_count >= filters.min_view_count)

        if filters.max_view_count is not None:
            conditions.append(VideoDB.view_count <= filters.max_view_count)

        # Like count filters
        if filters.min_like_count is not None:
            conditions.append(VideoDB.like_count >= filters.min_like_count)

        # Kids-friendly filter
        if filters.kids_friendly_only is not None:
            if filters.kids_friendly_only:
                conditions.append(
                    or_(
                        VideoDB.made_for_kids.is_(True),
                        VideoDB.self_declared_made_for_kids.is_(True),
                    )
                )
            else:
                conditions.append(
                    and_(
                        VideoDB.made_for_kids.is_(False),
                        VideoDB.self_declared_made_for_kids.is_(False),
                    )
                )

        # Transcripts filter
        if filters.has_transcripts is not None:
            if filters.has_transcripts:
                # Has transcripts - use exists subquery
                from chronovista.db.models import VideoTranscript

                transcript_exists = (
                    select(VideoTranscript.video_id)
                    .where(VideoTranscript.video_id == VideoDB.video_id)
                    .exists()
                )
                conditions.append(transcript_exists)
            else:
                # No transcripts - use not exists
                from chronovista.db.models import VideoTranscript

                transcript_exists = (
                    select(VideoTranscript.video_id)
                    .where(VideoTranscript.video_id == VideoDB.video_id)
                    .exists()
                )
                conditions.append(~transcript_exists)

        # Apply all conditions
        if conditions:
            query = query.where(and_(*conditions))

        # Default ordering by upload date
        query = query.order_by(VideoDB.upload_date.desc())

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_popular_videos(
        self, session: AsyncSession, limit: int = 10, days_back: int = 30
    ) -> List[VideoDB]:
        """
        Get most popular videos by view count from recent period.

        Parameters
        ----------
        session : AsyncSession
            Database session
        limit : int
            Maximum number of results to return
        days_back : int
            Number of days to look back

        Returns
        -------
        List[VideoDB]
            List of popular videos by view count
        """
        cutoff_date = datetime.now() - timedelta(days=days_back)

        result = await session.execute(
            select(VideoDB)
            .where(
                and_(
                    VideoDB.upload_date >= cutoff_date,
                    VideoDB.view_count.is_not(None),
                    VideoDB.deleted_flag.is_(False),
                )
            )
            .order_by(VideoDB.view_count.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find_deleted_videos(self, session: AsyncSession) -> List[VideoDB]:
        """
        Find videos marked as deleted.

        Parameters
        ----------
        session : AsyncSession
            Database session

        Returns
        -------
        List[VideoDB]
            List of deleted videos
        """
        result = await session.execute(
            select(VideoDB)
            .where(VideoDB.deleted_flag.is_(True))
            .order_by(VideoDB.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_or_update(
        self, session: AsyncSession, video_data: VideoCreate
    ) -> VideoDB:
        """
        Create a new video or update existing one.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_data : VideoCreate
            Video data to create or update

        Returns
        -------
        VideoDB
            Created or updated video
        """
        existing = await self.get_by_video_id(session, video_data.video_id)

        if existing:
            # Update existing video
            update_data = VideoUpdate(
                title=video_data.title,
                description=video_data.description,
                duration=video_data.duration,
                made_for_kids=video_data.made_for_kids,
                self_declared_made_for_kids=video_data.self_declared_made_for_kids,
                default_language=video_data.default_language,
                default_audio_language=video_data.default_audio_language,
                available_languages=video_data.available_languages,
                region_restriction=video_data.region_restriction,
                content_rating=video_data.content_rating,
                like_count=video_data.like_count,
                view_count=video_data.view_count,
                comment_count=video_data.comment_count,
                deleted_flag=video_data.deleted_flag,
            )
            return await self.update(session, db_obj=existing, obj_in=update_data)
        else:
            # Create new video
            return await self.create(session, obj_in=video_data)

    async def get_video_statistics(self, session: AsyncSession) -> VideoStatistics:
        """
        Get comprehensive video statistics.

        Parameters
        ----------
        session : AsyncSession
            Database session

        Returns
        -------
        VideoStatistics
            Video statistics summary
        """
        # Get basic counts and aggregates
        result = await session.execute(
            select(
                func.count(VideoDB.video_id).label("total_videos"),
                func.sum(VideoDB.duration).label("total_duration"),
                func.avg(VideoDB.duration).label("avg_duration"),
                func.sum(VideoDB.view_count).label("total_views"),
                func.sum(VideoDB.like_count).label("total_likes"),
                func.sum(VideoDB.comment_count).label("total_comments"),
                func.avg(VideoDB.view_count).label("avg_views"),
                func.avg(VideoDB.like_count).label("avg_likes"),
                func.sum(func.case((VideoDB.deleted_flag.is_(True), 1), else_=0)).label(
                    "deleted_count"
                ),
                func.sum(
                    func.case(
                        (
                            or_(
                                VideoDB.made_for_kids.is_(True),
                                VideoDB.self_declared_made_for_kids.is_(True),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("kids_count"),
            )
        )

        stats_row = result.first()
        if not stats_row:
            return VideoStatistics(
                total_videos=0,
                total_duration=0,
                avg_duration=0.0,
                total_views=0,
                total_likes=0,
                total_comments=0,
                avg_views_per_video=0.0,
                avg_likes_per_video=0.0,
                deleted_video_count=0,
                kids_friendly_count=0,
                top_languages=[],
                upload_trend={},
            )

        # Get top languages
        language_result = await session.execute(
            select(VideoDB.default_language, func.count().label("count"))
            .where(VideoDB.default_language.is_not(None))
            .group_by(VideoDB.default_language)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_languages = [(str(row[0]), int(row[1])) for row in language_result]

        # Get upload trend by month
        trend_result = await session.execute(
            select(
                func.to_char(VideoDB.upload_date, "YYYY-MM").label("month"),
                func.count().label("count"),
            )
            .group_by(func.to_char(VideoDB.upload_date, "YYYY-MM"))
            .order_by(func.to_char(VideoDB.upload_date, "YYYY-MM"))
        )
        upload_trend = {str(row[0]): int(row[1]) for row in trend_result}

        return VideoStatistics(
            total_videos=int(stats_row.total_videos or 0),
            total_duration=int(stats_row.total_duration or 0),
            avg_duration=float(stats_row.avg_duration or 0.0),
            total_views=int(stats_row.total_views or 0),
            total_likes=int(stats_row.total_likes or 0),
            total_comments=int(stats_row.total_comments or 0),
            avg_views_per_video=float(stats_row.avg_views or 0.0),
            avg_likes_per_video=float(stats_row.avg_likes or 0.0),
            deleted_video_count=int(stats_row.deleted_count or 0),
            kids_friendly_count=int(stats_row.kids_count or 0),
            top_languages=top_languages,
            upload_trend=upload_trend,
        )

    # Video Localization Integration Methods

    async def get_videos_with_preferred_localizations(
        self,
        session: AsyncSession,
        video_ids: List[str],
        preferred_languages: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get videos with their preferred localizations.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_ids : List[str]
            List of video IDs to get localizations for
        preferred_languages : List[str]
            List of preferred language codes in order of preference

        Returns
        -------
        Dict[str, Dict[str, Any]]
            Mapping of video_id to video data with preferred localization
        """
        from .video_localization_repository import VideoLocalizationRepository

        if not video_ids:
            return {}

        # Get videos
        videos_result = await session.execute(
            select(VideoDB).where(VideoDB.video_id.in_(video_ids))
        )
        videos = {video.video_id: video for video in videos_result.scalars().all()}

        if not videos:
            return {}

        # Get preferred localizations
        localization_repo = VideoLocalizationRepository()
        preferred_localizations = await localization_repo.get_preferred_localizations(
            session, video_ids, preferred_languages
        )

        # Combine video data with localizations
        result = {}
        for video_id, video in videos.items():
            localization = preferred_localizations.get(video_id)

            result[video_id] = {
                "video": video,
                "preferred_localization": localization,
                "localized_title": (
                    localization.localized_title if localization else video.title
                ),
                "localized_description": (
                    localization.localized_description
                    if localization
                    else video.description
                ),
                "localization_language": (
                    localization.language_code
                    if localization
                    else video.default_language
                ),
            }

        return result

    async def get_videos_with_localization_support(
        self,
        session: AsyncSession,
        language_codes: Optional[List[str]] = None,
        min_localizations: int = 1,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get videos that have localization support in specified languages.

        Parameters
        ----------
        session : AsyncSession
            Database session
        language_codes : Optional[List[str]]
            List of language codes to filter by. If None, returns videos with any localizations
        min_localizations : int
            Minimum number of localizations required
        skip : int
            Number of records to skip
        limit : int
            Maximum number of records to return

        Returns
        -------
        List[Dict[str, Any]]
            List of videos with localization information
        """
        from .video_localization_repository import VideoLocalizationRepository

        localization_repo = VideoLocalizationRepository()

        if language_codes:
            # Get videos that have localizations in specific languages
            video_ids_per_language = {}
            for lang in language_codes:
                video_ids = await localization_repo.get_videos_by_language(
                    session, lang
                )
                video_ids_per_language[lang] = set(video_ids)

            # Find videos that appear in enough languages
            video_counts: Dict[str, int] = {}
            for lang, video_ids_set in video_ids_per_language.items():
                for video_id in video_ids_set:
                    video_counts[video_id] = video_counts.get(video_id, 0) + 1

            qualified_video_ids = [
                video_id
                for video_id, count in video_counts.items()
                if count >= min_localizations
            ]
        else:
            # Get all videos with localizations
            multilingual_videos = await localization_repo.get_multilingual_videos(
                session, min_languages=min_localizations
            )
            qualified_video_ids = [video_id for video_id, _ in multilingual_videos]

        if not qualified_video_ids:
            return []

        # Get video data with pagination
        videos_result = await session.execute(
            select(VideoDB)
            .where(
                and_(
                    VideoDB.video_id.in_(qualified_video_ids),
                    VideoDB.deleted_flag.is_(False),
                )
            )
            .order_by(VideoDB.upload_date.desc())
            .offset(skip)
            .limit(limit)
        )
        videos = list(videos_result.scalars().all())

        # Get localization counts for each video
        result = []
        for video in videos:
            localizations = await localization_repo.get_by_video_id(
                session, video.video_id
            )
            supported_languages = [loc.language_code for loc in localizations]

            result.append(
                {
                    "video": video,
                    "localization_count": len(localizations),
                    "supported_languages": supported_languages,
                    "localizations": localizations,
                }
            )

        return result

    async def get_videos_missing_localizations(
        self,
        session: AsyncSession,
        target_languages: List[str],
        video_ids: Optional[List[str]] = None,
        limit: int = 50,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get videos that are missing localizations in target languages.

        Parameters
        ----------
        session : AsyncSession
            Database session
        target_languages : List[str]
            List of target language codes
        video_ids : Optional[List[str]]
            Specific video IDs to check. If None, checks all videos
        limit : int
            Maximum number of videos to return

        Returns
        -------
        Dict[str, Dict[str, Any]]
            Mapping of video_id to video data with missing language information
        """
        from .video_localization_repository import VideoLocalizationRepository

        localization_repo = VideoLocalizationRepository()

        # Get missing localizations
        missing_localizations = await localization_repo.find_missing_localizations(
            session, target_languages, video_ids
        )

        if not missing_localizations:
            return {}

        # Get video data for videos with missing localizations
        video_ids_with_missing = list(missing_localizations.keys())[:limit]
        videos_result = await session.execute(
            select(VideoDB)
            .where(
                and_(
                    VideoDB.video_id.in_(video_ids_with_missing),
                    VideoDB.deleted_flag.is_(False),
                )
            )
            .order_by(VideoDB.upload_date.desc())
        )
        videos = {video.video_id: video for video in videos_result.scalars().all()}

        # Combine video data with missing language information
        result = {}
        for video_id, missing_languages in missing_localizations.items():
            if video_id in videos:
                # Get existing localizations for context
                existing_localizations = await localization_repo.get_by_video_id(
                    session, video_id
                )
                existing_languages = [
                    loc.language_code for loc in existing_localizations
                ]

                result[video_id] = {
                    "video": videos[video_id],
                    "missing_languages": missing_languages,
                    "existing_languages": existing_languages,
                    "existing_localizations": existing_localizations,
                    "completion_percentage": (
                        len(existing_languages) / len(target_languages) * 100
                        if target_languages
                        else 0
                    ),
                }

        return result

    async def get_video_localization_summary(
        self,
        session: AsyncSession,
        video_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive localization summary for a single video.

        Parameters
        ----------
        session : AsyncSession
            Database session
        video_id : str
            Video ID to get summary for

        Returns
        -------
        Optional[Dict[str, Any]]
            Video localization summary or None if video not found
        """
        from .video_localization_repository import VideoLocalizationRepository

        # Get video
        video = await self.get_by_video_id(session, video_id)
        if not video:
            return None

        localization_repo = VideoLocalizationRepository()

        # Get all localizations for this video
        localizations = await localization_repo.get_by_video_id(session, video_id)

        # Get language coverage for context
        language_coverage = await localization_repo.get_language_coverage(session)

        # Calculate metrics
        supported_languages = [loc.language_code for loc in localizations]

        return {
            "video": video,
            "localization_count": len(localizations),
            "supported_languages": supported_languages,
            "localizations": localizations,
            "has_localizations": len(localizations) > 0,
            "most_common_language": (
                max(language_coverage.items(), key=lambda x: x[1])[0]
                if language_coverage
                else None
            ),
            "is_multilingual": len(localizations) > 1,
            "localization_summary": {
                loc.language_code: {
                    "title": loc.localized_title,
                    "has_description": bool(loc.localized_description),
                    "created_at": loc.created_at,
                }
                for loc in localizations
            },
        }

    async def find_by_category_id(
        self,
        session: AsyncSession,
        category_id: str,
        *,
        skip: int = 0,
        limit: int | None = None,
        exclude_deleted: bool = True,
    ) -> List[VideoDB]:
        """
        Find videos by YouTube video category ID.

        Parameters
        ----------
        session : AsyncSession
            Database session
        category_id : str
            YouTube video category ID (e.g., "23" for Comedy)
        skip : int
            Number of videos to skip (default: 0)
        limit : int | None
            Maximum number of videos to return (default: None for all)
        exclude_deleted : bool
            Whether to exclude deleted videos (default: True)

        Returns
        -------
        List[VideoDB]
            List of videos in the specified category
        """
        query = select(VideoDB).where(VideoDB.category_id == category_id)

        if exclude_deleted:
            query = query.where(VideoDB.deleted_flag.is_(False))

        query = query.order_by(desc(VideoDB.view_count)).offset(skip)

        if limit is not None:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def count_by_category_id(
        self,
        session: AsyncSession,
        category_id: str,
        *,
        exclude_deleted: bool = True,
    ) -> int:
        """
        Count videos in a specific category.

        Parameters
        ----------
        session : AsyncSession
            Database session
        category_id : str
            YouTube video category ID
        exclude_deleted : bool
            Whether to exclude deleted videos (default: True)

        Returns
        -------
        int
            Number of videos in the category
        """
        query = select(func.count()).select_from(VideoDB).where(
            VideoDB.category_id == category_id
        )

        if exclude_deleted:
            query = query.where(VideoDB.deleted_flag.is_(False))

        result = await session.execute(query)
        return result.scalar() or 0
