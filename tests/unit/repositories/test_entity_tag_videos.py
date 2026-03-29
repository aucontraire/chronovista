"""
Tests for EntityMentionRepository private helpers introduced in Feature 053
(entity-tag-videos): T006 and T007.

T006 — _get_tag_associated_video_ids()
    Source 2 query path: canonical_tags (entity_id FK) → tag_aliases
    (canonical_tag_id) → video_tags (tag = raw_form) → set[str] of video_ids.

T007 — _get_alias_matched_tag_video_ids()
    Source 3 query path: entity_aliases (entity_id) → normalize(alias_name)
    via TagNormalizationService → tag_aliases (normalized_form IN (...)) →
    video_tags (tag = raw_form) → set[str] of video_ids.

Mock strategy
-------------
Both private methods are tested via MagicMock(spec=AsyncSession) with an
AsyncMock execute attribute — the same pattern used throughout the project
(see test_entity_mention_repository.py).

For _get_tag_associated_video_ids: one execute() call is made; the mock
returns a result whose .scalars().all() yields the video IDs.

For _get_alias_matched_tag_video_ids: the method makes *two* execute() calls
in sequence:
  1. Fetch alias_name values from entity_aliases.
  2. Fetch video_id values from tag_aliases → video_tags (only if there are
     aliases with non-None normalized forms).
session.execute is configured as AsyncMock with side_effect to return
different mock results per call.

TagNormalizationService is patched at the module level so that normalize()
returns predictable values without running the full 9-step pipeline.

References
----------
- specs/053-entity-tag-videos/research.md — Decisions 7, 8, 9, 10
- specs/053-entity-tag-videos/spec.md — EC-001, EC-002, EC-007, EC-008,
  EC-010, EC-012
- src/chronovista/repositories/entity_mention_repository.py — lines 1300-1399
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.repositories.entity_mention_repository import EntityMentionRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid() -> uuid.UUID:
    """Return a UUIDv7 expressed as a stdlib ``uuid.UUID`` instance."""
    return uuid.UUID(bytes=uuid7().bytes)


def _make_mock_session() -> MagicMock:
    """Create a MagicMock AsyncSession with an AsyncMock execute attribute.

    Returns
    -------
    MagicMock
        Mock session compatible with the AsyncSession interface.
    """
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    return session


def _scalars_result(values: list[str]) -> MagicMock:
    """Build a mock execute() result whose .scalars().all() returns *values*.

    Parameters
    ----------
    values : list[str]
        The list that .scalars().all() should return.

    Returns
    -------
    MagicMock
        Mock compatible with SQLAlchemy CursorResult.scalars().all() chain.
    """
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = values
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    return mock_result


# ---------------------------------------------------------------------------
# T006 — _get_tag_associated_video_ids()
# ---------------------------------------------------------------------------


class TestGetTagAssociatedVideoIds:
    """Tests for _get_tag_associated_video_ids() (T006).

    The method runs the query path:
        canonical_tags WHERE entity_id = ?
          JOIN tag_aliases ON tag_aliases.canonical_tag_id = canonical_tags.id
          JOIN video_tags  ON video_tags.tag = tag_aliases.raw_form
        SELECT DISTINCT video_tags.video_id

    It issues exactly one session.execute() call and returns the result as
    a set[str].  It does NOT filter by canonical_tags.status (Decision 8).
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh EntityMentionRepository for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    # ------------------------------------------------------------------
    # T006-1: canonical tag path returns video_ids
    # ------------------------------------------------------------------

    async def test_canonical_tag_path_returns_video_ids(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Entity linked to a canonical tag — associated video_ids are returned.

        When the database returns video IDs via the canonical_tags →
        tag_aliases → video_tags join path, the method must return all of
        them as a set[str].
        """
        entity_id = _uuid()
        expected_ids = ["dQw4w9WgXcQ", "9bZkp7q19f0", "jNQXAC9IVRw"]

        mock_session.execute.return_value = _scalars_result(expected_ids)

        result = await repository._get_tag_associated_video_ids(
            mock_session, entity_id
        )

        assert result == set(expected_ids)
        mock_session.execute.assert_called_once()

    async def test_canonical_tag_path_returns_set_type(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Return type is always set[str], even for a single video ID."""
        entity_id = _uuid()

        mock_session.execute.return_value = _scalars_result(["abc123"])

        result = await repository._get_tag_associated_video_ids(
            mock_session, entity_id
        )

        assert isinstance(result, set)
        assert result == {"abc123"}

    # ------------------------------------------------------------------
    # T006-2: no canonical tag link returns empty set (EC-001)
    # ------------------------------------------------------------------

    async def test_no_canonical_tag_link_returns_empty_set(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Entity with no canonical_tags.entity_id link returns an empty set.

        Corresponds to EC-001: entities created manually (not via classify)
        have no canonical tag link.  The query produces zero rows, and the
        method must return set() without raising an error.
        """
        entity_id = _uuid()

        mock_session.execute.return_value = _scalars_result([])

        result = await repository._get_tag_associated_video_ids(
            mock_session, entity_id
        )

        assert result == set()
        mock_session.execute.assert_called_once()

    # ------------------------------------------------------------------
    # T006-3: deprecated canonical tag still returns videos (Decision 8 / EC-002)
    # ------------------------------------------------------------------

    async def test_deprecated_canonical_tag_still_returns_videos(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Deprecated canonical tag MUST still contribute its video IDs.

        Research Decision 8: the query path does NOT filter by
        canonical_tags.status.  Even if status='deprecated' or status='merged',
        the entity_id FK link is the relevant criterion, and the method must
        return the associated video IDs unchanged.

        EC-002: deprecation/merging affects tag management operations, not
        read-only queries.
        """
        entity_id = _uuid()
        # Simulate the DB returning videos even for a deprecated canonical tag
        video_ids = ["3tmd-ClpJxA", "hT_nvWreIhg"]

        mock_session.execute.return_value = _scalars_result(video_ids)

        result = await repository._get_tag_associated_video_ids(
            mock_session, entity_id
        )

        # Method returns whatever the DB produces — status is NOT filtered
        assert result == set(video_ids)

        # Verify the SQL does NOT include a status filter: compile the statement
        # that was passed to execute() and check it contains no status clause
        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "status" not in sql_str.lower(), (
            "Query must NOT filter by canonical_tags.status (Decision 8 / EC-002)"
        )

    # ------------------------------------------------------------------
    # T006-4: tag-sourced videos — no availability_status filtering (EC-012/A-006)
    # ------------------------------------------------------------------

    async def test_no_availability_status_filter_applied(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Tag-sourced videos are NOT filtered by availability_status.

        Research Decision 9 / A-006: the existing get_entity_video_list() does
        NOT filter by videos.availability_status, and this method must match
        that behaviour for consistency.  All local videos are returned regardless
        of their availability status.

        Verified by inspecting the compiled SQL for absence of
        'availability_status'.
        """
        entity_id = _uuid()
        mock_session.execute.return_value = _scalars_result(["vid_deleted_01"])

        await repository._get_tag_associated_video_ids(mock_session, entity_id)

        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "availability_status" not in sql_str.lower(), (
            "Query must NOT filter by availability_status (Decision 9 / EC-012)"
        )

    # ------------------------------------------------------------------
    # T006-5: orphaned canonical tag — no tag_aliases rows (EC-010)
    # ------------------------------------------------------------------

    async def test_orphaned_canonical_tag_returns_empty_set(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Canonical tag with no tag_aliases rows returns empty set.

        EC-010: if canonical_tags row exists but has zero tag_aliases rows,
        the JOINs produce no rows.  The method must return set() silently
        without raising an error.
        """
        entity_id = _uuid()

        # Simulate DB returning zero rows (orphaned canonical tag → no aliases)
        mock_session.execute.return_value = _scalars_result([])

        result = await repository._get_tag_associated_video_ids(
            mock_session, entity_id
        )

        assert result == set()

    # ------------------------------------------------------------------
    # T006-6: duplicate video_ids in DB result are deduplicated by set()
    # ------------------------------------------------------------------

    async def test_duplicate_video_ids_are_deduplicated(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Return type is set[str] — any duplicates from the DB are eliminated.

        The SQL uses DISTINCT, but even if duplicates were returned the method
        must guarantee uniqueness via Python set conversion.
        """
        entity_id = _uuid()
        # Deliberately supply a list with a repeated ID
        raw_result = ["dQw4w9WgXcQ", "dQw4w9WgXcQ", "9bZkp7q19f0"]

        mock_session.execute.return_value = _scalars_result(raw_result)

        result = await repository._get_tag_associated_video_ids(
            mock_session, entity_id
        )

        assert isinstance(result, set)
        assert len(result) == 2
        assert "dQw4w9WgXcQ" in result
        assert "9bZkp7q19f0" in result

    # ------------------------------------------------------------------
    # T006-7: SQL selects from correct tables (structural correctness)
    # ------------------------------------------------------------------

    async def test_query_joins_canonical_tags_tag_aliases_video_tags(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The compiled SQL references canonical_tags, tag_aliases, and video_tags.

        Verifies that the method constructs the correct three-table join path
        described in data-model.md Source 2.
        """
        entity_id = _uuid()
        mock_session.execute.return_value = _scalars_result([])

        await repository._get_tag_associated_video_ids(mock_session, entity_id)

        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()

        assert "canonical_tags" in sql_str, "Query must reference canonical_tags table"
        assert "tag_aliases" in sql_str, "Query must reference tag_aliases table"
        assert "video_tags" in sql_str, "Query must reference video_tags table"


# ---------------------------------------------------------------------------
# T007 — _get_alias_matched_tag_video_ids()
# ---------------------------------------------------------------------------


class TestGetAliasMatchedTagVideoIds:
    """Tests for _get_alias_matched_tag_video_ids() (T007).

    The method runs two execute() calls in sequence:

    Call 1 — Fetch entity aliases:
        SELECT alias_name FROM entity_aliases WHERE entity_id = ?
        → list[str] of alias_name values

    Call 2 (only if aliases exist with non-None normalized forms):
        SELECT DISTINCT video_tags.video_id
        FROM tag_aliases
        JOIN video_tags ON video_tags.tag = tag_aliases.raw_form
        WHERE tag_aliases.normalized_form IN (<normalized_aliases>)

    TagNormalizationService is patched for deterministic normalization.

    Key behaviours:
    - Zero aliases → immediate empty set (no second execute)
    - All aliases normalize to None → empty set (no second execute)
    - Non-None normalized forms → exact-match IN query (Decision 10)
    - Results converted to set[str] for deduplication
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh EntityMentionRepository for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    # ------------------------------------------------------------------
    # T007-1: alias matching — alias normalizes to form that matches tag
    # ------------------------------------------------------------------

    async def test_alias_matching_returns_video_ids(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Entity alias normalizes to a form matching tag_aliases.normalized_form.

        Given alias_name="AI" that normalizes to "ai", and tag_aliases has a
        row with normalized_form="ai" pointing to video_tags with video_ids,
        the method must return those video_ids.
        """
        entity_id = _uuid()
        expected_ids = ["vid_ai_001", "vid_ai_002"]

        # Call 1: returns alias names
        # Call 2: returns matched video IDs
        mock_session.execute.side_effect = [
            _scalars_result(["AI"]),
            _scalars_result(expected_ids),
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ) as mock_normalizer_cls:
            mock_normalizer = MagicMock()
            mock_normalizer.normalize.side_effect = lambda name: name.lower()
            mock_normalizer_cls.return_value = mock_normalizer

            result = await repository._get_alias_matched_tag_video_ids(
                mock_session, entity_id
            )

        assert result == set(expected_ids)
        assert mock_session.execute.call_count == 2

    # ------------------------------------------------------------------
    # T007-2: case-insensitive normalization matches tag
    # ------------------------------------------------------------------

    async def test_case_insensitive_normalization_matches_tag(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Alias 'MACHINE LEARNING' normalizes to 'machine learning' matching tag.

        Research Decision 2: TagNormalizationService.normalize() produces a
        casefolded form.  The method must pass the normalized form (not the raw
        alias) to the SQL IN clause, enabling case-insensitive matching against
        tag_aliases.normalized_form.
        """
        entity_id = _uuid()
        expected_ids = ["vid_ml_001"]

        mock_session.execute.side_effect = [
            _scalars_result(["MACHINE LEARNING"]),
            _scalars_result(expected_ids),
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ) as mock_normalizer_cls:
            mock_normalizer = MagicMock()
            # Simulate the casefold step of the normalization pipeline
            mock_normalizer.normalize.side_effect = lambda name: name.casefold()
            mock_normalizer_cls.return_value = mock_normalizer

            result = await repository._get_alias_matched_tag_video_ids(
                mock_session, entity_id
            )

        assert result == set(expected_ids)

        # Verify normalize() was called with the original alias_name
        mock_normalizer.normalize.assert_called_once_with("MACHINE LEARNING")

        # Verify the second SQL uses the normalized form, not the raw alias
        second_call_stmt = mock_session.execute.call_args_list[1].args[0]
        sql_str = str(
            second_call_stmt.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "machine learning" in sql_str, (
            "SQL must use normalized form 'machine learning' in the IN clause"
        )

    # ------------------------------------------------------------------
    # T007-3: None-normalized alias is skipped (Decision 7 / EC-008)
    # ------------------------------------------------------------------

    async def test_none_normalized_alias_is_skipped(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Alias whose normalize() returns None is silently skipped.

        Research Decision 7 / EC-008: TagNormalizationService.normalize()
        returns None for whitespace-only or empty input.  Such aliases MUST
        be skipped and MUST NOT contribute to the SQL IN clause.  When ALL
        aliases normalize to None, the method returns an empty set without
        issuing the second execute() call.
        """
        entity_id = _uuid()

        # One alias present but it has whitespace-only name → normalize → None
        mock_session.execute.side_effect = [
            _scalars_result(["   "]),  # Call 1: one alias, whitespace only
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ) as mock_normalizer_cls:
            mock_normalizer = MagicMock()
            # Whitespace-only → normalize returns None
            mock_normalizer.normalize.return_value = None
            mock_normalizer_cls.return_value = mock_normalizer

            result = await repository._get_alias_matched_tag_video_ids(
                mock_session, entity_id
            )

        assert result == set()
        # Only one execute() call — the second query must NOT be issued
        assert mock_session.execute.call_count == 1, (
            "Second execute() must NOT be called when all aliases normalize to None"
        )

    # ------------------------------------------------------------------
    # T007-3b: asr_error aliases are excluded from tag matching
    # ------------------------------------------------------------------

    async def test_asr_error_alias_excluded_from_tag_matching(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Alias with alias_type='asr_error' is excluded from tag matching.

        ASR error aliases (e.g., 'Andres', 'elon') are transcript-specific
        patterns that produce false positives when matched against YouTube
        tags.  The first SQL query must include a WHERE clause that filters
        out alias_type = 'asr_error', so these aliases never reach the
        normalization or tag-matching stages.
        """
        entity_id = _uuid()

        # The mock returns zero aliases because the only alias is asr_error
        # and should be filtered out by the WHERE clause
        mock_session.execute.side_effect = [
            _scalars_result([]),  # Call 1: no aliases after asr_error filter
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ):
            result = await repository._get_alias_matched_tag_video_ids(
                mock_session, entity_id
            )

        assert result == set()
        assert mock_session.execute.call_count == 1

        # Verify the SQL excludes asr_error aliases
        first_stmt = mock_session.execute.call_args_list[0].args[0]
        sql_str = str(
            first_stmt.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "alias_type" in sql_str, (
            "Query must filter by alias_type to exclude asr_error aliases"
        )
        assert "asr_error" in sql_str, (
            "Query must explicitly reference 'asr_error' in the WHERE clause"
        )

    async def test_asr_error_alias_with_valid_normalized_form_still_excluded(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """ASR error alias with a valid normalized form is still excluded.

        Even when an asr_error alias (e.g., 'elon') would produce a valid
        normalized form that matches tags, it must be excluded at the SQL
        level.  The alias never reaches TagNormalizationService.normalize().

        This test verifies the fix for the false-positive bug where ASR
        patterns like 'Andres', 'Lopez', 'elon' matched real YouTube tags.
        """
        entity_id = _uuid()
        expected_ids = ["vid_real_001"]

        # Call 1 returns only the non-ASR alias (DB filtered out 'elon')
        # Call 2 returns video IDs for the valid alias
        mock_session.execute.side_effect = [
            _scalars_result(["Elon Musk"]),  # Only the name_variant alias
            _scalars_result(expected_ids),
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ) as mock_normalizer_cls:
            mock_normalizer = MagicMock()
            mock_normalizer.normalize.side_effect = lambda name: name.lower()
            mock_normalizer_cls.return_value = mock_normalizer

            result = await repository._get_alias_matched_tag_video_ids(
                mock_session, entity_id
            )

        assert result == set(expected_ids)
        # normalize() should only be called for the non-ASR alias
        mock_normalizer.normalize.assert_called_once_with("Elon Musk")

    async def test_mixed_none_and_valid_normalized_aliases(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Only non-None normalized forms are included in the SQL IN clause.

        When some aliases normalize to None and others to valid strings, only
        the valid normalized forms must appear in the query.  The None aliases
        are silently skipped.
        """
        entity_id = _uuid()
        expected_ids = ["vid_valid_001"]

        mock_session.execute.side_effect = [
            _scalars_result(["  ", "AI"]),  # Two aliases: one whitespace, one valid
            _scalars_result(expected_ids),
        ]

        normalize_map = {"  ": None, "AI": "ai"}

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ) as mock_normalizer_cls:
            mock_normalizer = MagicMock()
            mock_normalizer.normalize.side_effect = lambda name: normalize_map.get(
                name
            )
            mock_normalizer_cls.return_value = mock_normalizer

            result = await repository._get_alias_matched_tag_video_ids(
                mock_session, entity_id
            )

        assert result == set(expected_ids)
        assert mock_session.execute.call_count == 2

        # Verify only "ai" appears in the second query
        second_stmt = mock_session.execute.call_args_list[1].args[0]
        sql_str = str(
            second_stmt.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "ai" in sql_str
        # The whitespace alias should not appear (it was skipped)
        # We can't check for absence of whitespace in SQL easily, but we can
        # confirm normalize was called for both aliases
        assert mock_normalizer.normalize.call_count == 2

    # ------------------------------------------------------------------
    # T007-4: zero aliases returns empty set immediately (EC-007)
    # ------------------------------------------------------------------

    async def test_zero_aliases_returns_empty_set(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Entity with no aliases returns an empty set without a second query.

        EC-007: when an entity has zero aliases (e.g., a newly created entity),
        no alias-to-tag matching can be performed.  The method must return set()
        after the first execute() call and MUST NOT issue a second execute().
        """
        entity_id = _uuid()

        mock_session.execute.side_effect = [
            _scalars_result([]),  # Call 1: no aliases found
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ):
            result = await repository._get_alias_matched_tag_video_ids(
                mock_session, entity_id
            )

        assert result == set()
        # Only one execute call — no second query for videos
        assert mock_session.execute.call_count == 1, (
            "Second execute() must NOT be called when entity has no aliases"
        )

    # ------------------------------------------------------------------
    # T007-5: multiple aliases matching same video are deduplicated
    # ------------------------------------------------------------------

    async def test_multiple_aliases_matching_same_video_are_deduplicated(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Two different aliases both matching the same video → video_id once.

        EC-006 / EC-009: when multiple aliases resolve to the same video_id
        (either because both aliases' normalized forms map to the same tag, or
        because the SQL DISTINCT collapses them), the returned set must contain
        that video_id exactly once.
        """
        entity_id = _uuid()

        # The second execute() returns the same video_id twice (simulating
        # UNION ALL or duplicate rows before DISTINCT is applied)
        mock_session.execute.side_effect = [
            _scalars_result(["AI", "Artificial Intelligence"]),
            _scalars_result(["shared_video_01", "shared_video_01"]),
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ) as mock_normalizer_cls:
            mock_normalizer = MagicMock()
            alias_map = {"AI": "ai", "Artificial Intelligence": "artificial intelligence"}
            mock_normalizer.normalize.side_effect = lambda name: alias_map.get(
                name, name.lower()
            )
            mock_normalizer_cls.return_value = mock_normalizer

            result = await repository._get_alias_matched_tag_video_ids(
                mock_session, entity_id
            )

        assert isinstance(result, set)
        assert len(result) == 1
        assert "shared_video_01" in result

    # ------------------------------------------------------------------
    # T007-6: multiple aliases matching different videos — union of all
    # ------------------------------------------------------------------

    async def test_multiple_aliases_matching_different_videos(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Multiple aliases matching different video_ids — all are returned.

        When aliases "AI" and "ML" each match different sets of videos via
        tag_aliases.normalized_form, the method must return the union of all
        matched video_ids as a single set.
        """
        entity_id = _uuid()

        mock_session.execute.side_effect = [
            _scalars_result(["AI", "ML"]),
            # The IN query covers both normalized forms; DB returns union of videos
            _scalars_result(["vid_ai_001", "vid_ai_002", "vid_ml_001"]),
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ) as mock_normalizer_cls:
            mock_normalizer = MagicMock()
            alias_map = {"AI": "ai", "ML": "ml"}
            mock_normalizer.normalize.side_effect = lambda name: alias_map.get(
                name, name.lower()
            )
            mock_normalizer_cls.return_value = mock_normalizer

            result = await repository._get_alias_matched_tag_video_ids(
                mock_session, entity_id
            )

        assert result == {"vid_ai_001", "vid_ai_002", "vid_ml_001"}
        assert mock_session.execute.call_count == 2

    # ------------------------------------------------------------------
    # T007-7: SQL uses exact equality (IN), not ILIKE (Decision 10)
    # ------------------------------------------------------------------

    async def test_sql_uses_exact_equality_not_ilike(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The second SQL query uses exact IN match, NOT ILIKE or LIKE.

        Research Decision 10: all alias-to-tag matching uses exact equality
        on normalized forms.  No fuzzy or substring matching is used.
        This is verified by inspecting the compiled SQL for ILIKE/LIKE clauses.
        """
        entity_id = _uuid()

        mock_session.execute.side_effect = [
            _scalars_result(["AI"]),
            _scalars_result([]),
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ) as mock_normalizer_cls:
            mock_normalizer = MagicMock()
            mock_normalizer.normalize.return_value = "ai"
            mock_normalizer_cls.return_value = mock_normalizer

            await repository._get_alias_matched_tag_video_ids(mock_session, entity_id)

        second_stmt = mock_session.execute.call_args_list[1].args[0]
        sql_str = str(
            second_stmt.compile(compile_kwargs={"literal_binds": False})
        ).upper()
        assert "ILIKE" not in sql_str, "Query must NOT use ILIKE (Decision 10)"
        assert "LIKE" not in sql_str, "Query must NOT use LIKE (Decision 10)"
        # Must use IN clause
        assert " IN " in sql_str, "Query must use exact IN clause (Decision 10)"

    # ------------------------------------------------------------------
    # T007-8: return type is always set[str]
    # ------------------------------------------------------------------

    async def test_return_type_is_set_of_strings(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Method always returns set[str], never a list or other collection."""
        entity_id = _uuid()

        mock_session.execute.side_effect = [
            _scalars_result(["alias1"]),
            _scalars_result(["vidA", "vidB"]),
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository.TagNormalizationService"
        ) as mock_normalizer_cls:
            mock_normalizer = MagicMock()
            mock_normalizer.normalize.return_value = "alias1"
            mock_normalizer_cls.return_value = mock_normalizer

            result = await repository._get_alias_matched_tag_video_ids(
                mock_session, entity_id
            )

        assert isinstance(result, set)
        for item in result:
            assert isinstance(item, str)


# ---------------------------------------------------------------------------
# Helpers for get_entity_video_list tests (T008-T010)
# ---------------------------------------------------------------------------


def _row_result(rows: list[Any]) -> MagicMock:
    """Build a mock execute() result whose .all() returns *rows*.

    Parameters
    ----------
    rows : list[Any]
        The list of row-like objects that .all() should return.

    Returns
    -------
    MagicMock
        Mock compatible with SQLAlchemy CursorResult.all() chain.
    """
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    return mock_result


def _make_video_row(
    *,
    video_id: str,
    video_title: str = "Test Video",
    channel_name: str = "Test Channel",
    mention_count: int = 1,
    detection_methods: list[str] | None = None,
    has_manual: bool = False,
    first_mention_time: float | None = 10.0,
    upload_date: Any = None,
) -> MagicMock:
    """Create a mock row representing a transcript-mention video result.

    Parameters
    ----------
    video_id : str
        YouTube video ID.
    video_title : str
        Video title.
    channel_name : str
        Channel name.
    mention_count : int
        Number of transcript mentions.
    detection_methods : list[str] | None
        Detection methods from the GROUP BY query.
    has_manual : bool
        Whether the video has a manual mention.
    first_mention_time : float | None
        Earliest transcript mention timestamp.
    upload_date : Any
        Upload date (should have .isoformat() for real use).

    Returns
    -------
    MagicMock
        Mock row object with attribute access for each column.
    """
    if detection_methods is None:
        detection_methods = ["rule_match"]
    row = MagicMock()
    row.video_id = video_id
    row.video_title = video_title
    row.channel_name = channel_name
    row.mention_count = mention_count
    row.detection_methods = detection_methods
    row.has_manual = has_manual
    row.first_mention_time = first_mention_time
    row.upload_date = upload_date
    return row


def _make_tag_meta_row(
    *,
    video_id: str,
    video_title: str = "Tagged Video",
    channel_name: str = "Tag Channel",
    upload_date: Any = None,
) -> MagicMock:
    """Create a mock row for tag-only video metadata.

    Parameters
    ----------
    video_id : str
        YouTube video ID.
    video_title : str
        Video title.
    channel_name : str
        Channel name.
    upload_date : Any
        Upload date mock.

    Returns
    -------
    MagicMock
        Mock row with attribute access for video/channel metadata.
    """
    row = MagicMock()
    row.video_id = video_id
    row.video_title = video_title
    row.channel_name = channel_name
    row.upload_date = upload_date
    return row


class _MockUploadDate:
    """Mock upload_date with isoformat() method."""

    def __init__(self, value: str) -> None:
        self._value = value

    def isoformat(self) -> str:
        return self._value


# ---------------------------------------------------------------------------
# T008 — entity with tagged + transcript mention videos returns all unique
# ---------------------------------------------------------------------------


class TestGetEntityVideoListTagIntegration:
    """Tests for get_entity_video_list() with canonical tag associations (T008-T010).

    These tests verify the integration of _get_tag_associated_video_ids()
    into get_entity_video_list(), including deduplication, source merging,
    sort order, and pagination count.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh EntityMentionRepository for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    # ------------------------------------------------------------------
    # T008: entity with 5 tagged + 1 transcript mention = 6 unique videos
    # ------------------------------------------------------------------

    async def test_tagged_plus_transcript_returns_all_unique_videos(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Entity with 5 tagged videos and 1 transcript mention returns 6 unique videos.

        The tagged videos do not overlap with the transcript mention video.
        Total count should be 6, and all 6 videos should appear in the results.
        Tag-only videos have mention_count=0, mentions=[], sources=["tag"].
        """
        entity_id = _uuid()
        transcript_vid = "vid_transcript_001"
        tag_vids = [f"vid_tag_{i:03d}" for i in range(1, 6)]

        # Mock _get_tag_associated_video_ids to return 5 tag video IDs
        # Mock _get_alias_matched_tag_video_ids to return empty set — Phase 3
        # tests focus on canonical tag behaviour, not alias matching.
        with patch.object(
            repository,
            "_get_tag_associated_video_ids",
            return_value=set(tag_vids),
        ), patch.object(
            repository,
            "_get_alias_matched_tag_video_ids",
            return_value=set(),
        ):
            # Call sequence for get_entity_video_list:
            # 1. transcript_vid_stmt — distinct transcript video IDs
            # 2. main_stmt — grouped transcript mention rows
            # 3. preview_stmt — mention previews for the transcript video
            # 4. tag_meta_stmt — metadata for tag-only videos
            upload_date = _MockUploadDate("2024-01-15")
            mock_session.execute.side_effect = [
                _scalars_result([transcript_vid]),  # transcript video IDs
                _row_result([  # main grouped query
                    _make_video_row(
                        video_id=transcript_vid,
                        mention_count=3,
                        upload_date=upload_date,
                    ),
                ]),
                _row_result([]),  # preview query (empty for simplicity)
                _row_result([  # tag-only video metadata
                    _make_tag_meta_row(
                        video_id=tv, upload_date=upload_date
                    )
                    for tv in tag_vids
                ]),
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=20, offset=0
            )

        assert total == 6
        assert len(results) == 6

        result_ids = {r["video_id"] for r in results}
        assert transcript_vid in result_ids
        for tv in tag_vids:
            assert tv in result_ids

        # Verify tag-only videos have correct fields
        for r in results:
            if r["video_id"] in tag_vids:
                assert r["mention_count"] == 0
                assert r["mentions"] == []
                assert r["sources"] == ["tag"]
                assert r["has_manual"] is False
                assert r["first_mention_time"] is None

    # ------------------------------------------------------------------
    # T009: entity with 0 mentions but 3 tagged videos returns 3
    # ------------------------------------------------------------------

    async def test_no_mentions_but_tagged_videos_returns_tagged(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Entity with no transcript mentions but 3 tagged videos returns 3 videos.

        This is the key scenario for tag-only entities: transcript mentions
        are empty, but the entity's canonical tag links to tagged videos.
        The result must NOT be empty.
        """
        entity_id = _uuid()
        tag_vids = ["vid_tag_a", "vid_tag_b", "vid_tag_c"]
        upload_date = _MockUploadDate("2024-06-01")

        with patch.object(
            repository,
            "_get_tag_associated_video_ids",
            return_value=set(tag_vids),
        ), patch.object(
            repository,
            "_get_alias_matched_tag_video_ids",
            return_value=set(),
        ):
            mock_session.execute.side_effect = [
                _scalars_result([]),  # no transcript video IDs
                # No main query needed (transcript_video_ids is empty)
                _row_result([  # tag-only video metadata
                    _make_tag_meta_row(
                        video_id=tv, upload_date=upload_date
                    )
                    for tv in tag_vids
                ]),
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=20, offset=0
            )

        assert total == 3
        assert len(results) == 3

        for r in results:
            assert r["video_id"] in tag_vids
            assert r["mention_count"] == 0
            assert r["mentions"] == []
            assert r["sources"] == ["tag"]
            assert r["has_manual"] is False
            assert r["first_mention_time"] is None

    # ------------------------------------------------------------------
    # T010: video in both sources appears once with merged sources
    # ------------------------------------------------------------------

    async def test_overlap_video_appears_once_with_merged_sources(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Video in both transcript mentions AND tags appears once with sources merged.

        When a video_id exists in both transcript results and tag results,
        the result must contain only one entry for that video_id.  The
        ``sources`` list must contain both "transcript" and "tag".  The
        transcript mention data (mention_count, mentions, first_mention_time)
        must be preserved.
        """
        entity_id = _uuid()
        overlap_vid = "vid_overlap_001"
        upload_date = _MockUploadDate("2024-03-20")

        with patch.object(
            repository,
            "_get_tag_associated_video_ids",
            return_value={overlap_vid},
        ), patch.object(
            repository,
            "_get_alias_matched_tag_video_ids",
            return_value=set(),
        ):
            mock_session.execute.side_effect = [
                _scalars_result([overlap_vid]),  # transcript video IDs
                _row_result([  # main grouped query
                    _make_video_row(
                        video_id=overlap_vid,
                        mention_count=5,
                        detection_methods=["rule_match"],
                        first_mention_time=12.5,
                        upload_date=upload_date,
                    ),
                ]),
                _row_result([]),  # preview query
                # No tag_meta_stmt — tag_only_ids is empty
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=20, offset=0
            )

        # Only one video in results (deduplicated)
        assert total == 1
        assert len(results) == 1

        video = results[0]
        assert video["video_id"] == overlap_vid
        assert "transcript" in video["sources"]
        assert "tag" in video["sources"]
        # Transcript mention data preserved
        assert video["mention_count"] == 5
        assert video["first_mention_time"] == 12.5

    async def test_overlap_via_different_raw_tag_forms_still_deduped(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Same video matched via different raw tag forms is still deduplicated (EC-009).

        Even if a video appears in tag results through multiple raw tag forms
        (e.g., "AI" and "A.I." both resolving to the same canonical tag),
        and also has transcript mentions, it must appear exactly once with
        merged sources.
        """
        entity_id = _uuid()
        overlap_vid = "vid_ec009"
        upload_date = _MockUploadDate("2024-05-10")

        # _get_tag_associated_video_ids already returns a set, so duplicates
        # from different raw forms are collapsed at that level.
        with patch.object(
            repository,
            "_get_tag_associated_video_ids",
            return_value={overlap_vid},  # set — already deduplicated
        ), patch.object(
            repository,
            "_get_alias_matched_tag_video_ids",
            return_value=set(),
        ):
            mock_session.execute.side_effect = [
                _scalars_result([overlap_vid]),  # transcript video IDs
                _row_result([
                    _make_video_row(
                        video_id=overlap_vid,
                        mention_count=2,
                        detection_methods=["rule_match"],
                        upload_date=upload_date,
                    ),
                ]),
                _row_result([]),  # preview query
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=20, offset=0
            )

        assert total == 1
        assert len(results) == 1
        assert results[0]["video_id"] == overlap_vid
        assert "tag" in results[0]["sources"]
        assert "transcript" in results[0]["sources"]

    # ------------------------------------------------------------------
    # T014: sort order — transcript-mention videos before tag-only
    # ------------------------------------------------------------------

    async def test_transcript_mention_videos_sorted_before_tag_only(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Transcript-mention videos appear before tag-only videos in results.

        Sort key: (has_transcript_mention DESC, mention_count DESC,
        upload_date DESC).  A tag-only video with a newer upload date must
        still sort AFTER a transcript-mention video.
        """
        entity_id = _uuid()
        transcript_vid = "vid_transcript_sort"
        tag_vid = "vid_tag_sort"
        old_date = _MockUploadDate("2020-01-01")
        new_date = _MockUploadDate("2025-12-31")

        with patch.object(
            repository,
            "_get_tag_associated_video_ids",
            return_value={tag_vid},
        ), patch.object(
            repository,
            "_get_alias_matched_tag_video_ids",
            return_value=set(),
        ):
            mock_session.execute.side_effect = [
                _scalars_result([transcript_vid]),  # transcript video IDs
                _row_result([
                    _make_video_row(
                        video_id=transcript_vid,
                        mention_count=1,
                        upload_date=old_date,
                    ),
                ]),
                _row_result([]),  # preview query
                _row_result([
                    _make_tag_meta_row(
                        video_id=tag_vid, upload_date=new_date
                    ),
                ]),
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=20, offset=0
            )

        assert total == 2
        assert len(results) == 2
        # Transcript-mention video first despite older upload_date
        assert results[0]["video_id"] == transcript_vid
        assert results[1]["video_id"] == tag_vid

    # ------------------------------------------------------------------
    # T015: pagination total reflects deduplicated count
    # ------------------------------------------------------------------

    async def test_pagination_total_reflects_deduplicated_count(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Total count is the deduplicated count across transcript + tag videos.

        Given 2 transcript-mention videos and 3 tag videos with 1 overlap,
        the total count should be 4 (not 5).
        """
        entity_id = _uuid()
        transcript_vids = ["vid_t1", "vid_t2"]
        tag_vids = {"vid_t2", "vid_tag1", "vid_tag2"}  # vid_t2 overlaps
        upload_date = _MockUploadDate("2024-01-01")

        with patch.object(
            repository,
            "_get_tag_associated_video_ids",
            return_value=tag_vids,
        ), patch.object(
            repository,
            "_get_alias_matched_tag_video_ids",
            return_value=set(),
        ):
            mock_session.execute.side_effect = [
                _scalars_result(transcript_vids),  # transcript video IDs
                _row_result([
                    _make_video_row(
                        video_id=vid, upload_date=upload_date
                    )
                    for vid in transcript_vids
                ]),
                _row_result([]),  # preview for vid_t1
                _row_result([]),  # preview for vid_t2
                _row_result([  # tag-only metadata (vid_tag1, vid_tag2)
                    _make_tag_meta_row(
                        video_id=vid, upload_date=upload_date
                    )
                    for vid in ["vid_tag1", "vid_tag2"]
                ]),
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=20, offset=0
            )

        # 2 transcript + 3 tag - 1 overlap = 4 unique
        assert total == 4
        assert len(results) == 4
        result_ids = {r["video_id"] for r in results}
        assert result_ids == {"vid_t1", "vid_t2", "vid_tag1", "vid_tag2"}


# ---------------------------------------------------------------------------
# T016-T018 — Alias-matched tag video association (User Story 2, Phase 4)
# ---------------------------------------------------------------------------


class TestGetEntityVideoListAliasTagIntegration:
    """Tests for alias-matched tag integration in get_entity_video_list() (T016-T018).

    These tests verify that _get_alias_matched_tag_video_ids() is called
    within get_entity_video_list() and its results are combined with
    canonical-tag video IDs before deduplication against transcript mentions.
    Both tag paths use the same "tag" source indicator.

    Key behaviours verified:
    - T016: case-insensitive alias matching via normalization
    - T017: multiple aliases surface videos from all matching tags, deduplicated
    - T018: alias that normalizes to None is silently skipped
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh EntityMentionRepository for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    # ------------------------------------------------------------------
    # T016: alias "AI" surfaces videos tagged "ai" (case-insensitive)
    # ------------------------------------------------------------------

    async def test_alias_surfaces_videos_via_case_insensitive_normalization(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Entity with alias "AI" surfaces videos tagged "ai" via normalization.

        The alias "AI" is normalized to "ai" by TagNormalizationService, which
        matches tag_aliases.normalized_form = "ai".  The resulting video_ids
        must appear in the entity video list with source "tag", mention_count 0,
        and empty mentions list.
        """
        entity_id = _uuid()
        alias_tag_vids = ["vid_ai_tag_001", "vid_ai_tag_002"]
        upload_date = _MockUploadDate("2024-08-15")

        with (
            patch.object(
                repository,
                "_get_tag_associated_video_ids",
                return_value=set(),  # No canonical tag link
            ),
            patch.object(
                repository,
                "_get_alias_matched_tag_video_ids",
                return_value=set(alias_tag_vids),
            ),
        ):
            mock_session.execute.side_effect = [
                _scalars_result([]),  # no transcript video IDs
                _row_result([  # tag-only video metadata
                    _make_tag_meta_row(
                        video_id=vid, upload_date=upload_date
                    )
                    for vid in alias_tag_vids
                ]),
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=20, offset=0
            )

        assert total == 2
        assert len(results) == 2

        result_ids = {r["video_id"] for r in results}
        assert result_ids == set(alias_tag_vids)

        for r in results:
            assert r["sources"] == ["tag"]
            assert r["mention_count"] == 0
            assert r["mentions"] == []
            assert r["first_mention_time"] is None
            assert r["has_manual"] is False

    # ------------------------------------------------------------------
    # T017: multiple aliases surface videos from all matching tags, deduped
    # ------------------------------------------------------------------

    async def test_multiple_aliases_surface_all_matching_tag_videos_deduplicated(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Entity with aliases "AI", "ML", "machine learning" surfaces all tagged videos.

        Each alias may match different tags/videos.  The union of all
        alias-matched video_ids is returned, deduplicated.  Videos from
        the canonical tag path are also included (if any).  All tag-sourced
        videos use source "tag".
        """
        entity_id = _uuid()
        # Alias path returns 3 unique videos (one might overlap across aliases)
        alias_tag_vids = ["vid_ai_01", "vid_ml_01", "vid_ml_02"]
        # Canonical path returns 1 additional video
        canonical_tag_vids = ["vid_canonical_01"]
        upload_date = _MockUploadDate("2024-09-01")

        with (
            patch.object(
                repository,
                "_get_tag_associated_video_ids",
                return_value=set(canonical_tag_vids),
            ),
            patch.object(
                repository,
                "_get_alias_matched_tag_video_ids",
                return_value=set(alias_tag_vids),
            ),
        ):
            all_tag_vids = set(alias_tag_vids) | set(canonical_tag_vids)

            mock_session.execute.side_effect = [
                _scalars_result([]),  # no transcript video IDs
                _row_result([  # tag-only video metadata for all 4 vids
                    _make_tag_meta_row(
                        video_id=vid, upload_date=upload_date
                    )
                    for vid in sorted(all_tag_vids)
                ]),
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=20, offset=0
            )

        assert total == 4
        assert len(results) == 4

        result_ids = {r["video_id"] for r in results}
        assert result_ids == all_tag_vids

        for r in results:
            assert r["sources"] == ["tag"]
            assert r["mention_count"] == 0

    # ------------------------------------------------------------------
    # T018: alias that normalizes to None is silently skipped
    # ------------------------------------------------------------------

    async def test_alias_normalizing_to_none_is_silently_skipped(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Alias whose normalize() returns None contributes no video_ids.

        When _get_alias_matched_tag_video_ids() returns an empty set because
        all aliases normalized to None, the entity video list falls back to
        transcript mentions and canonical tag associations only.  No error
        is raised and no spurious videos appear.
        """
        entity_id = _uuid()
        transcript_vid = "vid_transcript_only"
        upload_date = _MockUploadDate("2024-07-01")

        with (
            patch.object(
                repository,
                "_get_tag_associated_video_ids",
                return_value=set(),  # No canonical tag link
            ),
            patch.object(
                repository,
                "_get_alias_matched_tag_video_ids",
                return_value=set(),  # All aliases normalized to None → empty
            ),
        ):
            mock_session.execute.side_effect = [
                _scalars_result([transcript_vid]),  # transcript video IDs
                _row_result([  # main grouped query
                    _make_video_row(
                        video_id=transcript_vid,
                        mention_count=2,
                        upload_date=upload_date,
                    ),
                ]),
                _row_result([]),  # preview query
                # No tag-only metadata query — tag_only_ids is empty
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=20, offset=0
            )

        assert total == 1
        assert len(results) == 1
        assert results[0]["video_id"] == transcript_vid
        assert results[0]["sources"] == ["transcript"]
        assert results[0]["mention_count"] == 2

    # ------------------------------------------------------------------
    # T020: three-way overlap — "tag" appears only once in sources
    # ------------------------------------------------------------------

    async def test_three_way_overlap_tag_appears_once_in_sources(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Video in transcript + canonical tag + alias tag has "tag" only once.

        When a video_id is found via transcript mentions, canonical tag path,
        AND alias-matched tag path, the sources list must contain "tag" exactly
        once (not duplicated).  The dedup logic at T013 already checks
        ``"tag" not in sources`` before appending, so the three-way overlap
        is naturally handled.
        """
        entity_id = _uuid()
        overlap_vid = "vid_three_way"
        upload_date = _MockUploadDate("2024-10-01")

        # Both tag paths return the same video_id
        with (
            patch.object(
                repository,
                "_get_tag_associated_video_ids",
                return_value={overlap_vid},
            ),
            patch.object(
                repository,
                "_get_alias_matched_tag_video_ids",
                return_value={overlap_vid},
            ),
        ):
            mock_session.execute.side_effect = [
                _scalars_result([overlap_vid]),  # transcript video IDs
                _row_result([  # main grouped query
                    _make_video_row(
                        video_id=overlap_vid,
                        mention_count=7,
                        detection_methods=["rule_match"],
                        first_mention_time=5.0,
                        upload_date=upload_date,
                    ),
                ]),
                _row_result([]),  # preview query
                # No tag_meta_stmt — tag_only_ids is empty (video is in transcript)
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=20, offset=0
            )

        assert total == 1
        assert len(results) == 1

        video = results[0]
        assert video["video_id"] == overlap_vid
        # "tag" must appear exactly once despite two tag paths matching
        assert video["sources"].count("tag") == 1
        assert "transcript" in video["sources"]
        assert "tag" in video["sources"]
        # Transcript mention data preserved
        assert video["mention_count"] == 7
        assert video["first_mention_time"] == 5.0


# ---------------------------------------------------------------------------
# T028 — Entity header video count equals deduplicated total
# ---------------------------------------------------------------------------


class TestCombinedVideoCount:
    """Tests for combined video count in get_entity_video_list() (T028).

    Verifies that the total count returned by get_entity_video_list()
    reflects the deduplicated union of transcript-mention video IDs and
    tag-associated video IDs.  This count is used by the entity detail
    endpoint to display the correct video count in the entity header
    (FR-007).
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh EntityMentionRepository for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_combined_count_with_overlap(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """5 transcript + 3 tag with 2 overlap = 6 deduplicated total.

        Given an entity with 5 transcript-mention videos and 3 tag-associated
        videos where 2 video IDs overlap, the total count must be 6 (not 8).
        This validates FR-007 and US4 acceptance scenario 2.
        """
        entity_id = _uuid()
        transcript_vids = [f"vid_t_{i}" for i in range(1, 6)]  # 5 videos
        # 3 tag videos: 2 overlap with transcript, 1 unique
        tag_vids = {"vid_t_1", "vid_t_2", "vid_tag_unique"}
        upload_date = _MockUploadDate("2024-08-01")

        with patch.object(
            repository,
            "_get_tag_associated_video_ids",
            return_value=tag_vids,
        ), patch.object(
            repository,
            "_get_alias_matched_tag_video_ids",
            return_value=set(),
        ):
            mock_session.execute.side_effect = [
                _scalars_result(transcript_vids),  # transcript video IDs
                _row_result([  # main grouped query
                    _make_video_row(
                        video_id=vid,
                        mention_count=2,
                        upload_date=upload_date,
                    )
                    for vid in transcript_vids
                ]),
                _row_result([]),  # preview for vid_t_1
                _row_result([]),  # preview for vid_t_2
                _row_result([]),  # preview for vid_t_3
                _row_result([]),  # preview for vid_t_4
                _row_result([]),  # preview for vid_t_5
                _row_result([  # tag-only video metadata
                    _make_tag_meta_row(
                        video_id="vid_tag_unique",
                        upload_date=upload_date,
                    ),
                ]),
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=50, offset=0
            )

        # 5 transcript + 1 tag-only = 6 unique (2 overlap counted once)
        assert total == 6
        assert len(results) == 6

        # Verify overlap videos have "tag" in their sources
        for r in results:
            if r["video_id"] in ("vid_t_1", "vid_t_2"):
                assert "tag" in r["sources"]
                assert "transcript" in r["sources"]
            elif r["video_id"] == "vid_tag_unique":
                assert r["sources"] == ["tag"]
                assert r["mention_count"] == 0

    async def test_combined_count_no_overlap(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """3 transcript + 7 tag with 0 overlap = 10 total.

        US4 acceptance scenario 1: entity with 3 transcript-mention videos
        and 7 tag-only videos (no overlap), video count shows 10.
        """
        entity_id = _uuid()
        transcript_vids = [f"vid_t_{i}" for i in range(1, 4)]  # 3 videos
        tag_vids = {f"vid_tag_{i}" for i in range(1, 8)}  # 7 videos
        upload_date = _MockUploadDate("2024-09-15")

        with patch.object(
            repository,
            "_get_tag_associated_video_ids",
            return_value=tag_vids,
        ), patch.object(
            repository,
            "_get_alias_matched_tag_video_ids",
            return_value=set(),
        ):
            mock_session.execute.side_effect = [
                _scalars_result(transcript_vids),  # transcript video IDs
                _row_result([  # main grouped query
                    _make_video_row(
                        video_id=vid,
                        mention_count=1,
                        upload_date=upload_date,
                    )
                    for vid in transcript_vids
                ]),
                _row_result([]),  # preview for vid_t_1
                _row_result([]),  # preview for vid_t_2
                _row_result([]),  # preview for vid_t_3
                _row_result([  # tag-only video metadata
                    _make_tag_meta_row(
                        video_id=vid,
                        upload_date=upload_date,
                    )
                    for vid in sorted(tag_vids)
                ]),
            ]

            results, total = await repository.get_entity_video_list(
                mock_session, entity_id, limit=50, offset=0
            )

        assert total == 10
        assert len(results) == 10
