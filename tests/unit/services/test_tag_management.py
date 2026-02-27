"""
Tests for TagManagementService shared utilities.

Covers the three private helper methods that underpin all tag curation
operations:

- ``_validate_active_tag``: looks up a canonical tag by normalized form and
  asserts it is active, raising ``ValueError`` if it is missing, merged, or
  deprecated.
- ``_recalculate_counts``: fires COUNT and COUNT DISTINCT queries then issues
  an UPDATE statement to keep ``alias_count`` and ``video_count`` in sync.
- ``_log_operation``: creates a ``TagOperationLogCreate`` Pydantic model and
  persists it via the operation-log repository, returning the new entry UUID.

All database I/O is fully mocked — these are pure unit tests that validate
service-layer logic without any real database connection.

References
----------
- TagManagementService implementation:
  src/chronovista/services/tag_management.py
- TagOperationLogCreate Pydantic model:
  src/chronovista/models/tag_operation_log.py
- CanonicalTag DB model:
  src/chronovista/db/models.py (class CanonicalTag)
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import TagOperationLog as TagOperationLogDB
from chronovista.models.tag_operation_log import TagOperationLogCreate
from chronovista.services.tag_management import TagManagementService

# ---------------------------------------------------------------------------
# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_canonical_tag_repo() -> AsyncMock:
    """Provide a mock CanonicalTagRepository with async method stubs."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_tag_alias_repo() -> AsyncMock:
    """Provide a mock TagAliasRepository with async method stubs."""
    return AsyncMock()


@pytest.fixture
def mock_named_entity_repo() -> AsyncMock:
    """Provide a mock NamedEntityRepository with async method stubs."""
    return AsyncMock()


@pytest.fixture
def mock_entity_alias_repo() -> AsyncMock:
    """Provide a mock EntityAliasRepository with async method stubs."""
    return AsyncMock()


@pytest.fixture
def mock_operation_log_repo() -> AsyncMock:
    """Provide a mock TagOperationLogRepository with async method stubs."""
    return AsyncMock()


