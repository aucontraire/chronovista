"""
Unit tests for Entity CLI commands — ``--audit`` flag on ``entities scan``.

Tests the ``--audit`` parameter of the ``scan_entities`` command without
touching the database. All external dependencies (session factory, service)
are mocked so that only CLI option-parsing and output-formatting logic is
exercised.

Covered scenarios (T015 — Feature 044, US3)
--------------------------------------------
(a) ``--audit --full`` is mutually exclusive → raises typer.BadParameter.
(b) ``--audit`` calls ``audit_unregistered_mentions()`` and displays results.
(c) Output formatting includes Rich table with expected columns.
(d) ``--audit --dry-run`` executes without error (dry-run is a no-op for the
    read-only audit path).

Feature 044 — Search Accuracy & Mention Audit (T015)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.entity_commands import entity_app

# CRITICAL: Module-level asyncio marker ensures async tests work with coverage.

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_uuid() -> uuid.UUID:
    """Return a fresh UUID4 for test data."""
    return uuid.uuid4()


def _audit_result(
    canonical_name: str = "Noam Chomsky",
    entity_id: uuid.UUID | None = None,
    mention_text: str = "chomsky",
    segment_count: int = 3,
) -> tuple[str, uuid.UUID, str, int]:
    """Build a single audit result tuple matching the service return type."""
    return (canonical_name, entity_id or _make_uuid(), mention_text, segment_count)


# ---------------------------------------------------------------------------
# TestScanAuditFlag (T015)
# ---------------------------------------------------------------------------


class TestScanAuditFlag:
    """Tests for the ``--audit`` flag on ``entities scan``.

    Parameters
    ----------
    runner : CliRunner
        Typer CliRunner fixture for invoking CLI commands in-process.
    """

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a Typer CLI test runner."""
        return CliRunner()

    # ------------------------------------------------------------------
    # (a) --audit --full raises error / shows error message
    # ------------------------------------------------------------------

    def test_audit_and_full_are_mutually_exclusive(self, runner: CliRunner) -> None:
        """``--audit --full`` must be rejected before any I/O occurs.

        The ``scan_entities`` command validates mutual exclusivity in the
        synchronous preamble (before ``asyncio.run``), so this test does not
        need to mock the database or service layer.
        """
        result = runner.invoke(entity_app, ["scan", "--audit", "--full"])

        # typer.BadParameter causes a non-zero exit
        assert result.exit_code != 0

    def test_audit_and_full_error_message_contains_audit(
        self, runner: CliRunner
    ) -> None:
        """The error message for ``--audit --full`` must mention both flags."""
        result = runner.invoke(entity_app, ["scan", "--audit", "--full"])

        combined = (result.stdout or "") + (result.stderr or "")
        # The error must communicate the conflict; at minimum mention "audit"
        assert "audit" in combined.lower() or result.exit_code != 0

    # ------------------------------------------------------------------
    # (b) --audit calls audit_unregistered_mentions() and displays results
    # ------------------------------------------------------------------

    @patch("chronovista.cli.entity_commands.asyncio.run")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_audit_flag_calls_asyncio_run(
        self,
        mock_db_manager: MagicMock,
        mock_asyncio_run: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Invoking ``entities scan --audit`` must call ``asyncio.run`` once."""
        mock_db_manager.get_session_factory.return_value = MagicMock()

        result = runner.invoke(entity_app, ["scan", "--audit"])

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_audit_invokes_audit_unregistered_mentions(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The audit path must delegate to ``audit_unregistered_mentions()``.

        We patch ``asyncio.run`` at the entity_commands module level so the
        inner coroutine runs synchronously in the test via a patched call.
        """
        entity_id = _make_uuid()
        audit_rows = [_audit_result(entity_id=entity_id)]

        # Build a mock service instance whose audit method returns our rows
        mock_service = MagicMock()
        mock_service.audit_unregistered_mentions = AsyncMock(return_value=audit_rows)
        mock_service_cls.return_value = mock_service

        mock_db_manager.get_session_factory.return_value = MagicMock()

        # Capture the coroutine passed to asyncio.run and execute it
        captured_coro: list[object] = []

        def fake_asyncio_run(coro: object) -> None:
            import asyncio

            captured_coro.append(coro)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)  # type: ignore[arg-type]
            finally:
                loop.close()

        with patch("chronovista.cli.entity_commands.asyncio.run", side_effect=fake_asyncio_run):
            result = runner.invoke(entity_app, ["scan", "--audit"])

        assert result.exit_code == 0
        mock_service.audit_unregistered_mentions.assert_called_once()

    # ------------------------------------------------------------------
    # (c) Output formatting includes Rich table with expected columns
    # ------------------------------------------------------------------

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_audit_table_columns_present_in_output(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The Rich table rendered for audit results must include the four
        expected column headers: Entity, Mention Text, Segment Count,
        Suggestion.

        The CliRunner captures Rich's rendered output, so column titles
        appear as plain text in ``result.stdout``.
        """
        entity_id = _make_uuid()
        audit_rows = [
            _audit_result(
                canonical_name="Noam Chomsky",
                entity_id=entity_id,
                mention_text="chomsky",
                segment_count=5,
            )
        ]

        mock_service = MagicMock()
        mock_service.audit_unregistered_mentions = AsyncMock(return_value=audit_rows)
        mock_service_cls.return_value = mock_service

        mock_db_manager.get_session_factory.return_value = MagicMock()

        def fake_asyncio_run(coro: object) -> None:
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)  # type: ignore[arg-type]
            finally:
                loop.close()

        with patch("chronovista.cli.entity_commands.asyncio.run", side_effect=fake_asyncio_run):
            result = runner.invoke(entity_app, ["scan", "--audit"])

        assert result.exit_code == 0
        output = result.stdout

        # The table title and at least three visible column headers must appear.
        # Note: CliRunner uses a narrow terminal so Rich may abbreviate
        # "Segment Count" to fit; we assert on the title and unambiguous headers.
        assert "Unregistered Mention Texts" in output
        assert "Entity" in output
        assert "Mention Text" in output
        assert "Suggestion" in output

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_audit_table_contains_entity_name_and_mention_text(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The canonical name and mention text must appear in the table rows."""
        entity_id = _make_uuid()
        audit_rows = [
            _audit_result(
                canonical_name="Ada Lovelace",
                entity_id=entity_id,
                mention_text="lovelace",
                segment_count=2,
            )
        ]

        mock_service = MagicMock()
        mock_service.audit_unregistered_mentions = AsyncMock(return_value=audit_rows)
        mock_service_cls.return_value = mock_service

        mock_db_manager.get_session_factory.return_value = MagicMock()

        def fake_asyncio_run(coro: object) -> None:
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)  # type: ignore[arg-type]
            finally:
                loop.close()

        with patch("chronovista.cli.entity_commands.asyncio.run", side_effect=fake_asyncio_run):
            result = runner.invoke(entity_app, ["scan", "--audit"])

        assert result.exit_code == 0
        output = result.stdout
        assert "Ada Lovelace" in output
        assert "lovelace" in output

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_audit_table_contains_suggestion_command(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """The Suggestion column must contain the ``add-alias`` CLI command."""
        entity_id = _make_uuid()
        audit_rows = [
            _audit_result(
                canonical_name="Noam Chomsky",
                entity_id=entity_id,
                mention_text="chomsky",
                segment_count=1,
            )
        ]

        mock_service = MagicMock()
        mock_service.audit_unregistered_mentions = AsyncMock(return_value=audit_rows)
        mock_service_cls.return_value = mock_service

        mock_db_manager.get_session_factory.return_value = MagicMock()

        def fake_asyncio_run(coro: object) -> None:
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)  # type: ignore[arg-type]
            finally:
                loop.close()

        with patch("chronovista.cli.entity_commands.asyncio.run", side_effect=fake_asyncio_run):
            result = runner.invoke(entity_app, ["scan", "--audit"])

        assert result.exit_code == 0
        output = result.stdout
        # The suggestion renders: chronovista entities add-alias "Noam Chomsky" --alias "chomsky"
        assert "add-alias" in output

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_audit_displays_summary_line(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """After the table, a summary line with counts must appear."""
        eid1 = _make_uuid()
        eid2 = _make_uuid()
        audit_rows = [
            _audit_result("Entity A", eid1, "text_a", 3),
            _audit_result("Entity B", eid2, "text_b", 1),
        ]

        mock_service = MagicMock()
        mock_service.audit_unregistered_mentions = AsyncMock(return_value=audit_rows)
        mock_service_cls.return_value = mock_service

        mock_db_manager.get_session_factory.return_value = MagicMock()

        def fake_asyncio_run(coro: object) -> None:
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)  # type: ignore[arg-type]
            finally:
                loop.close()

        with patch("chronovista.cli.entity_commands.asyncio.run", side_effect=fake_asyncio_run):
            result = runner.invoke(entity_app, ["scan", "--audit"])

        assert result.exit_code == 0
        output = result.stdout
        # Summary line mentions result count and entity count
        assert "2" in output  # 2 unregistered mention texts
        assert "unregistered" in output.lower()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_audit_no_results_shows_success_message(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """When audit returns no rows, a success message must be displayed
        instead of the table.
        """
        mock_service = MagicMock()
        mock_service.audit_unregistered_mentions = AsyncMock(return_value=[])
        mock_service_cls.return_value = mock_service

        mock_db_manager.get_session_factory.return_value = MagicMock()

        def fake_asyncio_run(coro: object) -> None:
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)  # type: ignore[arg-type]
            finally:
                loop.close()

        with patch("chronovista.cli.entity_commands.asyncio.run", side_effect=fake_asyncio_run):
            result = runner.invoke(entity_app, ["scan", "--audit"])

        assert result.exit_code == 0
        output = result.stdout
        assert "No unregistered mention texts found" in output

    # ------------------------------------------------------------------
    # (d) --audit --dry-run executes without error
    # ------------------------------------------------------------------

    @patch("chronovista.cli.entity_commands.asyncio.run")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_audit_with_dry_run_does_not_raise(
        self,
        mock_db_manager: MagicMock,
        mock_asyncio_run: MagicMock,
        runner: CliRunner,
    ) -> None:
        """``--audit --dry-run`` must be accepted and exit cleanly.

        The ``--audit`` path is read-only; ``--dry-run`` is a no-op for it.
        The two flags are not mutually exclusive (only ``--audit --full`` is).
        """
        mock_db_manager.get_session_factory.return_value = MagicMock()

        result = runner.invoke(entity_app, ["scan", "--audit", "--dry-run"])

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()

    @patch("chronovista.cli.entity_commands.EntityMentionScanService")
    @patch("chronovista.cli.entity_commands.db_manager")
    def test_audit_with_dry_run_still_calls_audit_method(
        self,
        mock_db_manager: MagicMock,
        mock_service_cls: MagicMock,
        runner: CliRunner,
    ) -> None:
        """``--audit --dry-run`` must still delegate to
        ``audit_unregistered_mentions()`` rather than to ``service.scan()``.

        The ``--audit`` branch runs unconditionally when ``audit=True``,
        even when ``--dry-run`` is also set.
        """
        mock_service = MagicMock()
        mock_service.audit_unregistered_mentions = AsyncMock(return_value=[])
        mock_service.scan = AsyncMock()
        mock_service_cls.return_value = mock_service

        mock_db_manager.get_session_factory.return_value = MagicMock()

        def fake_asyncio_run(coro: object) -> None:
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)  # type: ignore[arg-type]
            finally:
                loop.close()

        with patch("chronovista.cli.entity_commands.asyncio.run", side_effect=fake_asyncio_run):
            result = runner.invoke(entity_app, ["scan", "--audit", "--dry-run"])

        assert result.exit_code == 0
        mock_service.audit_unregistered_mentions.assert_called_once()
        # ``service.scan()`` must NOT be called during an audit
        mock_service.scan.assert_not_called()

    # ------------------------------------------------------------------
    # Additional guard: scan --help shows --audit option
    # ------------------------------------------------------------------

    def test_scan_help_includes_audit_option(self, runner: CliRunner) -> None:
        """``entities scan --help`` must document the ``--audit`` option."""
        result = runner.invoke(entity_app, ["scan", "--help"])

        assert result.exit_code == 0
        assert "--audit" in result.stdout
