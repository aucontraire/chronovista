"""Sync operation endpoints for triggering and monitoring data synchronization.

This module provides endpoints for triggering sync operations (subscriptions,
videos, transcripts, etc.) and monitoring their status. Supports only one
concurrent sync operation at a time.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, status

from chronovista.api.deps import require_auth
from chronovista.api.routers.responses import (
    CONFLICT_RESPONSE,
    LIST_ERRORS,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from chronovista.api.schemas.sync import (
    SyncOperationType,
    SyncStartedResponse,
    SyncStatusResponse,
    TranscriptSyncRequest,
)
from chronovista.api.services.sync_manager import sync_manager
from chronovista.exceptions import ConflictError

router = APIRouter(dependencies=[Depends(require_auth)])


@router.post(
    "/sync/{operation}",
    response_model=SyncStartedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {
            "description": "Sync operation started successfully",
            "model": SyncStartedResponse,
        },
        **UNAUTHORIZED_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def trigger_sync(
    operation: SyncOperationType,
    request: Optional[TranscriptSyncRequest] = Body(default=None),
) -> SyncStartedResponse:
    """
    Trigger a sync operation.

    Starts a new sync operation of the specified type. Only one sync operation
    can run at a time. If a sync is already in progress, returns 409 Conflict.

    Parameters
    ----------
    operation : SyncOperationType
        The type of sync operation to trigger:
        - subscriptions: Sync user's YouTube subscriptions
        - videos: Sync videos from subscribed channels
        - transcripts: Sync transcripts for videos (accepts optional request body)
        - playlists: Sync user's playlists
        - topics: Sync channel topics
        - channel: Sync channel metadata
        - liked: Sync liked videos

    request : Optional[TranscriptSyncRequest]
        Optional request body for transcript sync operation. Allows specifying
        video IDs, language preferences, and force re-download option.
        Ignored for non-transcript operations.

    Returns
    -------
    SyncStartedResponse
        Contains operation details including operation_id for tracking.

    Raises
    ------
    ConflictError
        If sync already in progress (409).
    """
    # Check if sync already running
    if sync_manager.is_sync_running():
        current_status = sync_manager.get_current_status()
        raise ConflictError(
            message=(
                f"Sync already in progress "
                f"(operation: {current_status.operation_id}). "
                "Wait for completion or check status."
            ),
            details={
                "operation_id": current_status.operation_id,
                "operation_type": (
                    current_status.operation_type.value
                    if current_status.operation_type
                    else None
                ),
                "started_at": (
                    current_status.started_at.isoformat()
                    if current_status.started_at
                    else None
                ),
            },
        )

    # Start the operation
    try:
        started = sync_manager.start_operation(operation)
        # TODO: Actually trigger the sync in background task
        # For now, just track the operation start
        return SyncStartedResponse(data=started)
    except ValueError as e:
        # Should not happen if is_sync_running check passes, but handle anyway
        raise ConflictError(
            message=str(e),
            details={"reason": "concurrent_sync"},
        )


@router.get(
    "/sync/status",
    response_model=SyncStatusResponse,
    responses=LIST_ERRORS,
)
async def get_sync_status() -> SyncStatusResponse:
    """
    Get current sync operation status.

    Returns the status of the current or most recent sync operation.
    If no sync is running, returns idle status with last successful
    sync timestamps (if available).

    Returns
    -------
    SyncStatusResponse
        Current sync status including:
        - status: idle, running, completed, or failed
        - operation_type: Type of current/last operation
        - operation_id: Unique operation identifier
        - progress: Progress details if running
        - last_successful_sync: Timestamp of last success
        - error_message: Error details if failed
        - started_at: When operation started
        - completed_at: When operation completed

    Notes
    -----
    Requires authentication (handled by router dependency).
    """
    sync_status = sync_manager.get_current_status()
    return SyncStatusResponse(data=sync_status)
