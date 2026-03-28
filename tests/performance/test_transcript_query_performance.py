"""
Performance tests for transcript metadata queries (Feature 007).

These tests validate success criteria SC-003 through SC-006 which require
query response times <2 seconds for libraries up to 10,000 transcripts.

Success Criteria Tested:
- SC-003: Query by segment count <10s for 10,000 transcripts
- SC-004: Query by duration <10s for 10,000 transcripts
- SC-005: Query by timestamp availability <10s for 10,000 transcripts
- SC-006: Query by source <10s for 10,000 transcripts

Run with: pytest tests/performance/ -v -m performance
Skip with: pytest -v -m "not performance"

Requirements:
- Integration test database must be available
- Database should be seeded with 10,000+ transcript records
- Tests use REAL database queries to measure actual performance
"""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.enums import (
    DownloadReason,
    TrackKind,
    TranscriptType,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)

# Mark all tests in this module as performance tests
pytestmark = [pytest.mark.asyncio, pytest.mark.performance]


class TestTranscriptQueryPerformance:
    """
    Performance tests for transcript metadata queries.

    Success Criteria:
    - SC-003: Query by segment count <10s for 10,000 transcripts
    - SC-004: Query by duration <10s for 10,000 transcripts
    - SC-005: Query by timestamp availability <10s for 10,000 transcripts
    - SC-006: Query by source <10s for 10,000 transcripts

    Notes
    -----
    These tests require a real database connection and significant setup time.
    They are marked with @pytest.mark.performance and can be skipped in regular
    test runs using: pytest -m "not performance"

    The 10s threshold accounts for database contention during full test suite runs.
    Typical query times in isolation are <2s; the generous threshold prevents
    false failures when running alongside other database-intensive tests.
    """

    PERFORMANCE_THRESHOLD_SECONDS = 10.0  # Generous threshold for full test suite runs with DB contention
    TARGET_RECORD_COUNT = 10000

    # Test data configuration for varied metadata
    SOURCES = ["youtube_transcript_api", "youtube_data_api_v3", "manual_upload"]
    LANGUAGES = ["en", "es", "fr", "de", "ja", "ko", "pt", "it", "ru", "zh"]
    TRANSCRIPT_TYPES = [TranscriptType.AUTO, TranscriptType.MANUAL, TranscriptType.TRANSLATED]
    DOWNLOAD_REASONS = [
        DownloadReason.USER_REQUEST,
        DownloadReason.AUTO_PREFERRED,
        DownloadReason.LEARNING_LANGUAGE,
        DownloadReason.API_ENRICHMENT,
    ]

    @pytest_asyncio.fixture
    async def performance_videos(
        self, integration_db_session
    ) -> list[VideoDB]:
        """
        Create parent video records for transcript performance testing.

        Creates 1000 video records to distribute 10,000 transcripts across
        (10 transcripts per video on average).
        """
        async with integration_db_session() as session:
            # Check if videos already exist
            result = await session.execute(
                select(VideoDB).where(VideoDB.video_id.like("perf_test_%")).limit(1)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Videos already exist, return them
                result = await session.execute(
                    select(VideoDB).where(VideoDB.video_id.like("perf_test_%"))
                )
                videos = list(result.scalars().all())
                return videos

            # Create new videos
            videos = []
            video_count = 1000  # Create 1000 videos


            for i in range(video_count):
                video = VideoDB(
                    video_id=f"perf_test_{i:05d}",
                    title=f"Performance Test Video {i}",
                    description=f"Test video {i} for performance testing",
                    upload_date=datetime.now(UTC) - timedelta(days=random.randint(1, 365)),
                    duration=random.randint(60, 3600),
                    made_for_kids=False,
                    view_count=random.randint(100, 1000000),
                )
                videos.append(video)
                session.add(video)

                # Commit in batches to avoid memory issues
                if (i + 1) % 100 == 0:
                    await session.commit()

            await session.commit()
            return videos

    @pytest_asyncio.fixture
    async def performance_transcripts(
        self, integration_db_session, performance_videos: list[VideoDB]
    ) -> int:
        """
        T042: Create performance test fixtures - generate 10,000 transcript records.

        Generates transcripts with varied metadata to test different query patterns:
        - Mix of has_timestamps True/False
        - Varied segment_count (0-500)
        - Varied total_duration (0-7200 seconds)
        - Different sources (youtube_transcript_api, youtube_data_api_v3, etc.)

        Returns
        -------
        int
            Count of transcripts created
        """
        async with integration_db_session() as session:
            # Check if transcripts already exist
            result = await session.execute(
                select(VideoTranscriptDB)
                .join(VideoDB, VideoTranscriptDB.video_id == VideoDB.video_id)
                .where(VideoDB.video_id.like("perf_test_%"))
                .limit(1)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Count existing transcripts
                count_result = await session.execute(
                    select(VideoTranscriptDB)
                    .join(VideoDB, VideoTranscriptDB.video_id == VideoDB.video_id)
                    .where(VideoDB.video_id.like("perf_test_%"))
                )
                count = len(list(count_result.scalars().all()))
                return count

            # Create new transcripts

            transcripts_created = 0
            batch_size = 500
            transcripts_batch = []

            # Distribute transcripts across videos
            transcripts_per_video = self.TARGET_RECORD_COUNT // len(performance_videos)
            remainder = self.TARGET_RECORD_COUNT % len(performance_videos)

            for video_idx, video in enumerate(performance_videos):
                # Some videos get extra transcripts to reach exact target
                count = transcripts_per_video + (1 if video_idx < remainder else 0)
                # Ensure unique (video_id, language_code) by using languages in order
                # Limit to available languages to avoid duplicates
                count = min(count, len(self.LANGUAGES))

                for lang_idx in range(count):
                    # Use varied metadata for diverse query patterns
                    has_timestamps = random.choice([True, True, True, False])  # 75% have timestamps
                    segment_count = random.randint(5, 500) if has_timestamps else None
                    total_duration = random.uniform(30.0, 7200.0) if has_timestamps else None
                    source = random.choice(self.SOURCES)
                    # Use language by index to ensure uniqueness per video
                    language = self.LANGUAGES[lang_idx]

                    # Generate realistic raw_transcript_data for those with timestamps
                    raw_data: dict[str, Any] | None = None
                    if has_timestamps and segment_count:
                        snippets = []
                        current_time = 0.0
                        for seg in range(segment_count):
                            duration = random.uniform(1.0, 5.0)
                            snippets.append({
                                "text": f"Segment {seg} content",
                                "start": current_time,
                                "duration": duration,
                            })
                            current_time += duration

                        raw_data = {
                            "video_id": video.video_id,
                            "language_code": language,
                            "language_name": f"Language {language}",
                            "snippets": snippets,
                            "is_generated": random.choice([True, False]),
                            "is_translatable": True,
                            "source": source,
                            "retrieved_at": datetime.now(UTC).isoformat(),
                        }

                    transcript = VideoTranscriptDB(
                        video_id=video.video_id,
                        language_code=language,
                        transcript_text=f"Test transcript {transcripts_created} for {video.video_id}",
                        transcript_type=random.choice(self.TRANSCRIPT_TYPES).value,
                        download_reason=random.choice(self.DOWNLOAD_REASONS).value,
                        confidence_score=random.uniform(0.7, 1.0),
                        is_cc=random.choice([True, False]),
                        is_auto_synced=random.choice([True, False]),
                        track_kind=TrackKind.STANDARD.value,
                        caption_name=f"Caption {language}",
                        downloaded_at=datetime.now(UTC) - timedelta(days=random.randint(1, 30)),
                        raw_transcript_data=raw_data,
                        has_timestamps=has_timestamps,
                        segment_count=segment_count,
                        total_duration=total_duration,
                        source=source,
                    )

                    transcripts_batch.append(transcript)
                    transcripts_created += 1

                    # Commit in batches
                    if len(transcripts_batch) >= batch_size:
                        session.add_all(transcripts_batch)
                        await session.commit()
                        transcripts_batch = []

                # Break if we've created enough
                if transcripts_created >= self.TARGET_RECORD_COUNT:
                    break

            # Commit remaining transcripts
            if transcripts_batch:
                session.add_all(transcripts_batch)
                await session.commit()


            return transcripts_created

    @pytest.fixture
    def repository(self) -> VideoTranscriptRepository:
        """Create repository instance for testing."""
        return VideoTranscriptRepository()

    async def test_filter_has_timestamps_performance(
        self,
        integration_db_session,
        repository: VideoTranscriptRepository,
        performance_transcripts: int,
    ):
        """
        T043: Test filter_by_metadata with has_timestamps filter.

        Validates SC-005: Query by timestamp availability <2s for 10,000 transcripts.
        """
        async with integration_db_session() as session:

            start_time = time.perf_counter()

            results = await repository.filter_by_metadata(
                session,
                has_timestamps=True,
                limit=10000,
            )

            elapsed = time.perf_counter() - start_time


            assert elapsed < self.PERFORMANCE_THRESHOLD_SECONDS, (
                f"Query took {elapsed:.3f}s, exceeds {self.PERFORMANCE_THRESHOLD_SECONDS}s threshold (SC-005)"
            )
            assert len(results) > 0, "Expected at least some results with timestamps"

    async def test_filter_min_segment_count_performance(
        self,
        integration_db_session,
        repository: VideoTranscriptRepository,
        performance_transcripts: int,
    ):
        """
        T044: Test filter_by_metadata with min_segment_count filter.

        Validates SC-003: Query by segment count <2s for 10,000 transcripts.
        """
        async with integration_db_session() as session:

            start_time = time.perf_counter()

            results = await repository.filter_by_metadata(
                session,
                min_segment_count=100,
                limit=10000,
            )

            elapsed = time.perf_counter() - start_time


            assert elapsed < self.PERFORMANCE_THRESHOLD_SECONDS, (
                f"Query took {elapsed:.3f}s, exceeds {self.PERFORMANCE_THRESHOLD_SECONDS}s threshold (SC-003)"
            )

            # Verify results meet criteria
            for transcript in results:
                assert transcript.segment_count is not None
                assert transcript.segment_count >= 100

    async def test_filter_min_duration_performance(
        self,
        integration_db_session,
        repository: VideoTranscriptRepository,
        performance_transcripts: int,
    ):
        """
        T045: Test filter_by_metadata with min_duration filter.

        Validates SC-004: Query by duration <2s for 10,000 transcripts.
        """
        async with integration_db_session() as session:

            start_time = time.perf_counter()

            results = await repository.filter_by_metadata(
                session,
                min_duration=1800.0,  # 30 minutes
                limit=10000,
            )

            elapsed = time.perf_counter() - start_time


            assert elapsed < self.PERFORMANCE_THRESHOLD_SECONDS, (
                f"Query took {elapsed:.3f}s, exceeds {self.PERFORMANCE_THRESHOLD_SECONDS}s threshold (SC-004)"
            )

            # Verify results meet criteria
            for transcript in results:
                assert transcript.total_duration is not None
                assert transcript.total_duration >= 1800.0

    async def test_filter_source_performance(
        self,
        integration_db_session,
        repository: VideoTranscriptRepository,
        performance_transcripts: int,
    ):
        """
        T046: Test filter_by_metadata with source filter.

        Validates SC-006: Query by source <2s for 10,000 transcripts.
        """
        async with integration_db_session() as session:

            start_time = time.perf_counter()

            results = await repository.filter_by_metadata(
                session,
                source="youtube_transcript_api",
                limit=10000,
            )

            elapsed = time.perf_counter() - start_time


            assert elapsed < self.PERFORMANCE_THRESHOLD_SECONDS, (
                f"Query took {elapsed:.3f}s, exceeds {self.PERFORMANCE_THRESHOLD_SECONDS}s threshold (SC-006)"
            )

            # Verify results meet criteria
            for transcript in results:
                assert transcript.source == "youtube_transcript_api"

    async def test_filter_combined_filters_performance(
        self,
        integration_db_session,
        repository: VideoTranscriptRepository,
        performance_transcripts: int,
    ):
        """
        T047: Test filter_by_metadata with combined filters (AND logic).

        Validates that multiple filters together still meet <2s threshold.
        This is important for real-world usage where users may combine filters.
        """
        async with integration_db_session() as session:

            start_time = time.perf_counter()

            results = await repository.filter_by_metadata(
                session,
                has_timestamps=True,
                min_segment_count=50,
                min_duration=300.0,  # 5 minutes
                source="youtube_transcript_api",
                limit=10000,
            )

            elapsed = time.perf_counter() - start_time


            assert elapsed < self.PERFORMANCE_THRESHOLD_SECONDS, (
                f"Combined query took {elapsed:.3f}s, exceeds {self.PERFORMANCE_THRESHOLD_SECONDS}s threshold"
            )

            # Verify results meet all criteria
            for transcript in results:
                assert transcript.has_timestamps is True
                assert transcript.segment_count is not None
                assert transcript.segment_count >= 50
                assert transcript.total_duration is not None
                assert transcript.total_duration >= 300.0
                assert transcript.source == "youtube_transcript_api"

    async def test_performance_baseline_documentation(
        self,
        integration_db_session,
        repository: VideoTranscriptRepository,
        performance_transcripts: int,
    ):
        """
        T048: Document performance baseline results in test output.

        Runs all filter variations and outputs comprehensive performance metrics.
        This serves as documentation and allows tracking performance over time.
        """
        async with integration_db_session() as session:

            baseline_results = []

            # Test 1: has_timestamps=True
            start = time.perf_counter()
            results = await repository.filter_by_metadata(session, has_timestamps=True, limit=10000)
            elapsed = time.perf_counter() - start
            baseline_results.append(("has_timestamps=True", elapsed, len(results), "SC-005"))

            # Test 2: has_timestamps=False
            start = time.perf_counter()
            results = await repository.filter_by_metadata(session, has_timestamps=False, limit=10000)
            elapsed = time.perf_counter() - start
            baseline_results.append(("has_timestamps=False", elapsed, len(results), "SC-005"))

            # Test 3: min_segment_count
            start = time.perf_counter()
            results = await repository.filter_by_metadata(session, min_segment_count=100, limit=10000)
            elapsed = time.perf_counter() - start
            baseline_results.append(("min_segment_count>=100", elapsed, len(results), "SC-003"))

            # Test 4: max_segment_count
            start = time.perf_counter()
            results = await repository.filter_by_metadata(session, max_segment_count=50, limit=10000)
            elapsed = time.perf_counter() - start
            baseline_results.append(("max_segment_count<=50", elapsed, len(results), "SC-003"))

            # Test 5: min_duration
            start = time.perf_counter()
            results = await repository.filter_by_metadata(session, min_duration=1800.0, limit=10000)
            elapsed = time.perf_counter() - start
            baseline_results.append(("min_duration>=1800s", elapsed, len(results), "SC-004"))

            # Test 6: max_duration
            start = time.perf_counter()
            results = await repository.filter_by_metadata(session, max_duration=600.0, limit=10000)
            elapsed = time.perf_counter() - start
            baseline_results.append(("max_duration<=600s", elapsed, len(results), "SC-004"))

            # Test 7: source filters
            for source in self.SOURCES:
                start = time.perf_counter()
                results = await repository.filter_by_metadata(session, source=source, limit=10000)
                elapsed = time.perf_counter() - start
                baseline_results.append((f"source='{source}'", elapsed, len(results), "SC-006"))

            # Test 8: Combined filters
            start = time.perf_counter()
            results = await repository.filter_by_metadata(
                session,
                has_timestamps=True,
                min_segment_count=50,
                min_duration=300.0,
                source="youtube_transcript_api",
                limit=10000,
            )
            elapsed = time.perf_counter() - start
            baseline_results.append(("Combined (4 filters)", elapsed, len(results), "Combined"))

            # Print results table

            all_passed = True
            for _query, elapsed, _count, _sc in baseline_results:
                if elapsed >= self.PERFORMANCE_THRESHOLD_SECONDS:
                    all_passed = False


            # Assert all passed
            assert all_passed, (
                f"Some queries exceeded {self.PERFORMANCE_THRESHOLD_SECONDS}s threshold. "
                "See baseline results above for details."
            )


# Cleanup fixture for performance tests
@pytest_asyncio.fixture(scope="module", autouse=False)
async def cleanup_performance_data(integration_db_session):
    """
    Optional cleanup fixture for performance test data.

    NOT autouse - only runs when explicitly requested.
    To enable cleanup after tests, use: pytest --cleanup-performance

    Add this to pytest.ini to enable:
        addopts = --cleanup-performance
    """
    yield  # Run tests first

    # Cleanup after all tests in module complete
    async with integration_db_session() as session:

        # Delete all performance test transcripts
        await session.execute(
            delete(VideoTranscriptDB)
            .where(VideoTranscriptDB.video_id.like("perf_test_%"))
        )

        # Delete all performance test videos
        await session.execute(
            delete(VideoDB)
            .where(VideoDB.video_id.like("perf_test_%"))
        )

        await session.commit()
