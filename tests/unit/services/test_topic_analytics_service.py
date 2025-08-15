"""
Tests for TopicAnalyticsService.

Comprehensive test coverage for topic analytics including popularity rankings,
relationship analysis, and caching functionality.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark all async tests in this module
pytestmark = pytest.mark.asyncio

from chronovista.models.topic_analytics import (
    TopicAnalyticsSummary,
    TopicDiscoveryAnalysis,
    TopicInsightCollection,
    TopicOverlap,
    TopicPopularity,
    TopicRelationships,
    TopicTrend,
)

from chronovista.services.topic_analytics_service import TopicAnalyticsService
from tests.factories.id_factory import TestIds


class TestTopicAnalyticsServiceInitialization:
    """Tests for service initialization."""

    def test_initialization(self) -> None:
        """Test TopicAnalyticsService initialization."""
        service = TopicAnalyticsService()

        assert service.topic_category_repository is not None
        assert service.video_topic_repository is not None
        assert service.channel_topic_repository is not None
        assert service._cache == {}
        assert service._cache_ttl == 300  # 5 minutes


class TestTopicAnalyticsServiceCaching:
    """Tests for caching functionality."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    def test_cache_key_generation(self, service: TopicAnalyticsService) -> None:
        """Test cache key generation."""
        key1 = service._get_cache_key("method1", "arg1", "arg2")
        key2 = service._get_cache_key("method1", "arg1", "arg2")
        key3 = service._get_cache_key("method1", "arg1", "different")

        assert key1 == key2  # Same args should generate same key
        assert key1 != key3  # Different args should generate different key

    def test_cache_clearing(self, service: TopicAnalyticsService) -> None:
        """Test cache clearing."""
        service.clear_cache()
        assert service._cache == {}

    def test_cache_miss(self, service: TopicAnalyticsService) -> None:
        """Test cache miss with empty cache."""
        result = service._get_cached_result("nonexistent_key")
        assert result is None

    def test_cache_hit_valid_entry(self, service: TopicAnalyticsService) -> None:
        """Test cache hit with valid cache entry."""
        key = "test_key"
        now = datetime.now()
        data = {"test": "data"}
        service._cache[key] = (now, data)

        result = service._get_cached_result(key)
        assert result == data

    def test_cache_miss_expired_entry(self, service: TopicAnalyticsService) -> None:
        """Test cache miss with expired cache entry."""
        key = "test_key"
        expired_time = datetime(2020, 1, 1)
        service._cache[key] = (expired_time, {"test": "data"})

        result = service._get_cached_result(key)
        assert result is None

    def test_cache_result_storage(self, service: TopicAnalyticsService) -> None:
        """Test caching result storage."""
        key = "test_key"
        data = {"test": "data"}

        service._cache_result(key, data)

        assert key in service._cache
        cached_time, cached_data = service._cache[key]
        assert cached_data == data
        assert isinstance(cached_time, datetime)

    def test_cache_validity_check(self, service: TopicAnalyticsService) -> None:
        """Test cache validity checking."""
        now = datetime.now()
        expired = datetime(2020, 1, 1)

        assert service._is_cache_valid(now)
        assert not service._is_cache_valid(expired)


