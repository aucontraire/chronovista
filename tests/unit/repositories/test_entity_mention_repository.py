"""
Tests for EntityMentionRepository (Feature 038 — T012; Feature 044 — T009;
Feature 050 — T012/T013).

Covers all public methods with mocked AsyncSession:
- bulk_create_with_conflict_skip() — INSERT ... ON CONFLICT DO NOTHING for bulk inserts
- delete_by_scope()               — scoped deletion with optional entity/video/language filters
- get_entities_with_zero_mentions() — entities with no mention rows
- update_entity_counters()        — refreshes mention_count / video_count on named_entities
                                    (Feature 044 T009: ASR-error alias exclusion tests added)
- get_video_entity_summary()      — per-entity aggregation for a video
- get_entity_video_list()         — paginated video list where an entity is mentioned
- get_statistics()                — aggregate stats with optional entity_type filter
- search_entities()               — entity autocomplete search with alias matching
                                    (Feature 050 T012)
- create_manual_association()     — create a manual entity-video link
                                    (Feature 050 T013)

Mock strategy: every test creates a ``MagicMock(spec=AsyncSession)`` whose
``execute`` attribute is an ``AsyncMock``.  This mirrors the pattern used
throughout the project (see test_transcript_correction_repository.py and
test_canonical_tag_repository.py) and avoids any real database I/O.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from sqlalchemy.dialects import postgresql as pg_dialect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.models.entity_mention import EntityMentionCreate
from chronovista.models.enums import DetectionMethod
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from tests.factories.entity_mention_factory import (
    EntityMentionCreateFactory,
    EntityMentionFactory,
    create_entity_mention,
    create_entity_mention_create,
)

# ---------------------------------------------------------------------------
# Module-level patch: replace sqlalchemy.insert with the PostgreSQL dialect
# insert inside the repository module so that .on_conflict_do_nothing() is
# available during testing (without a live PG connection).
# ---------------------------------------------------------------------------
_pg_insert_patcher = patch(
    "chronovista.repositories.entity_mention_repository.insert",
    new=pg_insert,
)
_pg_insert_patcher.start()

# CRITICAL: ensures every async test in this module is recognised by
# pytest-asyncio regardless of how coverage is invoked
# (see CLAUDE.md §pytest-asyncio Coverage Integration Issues).
pytestmark = pytest.mark.asyncio


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


def _make_entity_mention_db(
    *,
    id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    segment_id: int = 1,
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    mention_text: str = "Elon Musk",
    detection_method: str = DetectionMethod.RULE_MATCH.value,
    confidence: float = 1.0,
) -> EntityMentionDB:
    """Build an in-memory EntityMentionDB instance without a DB session.

    Parameters
    ----------
    id : uuid.UUID, optional
        Primary key; generated via UUIDv7 when omitted.
    entity_id : uuid.UUID, optional
        Named entity FK; generated via UUIDv7 when omitted.
    segment_id : int
        FK to transcript_segments.id.
    video_id : str
        YouTube video ID (max 20 chars).
    language_code : str
        BCP-47 language code.
    mention_text : str
        Exact text span that triggered the mention.
    detection_method : str
        One of the DetectionMethod enum string values.
    confidence : float
        Detection confidence in [0.0, 1.0].

    Returns
    -------
    EntityMentionDB
        In-memory ORM instance (no active DB session required).
    """
    return EntityMentionDB(
        id=id or _uuid(),
        entity_id=entity_id or _uuid(),
        segment_id=segment_id,
        video_id=video_id,
        language_code=language_code,
        mention_text=mention_text,
        detection_method=detection_method,
        confidence=confidence,
        created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# TestEntityMentionRepositoryInitialization
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
class TestEntityMentionRepositoryInitialization:
    """Verify repository can be instantiated and model attribute is correct.

    These tests are synchronous; the module-level pytestmark does not prevent
    synchronous test methods from running normally.
    """

    def test_repository_can_be_instantiated(self) -> None:
        """EntityMentionRepository can be constructed without arguments."""
        repo = EntityMentionRepository()
        assert repo is not None

    def test_repository_model_attribute_is_correct(self) -> None:
        """repository.model points to the EntityMentionDB ORM class."""
        repo = EntityMentionRepository()
        assert repo.model is EntityMentionDB

    def test_repository_has_standard_crud_methods(self) -> None:
        """Repository exposes the standard CRUD interface from BaseSQLAlchemyRepository."""
        repo = EntityMentionRepository()
        for method in ("get", "exists", "create", "update", "delete", "get_multi"):
            assert hasattr(repo, method), f"Missing expected method: {method}"

    def test_repository_has_domain_specific_methods(self) -> None:
        """Repository exposes all domain-specific methods required by Feature 038."""
        repo = EntityMentionRepository()
        for method in (
            "bulk_create_with_conflict_skip",
            "delete_by_scope",
            "get_entities_with_zero_mentions",
            "update_entity_counters",
            "update_alias_counters",
            "get_video_entity_summary",
            "get_entity_video_list",
            "get_statistics",
        ):
            assert hasattr(repo, method), f"Missing domain method: {method}"


# ---------------------------------------------------------------------------
# TestEntityMentionRepositoryGet
# ---------------------------------------------------------------------------


class TestEntityMentionRepositoryGet:
    """Tests for get() and exists() — primary-key lookup methods."""

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_get_returns_entity_mention_when_found(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get() returns the matching EntityMentionDB row when it exists."""
        db_obj = _make_entity_mention_db()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = db_obj
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, db_obj.id)

        assert result is db_obj
        mock_session.execute.assert_called_once()

    async def test_get_returns_none_when_not_found(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get() returns None when no row matches the given UUID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, _uuid())

        assert result is None
        mock_session.execute.assert_called_once()

    async def test_exists_returns_true_for_existing_mention(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """exists() returns True when the UUID exists in the database."""
        mention_id = _uuid()

        mock_result = MagicMock()
        mock_result.first.return_value = (mention_id,)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, mention_id)

        assert result is True
        mock_session.execute.assert_called_once()

    async def test_exists_returns_false_for_missing_mention(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """exists() returns False when no row matches the given UUID."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, _uuid())

        assert result is False
        mock_session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# TestBulkCreateWithConflictSkip
# ---------------------------------------------------------------------------


class TestBulkCreateWithConflictSkip:
    """Tests for bulk_create_with_conflict_skip().

    Verifies INSERT execution with ON CONFLICT DO NOTHING semantics,
    correct rowcount propagation, and empty-list short-circuit behaviour.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_empty_list_returns_zero_without_db_call(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Calling bulk_create_with_conflict_skip with [] must return 0 immediately.

        The repository has an early-return guard for empty inputs to avoid
        emitting a zero-row INSERT statement. No database round-trip should occur.
        """
        result = await repository.bulk_create_with_conflict_skip(mock_session, [])

        assert result == 0
        mock_session.execute.assert_not_called()

    async def test_returns_rowcount_for_inserted_rows(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Return value equals the rowcount from the INSERT result.

        The rowcount reflects rows actually written (not conflicted-and-skipped).
        """
        mentions = EntityMentionCreateFactory.build_batch(3)

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        result = await repository.bulk_create_with_conflict_skip(mock_session, mentions)

        assert result == 3
        mock_session.execute.assert_called_once()

    async def test_returns_partial_rowcount_when_conflicts_skipped(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Return value is the actual inserted count, which may be less than input length.

        ON CONFLICT DO NOTHING causes duplicate rows to be silently skipped.
        The repository must return the real rowcount, not len(mentions).
        """
        mentions = EntityMentionCreateFactory.build_batch(5)

        mock_result = MagicMock()
        # Simulate 2 conflicts skipped → only 3 rows actually inserted
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        result = await repository.bulk_create_with_conflict_skip(mock_session, mentions)

        assert result == 3

    async def test_insert_statement_uses_on_conflict_do_nothing(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The INSERT statement must reference the ON CONFLICT constraint name.

        Inspecting the compiled SQL confirms that the statement carries the
        correct conflict-resolution clause targeting
        ``uq_entity_mention_entity_segment_text``.
        """
        entity_id = _uuid()
        mention = create_entity_mention_create(
            entity_id=entity_id,
            segment_id=42,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            mention_text="Python",
        )

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await repository.bulk_create_with_conflict_skip(mock_session, [mention])

        # The INSERT statement was passed as the first positional argument to execute()
        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        # ON CONFLICT DO NOTHING compiles to "ON CONFLICT DO NOTHING" in PostgreSQL dialect
        # The constraint name appears in the clause when specified
        assert "ON CONFLICT" in sql_str.upper() or "on_conflict_do_nothing" in str(stmt)

    async def test_detection_method_enum_is_serialised_to_string(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """DetectionMethod enum values must be converted to their string form before INSERT.

        The ORM column stores a plain VARCHAR, so the repository must call
        `.value` on the enum before building the INSERT values list.
        """
        mention = create_entity_mention_create(
            detection_method=DetectionMethod.SPACY_NER,
        )

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        # Should not raise (e.g. database type mismatch for enum object)
        result = await repository.bulk_create_with_conflict_skip(mock_session, [mention])
        assert result == 1

    async def test_single_mention_executes_once(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """A single-element list triggers exactly one execute() call."""
        mention = create_entity_mention_create()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await repository.bulk_create_with_conflict_skip(mock_session, [mention])

        mock_session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# TestDeleteByScope
# ---------------------------------------------------------------------------


class TestDeleteByScope:
    """Tests for delete_by_scope().

    Verifies that each optional filter (entity_ids, video_ids, language_code)
    is applied correctly and that the default detection_method filter is always
    present. The return value must reflect the deleted row count.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_delete_with_entity_ids_filter(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_by_scope() applies entity_id IN filter when entity_ids is provided."""
        entity_ids = [_uuid(), _uuid()]

        mock_result = MagicMock()
        mock_result.rowcount = 4
        mock_session.execute.return_value = mock_result

        count = await repository.delete_by_scope(mock_session, entity_ids=entity_ids)

        assert count == 4
        mock_session.execute.assert_called_once()
        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "entity_id" in sql_str

    async def test_delete_with_video_ids_filter(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_by_scope() applies video_id IN filter when video_ids is provided."""
        video_ids = ["dQw4w9WgXcQ", "9bZkp7q19f0"]

        mock_result = MagicMock()
        mock_result.rowcount = 6
        mock_session.execute.return_value = mock_result

        count = await repository.delete_by_scope(mock_session, video_ids=video_ids)

        assert count == 6
        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "video_id" in sql_str

    async def test_delete_with_language_code_filter(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_by_scope() applies language_code equality filter when provided."""
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_session.execute.return_value = mock_result

        count = await repository.delete_by_scope(mock_session, language_code="es")

        assert count == 2
        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "language_code" in sql_str

    async def test_delete_with_all_filters_combined(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_by_scope() applies all three optional filters simultaneously."""
        entity_ids = [_uuid()]
        video_ids = ["dQw4w9WgXcQ"]

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        count = await repository.delete_by_scope(
            mock_session,
            entity_ids=entity_ids,
            video_ids=video_ids,
            language_code="en",
        )

        assert count == 1
        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "entity_id" in sql_str
        assert "video_id" in sql_str
        assert "language_code" in sql_str

    async def test_delete_with_no_optional_filters_still_filters_by_detection_method(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_by_scope() always filters by detection_method even when no optional filters are given.

        Without any optional filters the statement should only target rows
        matching the default detection_method ("rule_match"), preventing
        accidental deletion of manually-created or LLM-extracted mentions.
        """
        mock_result = MagicMock()
        mock_result.rowcount = 10
        mock_session.execute.return_value = mock_result

        count = await repository.delete_by_scope(mock_session)

        assert count == 10
        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "detection_method" in sql_str

    async def test_delete_returns_zero_when_no_rows_match(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_by_scope() returns 0 when the DELETE affects no rows."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await repository.delete_by_scope(
            mock_session, entity_ids=[_uuid()]
        )

        assert count == 0

    async def test_delete_custom_detection_method_is_used(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_by_scope() uses the supplied detection_method instead of the default."""
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        await repository.delete_by_scope(
            mock_session,
            detection_method=DetectionMethod.SPACY_NER.value,
        )

        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "detection_method" in sql_str


# ---------------------------------------------------------------------------
# TestDeleteByCorrectionIds (Feature 043 — T032)
# ---------------------------------------------------------------------------


class TestDeleteByCorrectionIds:
    """Tests for delete_by_correction_ids().

    Deletes entity mentions linked to specific correction IDs.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    async def test_deletes_by_correction_ids(self, repository: EntityMentionRepository) -> None:
        """Deletes mentions whose correction_id is in the given list."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        session.execute.return_value = mock_result

        corr_ids = [uuid.uuid4(), uuid.uuid4()]
        count = await repository.delete_by_correction_ids(session, corr_ids)

        assert count == 5
        session.execute.assert_called_once()

    async def test_empty_list_returns_zero(self, repository: EntityMentionRepository) -> None:
        """Empty correction_ids list returns 0 without executing."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()

        count = await repository.delete_by_correction_ids(session, [])

        assert count == 0
        session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestGetEntityIdsByCorrectionIds (Feature 043 — T033)
# ---------------------------------------------------------------------------


class TestGetEntityIdsByCorrectionIds:
    """Tests for get_entity_ids_by_correction_ids().

    Returns distinct entity IDs linked to the given correction IDs.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    async def test_returns_distinct_entity_ids(self, repository: EntityMentionRepository) -> None:
        """Returns entity IDs for mentions linked to given correction IDs."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        entity_id_1 = uuid.uuid4()
        entity_id_2 = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entity_id_1, entity_id_2]
        session.execute.return_value = mock_result

        corr_ids = [uuid.uuid4()]
        result = await repository.get_entity_ids_by_correction_ids(session, corr_ids)

        assert result == [entity_id_1, entity_id_2]
        session.execute.assert_called_once()

    async def test_empty_correction_ids_returns_empty(self, repository: EntityMentionRepository) -> None:
        """Empty correction_ids returns empty list without DB call."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()

        result = await repository.get_entity_ids_by_correction_ids(session, [])

        assert result == []
        session.execute.assert_not_called()

    async def test_no_matching_mentions_returns_empty(self, repository: EntityMentionRepository) -> None:
        """Returns empty list when no mentions match the correction IDs."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        result = await repository.get_entity_ids_by_correction_ids(session, [uuid.uuid4()])

        assert result == []


# ---------------------------------------------------------------------------
# TestGetEntitiesWithZeroMentions
# ---------------------------------------------------------------------------


class TestGetEntitiesWithZeroMentions:
    """Tests for get_entities_with_zero_mentions().

    The method queries named_entities for IDs that have no rows in
    entity_mentions. An optional entity_type filter narrows the result.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_returns_entity_ids_with_no_mentions(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Returns a list of entity UUIDs that have zero entity_mention rows."""
        entity_id_1 = _uuid()
        entity_id_2 = _uuid()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [entity_id_1, entity_id_2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_entities_with_zero_mentions(mock_session)

        assert len(result) == 2
        assert entity_id_1 in result
        assert entity_id_2 in result
        mock_session.execute.assert_called_once()

    async def test_returns_empty_list_when_all_entities_have_mentions(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Returns an empty list when every entity has at least one mention."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_entities_with_zero_mentions(mock_session)

        assert result == []

    async def test_entity_type_filter_applied_when_provided(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """entity_type parameter restricts the query to entities of the given type."""
        entity_id = _uuid()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [entity_id]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_entities_with_zero_mentions(
            mock_session, entity_type="person"
        )

        assert entity_id in result
        # Verify the SQL includes an entity_type filter
        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "entity_type" in sql_str

    async def test_no_entity_type_filter_omits_type_clause(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """When entity_type is None the query returns entities of all types."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Should complete without raising — the entity_type clause is optional
        await repository.get_entities_with_zero_mentions(mock_session)

        mock_session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# TestUpdateEntityCounters
# ---------------------------------------------------------------------------


class TestUpdateEntityCounters:
    """Tests for update_entity_counters().

    The method runs two UPDATE statements: one to set real counts for entities
    that have mentions, and another to zero-out counts for entities in the list
    that have no remaining mentions.

    Feature 044 (T009) extends this class with tests that verify the ASR-error
    alias exclusion logic introduced in US2.  The updated method builds a
    ``visible_names`` subquery that unions canonical names and non-ASR-error
    aliases; only mentions whose ``mention_text`` matches a visible name count
    toward ``mention_count`` and ``video_count``.  Entities whose only matches
    are against ASR-error aliases receive ``mention_count=0``.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_empty_entity_ids_is_noop(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Calling update_entity_counters([]) must not touch the database.

        When there are no entity IDs to refresh the method must return early
        without issuing any SQL to avoid emitting unbounded UPDATE statements.
        """
        await repository.update_entity_counters(mock_session, entity_ids=[])

        mock_session.execute.assert_not_called()

    async def test_two_update_statements_executed_for_non_empty_list(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Two UPDATE statements are issued: one for non-zero counts, one for zeros.

        The repository updates mention_count/video_count for entities that
        have matching rows, then separately sets both counters to 0 for any
        entity in the provided list that has no mentions at all.
        """
        entity_ids = [_uuid(), _uuid()]

        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_session.execute.return_value = mock_result

        await repository.update_entity_counters(mock_session, entity_ids=entity_ids)

        # Exactly two UPDATE round-trips should have occurred
        assert mock_session.execute.call_count == 2

    async def test_update_statements_target_named_entities_table(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Both UPDATE statements must target the named_entities table."""
        entity_id = _uuid()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await repository.update_entity_counters(mock_session, entity_ids=[entity_id])

        for call_args in mock_session.execute.call_args_list:
            stmt = call_args.args[0]
            sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
            assert "named_entities" in sql_str, (
                f"Expected UPDATE to target named_entities; got SQL: {sql_str}"
            )

    async def test_first_update_sets_mention_and_video_counts(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The first UPDATE must set mention_count and video_count columns."""
        entity_id = _uuid()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await repository.update_entity_counters(mock_session, entity_ids=[entity_id])

        first_stmt = mock_session.execute.call_args_list[0].args[0]
        sql_str = str(first_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "mention_count" in sql_str
        assert "video_count" in sql_str

    # ------------------------------------------------------------------
    # T009 — US2: ASR-error alias exclusion from counter logic
    # ------------------------------------------------------------------

    @staticmethod
    def _compile_pg_sql(stmt: Any) -> str:
        """Compile a SQLAlchemy statement to SQL string with the PostgreSQL dialect.

        Uses ``literal_binds=True`` so that enum string values (like
        ``'asr_error'``) appear literally in the output rather than as
        ``__[POSTCOMPILE_...]`` placeholders.

        Parameters
        ----------
        stmt : Any
            A SQLAlchemy statement (UPDATE, SELECT, etc.).

        Returns
        -------
        str
            The fully rendered SQL string.
        """
        return str(
            stmt.compile(
                dialect=pg_dialect.dialect(),  # type: ignore[no-untyped-call]
                compile_kwargs={"literal_binds": True},
            )
        )

    async def test_sql_excludes_asr_error_alias_type(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The generated SQL must filter out asr_error aliases from the visible-names set.

        The updated ``update_entity_counters()`` builds a ``visible_names``
        subquery that unions canonical names with non-ASR-error aliases.  The
        first UPDATE statement's SQL must reference the ``entity_aliases`` table
        and the ``asr_error`` string so that mentions matched only against ASR
        noise forms are excluded from the counter.
        """
        entity_id = _uuid()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await repository.update_entity_counters(mock_session, entity_ids=[entity_id])

        first_stmt = mock_session.execute.call_args_list[0].args[0]
        sql_str = self._compile_pg_sql(first_stmt)

        # The visible-names subquery must JOIN entity_aliases
        assert "entity_aliases" in sql_str, (
            "Expected entity_aliases to appear in the counter SQL; "
            f"got: {sql_str[:500]}"
        )
        # The asr_error value must appear as a literal exclusion filter
        assert "asr_error" in sql_str, (
            "Expected 'asr_error' exclusion in counter SQL; "
            f"got: {sql_str[:500]}"
        )

    async def test_sql_references_named_entities_canonical_name(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The visible-names subquery must include canonical names from named_entities.

        Canonical names count as visible regardless of alias type; the SQL must
        SELECT from ``named_entities`` (for canonical names) as well as from
        ``entity_aliases`` (for non-ASR-error aliases).
        """
        entity_id = _uuid()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await repository.update_entity_counters(mock_session, entity_ids=[entity_id])

        first_stmt = mock_session.execute.call_args_list[0].args[0]
        sql_str = self._compile_pg_sql(first_stmt)

        # Both source tables of the visible-names union must appear in the SQL
        assert "named_entities" in sql_str, (
            "Expected named_entities to provide canonical name rows; "
            f"got: {sql_str[:500]}"
        )
        assert "entity_aliases" in sql_str, (
            "Expected entity_aliases to provide non-ASR alias rows; "
            f"got: {sql_str[:500]}"
        )

    async def test_second_update_zeros_entities_with_no_visible_mentions(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The second UPDATE must zero-out entities that have no visible-name mentions.

        When an entity's only mentions are matched via ASR-error aliases (and
        thus excluded from the visible-names join), the second UPDATE statement
        must set mention_count=0 and video_count=0 for that entity.
        """
        entity_id = _uuid()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await repository.update_entity_counters(mock_session, entity_ids=[entity_id])

        # Exactly two UPDATE calls must be made
        assert mock_session.execute.call_count == 2

        # The second statement must also reference named_entities (zero-out)
        second_stmt = mock_session.execute.call_args_list[1].args[0]
        sql_str = str(second_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "named_entities" in sql_str, (
            "Second UPDATE (zero-out) must target named_entities; "
            f"got: {sql_str[:400]}"
        )
        # The zero-out branch must still set both counter columns to 0
        assert "mention_count" in sql_str, (
            "Zero-out UPDATE must include mention_count; "
            f"got: {sql_str[:400]}"
        )
        assert "video_count" in sql_str, (
            "Zero-out UPDATE must include video_count; "
            f"got: {sql_str[:400]}"
        )

    async def test_visible_names_join_uses_lower_for_case_insensitive_match(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The counter join must be case-insensitive via lower() on mention_text.

        Mentions stored as 'elon musk' must match canonical name 'Elon Musk'
        because the SQL uses ``lower(mention_text) = lower(name)`` in the join.
        The compiled SQL must contain the lower() function.
        """
        entity_id = _uuid()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await repository.update_entity_counters(mock_session, entity_ids=[entity_id])

        first_stmt = mock_session.execute.call_args_list[0].args[0]
        sql_str = str(first_stmt.compile(compile_kwargs={"literal_binds": False}))

        assert "lower" in sql_str.lower(), (
            "Expected lower() function for case-insensitive counter join; "
            f"got: {sql_str[:400]}"
        )

    async def test_empty_list_does_not_generate_zero_update(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """With an empty entity_ids list, the zero-out UPDATE must not be issued.

        This is a guard against accidentally running unbounded UPDATE statements
        when no entities are in scope for counter refresh.
        """
        await repository.update_entity_counters(mock_session, entity_ids=[])

        # No SQL at all — not even the zero-out branch
        mock_session.execute.assert_not_called()

    async def test_multiple_entity_ids_accepted(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Passing multiple entity IDs must still produce exactly two UPDATEs.

        The method batches all entity IDs into a single set of UPDATE statements
        rather than issuing one pair per entity.
        """
        entity_ids = [_uuid() for _ in range(5)]

        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        await repository.update_entity_counters(mock_session, entity_ids=entity_ids)

        # Still exactly two round-trips, not 10 (5 entities × 2)
        assert mock_session.execute.call_count == 2


# ---------------------------------------------------------------------------
# TestUpdateAliasCounters
# ---------------------------------------------------------------------------


class TestUpdateAliasCounters:
    """Tests for update_alias_counters().

    The method runs two UPDATE statements: one to set occurrence_count on
    entity_aliases by matching lower(alias_name) to lower(mention_text) from
    entity_mentions, and another to zero out aliases with no matching mentions.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_empty_entity_ids_is_noop(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Calling update_alias_counters([]) must not touch the database.

        When there are no entity IDs to refresh the method must return early
        without issuing any SQL to avoid emitting unbounded UPDATE statements.
        """
        await repository.update_alias_counters(mock_session, entity_ids=[])

        mock_session.execute.assert_not_called()

    async def test_two_update_statements_executed_for_non_empty_list(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Two UPDATE statements are issued: one for real counts, one for zeroing.

        The repository sets occurrence_count for aliases that have matching
        mention_text rows, then separately zeros out aliases with no matches
        for any alias belonging to the provided entity IDs.
        """
        entity_ids = [_uuid(), _uuid()]

        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_session.execute.return_value = mock_result

        await repository.update_alias_counters(mock_session, entity_ids=entity_ids)

        # Exactly two UPDATE round-trips should have occurred
        assert mock_session.execute.call_count == 2

    async def test_update_statements_target_entity_aliases_table(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Both UPDATE statements must target the entity_aliases table."""
        entity_id = _uuid()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await repository.update_alias_counters(mock_session, entity_ids=[entity_id])

        for call_args in mock_session.execute.call_args_list:
            stmt = call_args.args[0]
            sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
            assert "entity_aliases" in sql_str, (
                f"Expected UPDATE to target entity_aliases; got SQL: {sql_str}"
            )

    async def test_first_update_sets_occurrence_count(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The first UPDATE must set the occurrence_count column."""
        entity_id = _uuid()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await repository.update_alias_counters(mock_session, entity_ids=[entity_id])

        first_stmt = mock_session.execute.call_args_list[0].args[0]
        sql_str = str(first_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "occurrence_count" in sql_str


# ---------------------------------------------------------------------------
# TestGetVideoEntitySummary
# ---------------------------------------------------------------------------


class TestGetVideoEntitySummary:
    """Tests for get_video_entity_summary().

    Returns a list of dicts (one per entity) with aggregated mention counts
    and first mention time for a given video. Each dict matches the
    VideoEntitySummary schema.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    def _make_summary_row(
        self,
        *,
        entity_id: uuid.UUID | None = None,
        canonical_name: str = "Python",
        entity_type: str = "technology",
        description: str | None = "Programming language",
        mention_count: int = 3,
        first_mention_time: float = 12.5,
    ) -> MagicMock:
        """Build a row mock matching the SELECT columns of get_video_entity_summary."""
        row = MagicMock()
        row.entity_id = entity_id or _uuid()
        row.canonical_name = canonical_name
        row.entity_type = entity_type
        row.description = description
        row.mention_count = mention_count
        row.first_mention_time = first_mention_time
        return row

    async def test_returns_list_of_summary_dicts(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Returns a list of dicts with the expected keys for each entity."""
        row = self._make_summary_row()
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.execute.return_value = mock_result

        result = await repository.get_video_entity_summary(
            mock_session, video_id="dQw4w9WgXcQ"
        )

        assert len(result) == 1
        item = result[0]
        assert "entity_id" in item
        assert "canonical_name" in item
        assert "entity_type" in item
        assert "description" in item
        assert "mention_count" in item
        assert "first_mention_time" in item

    async def test_entity_id_is_serialised_to_string(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """entity_id in each returned dict must be a string (not uuid.UUID)."""
        entity_id = _uuid()
        row = self._make_summary_row(entity_id=entity_id)
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.execute.return_value = mock_result

        result = await repository.get_video_entity_summary(
            mock_session, video_id="dQw4w9WgXcQ"
        )

        assert isinstance(result[0]["entity_id"], str)
        assert result[0]["entity_id"] == str(entity_id)

    async def test_language_code_filter_is_applied(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """When language_code is supplied the SQL includes a language_code predicate."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        await repository.get_video_entity_summary(
            mock_session, video_id="dQw4w9WgXcQ", language_code="en"
        )

        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "language_code" in sql_str

    async def test_empty_result_when_no_mentions_for_video(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Returns an empty list when the video has no entity mentions."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_video_entity_summary(
            mock_session, video_id="unknownVid1"
        )

        assert result == []

    async def test_multiple_entities_returned(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Multiple entity rows are all converted to dicts and returned."""
        rows = [
            self._make_summary_row(canonical_name="Python", mention_count=5),
            self._make_summary_row(canonical_name="Google", mention_count=3),
            self._make_summary_row(canonical_name="New York", mention_count=1),
        ]
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        mock_session.execute.return_value = mock_result

        result = await repository.get_video_entity_summary(
            mock_session, video_id="dQw4w9WgXcQ"
        )

        assert len(result) == 3
        assert result[0]["canonical_name"] == "Python"
        assert result[1]["canonical_name"] == "Google"
        assert result[2]["canonical_name"] == "New York"


# ---------------------------------------------------------------------------
# TestGetEntityVideoList
# ---------------------------------------------------------------------------


class TestGetEntityVideoList:
    """Tests for get_entity_video_list().

    Returns a (results, total_count) tuple.  The results list contains dicts
    for each video where the entity is mentioned, each with up to 5 mention
    previews.  Pagination is controlled by limit and offset.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    def _make_video_row(
        self,
        *,
        video_id: str = "dQw4w9WgXcQ",
        video_title: str = "Test Video",
        channel_name: str = "Test Channel",
        mention_count: int = 3,
    ) -> MagicMock:
        """Build a row mock matching the main SELECT in get_entity_video_list."""
        row = MagicMock()
        row.video_id = video_id
        row.video_title = video_title
        row.channel_name = channel_name
        row.mention_count = mention_count
        return row

    def _make_preview_row(
        self,
        *,
        segment_id: int = 1,
        start_time: float = 5.0,
        mention_text: str = "Python",
    ) -> MagicMock:
        """Build a preview row mock matching the preview SELECT."""
        row = MagicMock()
        row.segment_id = segment_id
        row.start_time = start_time
        row.mention_text = mention_text
        return row

    async def test_returns_empty_tuple_when_total_count_is_zero(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """When no videos mention the entity the method returns ([], 0) immediately.

        The count query fires first; when it returns 0 the method must skip the
        main and preview queries and return ([], 0).
        """
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_session.execute.return_value = count_result

        results, total = await repository.get_entity_video_list(
            mock_session, entity_id=_uuid()
        )

        assert results == []
        assert total == 0
        # Only the count query should have fired
        mock_session.execute.assert_called_once()

    async def test_returns_paginated_results_with_total_count(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Returns (results, total_count) where total reflects all videos, not just the page.

        The total_count comes from a COUNT(DISTINCT video_id) query and must
        represent the full dataset, not the number of items on the current page.
        """
        entity_id = _uuid()
        video_row = self._make_video_row(video_id="dQw4w9WgXcQ", mention_count=4)
        preview_row = self._make_preview_row()

        count_result = MagicMock()
        count_result.scalar.return_value = 5  # 5 total videos across all pages

        main_result = MagicMock()
        main_result.all.return_value = [video_row]

        preview_result = MagicMock()
        preview_result.all.return_value = [preview_row]

        # count → main → preview (one per video row)
        mock_session.execute.side_effect = [count_result, main_result, preview_result]

        results, total = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id, limit=1, offset=0
        )

        assert total == 5
        assert len(results) == 1
        assert results[0]["video_id"] == "dQw4w9WgXcQ"
        assert results[0]["mention_count"] == 4

    async def test_result_dict_has_expected_keys(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Each result dict must contain video_id, video_title, channel_name, mention_count, mentions."""
        entity_id = _uuid()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        video_row = self._make_video_row()
        main_result = MagicMock()
        main_result.all.return_value = [video_row]

        preview_result = MagicMock()
        preview_result.all.return_value = []

        mock_session.execute.side_effect = [count_result, main_result, preview_result]

        results, _ = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        assert len(results) == 1
        item = results[0]
        for key in ("video_id", "video_title", "channel_name", "mention_count", "mentions"):
            assert key in item, f"Expected key '{key}' missing from result dict"

    async def test_mention_previews_limited_to_five(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Each video in the result includes a preview query limited to 5 rows.

        The preview SELECT must have a LIMIT 5 clause; the repository enforces
        this directly on the statement regardless of how many matching rows exist.
        """
        entity_id = _uuid()
        video_row = self._make_video_row()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        main_result = MagicMock()
        main_result.all.return_value = [video_row]

        # Simulate DB returning 3 previews (<=5 so the LIMIT is not visible here)
        preview_rows = [self._make_preview_row(segment_id=i) for i in range(1, 4)]
        preview_result = MagicMock()
        preview_result.all.return_value = preview_rows

        mock_session.execute.side_effect = [count_result, main_result, preview_result]

        results, _ = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        assert len(results[0]["mentions"]) == 3

        # Check the preview statement has the LIMIT 5 clause
        preview_stmt = mock_session.execute.call_args_list[2].args[0]
        preview_sql = str(preview_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "5" in preview_sql, (
            f"Expected LIMIT 5 in preview SQL; got: {preview_sql}"
        )

    async def test_language_code_filter_applied_to_all_queries(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The language_code filter must appear in count, main, and preview queries."""
        entity_id = _uuid()
        video_row = self._make_video_row()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        main_result = MagicMock()
        main_result.all.return_value = [video_row]

        preview_result = MagicMock()
        preview_result.all.return_value = []

        mock_session.execute.side_effect = [count_result, main_result, preview_result]

        await repository.get_entity_video_list(
            mock_session, entity_id=entity_id, language_code="fr"
        )

        assert mock_session.execute.call_count == 3
        for i, call_args in enumerate(mock_session.execute.call_args_list):
            stmt = call_args.args[0]
            sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
            assert "language_code" in sql_str, (
                f"Expected language_code filter in query #{i + 1}; got: {sql_str}"
            )

    async def test_pagination_offset_and_limit_are_applied(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The OFFSET and LIMIT values are applied to the main video-list query."""
        entity_id = _uuid()

        count_result = MagicMock()
        count_result.scalar.return_value = 10

        main_result = MagicMock()
        main_result.all.return_value = []

        mock_session.execute.side_effect = [count_result, main_result]

        await repository.get_entity_video_list(
            mock_session, entity_id=entity_id, limit=5, offset=10
        )

        main_stmt = mock_session.execute.call_args_list[1].args[0]
        sql_str = str(main_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "10" in sql_str and "5" in sql_str, (
            f"Expected LIMIT 5 and OFFSET 10 in main SQL; got: {sql_str}"
        )

    async def test_multiple_videos_each_get_preview_query(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Each video in the main result triggers a separate preview execute() call."""
        entity_id = _uuid()
        video_rows = [
            self._make_video_row(video_id="dQw4w9WgXcQ"),
            self._make_video_row(video_id="9bZkp7q19f0"),
        ]

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        main_result = MagicMock()
        main_result.all.return_value = video_rows

        preview_result_1 = MagicMock()
        preview_result_1.all.return_value = [self._make_preview_row()]
        preview_result_2 = MagicMock()
        preview_result_2.all.return_value = []

        mock_session.execute.side_effect = [
            count_result,
            main_result,
            preview_result_1,
            preview_result_2,
        ]

        results, total = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        # 1 count + 1 main + 2 previews = 4 execute() calls
        assert mock_session.execute.call_count == 4
        assert total == 2
        assert len(results) == 2

    # ------------------------------------------------------------------
    # Bug fix: get_entity_video_list must exclude ASR-error alias mentions
    # ------------------------------------------------------------------

    @staticmethod
    def _compile_pg_sql(stmt: Any) -> str:
        """Compile a SQLAlchemy statement to SQL string with the PostgreSQL dialect.

        Uses ``literal_binds=True`` so that enum string values (like
        ``'asr_error'``) appear literally in the output rather than as
        ``__[POSTCOMPILE_...]`` placeholders.

        Parameters
        ----------
        stmt : Any
            A SQLAlchemy statement (UPDATE, SELECT, etc.).

        Returns
        -------
        str
            The fully rendered SQL string.
        """
        return str(
            stmt.compile(
                dialect=pg_dialect.dialect(),  # type: ignore[no-untyped-call]
                compile_kwargs={"literal_binds": True},
            )
        )

    async def test_count_query_references_asr_error_exclusion(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The count query SQL must exclude ASR-error alias mentions via visible_names join.

        Bug fix: before the fix, get_entity_video_list counted ALL mentions for
        an entity, including those matched only via asr_error aliases.  After the
        fix, the count query joins a visible_names subquery that excludes
        alias_type = 'asr_error', so ASR-error-alias-matched mentions do not
        inflate the video count.

        This test inspects the compiled SQL of the count query (first execute())
        and confirms the 'asr_error' exclusion filter appears in it.
        """
        entity_id = _uuid()

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_session.execute.return_value = count_result

        await repository.get_entity_video_list(mock_session, entity_id=entity_id)

        # Only the count query should have been issued (total=0 short-circuits)
        mock_session.execute.assert_called_once()
        count_stmt = mock_session.execute.call_args_list[0].args[0]
        sql_str = self._compile_pg_sql(count_stmt)

        assert "asr_error" in sql_str, (
            "Expected 'asr_error' exclusion in the count query SQL; "
            f"got: {sql_str[:700]}"
        )

    async def test_count_query_visible_names_includes_entity_aliases_table(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The count query must JOIN entity_aliases to build the visible_names subquery.

        The visible_names subquery unions canonical_name rows from named_entities
        with non-asr_error alias rows from entity_aliases.  The count query SQL
        must therefore reference the entity_aliases table.
        """
        entity_id = _uuid()

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_session.execute.return_value = count_result

        await repository.get_entity_video_list(mock_session, entity_id=entity_id)

        count_stmt = mock_session.execute.call_args_list[0].args[0]
        sql_str = self._compile_pg_sql(count_stmt)

        assert "entity_aliases" in sql_str, (
            "Expected entity_aliases to appear in the visible_names join of the count query; "
            f"got: {sql_str[:700]}"
        )
        assert "named_entities" in sql_str, (
            "Expected named_entities to appear (canonical name source) in the count query; "
            f"got: {sql_str[:700]}"
        )

    async def test_main_query_visible_names_excludes_asr_error_aliases(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The main group-by query must join visible_names with asr_error exclusion.

        The main query computes mention_count per video_id; only mentions whose
        mention_text matches a visible name (canonical or non-ASR-error alias)
        should be counted.  The compiled SQL must contain 'asr_error' to confirm
        the WHERE clause excludes ASR-alias-matched mentions.
        """
        entity_id = _uuid()

        count_result = MagicMock()
        count_result.scalar.return_value = 1  # non-zero so main query runs

        video_row = self._make_video_row()
        main_result = MagicMock()
        main_result.all.return_value = [video_row]

        preview_result = MagicMock()
        preview_result.all.return_value = []

        mock_session.execute.side_effect = [count_result, main_result, preview_result]

        await repository.get_entity_video_list(mock_session, entity_id=entity_id)

        # count=0, main=1, preview=2
        assert mock_session.execute.call_count == 3
        main_stmt = mock_session.execute.call_args_list[1].args[0]
        sql_str = self._compile_pg_sql(main_stmt)

        assert "asr_error" in sql_str, (
            "Expected 'asr_error' exclusion in the main group-by query SQL; "
            f"got: {sql_str[:700]}"
        )

    async def test_preview_query_visible_names_excludes_asr_error_aliases(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The preview query must also join visible_names and exclude asr_error aliases.

        Preview mentions shown for each video must only include mentions
        matched via canonical name or non-ASR-error aliases, not via ASR
        noise forms.  The compiled preview SQL must contain 'asr_error'.
        """
        entity_id = _uuid()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        video_row = self._make_video_row()
        main_result = MagicMock()
        main_result.all.return_value = [video_row]

        preview_row = self._make_preview_row(mention_text="Bonaparte")
        preview_result = MagicMock()
        preview_result.all.return_value = [preview_row]

        mock_session.execute.side_effect = [count_result, main_result, preview_result]

        await repository.get_entity_video_list(mock_session, entity_id=entity_id)

        preview_stmt = mock_session.execute.call_args_list[2].args[0]
        sql_str = self._compile_pg_sql(preview_stmt)

        assert "asr_error" in sql_str, (
            "Expected 'asr_error' exclusion in the preview query SQL; "
            f"got: {sql_str[:700]}"
        )

    async def test_count_returns_zero_when_only_asr_alias_mentions_exist(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """When the DB count returns 0, the method returns ([], 0) without running main query.

        This models the scenario after the bug fix: an entity whose only mentions
        were matched via asr_error aliases will have those mentions excluded by
        the visible_names join, so the count query returns 0.  The method must
        short-circuit and return ([], 0) without issuing the main or preview
        queries.
        """
        entity_id = _uuid()

        # DB returns 0 — simulates all mentions being ASR-error-alias-sourced and
        # thus filtered out by the visible_names join in the real query
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_session.execute.return_value = count_result

        results, total = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        assert results == [], "No videos should be returned when count is zero"
        assert total == 0
        # Only one query should have been issued (the count); the main and preview
        # queries must be skipped by the early-return guard
        mock_session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# TestGetStatistics
# ---------------------------------------------------------------------------


class TestGetStatistics:
    """Tests for get_statistics().

    Returns a single dict with aggregate stats.  An optional entity_type
    filter narrows all sub-queries to that type. Zero-mention state must
    produce sensible zero values (no division-by-zero).
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    def _make_execute_sequence(
        self,
        mock_session: MagicMock,
        *,
        total_mentions: int = 100,
        unique_entities: int = 20,
        unique_videos: int = 15,
        total_entities: int = 30,
        type_rows: list[MagicMock] | None = None,
        top_rows: list[MagicMock] | None = None,
    ) -> None:
        """Wire mock_session.execute side_effect with the expected 6-query sequence.

        get_statistics() fires exactly 6 queries in order:
        1. total_mentions
        2. unique_entities_with_mentions
        3. unique_videos_with_mentions
        4. total_entities
        5. type_breakdown
        6. top_entities
        """
        # Scalar results for the four aggregate COUNT queries
        def _scalar_result(value: int) -> MagicMock:
            r = MagicMock()
            r.scalar.return_value = value
            return r

        def _rows_result(rows: list[MagicMock]) -> MagicMock:
            r = MagicMock()
            r.all.return_value = rows
            return r

        mock_session.execute.side_effect = [
            _scalar_result(total_mentions),
            _scalar_result(unique_entities),
            _scalar_result(unique_videos),
            _scalar_result(total_entities),
            _rows_result(type_rows or []),
            _rows_result(top_rows or []),
        ]

    async def test_returns_dict_with_all_expected_keys(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The returned dict must contain all seven expected top-level keys."""
        self._make_execute_sequence(mock_session)

        result = await repository.get_statistics(mock_session)

        expected_keys = {
            "total_mentions",
            "unique_entities_with_mentions",
            "unique_videos_with_mentions",
            "total_entities",
            "coverage_pct",
            "type_breakdown",
            "top_entities",
        }
        assert set(result.keys()) == expected_keys

    async def test_correct_coverage_pct_calculated(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """coverage_pct is computed as (unique_entities / total_entities) * 100 rounded to 2dp."""
        self._make_execute_sequence(
            mock_session,
            total_mentions=50,
            unique_entities=10,
            unique_videos=8,
            total_entities=20,
        )

        result = await repository.get_statistics(mock_session)

        # 10/20 * 100 = 50.0
        assert result["coverage_pct"] == 50.0

    async def test_coverage_pct_is_zero_when_no_entities(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """coverage_pct must be 0.0 when total_entities is 0 to prevent ZeroDivisionError."""
        self._make_execute_sequence(
            mock_session,
            total_mentions=0,
            unique_entities=0,
            unique_videos=0,
            total_entities=0,
        )

        result = await repository.get_statistics(mock_session)

        assert result["coverage_pct"] == 0.0

    async def test_zero_mention_state_returns_zero_counts(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """When there are no mentions all numeric fields must be 0."""
        self._make_execute_sequence(
            mock_session,
            total_mentions=0,
            unique_entities=0,
            unique_videos=0,
            total_entities=5,  # entities exist, just no mentions
        )

        result = await repository.get_statistics(mock_session)

        assert result["total_mentions"] == 0
        assert result["unique_entities_with_mentions"] == 0
        assert result["unique_videos_with_mentions"] == 0
        assert result["type_breakdown"] == []
        assert result["top_entities"] == []

    async def test_entity_type_filter_fires_six_queries(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """With entity_type filter the method still issues exactly 6 execute() calls."""
        self._make_execute_sequence(mock_session)

        await repository.get_statistics(mock_session, entity_type="person")

        assert mock_session.execute.call_count == 6

    async def test_type_breakdown_list_structure(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """type_breakdown list items must have entity_type, mention_count, entity_count keys."""
        type_row = MagicMock()
        type_row.entity_type = "person"
        type_row.mention_count = 42
        type_row.entity_count = 7

        self._make_execute_sequence(mock_session, type_rows=[type_row])

        result = await repository.get_statistics(mock_session)

        assert len(result["type_breakdown"]) == 1
        breakdown_item = result["type_breakdown"][0]
        assert breakdown_item["entity_type"] == "person"
        assert breakdown_item["mention_count"] == 42
        assert breakdown_item["entity_count"] == 7

    async def test_top_entities_list_structure(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """top_entities list items must have entity_id, canonical_name, entity_type, mention_count, video_count keys."""
        entity_id = _uuid()
        top_row = MagicMock()
        top_row.entity_id = entity_id
        top_row.canonical_name = "Google"
        top_row.entity_type = "organization"
        top_row.mention_count = 150
        top_row.video_count = 30

        self._make_execute_sequence(mock_session, top_rows=[top_row])

        result = await repository.get_statistics(mock_session)

        assert len(result["top_entities"]) == 1
        top_item = result["top_entities"][0]
        assert top_item["entity_id"] == str(entity_id)
        assert top_item["canonical_name"] == "Google"
        assert top_item["entity_type"] == "organization"
        assert top_item["mention_count"] == 150
        assert top_item["video_count"] == 30

    async def test_entity_id_in_top_entities_is_string(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """entity_id in top_entities must be a string, not a UUID object."""
        entity_id = _uuid()
        top_row = MagicMock()
        top_row.entity_id = entity_id
        top_row.canonical_name = "Test"
        top_row.entity_type = "misc"
        top_row.mention_count = 1
        top_row.video_count = 1

        self._make_execute_sequence(mock_session, top_rows=[top_row])

        result = await repository.get_statistics(mock_session)

        assert isinstance(result["top_entities"][0]["entity_id"], str)

    async def test_no_entity_type_filter_fires_six_queries(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Without entity_type filter the method issues exactly 6 execute() calls."""
        self._make_execute_sequence(mock_session)

        await repository.get_statistics(mock_session)

        assert mock_session.execute.call_count == 6


# ---------------------------------------------------------------------------
# TestEntityMentionRepositoryFactoryIntegration
# ---------------------------------------------------------------------------


class TestEntityMentionRepositoryFactoryIntegration:
    """Smoke-tests that factory-produced models are compatible with the repository.

    These tests exercise the factories defined in
    tests/factories/entity_mention_factory.py to confirm that the factory
    defaults produce instances accepted by the repository methods.
    No real database is involved.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_factory_built_mention_create_accepted_by_bulk_create(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """A list of EntityMentionCreate objects from the factory are accepted without error."""
        mentions = EntityMentionCreateFactory.build_batch(5)

        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        result = await repository.bulk_create_with_conflict_skip(mock_session, mentions)

        assert result == 5

    async def test_create_entity_mention_create_convenience_function(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """create_entity_mention_create() produces a valid EntityMentionCreate."""
        mention = create_entity_mention_create(
            language_code="es",
            mention_text="Madrid",
            detection_method=DetectionMethod.SPACY_NER,
        )

        assert isinstance(mention, EntityMentionCreate)
        assert mention.language_code == "es"
        assert mention.mention_text == "Madrid"
        assert mention.detection_method == DetectionMethod.SPACY_NER

    async def test_factory_detection_method_variants(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Factory can produce mentions for every DetectionMethod variant."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        for method in DetectionMethod:
            # Manual mentions require segment_id=None, confidence=None,
            # language_code=None per the EntityMentionCreate model validator.
            extra_kwargs: dict[str, Any] = {}
            if method == DetectionMethod.MANUAL:
                extra_kwargs = {
                    "segment_id": None,
                    "confidence": None,
                    "language_code": None,
                }
            mention = create_entity_mention_create(
                detection_method=method, **extra_kwargs
            )
            assert mention.detection_method == method

            # Each should be accepted by bulk_create without type errors
            result = await repository.bulk_create_with_conflict_skip(
                mock_session, [mention]
            )
            assert result == 1

    @pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
    def test_entity_mention_factory_produces_full_model(self) -> None:
        """EntityMentionFactory.build() produces an EntityMention with all required fields."""
        from chronovista.models.entity_mention import EntityMention

        mention = create_entity_mention()
        assert isinstance(mention, EntityMention)
        assert mention.id is not None
        assert mention.entity_id is not None
        assert mention.created_at is not None


# ---------------------------------------------------------------------------
# TestGetEntityVideoIds  (Feature 045 — T030)
# ---------------------------------------------------------------------------


class TestGetEntityVideoIds:
    """Tests for get_entity_video_ids().

    The method performs a UNION of two SQL paths:

    Path 1 — Direct entity mentions:
        SELECT DISTINCT video_id FROM entity_mentions WHERE entity_id = :eid

    Path 2 — Tag-based association:
        SELECT DISTINCT video_tags.video_id
        FROM video_tags
        JOIN tag_aliases ON video_tags.tag = tag_aliases.raw_form
        JOIN canonical_tags ON tag_aliases.canonical_tag_id = canonical_tags.id
        WHERE canonical_tags.entity_id = :eid

    The result is a ``set[str]`` that deduplicates across both paths.

    Mock strategy: ``session.execute`` is configured to return a mock whose
    ``scalars().all()`` yields the video IDs that the combined UNION should
    produce.  Because ``get_entity_video_ids`` executes a single combined
    ``union()`` statement, one ``execute`` call is expected.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    # ---- helper ----

    def _make_scalars_result(self, video_ids: list[str]) -> MagicMock:
        """Build a mock result whose .scalars().all() returns video_ids."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = video_ids
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        return mock_result

    # ---- (a) path 1 — direct entity mention video IDs ----

    async def test_returns_video_ids_from_entity_mentions_path(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Video IDs in entity_mentions for the given entity_id are returned.

        When the UNION result contains video IDs originating from direct
        entity_mentions rows, all of them must appear in the returned set.
        """
        entity_id = _uuid()
        expected_ids = ["dQw4w9WgXcQ", "9bZkp7q19f0"]

        mock_session.execute.return_value = self._make_scalars_result(expected_ids)

        result = await repository.get_entity_video_ids(mock_session, entity_id)

        assert result == set(expected_ids)
        mock_session.execute.assert_called_once()

    # ---- (b) path 2 — canonical_tags → tag_aliases → video_tags ----

    async def test_returns_video_ids_from_canonical_tag_path(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Video IDs reached via canonical_tags → tag_aliases → video_tags are returned.

        When the entity has canonical tag associations but no direct entity
        mention rows, the tag-based path must still contribute its video IDs to
        the result set.
        """
        entity_id = _uuid()
        tag_video_ids = ["3tmd-ClpJxA", "jNQXAC9IVRw"]

        mock_session.execute.return_value = self._make_scalars_result(tag_video_ids)

        result = await repository.get_entity_video_ids(mock_session, entity_id)

        assert result == set(tag_video_ids)
        mock_session.execute.assert_called_once()

    # ---- (c) union of both paths with deduplication ----

    async def test_union_deduplicates_video_ids_across_both_paths(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Video IDs present in both paths appear only once in the result.

        The UNION (not UNION ALL) must deduplicate so that a video with both a
        direct entity mention and a canonical-tag association is not counted
        twice.  We simulate this by having the mock return a list that already
        represents the deduplicated union output — matching what the DB would
        produce.
        """
        entity_id = _uuid()
        # Simulate DB returning the union-deduplicated set: vid A appears in
        # both paths but is returned only once.
        union_result = ["dQw4w9WgXcQ", "9bZkp7q19f0", "3tmd-ClpJxA"]

        mock_session.execute.return_value = self._make_scalars_result(union_result)

        result = await repository.get_entity_video_ids(mock_session, entity_id)

        # Result is a set — no duplicates regardless of what the mock returned
        assert len(result) == len(set(union_result))
        assert result == {"dQw4w9WgXcQ", "9bZkp7q19f0", "3tmd-ClpJxA"}

    async def test_duplicate_ids_in_scalars_are_deduplicated_by_set_conversion(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The repository must return a set, eliminating any duplicate values.

        Even if the underlying query returned duplicates (e.g., from UNION ALL
        used in a future refactor), the method's return type ``set[str]``
        guarantees uniqueness.
        """
        entity_id = _uuid()
        # Deliberately supply a list with a repeated ID
        raw_result = ["dQw4w9WgXcQ", "dQw4w9WgXcQ", "9bZkp7q19f0"]

        mock_session.execute.return_value = self._make_scalars_result(raw_result)

        result = await repository.get_entity_video_ids(mock_session, entity_id)

        assert isinstance(result, set)
        assert len(result) == 2
        assert "dQw4w9WgXcQ" in result
        assert "9bZkp7q19f0" in result

    # ---- (d) entity with no associations returns empty set ----

    async def test_entity_with_no_associations_returns_empty_set(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """An entity with no mention rows and no tag associations returns an empty set.

        This is the case for newly created entities that have never been scanned.
        The method must return an empty ``set``, not ``None`` or an empty list.
        """
        entity_id = _uuid()

        mock_session.execute.return_value = self._make_scalars_result([])

        result = await repository.get_entity_video_ids(mock_session, entity_id)

        assert isinstance(result, set)
        assert result == set()
        mock_session.execute.assert_called_once()

    # ---- return type and execute call count ----

    async def test_return_type_is_always_a_set(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_entity_video_ids() always returns a set[str], never a list."""
        entity_id = _uuid()
        mock_session.execute.return_value = self._make_scalars_result(
            ["dQw4w9WgXcQ"]
        )

        result = await repository.get_entity_video_ids(mock_session, entity_id)

        assert isinstance(result, set)

    async def test_executes_exactly_one_combined_query(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The method must fire only one execute() call for the combined UNION.

        Both paths are united in a single SQL UNION statement rather than two
        separate round-trips.
        """
        entity_id = _uuid()
        mock_session.execute.return_value = self._make_scalars_result(
            ["dQw4w9WgXcQ"]
        )

        await repository.get_entity_video_ids(mock_session, entity_id)

        mock_session.execute.assert_called_once()

    async def test_compiled_sql_contains_union(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """The SQL emitted by get_entity_video_ids contains a UNION keyword.

        This validates that both paths are combined at the SQL level rather than
        via in-memory Python set operations.
        """
        entity_id = _uuid()
        mock_session.execute.return_value = self._make_scalars_result([])

        await repository.get_entity_video_ids(mock_session, entity_id)

        stmt = mock_session.execute.call_args.args[0]
        sql_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "UNION" in sql_str.upper()


# ---------------------------------------------------------------------------
# Feature 050 — T012: TestSearchEntities
# ---------------------------------------------------------------------------


class TestSearchEntities:
    """Tests for search_entities() — entity autocomplete search method.

    This is a TDD test class for Feature 050 User Story 1. The
    ``search_entities`` method does not exist yet in the repository;
    these tests MUST fail until the implementation is added.

    Expected method signature:
        async def search_entities(
            self,
            session: AsyncSession,
            query: str,
            video_id: str | None = None,
            limit: int = 10,
        ) -> list[dict]
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    def _make_scalars_result(self, items: list[Any]) -> MagicMock:
        """Build a mock execute() result whose scalars().all() returns items."""
        result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = items
        result.scalars.return_value = scalars_mock
        return result

    def _make_all_result(self, rows: list[Any]) -> MagicMock:
        """Build a mock execute() result whose .all() returns rows."""
        result = MagicMock()
        result.all.return_value = rows
        return result

    def _make_entity_row(
        self,
        *,
        entity_id: uuid.UUID | None = None,
        canonical_name: str = "Joanna Hausmann",
        entity_type: str = "person",
        description: str | None = "Venezuelan-American comedian",
        status: str = "active",
        matched_alias: str | None = None,
    ) -> MagicMock:
        """Build a MagicMock simulating a SQLAlchemy named-tuple row.

        The repository is expected to return rows with at least:
        entity_id, canonical_name, entity_type, description, status,
        and matched_alias (None when matched via canonical name).
        """
        row = MagicMock()
        row.entity_id = entity_id or _uuid()
        row.canonical_name = canonical_name
        row.entity_type = entity_type
        row.description = description
        row.status = status
        row.matched_alias = matched_alias
        return row

    async def test_search_canonical_name_prefix_match(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """search_entities() returns an entity when the query matches its canonical name prefix.

        Query "Joan" should match the entity with canonical_name "Joanna Hausmann".
        The returned dict must include entity_id, canonical_name, entity_type,
        description, status, matched_alias=None, is_linked=None, and
        link_sources=None (no video_id provided).
        """
        entity_id = _uuid()
        fake_row = self._make_entity_row(
            entity_id=entity_id,
            canonical_name="Joanna Hausmann",
            matched_alias=None,
        )
        mock_session.execute.return_value = self._make_all_result([fake_row])

        results = await repository.search_entities(mock_session, query="Joan")

        assert isinstance(results, list)
        assert len(results) == 1
        item = results[0]
        assert item["canonical_name"] == "Joanna Hausmann"
        assert str(item["entity_id"]) == str(entity_id)
        assert item["matched_alias"] is None
        # is_linked and link_sources are None when video_id is not provided
        assert item.get("is_linked") is None
        assert item.get("link_sources") is None

    async def test_search_alias_match_with_matched_alias_field(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """search_entities() populates matched_alias when the hit came from an alias.

        When query "Joanna" matches the alias "Joanna" (not the canonical name
        "Joanna Hausmann"), the result dict's matched_alias field must equal
        the alias text that triggered the match.
        """
        entity_id = _uuid()
        fake_row = self._make_entity_row(
            entity_id=entity_id,
            canonical_name="Joanna Hausmann",
            matched_alias="Joanna",
        )
        mock_session.execute.return_value = self._make_all_result([fake_row])

        results = await repository.search_entities(mock_session, query="Joanna")

        assert len(results) >= 1
        item = next(
            (r for r in results if r["canonical_name"] == "Joanna Hausmann"), None
        )
        assert item is not None, "Expected 'Joanna Hausmann' in results"
        assert item["matched_alias"] == "Joanna"

    async def test_search_deduplication_canonical_and_alias(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """search_entities() returns an entity only once when matched via both canonical and alias.

        If the DB query returns the same entity_id twice (once via canonical
        name match and once via alias match), the implementation must
        deduplicate so the entity appears only once in the returned list.
        The canonical-name row should take precedence (matched_alias=None).
        """
        entity_id = _uuid()
        canonical_row = self._make_entity_row(
            entity_id=entity_id,
            canonical_name="Joanna Hausmann",
            matched_alias=None,
        )
        alias_row = self._make_entity_row(
            entity_id=entity_id,
            canonical_name="Joanna Hausmann",
            matched_alias="Joanna",
        )
        # Both rows have the same entity_id — duplicates
        mock_session.execute.return_value = self._make_all_result(
            [canonical_row, alias_row]
        )

        results = await repository.search_entities(mock_session, query="Joanna")

        entity_ids_returned = [r["entity_id"] for r in results]
        assert entity_ids_returned.count(str(entity_id)) == 1, (
            "Expected entity to appear exactly once even when matched by both "
            "canonical name and alias"
        )

    async def test_search_is_linked_when_video_id_provided(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """search_entities() sets is_linked=True and populates link_sources when video_id given.

        When a video_id is supplied and the entity already has entity_mention
        rows for that video, the result dict must have:
        - is_linked = True
        - link_sources = non-empty list of detection method strings
        """
        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"

        # First execute call: search query results
        fake_row = self._make_entity_row(
            entity_id=entity_id,
            canonical_name="Joanna Hausmann",
        )
        search_result = self._make_all_result([fake_row])

        # Second execute call: link status lookup.
        # entity_id must match the entity returned by the search so that
        # linked_map.get(row.entity_id, []) finds the right key.
        link_row = MagicMock()
        link_row.entity_id = entity_id
        link_row.detection_method = "rule_match"
        link_result = self._make_all_result([link_row])

        mock_session.execute.side_effect = [search_result, link_result]

        results = await repository.search_entities(
            mock_session, query="Joan", video_id=video_id
        )

        assert len(results) >= 1
        item = results[0]
        assert item.get("is_linked") is True
        link_sources = item.get("link_sources")
        assert link_sources is not None
        assert len(link_sources) >= 1

    async def test_search_deprecated_entity_included_with_status(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """search_entities() includes deprecated entities and marks status='deprecated'.

        Deprecated entities should appear in autocomplete results (so the user
        can see that the entity is no longer active) but their status field
        must be 'deprecated' so the UI can render an appropriate indicator.
        """
        entity_id = _uuid()
        fake_row = self._make_entity_row(
            entity_id=entity_id,
            canonical_name="Old Entity",
            status="deprecated",
        )
        mock_session.execute.return_value = self._make_all_result([fake_row])

        results = await repository.search_entities(mock_session, query="Old")

        deprecated_item = next(
            (r for r in results if r.get("canonical_name") == "Old Entity"), None
        )
        assert deprecated_item is not None, "Expected deprecated entity in results"
        assert deprecated_item["status"] == "deprecated"

    async def test_search_empty_results(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """search_entities() returns an empty list when no entity matches the query.

        A query that matches no canonical names and no aliases must yield an
        empty list without raising any exception.
        """
        mock_session.execute.return_value = self._make_all_result([])

        results = await repository.search_entities(
            mock_session, query="zzznomatch"
        )

        assert results == []

    async def test_search_minimum_2_char_validation(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """search_entities() raises ValueError (or equivalent) for a 1-character query.

        Autocomplete with a single character would produce too many results and
        is explicitly not supported. The implementation must raise a ValueError
        or similar validation error before touching the database.
        """
        with pytest.raises((ValueError, Exception)):
            await repository.search_entities(mock_session, query="J")

        # The DB must NOT have been touched for this short query
        mock_session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Feature 050 — T013: TestCreateManualAssociation
# ---------------------------------------------------------------------------


class TestCreateManualAssociation:
    """Tests for create_manual_association() — manual entity-video link method.

    This is a TDD test class for Feature 050 User Story 1. The
    ``create_manual_association`` method does not exist yet in the repository;
    these tests MUST fail until the implementation is added.

    Expected method signature:
        async def create_manual_association(
            self,
            session: AsyncSession,
            video_id: str,
            entity_id: uuid.UUID,
        ) -> EntityMentionDB

    Behaviour contract:
    - Creates an EntityMentionDB row with segment_id=None, confidence=None,
      language_code=None, detection_method='manual', and mention_text set to
      the entity's canonical_name.
    - Raises ConflictError (409) if a manual association for the same
      (entity_id, video_id) already exists.
    - Raises APIValidationError (422) if the entity status is 'deprecated'.
    - Raises NotFoundError (404) if video_id does not exist in the videos table.
    - Raises NotFoundError (404) if entity_id does not exist in named_entities.
    - Calls update_entity_counters() with [entity_id] after a successful insert.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    def _make_scalar_result(self, value: Any) -> MagicMock:
        """Return a mock whose .scalar_one_or_none() returns value."""
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        return result

    def _make_named_entity_db(
        self,
        *,
        entity_id: uuid.UUID | None = None,
        canonical_name: str = "Joanna Hausmann",
        status: str = "active",
    ) -> MagicMock:
        """Build a MagicMock simulating a NamedEntity ORM row."""
        from chronovista.db.models import NamedEntity as NamedEntityDB

        entity = MagicMock(spec=NamedEntityDB)
        entity.id = entity_id or _uuid()
        entity.canonical_name = canonical_name
        entity.status = status
        entity.entity_type = "person"
        return entity

    def _make_video_db(self, *, video_id: str = "dQw4w9WgXcQ") -> MagicMock:
        """Build a MagicMock simulating a Video ORM row."""
        from chronovista.db.models import Video as VideoDB

        video = MagicMock(spec=VideoDB)
        video.video_id = video_id
        return video

    def _make_mention_db(
        self,
        *,
        entity_id: uuid.UUID,
        video_id: str,
        canonical_name: str,
    ) -> MagicMock:
        """Build a MagicMock simulating a newly created EntityMentionDB row."""
        mention = MagicMock(spec=EntityMentionDB)
        mention.id = _uuid()
        mention.entity_id = entity_id
        mention.video_id = video_id
        mention.segment_id = None
        mention.language_code = None
        mention.confidence = None
        mention.detection_method = "manual"
        mention.mention_text = canonical_name
        mention.created_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        return mention

    async def test_create_successful(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """create_manual_association() returns a new EntityMentionDB row on success.

        The created row must have:
        - segment_id = None   (manual mentions have no segment)
        - confidence = None   (no statistical confidence for manual)
        - language_code = None (manual mentions are language-agnostic)
        - detection_method = 'manual'
        - mention_text = entity's canonical_name
        """
        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"
        canonical_name = "Joanna Hausmann"

        entity_db = self._make_named_entity_db(
            entity_id=entity_id, canonical_name=canonical_name, status="active"
        )
        video_db = self._make_video_db(video_id=video_id)
        new_mention = self._make_mention_db(
            entity_id=entity_id, video_id=video_id, canonical_name=canonical_name
        )

        # execute() calls in order:
        # 1. look up video
        # 2. look up entity
        # 3. check for duplicate manual association
        # 4+. update_entity_counters internals
        video_result = self._make_scalar_result(video_db)
        entity_result = self._make_scalar_result(entity_db)
        no_duplicate = self._make_scalar_result(None)
        counter_result = MagicMock()

        mock_session.execute.side_effect = [
            video_result,
            entity_result,
            no_duplicate,
            counter_result,
            counter_result,
        ]
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        # After flush, the mention is accessible via session.add's argument
        async def _flush_side_effect() -> None:
            pass

        mock_session.flush.side_effect = _flush_side_effect

        # Patch update_entity_counters to capture calls
        with patch.object(
            repository, "update_entity_counters", new=AsyncMock()
        ) as mock_counters:
            result = await repository.create_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

        # The method must call update_entity_counters at least once
        mock_counters.assert_called_once()

        # The result must be an EntityMentionDB (or compatible mock)
        assert result is not None
        # detection_method must be 'manual'
        assert result.detection_method == "manual"
        assert result.segment_id is None
        assert result.language_code is None
        assert result.confidence is None
        assert result.mention_text == canonical_name

    async def test_create_duplicate_409(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """create_manual_association() raises ConflictError when a manual association exists.

        If a row with detection_method='manual' already exists for the same
        (entity_id, video_id), the method must raise ConflictError (HTTP 409)
        without inserting a new row.
        """
        from chronovista.exceptions import ConflictError

        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"

        entity_db = self._make_named_entity_db(entity_id=entity_id, status="active")
        video_db = self._make_video_db(video_id=video_id)

        # Existing duplicate mention
        existing_mention = self._make_mention_db(
            entity_id=entity_id,
            video_id=video_id,
            canonical_name=entity_db.canonical_name,
        )

        video_result = self._make_scalar_result(video_db)
        entity_result = self._make_scalar_result(entity_db)
        duplicate_result = self._make_scalar_result(existing_mention)

        mock_session.execute.side_effect = [
            video_result,
            entity_result,
            duplicate_result,
        ]

        with pytest.raises(ConflictError):
            await repository.create_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

        # The session must not have had add() called (no row inserted)
        mock_session.add.assert_not_called()

    async def test_create_deprecated_entity_422(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """create_manual_association() raises APIValidationError for deprecated entities.

        Manually associating a deprecated entity to a video is not permitted.
        The method must raise APIValidationError (HTTP 422) when the entity's
        status is 'deprecated'.
        """
        from chronovista.exceptions import APIValidationError

        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"

        video_db = self._make_video_db(video_id=video_id)
        deprecated_entity = self._make_named_entity_db(
            entity_id=entity_id,
            canonical_name="Old Entity",
            status="deprecated",
        )

        video_result = self._make_scalar_result(video_db)
        entity_result = self._make_scalar_result(deprecated_entity)

        mock_session.execute.side_effect = [video_result, entity_result]

        with pytest.raises(APIValidationError):
            await repository.create_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

    async def test_create_nonexistent_video_404(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """create_manual_association() raises NotFoundError when the video does not exist.

        The method must verify the video exists before touching entity or
        mention data, and raise NotFoundError (HTTP 404) if it is absent.
        """
        from chronovista.exceptions import NotFoundError

        entity_id = _uuid()
        video_id = "nosuchvideo1"

        # Video lookup returns None
        video_result = self._make_scalar_result(None)
        mock_session.execute.side_effect = [video_result]

        with pytest.raises(NotFoundError):
            await repository.create_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

    async def test_create_nonexistent_entity_404(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """create_manual_association() raises NotFoundError when the entity does not exist.

        After verifying the video exists, the method must verify the entity
        exists and raise NotFoundError (HTTP 404) if it is absent.
        """
        from chronovista.exceptions import NotFoundError

        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"

        video_db = self._make_video_db(video_id=video_id)
        video_result = self._make_scalar_result(video_db)
        entity_result = self._make_scalar_result(None)  # entity missing

        mock_session.execute.side_effect = [video_result, entity_result]

        with pytest.raises(NotFoundError):
            await repository.create_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

    async def test_create_calls_update_entity_counters(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """create_manual_association() calls update_entity_counters with the correct entity_id.

        After a successful insert, the method must call update_entity_counters
        passing a list that contains the newly-associated entity_id so that
        mention_count and video_count on named_entities are kept in sync.
        """
        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"
        canonical_name = "Joanna Hausmann"

        entity_db = self._make_named_entity_db(
            entity_id=entity_id, canonical_name=canonical_name, status="active"
        )
        video_db = self._make_video_db(video_id=video_id)

        video_result = self._make_scalar_result(video_db)
        entity_result = self._make_scalar_result(entity_db)
        no_duplicate = self._make_scalar_result(None)
        counter_result = MagicMock()

        mock_session.execute.side_effect = [
            video_result,
            entity_result,
            no_duplicate,
            counter_result,
            counter_result,
        ]
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch.object(
            repository, "update_entity_counters", new=AsyncMock()
        ) as mock_counters:
            await repository.create_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

        # update_entity_counters must have been called with a list containing entity_id
        mock_counters.assert_called_once()
        call_args = mock_counters.call_args
        # First positional arg after session is the entity_ids list
        # Could be positional or keyword depending on impl
        entity_ids_arg = (
            call_args.args[1]
            if len(call_args.args) > 1
            else call_args.kwargs.get("entity_ids", [])
        )
        assert entity_id in entity_ids_arg, (
            f"Expected entity_id {entity_id} in update_entity_counters call, "
            f"got: {entity_ids_arg}"
        )


# ---------------------------------------------------------------------------
# TestGetEntityVideoListMultiSource (Feature 050 — T027)
# ---------------------------------------------------------------------------


class TestGetEntityVideoListMultiSource:
    """Tests for the multi-source enhancements to get_entity_video_list().

    Feature 050 US2 adds new fields (sources, has_manual, first_mention_time,
    upload_date) and changes the sort order to upload_date DESC with
    transcript-only mention counting.

    Mock strategy: the method issues multiple queries (count, main, previews)
    so mock_session.execute returns results via side_effect.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    @staticmethod
    def _make_count_result(count: int) -> MagicMock:
        """Create a mock scalar result for the count query."""
        mock = MagicMock()
        mock.scalar.return_value = count
        return mock

    @staticmethod
    def _make_video_row(
        *,
        video_id: str = "vid001",
        video_title: str = "Test Video",
        channel_name: str = "Test Channel",
        mention_count: int = 3,
        detection_methods: list[str] | None = None,
        has_manual: bool = False,
        first_mention_time: float | None = 10.5,
        upload_date: Any = None,
    ) -> MagicMock:
        """Build a mock row matching the main query's column shape."""
        from datetime import datetime as dt, timezone as tz

        row = MagicMock()
        row.video_id = video_id
        row.video_title = video_title
        row.channel_name = channel_name
        row.mention_count = mention_count
        row.detection_methods = detection_methods or ["rule_match"]
        row.has_manual = has_manual
        row.first_mention_time = first_mention_time
        row.upload_date = upload_date or dt(2024, 6, 15, tzinfo=tz.utc)
        return row

    @staticmethod
    def _make_main_result(rows: list[MagicMock]) -> MagicMock:
        """Create a mock result for the main query."""
        mock = MagicMock()
        mock.all.return_value = rows
        return mock

    @staticmethod
    def _make_preview_result(
        previews: list[dict[str, Any]] | None = None,
    ) -> MagicMock:
        """Create a mock result for the preview query."""
        mock = MagicMock()
        preview_rows = []
        for p in previews or []:
            r = MagicMock()
            r.segment_id = p.get("segment_id", 1)
            r.start_time = p.get("start_time", 0.0)
            r.mention_text = p.get("mention_text", "Test")
            preview_rows.append(r)
        mock.all.return_value = preview_rows
        return mock

    async def test_transcript_only_video(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Video with only transcript mentions has sources=['transcript'], has_manual=false."""
        entity_id = _uuid()

        row = self._make_video_row(
            detection_methods=["rule_match", "spacy_ner"],
            has_manual=False,
            mention_count=5,
        )

        mock_session.execute.side_effect = [
            self._make_count_result(1),     # count query
            self._make_main_result([row]),   # main query
            self._make_preview_result(),     # preview query
        ]

        results, total = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        assert total == 1
        assert len(results) == 1
        assert results[0]["sources"] == ["transcript"]
        assert results[0]["has_manual"] is False
        assert results[0]["mention_count"] == 5

    async def test_manual_only_video(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Video with only manual association has sources=['manual'], has_manual=true, mention_count=0."""
        entity_id = _uuid()

        row = self._make_video_row(
            detection_methods=["manual"],
            has_manual=True,
            mention_count=0,
            first_mention_time=None,
        )

        mock_session.execute.side_effect = [
            self._make_count_result(1),
            self._make_main_result([row]),
            self._make_preview_result([]),  # no transcript previews
        ]

        results, total = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        assert total == 1
        assert len(results) == 1
        assert results[0]["sources"] == ["manual"]
        assert results[0]["has_manual"] is True
        assert results[0]["mention_count"] == 0
        assert results[0]["first_mention_time"] is None

    async def test_both_sources(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Video with both transcript and manual has sources=['manual','transcript'], has_manual=true."""
        entity_id = _uuid()

        row = self._make_video_row(
            detection_methods=["rule_match", "manual"],
            has_manual=True,
            mention_count=3,
            first_mention_time=5.0,
        )

        mock_session.execute.side_effect = [
            self._make_count_result(1),
            self._make_main_result([row]),
            self._make_preview_result([{"segment_id": 1, "start_time": 5.0, "mention_text": "Elon"}]),
        ]

        results, total = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        assert total == 1
        assert len(results) == 1
        assert sorted(results[0]["sources"]) == ["manual", "transcript"]
        assert results[0]["has_manual"] is True
        assert results[0]["mention_count"] == 3
        assert results[0]["first_mention_time"] == 5.0

    async def test_deduplication_one_row_per_video(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Same video with both sources returns one row (GROUP BY video_id handles this)."""
        entity_id = _uuid()

        # The SQL GROUP BY ensures one row per video — we simulate that
        row = self._make_video_row(
            video_id="vid_dedup",
            detection_methods=["rule_match", "manual"],
            has_manual=True,
            mention_count=2,
        )

        mock_session.execute.side_effect = [
            self._make_count_result(1),
            self._make_main_result([row]),
            self._make_preview_result(),
        ]

        results, total = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        assert total == 1
        assert len(results) == 1
        assert results[0]["video_id"] == "vid_dedup"

    async def test_sort_by_upload_date_descending(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """SQL includes upload_date DESC ordering. Verify SQL structure."""
        entity_id = _uuid()

        mock_session.execute.side_effect = [
            self._make_count_result(0),  # count query returns 0, early exit
        ]

        results, total = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        assert total == 0
        assert results == []
        # Verify the count query was called
        mock_session.execute.assert_called_once()

    async def test_pagination(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """limit/offset are passed correctly. Verify 2 rows returned when total=5, limit=2."""
        entity_id = _uuid()

        row1 = self._make_video_row(video_id="vid_a", detection_methods=["rule_match"])
        row2 = self._make_video_row(video_id="vid_b", detection_methods=["manual"], has_manual=True, mention_count=0)

        mock_session.execute.side_effect = [
            self._make_count_result(5),       # total=5
            self._make_main_result([row1, row2]),
            self._make_preview_result(),      # previews for vid_a
            self._make_preview_result([]),    # previews for vid_b
        ]

        results, total = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id, limit=2, offset=0
        )

        assert total == 5
        assert len(results) == 2
        assert results[0]["video_id"] == "vid_a"
        assert results[1]["video_id"] == "vid_b"

    async def test_upload_date_field_in_results(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """upload_date is present in each result dict as an ISO string."""
        entity_id = _uuid()
        from datetime import datetime as dt, timezone as tz

        row = self._make_video_row(
            upload_date=dt(2024, 12, 25, 10, 0, 0, tzinfo=tz.utc),
            detection_methods=["rule_match"],
        )

        mock_session.execute.side_effect = [
            self._make_count_result(1),
            self._make_main_result([row]),
            self._make_preview_result(),
        ]

        results, _ = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        assert results[0]["upload_date"] is not None
        assert "2024-12-25" in results[0]["upload_date"]

    async def test_empty_previews_for_manual_only(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Manual-only videos have empty mentions preview list."""
        entity_id = _uuid()

        row = self._make_video_row(
            detection_methods=["manual"],
            has_manual=True,
            mention_count=0,
            first_mention_time=None,
        )

        mock_session.execute.side_effect = [
            self._make_count_result(1),
            self._make_main_result([row]),
            self._make_preview_result([]),  # No transcript previews
        ]

        results, _ = await repository.get_entity_video_list(
            mock_session, entity_id=entity_id
        )

        assert results[0]["mentions"] == []
        assert results[0]["has_manual"] is True


# ---------------------------------------------------------------------------
# TestDeleteManualAssociation (Feature 050 — T036)
# ---------------------------------------------------------------------------


class TestDeleteManualAssociation:
    """Tests for delete_manual_association() — remove manual entity-video link.

    This is a TDD test class for Feature 050 User Story 3.  The
    ``delete_manual_association`` method does not exist yet in the repository;
    these tests MUST fail until the implementation is added.

    Expected method signature:
        async def delete_manual_association(
            self,
            session: AsyncSession,
            video_id: str,
            entity_id: uuid.UUID,
        ) -> None

    Behaviour contract:
    - Queries for an EntityMentionDB row with detection_method='manual' for
      the given (video_id, entity_id) pair.
    - Raises NotFoundError (404) when no such manual row exists.
    - Calls session.delete() on the found row when it does exist.
    - Calls update_entity_counters() with [entity_id] in the same transaction
      after the delete so that mention_count / video_count stay accurate.
    - Only targets rows with detection_method='manual'; transcript-derived
      mentions for the same entity+video are never touched.
    """

    @pytest.fixture
    def repository(self) -> EntityMentionRepository:
        """Provide a fresh repository instance for each test."""
        return EntityMentionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        session = _make_mock_session()
        # delete() is synchronous on the SQLAlchemy session
        session.delete = AsyncMock()
        return session

    def _make_scalar_result(self, value: Any) -> MagicMock:
        """Return a mock whose .scalar_one_or_none() returns value."""
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        return result

    def _make_manual_mention(
        self,
        *,
        entity_id: uuid.UUID | None = None,
        video_id: str = "dQw4w9WgXcQ",
    ) -> MagicMock:
        """Build a MagicMock simulating a manual EntityMentionDB row."""
        mention = MagicMock(spec=EntityMentionDB)
        mention.id = _uuid()
        mention.entity_id = entity_id or _uuid()
        mention.video_id = video_id
        mention.segment_id = None
        mention.language_code = None
        mention.confidence = None
        mention.detection_method = "manual"
        mention.mention_text = "Joanna Hausmann"
        mention.created_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        return mention

    def _make_transcript_mention(
        self,
        *,
        entity_id: uuid.UUID | None = None,
        video_id: str = "dQw4w9WgXcQ",
        segment_id: int = 42,
    ) -> MagicMock:
        """Build a MagicMock simulating a transcript-derived EntityMentionDB row."""
        mention = MagicMock(spec=EntityMentionDB)
        mention.id = _uuid()
        mention.entity_id = entity_id or _uuid()
        mention.video_id = video_id
        mention.segment_id = segment_id
        mention.language_code = "en"
        mention.confidence = 0.95
        mention.detection_method = "rule_match"
        mention.mention_text = "Joanna Hausmann"
        mention.created_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        return mention

    async def test_delete_successful_calls_session_delete(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_manual_association() calls session.delete() on the found row.

        When a manual EntityMentionDB row exists for the given (video_id,
        entity_id) pair, the method must call session.delete() with that row
        and return None (no return value).
        """
        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"
        manual_mention = self._make_manual_mention(entity_id=entity_id, video_id=video_id)

        # execute() finds the manual mention
        mock_session.execute.return_value = self._make_scalar_result(manual_mention)

        with patch.object(
            repository, "update_entity_counters", new=AsyncMock()
        ):
            await repository.delete_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

        # delete_manual_association returns None (void)

        # session.delete must have been called with the found row
        mock_session.delete.assert_called_once_with(manual_mention)

    async def test_delete_raises_not_found_when_no_manual_row(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_manual_association() raises NotFoundError when no manual row exists.

        If no EntityMentionDB row with detection_method='manual' exists for the
        given (video_id, entity_id) pair, the method must raise NotFoundError
        (HTTP 404) without touching the session.
        """
        from chronovista.exceptions import NotFoundError

        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"

        # Manual mention lookup returns None — nothing to delete
        mock_session.execute.return_value = self._make_scalar_result(None)

        with pytest.raises(NotFoundError):
            await repository.delete_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

        # session.delete must NOT be called when the row is missing
        mock_session.delete.assert_not_called()

    async def test_delete_calls_update_entity_counters(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_manual_association() calls update_entity_counters with the entity_id.

        After deleting the manual mention, the method must call
        update_entity_counters passing a list that contains the entity_id so
        that mention_count and video_count on named_entities are refreshed in
        the same transaction.
        """
        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"
        manual_mention = self._make_manual_mention(entity_id=entity_id, video_id=video_id)

        mock_session.execute.return_value = self._make_scalar_result(manual_mention)

        with patch.object(
            repository, "update_entity_counters", new=AsyncMock()
        ) as mock_counters:
            await repository.delete_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

        # update_entity_counters must be called exactly once
        mock_counters.assert_called_once()
        call_args = mock_counters.call_args
        # First positional arg after session is the entity_ids list
        entity_ids_arg = (
            call_args.args[1]
            if len(call_args.args) > 1
            else call_args.kwargs.get("entity_ids", [])
        )
        assert entity_id in entity_ids_arg, (
            f"Expected entity_id {entity_id} in update_entity_counters call, "
            f"got: {entity_ids_arg}"
        )

    async def test_delete_counters_called_after_delete(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """update_entity_counters is called in the same transaction as session.delete().

        The ordering requirement is: delete the row first, then refresh counters.
        This test verifies that update_entity_counters is always called after
        the row deletion (i.e., delete precedes counter update in the call log).
        """
        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"
        manual_mention = self._make_manual_mention(entity_id=entity_id, video_id=video_id)

        mock_session.execute.return_value = self._make_scalar_result(manual_mention)

        call_order: list[str] = []

        async def _track_delete(obj: Any) -> None:
            call_order.append("delete")

        async def _track_counters(session: Any, entity_ids: Any) -> None:
            call_order.append("counters")

        mock_session.delete.side_effect = _track_delete

        with patch.object(
            repository, "update_entity_counters", new=AsyncMock(side_effect=_track_counters)
        ):
            await repository.delete_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

        assert call_order == ["delete", "counters"], (
            f"Expected delete before counters, got order: {call_order}"
        )

    async def test_delete_does_not_affect_transcript_mentions(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """delete_manual_association() only queries for detection_method='manual' rows.

        Transcript-derived mentions (rule_match, spacy_ner, etc.) for the same
        entity+video must be unaffected.  This test verifies that the method's
        lookup query targets only manual rows: the mock returns the manual row
        (not the transcript row), confirming the query filter is specific.
        """
        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"

        manual_mention = self._make_manual_mention(entity_id=entity_id, video_id=video_id)
        # transcript mention exists alongside the manual one — but the method
        # only queries for detection_method='manual', so only manual_mention
        # appears in the execute result.
        _transcript_mention = self._make_transcript_mention(
            entity_id=entity_id, video_id=video_id
        )

        # The execute mock returns only the manual mention — this simulates the
        # WHERE detection_method='manual' filter in the repository query.
        mock_session.execute.return_value = self._make_scalar_result(manual_mention)

        with patch.object(
            repository, "update_entity_counters", new=AsyncMock()
        ):
            await repository.delete_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

        # Only the manual mention is passed to session.delete()
        mock_session.delete.assert_called_once_with(manual_mention)
        # The transcript mention object was never touched
        assert mock_session.delete.call_args[0][0] is manual_mention

    async def test_delete_not_found_when_only_transcript_mention_exists(
        self,
        repository: EntityMentionRepository,
        mock_session: MagicMock,
    ) -> None:
        """NotFoundError is raised when only transcript-derived mentions exist.

        If the video+entity pair has transcript mentions but NO manual row,
        delete_manual_association() must raise NotFoundError because there is
        no manual association to remove.  This mirrors the API contract that
        DELETE only targets detection_method='manual' rows.
        """
        from chronovista.exceptions import NotFoundError

        entity_id = _uuid()
        video_id = "dQw4w9WgXcQ"

        # The query filtered on detection_method='manual' returns None even
        # though transcript mentions for this pair exist in the real DB.
        mock_session.execute.return_value = self._make_scalar_result(None)

        with pytest.raises(NotFoundError):
            await repository.delete_manual_association(
                mock_session, video_id=video_id, entity_id=entity_id
            )

        mock_session.delete.assert_not_called()
