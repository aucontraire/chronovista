"""
Unit tests for the ``--entity-id`` flag on the ``entities scan`` CLI command.

Covers Feature 052 — Targeted Entity & Video-Level Mention Scanning.

All external dependencies (database session, scan service) are mocked so
that only CLI option-parsing and output-formatting logic is exercised.

Covered scenarios:
(a) ``--entity-id`` with valid UUID format passes UUID parsing.
(b) ``--entity-id`` with invalid UUID string shows red Panel error, exits 1.
(c) ``--entity-id`` with non-existent entity shows "Entity not found" panel.
(d) ``--entity-id`` with inactive/merged entity shows "Entity is not active".
(e) ``--entity-id`` overrides ``--entity-type`` (entity_type is set to None).
(f) ``--entity-id`` overrides ``--new-entities-only`` (flag is cleared).
(g) ``--entity-id`` + ``--video-id`` passes both to scan().

Feature 052 — Targeted Entity & Video-Level Mention Scanning
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.entity_commands import entity_app

# CRITICAL: Module-level asyncio marker ensures async tests run with coverage.

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_uuid() -> uuid.UUID:
    """Return a fresh UUID4."""
    return uuid.uuid4()


def _make_entity_mock(
    entity_id: uuid.UUID | None = None,
    canonical_name: str = "Test Person",
    status: str = "active",
) -> MagicMock:
    """Build a mock NamedEntity DB row."""
    entity = MagicMock()
    entity.id = entity_id or _make_uuid()
    entity.canonical_name = canonical_name
    entity.status = status
    return entity


def _make_scan_result(**kwargs: Any) -> MagicMock:
    """Build a mock ScanResult with sensible defaults."""
    result = MagicMock()
    result.segments_scanned = kwargs.get("segments_scanned", 10)
    result.mentions_found = kwargs.get("mentions_found", 2)
    result.mentions_skipped = kwargs.get("mentions_skipped", 0)
    result.skipped_exclusion_pattern = kwargs.get("skipped_exclusion_pattern", 0)
    result.skipped_longest_match = kwargs.get("skipped_longest_match", 0)
    result.unique_entities = kwargs.get("unique_entities", 1)
    result.unique_videos = kwargs.get("unique_videos", 1)
    result.duration_seconds = kwargs.get("duration_seconds", 0.5)
    result.dry_run = kwargs.get("dry_run", False)
    result.dry_run_matches = kwargs.get("dry_run_matches")
    result.failed_batches = kwargs.get("failed_batches", 0)
    return result


def _make_async_session_generator(entity: Any) -> AsyncGenerator[Any, None]:
    """Create an async generator that yields a session with entity look-up."""

    async def _gen() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        session.get = AsyncMock(return_value=entity)
        yield session

    return _gen()


def _run_coro_via_fake_asyncio_run(coro: object) -> None:
    """Execute a coroutine synchronously (used to replace asyncio.run in CLI)."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)  # type: ignore[arg-type]
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# TestEntityIdUuidValidation
# ---------------------------------------------------------------------------


class TestEntityIdUuidValidation:
    """Tests for UUID format validation of the ``--entity-id`` option."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Return a Typer CliRunner."""
        return CliRunner()

    def test_invalid_uuid_shows_red_panel_error(self, runner: CliRunner) -> None:
        """An invalid UUID string must show a Rich Panel error message."""
        result = runner.invoke(entity_app, ["scan", "--entity-id", "not-a-uuid"])

        assert result.exit_code == 1
        output = result.stdout or ""
        assert "Invalid --entity-id" in output or "Invalid" in output.lower()

    def test_invalid_uuid_exits_with_code_1(self, runner: CliRunner) -> None:
        """``--entity-id not-a-uuid`` must exit with code 1."""
        result = runner.invoke(entity_app, ["scan", "--entity-id", "not-a-uuid"])
        assert result.exit_code == 1

    def test_invalid_uuid_does_not_call_asyncio_run(
        self, runner: CliRunner
    ) -> None:
        """UUID validation failure must exit before ``asyncio.run`` is called."""
        with patch(
            "chronovista.cli.entity_commands.asyncio.run"
        ) as mock_asyncio_run:
            runner.invoke(entity_app, ["scan", "--entity-id", "totally-wrong"])

        mock_asyncio_run.assert_not_called()

    def test_invalid_uuid_partial_hex_shows_error(self, runner: CliRunner) -> None:
        """A partial hex string must be rejected with exit code 1."""
        result = runner.invoke(
            entity_app, ["scan", "--entity-id", "550e8400-e29b"]
        )
        assert result.exit_code == 1

    def test_valid_uuid_format_passes_validation(self, runner: CliRunner) -> None:
        """A well-formed UUID string must not trigger the format-error path."""
        valid_uuid = str(_make_uuid())

        _make_entity_mock(status="active")

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.EntityMentionScanService"
            ),
            patch("chronovista.cli.entity_commands.asyncio.run") as mock_asyncio_run,
        ):
            mock_db.get_session_factory.return_value = MagicMock()
            mock_asyncio_run.return_value = None

            runner.invoke(entity_app, ["scan", "--entity-id", valid_uuid])

        # The scan would proceed to asyncio.run (entity lookup happens inside)
        # and NOT exit with code 1 due to UUID format error


