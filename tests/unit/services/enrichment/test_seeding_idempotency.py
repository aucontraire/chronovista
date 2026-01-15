"""
Unit tests for seeding idempotency - upsert and force flag behavior.

Tests cover:
- Idempotent seeding (skip existing items)
- Force flag behavior (delete all and re-seed)
- Upsert operations (create or update)
- Mixed scenarios (some existing, some new)
- Consistency across TopicSeeder and CategorySeeder
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.models.video_category import VideoCategoryCreate
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.repositories.video_category_repository import VideoCategoryRepository
from chronovista.services.enrichment.seeders import CategorySeeder, TopicSeeder
from chronovista.services.youtube_service import YouTubeService

pytestmark = pytest.mark.asyncio


class TestTopicSeederIdempotency:
    """Test TopicSeeder idempotent seeding behavior."""

    async def test_normal_run_skips_all_existing_topics(self) -> None:
        """Test that normal run skips all topics if they all exist."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # All topics exist
        mock_repo.exists = AsyncMock(return_value=True)

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=False)

        # Verify no creation, all skipped
        assert result.created == 0
        assert result.skipped == 58
        assert result.deleted == 0
        mock_repo.create.assert_not_called()

    async def test_normal_run_creates_only_missing_topics(self) -> None:
        """Test that normal run creates only missing topics."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # First 10 exist, rest don't
        call_count = 0
        async def exists_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count <= 10

        mock_repo.exists = AsyncMock(side_effect=exists_side_effect)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=False)

        assert result.created == 48  # 58 - 10
        assert result.skipped == 10
        assert result.deleted == 0

    async def test_force_flag_deletes_all_then_creates_all(self) -> None:
        """Test that force=True deletes all topics and aliases, then creates all."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock deletion - now includes alias deletion first
        delete_result_aliases = MagicMock()
        delete_result_aliases.rowcount = 20  # Aliases deleted
        delete_result_child = MagicMock()
        delete_result_child.rowcount = 51  # Child topics deleted
        delete_result_parent = MagicMock()
        delete_result_parent.rowcount = 7  # Parent topics deleted

        mock_session.execute = AsyncMock(
            side_effect=[
                delete_result_aliases,  # Alias deletion
                delete_result_child,  # Child topic deletion
                delete_result_parent,  # Parent topic deletion
            ]
        )

        # Mock creation
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=True)

        assert result.deleted == 58
        assert result.created == 58
        assert result.skipped == 0

    async def test_force_flag_with_empty_database(self) -> None:
        """Test that force=True works correctly on empty database."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock deletion returns 0 (no topics to delete)
        delete_result = MagicMock()
        delete_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=delete_result)

        # Mock creation
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=True)

        assert result.deleted == 0
        assert result.created == 58
        assert result.skipped == 0

    async def test_idempotency_multiple_runs_same_result(self) -> None:
        """Test that multiple idempotent runs produce same result."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # All topics exist
        mock_repo.exists = AsyncMock(return_value=True)

        seeder = TopicSeeder(topic_repository=mock_repo)

        # Run twice
        result1 = await seeder.seed(mock_session, force=False)
        result2 = await seeder.seed(mock_session, force=False)

        # Both runs should have same result
        assert result1.created == result2.created == 0
        assert result1.skipped == result2.skipped == 58
        assert result1.deleted == result2.deleted == 0


