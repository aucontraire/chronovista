"""In-memory background task manager for pipeline operations.

Provides a singleton TaskManager that tracks background pipeline
operations with per-operation-type mutual exclusion. Task history
is ephemeral and does not survive container restarts.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any, Callable, Coroutine

from chronovista.api.schemas.tasks import BackgroundTask
from chronovista.models.enums import OperationType, TaskStatus


class TaskManager:
    """In-memory background task manager.

    Tracks background pipeline operations with per-operation-type
    mutual exclusion. Task history is ephemeral and does not survive
    container restarts.

    Attributes
    ----------
    _tasks : dict[str, BackgroundTask]
        Registry of all tasks keyed by task ID.
    _running : dict[str, asyncio.Task[None]]
        Currently executing asyncio tasks keyed by task ID.
    _lock : asyncio.Lock
        Lock for safe concurrent access to task state.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}
        self._running: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        operation_type: OperationType,
        coro_factory: Callable[
            [Callable[[float], None]], Coroutine[Any, Any, dict[str, Any]]
        ],
    ) -> str:
        """Submit a background task for execution.

        Enforces mutual exclusion per ``operation_type`` — only one task
        of a given type may be queued or running at any time. Different
        operation types may execute concurrently.

        Parameters
        ----------
        operation_type : OperationType
            The pipeline operation this task represents.
        coro_factory : Callable[[Callable[[float], None]], Coroutine[Any, Any, dict[str, Any]]]
            A callable that accepts a progress callback (float 0-100) and
            returns a coroutine producing a dict of result metrics on
            success.

        Returns
        -------
        str
            The unique task ID assigned to the submitted task.

        Raises
        ------
        ValueError
            If a task with the same ``operation_type`` is already queued
            or running.
        """
        async with self._lock:
            for task in self._tasks.values():
                if task.operation_type == operation_type and task.status in (
                    TaskStatus.QUEUED,
                    TaskStatus.RUNNING,
                ):
                    raise ValueError(
                        f"Operation '{operation_type.value}' is already running"
                    )

            task_id = str(uuid.uuid4())
            task = BackgroundTask(
                id=task_id,
                operation_type=operation_type,
                status=TaskStatus.QUEUED,
                started_at=datetime.now(UTC),
            )
            self._tasks[task_id] = task

            def update_progress(pct: float) -> None:
                """Update the progress percentage for this task.

                Parameters
                ----------
                pct : float
                    Progress percentage, clamped to a maximum of 100.0.
                """
                if task_id in self._tasks:
                    self._tasks[task_id] = self._tasks[task_id].model_copy(
                        update={"progress": min(pct, 100.0)}
                    )

            self._running[task_id] = asyncio.create_task(
                self._run(task_id, coro_factory(update_progress))
            )
            return task_id

    async def _run(
        self, task_id: str, coro: Coroutine[Any, Any, dict[str, Any]]
    ) -> None:
        """Execute a background task and update its status on completion.

        Transitions the task from QUEUED to RUNNING, then to COMPLETED
        or FAILED depending on whether the coroutine succeeds or raises.

        Parameters
        ----------
        task_id : str
            The ID of the task to execute.
        coro : Coroutine[Any, Any, dict[str, Any]]
            The coroutine to await.
        """
        self._tasks[task_id] = self._tasks[task_id].model_copy(
            update={"status": TaskStatus.RUNNING}
        )
        try:
            await coro
            self._tasks[task_id] = self._tasks[task_id].model_copy(
                update={
                    "status": TaskStatus.COMPLETED,
                    "progress": 100.0,
                    "completed_at": datetime.now(UTC),
                }
            )
        except Exception as e:
            self._tasks[task_id] = self._tasks[task_id].model_copy(
                update={
                    "status": TaskStatus.FAILED,
                    "error": str(e),
                    "completed_at": datetime.now(UTC),
                }
            )
        finally:
            self._running.pop(task_id, None)

    def get_task(self, task_id: str) -> BackgroundTask | None:
        """Get a task by its ID.

        Parameters
        ----------
        task_id : str
            The unique identifier of the task.

        Returns
        -------
        BackgroundTask | None
            The task if found, otherwise ``None``.
        """
        return self._tasks.get(task_id)

    def list_tasks(
        self, status: TaskStatus | None = None
    ) -> list[BackgroundTask]:
        """List all tasks, optionally filtered by status.

        Results are sorted by ``started_at`` in descending order
        (most recent first).

        Parameters
        ----------
        status : TaskStatus | None, optional
            If provided, only tasks with this status are returned.

        Returns
        -------
        list[BackgroundTask]
            Matching tasks sorted most-recent-first.
        """
        tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return sorted(
            tasks,
            key=lambda t: t.started_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

    def get_running_task_for_operation(
        self, operation_type: OperationType
    ) -> BackgroundTask | None:
        """Get the currently active task for an operation type.

        A task is considered active if its status is QUEUED or RUNNING.

        Parameters
        ----------
        operation_type : OperationType
            The pipeline operation type to look up.

        Returns
        -------
        BackgroundTask | None
            The active task if one exists, otherwise ``None``.
        """
        for task in self._tasks.values():
            if task.operation_type == operation_type and task.status in (
                TaskStatus.QUEUED,
                TaskStatus.RUNNING,
            ):
                return task
        return None