class TestTopicAnalyticsServicePopularityAnalysis:
    """Tests for topic popularity analysis using actual method signatures."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    async def test_get_popular_topics_videos_metric(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test getting popular topics by video count."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_get_session:
            mock_async_session = AsyncMock()
            
            # Mock the async iterator pattern used by get_session
            mock_get_session.return_value.__aiter__.return_value = [mock_async_session]

            # Mock total counts queries results
            mock_total_result = MagicMock()
            mock_total_result.scalar.return_value = 100

            # Mock the main database query result
            mock_main_result = MagicMock()
            mock_main_result.fetchall.return_value = [
                MagicMock(
                    topic_id=TestIds.MUSIC_TOPIC,
                    category_name="Music",
                    video_count=10,
                    channel_count=5,
                ),
                MagicMock(
                    topic_id=TestIds.GAMING_TOPIC,
                    category_name="Gaming",
                    video_count=8,
                    channel_count=3,
                ),
            ]

            # Set up the execute calls in order: total_videos, total_channels, main_query
            mock_async_session.execute.side_effect = [
                mock_total_result,  # total videos
                mock_total_result,  # total channels
                mock_main_result,   # main query
            ]

            result = await service.get_popular_topics(metric="videos", limit=2)

            assert isinstance(result, list)
            assert len(result) == 2
            assert all(isinstance(item, TopicPopularity) for item in result)

    async def test_get_popular_topics_channels_metric(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test getting popular topics by channel count."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            result = await service.get_popular_topics(metric="channels", limit=5)

            assert isinstance(result, list)

    async def test_get_popular_topics_combined_metric(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test getting popular topics by combined metric."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            result = await service.get_popular_topics(metric="combined", limit=10)

            assert isinstance(result, list)


class TestTopicAnalyticsServiceRelationshipAnalysis:
    """Tests for topic relationship analysis."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    async def test_get_topic_relationships_success(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test successful topic relationships retrieval."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            # Mock repository get method
            mock_topic = MagicMock()
            mock_topic.category_name = "Music"
            with patch.object(service.topic_category_repository, 'get', new_callable=AsyncMock, return_value=mock_topic):

                result = await service.get_topic_relationships(
                    topic_id=TestIds.MUSIC_TOPIC, min_confidence=0.1, limit=10
                )

                assert isinstance(result, TopicRelationships)
                assert result.source_topic_id == TestIds.MUSIC_TOPIC

    async def test_calculate_topic_overlap_success(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test successful topic overlap calculation."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            # Mock topic repository returns
            mock_topic1 = MagicMock()
            mock_topic1.category_name = "Music"
            mock_topic2 = MagicMock()
            mock_topic2.category_name = "Gaming"

            with patch.object(service.topic_category_repository, 'get', new_callable=AsyncMock, side_effect=[mock_topic1, mock_topic2]):

                result = await service.calculate_topic_overlap(
                    topic1_id=TestIds.MUSIC_TOPIC, topic2_id=TestIds.GAMING_TOPIC
                )

                assert isinstance(result, TopicOverlap)
                assert result.topic1_id == TestIds.MUSIC_TOPIC
                assert result.topic2_id == TestIds.GAMING_TOPIC


class TestTopicAnalyticsServiceAnalyticsSummary:
    """Tests for analytics summary functionality."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    async def test_get_analytics_summary(self, service: TopicAnalyticsService) -> None:
        """Test getting analytics summary."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            # Mock the get_popular_topics method
            mock_popular_topics = [
                TopicPopularity(
                    topic_id=TestIds.MUSIC_TOPIC,
                    category_name="Music",
                    video_count=10,
                    channel_count=5,
                    total_content_count=15,
                    video_percentage=Decimal("20.0"),
                    channel_percentage=Decimal("25.0"),
                    popularity_score=Decimal("100.0"),
                    rank=1,
                )
            ]

            with patch.object(service, 'get_popular_topics', new=AsyncMock(return_value=mock_popular_topics)):
                result = await service.get_analytics_summary()

            assert isinstance(result, TopicAnalyticsSummary)
            assert result.total_topics >= 0
            assert result.total_videos >= 0
            assert result.total_channels >= 0
            assert isinstance(result.most_popular_topics, list)
            assert isinstance(result.topic_distribution, dict)


class TestTopicAnalyticsServiceSimilarTopics:
    """Tests for similar topics functionality."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    async def test_get_similar_topics(self, service: TopicAnalyticsService) -> None:
        """Test getting similar topics."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            # Mock repository get method
            mock_topic = MagicMock()
            mock_topic.category_name = "Music"
            with patch.object(service.topic_category_repository, 'get', new_callable=AsyncMock, return_value=mock_topic):

                result = await service.get_similar_topics(
                    topic_id=TestIds.MUSIC_TOPIC, min_similarity=0.5, limit=10
                )

                assert isinstance(result, list)
                assert all(isinstance(item, TopicPopularity) for item in result)


class TestTopicAnalyticsServiceDiscoveryAnalysis:
    """Tests for topic discovery analysis."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    async def test_get_topic_discovery_analysis(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test getting topic discovery analysis."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            result = await service.get_topic_discovery_analysis(
                limit_topics=20, min_interactions=2
            )

            assert isinstance(result, TopicDiscoveryAnalysis)
            assert result.total_users >= 0
            assert result.total_discoveries >= 0
            assert isinstance(result.discovery_paths, list)
            assert isinstance(result.top_entry_topics, list)
            assert isinstance(result.high_retention_topics, list)


class TestTopicAnalyticsServiceTrends:
    """Tests for topic trends functionality."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    async def test_get_topic_trends(self, service: TopicAnalyticsService) -> None:
        """Test getting topic trends."""
        # Mock the get_popular_topics method since it's called internally
        mock_popular_topics = [
            TopicPopularity(
                topic_id=TestIds.MUSIC_TOPIC,
                category_name="Music",
                video_count=10,
                channel_count=5,
                total_content_count=15,
                video_percentage=Decimal("20.0"),
                channel_percentage=Decimal("25.0"),
                popularity_score=Decimal("100.0"),
                rank=1,
            )
        ]

        with patch.object(service, 'get_popular_topics', new=AsyncMock(return_value=mock_popular_topics)):
            with patch(
                "chronovista.config.database.db_manager.get_session"
            ) as mock_session:
                mock_async_session = AsyncMock()
                mock_session.return_value.__aenter__.return_value = mock_async_session
                mock_session.return_value.__aexit__ = AsyncMock()

                result = await service.get_topic_trends(
                    period="monthly", limit_topics=20, months_back=12
                )

            assert isinstance(result, list)
            assert all(isinstance(item, TopicTrend) for item in result)


class TestTopicAnalyticsServiceInsights:
    """Tests for topic insights functionality."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    async def test_get_topic_insights(self, service: TopicAnalyticsService) -> None:
        """Test getting topic insights."""
        # Mock the get_similar_topics method since it's called internally
        with patch.object(service, 'get_similar_topics', new=AsyncMock(return_value=[])):
            with patch(
                "chronovista.config.database.db_manager.get_session"
            ) as mock_session:
                mock_async_session = AsyncMock()
                mock_session.return_value.__aenter__.return_value = mock_async_session
                mock_session.return_value.__aexit__ = AsyncMock()

                result = await service.get_topic_insights(
                    user_id="test_user", limit_per_category=5
                )

            assert isinstance(result, TopicInsightCollection)
            assert result.user_id == "test_user"
            assert isinstance(result.emerging_interests, list)
            assert isinstance(result.dominant_interests, list)
            assert isinstance(result.underexplored_topics, list)
            assert isinstance(result.similar_recommendations, list)


class TestTopicAnalyticsServiceGraphGeneration:
    """Tests for graph generation functionality."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    async def test_generate_topic_graph_dot(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test DOT format graph generation."""
        # Mock the get_popular_topics and get_topic_relationships methods
        mock_popular_topics = [
            TopicPopularity(
                topic_id=TestIds.MUSIC_TOPIC,
                category_name="Music",
                video_count=10,
                channel_count=5,
                total_content_count=15,
                video_percentage=Decimal("20.0"),
                channel_percentage=Decimal("25.0"),
                popularity_score=Decimal("100.0"),
                rank=1,
            )
        ]

        mock_relationships = TopicRelationships(
            source_topic_id=TestIds.MUSIC_TOPIC,
            source_category_name="Music",
            total_videos=10,
            total_channels=5,
            relationships=[],
            analysis_date=datetime.now().isoformat(),
        )

        with patch.object(service, 'get_popular_topics', new=AsyncMock(return_value=mock_popular_topics)):
            with patch.object(service, 'get_topic_relationships', new=AsyncMock(return_value=mock_relationships)):
                result = await service.generate_topic_graph_dot(
                    min_confidence=0.1, max_topics=50
                )

        assert isinstance(result, str)
        assert "digraph TopicGraph" in result

    async def test_generate_topic_graph_json(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test JSON format graph generation."""
        # Mock the get_popular_topics and get_topic_relationships methods
        mock_popular_topics = [
            TopicPopularity(
                topic_id=TestIds.MUSIC_TOPIC,
                category_name="Music",
                video_count=10,
                channel_count=5,
                total_content_count=15,
                video_percentage=Decimal("20.0"),
                channel_percentage=Decimal("25.0"),
                popularity_score=Decimal("100.0"),
                rank=1,
            )
        ]

        mock_relationships = TopicRelationships(
            source_topic_id=TestIds.MUSIC_TOPIC,
            source_category_name="Music",
            total_videos=10,
            total_channels=5,
            relationships=[],
            analysis_date=datetime.now().isoformat(),
        )

        with patch.object(service, 'get_popular_topics', new=AsyncMock(return_value=mock_popular_topics)):
            with patch.object(service, 'get_topic_relationships', new=AsyncMock(return_value=mock_relationships)):
                result = await service.generate_topic_graph_json(
                    min_confidence=0.1, max_topics=50
                )

        assert isinstance(result, dict)
        assert "nodes" in result
        assert "links" in result
        assert "metadata" in result


class TestTopicAnalyticsServiceEngagement:
    """Tests for engagement scoring functionality."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    async def test_get_topic_engagement_scores(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test getting topic engagement scores."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            result = await service.get_topic_engagement_scores(topic_id=None, limit=20)

            assert isinstance(result, list)
            assert all(isinstance(item, dict) for item in result)

    async def test_get_channel_engagement_by_topic(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test getting channel engagement by topic."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            result = await service.get_channel_engagement_by_topic(
                topic_id=TestIds.MUSIC_TOPIC, limit=10
            )

            assert isinstance(result, list)
            assert all(isinstance(item, dict) for item in result)


class TestTopicAnalyticsServiceEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def service(self) -> TopicAnalyticsService:
        """Create service instance."""
        return TopicAnalyticsService()

    async def test_get_topic_relationships_nonexistent_topic(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test topic relationships for nonexistent topic."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            # Mock repository to return None (topic doesn't exist)
            with patch.object(service.topic_category_repository, 'get', new_callable=AsyncMock, return_value=None):

                result = await service.get_topic_relationships(
                    topic_id="nonexistent_topic", min_confidence=0.1, limit=10
                )

                assert isinstance(result, TopicRelationships)
                assert result.source_topic_id == "nonexistent_topic"
                assert "Unknown Topic" in result.source_category_name
                assert result.total_videos == 0
                assert result.total_channels == 0
                assert len(result.relationships) == 0

    async def test_get_popular_topics_empty_database(
        self, service: TopicAnalyticsService
    ) -> None:
        """Test popular topics with empty database."""
        with patch(
            "chronovista.config.database.db_manager.get_session"
        ) as mock_session:
            mock_async_session = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_async_session
            mock_session.return_value.__aexit__ = AsyncMock()

            # Mock empty query results
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            mock_result.scalar.return_value = 0
            mock_async_session.execute = AsyncMock(return_value=mock_result)

            result = await service.get_popular_topics(metric="videos", limit=10)

            assert isinstance(result, list)
            assert len(result) == 0

    def test_cache_key_consistency(self, service: TopicAnalyticsService) -> None:
        """Test cache key generation is consistent."""
        key1 = service._get_cache_key("method", "arg1", "arg2")
        key2 = service._get_cache_key("method", "arg1", "arg2")

        assert key1 == key2
        assert isinstance(key1, str)
        assert len(key1) > 0

    def test_cache_ttl_configuration(self, service: TopicAnalyticsService) -> None:
        """Test cache TTL is properly configured."""
        assert service._cache_ttl == 300
        assert isinstance(service._cache_ttl, int)
        assert service._cache_ttl > 0
