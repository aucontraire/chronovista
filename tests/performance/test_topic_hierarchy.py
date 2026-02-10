"""Performance tests for topic hierarchy loading.

Tests NFR-002: Topic hierarchy load < 500ms for 1000 topics.

This test suite validates that the topic hierarchy endpoint can load
large topic hierarchies within the specified performance threshold.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from typing import Any, Dict, List

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TopicCategory

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


class TestTopicHierarchyPerformance:
    """Test NFR-002: Topic hierarchy load performance."""

    @pytest.fixture
    async def seed_topics(
        self,
        integration_db_session: Any,
    ) -> List[str]:
        """
        Seed database with test topics for performance testing.

        Creates a hierarchical structure of topics to simulate real-world data.

        Parameters
        ----------
        integration_db_session : DatabaseAvailabilityChecker
            Integration test database session factory.

        Returns
        -------
        List[str]
            List of created topic IDs.
        """
        topic_ids: List[str] = []

        async with integration_db_session() as session:
            # Create root topics (10 categories)
            root_topics: List[TopicCategory] = []
            for i in range(10):
                topic = TopicCategory(
                    topic_id=f"/perf/root_{i}",
                    category_name=f"Root Category {i}",
                    parent_topic_id=None,
                    topic_type="freebase",
                    source="performance_test",
                )
                session.add(topic)
                root_topics.append(topic)
                topic_ids.append(topic.topic_id)

            # Create first-level children (10 per root = 100 total)
            first_level: List[TopicCategory] = []
            for root in root_topics:
                for j in range(10):
                    topic = TopicCategory(
                        topic_id=f"{root.topic_id}/child_{j}",
                        category_name=f"Child {j} of {root.category_name}",
                        parent_topic_id=root.topic_id,
                        topic_type="freebase",
                        source="performance_test",
                    )
                    session.add(topic)
                    first_level.append(topic)
                    topic_ids.append(topic.topic_id)

            # Create second-level children (9 per first-level = 900 total)
            # This gives us 10 + 100 + 900 = 1010 topics total
            for parent in first_level:
                for k in range(9):
                    topic = TopicCategory(
                        topic_id=f"{parent.topic_id}/leaf_{k}",
                        category_name=f"Leaf {k} of {parent.category_name}",
                        parent_topic_id=parent.topic_id,
                        topic_type="freebase",
                        source="performance_test",
                    )
                    session.add(topic)
                    topic_ids.append(topic.topic_id)

            await session.commit()

        return topic_ids

    @pytest.fixture
    async def cleanup_topics(
        self,
        integration_db_session: Any,
        seed_topics: List[str],
    ) -> AsyncGenerator[None, None]:
        """
        Clean up seeded topics after test.

        Parameters
        ----------
        integration_db_session : DatabaseAvailabilityChecker
            Integration test database session factory.
        seed_topics : List[str]
            List of topic IDs to clean up.
        """
        yield  # Allow test to run

        # Cleanup after test
        async with integration_db_session() as session:
            for topic_id in reversed(seed_topics):  # Delete leaves first
                result = await session.execute(
                    select(TopicCategory).where(TopicCategory.topic_id == topic_id)
                )
                topic = result.scalar_one_or_none()
                if topic:
                    await session.delete(topic)
            await session.commit()

    @pytest.mark.performance
    async def test_topic_hierarchy_load_under_500ms(
        self,
        integration_db_session: Any,
        seed_topics: List[str],
        cleanup_topics: None,
    ) -> None:
        """
        NFR-002: Topic hierarchy load < 500ms for 1000 topics.

        This test validates that the topic hierarchy query can handle
        1000+ topics and return results within 500ms.

        Parameters
        ----------
        integration_db_session : DatabaseAvailabilityChecker
            Integration test database session factory.
        seed_topics : List[str]
            Seeded topic IDs for the test.
        cleanup_topics : None
            Fixture to clean up topics after test.
        """
        # Verify we have at least 1000 topics
        assert len(seed_topics) >= 1000, (
            f"Expected at least 1000 topics, got {len(seed_topics)}"
        )

        async with integration_db_session() as session:
            # Warm up query (exclude from timing)
            await session.execute(select(TopicCategory).limit(1))

            # Measure query time for full hierarchy load
            times: List[float] = []
            for _ in range(5):  # Run 5 iterations for stability
                start = time.perf_counter()

                # Query all topics with their hierarchy info
                result = await session.execute(
                    select(
                        TopicCategory.topic_id,
                        TopicCategory.category_name,
                        TopicCategory.parent_topic_id,
                    )
                )
                rows = result.all()

                elapsed_ms = (time.perf_counter() - start) * 1000
                times.append(elapsed_ms)

                # Verify we got all topics
                assert len(rows) >= 1000, (
                    f"Expected at least 1000 topics in result, got {len(rows)}"
                )

            # Calculate p95 latency
            times.sort()
            p95_index = int(len(times) * 0.95)
            p95 = times[p95_index] if p95_index < len(times) else times[-1]

            # Assert p95 is under 500ms
            assert p95 < 500, (
                f"p95 latency {p95:.1f}ms exceeds 500ms target for topic hierarchy load"
            )

            # Log results for debugging
            avg = sum(times) / len(times)
            print(f"\nTopic hierarchy load performance:")
            print(f"  Topics loaded: {len(rows)}")
            print(f"  Average: {avg:.1f}ms")
            print(f"  p95: {p95:.1f}ms")
            print(f"  Max: {max(times):.1f}ms")

    @pytest.mark.performance
    async def test_topic_hierarchy_query_execution_time(
        self,
        integration_db_session: Any,
    ) -> None:
        """
        Test topic hierarchy query execution time with existing data.

        This test runs against whatever data exists in the database
        and measures the query performance without seeding.

        Parameters
        ----------
        integration_db_session : DatabaseAvailabilityChecker
            Integration test database session factory.
        """
        async with integration_db_session() as session:
            # Measure query time
            start = time.perf_counter()

            result = await session.execute(
                select(
                    TopicCategory.topic_id,
                    TopicCategory.category_name,
                    TopicCategory.parent_topic_id,
                )
            )
            rows = result.all()

            elapsed_ms = (time.perf_counter() - start) * 1000

            # Log results
            print(f"\nTopic hierarchy query (existing data):")
            print(f"  Topics loaded: {len(rows)}")
            print(f"  Execution time: {elapsed_ms:.1f}ms")

            # If we have topics, assert reasonable performance
            if len(rows) > 0:
                # Scale the threshold based on topic count
                # Base: 500ms for 1000 topics, scales linearly
                expected_threshold_ms = max(100, (len(rows) / 1000) * 500)
                assert elapsed_ms < expected_threshold_ms, (
                    f"Query took {elapsed_ms:.1f}ms for {len(rows)} topics, "
                    f"expected < {expected_threshold_ms:.1f}ms"
                )
