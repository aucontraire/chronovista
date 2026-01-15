"""
Unit tests for TopicSeeder - YouTube topic hierarchy seeding.

Tests cover:
- Topic count validation (58 total: 7 parents + 51 children)
- Parent-child relationship integrity
- Topic type validation (YOUTUBE)
- Freebase ID format validation
- Idempotent seeding behavior
- Force mode (delete and re-seed)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.models.enums import TopicType
from chronovista.models.topic_category import TopicCategoryCreate
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.services.enrichment.seeders import TopicSeeder, TopicSeedResult

pytestmark = pytest.mark.asyncio


class TestTopicSeederConstants:
    """Test TopicSeeder constants and class methods."""

    def test_expected_topic_count(self) -> None:
        """Test that expected topic count is 58 (7 parents + 51 children)."""
        expected_count = TopicSeeder.get_expected_topic_count()
        assert expected_count == 58, "YouTube has 58 official topics"

    def test_parent_count(self) -> None:
        """Test that there are 7 parent (root) topics."""
        parent_count = TopicSeeder.get_parent_count()
        assert parent_count == 7, "YouTube has 7 root topic categories"

    def test_child_count(self) -> None:
        """Test that there are 51 child topics."""
        child_count = TopicSeeder.get_child_count()
        assert child_count == 51, "YouTube has 51 child topics (58 - 7)"

    def test_parent_topic_ids_structure(self) -> None:
        """Test parent topic IDs structure and format."""
        parent_ids = TopicSeeder.PARENT_TOPIC_IDS

        # Verify count
        assert len(parent_ids) == 7

        # Verify all parent IDs start with /m/ (Freebase format)
        for topic_id in parent_ids:
            assert topic_id.startswith("/m/"), f"Parent topic ID {topic_id} should use Freebase format"

        # Verify expected parent IDs
        expected_parents = {
            "/m/04rlf",   # Music
            "/m/0bzvm2",  # Gaming
            "/m/06ntj",   # Sports
            "/m/02jjt",   # Entertainment
            "/m/019_rr",  # Lifestyle
            "/m/01k8wb",  # Knowledge
            "/m/098wr",   # Society
        }
        assert parent_ids == expected_parents

    def test_all_topics_have_freebase_format(self) -> None:
        """Test that all topic IDs use Freebase format (/m/...)."""
        for topic_id in TopicSeeder.YOUTUBE_TOPICS.keys():
            assert topic_id.startswith("/m/"), f"Topic ID {topic_id} should use Freebase format"
            assert len(topic_id) > 3, f"Topic ID {topic_id} should have content after /m/"

    def test_parent_topics_have_no_parent(self) -> None:
        """Test that all parent topics have parent_id=None."""
        for topic_id in TopicSeeder.PARENT_TOPIC_IDS:
            name, parent_id, wiki_slug = TopicSeeder.YOUTUBE_TOPICS[topic_id]
            assert parent_id is None, f"Parent topic {topic_id} should have no parent"

    def test_child_topics_have_valid_parent(self) -> None:
        """Test that all child topics reference valid parent IDs."""
        for topic_id, (name, parent_id, wiki_slug) in TopicSeeder.YOUTUBE_TOPICS.items():
            if parent_id is not None:  # Child topic
                assert parent_id in TopicSeeder.YOUTUBE_TOPICS, \
                    f"Child topic {topic_id} references non-existent parent {parent_id}"
                assert parent_id in TopicSeeder.PARENT_TOPIC_IDS, \
                    f"Child topic {topic_id} references non-root parent {parent_id}"

    def test_no_duplicate_topic_names(self) -> None:
        """Test that topic names are unique across all topics."""
        topic_names = [name for name, parent_id, wiki_slug in TopicSeeder.YOUTUBE_TOPICS.values()]
        assert len(topic_names) == len(set(topic_names)), "Topic names should be unique"

    def test_get_topic_by_id(self) -> None:
        """Test retrieving topic information by ID."""
        # Test parent topic
        music_info = TopicSeeder.get_topic_by_id("/m/04rlf")
        assert music_info is not None
        assert music_info[0] == "Music"
        assert music_info[1] is None  # No parent
        assert music_info[2] == "Music"  # Wikipedia slug

        # Test child topic
        jazz_info = TopicSeeder.get_topic_by_id("/m/03_d0")
        assert jazz_info is not None
        assert jazz_info[0] == "Jazz"
        assert jazz_info[1] == "/m/04rlf"  # Parent is Music
        assert jazz_info[2] == "Jazz"  # Wikipedia slug

        # Test non-existent topic
        invalid_info = TopicSeeder.get_topic_by_id("/m/invalid")
        assert invalid_info is None

    def test_get_topics_by_parent(self) -> None:
        """Test retrieving child topics for a given parent."""
        # Test Music children (should have 14)
        music_children = TopicSeeder.get_topics_by_parent("/m/04rlf")
        assert len(music_children) == 14

        # Test Gaming children (should have 10)
        gaming_children = TopicSeeder.get_topics_by_parent("/m/0bzvm2")
        assert len(gaming_children) == 10

        # Test Sports children (should have 13)
        sports_children = TopicSeeder.get_topics_by_parent("/m/06ntj")
        assert len(sports_children) == 13

        # Test Entertainment children (should have 5)
        entertainment_children = TopicSeeder.get_topics_by_parent("/m/02jjt")
        assert len(entertainment_children) == 5

        # Test Lifestyle children (should have 9)
        lifestyle_children = TopicSeeder.get_topics_by_parent("/m/019_rr")
        assert len(lifestyle_children) == 9

        # Test Knowledge children (should have 0 - leaf category)
        knowledge_children = TopicSeeder.get_topics_by_parent("/m/01k8wb")
        assert len(knowledge_children) == 0

        # Test Society children (should have 0 - leaf category)
        society_children = TopicSeeder.get_topics_by_parent("/m/098wr")
        assert len(society_children) == 0


class TestTopicSeederInitialization:
    """Test TopicSeeder initialization."""

    def test_seeder_initialization(self) -> None:
        """Test TopicSeeder can be initialized with repository."""
        mock_repo = MagicMock(spec=TopicCategoryRepository)
        seeder = TopicSeeder(topic_repository=mock_repo)

        assert seeder.topic_repository == mock_repo


class TestTopicSeederSeeding:
    """Test TopicSeeder seeding operations."""

    async def test_seed_creates_all_topics_on_empty_database(self) -> None:
        """Test seeding creates all 58 topics when database is empty."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock repository to return False for all exists checks (empty DB)
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=False)

        # Verify result
        assert result.created == 58
        assert result.skipped == 0
        assert result.deleted == 0
        assert result.failed == 0
        assert result.total_processed == 58
        assert result.success_rate == 100.0

        # Verify session operations
        mock_session.commit.assert_called_once()

    async def test_seed_skips_existing_topics_idempotent(self) -> None:
        """Test idempotent seeding skips existing topics."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock repository to return True for all exists checks (all exist)
        mock_repo.exists = AsyncMock(return_value=True)

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=False)

        # Verify result
        assert result.created == 0
        assert result.skipped == 58
        assert result.deleted == 0
        assert result.failed == 0
        assert result.total_processed == 58
        assert result.success_rate == 100.0

    async def test_seed_partial_existing_topics(self) -> None:
        """Test seeding with some topics already existing."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock to simulate 7 parent topics exist, 51 children don't
        call_count = 0
        async def exists_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First 7 calls return True (parents exist), rest return False
            return call_count <= 7

        mock_repo.exists = AsyncMock(side_effect=exists_side_effect)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=False)

        # Verify result
        assert result.created == 51  # Only children created
        assert result.skipped == 7   # Parents skipped
        assert result.deleted == 0
        assert result.failed == 0

    async def test_seed_force_mode_deletes_and_recreates(self) -> None:
        """Test force mode deletes all existing topics and re-seeds."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock delete operation
        with patch.object(
            seeder := TopicSeeder(topic_repository=mock_repo),
            '_delete_all_youtube_topics',
            new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = 58  # All topics deleted

            # Mock repository for create operations
            mock_repo.exists = AsyncMock(return_value=False)
            mock_repo.create = AsyncMock()

            result = await seeder.seed(mock_session, force=True)

            # Verify deletion was called
            mock_delete.assert_called_once_with(mock_session)

            # Verify result
            assert result.deleted == 58
            assert result.created == 58
            assert result.skipped == 0
            assert result.failed == 0

    async def test_seed_creates_parents_before_children(self) -> None:
        """Test that parent topics are created before child topics."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        created_topics = []

        async def create_side_effect(session, obj_in):
            """Track order of topic creation."""
            created_topics.append((obj_in.topic_id, obj_in.parent_topic_id))
            return MagicMock()

        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock(side_effect=create_side_effect)

        seeder = TopicSeeder(topic_repository=mock_repo)
        await seeder.seed(mock_session, force=False)

        # Verify parents are created first (first 7 topics have no parent)
        parent_creates = [t for t in created_topics[:7] if t[1] is None]
        assert len(parent_creates) == 7, "First 7 topics should be parents"

        # Verify all remaining topics have parents
        child_creates = [t for t in created_topics[7:] if t[1] is not None]
        assert len(child_creates) == 51, "Remaining 51 topics should be children"

    async def test_seed_uses_youtube_topic_type(self) -> None:
        """Test that all seeded topics use TopicType.YOUTUBE."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        created_topic_types = []

        async def create_side_effect(session, obj_in):
            """Track topic types."""
            created_topic_types.append(obj_in.topic_type)
            return MagicMock()

        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock(side_effect=create_side_effect)

        seeder = TopicSeeder(topic_repository=mock_repo)
        await seeder.seed(mock_session, force=False)

        # Verify all topics use YOUTUBE type
        assert len(created_topic_types) == 58
        assert all(t == TopicType.YOUTUBE for t in created_topic_types)

    async def test_seed_handles_creation_errors_gracefully(self) -> None:
        """Test that seeding continues when individual topic creation fails."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock to fail on 3rd topic
        call_count = 0
        async def create_side_effect(session, obj_in):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise Exception("Database error")
            return MagicMock()

        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock(side_effect=create_side_effect)

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=False)

        # Verify result
        assert result.created == 57  # 58 - 1 failed
        assert result.failed == 1
        assert result.skipped == 0
        assert len(result.errors) == 1
        assert "Database error" in result.errors[0]

    async def test_seed_rollback_on_exception(self) -> None:
        """Test that session is rolled back on catastrophic failure."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock session commit to raise exception
        mock_session.commit = AsyncMock(side_effect=Exception("Commit failed"))
        mock_repo.exists = AsyncMock(return_value=False)
        mock_repo.create = AsyncMock()

        seeder = TopicSeeder(topic_repository=mock_repo)
        result = await seeder.seed(mock_session, force=False)

        # Verify rollback was called
        mock_session.rollback.assert_called_once()

        # Verify result indicates failure
        assert result.failed > 0
        assert len(result.errors) > 0


class TestTopicSeederDeletion:
    """Test TopicSeeder deletion operations."""

    async def test_delete_all_youtube_topics_deletes_children_first(self) -> None:
        """Test that child topics are deleted before parents (FK constraints)."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock two separate delete operations (children first, then parents)
        child_result = MagicMock()
        child_result.rowcount = 51
        parent_result = MagicMock()
        parent_result.rowcount = 7

        # Return child result first, then parent result
        mock_session.execute = AsyncMock(side_effect=[child_result, parent_result])

        seeder = TopicSeeder(topic_repository=mock_repo)
        deleted_count = await seeder._delete_all_youtube_topics(mock_session)

        # Verify correct deletion count
        assert deleted_count == 58

        # Verify flush was called
        mock_session.flush.assert_called_once()

    async def test_get_topic_count(self) -> None:
        """Test retrieving current topic count from database."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock count query
        result = MagicMock()
        result.scalar.return_value = 58
        mock_session.execute = AsyncMock(return_value=result)

        seeder = TopicSeeder(topic_repository=mock_repo)
        count = await seeder.get_topic_count(mock_session)

        assert count == 58

    async def test_get_topic_count_empty_database(self) -> None:
        """Test retrieving topic count from empty database."""
        mock_repo = AsyncMock(spec=TopicCategoryRepository)
        mock_session = AsyncMock()

        # Mock count query returning None
        result = MagicMock()
        result.scalar.return_value = None
        mock_session.execute = AsyncMock(return_value=result)

        seeder = TopicSeeder(topic_repository=mock_repo)
        count = await seeder.get_topic_count(mock_session)

        assert count == 0


class TestTopicSeedResult:
    """Test TopicSeedResult model."""

    def test_seed_result_creation(self) -> None:
        """Test basic TopicSeedResult creation."""
        result = TopicSeedResult(
            created=50,
            skipped=8,
            deleted=0,
            failed=0,
            duration_seconds=5.5
        )

        assert result.created == 50
        assert result.skipped == 8
        assert result.deleted == 0
        assert result.failed == 0
        assert result.duration_seconds == 5.5
        assert result.errors == []

    def test_seed_result_total_processed(self) -> None:
        """Test total_processed property calculation."""
        result = TopicSeedResult(created=50, skipped=8, failed=0)
        assert result.total_processed == 58

    def test_seed_result_success_rate_perfect(self) -> None:
        """Test success rate calculation with 100% success."""
        result = TopicSeedResult(created=50, skipped=8, failed=0)
        assert result.success_rate == 100.0

    def test_seed_result_success_rate_partial(self) -> None:
        """Test success rate calculation with failures."""
        result = TopicSeedResult(created=50, skipped=5, failed=3)
        # (50 + 5) / (50 + 5 + 3) = 55/58 ≈ 94.83%
        assert abs(result.success_rate - 94.83) < 0.01

    def test_seed_result_with_errors(self) -> None:
        """Test TopicSeedResult with error messages."""
        errors = ["Error 1", "Error 2", "Error 3"]
        result = TopicSeedResult(created=55, failed=3, errors=errors)

        assert result.errors == errors
        assert len(result.errors) == 3
