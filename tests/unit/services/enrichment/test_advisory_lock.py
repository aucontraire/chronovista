"""
Unit tests for EnrichmentLock - advisory lock mechanism.

Tests cover:
- PostgreSQL advisory lock acquisition/release
- File-based lock acquisition/release (fallback)
- Force flag behavior (override existing locks)
- Stale lock detection and cleanup
- Lock holder PID tracking
- Error handling and graceful degradation
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.services.enrichment.enrichment_service import (
    EnrichmentLock,
    LockAcquisitionError,
    LockInfo,
)

pytestmark = pytest.mark.asyncio


class TestLockInfo:
    """Test LockInfo model."""

    def test_lock_info_creation(self) -> None:
        """Test basic LockInfo creation."""
        lock_info = LockInfo(lock_type="postgresql")

        assert lock_info.lock_type == "postgresql"
        assert lock_info.pid == os.getpid()
        assert lock_info.acquired_at is not None

    def test_lock_info_file_type(self) -> None:
        """Test LockInfo with file lock type."""
        lock_info = LockInfo(lock_type="file")

        assert lock_info.lock_type == "file"


class TestLockAcquisitionError:
    """Test LockAcquisitionError exception."""

    def test_error_creation_without_pid(self) -> None:
        """Test error creation without PID."""
        error = LockAcquisitionError("Lock held by another process")

        assert error.message == "Lock held by another process"
        assert error.pid is None
        assert str(error) == "Lock held by another process"

    def test_error_creation_with_pid(self) -> None:
        """Test error creation with PID."""
        error = LockAcquisitionError("Lock held by another process", pid=12345)

        assert error.message == "Lock held by another process"
        assert error.pid == 12345
        assert str(error) == "Lock held by another process (PID: 12345)"


class TestEnrichmentLockConstants:
    """Test EnrichmentLock constants."""

    def test_lock_id_is_stable(self) -> None:
        """Test that LOCK_ID is a stable 32-bit signed integer."""
        lock_id = EnrichmentLock.LOCK_ID

        # Verify it's an integer
        assert isinstance(lock_id, int)

        # Verify it's within 32-bit signed integer range
        assert -(2**31) <= lock_id < 2**31

        # Verify it's consistent across instances
        lock2 = EnrichmentLock()
        assert EnrichmentLock.LOCK_ID == lock2.LOCK_ID

    def test_lock_file_path(self) -> None:
        """Test that LOCK_FILE is in correct location."""
        expected_path = Path.home() / ".chronovista" / "enrichment.lock"
        assert EnrichmentLock.LOCK_FILE == expected_path


class TestEnrichmentLockInitialization:
    """Test EnrichmentLock initialization."""

    def test_lock_initialization(self) -> None:
        """Test basic lock initialization."""
        lock = EnrichmentLock()

        assert lock._lock_info is None
        assert lock._has_pg_lock is False
        assert lock._has_file_lock is False
        assert lock.is_locked is False


class TestPostgreSQLAdvisoryLock:
    """Test PostgreSQL advisory lock functionality."""

    async def test_acquire_pg_lock_success(self) -> None:
        """Test successful PostgreSQL advisory lock acquisition."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        # Mock successful lock acquisition
        result = MagicMock()
        result.fetchone.return_value = (True,)
        mock_session.execute = AsyncMock(return_value=result)

        acquired = await lock._acquire_pg_lock(mock_session, force=False)

        assert acquired is True
        mock_session.execute.assert_called_once()

    async def test_acquire_pg_lock_already_held(self) -> None:
        """Test PostgreSQL advisory lock when already held."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        # Mock lock already held
        result = MagicMock()
        result.fetchone.return_value = (False,)
        mock_session.execute = AsyncMock(return_value=result)

        acquired = await lock._acquire_pg_lock(mock_session, force=False)

        assert acquired is False

    async def test_acquire_pg_lock_with_force(self) -> None:
        """Test PostgreSQL advisory lock with force flag."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        # Mock force unlock and then successful lock
        results = [
            MagicMock(),  # unlock result (ignored)
            MagicMock(fetchone=lambda: (True,)),  # lock result
        ]
        mock_session.execute = AsyncMock(side_effect=results)

        acquired = await lock._acquire_pg_lock(mock_session, force=True)

        assert acquired is True
        assert mock_session.execute.call_count == 2

    async def test_release_pg_lock(self) -> None:
        """Test PostgreSQL advisory lock release."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        await lock._release_pg_lock(mock_session)

        mock_session.execute.assert_called_once()
        # Verify unlock method was called (SQL statement is TextClause)
        assert mock_session.execute.call_count == 1

    async def test_acquire_uses_pg_lock_when_session_available(self) -> None:
        """Test that acquire() prefers PostgreSQL lock when session available."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        # Mock successful PostgreSQL lock
        result = MagicMock()
        result.fetchone.return_value = (True,)
        mock_session.execute = AsyncMock(return_value=result)

        acquired = await lock.acquire(mock_session)

        assert acquired is True
        assert lock._has_pg_lock is True
        assert lock._has_file_lock is False
        assert lock._lock_info is not None
        assert lock._lock_info.lock_type == "postgresql"


