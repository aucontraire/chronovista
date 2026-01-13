"""
Tests for sync command base infrastructure.

Tests SyncResult model and utility functions.
"""

from __future__ import annotations

from typing import FrozenSet
from unittest.mock import MagicMock, patch

import pytest

from chronovista.cli.sync.base import (
    SyncResult,
    check_authenticated,
    display_auth_error,
    display_error,
    display_progress_start,
    display_success,
    display_sync_results,
    display_warning,
    require_auth,
    run_sync_operation,
)


class TestSyncResult:
    """Tests for SyncResult model."""

    def test_default_values(self) -> None:
        """Test SyncResult has correct default values."""
        result = SyncResult()
        assert result.created == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.failed == 0
        assert result.errors == []

    def test_total_processed(self) -> None:
        """Test total_processed calculation."""
        result = SyncResult(created=5, updated=3, failed=2)
        assert result.total_processed == 10

    def test_total_processed_excludes_skipped(self) -> None:
        """Test total_processed excludes skipped items."""
        result = SyncResult(created=5, updated=3, failed=2, skipped=10)
        assert result.total_processed == 10  # skipped not included

    def test_total_successful(self) -> None:
        """Test total_successful calculation."""
        result = SyncResult(created=5, updated=3, failed=2)
        assert result.total_successful == 8

    def test_success_rate_all_successful(self) -> None:
        """Test success_rate when all items succeed."""
        result = SyncResult(created=5, updated=5, failed=0)
        assert result.success_rate == 100.0

    def test_success_rate_with_failures(self) -> None:
        """Test success_rate with some failures."""
        result = SyncResult(created=4, updated=4, failed=2)
        assert result.success_rate == 80.0

    def test_success_rate_empty(self) -> None:
        """Test success_rate when no items processed."""
        result = SyncResult()
        assert result.success_rate == 100.0

    def test_merge_results(self) -> None:
        """Test merging two SyncResults."""
        result1 = SyncResult(created=5, updated=3, failed=1, errors=["error1"])
        result2 = SyncResult(created=2, updated=4, failed=2, errors=["error2"])

        merged = result1.merge(result2)

        assert merged.created == 7
        assert merged.updated == 7
        assert merged.failed == 3
        assert merged.errors == ["error1", "error2"]

    def test_merge_preserves_skipped(self) -> None:
        """Test merging preserves skipped counts."""
        result1 = SyncResult(created=1, skipped=5)
        result2 = SyncResult(created=1, skipped=3)

        merged = result1.merge(result2)

        assert merged.skipped == 8

    def test_add_error(self) -> None:
        """Test add_error method."""
        result = SyncResult(created=5, failed=1)
        result.add_error("Something went wrong")

        assert result.failed == 2
        assert "Something went wrong" in result.errors


class TestCheckAuthenticated:
    """Tests for check_authenticated function."""

    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_returns_true_when_authenticated(
        self, mock_oauth: MagicMock
    ) -> None:
        """Test returns True when authenticated."""
        mock_oauth.is_authenticated.return_value = True
        assert check_authenticated() is True

    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_returns_false_when_not_authenticated(
        self, mock_oauth: MagicMock
    ) -> None:
        """Test returns False when not authenticated."""
        mock_oauth.is_authenticated.return_value = False
        assert check_authenticated() is False


