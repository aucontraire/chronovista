"""
Tests for CanonicalTagRepository query methods added in Feature 030.

Tests the five query methods:
- search()
- get_by_normalized_form()
- get_top_aliases()
- get_videos_by_normalized_form()
- build_canonical_tag_video_subqueries()
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import (
    CanonicalTag as CanonicalTagDB,
    TagAlias as TagAliasDB,
    Video as VideoDB,
    VideoTag,
)
from chronovista.repositories.canonical_tag_repository import CanonicalTagRepository

pytestmark = pytest.mark.asyncio


def _make_uuid() -> uuid.UUID:
    """Generate a UUIDv7 as stdlib uuid.UUID."""
    return uuid.UUID(bytes=uuid7().bytes)


def _make_canonical_tag(
    *,
    canonical_form: str = "Python",
    normalized_form: str = "python",
    status: str = "active",
    video_count: int = 100,
    alias_count: int = 5,
    entity_type: str | None = "technical_term",
) -> CanonicalTagDB:
    """Create a sample CanonicalTagDB ORM object."""
    tag = CanonicalTagDB(
        canonical_form=canonical_form,
        normalized_form=normalized_form,
        entity_type=entity_type,
        status=status,
        alias_count=alias_count,
        video_count=video_count,
    )
    return tag


def _make_tag_alias(
    *,
    raw_form: str = "Python",
    normalized_form: str = "python",
    canonical_tag_id: uuid.UUID | None = None,
    occurrence_count: int = 50,
) -> TagAliasDB:
    """Create a sample TagAliasDB ORM object."""
    alias = TagAliasDB(
        raw_form=raw_form,
        normalized_form=normalized_form,
        canonical_tag_id=canonical_tag_id or _make_uuid(),
        occurrence_count=occurrence_count,
        creation_method="auto_normalize",
        normalization_version=1,
    )
    return alias


def _make_video(
    *,
    video_id: str = "dQw4w9WgXcQ",
    title: str = "Test Video",
    upload_date: datetime | None = None,
    availability_status: str = "available",
) -> VideoDB:
    """Create a sample VideoDB ORM object."""
    video = VideoDB(
        video_id=video_id,
        title=title,
        upload_date=upload_date or datetime(2024, 6, 15, tzinfo=timezone.utc),
        duration=300,
        made_for_kids=False,
        self_declared_made_for_kids=False,
        availability_status=availability_status,
    )
    return video


class TestCanonicalTagRepositorySearch:
    """Tests for CanonicalTagRepository.search()."""

    @pytest.fixture
    def repository(self) -> CanonicalTagRepository:
        """Create repository instance."""
        return CanonicalTagRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    async def test_search_no_filter_returns_items_sorted_by_video_count(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Search without q filter returns items ordered by video_count DESC."""
        tag_a = _make_canonical_tag(canonical_form="Python", normalized_form="python", video_count=200)
        tag_b = _make_canonical_tag(canonical_form="Java", normalized_form="java", video_count=100)

        # First execute call: count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        # Second execute call: items query
        items_scalars = MagicMock()
        items_scalars.all.return_value = [tag_a, tag_b]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.search(mock_session)

        assert total == 2
        assert items == [tag_a, tag_b]
        assert mock_session.execute.call_count == 2

    async def test_search_with_q_prefix_match(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Search with q parameter applies ILIKE prefix pattern."""
        tag = _make_canonical_tag(canonical_form="Python", normalized_form="python", video_count=50)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        items_scalars = MagicMock()
        items_scalars.all.return_value = [tag]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.search(mock_session, q="pyt")

        assert total == 1
        assert items == [tag]
        assert mock_session.execute.call_count == 2

    async def test_search_with_status_filter(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Search respects status filter parameter."""
        merged_tag = _make_canonical_tag(
            canonical_form="Py", normalized_form="py", status="merged", video_count=10
        )

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        items_scalars = MagicMock()
        items_scalars.all.return_value = [merged_tag]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.search(mock_session, status="merged")

        assert total == 1
        assert items == [merged_tag]

    async def test_search_pagination_skip_and_limit(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Search applies skip and limit for pagination."""
        tag_c = _make_canonical_tag(canonical_form="Go", normalized_form="go", video_count=50)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 5  # Total is 5 but we only get 1 page

        items_scalars = MagicMock()
        items_scalars.all.return_value = [tag_c]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.search(mock_session, skip=2, limit=1)

        assert total == 5
        assert len(items) == 1
        assert items[0] == tag_c

    async def test_search_empty_results(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Search returns ([], 0) when no results match."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        items_scalars = MagicMock()
        items_scalars.all.return_value = []
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.search(mock_session, q="nonexistent")

        assert items == []
        assert total == 0


class TestCanonicalTagRepositoryGetByNormalizedForm:
    """Tests for CanonicalTagRepository.get_by_normalized_form()."""

    @pytest.fixture
    def repository(self) -> CanonicalTagRepository:
        """Create repository instance."""
        return CanonicalTagRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    async def test_found_returns_canonical_tag(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_normalized_form returns CanonicalTagDB when found."""
        tag = _make_canonical_tag(normalized_form="python")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tag
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_normalized_form(mock_session, "python")

        assert result is tag
        mock_session.execute.assert_called_once()

    async def test_not_found_returns_none(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_normalized_form returns None when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_normalized_form(mock_session, "nonexistent")

        assert result is None
        mock_session.execute.assert_called_once()

    async def test_merged_tag_excluded_by_default_status_filter(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_normalized_form with default status='active' excludes merged tags."""
        # The merged tag exists but the query filters status='active',
        # so the DB returns None for a merged tag.
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_normalized_form(mock_session, "oldtag")

        assert result is None
        mock_session.execute.assert_called_once()


class TestCanonicalTagRepositoryGetTopAliases:
    """Tests for CanonicalTagRepository.get_top_aliases()."""

    @pytest.fixture
    def repository(self) -> CanonicalTagRepository:
        """Create repository instance."""
        return CanonicalTagRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    async def test_returns_aliases_ordered_by_occurrence_count_desc(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_top_aliases returns aliases ordered by occurrence_count DESC."""
        ct_id = _make_uuid()
        alias_a = _make_tag_alias(raw_form="Python", occurrence_count=100, canonical_tag_id=ct_id)
        alias_b = _make_tag_alias(raw_form="python", occurrence_count=80, canonical_tag_id=ct_id)
        alias_c = _make_tag_alias(raw_form="PYTHON", occurrence_count=20, canonical_tag_id=ct_id)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [alias_a, alias_b, alias_c]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_top_aliases(mock_session, ct_id)

        assert result == [alias_a, alias_b, alias_c]
        assert result[0].occurrence_count > result[1].occurrence_count > result[2].occurrence_count
        mock_session.execute.assert_called_once()

    async def test_respects_limit_parameter(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_top_aliases respects the limit parameter."""
        ct_id = _make_uuid()
        alias_top = _make_tag_alias(raw_form="Python", occurrence_count=200, canonical_tag_id=ct_id)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [alias_top]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_top_aliases(mock_session, ct_id, limit=1)

        assert len(result) == 1
        assert result[0] is alias_top

    async def test_empty_list_when_no_aliases(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_top_aliases returns empty list when canonical tag has no aliases."""
        ct_id = _make_uuid()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_top_aliases(mock_session, ct_id)

        assert result == []


class TestCanonicalTagRepositoryGetVideosByNormalizedForm:
    """Tests for CanonicalTagRepository.get_videos_by_normalized_form()."""

    @pytest.fixture
    def repository(self) -> CanonicalTagRepository:
        """Create repository instance."""
        return CanonicalTagRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    async def test_basic_3_table_join_returns_videos(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_videos_by_normalized_form joins 3 tables and returns videos."""
        video_a = _make_video(video_id="vid_001", title="Python Tutorial")
        video_b = _make_video(video_id="vid_002", title="Python Tips")

        # Count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        # Items query
        items_scalars = MagicMock()
        items_scalars.all.return_value = [video_a, video_b]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.get_videos_by_normalized_form(
            mock_session, "python"
        )

        assert total == 2
        assert items == [video_a, video_b]
        assert mock_session.execute.call_count == 2

    async def test_include_unavailable_false_excludes_unavailable(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Default include_unavailable=False excludes unavailable videos."""
        video_available = _make_video(
            video_id="vid_avail", title="Available", availability_status="available"
        )

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        items_scalars = MagicMock()
        items_scalars.all.return_value = [video_available]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.get_videos_by_normalized_form(
            mock_session, "python", include_unavailable=False
        )

        assert total == 1
        assert len(items) == 1
        assert items[0].availability_status == "available"

    async def test_include_unavailable_true_includes_all(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """include_unavailable=True returns both available and unavailable videos."""
        video_available = _make_video(
            video_id="vid_a", title="Available", availability_status="available"
        )
        video_deleted = _make_video(
            video_id="vid_d", title="Deleted", availability_status="deleted"
        )

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        items_scalars = MagicMock()
        items_scalars.all.return_value = [video_available, video_deleted]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.get_videos_by_normalized_form(
            mock_session, "python", include_unavailable=True
        )

        assert total == 2
        assert len(items) == 2

    async def test_pagination_respects_skip_and_limit(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Pagination skip/limit are applied correctly."""
        video = _make_video(video_id="vid_page", title="Page 2 Video")

        count_result = MagicMock()
        count_result.scalar_one.return_value = 10  # Total across all pages

        items_scalars = MagicMock()
        items_scalars.all.return_value = [video]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.get_videos_by_normalized_form(
            mock_session, "python", skip=5, limit=1
        )

        assert total == 10
        assert len(items) == 1
        assert items[0] is video

    async def test_nonexistent_tag_returns_empty(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Nonexistent normalized_form returns ([], 0)."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        items_scalars = MagicMock()
        items_scalars.all.return_value = []
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.get_videos_by_normalized_form(
            mock_session, "nonexistent_form"
        )

        assert items == []
        assert total == 0

    async def test_orders_by_upload_date_desc(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Results are ordered by upload_date DESC (newest first)."""
        video_new = _make_video(
            video_id="vid_new",
            title="New Video",
            upload_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
        )
        video_old = _make_video(
            video_id="vid_old",
            title="Old Video",
            upload_date=datetime(2020, 6, 1, tzinfo=timezone.utc),
        )

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        # Mock returns them in expected DESC order
        items_scalars = MagicMock()
        items_scalars.all.return_value = [video_new, video_old]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.get_videos_by_normalized_form(
            mock_session, "python"
        )

        assert total == 2
        assert items[0].upload_date > items[1].upload_date


class TestCanonicalTagRepositoryBuildSubqueries:
    """Tests for CanonicalTagRepository.build_canonical_tag_video_subqueries()."""

    @pytest.fixture
    def repository(self) -> CanonicalTagRepository:
        """Create repository instance."""
        return CanonicalTagRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    async def test_empty_list_returns_empty_list(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Empty normalized_forms list returns []."""
        result = await repository.build_canonical_tag_video_subqueries(
            mock_session, []
        )

        assert result == []
        mock_session.execute.assert_not_called()

    async def test_single_normalized_form_returns_one_subquery(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Single normalized_form returns list with one subquery."""
        tag = _make_canonical_tag(normalized_form="python")

        # Mock get_by_normalized_form via session.execute
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tag
        mock_session.execute.return_value = mock_result

        result = await repository.build_canonical_tag_video_subqueries(
            mock_session, ["python"]
        )

        assert result is not None
        assert len(result) == 1
        # The result should be a SQLAlchemy Select object
        assert hasattr(result[0], "subquery")

    async def test_multiple_forms_returns_multiple_subqueries(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Multiple normalized_forms returns corresponding subqueries."""
        tag_python = _make_canonical_tag(normalized_form="python")
        tag_java = _make_canonical_tag(normalized_form="java")

        # get_by_normalized_form is called once per form, each uses session.execute
        result_python = MagicMock()
        result_python.scalar_one_or_none.return_value = tag_python
        result_java = MagicMock()
        result_java.scalar_one_or_none.return_value = tag_java

        mock_session.execute.side_effect = [result_python, result_java]

        result = await repository.build_canonical_tag_video_subqueries(
            mock_session, ["python", "java"]
        )

        assert result is not None
        assert len(result) == 2
        assert mock_session.execute.call_count == 2

    async def test_unrecognized_form_returns_none(
        self,
        repository: CanonicalTagRepository,
        mock_session: MagicMock,
    ) -> None:
        """Unrecognized normalized_form short-circuits and returns None."""
        # get_by_normalized_form returns None for unknown tag
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.build_canonical_tag_video_subqueries(
            mock_session, ["unknown_tag"]
        )

        assert result is None
        # Only one call needed: the short-circuit on first unknown
        mock_session.execute.assert_called_once()
