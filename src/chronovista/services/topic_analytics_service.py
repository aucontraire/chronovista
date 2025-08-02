"""
Topic analytics service.

Provides advanced analytics for topic data including popularity rankings,
relationship analysis, and statistical calculations with caching support.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config.database import db_manager
from ..db.models import Channel, TopicCategory, UserVideo, Video, VideoTopic
from ..models.topic_analytics import (
    TopicAnalyticsSummary,
    TopicDiscoveryAnalysis,
    TopicDiscoveryPath,
    TopicInsight,
    TopicInsightCollection,
    TopicOverlap,
    TopicPopularity,
    TopicRelationship,
    TopicRelationships,
    TopicStats,
    TopicTrend,
)
from ..models.youtube_types import TopicId
from ..repositories.channel_topic_repository import ChannelTopicRepository
from ..repositories.topic_category_repository import TopicCategoryRepository
from ..repositories.video_topic_repository import VideoTopicRepository


class TopicAnalyticsService:
    """Advanced analytics for topic data with caching and optimization."""

    def __init__(self) -> None:
        """Initialize the analytics service with repositories."""
        self.topic_category_repository = TopicCategoryRepository()
        self.video_topic_repository = VideoTopicRepository()
        self.channel_topic_repository = ChannelTopicRepository()
        self._cache: Dict[str, tuple[datetime, object]] = {}
        self._cache_ttl = 300  # 5 minutes cache TTL

    def _get_cache_key(self, method: str, *args: str) -> str:
        """Generate cache key for method and arguments."""
        return f"{method}:{':'.join(str(arg) for arg in args)}"

    def _is_cache_valid(self, timestamp: datetime) -> bool:
        """Check if cached result is still valid."""
        return (datetime.now() - timestamp).total_seconds() < self._cache_ttl

    def _get_cached_result(self, cache_key: str) -> Optional[object]:
        """Get cached result if valid."""
        if cache_key in self._cache:
            timestamp, result = self._cache[cache_key]
            if self._is_cache_valid(timestamp):
                return result
            else:
                # Remove expired cache entry
                del self._cache[cache_key]
        return None

    def _cache_result(self, cache_key: str, result: object) -> None:
        """Cache result with timestamp."""
        self._cache[cache_key] = (datetime.now(), result)

    async def get_popular_topics(
        self,
        metric: Literal["videos", "channels", "combined"] = "videos",
        limit: int = 20,
    ) -> List[TopicPopularity]:
        """
        Get topics ranked by popularity.

        Parameters
        ----------
        metric : str
            Ranking metric: "videos", "channels", or "combined"
        limit : int
            Maximum number of topics to return

        Returns
        -------
        List[TopicPopularity]
            Topics ranked by popularity
        """
        cache_key = self._get_cache_key("popular_topics", metric, str(limit))
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session():
            # Get total counts for percentage calculations
            total_videos_query = select(
                func.count(func.distinct(self.video_topic_repository.model.video_id))
            ).select_from(self.video_topic_repository.model)
            total_videos_result = await session.execute(total_videos_query)
            total_videos = total_videos_result.scalar() or 0

            total_channels_query = select(
                func.count(
                    func.distinct(self.channel_topic_repository.model.channel_id)
                )
            ).select_from(self.channel_topic_repository.model)
            total_channels_result = await session.execute(total_channels_query)
            total_channels = total_channels_result.scalar() or 0

            # Build main query based on metric
            if metric == "videos":
                # Rank by video count
                query = (
                    select(
                        TopicCategory.topic_id,
                        TopicCategory.category_name,
                        func.count(self.video_topic_repository.model.video_id).label(
                            "video_count"
                        ),
                        func.coalesce(
                            func.count(self.channel_topic_repository.model.channel_id),
                            0,
                        ).label("channel_count"),
                    )
                    .select_from(TopicCategory)
                    .outerjoin(
                        self.video_topic_repository.model,
                        TopicCategory.topic_id
                        == self.video_topic_repository.model.topic_id,
                    )
                    .outerjoin(
                        self.channel_topic_repository.model,
                        TopicCategory.topic_id
                        == self.channel_topic_repository.model.topic_id,
                    )
                    .group_by(TopicCategory.topic_id, TopicCategory.category_name)
                    .having(func.count(self.video_topic_repository.model.video_id) > 0)
                    .order_by(desc("video_count"))
                    .limit(limit)
                )
            elif metric == "channels":
                # Rank by channel count
                query = (
                    select(
                        TopicCategory.topic_id,
                        TopicCategory.category_name,
                        func.coalesce(
                            func.count(self.video_topic_repository.model.video_id), 0
                        ).label("video_count"),
                        func.count(
                            self.channel_topic_repository.model.channel_id
                        ).label("channel_count"),
                    )
                    .select_from(TopicCategory)
                    .outerjoin(
                        self.video_topic_repository.model,
                        TopicCategory.topic_id
                        == self.video_topic_repository.model.topic_id,
                    )
                    .outerjoin(
                        self.channel_topic_repository.model,
                        TopicCategory.topic_id
                        == self.channel_topic_repository.model.topic_id,
                    )
                    .group_by(TopicCategory.topic_id, TopicCategory.category_name)
                    .having(
                        func.count(self.channel_topic_repository.model.channel_id) > 0
                    )
                    .order_by(desc("channel_count"))
                    .limit(limit)
                )
            else:  # combined
                # Rank by combined score (videos + channels with weights)
                query = (
                    select(
                        TopicCategory.topic_id,
                        TopicCategory.category_name,
                        func.coalesce(
                            func.count(self.video_topic_repository.model.video_id), 0
                        ).label("video_count"),
                        func.coalesce(
                            func.count(self.channel_topic_repository.model.channel_id),
                            0,
                        ).label("channel_count"),
                    )
                    .select_from(TopicCategory)
                    .outerjoin(
                        self.video_topic_repository.model,
                        TopicCategory.topic_id
                        == self.video_topic_repository.model.topic_id,
                    )
                    .outerjoin(
                        self.channel_topic_repository.model,
                        TopicCategory.topic_id
                        == self.channel_topic_repository.model.topic_id,
                    )
                    .group_by(TopicCategory.topic_id, TopicCategory.category_name)
                    .having(
                        func.coalesce(
                            func.count(self.video_topic_repository.model.video_id), 0
                        )
                        + func.coalesce(
                            func.count(self.channel_topic_repository.model.channel_id),
                            0,
                        )
                        > 0
                    )
                    .order_by(
                        desc(
                            func.coalesce(
                                func.count(self.video_topic_repository.model.video_id),
                                0,
                            )
                            + func.coalesce(
                                func.count(
                                    self.channel_topic_repository.model.channel_id
                                ),
                                0,
                            )
                        )
                    )
                    .limit(limit)
                )

            result = await session.execute(query)
            rows = result.fetchall()

            # Convert to TopicPopularity models
            popular_topics = []
            for rank, row in enumerate(rows, 1):
                video_count = int(row.video_count) if row.video_count else 0
                channel_count = int(row.channel_count) if row.channel_count else 0

                # Calculate percentages
                video_percentage = (
                    Decimal(str(video_count / total_videos * 100))
                    if total_videos > 0
                    else Decimal("0.0")
                )
                channel_percentage = (
                    Decimal(str(channel_count / total_channels * 100))
                    if total_channels > 0
                    else Decimal("0.0")
                )

                # Calculate popularity score based on metric
                if metric == "videos":
                    popularity_score = Decimal(str(video_count))
                elif metric == "channels":
                    popularity_score = Decimal(str(channel_count))
                else:  # combined
                    popularity_score = Decimal(
                        str(video_count * 0.7 + channel_count * 0.3)
                    )

                topic_popularity = TopicPopularity(
                    topic_id=row.topic_id,
                    category_name=row.category_name,
                    video_count=video_count,
                    channel_count=channel_count,
                    total_content_count=video_count + channel_count,
                    video_percentage=video_percentage,
                    channel_percentage=channel_percentage,
                    popularity_score=popularity_score,
                    rank=rank,
                )
                popular_topics.append(topic_popularity)

            # Cache and return results
            self._cache_result(cache_key, popular_topics)
            return popular_topics

        # This should never be reached, but added for mypy
        return []

    async def get_topic_relationships(
        self, topic_id: TopicId, min_confidence: float = 0.1, limit: int = 10
    ) -> TopicRelationships:
        """
        Get topics that are related to the given topic.

        Parameters
        ----------
        topic_id : TopicId
            Source topic to find relationships for
        min_confidence : float
            Minimum confidence score for relationships
        limit : int
            Maximum number of related topics to return

        Returns
        -------
        TopicRelationships
            Related topics with confidence scores
        """
        cache_key = self._get_cache_key(
            "topic_relationships", topic_id, str(min_confidence), str(limit)
        )
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session():
            # Get source topic info
            source_topic = await self.topic_category_repository.get(session, topic_id)
            if not source_topic:
                return TopicRelationships(
                    source_topic_id=topic_id,
                    source_category_name=f"Unknown Topic {topic_id}",
                    total_videos=0,
                    total_channels=0,
                    relationships=[],
                    analysis_date=datetime.now().isoformat(),
                )

            # Get source topic content counts
            source_videos_query = (
                select(func.count())
                .select_from(self.video_topic_repository.model)
                .where(self.video_topic_repository.model.topic_id == topic_id)
            )
            source_videos_result = await session.execute(source_videos_query)
            source_videos = source_videos_result.scalar() or 0

            source_channels_query = (
                select(func.count())
                .select_from(self.channel_topic_repository.model)
                .where(self.channel_topic_repository.model.topic_id == topic_id)
            )
            source_channels_result = await session.execute(source_channels_query)
            source_channels = source_channels_result.scalar() or 0

            # Find related topics through shared videos
            video_relationships_query = text(
                """
                WITH source_videos AS (
                    SELECT video_id FROM video_topics WHERE topic_id = :topic_id
                ),
                related_topics AS (
                    SELECT 
                        vt.topic_id,
                        tc.category_name,
                        COUNT(DISTINCT vt.video_id) as shared_videos,
                        0 as shared_channels
                    FROM video_topics vt
                    JOIN topic_categories tc ON vt.topic_id = tc.topic_id
                    WHERE vt.video_id IN (SELECT video_id FROM source_videos)
                      AND vt.topic_id != :topic_id
                    GROUP BY vt.topic_id, tc.category_name
                )
                SELECT 
                    topic_id,
                    category_name,
                    shared_videos,
                    shared_channels,
                    shared_videos as total_shared,
                    CAST(shared_videos AS FLOAT) / :source_videos as confidence_score
                FROM related_topics
                WHERE CAST(shared_videos AS FLOAT) / :source_videos >= :min_confidence
                ORDER BY confidence_score DESC, shared_videos DESC
                LIMIT :limit
            """
            )

            relationships_result = await session.execute(
                video_relationships_query,
                {
                    "topic_id": topic_id,
                    "source_videos": max(source_videos, 1),  # Avoid division by zero
                    "min_confidence": min_confidence,
                    "limit": limit,
                },
            )
            relationship_rows = relationships_result.fetchall()

            # Convert to TopicRelationship models
            relationships = []
            for row in relationship_rows:
                confidence_score = Decimal(str(row.confidence_score))
                lift_score = confidence_score  # Simplified lift calculation

                relationship = TopicRelationship(
                    topic_id=row.topic_id,
                    category_name=row.category_name,
                    shared_videos=int(row.shared_videos),
                    shared_channels=int(row.shared_channels),
                    total_shared=int(row.total_shared),
                    confidence_score=confidence_score,
                    lift_score=lift_score,
                    relationship_type="related",
                )
                relationships.append(relationship)

            result = TopicRelationships(
                source_topic_id=topic_id,
                source_category_name=source_topic.category_name,
                total_videos=source_videos,
                total_channels=source_channels,
                relationships=relationships,
                analysis_date=datetime.now().isoformat(),
            )

            # Cache and return results
            self._cache_result(cache_key, result)
            return result

        # This should never be reached, but added for mypy
        return TopicRelationships(
            source_topic_id=topic_id,
            source_category_name=f"Unknown Topic {topic_id}",
            total_videos=0,
            total_channels=0,
            relationships=[],
            analysis_date=datetime.now().isoformat(),
        )

    async def calculate_topic_overlap(
        self, topic1_id: TopicId, topic2_id: TopicId
    ) -> TopicOverlap:
        """
        Calculate overlap between two topics.

        Parameters
        ----------
        topic1_id : TopicId
            First topic identifier
        topic2_id : TopicId
            Second topic identifier

        Returns
        -------
        TopicOverlap
            Overlap analysis between the two topics
        """
        cache_key = self._get_cache_key("topic_overlap", topic1_id, topic2_id)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session():
            # Get topic names
            topic1 = await self.topic_category_repository.get(session, topic1_id)
            topic2 = await self.topic_category_repository.get(session, topic2_id)

            topic1_name = topic1.category_name if topic1 else f"Topic {topic1_id}"
            topic2_name = topic2.category_name if topic2 else f"Topic {topic2_id}"

            # Calculate video overlap using raw SQL for efficiency
            video_overlap_query = text(
                """
                WITH topic1_videos AS (
                    SELECT video_id FROM video_topics WHERE topic_id = :topic1_id
                ),
                topic2_videos AS (
                    SELECT video_id FROM video_topics WHERE topic_id = :topic2_id
                ),
                overlap_stats AS (
                    SELECT 
                        (SELECT COUNT(*) FROM topic1_videos) as topic1_count,
                        (SELECT COUNT(*) FROM topic2_videos) as topic2_count,
                        (SELECT COUNT(*) FROM topic1_videos t1 
                         JOIN topic2_videos t2 ON t1.video_id = t2.video_id) as shared_count
                )
                SELECT topic1_count, topic2_count, shared_count FROM overlap_stats
            """
            )

            video_result = await session.execute(
                video_overlap_query, {"topic1_id": topic1_id, "topic2_id": topic2_id}
            )
            video_row = video_result.fetchone()

            # Calculate channel overlap
            channel_overlap_query = text(
                """
                WITH topic1_channels AS (
                    SELECT channel_id FROM channel_topics WHERE topic_id = :topic1_id
                ),
                topic2_channels AS (
                    SELECT channel_id FROM channel_topics WHERE topic_id = :topic2_id
                ),
                overlap_stats AS (
                    SELECT 
                        (SELECT COUNT(*) FROM topic1_channels) as topic1_count,
                        (SELECT COUNT(*) FROM topic2_channels) as topic2_count,
                        (SELECT COUNT(*) FROM topic1_channels t1 
                         JOIN topic2_channels t2 ON t1.channel_id = t2.channel_id) as shared_count
                )
                SELECT topic1_count, topic2_count, shared_count FROM overlap_stats
            """
            )

            channel_result = await session.execute(
                channel_overlap_query, {"topic1_id": topic1_id, "topic2_id": topic2_id}
            )
            channel_row = channel_result.fetchone()

            # Extract counts
            topic1_videos = int(video_row.topic1_count) if video_row else 0
            topic2_videos = int(video_row.topic2_count) if video_row else 0
            shared_videos = int(video_row.shared_count) if video_row else 0

            topic1_channels = int(channel_row.topic1_count) if channel_row else 0
            topic2_channels = int(channel_row.topic2_count) if channel_row else 0
            shared_channels = int(channel_row.shared_count) if channel_row else 0

            # Calculate percentages
            video_overlap_pct = Decimal("0.0")
            if topic1_videos > 0 and topic2_videos > 0:
                video_overlap_pct = Decimal(
                    str(shared_videos / min(topic1_videos, topic2_videos) * 100)
                )

            channel_overlap_pct = Decimal("0.0")
            if topic1_channels > 0 and topic2_channels > 0:
                channel_overlap_pct = Decimal(
                    str(shared_channels / min(topic1_channels, topic2_channels) * 100)
                )

            # Calculate Jaccard similarity
            union_videos = topic1_videos + topic2_videos - shared_videos
            union_channels = topic1_channels + topic2_channels - shared_channels
            total_union = union_videos + union_channels
            total_intersection = shared_videos + shared_channels

            jaccard_similarity = Decimal("0.0")
            if total_union > 0:
                jaccard_similarity = Decimal(str(total_intersection / total_union))

            # Determine overlap strength
            avg_overlap_pct = (video_overlap_pct + channel_overlap_pct) / 2
            if avg_overlap_pct >= 50:
                overlap_strength = "strong"
            elif avg_overlap_pct >= 25:
                overlap_strength = "moderate"
            elif avg_overlap_pct >= 10:
                overlap_strength = "weak"
            else:
                overlap_strength = "none"

            result = TopicOverlap(
                topic1_id=topic1_id,
                topic1_name=topic1_name,
                topic2_id=topic2_id,
                topic2_name=topic2_name,
                topic1_videos=topic1_videos,
                topic2_videos=topic2_videos,
                shared_videos=shared_videos,
                video_overlap_percentage=video_overlap_pct,
                topic1_channels=topic1_channels,
                topic2_channels=topic2_channels,
                shared_channels=shared_channels,
                channel_overlap_percentage=channel_overlap_pct,
                jaccard_similarity=jaccard_similarity,
                overlap_strength=overlap_strength,
            )

            # Cache and return results
            self._cache_result(cache_key, result)
            return result

        # This should never be reached, but added for mypy
        return TopicOverlap(
            topic1_id=topic1_id,
            topic1_name=f"Topic {topic1_id}",
            topic2_id=topic2_id,
            topic2_name=f"Topic {topic2_id}",
            topic1_videos=0,
            topic2_videos=0,
            shared_videos=0,
            video_overlap_percentage=Decimal("0.0"),
            topic1_channels=0,
            topic2_channels=0,
            shared_channels=0,
            channel_overlap_percentage=Decimal("0.0"),
            jaccard_similarity=Decimal("0.0"),
            overlap_strength="none",
        )

    async def get_analytics_summary(self) -> TopicAnalyticsSummary:
        """
        Get overall topic analytics summary.

        Returns
        -------
        TopicAnalyticsSummary
            Summary of topic analytics
        """
        cache_key = self._get_cache_key("analytics_summary")
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session():
            # Get total counts
            total_topics_query = select(func.count()).select_from(TopicCategory)
            total_topics_result = await session.execute(total_topics_query)
            total_topics = total_topics_result.scalar() or 0

            total_videos_query = select(
                func.count(func.distinct(self.video_topic_repository.model.video_id))
            ).select_from(self.video_topic_repository.model)
            total_videos_result = await session.execute(total_videos_query)
            total_videos = total_videos_result.scalar() or 0

            total_channels_query = select(
                func.count(
                    func.distinct(self.channel_topic_repository.model.channel_id)
                )
            ).select_from(self.channel_topic_repository.model)
            total_channels_result = await session.execute(total_channels_query)
            total_channels = total_channels_result.scalar() or 0

            # Get total content for coverage calculation
            all_videos_query = select(func.count()).select_from(Video)
            all_videos_result = await session.execute(all_videos_query)
            all_videos = all_videos_result.scalar() or 0

            all_channels_query = select(func.count()).select_from(Channel)
            all_channels_result = await session.execute(all_channels_query)
            all_channels = all_channels_result.scalar() or 0

            # Calculate coverage percentage
            total_content_with_topics = total_videos + total_channels
            total_content = all_videos + all_channels
            coverage_percentage = Decimal("0.0")
            if total_content > 0:
                coverage_percentage = Decimal(
                    str(total_content_with_topics / total_content * 100)
                )

            # Get top 5 popular topics
            popular_topics = await self.get_popular_topics(metric="combined", limit=5)

            # Get topic distribution
            distribution_query = (
                select(
                    TopicCategory.category_name,
                    func.count(self.video_topic_repository.model.video_id).label(
                        "count"
                    ),
                )
                .select_from(TopicCategory)
                .join(
                    self.video_topic_repository.model,
                    TopicCategory.topic_id
                    == self.video_topic_repository.model.topic_id,
                )
                .group_by(TopicCategory.category_name)
                .order_by(desc("count"))
            )
            distribution_result = await session.execute(distribution_query)
            distribution_rows = distribution_result.fetchall()

            topic_distribution: Dict[str, int] = {}
            for row in distribution_rows:
                topic_distribution[row.category_name] = getattr(row, "count", 0)

            result = TopicAnalyticsSummary(
                total_topics=total_topics,
                total_videos=total_videos,
                total_channels=total_channels,
                most_popular_topics=popular_topics,
                topic_distribution=topic_distribution,
                analysis_date=datetime.now().isoformat(),
                coverage_percentage=coverage_percentage,
            )

            # Cache and return results
            self._cache_result(cache_key, result)
            return result

        # This should never be reached, but added for mypy
        return TopicAnalyticsSummary(
            total_topics=0,
            total_videos=0,
            total_channels=0,
            most_popular_topics=[],
            topic_distribution={},
            analysis_date=datetime.now().isoformat(),
            coverage_percentage=Decimal("0.0"),
        )

    async def get_similar_topics(
        self, topic_id: TopicId, min_similarity: float = 0.5, limit: int = 10
    ) -> List[TopicPopularity]:
        """
        Get topics that are similar to the given topic based on content patterns.

        Parameters
        ----------
        topic_id : TopicId
            Source topic to find similar topics for
        min_similarity : float
            Minimum similarity score (0.0-1.0)
        limit : int
            Maximum number of similar topics to return

        Returns
        -------
        List[TopicPopularity]
            Topics similar to the source topic with similarity scores
        """
        cache_key = self._get_cache_key(
            "similar_topics", topic_id, str(min_similarity), str(limit)
        )
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session():
            # Get source topic info
            source_topic = await self.topic_category_repository.get(session, topic_id)
            if not source_topic:
                return []

            # Get source topic content counts
            source_videos_query = (
                select(func.count())
                .select_from(self.video_topic_repository.model)
                .where(self.video_topic_repository.model.topic_id == topic_id)
            )
            source_videos_result = await session.execute(source_videos_query)
            source_videos = source_videos_result.scalar() or 0

            source_channels_query = (
                select(func.count())
                .select_from(self.channel_topic_repository.model)
                .where(self.channel_topic_repository.model.topic_id == topic_id)
            )
            source_channels_result = await session.execute(source_channels_query)
            source_channels = source_channels_result.scalar() or 0

            if source_videos == 0 and source_channels == 0:
                return []

            # Calculate source topic characteristics
            source_total = source_videos + source_channels
            source_video_ratio = source_videos / source_total if source_total > 0 else 0
            source_channel_ratio = (
                source_channels / source_total if source_total > 0 else 0
            )

            # Get all topics with content for similarity comparison
            all_topics_query = (
                select(
                    TopicCategory.topic_id,
                    TopicCategory.category_name,
                    func.coalesce(
                        func.count(self.video_topic_repository.model.video_id), 0
                    ).label("video_count"),
                    func.coalesce(
                        func.count(self.channel_topic_repository.model.channel_id), 0
                    ).label("channel_count"),
                )
                .select_from(TopicCategory)
                .outerjoin(
                    self.video_topic_repository.model,
                    TopicCategory.topic_id
                    == self.video_topic_repository.model.topic_id,
                )
                .outerjoin(
                    self.channel_topic_repository.model,
                    TopicCategory.topic_id
                    == self.channel_topic_repository.model.topic_id,
                )
                .where(TopicCategory.topic_id != topic_id)  # Exclude source topic
                .group_by(TopicCategory.topic_id, TopicCategory.category_name)
                .having(
                    func.coalesce(
                        func.count(self.video_topic_repository.model.video_id), 0
                    )
                    + func.coalesce(
                        func.count(self.channel_topic_repository.model.channel_id), 0
                    )
                    > 0
                )
            )

            result = await session.execute(all_topics_query)
            rows = result.fetchall()

            # Calculate similarity scores
            similar_topics = []
            for row in rows:
                video_count = int(row.video_count) if row.video_count else 0
                channel_count = int(row.channel_count) if row.channel_count else 0
                total_count = video_count + channel_count

                if total_count == 0:
                    continue

                # Calculate ratios for comparison topic
                video_ratio = video_count / total_count
                channel_ratio = channel_count / total_count

                # Calculate similarity using cosine similarity of content patterns
                # Consider: content volume similarity + ratio similarity

                # Volume similarity (normalized)
                volume_similarity = 1 - abs(source_total - total_count) / max(
                    source_total, total_count
                )

                # Ratio similarity (cosine similarity of [video_ratio, channel_ratio])
                dot_product = (
                    source_video_ratio * video_ratio
                    + source_channel_ratio * channel_ratio
                )
                source_magnitude = (
                    source_video_ratio**2 + source_channel_ratio**2
                ) ** 0.5
                target_magnitude = (video_ratio**2 + channel_ratio**2) ** 0.5

                if source_magnitude > 0 and target_magnitude > 0:
                    ratio_similarity = dot_product / (
                        source_magnitude * target_magnitude
                    )
                else:
                    ratio_similarity = 0

                # Combined similarity (weighted average)
                similarity_score = volume_similarity * 0.3 + ratio_similarity * 0.7

                if similarity_score >= min_similarity:
                    # Create TopicPopularity object with similarity as popularity_score
                    topic_popularity = TopicPopularity(
                        topic_id=row.topic_id,
                        category_name=row.category_name,
                        video_count=video_count,
                        channel_count=channel_count,
                        total_content_count=total_count,
                        video_percentage=Decimal(str(video_ratio * 100)),
                        channel_percentage=Decimal(str(channel_ratio * 100)),
                        popularity_score=Decimal(str(similarity_score)),
                        rank=0,  # Will be set after sorting
                    )
                    similar_topics.append(topic_popularity)

            # Sort by similarity score (descending) and set ranks
            similar_topics.sort(key=lambda x: x.popularity_score, reverse=True)
            for rank, topic in enumerate(similar_topics[:limit], 1):
                # Update rank (create new object since it's frozen)
                similar_topics[rank - 1] = TopicPopularity(
                    topic_id=topic.topic_id,
                    category_name=topic.category_name,
                    video_count=topic.video_count,
                    channel_count=topic.channel_count,
                    total_content_count=topic.total_content_count,
                    video_percentage=topic.video_percentage,
                    channel_percentage=topic.channel_percentage,
                    popularity_score=topic.popularity_score,
                    rank=rank,
                )

            result_topics = similar_topics[:limit]

            # Cache and return results
            self._cache_result(cache_key, result_topics)
            return result_topics

        # This should never be reached, but added for mypy
        return []

    async def get_topic_discovery_analysis(
        self, limit_topics: int = 20, min_interactions: int = 2
    ) -> TopicDiscoveryAnalysis:
        """
        Analyze how users discover topics based on their viewing patterns.

        Parameters
        ----------
        limit_topics : int
            Maximum number of topics to analyze for entry/retention
        min_interactions : int
            Minimum interactions required to be considered active

        Returns
        -------
        TopicDiscoveryAnalysis
            Analysis of topic discovery patterns
        """
        cache_key = self._get_cache_key(
            "topic_discovery", str(limit_topics), str(min_interactions)
        )
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session():
            # Get total users with interactions
            total_users_query = select(
                func.count(func.distinct(UserVideo.user_id))
            ).select_from(UserVideo)
            total_users_result = await session.execute(total_users_query)
            total_users = total_users_result.scalar() or 0

            # Get total discovery events (first time watching videos in each topic)
            discovery_events_query = text(
                """
                WITH first_topic_interactions AS (
                    SELECT 
                        uv.user_id,
                        vt.topic_id,
                        tc.category_name,
                        MIN(uv.watched_at) as first_interaction,
                        COUNT(*) as interaction_count,
                        AVG(COALESCE(uv.completion_percentage, 0)) as avg_completion,
                        AVG(CASE WHEN uv.liked THEN 1 ELSE 0 END) as like_rate
                    FROM user_videos uv
                    JOIN video_topics vt ON uv.video_id = vt.video_id
                    JOIN topic_categories tc ON vt.topic_id = tc.topic_id
                    WHERE uv.watched_at IS NOT NULL
                    GROUP BY uv.user_id, vt.topic_id, tc.category_name
                    HAVING COUNT(*) >= :min_interactions
                ),
                discovery_methods AS (
                    SELECT 
                        topic_id,
                        category_name,
                        CASE 
                            WHEN like_rate > 0.5 THEN 'liked_content'
                            WHEN avg_completion > 0.8 THEN 'watched_complete'
                            WHEN avg_completion > 0.3 THEN 'watched_partial'
                            ELSE 'browsed'
                        END as discovery_method,
                        COUNT(*) as discovery_count,
                        AVG(avg_completion * 100) as avg_engagement,
                        -- Calculate retention as users who had multiple interactions
                        COUNT(CASE WHEN interaction_count > :min_interactions THEN 1 END) * 100.0 / COUNT(*) as retention_rate
                    FROM first_topic_interactions
                    GROUP BY topic_id, category_name, 
                        CASE 
                            WHEN like_rate > 0.5 THEN 'liked_content'
                            WHEN avg_completion > 0.8 THEN 'watched_complete'
                            WHEN avg_completion > 0.3 THEN 'watched_partial'
                            ELSE 'browsed'
                        END
                )
                SELECT 
                    discovery_method,
                    topic_id,
                    category_name,
                    discovery_count,
                    avg_engagement,
                    retention_rate
                FROM discovery_methods
                ORDER BY discovery_count DESC
            """
            )

            discovery_result = await session.execute(
                discovery_events_query, {"min_interactions": min_interactions}
            )
            discovery_rows = discovery_result.fetchall()

            # Process discovery paths
            discovery_paths = []
            total_discoveries = 0
            for row in discovery_rows:
                total_discoveries += int(row.discovery_count)
                discovery_path = TopicDiscoveryPath(
                    discovery_method=row.discovery_method,
                    topic_id=row.topic_id,
                    category_name=row.category_name,
                    discovery_count=int(row.discovery_count),
                    avg_engagement=Decimal(str(row.avg_engagement)),
                    retention_rate=Decimal(str(row.retention_rate)),
                )
                discovery_paths.append(discovery_path)

            # Get top entry topics (topics users discover first)
            entry_topics_query = text(
                """
                WITH user_first_topics AS (
                    SELECT DISTINCT ON (uv.user_id)
                        uv.user_id,
                        vt.topic_id,
                        tc.category_name,
                        uv.watched_at
                    FROM user_videos uv
                    JOIN video_topics vt ON uv.video_id = vt.video_id
                    JOIN topic_categories tc ON vt.topic_id = tc.topic_id
                    WHERE uv.watched_at IS NOT NULL
                    ORDER BY uv.user_id, uv.watched_at ASC
                ),
                entry_topic_stats AS (
                    SELECT 
                        topic_id,
                        category_name,
                        COUNT(*) as entry_count
                    FROM user_first_topics
                    GROUP BY topic_id, category_name
                )
                SELECT 
                    topic_id,
                    category_name,
                    entry_count as video_count,
                    0 as channel_count,
                    entry_count as total_content_count,
                    entry_count * 100.0 / :total_users as video_percentage,
                    0.0 as channel_percentage,
                    entry_count as popularity_score
                FROM entry_topic_stats
                ORDER BY entry_count DESC
                LIMIT :limit_topics
            """
            )

            entry_result = await session.execute(
                entry_topics_query,
                {"total_users": max(total_users, 1), "limit_topics": limit_topics},
            )
            entry_rows = entry_result.fetchall()

            top_entry_topics = []
            for rank, row in enumerate(entry_rows, 1):
                topic_popularity = TopicPopularity(
                    topic_id=row.topic_id,
                    category_name=row.category_name,
                    video_count=int(row.video_count),
                    channel_count=int(row.channel_count),
                    total_content_count=int(row.total_content_count),
                    video_percentage=Decimal(str(row.video_percentage)),
                    channel_percentage=Decimal(str(row.channel_percentage)),
                    popularity_score=Decimal(str(row.popularity_score)),
                    rank=rank,
                )
                top_entry_topics.append(topic_popularity)

            # Get high retention topics
            retention_topics_query = text(
                """
                WITH topic_retention AS (
                    SELECT 
                        vt.topic_id,
                        tc.category_name,
                        COUNT(DISTINCT uv.user_id) as total_users,
                        COUNT(DISTINCT CASE WHEN interaction_stats.interaction_count > :min_interactions 
                               THEN uv.user_id END) as retained_users
                    FROM user_videos uv
                    JOIN video_topics vt ON uv.video_id = vt.video_id
                    JOIN topic_categories tc ON vt.topic_id = tc.topic_id
                    JOIN (
                        SELECT user_id, COUNT(*) as interaction_count
                        FROM user_videos
                        WHERE watched_at IS NOT NULL
                        GROUP BY user_id
                    ) interaction_stats ON uv.user_id = interaction_stats.user_id
                    WHERE uv.watched_at IS NOT NULL
                    GROUP BY vt.topic_id, tc.category_name
                    HAVING COUNT(DISTINCT uv.user_id) >= 2
                )
                SELECT 
                    topic_id,
                    category_name,
                    total_users as video_count,
                    0 as channel_count,
                    total_users as total_content_count,
                    retained_users * 100.0 / total_users as video_percentage,
                    0.0 as channel_percentage,
                    retained_users * 100.0 / total_users as popularity_score
                FROM topic_retention
                ORDER BY retained_users * 100.0 / total_users DESC
                LIMIT :limit_topics
            """
            )

            retention_result = await session.execute(
                retention_topics_query,
                {"min_interactions": min_interactions, "limit_topics": limit_topics},
            )
            retention_rows = retention_result.fetchall()

            high_retention_topics = []
            for rank, row in enumerate(retention_rows, 1):
                topic_popularity = TopicPopularity(
                    topic_id=row.topic_id,
                    category_name=row.category_name,
                    video_count=int(row.video_count),
                    channel_count=int(row.channel_count),
                    total_content_count=int(row.total_content_count),
                    video_percentage=Decimal(str(row.video_percentage)),
                    channel_percentage=Decimal(str(row.channel_percentage)),
                    popularity_score=Decimal(str(row.popularity_score)),
                    rank=rank,
                )
                high_retention_topics.append(topic_popularity)

            # Create analysis result
            result = TopicDiscoveryAnalysis(
                total_users=total_users,
                total_discoveries=total_discoveries,
                discovery_paths=discovery_paths,
                top_entry_topics=top_entry_topics,
                high_retention_topics=high_retention_topics,
                analysis_date=datetime.now().isoformat(),
            )

            # Cache and return results
            self._cache_result(cache_key, result)
            return result

        # This should never be reached, but added for mypy
        return TopicDiscoveryAnalysis(
            total_users=0,
            total_discoveries=0,
            discovery_paths=[],
            top_entry_topics=[],
            high_retention_topics=[],
            analysis_date=datetime.now().isoformat(),
        )

    async def get_topic_trends(
        self, period: str = "monthly", limit_topics: int = 20, months_back: int = 12
    ) -> List[TopicTrend]:
        """
        Analyze topic popularity trends over time.

        Parameters
        ----------
        period : str
            Time period for trend analysis: "monthly", "weekly", "daily"
        limit_topics : int
            Maximum number of topics to analyze trends for
        months_back : int
            Number of months to look back for trend analysis

        Returns
        -------
        List[TopicTrend]
            Topic trend data over time
        """
        cache_key = self._get_cache_key(
            "topic_trends", period, str(limit_topics), str(months_back)
        )
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session():
            # Define period format and interval based on period parameter
            if period == "monthly":
                date_format = "YYYY-MM"
                interval = "1 month"
            elif period == "weekly":
                date_format = "YYYY-WW"  # Year-Week
                interval = "1 week"
            elif period == "daily":
                date_format = "YYYY-MM-DD"
                interval = "1 day"
            else:
                # Default to monthly
                date_format = "YYYY-MM"
                interval = "1 month"

            # Get popular topics to analyze trends for
            popular_topics = await self.get_popular_topics(
                metric="combined", limit=limit_topics
            )

            if not popular_topics:
                return []

            topic_ids = [topic.topic_id for topic in popular_topics]

            # Generate trend analysis query
            trends_query = text(
                f"""
                WITH date_series AS (
                    SELECT 
                        generate_series(
                            date_trunc('{period}', NOW() - INTERVAL '{months_back} months'),
                            date_trunc('{period}', NOW()),
                            INTERVAL '{interval}'
                        ) AS period_date
                ),
                topic_periods AS (
                    SELECT 
                        tc.topic_id,
                        tc.category_name,
                        TO_CHAR(ds.period_date, '{date_format}') as period,
                        ds.period_date,
                        
                        -- Count videos uploaded in this period
                        COALESCE(COUNT(DISTINCT CASE 
                            WHEN v.upload_date >= ds.period_date 
                                AND v.upload_date < ds.period_date + INTERVAL '{interval}'
                            THEN v.video_id 
                        END), 0) as period_videos,
                        
                        -- Count user interactions in this period
                        COALESCE(COUNT(DISTINCT CASE 
                            WHEN uv.watched_at >= ds.period_date 
                                AND uv.watched_at < ds.period_date + INTERVAL '{interval}'
                            THEN uv.user_id 
                        END), 0) as period_interactions,
                        
                        -- Count new channels added in this period  
                        COALESCE(COUNT(DISTINCT CASE 
                            WHEN c.created_at >= ds.period_date 
                                AND c.created_at < ds.period_date + INTERVAL '{interval}'
                            THEN c.channel_id 
                        END), 0) as period_channels
                        
                    FROM date_series ds
                    CROSS JOIN topic_categories tc
                    LEFT JOIN video_topics vt ON tc.topic_id = vt.topic_id
                    LEFT JOIN videos v ON vt.video_id = v.video_id
                    LEFT JOIN user_videos uv ON v.video_id = uv.video_id
                    LEFT JOIN channel_topics ct ON tc.topic_id = ct.topic_id
                    LEFT JOIN channels c ON ct.channel_id = c.channel_id
                    WHERE tc.topic_id = ANY(:topic_ids)
                    GROUP BY tc.topic_id, tc.category_name, ds.period_date
                    ORDER BY tc.topic_id, ds.period_date
                ),
                trend_calculations AS (
                    SELECT 
                        topic_id,
                        category_name,
                        period,
                        period_date,
                        period_videos,
                        period_interactions,
                        period_channels,
                        period_videos + period_interactions + period_channels as total_activity,
                        
                        -- Calculate growth rate compared to previous period
                        LAG(period_videos + period_interactions + period_channels, 1, 0) 
                            OVER (PARTITION BY topic_id ORDER BY period_date) as prev_activity,
                            
                        ROW_NUMBER() OVER (PARTITION BY topic_id ORDER BY period_date DESC) as recency_rank
                        
                    FROM topic_periods
                    WHERE period_date >= NOW() - INTERVAL '{months_back} months'
                )
                SELECT 
                    topic_id,
                    category_name,
                    period,
                    period_videos as video_count,
                    period_channels as channel_count,
                    
                    -- Calculate growth rate
                    CASE 
                        WHEN prev_activity > 0 THEN 
                            ROUND(((total_activity - prev_activity) * 100.0 / prev_activity), 2)
                        WHEN total_activity > 0 AND prev_activity = 0 THEN 100.0
                        ELSE 0.0
                    END as growth_rate,
                    
                    -- Determine trend direction
                    CASE 
                        WHEN total_activity > prev_activity THEN 'growing'
                        WHEN total_activity < prev_activity THEN 'declining' 
                        ELSE 'stable'
                    END as trend_direction
                    
                FROM trend_calculations
                WHERE recency_rank = 1  -- Only get the most recent period for each topic
                    AND total_activity > 0  -- Only include topics with activity
                ORDER BY growth_rate DESC, total_activity DESC
            """
            )

            result = await session.execute(trends_query, {"topic_ids": topic_ids})
            rows = result.fetchall()

            # Convert to TopicTrend models
            trends = []
            for row in rows:
                trend = TopicTrend(
                    topic_id=row.topic_id,
                    category_name=row.category_name,
                    period=row.period,
                    video_count=int(row.video_count),
                    channel_count=int(row.channel_count),
                    growth_rate=Decimal(str(row.growth_rate)),
                    trend_direction=row.trend_direction,
                )
                trends.append(trend)

            # Cache and return results
            self._cache_result(cache_key, trends)
            return trends

        # This should never be reached, but added for mypy
        return []

    async def get_topic_insights(
        self, user_id: str = "default_user", limit_per_category: int = 5
    ) -> TopicInsightCollection:
        """
        Generate personalized topic insights and recommendations for a user.

        Parameters
        ----------
        user_id : str
            User identifier for personalized analysis
        limit_per_category : int
            Maximum number of insights per category

        Returns
        -------
        TopicInsightCollection
            Complete topic insights analysis with recommendations
        """
        cache_key = self._get_cache_key(
            "topic_insights", user_id, str(limit_per_category)
        )
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session():
            # Get user's total watch time and topic exploration
            user_stats_query = text(
                """
                WITH user_topic_stats AS (
                    SELECT 
                        uv.user_id,
                        vt.topic_id,
                        tc.category_name,
                        COUNT(DISTINCT uv.video_id) as videos_watched,
                        SUM(COALESCE(uv.watch_duration, 0)) as total_watch_seconds,
                        AVG(COALESCE(uv.completion_percentage, 0)) as avg_completion,
                        COUNT(CASE WHEN uv.liked THEN 1 END) as likes_given,
                        COUNT(CASE WHEN uv.saved_to_playlist THEN 1 END) as saves_made
                    FROM user_videos uv
                    JOIN video_topics vt ON uv.video_id = vt.video_id
                    JOIN topic_categories tc ON vt.topic_id = tc.topic_id
                    WHERE uv.user_id = :user_id AND uv.watched_at IS NOT NULL
                    GROUP BY uv.user_id, vt.topic_id, tc.category_name
                ),
                user_totals AS (
                    SELECT 
                        COUNT(DISTINCT topic_id) as topics_explored,
                        SUM(total_watch_seconds) as total_watch_seconds,
                        AVG(avg_completion) as overall_avg_completion
                    FROM user_topic_stats
                )
                SELECT 
                    uts.topic_id,
                    uts.category_name,
                    uts.videos_watched,
                    uts.total_watch_seconds,
                    uts.avg_completion,
                    uts.likes_given,
                    uts.saves_made,
                    ut.topics_explored,
                    ut.total_watch_seconds as user_total_seconds,
                    ut.overall_avg_completion
                FROM user_topic_stats uts
                CROSS JOIN user_totals ut
                ORDER BY uts.total_watch_seconds DESC
            """
            )

            user_stats_result = await session.execute(
                user_stats_query, {"user_id": user_id}
            )
            user_stats_rows = user_stats_result.fetchall()

            if not user_stats_rows:
                # No user data found, return empty insights
                return TopicInsightCollection(
                    user_id=user_id,
                    total_watched_hours=Decimal("0.0"),
                    topics_explored=0,
                    emerging_interests=[],
                    dominant_interests=[],
                    underexplored_topics=[],
                    similar_recommendations=[],
                    diversity_score=Decimal("0.0"),
                    exploration_trend="stable",
                    analysis_date=datetime.now().isoformat(),
                )

            # Process user data
            topics_explored = user_stats_rows[0].topics_explored
            total_watch_hours = Decimal(
                str(user_stats_rows[0].user_total_seconds / 3600)
            )
            overall_avg_completion = Decimal(
                str(user_stats_rows[0].overall_avg_completion)
            )

            # Calculate diversity score (based on even distribution of watch time across topics)
            watch_time_distribution = []
            user_topic_data = {}

            for row in user_stats_rows:
                watch_hours = Decimal(str(row.total_watch_seconds / 3600))
                completion_rate = Decimal(str(row.avg_completion))
                engagement_score = (
                    completion_rate
                    + Decimal(str(row.likes_given * 10 + row.saves_made * 5))
                ) / 100

                watch_time_distribution.append(float(watch_hours))
                user_topic_data[row.topic_id] = {
                    "category_name": row.category_name,
                    "watch_hours": watch_hours,
                    "completion_rate": completion_rate,
                    "engagement_score": engagement_score,
                    "videos_watched": row.videos_watched,
                    "likes_given": row.likes_given,
                    "saves_made": row.saves_made,
                }

            # Calculate diversity using coefficient of variation (lower = more diverse)
            if len(watch_time_distribution) > 1:
                import statistics

                mean_time = statistics.mean(watch_time_distribution)
                if mean_time > 0:
                    cv = statistics.stdev(watch_time_distribution) / mean_time
                    diversity_score = max(
                        Decimal("0.0"), Decimal("1.0") - Decimal(str(cv))
                    )
                else:
                    diversity_score = Decimal("0.0")
            else:
                diversity_score = Decimal("0.0")

            # Identify dominant interests (top engagement and watch time)
            dominant_interests = []
            sorted_topics = sorted(
                user_topic_data.items(),
                key=lambda x: (x[1]["engagement_score"], x[1]["watch_hours"]),
                reverse=True,
            )

            for topic_id, data in sorted_topics[:limit_per_category]:
                vs_avg = data["engagement_score"] - (overall_avg_completion / 100)

                insight = TopicInsight(
                    topic_id=topic_id,
                    category_name=data["category_name"],
                    insight_type="dominant",
                    confidence_score=min(Decimal("1.0"), data["engagement_score"]),
                    user_engagement=data["engagement_score"],
                    watch_time_hours=data["watch_hours"],
                    completion_rate=data["completion_rate"],
                    recommendation_reason=f"Your top interest with {data['watch_hours']:.1f}h watched and {data['completion_rate']:.0f}% completion rate",
                    potential_interest_score=min(
                        Decimal("1.0"), data["engagement_score"]
                    ),
                    suggested_content_count=data["videos_watched"],
                    vs_average_engagement=vs_avg,
                    growth_potential="high" if vs_avg > Decimal("0.2") else "medium",
                )
                dominant_interests.append(insight)

            # Identify emerging interests (recent engagement growth)
            emerging_interests_query = text(
                """
                WITH recent_activity AS (
                    SELECT 
                        vt.topic_id,
                        tc.category_name,
                        COUNT(CASE WHEN uv.watched_at >= NOW() - INTERVAL '30 days' THEN 1 END) as recent_videos,
                        COUNT(CASE WHEN uv.watched_at >= NOW() - INTERVAL '60 days' 
                                     AND uv.watched_at < NOW() - INTERVAL '30 days' THEN 1 END) as prev_videos,
                        AVG(CASE WHEN uv.watched_at >= NOW() - INTERVAL '30 days' 
                                 THEN COALESCE(uv.completion_percentage, 0) END) as recent_completion,
                        COUNT(CASE WHEN uv.watched_at >= NOW() - INTERVAL '30 days' AND uv.liked THEN 1 END) as recent_likes
                    FROM user_videos uv
                    JOIN video_topics vt ON uv.video_id = vt.video_id
                    JOIN topic_categories tc ON vt.topic_id = tc.topic_id
                    WHERE uv.user_id = :user_id AND uv.watched_at IS NOT NULL
                    GROUP BY vt.topic_id, tc.category_name
                    HAVING COUNT(CASE WHEN uv.watched_at >= NOW() - INTERVAL '30 days' THEN 1 END) > 0
                )
                SELECT 
                    topic_id,
                    category_name,
                    recent_videos,
                    prev_videos,
                    recent_completion,
                    recent_likes,
                    CASE 
                        WHEN prev_videos > 0 THEN (recent_videos - prev_videos) * 100.0 / prev_videos
                        WHEN recent_videos > 0 THEN 100.0
                        ELSE 0.0
                    END as growth_rate
                FROM recent_activity
                WHERE topic_id NOT IN (
                    SELECT UNNEST(CAST(:dominant_topic_ids AS TEXT[]))
                )
                ORDER BY growth_rate DESC, recent_videos DESC
                LIMIT :limit_per_category
            """
            )

            dominant_topic_ids = [
                topic_id for topic_id, _ in sorted_topics[:limit_per_category]
            ]
            if not dominant_topic_ids:
                dominant_topic_ids = [""]  # Placeholder for empty case

            emerging_result = await session.execute(
                emerging_interests_query,
                {
                    "user_id": user_id,
                    "limit_per_category": limit_per_category,
                    "dominant_topic_ids": dominant_topic_ids,
                },
            )
            emerging_rows = emerging_result.fetchall()

            emerging_interests = []
            for row in emerging_rows:
                completion_rate = Decimal(str(row.recent_completion or 0))
                growth_rate = Decimal(str(row.growth_rate))
                confidence = min(
                    Decimal("1.0"), (completion_rate / 100) + (growth_rate / 200)
                )

                insight = TopicInsight(
                    topic_id=row.topic_id,
                    category_name=row.category_name,
                    insight_type="emerging",
                    confidence_score=confidence,
                    user_engagement=completion_rate / 100,
                    watch_time_hours=Decimal(str(row.recent_videos * 0.5)),  # Estimate
                    completion_rate=completion_rate,
                    recommendation_reason=f"Growing interest with {growth_rate:.0f}% increase in recent activity",
                    potential_interest_score=confidence,
                    suggested_content_count=row.recent_videos,
                    vs_average_engagement=Decimal("0.1"),  # Emerging assumption
                    growth_potential="high" if growth_rate > 50 else "medium",
                )
                emerging_interests.append(insight)

            # Find underexplored topics (low engagement but potential)
            underexplored_query = text(
                """
                WITH user_topic_stats AS (
                    SELECT 
                        vt.topic_id,
                        tc.category_name,
                        COUNT(DISTINCT uv.video_id) as videos_watched,
                        AVG(COALESCE(uv.completion_percentage, 0)) as avg_completion,
                        COUNT(CASE WHEN uv.liked THEN 1 END) as likes_given
                    FROM user_videos uv
                    JOIN video_topics vt ON uv.video_id = vt.video_id
                    JOIN topic_categories tc ON vt.topic_id = tc.topic_id
                    WHERE uv.user_id = :user_id AND uv.watched_at IS NOT NULL
                    GROUP BY vt.topic_id, tc.category_name
                    HAVING COUNT(DISTINCT uv.video_id) BETWEEN 1 AND 3
                        AND AVG(COALESCE(uv.completion_percentage, 0)) < 50
                ),
                topic_popularity AS (
                    SELECT 
                        vt.topic_id,
                        COUNT(DISTINCT uv.user_id) as total_users,
                        COUNT(DISTINCT vt.video_id) as total_videos
                    FROM video_topics vt
                    JOIN user_videos uv ON vt.video_id = uv.video_id
                    GROUP BY vt.topic_id
                )
                SELECT 
                    uts.topic_id,
                    uts.category_name,
                    uts.videos_watched,
                    uts.avg_completion,
                    uts.likes_given,
                    tp.total_users,
                    tp.total_videos
                FROM user_topic_stats uts
                JOIN topic_popularity tp ON uts.topic_id = tp.topic_id
                WHERE tp.total_users > 10  -- Only suggest popular topics
                ORDER BY tp.total_users DESC, tp.total_videos DESC
                LIMIT :limit_per_category
            """
            )

            underexplored_result = await session.execute(
                underexplored_query,
                {"user_id": user_id, "limit_per_category": limit_per_category},
            )
            underexplored_rows = underexplored_result.fetchall()

            underexplored_topics = []
            for row in underexplored_rows:
                completion_rate = Decimal(str(row.avg_completion))
                potential_score = min(
                    Decimal("1.0"), Decimal(str(row.total_users / 100))
                )

                insight = TopicInsight(
                    topic_id=row.topic_id,
                    category_name=row.category_name,
                    insight_type="underexplored",
                    confidence_score=potential_score,
                    user_engagement=completion_rate / 100,
                    watch_time_hours=Decimal(str(row.videos_watched * 0.3)),  # Estimate
                    completion_rate=completion_rate,
                    recommendation_reason=f"Popular topic ({row.total_users} users) that you've barely explored",
                    potential_interest_score=potential_score,
                    suggested_content_count=row.total_videos,
                    vs_average_engagement=Decimal("-0.2"),  # Below average assumption
                    growth_potential="high" if row.total_users > 50 else "medium",
                )
                underexplored_topics.append(insight)

            # Get similar topic recommendations based on user's top topics
            similar_recommendations = []
            if dominant_interests:
                top_topic_id = dominant_interests[0].topic_id
                similar_topics = await self.get_similar_topics(
                    topic_id=top_topic_id, min_similarity=0.3, limit=limit_per_category
                )

                for similar_topic in similar_topics:
                    # Check if user hasn't explored this topic much
                    if similar_topic.topic_id not in user_topic_data:
                        insight = TopicInsight(
                            topic_id=similar_topic.topic_id,
                            category_name=similar_topic.category_name,
                            insight_type="similar",
                            confidence_score=similar_topic.popularity_score,  # Similarity score
                            user_engagement=Decimal("0.0"),
                            watch_time_hours=Decimal("0.0"),
                            completion_rate=Decimal("0.0"),
                            recommendation_reason=f"Similar to your favorite topic '{dominant_interests[0].category_name}'",
                            potential_interest_score=similar_topic.popularity_score,
                            suggested_content_count=similar_topic.video_count,
                            vs_average_engagement=Decimal("0.0"),
                            growth_potential="medium",
                        )
                        similar_recommendations.append(insight)

            # Determine exploration trend
            exploration_trend = "stable"
            if len(emerging_interests) > len(dominant_interests):
                exploration_trend = "expanding"
            elif len(underexplored_topics) > len(dominant_interests):
                exploration_trend = "narrowing"

            result = TopicInsightCollection(
                user_id=user_id,
                total_watched_hours=total_watch_hours,
                topics_explored=topics_explored,
                emerging_interests=emerging_interests,
                dominant_interests=dominant_interests,
                underexplored_topics=underexplored_topics,
                similar_recommendations=similar_recommendations,
                diversity_score=diversity_score,
                exploration_trend=exploration_trend,
                analysis_date=datetime.now().isoformat(),
            )

            # Cache and return results
            self._cache_result(cache_key, result)
            return result

        # This should never be reached, but added for mypy
        return TopicInsightCollection(
            user_id=user_id,
            total_watched_hours=Decimal("0.0"),
            topics_explored=0,
            emerging_interests=[],
            dominant_interests=[],
            underexplored_topics=[],
            similar_recommendations=[],
            diversity_score=Decimal("0.0"),
            exploration_trend="stable",
            analysis_date=datetime.now().isoformat(),
        )

    async def generate_topic_graph_dot(
        self, min_confidence: float = 0.1, max_topics: int = 50
    ) -> str:
        """
        Generate topic relationship graph in DOT format for Graphviz visualization.

        Parameters
        ----------
        min_confidence : float
            Minimum confidence for including relationships
        max_topics : int
            Maximum number of topics to include in graph

        Returns
        -------
        str
            DOT format graph representation
        """
        cache_key = self._get_cache_key(
            "graph_dot", str(min_confidence), str(max_topics)
        )
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session():
            # Get popular topics to build graph around
            popular_topics = await self.get_popular_topics(
                metric="combined", limit=max_topics
            )

            if not popular_topics:
                return 'digraph TopicGraph {\n  "No topics found";\n}'

            # Build DOT graph
            dot_lines = [
                "digraph TopicGraph {",
                "  // Graph settings",
                "  rankdir=TB;",
                '  node [shape=ellipse, style=filled, fontname="Arial"];',
                '  edge [fontname="Arial", fontsize=10];',
                "  ",
                "  // Topic nodes",
            ]

            # Add nodes for each topic
            for topic in popular_topics:
                # Color nodes by popularity
                if topic.rank <= 5:
                    color = "#ff6b6b"  # Red for top topics
                elif topic.rank <= 10:
                    color = "#feca57"  # Yellow for popular topics
                else:
                    color = "#48dbfb"  # Blue for others

                # Create clean label
                clean_name = topic.category_name.replace('"', '\\"')
                dot_lines.append(
                    f'  "{topic.topic_id}" [label="{clean_name}\\n'
                    f'({topic.video_count}v, {topic.channel_count}c)", '
                    f'fillcolor="{color}", tooltip="{clean_name}"];'
                )

            dot_lines.extend(["  ", "  // Relationships"])

            # Get relationships for each topic
            topic_ids = [
                topic.topic_id for topic in popular_topics[:20]
            ]  # Limit for performance
            added_edges = set()  # Prevent duplicate edges

            for topic in popular_topics[:20]:  # Limit relationships for readability
                relationships = await self.get_topic_relationships(
                    topic.topic_id, min_confidence=min_confidence, limit=5
                )

                for rel in relationships.relationships:
                    # Only include edges between topics in our graph
                    if rel.topic_id in topic_ids:
                        edge_key = tuple(sorted([topic.topic_id, rel.topic_id]))
                        if edge_key not in added_edges:
                            added_edges.add(edge_key)

                            # Edge style based on confidence
                            if rel.confidence_score >= 0.5:
                                style = 'style=bold, color="#2d3436"'
                            elif rel.confidence_score >= 0.2:
                                style = 'style=solid, color="#636e72"'
                            else:
                                style = 'style=dashed, color="#b2bec3"'

                            dot_lines.append(
                                f'  "{topic.topic_id}" -> "{rel.topic_id}" '
                                f'[label="{rel.confidence_score:.2f}", {style}];'
                            )

            dot_lines.extend(
                [
                    "  ",
                    "  // Legend",
                    "  subgraph cluster_legend {",
                    '    label="Legend";',
                    "    style=filled;",
                    "    color=lightgrey;",
                    '    "legend_top" [label="Top 5", fillcolor="#ff6b6b"];',
                    '    "legend_popular" [label="Popular", fillcolor="#feca57"];',
                    '    "legend_other" [label="Others", fillcolor="#48dbfb"];',
                    "  }",
                    "}",
                ]
            )

            dot_content = "\n".join(dot_lines)

            # Cache and return
            self._cache_result(cache_key, dot_content)
            return dot_content

        # Fallback
        return 'digraph TopicGraph {\n  "Error generating graph";\n}'

    async def generate_topic_graph_json(
        self, min_confidence: float = 0.1, max_topics: int = 50
    ) -> Dict[str, Any]:
        """
        Generate topic relationship graph in JSON format for D3.js and other visualizations.

        Parameters
        ----------
        min_confidence : float
            Minimum confidence for including relationships
        max_topics : int
            Maximum number of topics to include in graph

        Returns
        -------
        Dict[str, Any]
            JSON graph with nodes and links
        """
        cache_key = self._get_cache_key(
            "graph_json", str(min_confidence), str(max_topics)
        )
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session():
            # Get popular topics to build graph around
            popular_topics = await self.get_popular_topics(
                metric="combined", limit=max_topics
            )

            if not popular_topics:
                return {"nodes": [], "links": [], "metadata": {"total_topics": 0}}

            # Build nodes
            nodes = []
            topic_index = {}  # Map topic_id to index for links

            for i, topic in enumerate(popular_topics):
                topic_index[topic.topic_id] = i

                # Determine node category
                if topic.rank <= 5:
                    category = "top"
                elif topic.rank <= 10:
                    category = "popular"
                else:
                    category = "other"

                nodes.append(
                    {
                        "id": topic.topic_id,
                        "name": topic.category_name,
                        "category": category,
                        "rank": topic.rank,
                        "video_count": topic.video_count,
                        "channel_count": topic.channel_count,
                        "total_content": topic.total_content_count,
                        "popularity_score": float(topic.popularity_score),
                        "size": min(
                            50, max(10, topic.total_content_count * 2)
                        ),  # Node size for visualization
                    }
                )

            # Build links (edges)
            links = []
            topic_ids = [topic.topic_id for topic in popular_topics]
            added_edges = set()

            for topic in popular_topics[:20]:  # Limit for performance
                relationships = await self.get_topic_relationships(
                    topic.topic_id, min_confidence=min_confidence, limit=5
                )

                for rel in relationships.relationships:
                    # Only include edges between topics in our graph
                    if rel.topic_id in topic_ids:
                        edge_key = tuple(sorted([topic.topic_id, rel.topic_id]))
                        if edge_key not in added_edges:
                            added_edges.add(edge_key)

                            # Determine link strength
                            if rel.confidence_score >= 0.5:
                                strength = "strong"
                            elif rel.confidence_score >= 0.2:
                                strength = "medium"
                            else:
                                strength = "weak"

                            links.append(
                                {
                                    "source": topic_index[topic.topic_id],
                                    "target": topic_index[rel.topic_id],
                                    "confidence": float(rel.confidence_score),
                                    "strength": strength,
                                    "shared_videos": rel.shared_videos,
                                    "shared_channels": rel.shared_channels,
                                    "relationship_type": rel.relationship_type,
                                }
                            )

            graph_data = {
                "nodes": nodes,
                "links": links,
                "metadata": {
                    "total_topics": len(nodes),
                    "total_links": len(links),
                    "min_confidence": min_confidence,
                    "max_topics": max_topics,
                    "generated_at": datetime.now().isoformat(),
                    "graph_type": "topic_relationships",
                },
            }

            # Cache and return
            self._cache_result(cache_key, graph_data)
            return graph_data

        # Fallback
        return {
            "nodes": [],
            "links": [],
            "metadata": {"error": "Failed to generate graph"},
        }

    async def get_topic_engagement_scores(
        self, topic_id: Optional[TopicId] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Calculate engagement scores for topics based on likes, views, and comments.
        
        Parameters
        ----------
        topic_id : Optional[TopicId]
            Specific topic to analyze, or None for all topics
        limit : int
            Maximum number of results to return
            
        Returns
        -------
        List[Dict[str, Any]]
            Topic engagement data with calculated scores
        """
        cache_key = self._get_cache_key("engagement_scores", str(topic_id), str(limit))
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session(echo=False):
            # Build query for engagement metrics
            query = (
                select(
                    TopicCategory.topic_id,
                    TopicCategory.category_name,
                    func.count(Video.video_id).label("video_count"),
                    func.avg(Video.like_count).label("avg_likes"),
                    func.avg(Video.view_count).label("avg_views"),
                    func.avg(Video.comment_count).label("avg_comments"),
                    func.sum(Video.like_count).label("total_likes"),
                    func.sum(Video.view_count).label("total_views"),
                    func.sum(Video.comment_count).label("total_comments"),
                    # Calculate engagement rate: (likes + comments) / views
                    func.avg(
                        (func.coalesce(Video.like_count, 0) + func.coalesce(Video.comment_count, 0)) /
                        func.nullif(Video.view_count, 0)
                    ).label("engagement_rate"),
                )
                .select_from(TopicCategory)
                .join(VideoTopic, TopicCategory.topic_id == VideoTopic.topic_id)
                .join(Video, VideoTopic.video_id == Video.video_id)
                .where(
                    and_(
                        Video.deleted_flag.is_(False),
                        Video.like_count.is_not(None),
                        Video.view_count.is_not(None),
                        Video.view_count > 0,  # Avoid division by zero
                    )
                )
                .group_by(TopicCategory.topic_id, TopicCategory.category_name)
            )

            # Filter by specific topic if provided
            if topic_id:
                query = query.where(TopicCategory.topic_id == topic_id)

            # Order by engagement rate and limit results
            query = query.order_by(desc("engagement_rate")).limit(limit)

            result = await session.execute(query)
            rows = result.fetchall()

            engagement_scores = []
            for row in rows:
                # Calculate normalized engagement score (0-100)
                engagement_rate = float(row.engagement_rate or 0)
                avg_likes = float(row.avg_likes or 0)
                avg_views = float(row.avg_views or 0) 
                avg_comments = float(row.avg_comments or 0)
                
                # Weighted engagement score considering multiple factors
                # Views get lower weight as they're easier to get than likes/comments
                view_score = min(avg_views / 10000, 100) * 0.3  # Cap at 100, weight 0.3
                like_score = min(avg_likes / 100, 100) * 0.4     # Cap at 100, weight 0.4
                comment_score = min(avg_comments / 10, 100) * 0.3 # Cap at 100, weight 0.3
                
                normalized_score = min(view_score + like_score + comment_score, 100)

                engagement_scores.append({
                    "topic_id": row.topic_id,
                    "category_name": row.category_name,
                    "video_count": row.video_count,
                    "avg_likes": round(avg_likes, 1),
                    "avg_views": round(avg_views, 1),
                    "avg_comments": round(avg_comments, 1),
                    "total_likes": int(row.total_likes or 0),
                    "total_views": int(row.total_views or 0),
                    "total_comments": int(row.total_comments or 0),
                    "engagement_rate": round(engagement_rate * 100, 3),  # Convert to percentage
                    "engagement_score": round(normalized_score, 1),
                    "engagement_tier": (
                        "High" if normalized_score >= 70 else
                        "Medium" if normalized_score >= 40 else
                        "Low"
                    ),
                })

            # Cache and return results
            self._cache_result(cache_key, engagement_scores)
            return engagement_scores

        return []

    async def get_channel_engagement_by_topic(
        self, topic_id: TopicId, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get channel engagement metrics for a specific topic.
        
        Parameters
        ----------
        topic_id : TopicId
            Topic to analyze channel engagement for
        limit : int
            Maximum number of channels to return
            
        Returns
        -------
        List[Dict[str, Any]]
            Channel engagement data for the topic
        """
        cache_key = self._get_cache_key("channel_engagement", topic_id, str(limit))
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result  # type: ignore

        async for session in db_manager.get_session(echo=False):
            query = (
                select(
                    Channel.channel_id,
                    Channel.title.label("channel_name"),
                    func.count(Video.video_id).label("video_count"),
                    func.avg(Video.like_count).label("avg_likes"),
                    func.avg(Video.view_count).label("avg_views"),
                    func.avg(Video.comment_count).label("avg_comments"),
                    func.sum(Video.like_count).label("total_likes"),
                    func.sum(Video.view_count).label("total_views"),
                    func.sum(Video.comment_count).label("total_comments"),
                )
                .select_from(Channel)
                .join(Video, Channel.channel_id == Video.channel_id)
                .join(VideoTopic, Video.video_id == VideoTopic.video_id)
                .where(
                    and_(
                        VideoTopic.topic_id == topic_id,
                        Video.deleted_flag.is_(False),
                        Video.like_count.is_not(None),
                        Video.view_count.is_not(None),
                        Video.view_count > 0,
                    )
                )
                .group_by(Channel.channel_id, Channel.title)
                .order_by(desc("total_views"))
                .limit(limit)
            )

            result = await session.execute(query)
            rows = result.fetchall()

            channel_engagement = []
            for row in rows:
                avg_likes = float(row.avg_likes or 0)
                avg_views = float(row.avg_views or 0)
                avg_comments = float(row.avg_comments or 0)
                
                # Calculate engagement rate for this channel
                engagement_rate = (avg_likes + avg_comments) / avg_views if avg_views > 0 else 0

                channel_engagement.append({
                    "channel_id": row.channel_id,
                    "channel_name": row.channel_name,
                    "video_count": row.video_count,
                    "avg_likes": round(avg_likes, 1),
                    "avg_views": round(avg_views, 1),
                    "avg_comments": round(avg_comments, 1),
                    "total_likes": int(row.total_likes or 0),
                    "total_views": int(row.total_views or 0),
                    "total_comments": int(row.total_comments or 0),
                    "engagement_rate": round(engagement_rate * 100, 3),
                })

            # Cache and return results
            self._cache_result(cache_key, channel_engagement)
            return channel_engagement

        return []

    def clear_cache(self) -> None:
        """Clear all cached analytics results."""
        self._cache.clear()