class TestDisplayFunctions:
    """Tests for display utility functions."""

    @patch("chronovista.cli.sync.base.console")
    def test_display_auth_error(self, mock_console: MagicMock) -> None:
        """Test display_auth_error calls console.print with a Panel."""
        from rich.panel import Panel

        display_auth_error("Test Command")
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        # Check that it's a Panel (content check not possible with mock)
        assert isinstance(call_args, Panel)

    @patch("chronovista.cli.sync.base.console")
    def test_display_error(self, mock_console: MagicMock) -> None:
        """Test display_error shows correct message."""
        display_error("Something failed", "Test Error")
        mock_console.print.assert_called_once()

    @patch("chronovista.cli.sync.base.console")
    def test_display_warning(self, mock_console: MagicMock) -> None:
        """Test display_warning shows correct message."""
        display_warning("Be careful", "Test Warning")
        mock_console.print.assert_called_once()

    @patch("chronovista.cli.sync.base.console")
    def test_display_success(self, mock_console: MagicMock) -> None:
        """Test display_success shows correct message."""
        display_success("All good!")
        mock_console.print.assert_called_once()

    @patch("chronovista.cli.sync.base.console")
    def test_display_progress_start(self, mock_console: MagicMock) -> None:
        """Test display_progress_start shows correct message."""
        display_progress_start("Starting sync...", "Sync Topics")
        mock_console.print.assert_called_once()

    @patch("chronovista.cli.sync.base.console")
    def test_display_sync_results_success(self, mock_console: MagicMock) -> None:
        """Test display_sync_results with successful result."""
        result = SyncResult(created=5, updated=3)
        display_sync_results(result, title="Test Sync")
        assert mock_console.print.call_count >= 2  # Table + Panel

    @patch("chronovista.cli.sync.base.console")
    def test_display_sync_results_with_errors(self, mock_console: MagicMock) -> None:
        """Test display_sync_results with errors."""
        result = SyncResult(created=5, failed=2, errors=["err1", "err2"])
        display_sync_results(result, title="Test Sync")
        assert mock_console.print.call_count >= 3  # Table + Panel + Errors

    @patch("chronovista.cli.sync.base.console")
    def test_display_sync_results_no_table(self, mock_console: MagicMock) -> None:
        """Test display_sync_results without table."""
        result = SyncResult(created=5)
        display_sync_results(result, show_table=False)
        # Should only show panel, not table
        assert mock_console.print.call_count >= 1


class TestRequireAuth:
    """Tests for require_auth decorator."""

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    def test_allows_when_authenticated(
        self, mock_console: MagicMock, mock_oauth: MagicMock
    ) -> None:
        """Test decorator allows execution when authenticated."""
        mock_oauth.is_authenticated.return_value = True

        @require_auth("Test")
        def my_sync() -> str:
            return "success"

        result = my_sync()
        assert result == "success"

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    def test_blocks_when_not_authenticated(
        self, mock_console: MagicMock, mock_oauth: MagicMock
    ) -> None:
        """Test decorator blocks execution when not authenticated."""
        mock_oauth.is_authenticated.return_value = False

        @require_auth("Test")
        def my_sync() -> str:
            return "success"

        result = my_sync()
        assert result is None
        mock_console.print.assert_called_once()


class TestRunSyncOperation:
    """Tests for run_sync_operation function."""

    @patch("chronovista.cli.sync.base.console")
    def test_runs_async_function_successfully(
        self, mock_console: MagicMock
    ) -> None:
        """Test run_sync_operation executes async function."""

        async def my_async_fn() -> str:
            return "async result"

        result = run_sync_operation(my_async_fn, "Test Sync")
        assert result == "async result"

    @patch("chronovista.cli.sync.base.console")
    def test_handles_exception(self, mock_console: MagicMock) -> None:
        """Test run_sync_operation handles exceptions."""

        async def failing_fn() -> str:
            raise ValueError("Something went wrong")

        result = run_sync_operation(failing_fn, "Test Sync")
        assert result is None
        mock_console.print.assert_called_once()

    @patch("chronovista.cli.sync.base.console")
    def test_displays_error_panel_on_exception(
        self, mock_console: MagicMock
    ) -> None:
        """Test run_sync_operation displays error panel."""
        from rich.panel import Panel

        async def failing_fn() -> str:
            raise ValueError("Boom!")

        run_sync_operation(failing_fn, "My Operation")
        call_args = mock_console.print.call_args[0][0]
        # Check that it's a Panel (content check not possible with mock)
        assert isinstance(call_args, Panel)