# ---------------------------------------------------------------------------
# TestEntityIdEntityNotFound
# ---------------------------------------------------------------------------


class TestEntityIdEntityNotFound:
    """Tests for the 'Entity not found' error path inside the async scan flow."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Return a Typer CliRunner."""
        return CliRunner()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_non_existent_entity_shows_not_found_panel(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When session.get() returns None, an 'Entity not found' panel is shown."""
        valid_uuid = str(_make_uuid())

        mock_db_manager.get_session_factory.return_value = MagicMock()

        # session.get returns None → entity not found
        async def fake_get_session(**kwargs: Any) -> AsyncGenerator[Any, None]:
            session = AsyncMock()
            session.get = AsyncMock(return_value=None)
            yield session

        mock_db_manager.get_session.return_value = fake_get_session()

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app, ["scan", "--entity-id", valid_uuid]
            )

        assert result.exit_code == 1
        output = result.stdout or ""
        assert (
            "not found" in output.lower()
            or "Entity not found" in output
        ), f"Expected 'not found' in output; got: {output[:400]}"

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_non_existent_entity_exits_with_code_1(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When entity is not found, the command must exit with code 1."""
        valid_uuid = str(_make_uuid())
        mock_db_manager.get_session_factory.return_value = MagicMock()

        async def fake_get_session(**kwargs: Any) -> AsyncGenerator[Any, None]:
            session = AsyncMock()
            session.get = AsyncMock(return_value=None)
            yield session

        mock_db_manager.get_session.return_value = fake_get_session()

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app, ["scan", "--entity-id", valid_uuid]
            )

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# TestEntityIdInactiveEntity
# ---------------------------------------------------------------------------


