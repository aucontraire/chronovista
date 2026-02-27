"""
Tests for TagOperationLogRepository.

Covers all public methods:
- create() (inherited from BaseSQLAlchemyRepository, driven by TagOperationLogCreate)
- get() – lookup by UUID primary key
- exists() – presence check by UUID primary key
- get_recent() – ordered list with default and custom limits
- get_by_operation_id() – semantic alias for get()

Mock strategy: every test creates a MagicMock(spec=AsyncSession) whose
``execute`` attribute is an AsyncMock. This mirrors the pattern used in
``test_canonical_tag_repository.py`` and avoids any real database I/O.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import TagOperationLog as TagOperationLogDB
from chronovista.models.tag_operation_log import TagOperationLogCreate
from chronovista.repositories.tag_operation_log_repository import (
    TagOperationLogRepository,
)
from tests.factories.tag_operation_log_factory import (
    TagOperationLogFactory,
    create_merge_operation_log,
    create_split_operation_log,
    create_tag_operation_log,
)

# Ensures every async test in this module is recognised by pytest-asyncio
# regardless of how coverage is invoked (see CLAUDE.md §pytest-asyncio section).
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_uuid() -> uuid.UUID:
    """Return a UUIDv7 expressed as a stdlib ``uuid.UUID`` instance."""
    return uuid.UUID(bytes=uuid7().bytes)


def _make_log_db(
    *,
    id: uuid.UUID | None = None,
    operation_type: str = "create",
    source_canonical_ids: list[str] | None = None,
    target_canonical_id: uuid.UUID | None = None,
    affected_alias_ids: list[str] | None = None,
    reason: str | None = None,
    performed_by: str = "system",
    performed_at: datetime | None = None,
    rollback_data: dict[str, Any] | None = None,
    rolled_back: bool = False,
    rolled_back_at: datetime | None = None,
) -> TagOperationLogDB:
    """
    Build an in-memory TagOperationLogDB instance without a DB session.

    Parameters
    ----------
    id : uuid.UUID, optional
        Primary key; generated via UUIDv7 when omitted.
    operation_type : str
        One of: merge, split, rename, delete, create.
    source_canonical_ids : list[str], optional
        JSONB list of source canonical-tag UUIDs as strings.
    target_canonical_id : uuid.UUID, optional
        Target canonical tag UUID for merge/rename operations.
    affected_alias_ids : list[str], optional
        JSONB list of alias UUIDs as strings.
    reason : str, optional
        Human-readable reason for the operation.
    performed_by : str
        Actor identifier (default ``"system"``).
    performed_at : datetime, optional
        Timestamp; defaults to 2024-01-15 10:30 UTC.
    rollback_data : dict, optional
        Snapshot data for rollback; defaults to empty dict.
    rolled_back : bool
        Whether the operation has been reversed.
    rolled_back_at : datetime, optional
        Timestamp of the rollback, if any.

    Returns
    -------
    TagOperationLogDB
        An ORM instance suitable for use in mock return values.
    """
    return TagOperationLogDB(
        id=id or _make_uuid(),
        operation_type=operation_type,
        source_canonical_ids=source_canonical_ids or [],
        target_canonical_id=target_canonical_id,
        affected_alias_ids=affected_alias_ids or [],
        reason=reason,
        performed_by=performed_by,
        performed_at=performed_at or datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        rollback_data=rollback_data or {},
        rolled_back=rolled_back,
        rolled_back_at=rolled_back_at,
    )


# ---------------------------------------------------------------------------
# TestTagOperationLogRepositoryInit
# ---------------------------------------------------------------------------


class TestTagOperationLogRepositoryInit:
    """Tests that the repository wires the correct ORM model."""

    async def test_model_is_tag_operation_log_db(self) -> None:
        """Repository must be initialised with TagOperationLogDB."""
        repo = TagOperationLogRepository()
        assert repo.model is TagOperationLogDB

    async def test_repository_exposes_expected_methods(self) -> None:
        """All public methods described in the spec must exist on the repository."""
        repo = TagOperationLogRepository()
        for method_name in ("create", "get", "exists", "get_recent", "get_by_operation_id"):
            assert hasattr(repo, method_name), f"Missing method: {method_name}"


# ---------------------------------------------------------------------------
# TestTagOperationLogRepositoryCreate
# ---------------------------------------------------------------------------


class TestTagOperationLogRepositoryCreate:
    """Tests for create() which is inherited from BaseSQLAlchemyRepository."""

    @pytest.fixture
    def repository(self) -> TagOperationLogRepository:
        """Create repository instance."""
        return TagOperationLogRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create a mock AsyncSession with async flush/refresh."""
        session = MagicMock(spec=AsyncSession)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    async def test_create_with_minimal_pydantic_model(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """
        create() with a minimal TagOperationLogCreate (only operation_type) calls
        session.add, flush, and refresh in order.
        """
        obj_in = TagOperationLogCreate(operation_type="create")
        db_log = _make_log_db(operation_type="create")
        mock_session.refresh.side_effect = lambda obj: None

        # Patch the ORM constructor so we control the returned object.
        with patch.object(
            TagOperationLogDB,
            "__init__",
            return_value=None,
        ):
            # We can't easily intercept __init__ and still return db_log, so
            # instead we verify session interaction through the real flow:
            pass

        # Use a simpler approach: verify via side effects on session.refresh
        # that create() passes through the full add→flush→refresh cycle.
        result_holder: list[TagOperationLogDB] = []

        async def _fake_refresh(obj: TagOperationLogDB) -> None:
            result_holder.append(obj)

        mock_session.refresh.side_effect = _fake_refresh

        returned = await repository.create(mock_session, obj_in=obj_in)

        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()
        # The object passed to session.add must be a TagOperationLogDB instance.
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, TagOperationLogDB)
        assert added_obj.operation_type == "create"

    async def test_create_with_merge_operation(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """
        create() with a merge-type TagOperationLogCreate sets all provided fields
        on the resulting ORM object.
        """
        source_id = _make_uuid()
        target_id = _make_uuid()
        alias_id = _make_uuid()

        second_source_id = _make_uuid()
        obj_in = TagOperationLogCreate(
            operation_type="merge",
            source_canonical_ids=[str(source_id), str(second_source_id)],
            target_canonical_id=target_id,
            affected_alias_ids=[str(alias_id)],
            reason="Duplicate tags consolidated",
            performed_by="backfill_script",
            rollback_data={"original_form": "Python3"},
        )

        await repository.create(mock_session, obj_in=obj_in)

        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, TagOperationLogDB)
        assert added_obj.operation_type == "merge"
        assert added_obj.performed_by == "backfill_script"
        assert added_obj.reason == "Duplicate tags consolidated"
        assert added_obj.rollback_data == {"original_form": "Python3"}

    async def test_create_with_all_operation_types(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """
        create() accepts all five valid operation_type values without raising.
        """
        for op_type in ("merge", "split", "rename", "delete", "create"):
            mock_session.add.reset_mock()
            mock_session.flush.reset_mock()
            mock_session.refresh.reset_mock()

            obj_in = TagOperationLogCreate(operation_type=op_type)
            await repository.create(mock_session, obj_in=obj_in)

            added_obj = mock_session.add.call_args[0][0]
            assert added_obj.operation_type == op_type

    async def test_create_default_performed_by_is_cli(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """
        When performed_by is not supplied, the Pydantic default 'cli' is used and
        propagated to the ORM object.
        """
        obj_in = TagOperationLogCreate(operation_type="delete")
        assert obj_in.performed_by == "cli"

        await repository.create(mock_session, obj_in=obj_in)

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.performed_by == "cli"

    async def test_create_with_rollback_data_dict(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """
        rollback_data dict is faithfully passed to the ORM constructor.
        """
        rollback_payload: dict[str, Any] = {
            "old_canonical_form": "ML",
            "aliases_affected": ["ml", "M.L."],
            "video_count_snapshot": 42,
        }
        obj_in = TagOperationLogCreate(
            operation_type="rename",
            rollback_data=rollback_payload,
        )

        await repository.create(mock_session, obj_in=obj_in)

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.rollback_data == rollback_payload


# ---------------------------------------------------------------------------
# TestTagOperationLogRepositoryGet
# ---------------------------------------------------------------------------


class TestTagOperationLogRepositoryGet:
    """Tests for get() – lookup by UUID primary key."""

    @pytest.fixture
    def repository(self) -> TagOperationLogRepository:
        """Create repository instance."""
        return TagOperationLogRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create a mock AsyncSession."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    async def test_get_returns_matching_log_entry(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get() returns the TagOperationLogDB when it exists."""
        log_id = _make_uuid()
        db_log = _make_log_db(id=log_id, operation_type="split")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = db_log
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, log_id)

        assert result is db_log
        mock_session.execute.assert_awaited_once()

    async def test_get_returns_none_when_not_found(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get() returns None for a UUID that does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, _make_uuid())

        assert result is None
        mock_session.execute.assert_awaited_once()

    async def test_get_executes_exactly_one_query(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get() issues exactly one SELECT to the session."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        await repository.get(mock_session, _make_uuid())

        assert mock_session.execute.await_count == 1

    async def test_get_with_factory_produced_log(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get() works correctly when the return value is a factory-built object."""
        factory_log = create_tag_operation_log(operation_type="rename")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = factory_log
        mock_session.execute.return_value = mock_result

        # TagOperationLogFactory produces uuid7 instances; convert for the call.
        log_id = uuid.UUID(bytes=factory_log.id.bytes)
        result = await repository.get(mock_session, log_id)

        assert result is factory_log
        assert result.operation_type == "rename"


# ---------------------------------------------------------------------------
# TestTagOperationLogRepositoryExists
# ---------------------------------------------------------------------------


class TestTagOperationLogRepositoryExists:
    """Tests for exists() – Boolean presence check by UUID."""

    @pytest.fixture
    def repository(self) -> TagOperationLogRepository:
        """Create repository instance."""
        return TagOperationLogRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create a mock AsyncSession."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    async def test_exists_returns_true_when_row_found(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """exists() returns True when the SELECT finds a matching row."""
        log_id = _make_uuid()

        # session.execute(...).first() is not None → True
        mock_result = MagicMock()
        mock_result.first.return_value = (log_id,)  # non-None row
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, log_id)

        assert result is True
        mock_session.execute.assert_awaited_once()

    async def test_exists_returns_false_when_row_missing(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """exists() returns False when the SELECT returns no rows."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, _make_uuid())

        assert result is False
        mock_session.execute.assert_awaited_once()

    async def test_exists_executes_exactly_one_query(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """exists() must issue exactly one lightweight SELECT per call."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        await repository.exists(mock_session, _make_uuid())
        await repository.exists(mock_session, _make_uuid())

        assert mock_session.execute.await_count == 2

    async def test_exists_true_for_factory_built_log(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """exists() correctly reflects presence for a factory-generated log."""
        factory_log = create_merge_operation_log()
        log_id = uuid.UUID(bytes=factory_log.id.bytes)

        mock_result = MagicMock()
        mock_result.first.return_value = (log_id,)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, log_id)

        assert result is True


# ---------------------------------------------------------------------------
# TestTagOperationLogRepositoryGetRecent
# ---------------------------------------------------------------------------


class TestTagOperationLogRepositoryGetRecent:
    """Tests for get_recent() – ordered list with configurable limit."""

    @pytest.fixture
    def repository(self) -> TagOperationLogRepository:
        """Create repository instance."""
        return TagOperationLogRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create a mock AsyncSession."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    async def test_get_recent_returns_all_logs_when_within_default_limit(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_recent() with no limit argument returns up to 20 entries."""
        logs = [_make_log_db(operation_type="create") for _ in range(5)]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = logs
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_recent(mock_session)

        assert result == logs
        assert len(result) == 5
        mock_session.execute.assert_awaited_once()

    async def test_get_recent_respects_custom_limit(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_recent() honours an explicit limit parameter."""
        logs = [_make_log_db(operation_type="merge") for _ in range(3)]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = logs
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_recent(mock_session, limit=3)

        assert result == logs
        assert len(result) == 3

    async def test_get_recent_returns_empty_list_when_no_logs(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_recent() returns [] when the table has no entries."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_recent(mock_session)

        assert result == []

    async def test_get_recent_result_is_a_list(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_recent() always returns a list (not a SQLAlchemy ScalarResult)."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [_make_log_db()]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_recent(mock_session)

        assert isinstance(result, list)

    async def test_get_recent_limit_one_returns_single_item_list(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_recent(limit=1) returns exactly one item."""
        single_log = _make_log_db(operation_type="delete")

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [single_log]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_recent(mock_session, limit=1)

        assert len(result) == 1
        assert result[0] is single_log

    async def test_get_recent_with_mixed_operation_types(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """
        get_recent() can return logs of different operation types as produced by
        the factory helpers.
        """
        create_log = create_tag_operation_log(operation_type="create")
        merge_log = create_merge_operation_log()
        split_log = create_split_operation_log()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [create_log, merge_log, split_log]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_recent(mock_session, limit=10)

        assert len(result) == 3
        operation_types = {entry.operation_type for entry in result}
        assert "create" in operation_types
        assert "merge" in operation_types
        assert "split" in operation_types

    async def test_get_recent_executes_exactly_one_query(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_recent() must not issue more than one database round-trip."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await repository.get_recent(mock_session, limit=50)

        assert mock_session.execute.await_count == 1


# ---------------------------------------------------------------------------
# TestTagOperationLogRepositoryGetByOperationId
# ---------------------------------------------------------------------------


class TestTagOperationLogRepositoryGetByOperationId:
    """
    Tests for get_by_operation_id() – semantic alias for get().

    The implementation delegates to self.get(session, operation_id), so these
    tests verify both the delegation and the contract of the alias.
    """

    @pytest.fixture
    def repository(self) -> TagOperationLogRepository:
        """Create repository instance."""
        return TagOperationLogRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create a mock AsyncSession."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    async def test_delegates_to_get_and_returns_log(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_operation_id() returns the same object as get() for the same UUID."""
        log_id = _make_uuid()
        db_log = _make_log_db(id=log_id, operation_type="rename")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = db_log
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_operation_id(mock_session, log_id)

        assert result is db_log
        mock_session.execute.assert_awaited_once()

    async def test_returns_none_when_operation_id_not_found(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_operation_id() returns None for an unknown operation UUID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_operation_id(mock_session, _make_uuid())

        assert result is None

    async def test_get_by_operation_id_is_equivalent_to_get(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """
        get_by_operation_id() must produce identical results to calling get()
        directly with the same UUID. We verify this by patching get() and
        confirming it is invoked with the correct argument.
        """
        operation_id = _make_uuid()
        db_log = _make_log_db(id=operation_id)

        # Patch repository.get to record its invocation.
        original_get = repository.get

        get_call_args: list[uuid.UUID] = []

        async def _spy_get(session: AsyncSession, id: uuid.UUID) -> TagOperationLogDB | None:
            get_call_args.append(id)
            # Reproduce the real SELECT path via mock.
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = db_log
            mock_session.execute.return_value = mock_result
            return await original_get(session, id)

        repository.get = _spy_get  # type: ignore[method-assign]

        result = await repository.get_by_operation_id(mock_session, operation_id)

        assert result is db_log
        assert len(get_call_args) == 1
        assert get_call_args[0] == operation_id

    async def test_get_by_operation_id_with_merge_factory_log(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_operation_id() works with a factory-built merge log entry."""
        factory_log = create_merge_operation_log(reason="Normalisation pass")
        log_id = uuid.UUID(bytes=factory_log.id.bytes)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = factory_log
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_operation_id(mock_session, log_id)

        assert result is factory_log
        assert result.operation_type == "merge"
        assert result.reason == "Normalisation pass"

    async def test_get_by_operation_id_issues_single_query(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_operation_id() must not fan out into extra queries."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        await repository.get_by_operation_id(mock_session, _make_uuid())

        assert mock_session.execute.await_count == 1


# ---------------------------------------------------------------------------
# TestTagOperationLogRepositoryEdgeCases
# ---------------------------------------------------------------------------


class TestTagOperationLogRepositoryEdgeCases:
    """Edge-case and boundary tests that cut across multiple methods."""

    @pytest.fixture
    def repository(self) -> TagOperationLogRepository:
        """Create repository instance."""
        return TagOperationLogRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create a mock AsyncSession."""
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    async def test_create_with_empty_source_canonical_ids(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """TagOperationLogCreate defaults source_canonical_ids to empty list."""
        obj_in = TagOperationLogCreate(operation_type="create")
        assert obj_in.source_canonical_ids == []

        await repository.create(mock_session, obj_in=obj_in)

        added = mock_session.add.call_args[0][0]
        assert added.source_canonical_ids == []

    async def test_create_with_many_source_ids(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """TagOperationLogCreate accepts arbitrarily many source_canonical_ids."""
        ids = [str(_make_uuid()) for _ in range(10)]
        obj_in = TagOperationLogCreate(
            operation_type="merge",
            source_canonical_ids=ids,
        )
        assert len(obj_in.source_canonical_ids) == 10

        await repository.create(mock_session, obj_in=obj_in)

        added = mock_session.add.call_args[0][0]
        assert len(added.source_canonical_ids) == 10

    async def test_get_and_exists_are_independent_sessions(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """
        get() and exists() can be called sequentially on the same mock session
        without interfering with each other's results.
        """
        log_id = _make_uuid()
        db_log = _make_log_db(id=log_id)

        get_result = MagicMock()
        get_result.scalar_one_or_none.return_value = db_log

        exists_result = MagicMock()
        exists_result.first.return_value = (log_id,)

        mock_session.execute.side_effect = [get_result, exists_result]

        fetched = await repository.get(mock_session, log_id)
        found = await repository.exists(mock_session, log_id)

        assert fetched is db_log
        assert found is True
        assert mock_session.execute.await_count == 2

    async def test_get_recent_with_limit_zero_returns_empty(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """
        When limit=0 is passed the mock returns an empty list; the repository
        must propagate this without error.
        """
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_recent(mock_session, limit=0)

        assert result == []

    async def test_pydantic_create_rejects_invalid_operation_type(self) -> None:
        """
        TagOperationLogCreate raises ValueError for unknown operation types.
        This guards the repository against receiving bad input before it reaches
        the database.
        """
        import pytest

        with pytest.raises(Exception):
            TagOperationLogCreate(operation_type="invalid_op")

    async def test_pydantic_create_all_valid_operation_types(self) -> None:
        """TagOperationLogCreate accepts each of the five defined operation types."""
        for op in ("merge", "split", "rename", "delete", "create"):
            obj = TagOperationLogCreate(operation_type=op)
            assert obj.operation_type == op

    async def test_get_recent_returns_list_of_tag_operation_log_db_instances(
        self,
        repository: TagOperationLogRepository,
        mock_session: MagicMock,
    ) -> None:
        """Each element returned by get_recent() is a TagOperationLogDB."""
        logs = [
            _make_log_db(operation_type="create"),
            _make_log_db(operation_type="delete"),
        ]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = logs
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_recent(mock_session)

        for entry in result:
            assert isinstance(entry, TagOperationLogDB)