class TestFileBasedLock:
    """Test file-based lock functionality."""

    async def test_acquire_file_lock_success(self) -> None:
        """Test successful file-based lock acquisition."""
        lock = EnrichmentLock()

        with patch("os.open") as mock_open, \
             patch("os.write") as mock_write, \
             patch("os.close") as mock_close, \
             patch.object(Path, "exists", return_value=False):

            mock_open.return_value = 3  # File descriptor
            acquired = await lock._acquire_file_lock(force=False)

            assert acquired is True
            mock_open.assert_called_once()
            mock_write.assert_called_once()
            mock_close.assert_called_once_with(3)

    async def test_acquire_file_lock_already_held_process_running(self) -> None:
        """Test file lock when already held by running process."""
        lock = EnrichmentLock()

        # Mock lock file exists and process is running
        with patch.object(Path, "exists", return_value=True), \
             patch.object(lock, "get_lock_holder_pid", return_value=os.getpid()), \
             patch("os.kill") as mock_kill:

            # os.kill with signal 0 succeeds (process exists)
            mock_kill.return_value = None

            acquired = await lock._acquire_file_lock(force=False)

            assert acquired is False

    async def test_acquire_file_lock_stale_lock_cleanup(self) -> None:
        """Test stale lock detection and cleanup."""
        lock = EnrichmentLock()

        # Mock lock file exists but process is not running
        with patch.object(Path, "exists", return_value=True), \
             patch.object(lock, "get_lock_holder_pid", return_value=99999), \
             patch("os.kill", side_effect=OSError("No such process")), \
             patch.object(Path, "unlink") as mock_unlink, \
             patch("os.open") as mock_open, \
             patch("os.write"), \
             patch("os.close"):

            mock_open.return_value = 3
            acquired = await lock._acquire_file_lock(force=False)

            assert acquired is True
            mock_unlink.assert_called_once()

    async def test_acquire_file_lock_with_force(self) -> None:
        """Test file lock acquisition with force flag."""
        lock = EnrichmentLock()

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "unlink") as mock_unlink, \
             patch("os.open") as mock_open, \
             patch("os.write"), \
             patch("os.close"):

            mock_open.return_value = 3
            acquired = await lock._acquire_file_lock(force=True)

            assert acquired is True
            # Called during force cleanup
            assert mock_unlink.call_count >= 1

    async def test_release_file_lock(self) -> None:
        """Test file-based lock release."""
        lock = EnrichmentLock()

        with patch.object(Path, "exists", return_value=True), \
             patch.object(lock, "get_lock_holder_pid", return_value=os.getpid()), \
             patch.object(Path, "unlink") as mock_unlink:

            lock._release_file_lock()

            mock_unlink.assert_called_once()

    async def test_release_file_lock_owned_by_different_process(self) -> None:
        """Test that lock is not released if owned by different process."""
        lock = EnrichmentLock()

        with patch.object(Path, "exists", return_value=True), \
             patch.object(lock, "get_lock_holder_pid", return_value=99999), \
             patch.object(Path, "unlink") as mock_unlink:

            lock._release_file_lock()

            mock_unlink.assert_not_called()

    def test_get_lock_holder_pid_success(self) -> None:
        """Test retrieving lock holder PID from file."""
        lock = EnrichmentLock()

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", return_value="12345"):

            pid = lock.get_lock_holder_pid()

            assert pid == 12345

    def test_get_lock_holder_pid_file_not_exists(self) -> None:
        """Test get_lock_holder_pid when file doesn't exist."""
        lock = EnrichmentLock()

        with patch.object(Path, "exists", return_value=False):
            pid = lock.get_lock_holder_pid()

            assert pid is None

    def test_get_lock_holder_pid_invalid_content(self) -> None:
        """Test get_lock_holder_pid with invalid file content."""
        lock = EnrichmentLock()

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", return_value="not_a_number"):

            pid = lock.get_lock_holder_pid()

            assert pid is None


