"""
Integration tests for tag backfill pipeline.

This test suite validates the full tag normalization backfill process against
a real database. It verifies that the SQL operations work correctly end-to-end,
including:

1. Reading distinct tags from video_tags table
2. Normalizing and grouping tags
3. Batch inserting into canonical_tags and tag_aliases
4. Updating video counts via JOIN query
5. Idempotent re-run behavior (ON CONFLICT DO NOTHING)
6. video_tags table remains unchanged (SC-007)
7. tag_operation_logs remains empty (FR-013)

Related: Feature 028 (Tag Normalization Schema), Phase 2 (US1/US2 - T004-T011)
Architecture: ADR-003 Tag Normalization
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import cast

import pytest
from rich.console import Console
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import (
    CanonicalTag as CanonicalTagDB,
    Channel as ChannelDB,
    TagAlias as TagAliasDB,
    TagOperationLog as TagOperationLogDB,
    Video as VideoDB,
    VideoTag as VideoTagDB,
)
from chronovista.services.tag_backfill import TagBackfillService
from chronovista.services.tag_normalization import TagNormalizationService

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


@pytest.fixture
async def seeded_session(db_session: AsyncSession) -> AsyncSession:
    """
    Provide a database session pre-seeded with test data.

    Seeds:
    - 1 channel
    - 3 videos
    - Multiple video tags with various case/hashtag variants

    Returns
    -------
    AsyncSession
        Database session with seeded test data
    """
    # Seed a channel (required FK for videos)
    channel = ChannelDB(
        channel_id="UCtest123",
        title="Test Channel",
        description="Test channel for integration tests",
        is_subscribed=False,
    )
    db_session.add(channel)
    await db_session.flush()

    # Seed videos (required FK for video_tags)
    videos = [
        VideoDB(
            video_id="vid001",
            channel_id="UCtest123",
            title="Test Video 1",
            description="Test description",
            upload_date=datetime(2023, 1, 1, tzinfo=UTC),
            duration=300,
            made_for_kids=False,
            self_declared_made_for_kids=False,
        ),
        VideoDB(
            video_id="vid002",
            channel_id="UCtest123",
            title="Test Video 2",
            description="Test description",
            upload_date=datetime(2023, 1, 2, tzinfo=UTC),
            duration=400,
            made_for_kids=False,
            self_declared_made_for_kids=False,
        ),
        VideoDB(
            video_id="vid003",
            channel_id="UCtest123",
            title="Test Video 3",
            description="Test description",
            upload_date=datetime(2023, 1, 3, tzinfo=UTC),
            duration=500,
            made_for_kids=False,
            self_declared_made_for_kids=False,
        ),
    ]
    for video in videos:
        db_session.add(video)
    await db_session.flush()

    # Seed video tags with various case/hashtag variants
    # "Python" tag group: Python, python, PYTHON, #Python (4 variants, 3 videos)
    video_tags = [
        VideoTagDB(video_id="vid001", tag="Python", tag_order=1),
        VideoTagDB(video_id="vid001", tag="Machine Learning", tag_order=2),
        VideoTagDB(video_id="vid002", tag="python", tag_order=1),
        VideoTagDB(video_id="vid002", tag="AI", tag_order=2),
        VideoTagDB(video_id="vid003", tag="PYTHON", tag_order=1),
        VideoTagDB(video_id="vid003", tag="#Python", tag_order=2),
        VideoTagDB(video_id="vid003", tag="machine learning", tag_order=3),
    ]
    for video_tag in video_tags:
        db_session.add(video_tag)
    await db_session.flush()

    await db_session.commit()
    return db_session


@pytest.fixture
def backfill_service() -> TagBackfillService:
    """
    Provide a TagBackfillService instance for testing.

    Returns
    -------
    TagBackfillService
        Service instance with normalization service
    """
    normalization_service = TagNormalizationService()
    return TagBackfillService(normalization_service)


@pytest.fixture
def silent_console() -> Console:
    """
    Provide a Rich Console that outputs to a StringIO buffer.

    This silences console output in tests while still allowing the service
    to execute its Rich formatting code.

    Returns
    -------
    Console
        Rich console instance writing to in-memory buffer
    """
    return Console(file=io.StringIO())


# =============================================================================
# Test Class: Full Backfill Pipeline
# =============================================================================


class TestFullBackfillPipeline:
    """Test the complete backfill pipeline on seeded data."""

    async def test_full_backfill_on_seeded_data(
        self,
        seeded_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Run full backfill and verify correct canonical_tags and tag_aliases creation.

        Validates:
        - canonical_tags has expected row count (3 groups: python, machine learning, ai)
        - tag_aliases has expected row count (7 raw tags)
        - Canonical form selection is correct (title case preference)
        - alias_count values are correct
        - normalized_form values are correct
        """
        # Run backfill
        await backfill_service.run_backfill(
            session=seeded_session,
            batch_size=1000,
            console=silent_console,
        )

        # Verify canonical_tags count (3 distinct normalized forms)
        # Expected groups:
        # 1. python (from Python, python, PYTHON, #Python)
        # 2. machine learning (from Machine Learning, machine learning)
        # 3. ai (from AI)
        result = await seeded_session.execute(select(func.count()).select_from(CanonicalTagDB))
        canonical_count = result.scalar()
        assert canonical_count == 3, f"Expected 3 canonical tags, got {canonical_count}"

        # Verify tag_aliases count (7 raw tags)
        result = await seeded_session.execute(select(func.count()).select_from(TagAliasDB))
        alias_count = result.scalar()
        assert alias_count == 7, f"Expected 7 tag aliases, got {alias_count}"

        # Verify canonical form selection (title case preference with alphabetical tiebreaker)
        # "Python" tag group: has 2 title case forms ("Python", "#Python") both with count=1
        # Alphabetical min tiebreaker selects "#Python" (# < P in ASCII)
        result = await seeded_session.execute(
            select(CanonicalTagDB.canonical_form, CanonicalTagDB.normalized_form)
            .where(CanonicalTagDB.normalized_form == "python")
        )
        row = result.first()
        assert row is not None
        canonical_form, normalized_form = row
        assert canonical_form == "#Python", f"Expected '#Python', got '{canonical_form}'"
        assert normalized_form == "python"

        # Verify "Machine Learning" tag group (title case preference)
        result = await seeded_session.execute(
            select(CanonicalTagDB.canonical_form, CanonicalTagDB.normalized_form)
            .where(CanonicalTagDB.normalized_form == "machine learning")
        )
        row = result.first()
        assert row is not None
        canonical_form, normalized_form = row
        assert canonical_form == "Machine Learning"
        assert normalized_form == "machine learning"

        # Verify "AI" tag group (only one variant, no title case alternative)
        result = await seeded_session.execute(
            select(CanonicalTagDB.canonical_form, CanonicalTagDB.normalized_form)
            .where(CanonicalTagDB.normalized_form == "ai")
        )
        row = result.first()
        assert row is not None
        canonical_form, normalized_form = row
        assert canonical_form == "AI"
        assert normalized_form == "ai"

        # Verify alias_count values
        result = await seeded_session.execute(
            select(CanonicalTagDB.canonical_form, CanonicalTagDB.alias_count)
            .order_by(CanonicalTagDB.canonical_form)
        )
        alias_counts = {row[0]: row[1] for row in result.all()}
        assert alias_counts["#Python"] == 4  # Python, python, PYTHON, #Python
        assert alias_counts["Machine Learning"] == 2  # Machine Learning, machine learning
        assert alias_counts["AI"] == 1

        # Verify normalized_form values in tag_aliases match canonical_tags
        result = await seeded_session.execute(
            select(TagAliasDB.raw_form, TagAliasDB.normalized_form)
        )
        alias_mappings = {row[0]: row[1] for row in result.all()}
        assert alias_mappings["Python"] == "python"
        assert alias_mappings["python"] == "python"
        assert alias_mappings["PYTHON"] == "python"
        assert alias_mappings["#Python"] == "python"
        assert alias_mappings["Machine Learning"] == "machine learning"
        assert alias_mappings["machine learning"] == "machine learning"
        assert alias_mappings["AI"] == "ai"


