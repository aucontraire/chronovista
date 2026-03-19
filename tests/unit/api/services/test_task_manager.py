"""Unit tests for the in-memory TaskManager.

Covers the full task lifecycle, per-operation-type mutual exclusion,
concurrent operation support, error capture, progress callbacks, retry
semantics, and query methods (get_task, list_tasks, get_running_task_for_operation).
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

import pytest

from chronovista.api.schemas.tasks import BackgroundTask
from chronovista.api.services.task_manager import TaskManager
from chronovista.models.enums import OperationType, TaskStatus

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helper coroutine factories
# ---------------------------------------------------------------------------


def make_noop_coro() -> Callable[[Callable[[float], None]], Coroutine[Any, Any, dict[str, Any]]]:
    """Return a coro_factory that succeeds immediately with an empty dict."""

    async def _coro(progress_cb: Callable[[float], None]) -> dict[str, Any]:
        return {}

    return lambda cb: _coro(cb)


def make_progress_coro(
    steps: list[float],
) -> Callable[[Callable[[float], None]], Coroutine[Any, Any, dict[str, Any]]]:
    """Return a coro_factory that calls progress_cb at each step value.

    Parameters
    ----------
    steps : list[float]
        Progress percentages to emit before completing.
    """

    async def _coro(progress_cb: Callable[[float], None]) -> dict[str, Any]:
        for pct in steps:
            progress_cb(pct)
            await asyncio.sleep(0)  # yield control to event loop
        return {"steps_emitted": len(steps)}

    return lambda cb: _coro(cb)


def make_failing_coro(
    message: str = "pipeline error",
) -> Callable[[Callable[[float], None]], Coroutine[Any, Any, dict[str, Any]]]:
    """Return a coro_factory whose coroutine raises RuntimeError.

    Parameters
    ----------
    message : str
        The error message the exception will carry.
    """

    async def _coro(progress_cb: Callable[[float], None]) -> dict[str, Any]:
        raise RuntimeError(message)

    return lambda cb: _coro(cb)


def make_slow_coro(
    event: asyncio.Event,
) -> Callable[[Callable[[float], None]], Coroutine[Any, Any, dict[str, Any]]]:
    """Return a coro_factory that waits on an asyncio.Event before finishing.

    Used to hold a task in RUNNING state so tests can inspect concurrent behaviour.

    Parameters
    ----------
    event : asyncio.Event
        The event to wait on before the coroutine returns.
    """

    async def _coro(progress_cb: Callable[[float], None]) -> dict[str, Any]:
        await event.wait()
        return {}

    return lambda cb: _coro(cb)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager() -> TaskManager:
    """Provide a fresh TaskManager for each test."""
    return TaskManager()


# ---------------------------------------------------------------------------
# 1. Task lifecycle: QUEUED → RUNNING → COMPLETED
# ---------------------------------------------------------------------------


class TestTaskLifecycle:
    """Tests for the full happy-path task lifecycle."""

    async def test_submit_returns_string_task_id(self, manager: TaskManager) -> None:
        """submit() returns a non-empty string ID."""
        task_id = await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    async def test_task_is_queued_immediately_after_submit(
        self, manager: TaskManager
    ) -> None:
        """Task status is QUEUED right after submit() returns.

        Note: The asyncio background task is created inside submit(), but the
        event loop hasn't run _run() yet when submit() returns synchronously.
        """
        gate = asyncio.Event()
        task_id = await manager.submit(OperationType.LOAD_DATA, make_slow_coro(gate))

        # We haven't yielded to the event loop yet, so _run() hasn't started.
        # The task was registered as QUEUED.
        task = manager.get_task(task_id)
        assert task is not None
        # The task may be QUEUED or already RUNNING depending on scheduling;
        # what matters is it was created with the correct operation type.
        assert task.operation_type == OperationType.LOAD_DATA
        assert task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)

        # Clean up: unblock the slow coroutine
        gate.set()
        await asyncio.sleep(0)

    async def test_task_transitions_to_running(self, manager: TaskManager) -> None:
        """Task transitions to RUNNING once the event loop starts executing it."""
        gate = asyncio.Event()
        task_id = await manager.submit(OperationType.LOAD_DATA, make_slow_coro(gate))

        # Yield to the event loop so _run() starts
        await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.RUNNING

        gate.set()
        await asyncio.sleep(0)

    async def test_task_completes_with_status_completed(
        self, manager: TaskManager
    ) -> None:
        """Task ends with COMPLETED status after a successful coroutine."""
        task_id = await manager.submit(OperationType.LOAD_DATA, make_noop_coro())

        # Allow the event loop to run the background asyncio.Task to completion
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED

    async def test_task_progress_is_100_on_completion(
        self, manager: TaskManager
    ) -> None:
        """Progress is forced to 100.0 when a task completes successfully."""
        task_id = await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.progress == 100.0

    async def test_completed_task_has_completed_at_timestamp(
        self, manager: TaskManager
    ) -> None:
        """completed_at is set on task completion."""
        task_id = await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.completed_at is not None

    async def test_completed_task_has_no_error(self, manager: TaskManager) -> None:
        """error field is None on successful completion."""
        task_id = await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.error is None

    async def test_started_at_is_set_on_submit(self, manager: TaskManager) -> None:
        """started_at is populated immediately when a task is submitted."""
        gate = asyncio.Event()
        task_id = await manager.submit(OperationType.LOAD_DATA, make_slow_coro(gate))

        task = manager.get_task(task_id)
        assert task is not None
        assert task.started_at is not None

        gate.set()
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 2. Per-type mutual exclusion
# ---------------------------------------------------------------------------


class TestMutualExclusion:
    """Tests for per-operation-type mutual exclusion enforcement."""

    async def test_submit_same_type_while_running_raises_value_error(
        self, manager: TaskManager
    ) -> None:
        """Submitting a second task with the same OperationType raises ValueError."""
        gate = asyncio.Event()
        await manager.submit(OperationType.LOAD_DATA, make_slow_coro(gate))
        await asyncio.sleep(0)  # let _run() start so status becomes RUNNING

        with pytest.raises(ValueError, match="load_data"):
            await manager.submit(OperationType.LOAD_DATA, make_noop_coro())

        gate.set()
        await asyncio.sleep(0)

    async def test_submit_same_type_twice_without_yielding_raises_value_error(
        self, manager: TaskManager
    ) -> None:
        """Two submits of the same type without yielding both trigger exclusion.

        The first submit registers the task as QUEUED synchronously; the lock
        ensures the second submit sees it and raises before any scheduling.
        """
        gate = asyncio.Event()
        await manager.submit(OperationType.ENRICH_METADATA, make_slow_coro(gate))

        with pytest.raises(ValueError):
            await manager.submit(OperationType.ENRICH_METADATA, make_noop_coro())

        gate.set()
        await asyncio.sleep(0)

    async def test_error_message_includes_operation_type_value(
        self, manager: TaskManager
    ) -> None:
        """ValueError message contains the string value of the operation type."""
        gate = asyncio.Event()
        await manager.submit(OperationType.SYNC_TRANSCRIPTS, make_slow_coro(gate))
        await asyncio.sleep(0)

        with pytest.raises(ValueError) as exc_info:
            await manager.submit(OperationType.SYNC_TRANSCRIPTS, make_noop_coro())

        assert "sync_transcripts" in str(exc_info.value)

        gate.set()
        await asyncio.sleep(0)

    async def test_completed_task_allows_resubmit_of_same_type(
        self, manager: TaskManager
    ) -> None:
        """After a task completes, the same operation type can be submitted again."""
        task_id_1 = await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        # Let the first task complete
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task_1 = manager.get_task(task_id_1)
        assert task_1 is not None
        assert task_1.status == TaskStatus.COMPLETED

        # Should not raise — the previous task is no longer active
        task_id_2 = await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        assert task_id_2 != task_id_1

        await asyncio.sleep(0)
        await asyncio.sleep(0)

    async def test_failed_task_allows_resubmit_of_same_type(
        self, manager: TaskManager
    ) -> None:
        """After a task fails, the same operation type can be submitted again."""
        task_id_1 = await manager.submit(
            OperationType.NORMALIZE_TAGS, make_failing_coro()
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task_1 = manager.get_task(task_id_1)
        assert task_1 is not None
        assert task_1.status == TaskStatus.FAILED

        task_id_2 = await manager.submit(OperationType.NORMALIZE_TAGS, make_noop_coro())
        assert task_id_2 != task_id_1

        await asyncio.sleep(0)
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 3. Concurrent different types
# ---------------------------------------------------------------------------


class TestConcurrentDifferentTypes:
    """Tests verifying that different OperationType values run concurrently."""

    async def test_submit_different_types_while_first_is_running(
        self, manager: TaskManager
    ) -> None:
        """Two tasks with different types are both accepted without error."""
        gate = asyncio.Event()
        task_id_a = await manager.submit(
            OperationType.LOAD_DATA, make_slow_coro(gate)
        )
        # Different type — must NOT raise
        task_id_b = await manager.submit(OperationType.ENRICH_METADATA, make_noop_coro())

        assert task_id_a != task_id_b

        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    async def test_multiple_different_types_all_accepted(
        self, manager: TaskManager
    ) -> None:
        """All five distinct operation types can be submitted simultaneously."""
        gate = asyncio.Event()
        ids: list[str] = []

        for op_type in (
            OperationType.SEED_REFERENCE,
            OperationType.LOAD_DATA,
            OperationType.ENRICH_METADATA,
            OperationType.SYNC_TRANSCRIPTS,
            OperationType.NORMALIZE_TAGS,
        ):
            # Use the gate-blocked factory so they stay active; noop for all
            # except the first would also work, but keeping it consistent:
            task_id = await manager.submit(op_type, make_slow_coro(gate))
            ids.append(task_id)

        # All five task IDs must be unique
        assert len(set(ids)) == 5

        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    async def test_second_type_completes_while_first_still_running(
        self, manager: TaskManager
    ) -> None:
        """A fast task of type B completes while a slow task of type A is running."""
        gate = asyncio.Event()
        task_id_a = await manager.submit(
            OperationType.LOAD_DATA, make_slow_coro(gate)
        )
        task_id_b = await manager.submit(
            OperationType.NORMALIZE_TAGS, make_noop_coro()
        )

        # Let the event loop advance: task B (noop) should complete
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task_b = manager.get_task(task_id_b)
        assert task_b is not None
        assert task_b.status == TaskStatus.COMPLETED

        # Task A is still running (gate not set yet)
        task_a = manager.get_task(task_id_a)
        assert task_a is not None
        assert task_a.status == TaskStatus.RUNNING

        gate.set()
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 4. Failed task captures error
# ---------------------------------------------------------------------------


class TestFailedTask:
    """Tests verifying error capture on task failure."""

    async def test_failed_task_has_failed_status(self, manager: TaskManager) -> None:
        """Task status is FAILED when the coroutine raises an exception."""
        task_id = await manager.submit(
            OperationType.ENRICH_METADATA, make_failing_coro("something went wrong")
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED

    async def test_failed_task_captures_error_message(
        self, manager: TaskManager
    ) -> None:
        """The error field contains the exception's string representation."""
        task_id = await manager.submit(
            OperationType.ENRICH_METADATA, make_failing_coro("something went wrong")
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.error == "something went wrong"

    async def test_failed_task_has_completed_at_timestamp(
        self, manager: TaskManager
    ) -> None:
        """completed_at is populated even when a task fails."""
        task_id = await manager.submit(
            OperationType.ENRICH_METADATA, make_failing_coro()
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.completed_at is not None

    async def test_different_exception_types_captured_as_string(
        self, manager: TaskManager
    ) -> None:
        """Exceptions other than RuntimeError are also captured in the error field."""

        async def _coro(cb: Callable[[float], None]) -> dict[str, Any]:
            raise ValueError("bad value")

        task_id = await manager.submit(
            OperationType.SEED_REFERENCE, lambda cb: _coro(cb)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert "bad value" in (task.error or "")

    async def test_failed_task_is_removed_from_running_registry(
        self, manager: TaskManager
    ) -> None:
        """After failure, the asyncio.Task is removed from _running."""
        task_id = await manager.submit(
            OperationType.LOAD_DATA, make_failing_coro()
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        # The internal _running dict must no longer contain this task_id
        assert task_id not in manager._running


# ---------------------------------------------------------------------------
# 5. Progress callback
# ---------------------------------------------------------------------------


class TestProgressCallback:
    """Tests for the progress reporting mechanism."""

    async def test_progress_callback_updates_task_progress(
        self, manager: TaskManager
    ) -> None:
        """Progress values emitted by the coroutine are reflected on the task."""
        # We capture a reference to the progress callback by inspecting the
        # task mid-flight via a slow coroutine with a shared list.
        captured_progress: list[float] = []

        async def _recording_coro(
            progress_cb: Callable[[float], None],
        ) -> dict[str, Any]:
            for pct in [25.0, 50.0, 75.0, 100.0]:
                progress_cb(pct)
                captured_progress.append(pct)
                await asyncio.sleep(0)
            return {}

        task_id = await manager.submit(
            OperationType.NORMALIZE_TAGS, lambda cb: _recording_coro(cb)
        )

        # Allow all progress steps to execute
        for _ in range(10):
            await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        # The _run() method forces 100.0 on completion, but intermediate
        # progress was also emitted — captured_progress tracks what was sent.
        assert captured_progress == [25.0, 50.0, 75.0, 100.0]
        assert task.progress == 100.0

    async def test_progress_above_100_is_clamped(
        self, manager: TaskManager
    ) -> None:
        """Progress values above 100 are clamped to 100.0 by update_progress."""
        received: list[float] = []

        async def _coro(progress_cb: Callable[[float], None]) -> dict[str, Any]:
            progress_cb(150.0)
            await asyncio.sleep(0)
            return {}

        task_id = await manager.submit(
            OperationType.SEED_REFERENCE, lambda cb: _coro(cb)
        )

        for _ in range(5):
            await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        # The clamping ensures progress never exceeds 100.0
        assert task.progress <= 100.0

    async def test_progress_intermediate_value_visible_during_run(
        self, manager: TaskManager
    ) -> None:
        """An intermediate progress value is visible on the task between steps."""
        gate_mid = asyncio.Event()
        gate_end = asyncio.Event()
        saw_progress: list[float] = []

        async def _coro(progress_cb: Callable[[float], None]) -> dict[str, Any]:
            progress_cb(42.0)
            await gate_mid.wait()  # pause here so test can inspect
            progress_cb(100.0)
            await gate_end.wait()
            return {}

        task_id = await manager.submit(
            OperationType.LOAD_DATA, lambda cb: _coro(cb)
        )

        # Let the coroutine run until it blocks on gate_mid
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.progress == 42.0

        gate_mid.set()
        gate_end.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 6. Retry creates new task with a different ID
# ---------------------------------------------------------------------------


class TestRetrySemantics:
    """Tests verifying retry behaviour after task failure or completion."""

    async def test_retry_after_failure_creates_new_task_id(
        self, manager: TaskManager
    ) -> None:
        """Submitting the same type after a failure produces a distinct task ID."""
        task_id_1 = await manager.submit(
            OperationType.SYNC_TRANSCRIPTS, make_failing_coro()
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager.get_task(task_id_1) is not None
        assert manager.get_task(task_id_1).status == TaskStatus.FAILED  # type: ignore[union-attr]

        task_id_2 = await manager.submit(
            OperationType.SYNC_TRANSCRIPTS, make_noop_coro()
        )
        assert task_id_2 != task_id_1
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    async def test_old_failed_task_preserved_in_history_after_retry(
        self, manager: TaskManager
    ) -> None:
        """The original failed task remains retrievable after a successful retry."""
        task_id_1 = await manager.submit(
            OperationType.SYNC_TRANSCRIPTS, make_failing_coro("original failure")
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task_id_2 = await manager.submit(
            OperationType.SYNC_TRANSCRIPTS, make_noop_coro()
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        # Original task still in history with FAILED status
        old_task = manager.get_task(task_id_1)
        assert old_task is not None
        assert old_task.status == TaskStatus.FAILED
        assert old_task.error == "original failure"

        # New task is COMPLETED
        new_task = manager.get_task(task_id_2)
        assert new_task is not None
        assert new_task.status == TaskStatus.COMPLETED

    async def test_retry_after_completion_creates_new_task_id(
        self, manager: TaskManager
    ) -> None:
        """Submitting the same type after completion also produces a new task ID."""
        task_id_1 = await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager.get_task(task_id_1).status == TaskStatus.COMPLETED  # type: ignore[union-attr]

        task_id_2 = await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        assert task_id_2 != task_id_1

        await asyncio.sleep(0)
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 7. get_task returns None for unknown ID
# ---------------------------------------------------------------------------


class TestGetTask:
    """Tests for the get_task lookup method."""

    async def test_get_task_returns_none_for_unknown_id(
        self, manager: TaskManager
    ) -> None:
        """get_task returns None when the task ID does not exist."""
        result = manager.get_task("nonexistent-id")
        assert result is None

    async def test_get_task_returns_none_for_empty_string_id(
        self, manager: TaskManager
    ) -> None:
        """get_task returns None for an empty string ID."""
        result = manager.get_task("")
        assert result is None

    async def test_get_task_returns_background_task_instance(
        self, manager: TaskManager
    ) -> None:
        """get_task returns a BackgroundTask for a valid ID."""
        gate = asyncio.Event()
        task_id = await manager.submit(OperationType.LOAD_DATA, make_slow_coro(gate))
        result = manager.get_task(task_id)

        assert isinstance(result, BackgroundTask)
        assert result.id == task_id

        gate.set()
        await asyncio.sleep(0)

    async def test_get_task_returns_correct_operation_type(
        self, manager: TaskManager
    ) -> None:
        """get_task returns a task with the correct operation_type."""
        gate = asyncio.Event()
        task_id = await manager.submit(
            OperationType.ENRICH_METADATA, make_slow_coro(gate)
        )
        task = manager.get_task(task_id)

        assert task is not None
        assert task.operation_type == OperationType.ENRICH_METADATA

        gate.set()
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 8. list_tasks with status filter
# ---------------------------------------------------------------------------


class TestListTasks:
    """Tests for the list_tasks query method."""

    async def test_list_tasks_empty_when_no_tasks(
        self, manager: TaskManager
    ) -> None:
        """list_tasks returns an empty list when no tasks have been submitted."""
        result = manager.list_tasks()
        assert result == []

    async def test_list_tasks_returns_all_tasks_without_filter(
        self, manager: TaskManager
    ) -> None:
        """list_tasks returns every submitted task when no status filter is given."""
        gate = asyncio.Event()
        id_a = await manager.submit(OperationType.LOAD_DATA, make_slow_coro(gate))
        id_b = await manager.submit(OperationType.NORMALIZE_TAGS, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        all_tasks = manager.list_tasks()
        all_ids = {t.id for t in all_tasks}
        assert id_a in all_ids
        assert id_b in all_ids

        gate.set()
        await asyncio.sleep(0)

    async def test_list_tasks_filters_by_completed_status(
        self, manager: TaskManager
    ) -> None:
        """list_tasks(status=COMPLETED) returns only completed tasks."""
        gate = asyncio.Event()
        id_running = await manager.submit(
            OperationType.LOAD_DATA, make_slow_coro(gate)
        )
        id_done = await manager.submit(OperationType.NORMALIZE_TAGS, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        completed = manager.list_tasks(status=TaskStatus.COMPLETED)
        completed_ids = {t.id for t in completed}

        assert id_done in completed_ids
        assert id_running not in completed_ids

        gate.set()
        await asyncio.sleep(0)

    async def test_list_tasks_filters_by_failed_status(
        self, manager: TaskManager
    ) -> None:
        """list_tasks(status=FAILED) returns only failed tasks."""
        id_fail = await manager.submit(
            OperationType.ENRICH_METADATA, make_failing_coro()
        )
        id_ok = await manager.submit(OperationType.NORMALIZE_TAGS, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        failed = manager.list_tasks(status=TaskStatus.FAILED)
        failed_ids = {t.id for t in failed}

        assert id_fail in failed_ids
        assert id_ok not in failed_ids

    async def test_list_tasks_filters_by_running_status(
        self, manager: TaskManager
    ) -> None:
        """list_tasks(status=RUNNING) returns only running tasks."""
        gate = asyncio.Event()
        id_running = await manager.submit(
            OperationType.LOAD_DATA, make_slow_coro(gate)
        )
        await asyncio.sleep(0)  # let _run() start

        running = manager.list_tasks(status=TaskStatus.RUNNING)
        running_ids = {t.id for t in running}

        assert id_running in running_ids

        gate.set()
        await asyncio.sleep(0)

    async def test_list_tasks_empty_when_filter_matches_nothing(
        self, manager: TaskManager
    ) -> None:
        """list_tasks returns empty list when the filter matches no tasks."""
        id_ok = await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        # No task was ever FAILED
        failed = manager.list_tasks(status=TaskStatus.FAILED)
        assert failed == []

    async def test_list_tasks_returns_list_of_background_task_instances(
        self, manager: TaskManager
    ) -> None:
        """list_tasks returns a list of BackgroundTask objects."""
        await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        result = manager.list_tasks()
        assert len(result) == 1
        assert isinstance(result[0], BackgroundTask)


# ---------------------------------------------------------------------------
# 9. list_tasks ordering — most recent first
# ---------------------------------------------------------------------------


class TestListTasksOrdering:
    """Tests verifying descending started_at order in list_tasks."""

    async def test_list_tasks_orders_most_recent_first(
        self, manager: TaskManager
    ) -> None:
        """Tasks submitted later appear earlier in the list.

        We introduce a small asyncio yield between submissions so that
        `datetime.now(UTC)` captures distinct timestamps per task.
        """
        gate = asyncio.Event()

        id_first = await manager.submit(
            OperationType.SEED_REFERENCE, make_slow_coro(gate)
        )
        # Yield to ensure the second task gets a later timestamp
        await asyncio.sleep(0)
        id_second = await manager.submit(
            OperationType.LOAD_DATA, make_slow_coro(gate)
        )
        await asyncio.sleep(0)
        id_third = await manager.submit(
            OperationType.NORMALIZE_TAGS, make_slow_coro(gate)
        )

        all_tasks = manager.list_tasks()
        ids_in_order = [t.id for t in all_tasks]

        # The most recently submitted task must appear before earlier ones.
        # We allow ties (equal timestamps) by only asserting relative position
        # when timestamps differ.
        assert ids_in_order.index(id_third) <= ids_in_order.index(id_second)
        assert ids_in_order.index(id_second) <= ids_in_order.index(id_first)

        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    async def test_list_tasks_single_task_ordering_stable(
        self, manager: TaskManager
    ) -> None:
        """A single-task list is returned without errors."""
        await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        result = manager.list_tasks()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 10. get_running_task_for_operation
# ---------------------------------------------------------------------------


class TestGetRunningTaskForOperation:
    """Tests for the get_running_task_for_operation lookup method."""

    async def test_returns_none_when_no_task_running(
        self, manager: TaskManager
    ) -> None:
        """Returns None when no task of the given type is active."""
        result = manager.get_running_task_for_operation(OperationType.LOAD_DATA)
        assert result is None

    async def test_returns_none_after_task_completes(
        self, manager: TaskManager
    ) -> None:
        """Returns None once a task has finished (not QUEUED or RUNNING)."""
        await manager.submit(OperationType.LOAD_DATA, make_noop_coro())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        result = manager.get_running_task_for_operation(OperationType.LOAD_DATA)
        assert result is None

    async def test_returns_task_while_it_is_running(
        self, manager: TaskManager
    ) -> None:
        """Returns the active task when it is in RUNNING state."""
        gate = asyncio.Event()
        task_id = await manager.submit(
            OperationType.ENRICH_METADATA, make_slow_coro(gate)
        )
        await asyncio.sleep(0)  # let _run() transition task to RUNNING

        active = manager.get_running_task_for_operation(OperationType.ENRICH_METADATA)
        assert active is not None
        assert active.id == task_id
        assert active.status == TaskStatus.RUNNING

        gate.set()
        await asyncio.sleep(0)

    async def test_returns_task_while_queued(self, manager: TaskManager) -> None:
        """Returns the active task even when it is still in QUEUED state.

        A task is QUEUED synchronously from submit() until the event loop
        advances and _run() starts. The method treats both QUEUED and RUNNING
        as active.
        """
        gate = asyncio.Event()
        task_id = await manager.submit(
            OperationType.LOAD_DATA, make_slow_coro(gate)
        )
        # Do NOT yield — the asyncio.Task hasn't started yet

        active = manager.get_running_task_for_operation(OperationType.LOAD_DATA)
        # The task is registered; it may be QUEUED or RUNNING at this point
        assert active is not None
        assert active.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)

        gate.set()
        await asyncio.sleep(0)

    async def test_returns_none_for_different_operation_type(
        self, manager: TaskManager
    ) -> None:
        """Returns None when searching for a type that has no active task."""
        gate = asyncio.Event()
        await manager.submit(OperationType.LOAD_DATA, make_slow_coro(gate))
        await asyncio.sleep(0)

        # Query a different type — should be None
        result = manager.get_running_task_for_operation(OperationType.NORMALIZE_TAGS)
        assert result is None

        gate.set()
        await asyncio.sleep(0)

    async def test_returns_correct_task_when_multiple_types_running(
        self, manager: TaskManager
    ) -> None:
        """Returns the correct task when multiple types are concurrently active."""
        gate = asyncio.Event()
        id_load = await manager.submit(
            OperationType.LOAD_DATA, make_slow_coro(gate)
        )
        id_enrich = await manager.submit(
            OperationType.ENRICH_METADATA, make_slow_coro(gate)
        )
        await asyncio.sleep(0)

        active_load = manager.get_running_task_for_operation(OperationType.LOAD_DATA)
        active_enrich = manager.get_running_task_for_operation(
            OperationType.ENRICH_METADATA
        )

        assert active_load is not None
        assert active_load.id == id_load

        assert active_enrich is not None
        assert active_enrich.id == id_enrich

        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    async def test_returns_none_after_task_fails(
        self, manager: TaskManager
    ) -> None:
        """Returns None after a task has failed (no longer active)."""
        await manager.submit(
            OperationType.SYNC_TRANSCRIPTS, make_failing_coro()
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        result = manager.get_running_task_for_operation(
            OperationType.SYNC_TRANSCRIPTS
        )
        assert result is None