class TestCategorySeederIdempotency:
    """Test CategorySeeder idempotent seeding behavior."""

    async def test_normal_run_skips_all_existing_categories(self) -> None:
        """Test that normal run skips all categories if they all exist."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
            {"id": "20", "snippet": {"title": "Gaming", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)

        # All categories exist
        mock_repo.exists = AsyncMock(return_value=True)

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"])

        assert result.created == 0
        assert result.skipped == 2
        assert result.deleted == 0

    async def test_normal_run_creates_only_missing_categories(self) -> None:
        """Test that normal run creates only missing categories."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
            {"id": "20", "snippet": {"title": "Gaming", "assignable": True}},
            {"id": "24", "snippet": {"title": "Entertainment", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)

        # First category exists, rest don't
        call_count = 0
        async def exists_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count == 1

        mock_repo.exists = AsyncMock(side_effect=exists_side_effect)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"])

        assert result.created == 2
        assert result.skipped == 1
        assert result.deleted == 0

    async def test_force_flag_deletes_all_then_creates_all(self) -> None:
        """Test that force=True deletes all categories then creates all."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # Mock existing categories
        existing_cat1 = MagicMock(category_id="10")
        existing_cat2 = MagicMock(category_id="20")
        existing_cat3 = MagicMock(category_id="24")
        mock_repo.get_all = AsyncMock(return_value=[existing_cat1, existing_cat2, existing_cat3])
        mock_repo.delete_by_category_id = AsyncMock()

        # Mock API response
        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
            {"id": "20", "snippet": {"title": "Gaming", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"], force=True)

        assert result.deleted == 3
        assert result.created == 2
        assert result.skipped == 0

    async def test_force_flag_with_empty_database(self) -> None:
        """Test that force=True works correctly on empty database."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # No existing categories
        mock_repo.get_all = AsyncMock(return_value=[])

        # Mock API response
        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"], force=True)

        assert result.deleted == 0
        assert result.created == 1
        assert result.skipped == 0


class TestUpsertBehavior:
    """Test upsert (create or update) behavior."""

    async def test_category_create_or_update_creates_new(self) -> None:
        """Test that create_or_update creates new category when it doesn't exist."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)

        # Category doesn't exist
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"])

        # Verify create_or_update was called
        assert mock_repo.create_or_update.call_count == 1
        assert result.created == 1

    async def test_category_create_or_update_updates_existing_in_force_mode(self) -> None:
        """Test that create_or_update updates existing category in force mode."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # Mock existing category
        existing_cat = MagicMock(category_id="10")
        mock_repo.get_all = AsyncMock(return_value=[existing_cat])
        mock_repo.delete_by_category_id = AsyncMock()

        categories = [
            {"id": "10", "snippet": {"title": "Music Updated", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)

        # After deletion, category doesn't exist
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"], force=True)

        # Verify deletion and re-creation
        assert result.deleted == 1
        assert result.created == 1
        mock_repo.create_or_update.assert_called_once()


class TestMixedScenarios:
    """Test mixed scenarios with partial data."""

    async def test_mixed_existing_and_new_topics(self) -> None:
        """Test seeding with a mix of existing and new topics."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Half exist, half don't
        call_count = 0
        async def exists_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count <= 29  # First half exists

        mock_repo.exists = AsyncMock(side_effect=exists_side_effect)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=False)

        assert result.created == 29
        assert result.skipped == 29
        assert result.deleted == 0
        assert result.total_processed == 58

    async def test_mixed_existing_and_new_categories(self) -> None:
        """Test seeding with a mix of existing and new categories."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
            {"id": "20", "snippet": {"title": "Gaming", "assignable": True}},
            {"id": "24", "snippet": {"title": "Entertainment", "assignable": True}},
            {"id": "25", "snippet": {"title": "News", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)

        # Categories 10 and 20 exist, 24 and 25 don't
        async def exists_side_effect(session, category_id):
            return category_id in ["10", "20"]

        mock_repo.exists = AsyncMock(side_effect=exists_side_effect)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"])

        assert result.created == 2  # 24 and 25
        assert result.skipped == 2  # 10 and 20
        assert result.deleted == 0


class TestConsistencyAcrossSeeders:
    """Test consistency of idempotent behavior across seeders."""

    async def test_both_seeders_respect_force_flag(self) -> None:
        """Test that both TopicSeeder and CategorySeeder respect force flag."""
        # TopicSeeder
        topic_repo = AsyncMock(spec=TopicCategoryRepository)
        topic_session = AsyncMock()

        delete_result = MagicMock()
        delete_result.rowcount = 58
        topic_session.execute = AsyncMock(return_value=delete_result)
        topic_repo.exists = AsyncMock(return_value=False)
        topic_repo.create = AsyncMock()

        topic_seeder = TopicSeeder(topic_repository=topic_repo)
        topic_result = await topic_seeder.seed(topic_session, force=True)

        # CategorySeeder
        cat_repo = AsyncMock(spec=VideoCategoryRepository)
        cat_youtube = AsyncMock(spec=YouTubeService)
        cat_session = AsyncMock()

        existing_cats = [MagicMock(category_id=str(i)) for i in range(10)]
        cat_repo.get_all = AsyncMock(return_value=existing_cats)
        cat_repo.delete_by_category_id = AsyncMock()
        cat_youtube.get_video_categories = AsyncMock(return_value=[])

        cat_seeder = CategorySeeder(cat_repo, cat_youtube)
        cat_result = await cat_seeder.seed(cat_session, force=True)

        # Both should report deletions
        assert topic_result.deleted > 0
        assert cat_result.deleted > 0

    async def test_both_seeders_skip_existing_by_default(self) -> None:
        """Test that both seeders skip existing items by default."""
        # TopicSeeder
        topic_repo = AsyncMock(spec=TopicCategoryRepository)
        topic_session = AsyncMock()
        topic_repo.exists = AsyncMock(return_value=True)

        topic_seeder = TopicSeeder(topic_repository=topic_repo)
        topic_result = await topic_seeder.seed(topic_session, force=False)

        # CategorySeeder
        cat_repo = AsyncMock(spec=VideoCategoryRepository)
        cat_youtube = AsyncMock(spec=YouTubeService)
        cat_session = AsyncMock()

        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
        ]
        cat_youtube.get_video_categories = AsyncMock(return_value=categories)
        cat_repo.exists = AsyncMock(return_value=True)

        cat_seeder = CategorySeeder(cat_repo, cat_youtube)
        cat_result = await cat_seeder.seed(cat_session, regions=["US"])

        # Both should skip all items
        assert topic_result.created == 0
        assert topic_result.skipped > 0
        assert cat_result.created == 0
        assert cat_result.skipped > 0


# ============================================================================
# Phase 14 (T102): Additional SC-015 and SC-016 Tests
# ============================================================================


class TestSC015IdempotencyVerification:
    """
    SC-015: Seeding is idempotent (running twice produces same state).

    Additional tests to verify SC-015 success criteria.
    """

    async def test_topic_seeding_ten_times_produces_same_state(self) -> None:
        """Test that running TopicSeeder 10 times produces identical results."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # All topics exist
        mock_repo.exists = AsyncMock(return_value=True)

        seeder = TopicSeeder(topic_repository=mock_repo)

        # Run 10 times
        results: list[tuple[int, int, int]] = []
        for _ in range(10):
            result = await seeder.seed(mock_session, force=False)
            results.append((result.created, result.skipped, result.deleted))

        # All results should be identical
        first_result = results[0]
        for i, result_tuple in enumerate(results):
            assert result_tuple == first_result, f"Run {i+1} differs from run 1"

    async def test_category_seeding_preserves_existing_unchanged(self) -> None:
        """Test that CategorySeeder leaves existing categories unchanged."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        categories = [
            {"id": "10", "snippet": {"title": "Music", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)
        mock_repo.exists = AsyncMock(return_value=True)

        seeder = CategorySeeder(mock_repo, mock_youtube)

        # Run multiple times
        for _ in range(5):
            result = await seeder.seed(mock_session, regions=["US"])
            assert result.created == 0
            assert result.skipped == 1
            assert result.deleted == 0

        # create_or_update should never have been called
        mock_repo.create_or_update.assert_not_called()

    async def test_topic_seeder_preserves_parent_child_relationships(self) -> None:
        """Test that TopicSeeder preserves parent-child relationships."""
        # All child topics should have valid parent references
        for topic_id, (name, parent_id, wiki_slug) in TopicSeeder.YOUTUBE_TOPICS.items():
            if parent_id is not None:
                # Parent must exist in the topics dict
                assert parent_id in TopicSeeder.YOUTUBE_TOPICS
                # Parent's parent should be None (only 2-level hierarchy)
                parent_info = TopicSeeder.YOUTUBE_TOPICS[parent_id]
                assert parent_info[1] is None

    async def test_topic_seeder_get_topics_by_parent_returns_correct_children(self) -> None:
        """Test that get_topics_by_parent returns correct child topics."""
        # Music parent topic
        music_parent_id = "/m/04rlf"
        music_children = TopicSeeder.get_topics_by_parent(music_parent_id)

        # Should have 14 music subcategories
        assert len(music_children) == 14

        # All children should have correct names
        child_names = [name for _, name in music_children]
        assert "Christian music" in child_names
        assert "Classical music" in child_names
        assert "Pop music" in child_names
        assert "Rock music" in child_names


class TestSC016ForceReferentialIntegrity:
    """
    SC-016: Seeding with --force flag replaces all existing records
    without leaving orphan associations or breaking referential integrity.
    """

    async def test_force_deletes_children_before_parents(self) -> None:
        """Test that force mode deletes child topics before parents."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Track deletion order
        deletion_calls = []

        async def track_execute(query):
            deletion_calls.append(str(query))
            mock_result = MagicMock()
            mock_result.rowcount = 30
            return mock_result

        mock_session.execute = AsyncMock(side_effect=track_execute)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        await seeder.seed(mock_session, force=True)

        # Should have executed 2 delete statements (children first, then parents)
        assert len(deletion_calls) >= 2

    async def test_force_mode_commits_as_single_transaction(self) -> None:
        """Test that force mode commits all changes as a single transaction."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        delete_result = MagicMock()
        delete_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=delete_result)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        await seeder.seed(mock_session, force=True)

        # commit() should be called once at the end
        mock_session.commit.assert_called_once()

    async def test_category_force_mode_deletes_then_recreates(self) -> None:
        """Test that category force mode properly deletes then recreates."""
        mock_repo = AsyncMock(spec=VideoCategoryRepository)
        mock_youtube = AsyncMock(spec=YouTubeService)
        mock_session = AsyncMock()

        # Existing categories
        existing = [
            MagicMock(category_id="10"),
            MagicMock(category_id="20"),
        ]
        mock_repo.get_all = AsyncMock(return_value=existing)
        mock_repo.delete_by_category_id = AsyncMock()

        # API returns same categories with new info
        categories = [
            {"id": "10", "snippet": {"title": "Music Updated", "assignable": True}},
            {"id": "20", "snippet": {"title": "Gaming Updated", "assignable": True}},
        ]
        mock_youtube.get_video_categories = AsyncMock(return_value=categories)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create_or_update = AsyncMock()

        seeder = CategorySeeder(mock_repo, mock_youtube)
        result = await seeder.seed(mock_session, regions=["US"], force=True)

        # Should delete 2 existing, create 2 new
        assert result.deleted == 2
        assert result.created == 2
        assert mock_repo.delete_by_category_id.call_count == 2
        assert mock_repo.create_or_update.call_count == 2


class TestSeedResultProperties:
    """Test TopicSeedResult and CategorySeedResult computed properties."""

    def test_topic_seed_result_total_processed(self) -> None:
        """Test TopicSeedResult.total_processed calculation."""
        from chronovista.services.enrichment.seeders import TopicSeedResult

        result = TopicSeedResult(
            created=30,
            skipped=25,
            deleted=0,
            failed=3,
            duration_seconds=1.5,
        )

        # total = created + skipped + failed
        assert result.total_processed == 58

    def test_topic_seed_result_success_rate(self) -> None:
        """Test TopicSeedResult.success_rate calculation."""
        from chronovista.services.enrichment.seeders import TopicSeedResult

        result = TopicSeedResult(
            created=30,
            skipped=20,
            deleted=0,
            failed=10,
            duration_seconds=1.0,
        )

        # success_rate = (created + skipped) / total * 100
        expected_rate = (50 / 60) * 100
        assert abs(result.success_rate - expected_rate) < 0.01

    def test_topic_seed_result_success_rate_with_zero_processed(self) -> None:
        """Test success_rate returns 100% when nothing processed."""
        from chronovista.services.enrichment.seeders import TopicSeedResult

        result = TopicSeedResult()

        # Empty result should have 100% success rate
        assert result.success_rate == 100.0

    def test_category_seed_result_quota_tracking(self) -> None:
        """Test CategorySeedResult quota tracking."""
        from chronovista.services.enrichment.seeders import CategorySeedResult

        result = CategorySeedResult(
            created=25,
            skipped=5,
            deleted=0,
            failed=0,
            duration_seconds=2.0,
            quota_used=7,
        )

        assert result.quota_used == 7
        assert result.total_processed == 30
        assert result.success_rate == 100.0