@pytest.fixture
def service(
    mock_canonical_tag_repo: AsyncMock,
    mock_tag_alias_repo: AsyncMock,
    mock_named_entity_repo: AsyncMock,
    mock_entity_alias_repo: AsyncMock,
    mock_operation_log_repo: AsyncMock,
) -> TagManagementService:
    """
    Provide a ``TagManagementService`` instance wired with all mock repos.

    This is the canonical way to instantiate the service in unit tests.
    The constructor signature is:
        TagManagementService(
            canonical_tag_repo,
            tag_alias_repo,
            named_entity_repo,
            entity_alias_repo,
            operation_log_repo,
        )
    """
    return TagManagementService(
        canonical_tag_repo=mock_canonical_tag_repo,
        tag_alias_repo=mock_tag_alias_repo,
        named_entity_repo=mock_named_entity_repo,
        entity_alias_repo=mock_entity_alias_repo,
        operation_log_repo=mock_operation_log_repo,
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide a mock AsyncSession."""
    return AsyncMock()


# ---------------------------------------------------------------------------
# Helper: build a fake CanonicalTagDB instance
# ---------------------------------------------------------------------------


def _make_canonical_tag(
    *,
    normalized_form: str = "python",
    canonical_form: str = "Python",
    status: str = "active",
    alias_count: int = 3,
    video_count: int = 10,
) -> MagicMock:
    """
    Build a lightweight MagicMock that mimics a ``CanonicalTagDB`` row.

    Only the attributes accessed by the service methods under test are set;
    everything else falls back to MagicMock's default attribute access.
    """
    tag = MagicMock(spec=CanonicalTagDB)
    tag.id = uuid.uuid4()
    tag.normalized_form = normalized_form
    tag.canonical_form = canonical_form
    tag.status = status
    tag.alias_count = alias_count
    tag.video_count = video_count
    return tag


# ===========================================================================
# TestValidateActiveTag
# ===========================================================================


class TestValidateActiveTag:
    """
    Tests for ``TagManagementService._validate_active_tag``.

    The method queries the repository three times at most:
      1. ``get_by_normalized_form(session, normalized_form)``        → status="active" (default)
      2. ``get_by_normalized_form(session, normalized_form, status="merged")``
      3. ``get_by_normalized_form(session, normalized_form, status="deprecated")``

    It returns the active tag on success and raises ``ValueError`` in all
    other cases.
    """

    async def test_validate_active_tag_success(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Happy path: repo returns an active tag on the first call.

        Expected behaviour:
        - ``get_by_normalized_form`` is called exactly once with the
          default status (``"active"``).
        - The returned ``CanonicalTagDB`` object is passed back unchanged.
        - No ``ValueError`` is raised.
        """
        active_tag = _make_canonical_tag(normalized_form="python", status="active")
        mock_canonical_tag_repo.get_by_normalized_form.return_value = active_tag

        result = await service._validate_active_tag(mock_session, "python")

        assert result is active_tag
        # Only the first (active-status) query should have fired
        mock_canonical_tag_repo.get_by_normalized_form.assert_called_once_with(
            mock_session, "python"
        )

    async def test_validate_active_tag_not_found(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Tag not found in any status: all three repo calls return ``None``.

        Expected behaviour:
        - Three ``get_by_normalized_form`` calls are made (active, merged,
          deprecated).
        - ``ValueError("Tag 'x' not found")`` is raised.
        """
        mock_canonical_tag_repo.get_by_normalized_form.return_value = None

        with pytest.raises(ValueError, match="Tag 'nonexistent' not found"):
            await service._validate_active_tag(mock_session, "nonexistent")

        # All three status lookups must have been attempted
        assert mock_canonical_tag_repo.get_by_normalized_form.call_count == 3
        calls = mock_canonical_tag_repo.get_by_normalized_form.call_args_list
        # First call: default (active) — no explicit status keyword
        assert calls[0] == call(mock_session, "nonexistent")
        # Second call: merged
        assert calls[1] == call(mock_session, "nonexistent", status="merged")
        # Third call: deprecated
        assert calls[2] == call(mock_session, "nonexistent", status="deprecated")

    async def test_validate_active_tag_merged(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Tag exists but has ``merged`` status.

        Expected behaviour:
        - First call (active) returns ``None``.
        - Second call (merged) returns a ``CanonicalTagDB`` with status
          ``"merged"``.
        - Third call (deprecated) is never executed.
        - ``ValueError`` is raised with a message that includes the status
          string ``"merged"`` and the normalized form.
        """
        merged_tag = _make_canonical_tag(normalized_form="oldtag", status="merged")
        # Return None for "active" query, merged tag for "merged" query
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            None,         # first call: status="active"
            merged_tag,   # second call: status="merged"
        ]

        with pytest.raises(ValueError) as exc_info:
            await service._validate_active_tag(mock_session, "oldtag")

        error_message = str(exc_info.value)
        assert "oldtag" in error_message
        assert "merged" in error_message
        assert "active" in error_message

        # Only two calls should have been made (active + merged)
        assert mock_canonical_tag_repo.get_by_normalized_form.call_count == 2

    async def test_validate_active_tag_deprecated(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Tag exists but has ``deprecated`` status.

        Expected behaviour:
        - First call (active) returns ``None``.
        - Second call (merged) returns ``None``.
        - Third call (deprecated) returns a ``CanonicalTagDB`` with status
          ``"deprecated"``.
        - ``ValueError`` is raised with a message that includes both the
          status string ``"deprecated"`` and the normalized form.
        """
        deprecated_tag = _make_canonical_tag(
            normalized_form="oldertag", status="deprecated"
        )
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            None,           # first call: status="active"
            None,           # second call: status="merged"
            deprecated_tag, # third call: status="deprecated"
        ]

        with pytest.raises(ValueError) as exc_info:
            await service._validate_active_tag(mock_session, "oldertag")

        error_message = str(exc_info.value)
        assert "oldertag" in error_message
        assert "deprecated" in error_message
        assert "active" in error_message

        # All three status lookups must have been attempted
        assert mock_canonical_tag_repo.get_by_normalized_form.call_count == 3

    async def test_validate_active_tag_error_message_contains_status(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The ``ValueError`` message for a non-active tag must quote both
        the actual status and the string ``'active'`` so callers can display
        a useful diagnostic to the operator.
        """
        merged_tag = _make_canonical_tag(normalized_form="mytag", status="merged")
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            None,
            merged_tag,
        ]

        with pytest.raises(ValueError) as exc_info:
            await service._validate_active_tag(mock_session, "mytag")

        # Verify the precise phrasing matches the implementation
        error_message = str(exc_info.value)
        assert "mytag" in error_message
        assert "'merged'" in error_message
        assert "'active'" in error_message

    async def test_validate_active_tag_returns_correct_object(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The method must return the exact object returned by the repository,
        not a copy or re-constructed instance.
        """
        sentinel_tag = _make_canonical_tag(
            normalized_form="java", canonical_form="Java", status="active"
        )
        mock_canonical_tag_repo.get_by_normalized_form.return_value = sentinel_tag

        result = await service._validate_active_tag(mock_session, "java")

        assert result is sentinel_tag, (
            "Expected the exact CanonicalTagDB object returned by the repo"
        )

    async def test_validate_active_tag_passes_session_to_repo(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The session passed to ``_validate_active_tag`` must be forwarded
        to the repository without mutation.
        """
        active_tag = _make_canonical_tag(status="active")
        mock_canonical_tag_repo.get_by_normalized_form.return_value = active_tag

        await service._validate_active_tag(mock_session, "sometag")

        # Verify the exact session object was passed
        first_call_args = mock_canonical_tag_repo.get_by_normalized_form.call_args_list[0]
        assert first_call_args.args[0] is mock_session


# ===========================================================================
# TestRecalculateCounts
# ===========================================================================


class TestRecalculateCounts:
    """
    Tests for ``TagManagementService._recalculate_counts``.

    The method issues three ``session.execute`` calls in order:
      1. COUNT query on ``tag_aliases`` filtered by ``canonical_tag_id``.
      2. COUNT DISTINCT query on ``video_tags`` joined to ``tag_aliases``.
      3. UPDATE on ``canonical_tags`` setting the two new counts.

    It returns ``(alias_count, video_count)`` as a tuple of ints.
    """

    def _make_scalar_result(self, value: int) -> MagicMock:
        """Build a mock SQLAlchemy result whose ``scalar_one()`` returns *value*."""
        result = MagicMock()
        result.scalar_one.return_value = value
        return result

    async def test_recalculate_counts_returns_correct_tuple(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        Happy path: session.execute returns alias count then video count.

        Expected behaviour:
        - First execute call → alias_count scalar.
        - Second execute call → video_count scalar.
        - Third execute call → UPDATE statement (result ignored).
        - The method returns ``(alias_count, video_count)`` exactly.
        """
        canonical_tag_id = uuid.uuid4()

        alias_result = self._make_scalar_result(7)
        video_result = self._make_scalar_result(42)
        update_result = MagicMock()  # UPDATE return value is unused

        mock_session.execute = AsyncMock(
            side_effect=[alias_result, video_result, update_result]
        )

        result = await service._recalculate_counts(mock_session, canonical_tag_id)

        assert result == (7, 42), (
            f"Expected (7, 42) but got {result!r}"
        )

    async def test_recalculate_counts_calls_execute_three_times(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        ``session.execute`` must be called exactly three times: two SELECTs
        plus one UPDATE.
        """
        canonical_tag_id = uuid.uuid4()

        mock_session.execute = AsyncMock(
            side_effect=[
                self._make_scalar_result(5),
                self._make_scalar_result(20),
                MagicMock(),
            ]
        )

        await service._recalculate_counts(mock_session, canonical_tag_id)

        assert mock_session.execute.call_count == 3, (
            "Expected exactly 3 execute calls (2 SELECTs + 1 UPDATE)"
        )

    async def test_recalculate_counts_zero_aliases(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        Edge case: tag has zero aliases and zero video associations.

        The method must propagate zeros faithfully — the DB CHECK constraint
        (alias_count >= 1) is enforced at the DB layer, not here.
        """
        canonical_tag_id = uuid.uuid4()

        mock_session.execute = AsyncMock(
            side_effect=[
                self._make_scalar_result(0),
                self._make_scalar_result(0),
                MagicMock(),
            ]
        )

        alias_count, video_count = await service._recalculate_counts(
            mock_session, canonical_tag_id
        )

        assert alias_count == 0
        assert video_count == 0

    async def test_recalculate_counts_large_counts(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        Large integer counts are returned without truncation or overflow.
        """
        canonical_tag_id = uuid.uuid4()
        large_alias = 99_999
        large_video = 500_569

        mock_session.execute = AsyncMock(
            side_effect=[
                self._make_scalar_result(large_alias),
                self._make_scalar_result(large_video),
                MagicMock(),
            ]
        )

        alias_count, video_count = await service._recalculate_counts(
            mock_session, canonical_tag_id
        )

        assert alias_count == large_alias
        assert video_count == large_video

    async def test_recalculate_counts_return_type_is_tuple_of_ints(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        The return value must be a two-element tuple of plain Python ``int``
        values, matching the declared return type ``tuple[int, int]``.
        """
        canonical_tag_id = uuid.uuid4()

        mock_session.execute = AsyncMock(
            side_effect=[
                self._make_scalar_result(3),
                self._make_scalar_result(15),
                MagicMock(),
            ]
        )

        result = await service._recalculate_counts(mock_session, canonical_tag_id)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)


# ===========================================================================
# TestLogOperation
# ===========================================================================


class TestLogOperation:
    """
    Tests for ``TagManagementService._log_operation``.

    The method:
    1. Constructs a ``TagOperationLogCreate`` Pydantic model from the keyword
       arguments.
    2. Delegates persistence to ``self._operation_log_repo.create(session, obj_in=...)``.
    3. Returns the ``id`` attribute of the persisted ``TagOperationLogDB`` object.
    """

    def _make_log_entry(self, entry_id: uuid.UUID | None = None) -> MagicMock:
        """Build a mock ``TagOperationLogDB`` with the given ``id``."""
        entry = MagicMock(spec=TagOperationLogDB)
        entry.id = entry_id or uuid.uuid4()
        return entry

    async def test_log_operation_creates_entry_and_returns_id(
        self,
        service: TagManagementService,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Happy path: ``_log_operation`` delegates to the repo and returns the
        UUID of the persisted log entry.

        Verifies:
        - ``operation_log_repo.create`` is called exactly once.
        - The returned value is the ``id`` of the created entry (a ``uuid.UUID``).
        """
        expected_id = uuid.uuid4()
        log_entry = self._make_log_entry(expected_id)
        mock_operation_log_repo.create.return_value = log_entry

        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        alias_id = uuid.uuid4()

        result = await service._log_operation(
            mock_session,
            operation_type="merge",
            source_ids=[source_id],
            target_id=target_id,
            alias_ids=[alias_id],
            reason="Consolidating duplicate tags",
            rollback_data={"snapshot": "data"},
        )

        assert result == expected_id
        assert isinstance(result, uuid.UUID)
        mock_operation_log_repo.create.assert_called_once()

    async def test_log_operation_passes_correct_pydantic_model(
        self,
        service: TagManagementService,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The ``obj_in`` argument to ``repo.create`` must be a
        ``TagOperationLogCreate`` instance whose fields match the arguments
        passed to ``_log_operation``.

        Field mapping:
        - ``operation_type``       → operation_type
        - ``source_canonical_ids`` → source_ids
        - ``target_canonical_id``  → target_id
        - ``affected_alias_ids``   → alias_ids
        - ``reason``               → reason
        - ``rollback_data``        → rollback_data
        - ``performed_by``         → hard-coded to ``"cli"``
        """
        log_entry = self._make_log_entry()
        mock_operation_log_repo.create.return_value = log_entry

        source_id_1 = uuid.uuid4()
        source_id_2 = uuid.uuid4()
        target_id = uuid.uuid4()
        alias_id = uuid.uuid4()
        rollback: dict[str, Any] = {"previous_canonical_ids": [str(source_id_1)]}

        await service._log_operation(
            mock_session,
            operation_type="merge",
            source_ids=[source_id_1, source_id_2],
            target_id=target_id,
            alias_ids=[alias_id],
            reason="Test merge reason",
            rollback_data=rollback,
        )

        mock_operation_log_repo.create.assert_called_once()
        call_kwargs = mock_operation_log_repo.create.call_args

        # Verify the session was passed as the first positional argument
        assert call_kwargs.args[0] is mock_session

        # Extract the obj_in keyword argument
        obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]
        assert isinstance(obj_in, TagOperationLogCreate), (
            f"Expected TagOperationLogCreate, got {type(obj_in).__name__}"
        )

        # Verify field values
        assert obj_in.operation_type == "merge"
        assert obj_in.source_canonical_ids == [str(source_id_1), str(source_id_2)]
        assert obj_in.target_canonical_id == target_id
        assert obj_in.affected_alias_ids == [str(alias_id)]
        assert obj_in.reason == "Test merge reason"
        assert obj_in.rollback_data == rollback
        assert obj_in.performed_by == "cli"

    async def test_log_operation_with_none_target_id(
        self,
        service: TagManagementService,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Operations without a target (e.g. ``create``, ``deprecate``) pass
        ``target_id=None``.  The Pydantic model's ``target_canonical_id``
        field must be ``None`` in that case.
        """
        log_entry = self._make_log_entry()
        mock_operation_log_repo.create.return_value = log_entry

        await service._log_operation(
            mock_session,
            operation_type="create",
            source_ids=[],
            target_id=None,
            alias_ids=[],
            reason=None,
            rollback_data={},
        )

        call_kwargs = mock_operation_log_repo.create.call_args
        obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]

        assert obj_in.target_canonical_id is None
        assert obj_in.reason is None

    async def test_log_operation_with_empty_lists(
        self,
        service: TagManagementService,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Empty ``source_ids`` and ``alias_ids`` are valid inputs for operations
        like ``rename`` that don't involve alias movement.
        """
        log_entry = self._make_log_entry()
        mock_operation_log_repo.create.return_value = log_entry

        result = await service._log_operation(
            mock_session,
            operation_type="rename",
            source_ids=[],
            target_id=None,
            alias_ids=[],
            reason="Rename to match title case",
            rollback_data={"old_form": "python3", "new_form": "Python3"},
        )

        call_kwargs = mock_operation_log_repo.create.call_args
        obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]

        assert obj_in.source_canonical_ids == []
        assert obj_in.affected_alias_ids == []
        assert isinstance(result, uuid.UUID)

    async def test_log_operation_invalid_operation_type_raises(
        self,
        service: TagManagementService,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Passing an operation_type not in the allowed set
        ``{"merge", "split", "rename", "delete", "create"}`` must raise a
        ``ValueError`` from the ``TagOperationLogCreate`` Pydantic validator
        before the repository is called.
        """
        with pytest.raises(ValueError):
            await service._log_operation(
                mock_session,
                operation_type="invalid_type",
                source_ids=[],
                target_id=None,
                alias_ids=[],
                reason=None,
                rollback_data={},
            )

        # Repo must never be called if Pydantic validation fails
        mock_operation_log_repo.create.assert_not_called()

    async def test_log_operation_performed_by_is_always_cli(
        self,
        service: TagManagementService,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The ``performed_by`` field must always be ``"cli"`` regardless of
        the caller-supplied arguments — it is hard-coded in the service.
        """
        log_entry = self._make_log_entry()
        mock_operation_log_repo.create.return_value = log_entry

        for op_type in ("merge", "split", "rename", "delete", "create"):
            mock_operation_log_repo.create.reset_mock()

            await service._log_operation(
                mock_session,
                operation_type=op_type,
                source_ids=[],
                target_id=None,
                alias_ids=[],
                reason=None,
                rollback_data={},
            )

            call_kwargs = mock_operation_log_repo.create.call_args
            obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]
            assert obj_in.performed_by == "cli", (
                f"Expected performed_by='cli' for operation_type={op_type!r}, "
                f"got {obj_in.performed_by!r}"
            )

    async def test_log_operation_all_valid_operation_types(
        self,
        service: TagManagementService,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        All five allowed operation types must be accepted without error.

        The allowed types are defined in ``tag_operation_log.ALLOWED_OPERATION_TYPES``:
        ``{"merge", "split", "rename", "delete", "create"}``.
        """
        log_entry = self._make_log_entry()
        mock_operation_log_repo.create.return_value = log_entry

        allowed_types = {"merge", "split", "rename", "delete", "create"}
        for op_type in sorted(allowed_types):
            mock_operation_log_repo.create.reset_mock()

            result = await service._log_operation(
                mock_session,
                operation_type=op_type,
                source_ids=[],
                target_id=None,
                alias_ids=[],
                reason=None,
                rollback_data={},
            )

            assert isinstance(result, uuid.UUID), (
                f"Expected UUID return for operation_type={op_type!r}"
            )

    async def test_log_operation_rollback_data_preserved(
        self,
        service: TagManagementService,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Arbitrary rollback_data dicts (including nested structures and lists)
        must be forwarded to the Pydantic model without modification.
        """
        log_entry = self._make_log_entry()
        mock_operation_log_repo.create.return_value = log_entry

        complex_rollback: dict[str, Any] = {
            "previous_aliases": [
                {"id": str(uuid.uuid4()), "raw_form": "Python"},
                {"id": str(uuid.uuid4()), "raw_form": "python"},
            ],
            "previous_status": "active",
            "meta": {"version": 1, "source": "cli"},
        }

        await service._log_operation(
            mock_session,
            operation_type="merge",
            source_ids=[uuid.uuid4()],
            target_id=uuid.uuid4(),
            alias_ids=[uuid.uuid4()],
            reason="Complex rollback test",
            rollback_data=complex_rollback,
        )

        call_kwargs = mock_operation_log_repo.create.call_args
        obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.rollback_data == complex_rollback


# ===========================================================================
# Helpers for advanced test classes
# ===========================================================================


def _make_tag_alias(
    *,
    raw_form: str = "Python",
    normalized_form: str = "python",
    canonical_tag_id: uuid.UUID | None = None,
    occurrence_count: int = 5,
) -> MagicMock:
    """
    Build a lightweight MagicMock that mimics a ``TagAliasDB`` row.

    Only the attributes accessed by service methods under test are set.
    """
    from chronovista.db.models import TagAlias as TagAliasDB

    alias = MagicMock(spec=TagAliasDB)
    alias.id = uuid.uuid4()
    alias.raw_form = raw_form
    alias.normalized_form = normalized_form
    alias.canonical_tag_id = canonical_tag_id or uuid.uuid4()
    alias.occurrence_count = occurrence_count
    return alias


def _make_operation_log(
    *,
    operation_type: str = "merge",
    rolled_back: bool = False,
    rollback_data: dict[str, Any] | None = None,
    source_canonical_ids: list[str] | None = None,
    target_canonical_id: uuid.UUID | None = None,
) -> MagicMock:
    """
    Build a lightweight MagicMock that mimics a ``TagOperationLogDB`` row.
    """
    from chronovista.db.models import TagOperationLog as TagOperationLogDB

    log = MagicMock(spec=TagOperationLogDB)
    log.id = uuid.uuid4()
    log.operation_type = operation_type
    log.rolled_back = rolled_back
    log.rollback_data = rollback_data or {}
    log.source_canonical_ids = source_canonical_ids or []
    log.target_canonical_id = target_canonical_id
    log.rolled_back_at = None
    return log


def _make_named_entity(
    *,
    normalized_form: str = "python",
    entity_type: str = "technical_term",
    discovery_method: str = "user_created",
) -> MagicMock:
    """
    Build a lightweight MagicMock that mimics a ``NamedEntityDB`` row.
    """
    from chronovista.db.models import NamedEntity as NamedEntityDB

    entity = MagicMock(spec=NamedEntityDB)
    entity.id = uuid.uuid4()
    entity.canonical_name_normalized = normalized_form
    entity.entity_type = entity_type
    entity.discovery_method = discovery_method
    return entity


def _make_entity_alias(*, entity_id: uuid.UUID | None = None) -> MagicMock:
    """Build a lightweight MagicMock that mimics an ``EntityAliasDB`` row."""
    from chronovista.db.models import EntityAlias as EntityAliasDB

    ea = MagicMock(spec=EntityAliasDB)
    ea.id = uuid.uuid4()
    ea.entity_id = entity_id or uuid.uuid4()
    return ea


def _make_scalar_result(value: Any) -> MagicMock:
    """Build a mock SQLAlchemy scalar result returning *value* from scalar_one()."""
    r = MagicMock()
    r.scalar_one.return_value = value
    return r


def _make_scalars_result(items: list[Any]) -> MagicMock:
    """Build a mock result whose .scalars().all() returns *items*."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars_mock
    return result


# ===========================================================================
# TestMerge
# ===========================================================================


class TestMerge:
    """
    Tests for ``TagManagementService.merge``.

    Covers:
    - Single-source merge happy path
    - Multi-source merge
    - Self-merge rejection
    - Already-merged (non-active) source rejection
    - Non-existent target rejection
    - Non-active target rejection
    - FR-005a entity hint generation
    - rollback_data structure
    """

    def _setup_recalculate(self, mock_session: AsyncMock) -> None:
        """Wire mock_session.execute to return alias=5, video=10, UPDATE=None."""
        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([]),  # source alias SELECT (merge reassign)
                _make_scalar_result(5),    # recalculate alias count
                _make_scalar_result(10),   # recalculate video count
                MagicMock(),               # UPDATE
            ]
        )

    async def test_single_source_merge_returns_merge_result(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Happy path: single source merges into target.

        Verifies that MergeResult fields are populated correctly: source_tags,
        target_tag, aliases_moved, new_alias_count, new_video_count,
        operation_id, entity_hint (None when no entity type on sources).
        """
        from chronovista.services.tag_management import MergeResult

        source_tag = _make_canonical_tag(
            normalized_form="python3",
            canonical_form="Python3",
            status="active",
            alias_count=2,
            video_count=5,
        )
        source_tag.entity_type = None
        source_tag.entity_id = None

        target_tag = _make_canonical_tag(
            normalized_form="python",
            canonical_form="Python",
            status="active",
            alias_count=3,
            video_count=10,
        )
        target_tag.entity_type = None
        target_tag.entity_id = None

        # First get_by_normalized_form call = target validation (active)
        # Second call = source validation (active)
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            target_tag,   # target validate_active_tag
            source_tag,   # source validate_active_tag
        ]

        source_alias = _make_tag_alias(
            raw_form="python3",
            canonical_tag_id=source_tag.id,
        )
        # SELECT aliases for source tag
        alias_select_result = _make_scalars_result([source_alias])

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="merge")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        # recalculate: alias_count, video_count, UPDATE
        mock_session.execute = AsyncMock(
            side_effect=[
                alias_select_result,         # SELECT aliases for source
                MagicMock(),                 # UPDATE aliases to target (bulk UPDATE)
                _make_scalar_result(4),      # alias count after merge (recalculate)
                _make_scalar_result(12),     # video count after merge (recalculate)
                MagicMock(),                 # UPDATE canonical_tags counts
            ]
        )

        result = await service.merge(
            mock_session,
            source_normalized_forms=["python3"],
            target_normalized_form="python",
            reason="Consolidating Python variants",
        )

        assert isinstance(result, MergeResult)
        assert result.source_tags == ["python3"]
        assert result.target_tag == "python"
        assert result.aliases_moved == 1
        assert result.new_alias_count == 4
        assert result.new_video_count == 12
        assert result.operation_id == op_id
        assert result.entity_hint is None

    async def test_multi_source_merge_accumulates_aliases(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Multi-source merge: aliases from both sources accumulate into target.

        Verifies aliases_moved equals the sum of all source aliases moved.
        """
        from chronovista.services.tag_management import MergeResult

        source1 = _make_canonical_tag(normalized_form="ml", canonical_form="ML", status="active")
        source1.entity_type = None
        source1.entity_id = None
        source2 = _make_canonical_tag(
            normalized_form="machine learning", canonical_form="Machine Learning", status="active"
        )
        source2.entity_type = None
        source2.entity_id = None
        target = _make_canonical_tag(
            normalized_form="machine_learning", canonical_form="Machine_Learning", status="active"
        )
        target.entity_type = None
        target.entity_id = None

        # validate_active_tag calls: target, source1, source2
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            target,    # target
            source1,   # source1
            source2,   # source2
        ]

        alias1 = _make_tag_alias(raw_form="ML", canonical_tag_id=source1.id)
        alias2a = _make_tag_alias(raw_form="Machine Learning", canonical_tag_id=source2.id)
        alias2b = _make_tag_alias(raw_form="machine learning", canonical_tag_id=source2.id)

        op_id = uuid.uuid4()
        log_entry = _make_operation_log()
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias1]),         # SELECT aliases for source1
                MagicMock(),                             # UPDATE aliases for source1
                _make_scalars_result([alias2a, alias2b]),  # SELECT aliases for source2
                MagicMock(),                             # UPDATE aliases for source2
                _make_scalar_result(6),                  # recalculate alias count
                _make_scalar_result(15),                 # recalculate video count
                MagicMock(),                             # UPDATE canonical_tags
            ]
        )

        result = await service.merge(
            mock_session,
            source_normalized_forms=["ml", "machine learning"],
            target_normalized_form="machine_learning",
        )

        assert isinstance(result, MergeResult)
        assert result.aliases_moved == 3  # 1 + 2
        assert set(result.source_tags) == {"ml", "machine learning"}

    async def test_self_merge_raises_value_error(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Self-merge (source == target) must raise ValueError immediately.

        The implementation checks self-merge before any alias queries.
        """
        target = _make_canonical_tag(normalized_form="python", status="active")
        target.entity_type = None
        mock_canonical_tag_repo.get_by_normalized_form.return_value = target

        with pytest.raises(ValueError, match="Cannot merge tag 'python' into itself"):
            await service.merge(
                mock_session,
                source_normalized_forms=["python"],
                target_normalized_form="python",
            )

    async def test_non_active_source_raises_value_error(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Merging a merged (non-active) source must raise ValueError.

        _validate_active_tag is called for each source; a merged source
        raises ValueError with status information.
        """
        target = _make_canonical_tag(normalized_form="python", status="active")
        target.entity_type = None
        merged_source = _make_canonical_tag(normalized_form="python3", status="merged")

        # target validation succeeds, then source status check reveals merged
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            target,          # target validate_active_tag -> active
            None,            # source validate_active_tag -> not active (first call)
            merged_source,   # source status check -> merged
        ]

        with pytest.raises(ValueError, match="python3"):
            await service.merge(
                mock_session,
                source_normalized_forms=["python3"],
                target_normalized_form="python",
            )

    async def test_non_existent_target_raises_value_error(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Non-existent target must raise ValueError('Tag ... not found').
        """
        # All three status queries return None = tag does not exist
        mock_canonical_tag_repo.get_by_normalized_form.return_value = None

        with pytest.raises(ValueError, match="Tag 'nonexistent' not found"):
            await service.merge(
                mock_session,
                source_normalized_forms=["python3"],
                target_normalized_form="nonexistent",
            )

    async def test_non_active_target_raises_value_error(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Deprecated target must raise ValueError with status info.
        """
        deprecated_target = _make_canonical_tag(
            normalized_form="old_python", status="deprecated"
        )
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            None,              # active query -> None
            None,              # merged query -> None
            deprecated_target, # deprecated query -> found
        ]

        with pytest.raises(ValueError, match="deprecated"):
            await service.merge(
                mock_session,
                source_normalized_forms=["python3"],
                target_normalized_form="old_python",
            )

    async def test_entity_hint_generated_when_source_has_entity_type(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        FR-005a: If target has no entity_type but source does, entity_hint
        must be populated in the result encouraging classification.
        """
        from chronovista.services.tag_management import MergeResult

        source = _make_canonical_tag(
            normalized_form="python3", canonical_form="Python3", status="active"
        )
        source.entity_type = "technical_term"
        source.entity_id = None

        target = _make_canonical_tag(
            normalized_form="python", canonical_form="Python", status="active"
        )
        target.entity_type = None
        target.entity_id = None

        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [target, source]

        alias = _make_tag_alias(raw_form="python3", canonical_tag_id=source.id)
        op_id = uuid.uuid4()
        log_entry = _make_operation_log()
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias]),  # SELECT aliases for source
                MagicMock(),                     # UPDATE aliases to target
                _make_scalar_result(4),          # recalculate alias_count
                _make_scalar_result(12),         # recalculate video_count
                MagicMock(),                     # UPDATE canonical_tags counts
            ]
        )

        result = await service.merge(
            mock_session,
            source_normalized_forms=["python3"],
            target_normalized_form="python",
        )

        assert isinstance(result, MergeResult)
        assert result.entity_hint is not None
        assert "technical_term" in result.entity_hint
        assert "python" in result.entity_hint

    async def test_no_entity_hint_when_target_already_classified(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        No entity_hint when the target already has an entity_type, even
        if sources also have entity types.
        """
        from chronovista.services.tag_management import MergeResult

        source = _make_canonical_tag(
            normalized_form="python3", canonical_form="Python3", status="active"
        )
        source.entity_type = "technical_term"
        source.entity_id = None

        target = _make_canonical_tag(
            normalized_form="python", canonical_form="Python", status="active"
        )
        target.entity_type = "technical_term"  # already classified
        target.entity_id = None

        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [target, source]

        alias = _make_tag_alias(raw_form="python3", canonical_tag_id=source.id)
        op_id = uuid.uuid4()
        log_entry = _make_operation_log()
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias]),  # SELECT aliases for source
                MagicMock(),                     # UPDATE aliases to target
                _make_scalar_result(4),          # recalculate alias_count
                _make_scalar_result(10),         # recalculate video_count
                MagicMock(),                     # UPDATE canonical_tags counts
            ]
        )

        result = await service.merge(
            mock_session,
            source_normalized_forms=["python3"],
            target_normalized_form="python",
        )

        assert isinstance(result, MergeResult)
        assert result.entity_hint is None

    async def test_merge_rollback_data_structure(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The rollback_data passed to _log_operation must contain:
        - ``sources``: list with ``canonical_tag_id``, ``previous_status``,
          ``previous_alias_count``, ``previous_video_count``,
          ``previous_entity_type``, ``previous_entity_id``, ``alias_ids``
        - ``target``: dict with ``canonical_tag_id``, ``previous_alias_count``,
          ``previous_video_count``
        """
        source = _make_canonical_tag(
            normalized_form="py3",
            canonical_form="Py3",
            status="active",
            alias_count=2,
            video_count=5,
        )
        source.entity_type = None
        source.entity_id = None

        target = _make_canonical_tag(
            normalized_form="python",
            canonical_form="Python",
            status="active",
            alias_count=3,
            video_count=10,
        )
        target.entity_type = None
        target.entity_id = None

        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [target, source]

        alias = _make_tag_alias(raw_form="Py3", canonical_tag_id=source.id)
        op_id = uuid.uuid4()
        log_entry = _make_operation_log()
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias]),  # SELECT aliases for source
                MagicMock(),                     # UPDATE aliases to target
                _make_scalar_result(4),          # recalculate alias_count
                _make_scalar_result(12),         # recalculate video_count
                MagicMock(),                     # UPDATE canonical_tags counts
            ]
        )

        await service.merge(
            mock_session,
            source_normalized_forms=["py3"],
            target_normalized_form="python",
            reason="Test rollback structure",
        )

        # Inspect what rollback_data was passed to operation log repo
        call_kwargs = mock_operation_log_repo.create.call_args
        from chronovista.models.tag_operation_log import TagOperationLogCreate

        obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]
        rollback = obj_in.rollback_data

        assert "sources" in rollback
        assert "target" in rollback
        assert len(rollback["sources"]) == 1

        src_data = rollback["sources"][0]
        assert "canonical_tag_id" in src_data
        assert "previous_status" in src_data
        assert "previous_alias_count" in src_data
        assert "previous_video_count" in src_data
        assert "previous_entity_type" in src_data
        assert "previous_entity_id" in src_data
        assert "alias_ids" in src_data
        assert src_data["previous_status"] == "active"
        assert src_data["previous_alias_count"] == 2
        assert src_data["previous_video_count"] == 5

        tgt_data = rollback["target"]
        assert "canonical_tag_id" in tgt_data
        assert "previous_alias_count" in tgt_data
        assert "previous_video_count" in tgt_data
        assert tgt_data["previous_alias_count"] == 3
        assert tgt_data["previous_video_count"] == 10

    async def test_merge_marks_source_as_merged(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        After a successful merge, source.status must be set to 'merged'
        and source.merged_into_id must be set to target.id.
        """
        from chronovista.models.enums import TagStatus

        source = _make_canonical_tag(normalized_form="py3", status="active")
        source.entity_type = None
        source.entity_id = None
        target = _make_canonical_tag(normalized_form="python", status="active")
        target.entity_type = None
        target.entity_id = None

        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [target, source]

        alias = _make_tag_alias(raw_form="Py3", canonical_tag_id=source.id)
        op_id = uuid.uuid4()
        log_entry = _make_operation_log()
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias]),  # SELECT aliases for source
                MagicMock(),                     # UPDATE aliases to target
                _make_scalar_result(4),          # recalculate alias_count
                _make_scalar_result(12),         # recalculate video_count
                MagicMock(),                     # UPDATE canonical_tags counts
            ]
        )

        await service.merge(
            mock_session,
            source_normalized_forms=["py3"],
            target_normalized_form="python",
        )

        assert source.status == TagStatus.MERGED.value
        assert source.merged_into_id == target.id