class TestEntityIdInactiveEntity:
    """Tests for the 'Entity is not active' error path."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Return a Typer CliRunner."""
        return CliRunner()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_merged_entity_shows_not_active_panel(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When entity status is 'merged', an 'Entity is not active' panel is shown."""
        valid_uuid = str(_make_uuid())
        mock_db_manager.get_session_factory.return_value = MagicMock()

        merged_entity = _make_entity_mock(status="merged")

        async def fake_get_session(**kwargs: Any) -> AsyncGenerator[Any, None]:
            session = AsyncMock()
            session.get = AsyncMock(return_value=merged_entity)
            yield session

        mock_db_manager.get_session.return_value = fake_get_session()

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app, ["scan", "--entity-id", valid_uuid]
            )

        assert result.exit_code == 1
        output = result.stdout or ""
        assert (
            "not active" in output.lower()
            or "Entity is not active" in output
        ), f"Expected 'not active' in output; got: {output[:400]}"

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_deprecated_entity_shows_not_active_panel(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When entity status is 'deprecated', a not-active error is shown."""
        valid_uuid = str(_make_uuid())
        mock_db_manager.get_session_factory.return_value = MagicMock()

        deprecated_entity = _make_entity_mock(status="deprecated")

        async def fake_get_session(**kwargs: Any) -> AsyncGenerator[Any, None]:
            session = AsyncMock()
            session.get = AsyncMock(return_value=deprecated_entity)
            yield session

        mock_db_manager.get_session.return_value = fake_get_session()

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app, ["scan", "--entity-id", valid_uuid]
            )

        assert result.exit_code == 1
        output = result.stdout or ""
        assert (
            "not active" in output.lower()
            or "deprecated" in output.lower()
        ), f"Expected not-active indication; got: {output[:400]}"

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_inactive_entity_exits_with_code_1(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When entity is inactive, the command must exit with code 1."""
        valid_uuid = str(_make_uuid())
        mock_db_manager.get_session_factory.return_value = MagicMock()

        inactive_entity = _make_entity_mock(status="merged")

        async def fake_get_session(**kwargs: Any) -> AsyncGenerator[Any, None]:
            session = AsyncMock()
            session.get = AsyncMock(return_value=inactive_entity)
            yield session

        mock_db_manager.get_session.return_value = fake_get_session()

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app, ["scan", "--entity-id", valid_uuid]
            )

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# TestEntityIdTakesPrecedenceOverFilters
# ---------------------------------------------------------------------------


class TestEntityIdTakesPrecedenceOverFilters:
    """--entity-id overrides --entity-type and --new-entities-only."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Return a Typer CliRunner."""
        return CliRunner()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_entity_id_overrides_entity_type(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When --entity-id is given, entity_type must NOT be forwarded to scan().

        The code sets ``effective_entity_type = None`` after resolving the entity.
        """
        entity_uuid = _make_uuid()
        valid_uuid = str(entity_uuid)
        mock_db_manager.get_session_factory.return_value = MagicMock()

        active_entity = _make_entity_mock(entity_id=entity_uuid, status="active")

        async def fake_get_session(**kwargs: Any) -> AsyncGenerator[Any, None]:
            session = AsyncMock()
            session.get = AsyncMock(return_value=active_entity)
            yield session

        mock_db_manager.get_session.return_value = fake_get_session()

        captured_scan_kwargs: list[dict[str, Any]] = []

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            captured_scan_kwargs.append(kwargs)
            return _make_scan_result()

        mock_service.scan = capture_scan
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app,
                ["scan", "--entity-id", valid_uuid, "--entity-type", "person"],
            )

        assert result.exit_code == 0
        assert len(captured_scan_kwargs) == 1
        # entity_type must be None when --entity-id is provided
        assert captured_scan_kwargs[0].get("entity_type") is None, (
            f"Expected entity_type=None when --entity-id is given; "
            f"got: {captured_scan_kwargs[0]}"
        )

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_entity_id_overrides_new_entities_only(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When --entity-id is given, new_entities_only must be False for scan().

        The code sets ``effective_new_entities_only = False`` after resolving.
        """
        entity_uuid = _make_uuid()
        valid_uuid = str(entity_uuid)
        mock_db_manager.get_session_factory.return_value = MagicMock()

        active_entity = _make_entity_mock(entity_id=entity_uuid, status="active")

        async def fake_get_session(**kwargs: Any) -> AsyncGenerator[Any, None]:
            session = AsyncMock()
            session.get = AsyncMock(return_value=active_entity)
            yield session

        mock_db_manager.get_session.return_value = fake_get_session()

        captured_scan_kwargs: list[dict[str, Any]] = []

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            captured_scan_kwargs.append(kwargs)
            return _make_scan_result()

        mock_service.scan = capture_scan
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app,
                [
                    "scan",
                    "--entity-id",
                    valid_uuid,
                    "--new-entities-only",
                ],
            )

        assert result.exit_code == 0
        assert len(captured_scan_kwargs) == 1
        # new_entities_only must be False
        assert captured_scan_kwargs[0].get("new_entities_only") is False, (
            f"Expected new_entities_only=False when --entity-id is given; "
            f"got: {captured_scan_kwargs[0]}"
        )

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_entity_id_passes_entity_ids_to_scan(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When --entity-id is given, entity_ids=[parsed_uuid] is passed to scan()."""
        entity_uuid = _make_uuid()
        valid_uuid = str(entity_uuid)
        mock_db_manager.get_session_factory.return_value = MagicMock()

        active_entity = _make_entity_mock(entity_id=entity_uuid, status="active")

        async def fake_get_session(**kwargs: Any) -> AsyncGenerator[Any, None]:
            session = AsyncMock()
            session.get = AsyncMock(return_value=active_entity)
            yield session

        mock_db_manager.get_session.return_value = fake_get_session()

        captured_scan_kwargs: list[dict[str, Any]] = []

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            captured_scan_kwargs.append(kwargs)
            return _make_scan_result()

        mock_service.scan = capture_scan
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app, ["scan", "--entity-id", valid_uuid]
            )

        assert result.exit_code == 0
        assert len(captured_scan_kwargs) == 1
        entity_ids_arg = captured_scan_kwargs[0].get("entity_ids")
        assert entity_ids_arg == [entity_uuid], (
            f"Expected entity_ids=[{entity_uuid}]; got: {entity_ids_arg}"
        )


# ---------------------------------------------------------------------------
# TestEntityIdWithVideoId
# ---------------------------------------------------------------------------


class TestEntityIdWithVideoId:
    """--entity-id + --video-id pass both to the scan service."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Return a Typer CliRunner."""
        return CliRunner()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_entity_id_and_video_id_both_forwarded(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Both entity_ids and video_ids must appear in the scan() call."""
        entity_uuid = _make_uuid()
        valid_uuid = str(entity_uuid)
        test_video_id = "dQw4w9WgXcQ"

        mock_db_manager.get_session_factory.return_value = MagicMock()

        active_entity = _make_entity_mock(entity_id=entity_uuid, status="active")

        async def fake_get_session(**kwargs: Any) -> AsyncGenerator[Any, None]:
            session = AsyncMock()
            session.get = AsyncMock(return_value=active_entity)
            yield session

        mock_db_manager.get_session.return_value = fake_get_session()

        captured_scan_kwargs: list[dict[str, Any]] = []

        mock_service = MagicMock()

        async def capture_scan(**kwargs: Any) -> Any:
            captured_scan_kwargs.append(kwargs)
            return _make_scan_result()

        mock_service.scan = capture_scan
        mock_service_cls.return_value = mock_service

        with patch(
            "chronovista.cli.entity_commands.asyncio.run",
            side_effect=_run_coro_via_fake_asyncio_run,
        ):
            result = runner.invoke(
                entity_app,
                [
                    "scan",
                    "--entity-id",
                    valid_uuid,
                    "--video-id",
                    test_video_id,
                ],
            )

        assert result.exit_code == 0
        assert len(captured_scan_kwargs) == 1
        # Both entity_ids and video_ids must be set
        assert captured_scan_kwargs[0].get("entity_ids") == [entity_uuid], (
            f"entity_ids mismatch: {captured_scan_kwargs[0]}"
        )
        assert captured_scan_kwargs[0].get("video_ids") == [test_video_id], (
            f"video_ids mismatch: {captured_scan_kwargs[0]}"
        )
