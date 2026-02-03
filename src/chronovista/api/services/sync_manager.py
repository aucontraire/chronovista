"""SyncManager service for tracking sync operation state in the API layer.

This module provides a singleton SyncManager class that tracks the state of
sync operations at the API layer, including operation lifecycle management,
progress tracking, and last successful sync timestamps.
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timezone
from threading import Lock
from typing import Optional, TypedDict

from chronovista.api.schemas.sync import (
    SyncOperationStatus,
    SyncOperationType,
    SyncProgress,
    SyncStarted,
    SyncStatus,
)

logger = logging.getLogger(__name__)


class _OperationState(TypedDict):
    """Internal typed dictionary for operation state."""

    operation_id: str
    operation_type: SyncOperationType
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    processed_items: int
    total_items: Optional[int]
    current_item: Optional[str]
    error_message: Optional[str]


class SyncManager:
    """Manages sync operation state for the API layer.

    This class tracks the current sync operation state, progress updates,
    and maintains history of last successful syncs per operation type.
    Thread-safe operations are ensured via a lock for async FastAPI contexts.

    Attributes
    ----------
    _current_operation : Optional[dict]
        Stores the current operation state including operation_id, type,
        status, progress, started_at, etc.
    _last_successful_sync : dict[str, datetime]
        Maps operation type to its last successful sync timestamp.

    Examples
    --------
    >>> manager = SyncManager()
    >>> started = manager.start_operation(SyncOperationType.SUBSCRIPTIONS)
    >>> manager.update_progress(processed=10, total=100)
    >>> manager.complete_operation(success=True)
    """

    def __init__(self) -> None:
        """Initialize the SyncManager with empty state."""
        self._current_operation: Optional[_OperationState] = None
        self._last_successful_sync: dict[str, datetime] = {}
        self._lock = Lock()

    def is_sync_running(self) -> bool:
        """Check if any sync operation is currently running.

        Returns
        -------
        bool
            True if a sync operation is in progress, False otherwise.
        """
        with self._lock:
            return self._current_operation is not None

    def get_current_status(self) -> SyncStatus:
        """Get the current sync status.

        Returns
        -------
        SyncStatus
            Current sync status including operation details and progress.
            Returns idle status if no operation is running.
        """
        with self._lock:
            if self._current_operation is None:
                return SyncStatus(
                    status=SyncOperationStatus.IDLE,
                    operation_type=None,
                    operation_id=None,
                    progress=None,
                    last_successful_sync=None,
                    error_message=None,
                    started_at=None,
                    completed_at=None,
                )

            op = self._current_operation
            operation_type = op["operation_type"]
            last_sync = self._last_successful_sync.get(operation_type.value)

            # Build progress if available
            progress: Optional[SyncProgress] = None
            if op["processed_items"] is not None:
                progress = SyncProgress(
                    total_items=op["total_items"],
                    processed_items=op["processed_items"],
                    current_item=op["current_item"],
                    estimated_remaining=None,
                )

            return SyncStatus(
                status=SyncOperationStatus(op["status"]),
                operation_type=op["operation_type"],
                operation_id=op["operation_id"],
                progress=progress,
                last_successful_sync=last_sync,
                error_message=op["error_message"],
                started_at=op["started_at"],
                completed_at=op["completed_at"],
            )

    def start_operation(self, operation_type: SyncOperationType) -> SyncStarted:
        """Start a new sync operation.

        Parameters
        ----------
        operation_type : SyncOperationType
            The type of sync operation to start.

        Returns
        -------
        SyncStarted
            Confirmation of the started operation including operation_id.

        Raises
        ------
        ValueError
            If a sync operation is already running.
        """
        with self._lock:
            if self._current_operation is not None:
                current_op = self._current_operation
                raise ValueError(
                    f"Sync operation already running: "
                    f"type={current_op['operation_type']}, "
                    f"operation_id={current_op['operation_id']}, "
                    f"started_at={current_op['started_at']}"
                )

            operation_id = self._generate_operation_id(operation_type)
            op_started_at = datetime.now(timezone.utc)

            self._current_operation = _OperationState(
                operation_id=operation_id,
                operation_type=operation_type,
                status=SyncOperationStatus.RUNNING.value,
                started_at=op_started_at,
                completed_at=None,
                processed_items=0,
                total_items=None,
                current_item=None,
                error_message=None,
            )

            logger.info(
                f"Started sync operation: type={operation_type.value}, "
                f"operation_id={operation_id}"
            )

            return SyncStarted(
                operation_id=operation_id,
                operation_type=operation_type,
                started_at=op_started_at,
                message="Sync started successfully",
            )

    def update_progress(
        self,
        processed: int,
        total: Optional[int] = None,
        current_item: Optional[str] = None,
    ) -> None:
        """Update the progress of the current sync operation.

        Parameters
        ----------
        processed : int
            Number of items processed so far.
        total : Optional[int]
            Total number of items to process (if known).
        current_item : Optional[str]
            Identifier of the item currently being processed.

        Raises
        ------
        RuntimeError
            If no sync operation is currently running.
        """
        with self._lock:
            if self._current_operation is None:
                raise RuntimeError("No sync operation is currently running")

            self._current_operation["processed_items"] = processed
            if total is not None:
                self._current_operation["total_items"] = total
            if current_item is not None:
                self._current_operation["current_item"] = current_item

            logger.debug(
                f"Updated sync progress: processed={processed}, "
                f"total={total}, current_item={current_item}"
            )

    def complete_operation(
        self,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """Complete the current sync operation.

        Parameters
        ----------
        success : bool
            Whether the operation completed successfully.
        error_message : Optional[str]
            Error message if the operation failed.

        Raises
        ------
        RuntimeError
            If no sync operation is currently running.
        """
        with self._lock:
            if self._current_operation is None:
                raise RuntimeError("No sync operation is currently running")

            completed_at = datetime.now(timezone.utc)
            operation_type = self._current_operation["operation_type"]
            operation_id = self._current_operation["operation_id"]

            if success:
                self._current_operation["status"] = SyncOperationStatus.COMPLETED.value
                self._last_successful_sync[operation_type.value] = completed_at
                logger.info(
                    f"Completed sync operation successfully: "
                    f"type={operation_type.value}, operation_id={operation_id}"
                )
            else:
                self._current_operation["status"] = SyncOperationStatus.FAILED.value
                self._current_operation["error_message"] = error_message
                logger.warning(
                    f"Sync operation failed: type={operation_type.value}, "
                    f"operation_id={operation_id}, error={error_message}"
                )

            self._current_operation["completed_at"] = completed_at

            # Clear current operation after marking complete
            self._current_operation = None

    def _generate_operation_id(self, operation_type: SyncOperationType) -> str:
        """Generate a unique operation ID.

        Format: {type}_{timestamp}_{random}
        - Timestamp: YYYYMMDDTHHMMSSZ (ISO basic format, UTC)
        - Random: 6 character alphanumeric suffix

        Example: transcripts_20260203T143052Z_a7b3c9

        Parameters
        ----------
        operation_type : SyncOperationType
            The type of sync operation.

        Returns
        -------
        str
            Unique operation ID string.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        random_suffix = "".join(
            secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6)
        )
        return f"{operation_type.value}_{timestamp}_{random_suffix}"

    def get_last_successful_sync(
        self, operation_type: SyncOperationType
    ) -> Optional[datetime]:
        """Get the last successful sync timestamp for an operation type.

        Parameters
        ----------
        operation_type : SyncOperationType
            The type of sync operation.

        Returns
        -------
        Optional[datetime]
            The timestamp of the last successful sync, or None if never synced.
        """
        with self._lock:
            return self._last_successful_sync.get(operation_type.value)


# Module-level singleton instance for shared state across the API
sync_manager = SyncManager()