# ===========================================================================
# TestSplit
# ===========================================================================


class TestSplit:
    """
    Tests for ``TagManagementService.split``.

    Covers:
    - Basic split happy path
    - Canonical form selection from moved aliases
    - Normalized form computation
    - All-aliases-removed rejection
    - Wrong-alias rejection (aliases not on source tag)
    - Normalized form collision with active tag
    - Normalized form collision with deprecated tag
    - rollback_data structure
    """

    def _patch_normalization(
        self,
        monkeypatch: Any,
        canonical_form: str = "NewTag",
        normalized_form: str = "newtag",
    ) -> None:
        """
        Patch TagNormalizationService so tests are deterministic.
        The split() method imports it at call time (lazy import).
        """
        mock_norm = MagicMock()
        mock_norm.select_canonical_form.return_value = canonical_form
        mock_norm.normalize.return_value = normalized_form

        import chronovista.services.tag_normalization as _tn_module

        monkeypatch.setattr(
            _tn_module, "TagNormalizationService", lambda: mock_norm
        )

    async def test_basic_split_returns_split_result(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
        monkeypatch: Any,
    ) -> None:
        """
        Happy path: split two aliases from a three-alias source tag.

        Verifies SplitResult fields: original_tag, new_tag, new_canonical_form,
        aliases_moved, original_alias_count, new_alias_count, operation_id.
        """
        from chronovista.services.tag_management import SplitResult

        self._patch_normalization(
            monkeypatch,
            canonical_form="ML Python",
            normalized_form="ml python",
        )

        source_tag = _make_canonical_tag(
            normalized_form="python",
            canonical_form="Python",
            status="active",
            alias_count=3,
            video_count=8,
        )
        source_tag.entity_type = None

        alias_a = _make_tag_alias(raw_form="ML Python", canonical_tag_id=source_tag.id)
        alias_b = _make_tag_alias(raw_form="ml-python", canonical_tag_id=source_tag.id)
        alias_c = _make_tag_alias(raw_form="Python", canonical_tag_id=source_tag.id)

        new_tag = _make_canonical_tag(
            normalized_form="ml python",
            canonical_form="ML Python",
            status="active",
            alias_count=2,
            video_count=3,
        )

        # validate_active_tag -> source
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            source_tag,  # validate source
            None,        # collision check active
            None,        # collision check deprecated
        ]
        mock_canonical_tag_repo.create.return_value = new_tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="split")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias_a, alias_b, alias_c]),  # all aliases
                MagicMock(),   # UPDATE aliases (reassign to new tag)
                _make_scalar_result(1),   # orig recalculate alias_count
                _make_scalar_result(5),   # orig recalculate video_count
                MagicMock(),              # orig UPDATE
                _make_scalar_result(2),   # new recalculate alias_count
                _make_scalar_result(3),   # new recalculate video_count
                MagicMock(),              # new UPDATE
            ]
        )

        result = await service.split(
            mock_session,
            normalized_form="python",
            alias_raw_forms=["ML Python", "ml-python"],
            reason="Separate ML Python variant",
        )

        assert isinstance(result, SplitResult)
        assert result.original_tag == "python"
        assert result.new_tag == "ml python"
        assert result.new_canonical_form == "ML Python"
        assert result.aliases_moved == 2
        assert result.original_alias_count == 1
        assert result.original_video_count == 5
        assert result.new_alias_count == 2
        assert result.new_video_count == 3
        assert result.operation_id == op_id

    async def test_split_all_aliases_removed_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
        monkeypatch: Any,
    ) -> None:
        """
        Attempting to move all aliases must raise ValueError.

        At least one alias must remain on the original tag.
        """
        self._patch_normalization(monkeypatch)

        source = _make_canonical_tag(normalized_form="python", status="active")
        mock_canonical_tag_repo.get_by_normalized_form.return_value = source

        alias_a = _make_tag_alias(raw_form="Python", canonical_tag_id=source.id)
        alias_b = _make_tag_alias(raw_form="python", canonical_tag_id=source.id)

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias_a, alias_b]),  # all aliases
            ]
        )

        with pytest.raises(ValueError, match="Cannot split all aliases"):
            await service.split(
                mock_session,
                normalized_form="python",
                alias_raw_forms=["Python", "python"],
            )

    async def test_split_wrong_alias_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
        monkeypatch: Any,
    ) -> None:
        """
        Specifying an alias that does not belong to the source tag raises
        ValueError with the invalid alias names listed (all-or-nothing FR-010).
        """
        self._patch_normalization(monkeypatch)

        source = _make_canonical_tag(normalized_form="python", status="active")
        mock_canonical_tag_repo.get_by_normalized_form.return_value = source

        alias_a = _make_tag_alias(raw_form="Python", canonical_tag_id=source.id)
        # Note: "Py3" is NOT in source aliases

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias_a]),  # only Python alias
            ]
        )

        with pytest.raises(ValueError, match="Py3"):
            await service.split(
                mock_session,
                normalized_form="python",
                alias_raw_forms=["Py3"],
            )

    async def test_split_collision_with_active_tag_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
        monkeypatch: Any,
    ) -> None:
        """
        If the computed normalized form of the new tag collides with an
        existing active canonical tag, ValueError must be raised.
        """
        self._patch_normalization(
            monkeypatch,
            canonical_form="ML",
            normalized_form="ml",
        )

        source = _make_canonical_tag(normalized_form="python", status="active")
        existing_active = _make_canonical_tag(normalized_form="ml", status="active")

        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            source,          # validate source tag
            existing_active, # collision check: active tag with same normalized form
        ]

        alias_a = _make_tag_alias(raw_form="ML", canonical_tag_id=source.id)
        alias_b = _make_tag_alias(raw_form="Python", canonical_tag_id=source.id)

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias_a, alias_b]),
            ]
        )

        with pytest.raises(ValueError, match="already exists as an active canonical tag"):
            await service.split(
                mock_session,
                normalized_form="python",
                alias_raw_forms=["ML"],
            )

    async def test_split_collision_with_deprecated_tag_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
        monkeypatch: Any,
    ) -> None:
        """
        Collision with a deprecated tag must also raise ValueError (FR-010).
        """
        self._patch_normalization(
            monkeypatch,
            canonical_form="OldML",
            normalized_form="oldml",
        )

        source = _make_canonical_tag(normalized_form="python", status="active")
        deprecated_tag = _make_canonical_tag(normalized_form="oldml", status="deprecated")

        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            source,         # validate source
            None,           # collision check: no active tag
            deprecated_tag, # collision check: deprecated tag found
        ]

        alias_a = _make_tag_alias(raw_form="OldML", canonical_tag_id=source.id)
        alias_b = _make_tag_alias(raw_form="Python", canonical_tag_id=source.id)

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias_a, alias_b]),
            ]
        )

        with pytest.raises(ValueError, match="deprecated canonical tag"):
            await service.split(
                mock_session,
                normalized_form="python",
                alias_raw_forms=["OldML"],
            )

    async def test_split_rollback_data_structure(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
        monkeypatch: Any,
    ) -> None:
        """
        The rollback_data passed to _log_operation must contain:
        - ``original_canonical_id``
        - ``created_canonical_id``
        - ``moved_alias_ids``
        - ``previous_counts`` with ``original_alias_count`` and
          ``original_video_count``
        """
        self._patch_normalization(monkeypatch, canonical_form="PY3", normalized_form="py3")

        source = _make_canonical_tag(
            normalized_form="python",
            canonical_form="Python",
            status="active",
            alias_count=3,
            video_count=8,
        )
        new_tag = _make_canonical_tag(
            normalized_form="py3",
            canonical_form="PY3",
            status="active",
        )

        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            source, None, None
        ]
        mock_canonical_tag_repo.create.return_value = new_tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="split")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        alias_a = _make_tag_alias(raw_form="PY3", canonical_tag_id=source.id)
        alias_b = _make_tag_alias(raw_form="Python", canonical_tag_id=source.id)

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([alias_a, alias_b]),
                MagicMock(),
                _make_scalar_result(1),
                _make_scalar_result(4),
                MagicMock(),
                _make_scalar_result(1),
                _make_scalar_result(3),
                MagicMock(),
            ]
        )

        await service.split(
            mock_session,
            normalized_form="python",
            alias_raw_forms=["PY3"],
        )

        call_kwargs = mock_operation_log_repo.create.call_args
        from chronovista.models.tag_operation_log import TagOperationLogCreate

        obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]
        rollback = obj_in.rollback_data

        assert "original_canonical_id" in rollback
        assert "created_canonical_id" in rollback
        assert "moved_alias_ids" in rollback
        assert "previous_counts" in rollback
        assert "original_alias_count" in rollback["previous_counts"]
        assert "original_video_count" in rollback["previous_counts"]
        assert rollback["previous_counts"]["original_alias_count"] == 3
        assert rollback["previous_counts"]["original_video_count"] == 8
        assert len(rollback["moved_alias_ids"]) == 1


