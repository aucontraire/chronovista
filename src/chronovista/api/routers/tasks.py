"""Task API endpoints for background pipeline operations.

This module provides REST API endpoints for managing background tasks:
- POST /tasks - Start a new pipeline operation
- GET /tasks/{task_id} - Get task status by ID
- GET /tasks - List all tasks with optional status filter

All endpoints return RFC 7807 Problem Detail format for errors.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from chronovista.api.routers.responses import (
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from chronovista.api.schemas.tasks import BackgroundTask, TaskCreate
from chronovista.api.services.task_manager import TaskManager
from chronovista.exceptions import APIValidationError, ConflictError, NotFoundError
from chronovista.models.enums import TaskStatus
from chronovista.services.onboarding_service import OnboardingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks")

# Module-level singletons set during app lifespan
_task_manager: TaskManager | None = None
_onboarding_service: OnboardingService | None = None


def configure(
    task_manager: TaskManager,
    onboarding_service: OnboardingService,
) -> None:
    """Configure module-level singletons for dependency injection.

    Called during application startup to wire the TaskManager and
    OnboardingService instances used by all task endpoints.

    Parameters
    ----------
    task_manager : TaskManager
        The in-memory task manager singleton.
    onboarding_service : OnboardingService
        The onboarding service for dispatching pipeline operations.
    """
    global _task_manager, _onboarding_service  # noqa: PLW0603
    _task_manager = task_manager
    _onboarding_service = onboarding_service


def _get_task_manager() -> TaskManager:
    """Return the configured TaskManager or raise if not configured.

    Returns
    -------
    TaskManager
        The singleton task manager.

    Raises
    ------
    RuntimeError
        If ``configure()`` has not been called.
    """
    if _task_manager is None:
        raise RuntimeError("TaskManager not configured; call configure() first")
    return _task_manager


def _get_onboarding_service() -> OnboardingService:
    """Return the configured OnboardingService or raise if not configured.

    Returns
    -------
    OnboardingService
        The singleton onboarding service.

    Raises
    ------
    RuntimeError
        If ``configure()`` has not been called.
    """
    if _onboarding_service is None:
        raise RuntimeError(
            "OnboardingService not configured; call configure() first"
        )
    return _onboarding_service


@router.post(
    "",
    response_model=BackgroundTask,
    status_code=status.HTTP_201_CREATED,
    responses={
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
    summary="Start a pipeline operation",
)
async def create_task(body: TaskCreate) -> JSONResponse:
    """Start a new background pipeline operation.

    Validates that the operation's prerequisites are met and that no
    task of the same operation type is already running, then dispatches
    the operation via OnboardingService.

    Parameters
    ----------
    body : TaskCreate
        Request body containing the ``operation_type`` to start.

    Returns
    -------
    JSONResponse
        201 Created with the ``BackgroundTask`` payload.

    Raises
    ------
    ConflictError
        If a task with the same operation type is already queued or running (409).
    APIValidationError
        If prerequisites for the operation are not met (422).
    """
    onboarding = _get_onboarding_service()
    tm = _get_task_manager()

    try:
        task_id = await onboarding.dispatch(body.operation_type)
    except ValueError as exc:
        msg = str(exc)
        # TaskManager raises ValueError for duplicate operations
        if "already running" in msg:
            raise ConflictError(message=msg) from exc
        # OnboardingService raises ValueError for unmet prerequisites
        # and unknown operation types — return 422
        raise APIValidationError(message=msg) from exc

    task = tm.get_task(task_id)
    if task is None:
        # Should not happen, but guard defensively
        raise NotFoundError(resource_type="Task", identifier=task_id)

    return JSONResponse(
        content=task.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/{task_id}",
    response_model=BackgroundTask,
    responses={**NOT_FOUND_RESPONSE},
    summary="Get task status",
)
async def get_task(task_id: str) -> BackgroundTask:
    """Retrieve the current status of a background task.

    Parameters
    ----------
    task_id : str
        The unique identifier of the task.

    Returns
    -------
    BackgroundTask
        The task with its current status, progress, and error (if any).

    Raises
    ------
    NotFoundError
        If no task with the given ID exists (404).
    """
    tm = _get_task_manager()
    task = tm.get_task(task_id)
    if task is None:
        raise NotFoundError(resource_type="Task", identifier=task_id)
    return task


@router.get(
    "",
    response_model=dict[str, list[BackgroundTask]],
    summary="List tasks",
)
async def list_tasks(
    task_status: TaskStatus | None = Query(
        None,
        alias="status",
        description="Filter tasks by status",
    ),
) -> dict[str, list[BackgroundTask]]:
    """List all background tasks, optionally filtered by status.

    Returns tasks sorted by most recent first.

    Parameters
    ----------
    task_status : TaskStatus | None, optional
        If provided, only tasks with this status are returned.

    Returns
    -------
    dict[str, list[BackgroundTask]]
        A dict with key ``"tasks"`` containing the list of matching tasks.
    """
    tm = _get_task_manager()
    tasks = tm.list_tasks(status=task_status)
    return {"tasks": tasks}