class TestLockAcquireReleaseCycle:
    """Test complete lock acquire/release cycles."""

    async def test_acquire_and_release_pg_lock(self) -> None:
        """Test acquiring and releasing PostgreSQL lock."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        # Mock successful lock acquisition
        acquire_result = MagicMock()
        acquire_result.fetchone.return_value = (True,)
        mock_session.execute = AsyncMock(return_value=acquire_result)

        # Acquire
        acquired = await lock.acquire(mock_session)
        assert acquired is True
        assert lock.is_locked is True

        # Release
        await lock.release(mock_session)
        assert lock.is_locked is False

    async def test_acquire_and_release_file_lock(self) -> None:
        """Test acquiring and releasing file-based lock."""
        lock = EnrichmentLock()

        with patch("os.open") as mock_open, \
             patch("os.write"), \
             patch("os.close"), \
             patch.object(Path, "exists", side_effect=[False, True]), \
             patch.object(lock, "get_lock_holder_pid", return_value=os.getpid()), \
             patch.object(Path, "unlink") as mock_unlink:

            mock_open.return_value = 3

            # Acquire (no session = file lock)
            acquired = await lock.acquire(session=None)
            assert acquired is True
            # Check lock state after acquire
            acquired_state = lock.is_locked
            assert acquired_state is True
            assert lock._has_file_lock is True

            # Release
            await lock.release()
            # Check lock state after release
            released_state = lock.is_locked
            assert released_state is False
            mock_unlink.assert_called_once()

    async def test_acquire_fallback_to_file_lock_on_pg_failure(self) -> None:
        """Test fallback to file lock when PostgreSQL lock fails."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        # Mock PostgreSQL lock failure
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))

        with patch("os.open") as mock_open, \
             patch("os.write"), \
             patch("os.close"), \
             patch.object(Path, "exists", return_value=False):

            mock_open.return_value = 3
            acquired = await lock.acquire(mock_session)

            assert acquired is True
            assert lock._has_pg_lock is False
            assert lock._has_file_lock is True
            assert lock._lock_info is not None
            assert lock._lock_info.lock_type == "file"


class TestLockForceFlag:
    """Test force flag behavior."""

    async def test_force_overrides_existing_lock(self) -> None:
        """Test that force=True overrides existing lock."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        # Mock force unlock (pg_advisory_unlock_all) and successful lock
        # The implementation also checks prerequisites, so we need a third result
        prerequisite_result = MagicMock()
        unlock_all_result = MagicMock()
        lock_result = MagicMock()
        lock_result.fetchone.return_value = (True,)
        mock_session.execute = AsyncMock(side_effect=[prerequisite_result, unlock_all_result, lock_result])

        acquired = await lock.acquire(mock_session, force=True)

        assert acquired is True
        # Called: prerequisite check, pg_advisory_unlock_all, pg_try_advisory_lock
        assert mock_session.execute.call_count == 3

    async def test_force_removes_stale_file_lock(self) -> None:
        """Test that force=True removes stale file lock."""
        lock = EnrichmentLock()

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "unlink") as mock_unlink, \
             patch("os.open") as mock_open, \
             patch("os.write"), \
             patch("os.close"):

            mock_open.return_value = 3
            acquired = await lock.acquire(session=None, force=True)

            assert acquired is True
            # Should be called once during force cleanup
            assert mock_unlink.call_count >= 1


class TestLockErrorHandling:
    """Test error handling and exceptional cases."""

    async def test_acquire_raises_error_when_lock_held(self) -> None:
        """Test that acquire() raises LockAcquisitionError when lock is held."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        # Mock lock already held
        pg_result = MagicMock()
        pg_result.fetchone.return_value = (False,)
        mock_session.execute = AsyncMock(return_value=pg_result)

        # Mock file lock also held
        with patch.object(Path, "exists", return_value=True), \
             patch.object(lock, "get_lock_holder_pid", return_value=12345), \
             patch("os.kill"):

            with pytest.raises(LockAcquisitionError) as exc_info:
                await lock.acquire(mock_session, force=False)

            assert exc_info.value.pid == 12345

    async def test_release_without_session_for_pg_lock(self) -> None:
        """Test that releasing PG lock without session handles gracefully."""
        lock = EnrichmentLock()
        lock._has_pg_lock = True
        lock._lock_info = LockInfo(lock_type="postgresql")

        # Release without session (should not crash)
        await lock.release(session=None)

        # Lock should be released (set to False even without session)
        assert lock._has_pg_lock is False
        assert lock.is_locked is False

    async def test_release_is_safe_to_call_multiple_times(self) -> None:
        """Test that release() can be called multiple times safely."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        # First release
        await lock.release(mock_session)
        assert lock.is_locked is False

        # Second release (should not crash)
        await lock.release(mock_session)
        assert lock.is_locked is False


class TestLockContextUsage:
    """Test lock usage patterns (for documentation)."""

    async def test_typical_usage_pattern(self) -> None:
        """Test typical lock usage pattern with try/finally."""
        lock = EnrichmentLock()
        mock_session = AsyncMock()

        # Mock successful acquisition
        result = MagicMock()
        result.fetchone.return_value = (True,)
        mock_session.execute = AsyncMock(return_value=result)

        try:
            acquired = await lock.acquire(mock_session)
            assert acquired is True

            # Simulate enrichment work
            pass

        finally:
            await lock.release(mock_session)

        assert lock.is_locked is False