# ===========================================================================
# TestUndoSplit
# ===========================================================================


class TestUndoSplit:
    """
    Tests for ``TagManagementService._undo_split``.

    Covers:
    - Basic undo split: aliases returned to original, new tag deleted
    - FR-012a safety check: blocked when subsequent ops exist on created tag
    """

    async def test_basic_undo_split_returns_description(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Basic undo split: moves aliases back to original, deletes created tag,
        and returns a human-readable string.
        """
        original_id = uuid.uuid4()
        created_id = uuid.uuid4()
        alias_id = uuid.uuid4()

        log_entry = _make_operation_log(
            operation_type="split",
            rollback_data={
                "original_canonical_id": str(original_id),
                "created_canonical_id": str(created_id),
                "moved_alias_ids": [str(alias_id)],
                "previous_counts": {
                    "original_alias_count": 3,
                    "original_video_count": 8,
                },
            },
        )
        log_entry.id = uuid.uuid4()

        original_tag = _make_canonical_tag(
            normalized_form="python",
            canonical_form="Python",
            status="active",
        )
        created_tag = _make_canonical_tag(
            normalized_form="py3",
            canonical_form="PY3",
            status="active",
        )

        # SELECT to check subsequent ops -> empty
        # UPDATE alias back to original
        # get created_tag for deletion
        # recalculate original: alias, video, UPDATE
        # get original_tag for name
        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([]),    # subsequent_ops check
                MagicMock(),                  # UPDATE alias canonical_tag_id
                _make_scalar_result(3),       # recalculate alias_count
                _make_scalar_result(8),       # recalculate video_count
                MagicMock(),                  # UPDATE canonical_tags
            ]
        )
        mock_canonical_tag_repo.get.side_effect = [
            created_tag,   # get created_tag for deletion
            original_tag,  # get original_tag for name display
        ]
        mock_session.flush = AsyncMock()

        result = await service._undo_split(mock_session, log_entry)

        assert isinstance(result, str)
        assert "1" in result  # 1 alias moved back
        assert "python" in result.lower()

    async def test_undo_split_blocked_when_subsequent_ops_exist(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        FR-012a: If the created tag has subsequent non-rolled-back operations,
        undo must raise ValueError listing the blocking operation types.
        """
        original_id = uuid.uuid4()
        created_id = uuid.uuid4()
        alias_id = uuid.uuid4()

        log_entry = _make_operation_log(
            operation_type="split",
            rollback_data={
                "original_canonical_id": str(original_id),
                "created_canonical_id": str(created_id),
                "moved_alias_ids": [str(alias_id)],
                "previous_counts": {
                    "original_alias_count": 3,
                    "original_video_count": 8,
                },
            },
        )
        log_entry.id = uuid.uuid4()

        # A subsequent merge operation references the created tag
        subsequent_op = _make_operation_log(operation_type="merge", rolled_back=False)

        # subsequent_ops check returns one entry
        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([subsequent_op]),
            ]
        )

        with pytest.raises(ValueError, match="subsequent operation"):
            await service._undo_split(mock_session, log_entry)