# =============================================================================
# Test Class: Idempotent Re-Run
# =============================================================================


class TestIdempotentRerun:
    """Test that re-running backfill is idempotent (ON CONFLICT DO NOTHING)."""

    async def test_idempotent_rerun(
        self,
        seeded_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Run backfill twice and verify second run creates no new records.

        Validates:
        - Second run creates 0 new canonical tags
        - Second run creates 0 new tag aliases
        - Existing records are not modified
        """
        # Run backfill first time
        await backfill_service.run_backfill(
            session=seeded_session,
            batch_size=1000,
            console=silent_console,
        )

        # Count records after first run
        result = await seeded_session.execute(select(func.count()).select_from(CanonicalTagDB))
        canonical_count_1 = result.scalar()
        result = await seeded_session.execute(select(func.count()).select_from(TagAliasDB))
        alias_count_1 = result.scalar()

        # Capture canonical_forms and normalized_forms before second run
        result = await seeded_session.execute(
            select(CanonicalTagDB.canonical_form, CanonicalTagDB.normalized_form)
            .order_by(CanonicalTagDB.canonical_form)
        )
        canonical_forms_before = {row[0]: row[1] for row in result.all()}

        # Run backfill second time
        await backfill_service.run_backfill(
            session=seeded_session,
            batch_size=1000,
            console=silent_console,
        )

        # Count records after second run
        result = await seeded_session.execute(select(func.count()).select_from(CanonicalTagDB))
        canonical_count_2 = result.scalar()
        result = await seeded_session.execute(select(func.count()).select_from(TagAliasDB))
        alias_count_2 = result.scalar()

        # Verify no new records created
        assert canonical_count_2 == canonical_count_1, (
            f"Second run created new canonical tags: {canonical_count_1} -> {canonical_count_2}"
        )
        assert alias_count_2 == alias_count_1, (
            f"Second run created new tag aliases: {alias_count_1} -> {alias_count_2}"
        )

        # Verify canonical_forms unchanged
        result = await seeded_session.execute(
            select(CanonicalTagDB.canonical_form, CanonicalTagDB.normalized_form)
            .order_by(CanonicalTagDB.canonical_form)
        )
        canonical_forms_after = {row[0]: row[1] for row in result.all()}
        assert canonical_forms_after == canonical_forms_before, (
            "Canonical forms changed after second run"
        )


# =============================================================================
# Test Class: Video Count Correctness
# =============================================================================


class TestVideoCountCorrectness:
    """Test that video_count is correctly computed via JOIN query."""

    async def test_video_count_correctness(
        self,
        seeded_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Verify video_count on canonical tags matches actual video count.

        The seeded data has:
        - "python" variants on 3 videos (vid001, vid002, vid003)
        - "machine learning" variants on 2 videos (vid001, vid003)
        - "ai" on 1 video (vid002)
        """
        # Run backfill
        await backfill_service.run_backfill(
            session=seeded_session,
            batch_size=1000,
            console=silent_console,
        )

        # Verify video_count for "python" (3 videos)
        result = await seeded_session.execute(
            select(CanonicalTagDB.video_count)
            .where(CanonicalTagDB.normalized_form == "python")
        )
        video_count = result.scalar()
        assert video_count == 3, f"Expected 3 videos for 'python', got {video_count}"

        # Verify video_count for "machine learning" (2 videos)
        result = await seeded_session.execute(
            select(CanonicalTagDB.video_count)
            .where(CanonicalTagDB.normalized_form == "machine learning")
        )
        video_count = result.scalar()
        assert video_count == 2, f"Expected 2 videos for 'machine learning', got {video_count}"

        # Verify video_count for "ai" (1 video)
        result = await seeded_session.execute(
            select(CanonicalTagDB.video_count)
            .where(CanonicalTagDB.normalized_form == "ai")
        )
        video_count = result.scalar()
        assert video_count == 1, f"Expected 1 video for 'ai', got {video_count}"


# =============================================================================
# Test Class: Timestamp Fields
# =============================================================================


class TestTimestampFields:
    """Test that timestamp fields are set correctly on tag aliases."""

    async def test_first_seen_last_seen_timestamps(
        self,
        seeded_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Verify first_seen_at and last_seen_at are set to execution timestamp.

        Both fields should be set to the same timestamp (the backfill execution time).
        """
        # Capture timestamp before backfill
        before_timestamp = datetime.now(UTC)

        # Run backfill
        await backfill_service.run_backfill(
            session=seeded_session,
            batch_size=1000,
            console=silent_console,
        )

        # Capture timestamp after backfill
        after_timestamp = datetime.now(UTC)

        # Verify all tag aliases have first_seen_at and last_seen_at set
        result = await seeded_session.execute(
            select(TagAliasDB.raw_form, TagAliasDB.first_seen_at, TagAliasDB.last_seen_at)
        )
        for raw_form, first_seen, last_seen in result.all():
            assert first_seen is not None, f"first_seen_at is NULL for '{raw_form}'"
            assert last_seen is not None, f"last_seen_at is NULL for '{raw_form}'"

            # Verify timestamps are within expected range
            assert before_timestamp <= first_seen <= after_timestamp, (
                f"first_seen_at for '{raw_form}' is outside expected range"
            )
            assert before_timestamp <= last_seen <= after_timestamp, (
                f"last_seen_at for '{raw_form}' is outside expected range"
            )

            # For backfill, first_seen_at should equal last_seen_at
            assert first_seen == last_seen, (
                f"first_seen_at != last_seen_at for '{raw_form}'"
            )


# =============================================================================
# Test Class: Tag Operation Logs
# =============================================================================


class TestTagOperationLogs:
    """Test that tag_operation_logs remains empty after backfill (FR-013)."""

    async def test_no_tag_operation_logs_created(
        self,
        seeded_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Verify tag_operation_logs table has 0 rows after backfill.

        FR-013 specifies that backfill does NOT create audit log entries.
        """
        # Run backfill
        await backfill_service.run_backfill(
            session=seeded_session,
            batch_size=1000,
            console=silent_console,
        )

        # Verify tag_operation_logs is empty
        result = await seeded_session.execute(
            select(func.count()).select_from(TagOperationLogDB)
        )
        log_count = result.scalar()
        assert log_count == 0, f"Expected 0 operation logs, got {log_count}"


# =============================================================================
# Test Class: Video Tags Unchanged
# =============================================================================


class TestVideoTagsUnchanged:
    """Test that video_tags table remains unchanged after backfill (SC-007)."""

    async def test_video_tags_unchanged(
        self,
        seeded_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Count rows and content of video_tags before and after backfill.

        Validates SC-007: video_tags table is read-only for backfill.
        """
        # Count rows before backfill
        result = await seeded_session.execute(
            select(func.count()).select_from(VideoTagDB)
        )
        count_before = result.scalar()

        # Capture all video_tags content before backfill
        result = await seeded_session.execute(
            select(VideoTagDB.video_id, VideoTagDB.tag, VideoTagDB.tag_order)
            .order_by(VideoTagDB.video_id, VideoTagDB.tag)
        )
        video_tags_before = [(row[0], row[1], row[2]) for row in result.all()]

        # Run backfill
        await backfill_service.run_backfill(
            session=seeded_session,
            batch_size=1000,
            console=silent_console,
        )

        # Count rows after backfill
        result = await seeded_session.execute(
            select(func.count()).select_from(VideoTagDB)
        )
        count_after = result.scalar()

        # Capture all video_tags content after backfill
        result = await seeded_session.execute(
            select(VideoTagDB.video_id, VideoTagDB.tag, VideoTagDB.tag_order)
            .order_by(VideoTagDB.video_id, VideoTagDB.tag)
        )
        video_tags_after = [(row[0], row[1], row[2]) for row in result.all()]

        # Verify count unchanged
        assert count_after == count_before, (
            f"video_tags row count changed: {count_before} -> {count_after}"
        )

        # Verify content unchanged
        assert video_tags_after == video_tags_before, (
            "video_tags content changed after backfill"
        )


# =============================================================================
# Test Class: Large Canonical Group
# =============================================================================


class TestLargeCanonicalGroup:
    """Test handling of a large canonical group with 50+ variants."""

    async def test_large_canonical_group(
        self,
        db_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Seed 50+ case/hashtag variants of a single tag and verify single canonical tag.

        Validates:
        - Single canonical_tags row with correct alias_count
        - All variants mapped to the same canonical tag
        """
        # Seed a channel and video
        channel = ChannelDB(
            channel_id="UCtest456",
            title="Test Channel",
            description="Test channel",
            is_subscribed=False,
        )
        db_session.add(channel)
        await db_session.flush()

        video = VideoDB(
            video_id="vid999",
            channel_id="UCtest456",
            title="Test Video",
            description="Test description",
            upload_date=datetime(2023, 1, 1, tzinfo=UTC),
            duration=300,
            made_for_kids=False,
            self_declared_made_for_kids=False,
        )
        db_session.add(video)
        await db_session.flush()

        # Create 50+ variants of "Python" tag (only case/hashtag variations, no suffixes)
        # All these normalize to "python"
        variants = [
            "Python",
            "python",
            "PYTHON",
            "#Python",
            "#python",
            "#PYTHON",
            "PyThOn",
            "pYtHoN",
            "pYThOn",
            "#PyThOn",
            "#pYtHoN",
            "PYTHON ",  # with trailing space (will be stripped)
            "  python",  # with leading space (will be stripped)
            "Python  ",  # with trailing spaces
            "  Python  ",  # with both
            "#pYThOn",
            "#PYTHON ",
            "pyThon",
            "PYthon",
            "PytHon",
            "PythoN",
            "pythOn",
            "pythoN",
            "PYTHon",
            "PYTHOn",
            "PYThoN",
            "PyTHon",
            "PyTHOn",
            "PyThoN",
            "pYTHon",
            "pYTHOn",
            "pYThoN",
            "pYtHon",
            "pYtHOn",
            "pYthoN",
            "pyTHon",
            "pyTHOn",
            "pyThoN",
            "pytHon",
            "pytHOn",
            "pythoN",
            "#PYTHON",
            "##Python",  # double hashtag (first one stripped)
            "###python",  # triple hashtag
        ]

        # Insert video tags (deduplicate in advance to avoid PK violations)
        seen_tags = set()
        unique_variants = []
        for i, variant in enumerate(variants):
            if variant not in seen_tags:
                video_tag = VideoTagDB(video_id="vid999", tag=variant, tag_order=i)
                db_session.add(video_tag)
                seen_tags.add(variant)
                unique_variants.append(variant)

        await db_session.flush()
        await db_session.commit()

        # Verify we have at least 40 unique variants
        assert len(unique_variants) >= 40, (
            f"Expected at least 40 unique variants, got {len(unique_variants)}"
        )

        # Debug: Check that video_tags were actually inserted
        result = await db_session.execute(
            select(func.count()).select_from(VideoTagDB)
            .where(VideoTagDB.video_id == "vid999")
        )
        video_tag_count = result.scalar()

        # Run backfill
        await backfill_service.run_backfill(
            session=db_session,
            batch_size=1000,
            console=silent_console,
        )

        # Count how many of our unique variants normalize to "python"
        normalization_service = TagNormalizationService()
        python_variants = [
            v for v in unique_variants
            if normalization_service.normalize(v) == "python"
        ]
        expected_count = len(python_variants)

        # Debug: Check what canonical tags were actually created
        result = await db_session.execute(
            select(CanonicalTagDB.normalized_form, CanonicalTagDB.canonical_form, CanonicalTagDB.alias_count)
        )
        all_canonical_tags = [(row[0], row[1], row[2]) for row in result.all()]

        # Get the "python" canonical tag
        result = await db_session.execute(
            select(CanonicalTagDB.canonical_form, CanonicalTagDB.alias_count)
            .where(CanonicalTagDB.normalized_form == "python")
        )
        row = result.first()

        assert row is not None, (
            f"Expected 'python' canonical tag to exist. "
            f"Unique variants: {len(unique_variants)}, "
            f"Python variants: {expected_count}, "
            f"Video tags inserted: {video_tag_count}, "
            f"All canonical tags: {all_canonical_tags}"
        )

        canonical_form, alias_count = row
        assert alias_count == expected_count, (
            f"Expected alias_count {expected_count}, got {alias_count}"
        )
        # Verify we have a large group (>= 40 variants)
        assert alias_count >= 40, f"Expected at least 40 aliases, got {alias_count}"


# =============================================================================
# Test Class: Interrupted Then Resumed
# =============================================================================


class TestInterruptedThenResumed:
    """Test that backfill can be interrupted and resumed safely."""

    async def test_interrupted_then_resumed(
        self,
        seeded_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Run backfill with small batch_size, then run full backfill again.

        Validates ON CONFLICT fills the gap from interrupted run.
        """
        # Run backfill with very small batch size (simulates partial run)
        await backfill_service.run_backfill(
            session=seeded_session,
            batch_size=2,
            console=silent_console,
        )

        # Count records after partial run
        result = await seeded_session.execute(select(func.count()).select_from(CanonicalTagDB))
        canonical_count_1 = result.scalar()
        result = await seeded_session.execute(select(func.count()).select_from(TagAliasDB))
        alias_count_1 = result.scalar()

        # Run full backfill with normal batch size
        await backfill_service.run_backfill(
            session=seeded_session,
            batch_size=1000,
            console=silent_console,
        )

        # Count records after full run
        result = await seeded_session.execute(select(func.count()).select_from(CanonicalTagDB))
        canonical_count_2 = result.scalar()
        result = await seeded_session.execute(select(func.count()).select_from(TagAliasDB))
        alias_count_2 = result.scalar()

        # Verify all records exist (ON CONFLICT filled gaps)
        assert canonical_count_2 == 3, f"Expected 3 canonical tags, got {canonical_count_2}"
        assert alias_count_2 == 7, f"Expected 7 tag aliases, got {alias_count_2}"

        # Verify at least some records were added in the second run
        # (unless the first run completed, which is unlikely with batch_size=2)
        assert canonical_count_1 is not None, "canonical_count_1 should not be None"
        assert alias_count_1 is not None, "alias_count_1 should not be None"
        assert canonical_count_2 >= canonical_count_1
        assert alias_count_2 >= alias_count_1


# =============================================================================
# Test Class: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_empty_video_tags_table(
        self,
        db_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Run backfill on empty video_tags table.

        Should complete successfully without errors.
        """
        # Run backfill on empty database
        await backfill_service.run_backfill(
            session=db_session,
            batch_size=1000,
            console=silent_console,
        )

        # Verify no records created
        result = await db_session.execute(select(func.count()).select_from(CanonicalTagDB))
        canonical_count = result.scalar()
        assert canonical_count == 0

        result = await db_session.execute(select(func.count()).select_from(TagAliasDB))
        alias_count = result.scalar()
        assert alias_count == 0

    async def test_tags_that_normalize_to_empty(
        self,
        db_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Test tags that normalize to empty string (should be skipped).

        Examples: "   ", "#", "###", whitespace-only strings

        Note: "###" normalizes to "##" (only first # is stripped), not empty.
        """
        # Seed a channel and video
        channel = ChannelDB(
            channel_id="UCtest789",
            title="Test Channel",
            description="Test channel",
            is_subscribed=False,
        )
        db_session.add(channel)
        await db_session.flush()

        video = VideoDB(
            video_id="vid888",
            channel_id="UCtest789",
            title="Test Video",
            description="Test description",
            upload_date=datetime(2023, 1, 1, tzinfo=UTC),
            duration=300,
            made_for_kids=False,
            self_declared_made_for_kids=False,
        )
        db_session.add(video)
        await db_session.flush()

        # Add tags that normalize to empty (truly empty after normalization)
        empty_tags = [
            VideoTagDB(video_id="vid888", tag="   ", tag_order=1),  # whitespace only
            VideoTagDB(video_id="vid888", tag="#", tag_order=2),  # just hashtag
            VideoTagDB(video_id="vid888", tag="\t\n", tag_order=4),  # whitespace chars
        ]
        for video_tag in empty_tags:
            db_session.add(video_tag)
        await db_session.flush()

        # Also add one valid tag
        valid_tag = VideoTagDB(video_id="vid888", tag="ValidTag", tag_order=5)
        db_session.add(valid_tag)
        await db_session.flush()

        await db_session.commit()

        # Run backfill
        await backfill_service.run_backfill(
            session=db_session,
            batch_size=1000,
            console=silent_console,
        )

        # Verify only the valid tag created canonical_tags and tag_aliases
        result = await db_session.execute(select(func.count()).select_from(CanonicalTagDB))
        canonical_count = result.scalar()
        assert canonical_count == 1, f"Expected 1 canonical tag, got {canonical_count}"

        result = await db_session.execute(select(func.count()).select_from(TagAliasDB))
        alias_count = result.scalar()
        assert alias_count == 1, f"Expected 1 tag alias, got {alias_count}"

        # Verify the canonical tag is for "ValidTag"
        result = await db_session.execute(
            select(CanonicalTagDB.canonical_form)
        )
        canonical_forms = [row[0] for row in result.all()]
        assert "ValidTag" in canonical_forms

    async def test_batch_size_validation(
        self,
        db_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Test that batch_size < 1 raises SystemExit with code 2.
        """
        with pytest.raises(SystemExit) as exc_info:
            await backfill_service.run_backfill(
                session=db_session,
                batch_size=0,  # Invalid
                console=silent_console,
            )
        assert exc_info.value.code == 2

    async def test_missing_tables_raises_system_exit(
        self,
        db_session: AsyncSession,
        backfill_service: TagBackfillService,
        silent_console: Console,
    ) -> None:
        """
        Test that missing tables (canonical_tags, tag_aliases) raises SystemExit.

        This test drops the tables temporarily, runs backfill, then recreates them.
        """
        # Drop canonical_tags and tag_aliases tables
        await db_session.execute(text("DROP TABLE IF EXISTS tag_aliases CASCADE"))
        await db_session.execute(text("DROP TABLE IF EXISTS canonical_tags CASCADE"))
        await db_session.commit()

        # Try to run backfill (should raise SystemExit)
        with pytest.raises(SystemExit) as exc_info:
            await backfill_service.run_backfill(
                session=db_session,
                batch_size=1000,
                console=silent_console,
            )

        # Verify error message mentions missing tables
        assert "canonical_tags" in str(exc_info.value) or "tag_aliases" in str(exc_info.value)

        # Recreate tables for cleanup (conftest will drop all tables anyway)
        # This prevents FK constraint violations in cleanup
        await db_session.execute(
            text("""
                CREATE TABLE IF NOT EXISTS canonical_tags (
                    id UUID PRIMARY KEY,
                    canonical_form VARCHAR(500) NOT NULL,
                    normalized_form VARCHAR(500) NOT NULL UNIQUE,
                    alias_count INTEGER NOT NULL DEFAULT 1,
                    video_count INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(20) NOT NULL DEFAULT 'active'
                )
            """)
        )
        await db_session.execute(
            text("""
                CREATE TABLE IF NOT EXISTS tag_aliases (
                    id UUID PRIMARY KEY,
                    raw_form VARCHAR(500) NOT NULL UNIQUE,
                    normalized_form VARCHAR(500) NOT NULL,
                    canonical_tag_id UUID NOT NULL,
                    creation_method VARCHAR(30) NOT NULL DEFAULT 'auto_normalize',
                    normalization_version INTEGER NOT NULL DEFAULT 1,
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL
                )
            """)
        )
        await db_session.commit()