# ===========================================================================
# TestUndo (dispatch)
# ===========================================================================


class TestUndo:
    """
    Tests for ``TagManagementService.undo`` (the public dispatch method).

    Covers:
    - Undo merge dispatch
    - Undo split dispatch
    - Already-undone operation rejection
    - Non-existent operation rejection
    """

    async def test_undo_non_existent_operation_raises(
        self,
        service: TagManagementService,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Requesting undo on an operation that doesn't exist raises ValueError.
        """
        mock_operation_log_repo.get.return_value = None
        op_id = uuid.uuid4()

        with pytest.raises(ValueError, match=str(op_id)):
            await service.undo(mock_session, op_id)

    async def test_undo_already_undone_raises(
        self,
        service: TagManagementService,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Requesting undo on an already-rolled-back operation raises ValueError.
        """
        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="merge", rolled_back=True)
        log_entry.id = op_id
        mock_operation_log_repo.get.return_value = log_entry

        with pytest.raises(ValueError, match="already been undone"):
            await service.undo(mock_session, op_id)

    async def test_undo_merge_dispatches_correctly(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Undo of a merge operation dispatches to _undo_merge and returns
        an UndoResult with operation_type='merge'.
        """
        from chronovista.services.tag_management import UndoResult

        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        alias_id = uuid.uuid4()

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(
            operation_type="merge",
            rolled_back=False,
            rollback_data={
                "sources": [
                    {
                        "canonical_tag_id": str(source_id),
                        "previous_status": "active",
                        "previous_alias_count": 2,
                        "previous_video_count": 5,
                        "previous_entity_type": None,
                        "previous_entity_id": None,
                        "alias_ids": [str(alias_id)],
                    }
                ],
                "target": {
                    "canonical_tag_id": str(target_id),
                    "previous_alias_count": 3,
                    "previous_video_count": 10,
                },
            },
        )
        log_entry.id = op_id
        mock_operation_log_repo.get.return_value = log_entry

        source_tag = _make_canonical_tag(
            normalized_form="py3",
            canonical_form="Py3",
            status="merged",
        )
        mock_canonical_tag_repo.get.return_value = source_tag

        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(),              # UPDATE alias back to source
                _make_scalar_result(2),   # source recalculate alias_count
                _make_scalar_result(5),   # source recalculate video_count
                MagicMock(),              # source UPDATE
                _make_scalar_result(3),   # target recalculate alias_count
                _make_scalar_result(10),  # target recalculate video_count
                MagicMock(),              # target UPDATE
            ]
        )
        mock_session.add = MagicMock()

        result = await service.undo(mock_session, op_id)

        assert isinstance(result, UndoResult)
        assert result.operation_type == "merge"
        assert result.operation_id == op_id

    async def test_undo_split_dispatches_correctly(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Undo of a split operation dispatches to _undo_split and returns
        an UndoResult with operation_type='split'.
        """
        from chronovista.services.tag_management import UndoResult

        original_id = uuid.uuid4()
        created_id = uuid.uuid4()
        alias_id = uuid.uuid4()

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(
            operation_type="split",
            rolled_back=False,
            rollback_data={
                "original_canonical_id": str(original_id),
                "created_canonical_id": str(created_id),
                "moved_alias_ids": [str(alias_id)],
                "previous_counts": {
                    "original_alias_count": 3,
                    "original_video_count": 8,
                },
            },
        )
        log_entry.id = op_id
        mock_operation_log_repo.get.return_value = log_entry

        original_tag = _make_canonical_tag(
            normalized_form="python",
            canonical_form="Python",
            status="active",
        )
        created_tag = _make_canonical_tag(
            normalized_form="py3",
            canonical_form="PY3",
            status="active",
        )
        mock_canonical_tag_repo.get.side_effect = [created_tag, original_tag]

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([]),  # no subsequent ops
                MagicMock(),               # UPDATE alias
                _make_scalar_result(3),    # recalculate alias_count
                _make_scalar_result(8),    # recalculate video_count
                MagicMock(),               # UPDATE
            ]
        )
        mock_session.flush = AsyncMock()
        mock_session.add = MagicMock()

        result = await service.undo(mock_session, op_id)

        assert isinstance(result, UndoResult)
        assert result.operation_type == "split"
        assert result.operation_id == op_id

    async def test_undo_marks_log_entry_as_rolled_back(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        After a successful undo, the log entry must have rolled_back=True
        and rolled_back_at set to a non-None datetime.
        """
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        alias_id = uuid.uuid4()

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(
            operation_type="merge",
            rolled_back=False,
            rollback_data={
                "sources": [
                    {
                        "canonical_tag_id": str(source_id),
                        "previous_status": "active",
                        "previous_alias_count": 2,
                        "previous_video_count": 5,
                        "previous_entity_type": None,
                        "previous_entity_id": None,
                        "alias_ids": [str(alias_id)],
                    }
                ],
                "target": {
                    "canonical_tag_id": str(target_id),
                    "previous_alias_count": 3,
                    "previous_video_count": 10,
                },
            },
        )
        log_entry.id = op_id
        mock_operation_log_repo.get.return_value = log_entry

        source_tag = _make_canonical_tag(normalized_form="py3", status="merged")
        mock_canonical_tag_repo.get.return_value = source_tag

        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(),
                _make_scalar_result(2),
                _make_scalar_result(5),
                MagicMock(),
                _make_scalar_result(3),
                _make_scalar_result(10),
                MagicMock(),
            ]
        )
        mock_session.add = MagicMock()

        await service.undo(mock_session, op_id)

        assert log_entry.rolled_back is True
        assert log_entry.rolled_back_at is not None


# ===========================================================================
# TestRename
# ===========================================================================


class TestRename:
    """
    Tests for ``TagManagementService.rename``.

    Covers:
    - Basic rename happy path
    - Empty/whitespace display form rejection
    - Non-existent tag rejection
    - Non-active tag rejection
    - rollback_data structure
    """

    async def test_basic_rename_returns_rename_result(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Happy path: rename updates canonical_form and returns RenameResult.

        Verifies: normalized_form, old_form, new_form, operation_id.
        """
        from chronovista.services.tag_management import RenameResult

        tag = _make_canonical_tag(
            normalized_form="python",
            canonical_form="python",
            status="active",
        )
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="rename")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry
        mock_session.add = MagicMock()

        result = await service.rename(
            mock_session,
            normalized_form="python",
            new_display_form="Python",
            reason="Title-case correction",
        )

        assert isinstance(result, RenameResult)
        assert result.normalized_form == "python"
        assert result.old_form == "python"
        assert result.new_form == "Python"
        assert result.operation_id == op_id

    async def test_rename_updates_canonical_form_on_tag(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The canonical_form attribute on the tag object must be set to
        the new display form after rename.
        """
        tag = _make_canonical_tag(
            normalized_form="python",
            canonical_form="OldPython",
            status="active",
        )
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="rename")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry
        mock_session.add = MagicMock()

        await service.rename(
            mock_session,
            normalized_form="python",
            new_display_form="Python",
        )

        assert tag.canonical_form == "Python"

    async def test_rename_empty_form_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Empty new_display_form (including whitespace-only) must raise ValueError
        before any database access.
        """
        with pytest.raises(ValueError, match="cannot be empty"):
            await service.rename(
                mock_session,
                normalized_form="python",
                new_display_form="   ",
            )

        mock_canonical_tag_repo.get_by_normalized_form.assert_not_called()

    async def test_rename_non_existent_tag_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Renaming a tag that does not exist must raise ValueError.
        """
        mock_canonical_tag_repo.get_by_normalized_form.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.rename(
                mock_session,
                normalized_form="doesnotexist",
                new_display_form="New Form",
            )

    async def test_rename_non_active_tag_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Renaming a deprecated tag must raise ValueError with status info.
        """
        deprecated = _make_canonical_tag(normalized_form="oldtag", status="deprecated")
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            None, None, deprecated
        ]

        with pytest.raises(ValueError, match="deprecated"):
            await service.rename(
                mock_session,
                normalized_form="oldtag",
                new_display_form="New Form",
            )

    async def test_rename_rollback_data_structure(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The rollback_data for a rename must contain:
        - ``canonical_id``: str UUID of the tag
        - ``previous_form``: the old canonical_form
        - ``new_form``: the new canonical_form
        """
        tag = _make_canonical_tag(
            normalized_form="python",
            canonical_form="OldPython",
            status="active",
        )
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="rename")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry
        mock_session.add = MagicMock()

        await service.rename(
            mock_session,
            normalized_form="python",
            new_display_form="Python",
            reason="Fix case",
        )

        call_kwargs = mock_operation_log_repo.create.call_args
        from chronovista.models.tag_operation_log import TagOperationLogCreate

        obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]
        rollback = obj_in.rollback_data

        assert "canonical_id" in rollback
        assert rollback["canonical_id"] == str(tag.id)
        assert "previous_form" in rollback
        assert rollback["previous_form"] == "OldPython"
        assert "new_form" in rollback
        assert rollback["new_form"] == "Python"

    async def test_undo_rename_restores_old_form(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        _undo_rename must restore canonical_form to its previous value.
        """
        canonical_id = uuid.uuid4()
        log_entry = _make_operation_log(
            operation_type="rename",
            rollback_data={
                "canonical_id": str(canonical_id),
                "previous_form": "OldPython",
                "new_form": "Python",
            },
        )

        tag = _make_canonical_tag(
            normalized_form="python",
            canonical_form="Python",
            status="active",
        )
        mock_canonical_tag_repo.get.return_value = tag
        mock_session.add = MagicMock()

        result = await service._undo_rename(mock_session, log_entry)

        assert tag.canonical_form == "OldPython"
        assert "OldPython" in result
        assert "Python" in result


# ===========================================================================
# TestClassify
# ===========================================================================


class TestClassify:
    """
    Tests for ``TagManagementService.classify``.

    Covers:
    - Entity-producing type (creates new NamedEntity + entity aliases)
    - Tag-only type (topic/descriptor: no entity record)
    - Already-classified rejection (without force)
    - --force reclassification (deletes old entity if user_created)
    - rollback_data structure
    """

    async def test_classify_entity_producing_type_creates_entity(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_named_entity_repo: AsyncMock,
        mock_entity_alias_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Classifying with EntityType.PERSON (entity-producing) must:
        1. Create a new NamedEntity.
        2. Copy tag aliases as entity aliases.
        3. Return ClassifyResult with entity_created=True.
        """
        from chronovista.models.enums import EntityType
        from chronovista.services.tag_management import ClassifyResult

        tag = _make_canonical_tag(
            normalized_form="elon musk",
            canonical_form="Elon Musk",
            status="active",
        )
        tag.entity_type = None
        tag.entity_id = None
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        # No existing entity with same normalized form
        alias_a = _make_tag_alias(
            raw_form="Elon Musk", normalized_form="elon musk", canonical_tag_id=tag.id
        )
        alias_b = _make_tag_alias(
            raw_form="ElonMusk", normalized_form="elonmusk", canonical_tag_id=tag.id
        )

        new_entity = _make_named_entity(
            normalized_form="elon musk",
            entity_type="person",
            discovery_method="user_created",
        )
        mock_named_entity_repo.create.return_value = new_entity

        ea1 = _make_entity_alias(entity_id=new_entity.id)
        ea2 = _make_entity_alias(entity_id=new_entity.id)
        mock_entity_alias_repo.create.side_effect = [ea1, ea2]

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="create")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        # SELECT: no existing entity, SELECT: tag aliases,
        # SELECT: entity alias existence check per alias (upsert logic)
        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(**{"scalar_one_or_none.return_value": None}),  # existing entity check
                _make_scalars_result([alias_a, alias_b]),                # tag aliases
                MagicMock(**{"scalar_one_or_none.return_value": None}),  # alias_a upsert check
                MagicMock(**{"scalar_one_or_none.return_value": None}),  # alias_b upsert check
            ]
        )
        mock_session.add = MagicMock()

        result = await service.classify(
            mock_session,
            normalized_form="elon musk",
            entity_type=EntityType.PERSON,
            reason="Known person",
        )

        assert isinstance(result, ClassifyResult)
        assert result.entity_created is True
        assert result.entity_type == "person"
        assert result.entity_alias_count == 2
        assert result.operation_id == op_id
        mock_named_entity_repo.create.assert_called_once()

    async def test_classify_tag_only_type_no_entity_created(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_named_entity_repo: AsyncMock,
        mock_entity_alias_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Classifying with EntityType.TOPIC (tag-only) must:
        1. NOT create any NamedEntity.
        2. Set entity_type on the tag.
        3. Return ClassifyResult with entity_created=False, entity_alias_count=0.
        """
        from chronovista.models.enums import EntityType
        from chronovista.services.tag_management import ClassifyResult

        tag = _make_canonical_tag(
            normalized_form="coding tips",
            canonical_form="Coding Tips",
            status="active",
        )
        tag.entity_type = None
        tag.entity_id = None
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="create")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry
        mock_session.add = MagicMock()

        result = await service.classify(
            mock_session,
            normalized_form="coding tips",
            entity_type=EntityType.TOPIC,
        )

        assert isinstance(result, ClassifyResult)
        assert result.entity_created is False
        assert result.entity_type == "topic"
        assert result.entity_alias_count == 0
        mock_named_entity_repo.create.assert_not_called()
        mock_entity_alias_repo.create.assert_not_called()

    async def test_classify_descriptor_type_no_entity_created(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_named_entity_repo: AsyncMock,
        mock_entity_alias_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Classifying with EntityType.DESCRIPTOR (tag-only) must not create
        any entity record.
        """
        from chronovista.models.enums import EntityType
        from chronovista.services.tag_management import ClassifyResult

        tag = _make_canonical_tag(
            normalized_form="beginner friendly",
            canonical_form="Beginner Friendly",
            status="active",
        )
        tag.entity_type = None
        tag.entity_id = None
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="create")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry
        mock_session.add = MagicMock()

        result = await service.classify(
            mock_session,
            normalized_form="beginner friendly",
            entity_type=EntityType.DESCRIPTOR,
        )

        assert isinstance(result, ClassifyResult)
        assert result.entity_created is False
        assert result.entity_type == "descriptor"
        assert result.entity_alias_count == 0

    async def test_classify_already_classified_without_force_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Classifying an already-classified tag without force=True must raise
        ValueError with a message suggesting --force.
        """
        from chronovista.models.enums import EntityType

        tag = _make_canonical_tag(
            normalized_form="python",
            canonical_form="Python",
            status="active",
        )
        tag.entity_type = "technical_term"  # already classified
        tag.entity_id = uuid.uuid4()
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        with pytest.raises(ValueError, match="--force"):
            await service.classify(
                mock_session,
                normalized_form="python",
                entity_type=EntityType.TOPIC,
                force=False,
            )

    async def test_classify_force_reclassifies_tag_only_to_entity_producing(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_named_entity_repo: AsyncMock,
        mock_entity_alias_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        With force=True, an already-classified tag can be reclassified.
        If entity_id is None (tag-only previous type), no entity deletion needed.
        """
        from chronovista.models.enums import EntityType
        from chronovista.services.tag_management import ClassifyResult

        tag = _make_canonical_tag(
            normalized_form="python",
            canonical_form="Python",
            status="active",
        )
        tag.entity_type = "topic"    # previously classified as topic (tag-only)
        tag.entity_id = None         # no entity record for tag-only

        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        alias_a = _make_tag_alias(raw_form="Python", canonical_tag_id=tag.id)
        new_entity = _make_named_entity(
            normalized_form="python",
            entity_type="technical_term",
            discovery_method="user_created",
        )
        mock_named_entity_repo.create.return_value = new_entity

        ea = _make_entity_alias(entity_id=new_entity.id)
        mock_entity_alias_repo.create.return_value = ea

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="create")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(**{"scalar_one_or_none.return_value": None}),  # existing entity check
                _make_scalars_result([alias_a]),                          # tag aliases
                MagicMock(**{"scalar_one_or_none.return_value": None}),  # alias_a upsert check
            ]
        )
        mock_session.add = MagicMock()

        result = await service.classify(
            mock_session,
            normalized_form="python",
            entity_type=EntityType.TECHNICAL_TERM,
            force=True,
        )

        assert isinstance(result, ClassifyResult)
        assert result.entity_created is True
        assert result.entity_type == "technical_term"

    async def test_classify_rollback_data_structure(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_named_entity_repo: AsyncMock,
        mock_entity_alias_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        rollback_data for classify must contain:
        - ``canonical_id``
        - ``previous_entity_type``
        - ``new_entity_type``
        - ``created_entity_id`` (str UUID or None)
        - ``linked_existing_entity_id`` (str UUID or None)
        - ``created_entity_alias_ids`` (list of str UUIDs)
        """
        from chronovista.models.enums import EntityType
        from chronovista.models.tag_operation_log import TagOperationLogCreate

        tag = _make_canonical_tag(
            normalized_form="google",
            canonical_form="Google",
            status="active",
        )
        tag.entity_type = None
        tag.entity_id = None
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        alias_a = _make_tag_alias(raw_form="Google", canonical_tag_id=tag.id)
        new_entity = _make_named_entity(
            normalized_form="google",
            entity_type="organization",
            discovery_method="user_created",
        )
        mock_named_entity_repo.create.return_value = new_entity

        ea = _make_entity_alias(entity_id=new_entity.id)
        mock_entity_alias_repo.create.return_value = ea

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="create")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry

        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(**{"scalar_one_or_none.return_value": None}),  # existing entity check
                _make_scalars_result([alias_a]),                          # tag aliases
                MagicMock(**{"scalar_one_or_none.return_value": None}),  # alias_a upsert check
            ]
        )
        mock_session.add = MagicMock()

        await service.classify(
            mock_session,
            normalized_form="google",
            entity_type=EntityType.ORGANIZATION,
        )

        call_kwargs = mock_operation_log_repo.create.call_args
        obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]
        rollback = obj_in.rollback_data

        assert "canonical_id" in rollback
        assert rollback["canonical_id"] == str(tag.id)
        assert "previous_entity_type" in rollback
        assert rollback["previous_entity_type"] is None
        assert "new_entity_type" in rollback
        assert rollback["new_entity_type"] == "organization"
        assert "created_entity_id" in rollback
        assert rollback["created_entity_id"] == str(new_entity.id)
        assert "linked_existing_entity_id" in rollback
        assert rollback["linked_existing_entity_id"] is None
        assert "created_entity_alias_ids" in rollback
        assert len(rollback["created_entity_alias_ids"]) == 1


# ===========================================================================
# TestUndoClassify
# ===========================================================================


class TestUndoClassify:
    """
    Tests for ``TagManagementService._undo_classify``.

    Covers:
    - Undo when a new entity was created (delete entity + aliases)
    - Undo when tag-only classification (no entity to delete)
    """

    async def test_undo_classify_new_entity_deleted(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_named_entity_repo: AsyncMock,
        mock_entity_alias_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        When rollback_data has ``created_entity_id``, the entity and its
        aliases must be deleted and the tag's entity_type cleared.
        """
        canonical_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        ea_id = uuid.uuid4()

        log_entry = _make_operation_log(
            operation_type="create",
            rollback_data={
                "canonical_id": str(canonical_id),
                "previous_entity_type": None,
                "new_entity_type": "person",
                "created_entity_id": str(entity_id),
                "linked_existing_entity_id": None,
                "created_entity_alias_ids": [str(ea_id)],
            },
        )

        tag = _make_canonical_tag(
            normalized_form="elon musk",
            canonical_form="Elon Musk",
            status="active",
        )
        tag.entity_type = "person"
        tag.entity_id = entity_id

        entity = _make_named_entity(
            normalized_form="elon musk",
            entity_type="person",
            discovery_method="user_created",
        )

        ea = _make_entity_alias(entity_id=entity_id)
        ea.id = ea_id

        mock_canonical_tag_repo.get.return_value = tag
        mock_named_entity_repo.get.return_value = entity
        mock_entity_alias_repo.get.return_value = ea

        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.add = MagicMock()

        result = await service._undo_classify(mock_session, log_entry)

        # Tag entity_type should be restored to previous (None)
        assert tag.entity_type is None
        assert tag.entity_id is None
        # entity alias deleted
        mock_session.delete.assert_any_call(ea)
        # entity deleted
        mock_session.delete.assert_any_call(entity)
        assert isinstance(result, str)
        assert "elon musk" in result

    async def test_undo_classify_tag_only_clears_entity_type(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_named_entity_repo: AsyncMock,
        mock_entity_alias_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        For a tag-only classification (no entity), undo must clear entity_type
        without attempting to delete any entity.
        """
        canonical_id = uuid.uuid4()

        log_entry = _make_operation_log(
            operation_type="create",
            rollback_data={
                "canonical_id": str(canonical_id),
                "previous_entity_type": None,
                "new_entity_type": "topic",
                "created_entity_id": None,
                "linked_existing_entity_id": None,
                "created_entity_alias_ids": [],
            },
        )

        tag = _make_canonical_tag(
            normalized_form="tutorials",
            canonical_form="Tutorials",
            status="active",
        )
        tag.entity_type = "topic"
        tag.entity_id = None

        mock_canonical_tag_repo.get.return_value = tag
        mock_session.flush = AsyncMock()
        mock_session.add = MagicMock()

        result = await service._undo_classify(mock_session, log_entry)

        assert tag.entity_type is None
        assert tag.entity_id is None
        mock_named_entity_repo.get.assert_not_called()
        assert isinstance(result, str)


# ===========================================================================
# TestGetCollisions
# ===========================================================================


class TestGetCollisions:
    """
    Tests for ``TagManagementService.get_collisions``.

    Covers:
    - Basic collision detection (aliases with distinct casefolded forms)
    - Tags with no collision (single alias or all same casefold) are excluded
    - --include-reviewed flag controls filtering
    - --limit truncates results
    - Sorted by total_occurrence_count descending
    """

    async def test_basic_collision_detected(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        A tag with two aliases whose casefolded forms differ (e.g. 'cafe' vs
        'café') must appear in the collision list.
        """
        from chronovista.services.tag_management import CollisionGroup

        tag = _make_canonical_tag(
            normalized_form="cafe",
            canonical_form="Cafe",
            status="active",
        )
        tag.id = uuid.uuid4()

        alias_a = _make_tag_alias(
            raw_form="cafe",
            canonical_tag_id=tag.id,
            occurrence_count=10,
        )
        alias_b = _make_tag_alias(
            raw_form="café",
            canonical_tag_id=tag.id,
            occurrence_count=5,
        )

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([tag]),               # active tags (first)
                _make_scalars_result([]),                  # reviewed log entries (none)
                _make_scalars_result([alias_a, alias_b]),  # aliases for tag
            ]
        )

        result = await service.get_collisions(
            mock_session,
            include_reviewed=False,
        )

        assert len(result) == 1
        assert isinstance(result[0], CollisionGroup)
        assert result[0].normalized_form == "cafe"
        assert result[0].total_occurrence_count == 15
        assert len(result[0].aliases) == 2

    async def test_no_collision_when_aliases_same_casefold(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        A tag whose aliases all casefold to the same string must NOT appear
        in the collision list (e.g. 'Python' and 'PYTHON' both casefold to 'python').
        """
        tag = _make_canonical_tag(normalized_form="python", canonical_form="Python", status="active")

        alias_a = _make_tag_alias(raw_form="Python", canonical_tag_id=tag.id)
        alias_b = _make_tag_alias(raw_form="PYTHON", canonical_tag_id=tag.id)

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([tag]),               # active tags (first)
                _make_scalars_result([]),                  # reviewed entries (none)
                _make_scalars_result([alias_a, alias_b]),  # aliases
            ]
        )

        result = await service.get_collisions(mock_session)

        assert len(result) == 0

    async def test_single_alias_tag_excluded_from_collisions(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        Tags with fewer than 2 aliases must not appear as collision candidates.
        """
        tag = _make_canonical_tag(normalized_form="python", status="active")
        alias_a = _make_tag_alias(raw_form="Python", canonical_tag_id=tag.id)

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([tag]),      # active tags (first)
                _make_scalars_result([]),          # reviewed (none)
                _make_scalars_result([alias_a]),   # single alias
            ]
        )

        result = await service.get_collisions(mock_session)

        assert len(result) == 0

    async def test_collisions_sorted_by_occurrence_count_descending(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        Collision groups must be sorted by total_occurrence_count descending
        so the highest-impact collisions appear first.
        """
        from chronovista.services.tag_management import CollisionGroup

        tag1 = _make_canonical_tag(normalized_form="cafe", canonical_form="Cafe", status="active")
        tag1.id = uuid.uuid4()
        tag2 = _make_canonical_tag(normalized_form="resume", canonical_form="Resume", status="active")
        tag2.id = uuid.uuid4()

        alias1a = _make_tag_alias(raw_form="cafe", canonical_tag_id=tag1.id, occurrence_count=2)
        alias1b = _make_tag_alias(raw_form="café", canonical_tag_id=tag1.id, occurrence_count=3)
        # tag1 total = 5

        alias2a = _make_tag_alias(raw_form="resume", canonical_tag_id=tag2.id, occurrence_count=50)
        alias2b = _make_tag_alias(raw_form="résumé", canonical_tag_id=tag2.id, occurrence_count=50)
        # tag2 total = 100

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([tag1, tag2]),           # active tags (first)
                _make_scalars_result([]),                     # reviewed (none)
                _make_scalars_result([alias1a, alias1b]),     # tag1 aliases
                _make_scalars_result([alias2a, alias2b]),     # tag2 aliases
            ]
        )

        result = await service.get_collisions(mock_session)

        assert len(result) == 2
        # tag2 (100 occurrences) should come before tag1 (5 occurrences)
        assert result[0].total_occurrence_count == 100
        assert result[1].total_occurrence_count == 5

    async def test_collisions_with_limit(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        --limit must truncate the result list to at most N collision groups.
        """
        tags_and_aliases = []

        active_tags = []
        for i in range(5):
            tag = _make_canonical_tag(
                normalized_form=f"tag{i}",
                canonical_form=f"Tag{i}",
                status="active",
            )
            tag.id = uuid.uuid4()
            active_tags.append(tag)
            alias_a = _make_tag_alias(
                raw_form=f"tag{i}lower",
                canonical_tag_id=tag.id,
                occurrence_count=10,
            )
            alias_b = _make_tag_alias(
                raw_form=f"Tag{i}UPPER",
                canonical_tag_id=tag.id,
                occurrence_count=5,
            )
            tags_and_aliases.append((tag, [alias_a, alias_b]))

        # Order: active tags first, reviewed second, then per-tag alias queries
        execute_sides: list[Any] = [_make_scalars_result(active_tags)]  # active tags
        execute_sides.append(_make_scalars_result([]))  # reviewed (none)
        for _tag, aliases in tags_and_aliases:
            execute_sides.append(_make_scalars_result(aliases))

        mock_session.execute = AsyncMock(side_effect=execute_sides)

        result = await service.get_collisions(mock_session, limit=2)

        assert len(result) == 2

    async def test_collisions_include_reviewed_flag(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        With include_reviewed=True, the reviewed-log query must NOT be
        executed and all collision candidates must be included.
        """
        from chronovista.services.tag_management import CollisionGroup

        tag = _make_canonical_tag(
            normalized_form="naïve",
            canonical_form="Naïve",
            status="active",
        )
        tag.id = uuid.uuid4()

        alias_a = _make_tag_alias(raw_form="naive", canonical_tag_id=tag.id, occurrence_count=10)
        alias_b = _make_tag_alias(raw_form="naïve", canonical_tag_id=tag.id, occurrence_count=5)

        # With include_reviewed=True: no reviewed-log query, just active tags + aliases
        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([tag]),           # active tags
                _make_scalars_result([alias_a, alias_b]),  # aliases
            ]
        )

        result = await service.get_collisions(mock_session, include_reviewed=True)

        assert len(result) == 1
        assert isinstance(result[0], CollisionGroup)

    async def test_hashtag_stripping_in_collision_detection(
        self,
        service: TagManagementService,
        mock_session: AsyncMock,
    ) -> None:
        """
        Leading '#' characters must be stripped before casefolding for
        collision detection. '#cafe' and 'café' should produce a collision
        since 'cafe' != 'caf\xe9'.
        """
        from chronovista.services.tag_management import CollisionGroup

        tag = _make_canonical_tag(normalized_form="cafe", canonical_form="Cafe", status="active")
        tag.id = uuid.uuid4()

        alias_a = _make_tag_alias(raw_form="#cafe", canonical_tag_id=tag.id, occurrence_count=8)
        alias_b = _make_tag_alias(raw_form="café", canonical_tag_id=tag.id, occurrence_count=4)

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([tag]),               # active tags (first)
                _make_scalars_result([]),                  # reviewed (none)
                _make_scalars_result([alias_a, alias_b]),  # aliases
            ]
        )

        result = await service.get_collisions(mock_session)

        assert len(result) == 1
        assert isinstance(result[0], CollisionGroup)


# ===========================================================================
# TestDeprecate
# ===========================================================================


class TestDeprecate:
    """
    Tests for ``TagManagementService.deprecate``.

    Covers:
    - Basic deprecate happy path
    - Already-deprecated tag rejection
    - Merged tag rejection
    - rollback_data structure
    - Undo deprecate restores previous status
    """

    async def test_basic_deprecate_returns_deprecate_result(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Happy path: deprecate marks an active tag as deprecated.

        Verifies DeprecateResult fields: normalized_form, canonical_form,
        alias_count, operation_id.
        """
        from chronovista.services.tag_management import DeprecateResult

        tag = _make_canonical_tag(
            normalized_form="oldtag",
            canonical_form="OldTag",
            status="active",
            alias_count=3,
            video_count=5,
        )
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="delete")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry
        mock_session.add = MagicMock()

        result = await service.deprecate(
            mock_session,
            normalized_form="oldtag",
            reason="Superseded by newer tag",
        )

        assert isinstance(result, DeprecateResult)
        assert result.normalized_form == "oldtag"
        assert result.canonical_form == "OldTag"
        assert result.alias_count == 3
        assert result.operation_id == op_id

    async def test_deprecate_sets_status_to_deprecated(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        After deprecate, tag.status must be 'deprecated'.
        """
        from chronovista.models.enums import TagStatus

        tag = _make_canonical_tag(normalized_form="oldtag", status="active")
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="delete")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry
        mock_session.add = MagicMock()

        await service.deprecate(mock_session, normalized_form="oldtag")

        assert tag.status == TagStatus.DEPRECATED.value

    async def test_deprecate_already_deprecated_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Attempting to deprecate a tag that is already deprecated must raise
        ValueError with the current status in the message.
        """
        deprecated = _make_canonical_tag(normalized_form="oldtag", status="deprecated")
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            None, None, deprecated
        ]

        with pytest.raises(ValueError, match="deprecated"):
            await service.deprecate(mock_session, normalized_form="oldtag")

    async def test_deprecate_merged_tag_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Attempting to deprecate a merged tag must raise ValueError with
        the 'merged' status mentioned.
        """
        merged = _make_canonical_tag(normalized_form="oldtag", status="merged")
        mock_canonical_tag_repo.get_by_normalized_form.side_effect = [
            None, merged
        ]

        with pytest.raises(ValueError, match="merged"):
            await service.deprecate(mock_session, normalized_form="oldtag")

    async def test_deprecate_rollback_data_structure(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        rollback_data for deprecate must contain:
        - ``canonical_id``: str UUID of the tag
        - ``previous_status``: the status before deprecation ('active')
        """
        from chronovista.models.tag_operation_log import TagOperationLogCreate

        tag = _make_canonical_tag(
            normalized_form="oldtag",
            canonical_form="OldTag",
            status="active",
        )
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="delete")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry
        mock_session.add = MagicMock()

        await service.deprecate(
            mock_session,
            normalized_form="oldtag",
            reason="Superseded",
        )

        call_kwargs = mock_operation_log_repo.create.call_args
        obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]
        rollback = obj_in.rollback_data

        assert "canonical_id" in rollback
        assert rollback["canonical_id"] == str(tag.id)
        assert "previous_status" in rollback
        assert rollback["previous_status"] == "active"

    async def test_deprecate_logs_with_delete_operation_type(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_operation_log_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The operation log entry must use operation_type='delete' (per spec),
        not 'deprecate' (which is not a valid operation type).
        """
        from chronovista.models.tag_operation_log import TagOperationLogCreate

        tag = _make_canonical_tag(normalized_form="oldtag", status="active")
        mock_canonical_tag_repo.get_by_normalized_form.return_value = tag

        op_id = uuid.uuid4()
        log_entry = _make_operation_log(operation_type="delete")
        log_entry.id = op_id
        mock_operation_log_repo.create.return_value = log_entry
        mock_session.add = MagicMock()

        await service.deprecate(mock_session, normalized_form="oldtag")

        call_kwargs = mock_operation_log_repo.create.call_args
        obj_in: TagOperationLogCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.operation_type == "delete"

    async def test_undo_deprecate_restores_previous_status(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        _undo_deprecate must restore the tag status to its previous value
        (typically 'active').
        """
        canonical_id = uuid.uuid4()
        log_entry = _make_operation_log(
            operation_type="delete",
            rollback_data={
                "canonical_id": str(canonical_id),
                "previous_status": "active",
            },
        )

        tag = _make_canonical_tag(
            normalized_form="oldtag",
            canonical_form="OldTag",
            status="deprecated",
        )
        mock_canonical_tag_repo.get.return_value = tag
        mock_session.add = MagicMock()

        result = await service._undo_deprecate(mock_session, log_entry)

        assert tag.status == "active"
        assert isinstance(result, str)
        assert "oldtag" in result
        assert "active" in result

    async def test_undo_deprecate_tag_not_found_raises(
        self,
        service: TagManagementService,
        mock_canonical_tag_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        _undo_deprecate must raise ValueError if the canonical tag referenced
        in rollback_data no longer exists.
        """
        canonical_id = uuid.uuid4()
        log_entry = _make_operation_log(
            operation_type="delete",
            rollback_data={
                "canonical_id": str(canonical_id),
                "previous_status": "active",
            },
        )

        mock_canonical_tag_repo.get.return_value = None

        with pytest.raises(ValueError, match="Cannot undo deprecate"):
            await service._undo_deprecate(mock_session, log_entry)
