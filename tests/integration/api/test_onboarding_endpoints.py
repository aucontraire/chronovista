"""Integration tests for onboarding and task API endpoints.

Tests the following routes:
- GET /api/v1/onboarding/status
- POST /api/v1/tasks
- GET /api/v1/tasks/{task_id}
- GET /api/v1/tasks

Architecture notes
------------------
The tasks router uses module-level singletons (``_task_manager`` and
``_onboarding_service``) that are normally set by the FastAPI lifespan
handler in ``api/main.py``.  Because ``httpx.AsyncClient`` with
``ASGITransport`` does **not** trigger the lifespan, those singletons
remain ``None`` at test time — causing ``RuntimeError`` on the first
request.

To work around this we call ``tasks_router.configure()`` directly inside
the ``wire_task_router`` autouse fixture, which runs once per test module
and wires the shared ``TaskManager`` from the onboarding router module into
the tasks router.

The ``OnboardingService`` singleton inside the onboarding router calls
``db_manager.get_session_factory()``, which would connect to the app
database.  For the GET /onboarding/status tests we mock
``OnboardingService.get_status`` so no real DB queries are made.

For the POST /tasks and GET /tasks tests we mock
``OnboardingService.dispatch`` and inject tasks directly into the
``TaskManager._tasks`` dict, so the tests validate HTTP routing and
response structure without executing any pipeline code.

Usage
-----
::

    pytest tests/integration/api/test_onboarding_endpoints.py -v
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from chronovista.api.routers import onboarding as onboarding_router
from chronovista.api.routers import tasks as tasks_router
from chronovista.api.schemas.onboarding import OnboardingCounts, OnboardingStatus, PipelineStep
from chronovista.api.schemas.tasks import BackgroundTask
from chronovista.api.services.task_manager import TaskManager
from chronovista.models.enums import OperationType, PipelineStepStatus, TaskStatus

# CRITICAL: This line ensures async tests work with coverage tools
pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Module-level wiring
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="module")
def wire_task_router() -> Iterator[None]:
    """Wire the tasks router module-level singletons before any tests run.

    The FastAPI lifespan handler normally calls ``tasks_router.configure()``,
    but the ``async_client`` fixture uses ``ASGITransport`` which does not
    trigger the lifespan.  This fixture replicates the lifespan wiring so
    that task endpoint tests can run without a RuntimeError.

    The ``_get_onboarding_service()`` call inside ``onboarding_router``
    reaches ``db_manager.get_session_factory()``, which would open a DB
    connection.  We mock ``db_manager.get_session_factory`` for the duration
    of this module to prevent any real DB calls from that path.
    """
    # Build a fake session factory that satisfies the OnboardingService
    # constructor signature but should never be called in our tests
    # (all DB-touching methods are mocked at the service layer).
    fake_session_factory = MagicMock()

    with patch(
        "chronovista.api.routers.onboarding.db_manager"
    ) as mock_db_manager:
        mock_db_manager.get_session_factory.return_value = fake_session_factory
        # Reset any cached singleton so it picks up our mocked factory
        onboarding_router._onboarding_service = None
        service = onboarding_router._get_onboarding_service()
        tasks_router.configure(
            task_manager=onboarding_router._task_manager,
            onboarding_service=service,
        )
        yield
    # After the module scope ends, the onboarding service singleton holds a
    # reference to the fake factory — reset it so other test modules start
    # fresh if they import onboarding_router.
    onboarding_router._onboarding_service = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline_step(
    operation_type: OperationType = OperationType.SEED_REFERENCE,
    status: PipelineStepStatus = PipelineStepStatus.AVAILABLE,
) -> PipelineStep:
    """Build a minimal PipelineStep for injection into mocked status responses.

    Parameters
    ----------
    operation_type : OperationType
        The operation type for this step.
    status : PipelineStepStatus
        The status to assign.

    Returns
    -------
    PipelineStep
        A fully-populated pipeline step instance.
    """
    return PipelineStep(
        name="Seed Reference Data",
        operation_type=operation_type,
        description="Populate YouTube topic and video category reference tables.",
        status=status,
        dependencies=[],
        requires_auth=False,
        metrics={"categories": 0},
        error=None,
    )


def _make_onboarding_status(
    active_task: BackgroundTask | None = None,
) -> OnboardingStatus:
    """Build a minimal OnboardingStatus for use in mocked responses.

    Parameters
    ----------
    active_task : BackgroundTask | None
        Optional active task to include in the status.

    Returns
    -------
    OnboardingStatus
        A complete onboarding status payload.
    """
    steps = [
        _make_pipeline_step(OperationType.SEED_REFERENCE, PipelineStepStatus.AVAILABLE),
        _make_pipeline_step(OperationType.LOAD_DATA, PipelineStepStatus.AVAILABLE),
        _make_pipeline_step(OperationType.ENRICH_METADATA, PipelineStepStatus.BLOCKED),
        _make_pipeline_step(OperationType.SYNC_TRANSCRIPTS, PipelineStepStatus.BLOCKED),
        _make_pipeline_step(OperationType.NORMALIZE_TAGS, PipelineStepStatus.BLOCKED),
    ]
    return OnboardingStatus(
        steps=steps,
        is_authenticated=False,
        data_export_path="/data/takeout",
        data_export_detected=False,
        active_task=active_task,
        counts=OnboardingCounts(
            channels=0,
            videos=0,
            playlists=0,
            transcripts=0,
            categories=0,
            canonical_tags=0,
        ),
    )


def _make_background_task(
    task_id: str = "task-test-001",
    operation_type: OperationType = OperationType.SEED_REFERENCE,
    status: TaskStatus = TaskStatus.QUEUED,
) -> BackgroundTask:
    """Build a BackgroundTask for injection into the TaskManager.

    Parameters
    ----------
    task_id : str
        The unique task identifier.
    operation_type : OperationType
        The pipeline operation this task represents.
    status : TaskStatus
        The current task status.

    Returns
    -------
    BackgroundTask
        A fully-populated background task instance.
    """
    return BackgroundTask(
        id=task_id,
        operation_type=operation_type,
        status=status,
        progress=0.0,
        error=None,
        started_at=datetime.now(UTC),
        completed_at=None,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_task_manager() -> Iterator[None]:
    """Reset the module-level TaskManager singleton between tests.

    The ``onboarding`` router module owns the canonical ``_task_manager``
    instance.  Clearing its internal ``_tasks`` and ``_running`` dicts
    provides clean isolation without replacing the singleton object (which
    would break the reference already stored in the tasks router).

    Yields
    ------
    None
        Control returns to the test body after the reset.
    """
    # Clear state before the test
    onboarding_router._task_manager._tasks.clear()
    onboarding_router._task_manager._running.clear()
    yield
    # Clear state after the test as well
    onboarding_router._task_manager._tasks.clear()
    onboarding_router._task_manager._running.clear()


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/onboarding/status
# ---------------------------------------------------------------------------


class TestGetOnboardingStatus:
    """Tests for GET /api/v1/onboarding/status."""

    async def test_returns_200(self, async_client: AsyncClient) -> None:
        """GET /onboarding/status returns HTTP 200."""
        mocked_status = _make_onboarding_status()
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")
        assert response.status_code == 200

    async def test_returns_correct_top_level_structure(
        self, async_client: AsyncClient
    ) -> None:
        """GET /onboarding/status response contains all required top-level keys."""
        mocked_status = _make_onboarding_status()
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        data = response.json()
        assert "steps" in data, "Response must include 'steps'"
        assert "is_authenticated" in data, "Response must include 'is_authenticated'"
        assert "data_export_path" in data, "Response must include 'data_export_path'"
        assert "data_export_detected" in data, "Response must include 'data_export_detected'"
        assert "counts" in data, "Response must include 'counts'"
        assert "active_task" in data, "Response must include 'active_task'"

    async def test_steps_is_list_of_five(self, async_client: AsyncClient) -> None:
        """GET /onboarding/status steps field contains exactly 5 pipeline steps."""
        mocked_status = _make_onboarding_status()
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        data = response.json()
        assert isinstance(data["steps"], list), "steps must be a list"
        assert len(data["steps"]) == 5, f"Expected 5 steps, got {len(data['steps'])}"

    async def test_is_authenticated_is_bool(self, async_client: AsyncClient) -> None:
        """GET /onboarding/status is_authenticated field is a boolean."""
        mocked_status = _make_onboarding_status()
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        data = response.json()
        assert isinstance(data["is_authenticated"], bool), (
            "is_authenticated must be a bool"
        )

    async def test_data_export_path_is_string(self, async_client: AsyncClient) -> None:
        """GET /onboarding/status data_export_path field is a string."""
        mocked_status = _make_onboarding_status()
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        data = response.json()
        assert isinstance(data["data_export_path"], str), (
            "data_export_path must be a string"
        )

    async def test_data_export_detected_is_bool(self, async_client: AsyncClient) -> None:
        """GET /onboarding/status data_export_detected field is a boolean."""
        mocked_status = _make_onboarding_status()
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        data = response.json()
        assert isinstance(data["data_export_detected"], bool), (
            "data_export_detected must be a bool"
        )

    async def test_counts_has_expected_keys(self, async_client: AsyncClient) -> None:
        """GET /onboarding/status counts object contains all expected keys."""
        mocked_status = _make_onboarding_status()
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        counts = response.json()["counts"]
        expected_keys = {
            "channels", "videos", "playlists", "transcripts", "categories", "canonical_tags"
        }
        for key in expected_keys:
            assert key in counts, f"counts must include '{key}'"

    async def test_active_task_is_null_when_no_task_running(
        self, async_client: AsyncClient
    ) -> None:
        """GET /onboarding/status active_task is null when no task is running."""
        mocked_status = _make_onboarding_status(active_task=None)
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        data = response.json()
        assert data["active_task"] is None, (
            "active_task must be null when no task is running"
        )

    async def test_active_task_is_present_when_task_running(
        self, async_client: AsyncClient
    ) -> None:
        """GET /onboarding/status active_task is populated when a task is running."""
        running_task = _make_background_task(
            status=TaskStatus.RUNNING,
            operation_type=OperationType.SEED_REFERENCE,
        )
        mocked_status = _make_onboarding_status(active_task=running_task)
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        data = response.json()
        assert data["active_task"] is not None, (
            "active_task must be populated when a task is running"
        )
        assert data["active_task"]["operation_type"] == OperationType.SEED_REFERENCE.value
        assert data["active_task"]["status"] == TaskStatus.RUNNING.value

    async def test_each_step_has_required_fields(self, async_client: AsyncClient) -> None:
        """Each pipeline step in the response has all required fields."""
        mocked_status = _make_onboarding_status()
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        for i, step in enumerate(response.json()["steps"]):
            assert "name" in step, f"Step {i} missing 'name'"
            assert "operation_type" in step, f"Step {i} missing 'operation_type'"
            assert "description" in step, f"Step {i} missing 'description'"
            assert "status" in step, f"Step {i} missing 'status'"
            assert "dependencies" in step, f"Step {i} missing 'dependencies'"
            assert "requires_auth" in step, f"Step {i} missing 'requires_auth'"
            assert "metrics" in step, f"Step {i} missing 'metrics'"

    async def test_step_statuses_are_valid_enum_values(
        self, async_client: AsyncClient
    ) -> None:
        """Each pipeline step status is a valid PipelineStepStatus enum value."""
        mocked_status = _make_onboarding_status()
        valid_statuses = {s.value for s in PipelineStepStatus}
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        for step in response.json()["steps"]:
            assert step["status"] in valid_statuses, (
                f"Step status '{step['status']}' is not a valid PipelineStepStatus"
            )

    async def test_response_content_type_is_json(self, async_client: AsyncClient) -> None:
        """GET /onboarding/status returns JSON content type."""
        mocked_status = _make_onboarding_status()
        with patch(
            "chronovista.services.onboarding_service.OnboardingService.get_status",
            new_callable=AsyncMock,
            return_value=mocked_status,
        ):
            response = await async_client.get("/api/v1/onboarding/status")

        assert "application/json" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# Tests: POST /api/v1/tasks
# ---------------------------------------------------------------------------


class TestCreateTask:
    """Tests for POST /api/v1/tasks."""

    async def test_create_task_returns_201(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks returns HTTP 201 Created."""
        task_id = "test-seed-001"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.SEED_REFERENCE,
            status=TaskStatus.QUEUED,
        )
        onboarding_router._task_manager._tasks[task_id] = task

        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            return_value=task_id,
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "seed_reference"},
            )

        assert response.status_code == 201, (
            f"Expected 201 Created, got {response.status_code}: {response.text}"
        )

    async def test_create_task_returns_background_task_payload(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks response body contains required BackgroundTask fields."""
        task_id = "test-seed-002"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.SEED_REFERENCE,
            status=TaskStatus.QUEUED,
        )
        onboarding_router._task_manager._tasks[task_id] = task

        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            return_value=task_id,
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "seed_reference"},
            )

        data = response.json()
        assert "id" in data, "Response must include 'id'"
        assert "operation_type" in data, "Response must include 'operation_type'"
        assert "status" in data, "Response must include 'status'"
        assert "progress" in data, "Response must include 'progress'"

    async def test_create_task_operation_type_matches_request(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks response operation_type matches the requested value."""
        task_id = "test-seed-003"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.NORMALIZE_TAGS,
            status=TaskStatus.QUEUED,
        )
        onboarding_router._task_manager._tasks[task_id] = task

        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            return_value=task_id,
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "normalize_tags"},
            )

        data = response.json()
        assert data["operation_type"] == "normalize_tags"

    async def test_create_task_id_is_string(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks response id field is a non-empty string."""
        task_id = "test-seed-004"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.SEED_REFERENCE,
        )
        onboarding_router._task_manager._tasks[task_id] = task

        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            return_value=task_id,
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "seed_reference"},
            )

        data = response.json()
        assert isinstance(data["id"], str) and len(data["id"]) > 0, (
            "Task id must be a non-empty string"
        )

    async def test_create_task_invalid_operation_type_returns_422(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks with an unknown operation_type returns HTTP 422."""
        response = await async_client.post(
            "/api/v1/tasks",
            json={"operation_type": "not_a_real_operation"},
        )
        # FastAPI/Pydantic rejects the invalid enum value with a 422
        assert response.status_code == 422, (
            f"Expected 422 for invalid operation_type, got {response.status_code}"
        )

    async def test_create_task_missing_body_returns_422(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks with no request body returns HTTP 422."""
        response = await async_client.post("/api/v1/tasks")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tests: POST /api/v1/tasks — 409 Conflict (duplicate operation)
# ---------------------------------------------------------------------------


class TestCreateTaskConflict:
    """Tests for POST /tasks 409 Conflict behaviour.

    Verifies that submitting a second task of the same operation type while the
    first is still queued or running results in a 409 response in RFC 7807 format.
    """

    async def test_duplicate_operation_returns_409(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks returns 409 when same operation type is already running."""
        # OnboardingService.dispatch raises ValueError("already running") when
        # TaskManager rejects the submission for a duplicate type.
        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            side_effect=ValueError("Operation 'seed_reference' is already running"),
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "seed_reference"},
            )

        assert response.status_code == 409, (
            f"Expected 409 for duplicate operation, got {response.status_code}: {response.text}"
        )

    async def test_duplicate_operation_409_uses_rfc7807_format(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks 409 response uses RFC 7807 error format with code=CONFLICT."""
        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            side_effect=ValueError("Operation 'seed_reference' is already running"),
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "seed_reference"},
            )

        data = response.json()
        assert "code" in data, "RFC 7807 error must include 'code'"
        assert data["code"] == "CONFLICT", (
            f"Expected code=CONFLICT, got {data.get('code')}"
        )

    async def test_different_operation_types_can_succeed_independently(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks allows different operation types to be submitted independently.

        This test verifies that a ValueError containing "already running" only
        affects tasks of the same type — a different type does not trigger 409.
        """
        new_task_id = "test-dup-003"
        new_task = _make_background_task(
            task_id=new_task_id,
            operation_type=OperationType.NORMALIZE_TAGS,
            status=TaskStatus.QUEUED,
        )
        onboarding_router._task_manager._tasks[new_task_id] = new_task

        # NORMALIZE_TAGS dispatch succeeds (no conflict for this type)
        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            return_value=new_task_id,
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "normalize_tags"},
            )

        assert response.status_code == 201, (
            f"Different operation type should succeed, got {response.status_code}"
        )


# ---------------------------------------------------------------------------
# Tests: POST /api/v1/tasks — 422 Unmet Prerequisites
# ---------------------------------------------------------------------------


class TestCreateTaskUnmetPrerequisites:
    """Tests for POST /tasks 422 Unprocessable Entity (unmet prerequisites).

    Verifies that submitting a task whose dependencies have not been satisfied
    results in a 422 response in RFC 7807 format.
    """

    async def test_enrich_metadata_without_videos_returns_422(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks with enrich_metadata while no videos loaded returns 422.

        enrich_metadata depends on load_data.  When videos count is 0 the
        OnboardingService raises ValueError for the unmet prerequisite.
        The tasks router maps this to APIValidationError → 422.
        """
        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            side_effect=ValueError(
                "Dependency 'load_data' not satisfied for 'enrich_metadata'"
            ),
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "enrich_metadata"},
            )

        assert response.status_code == 422, (
            f"Expected 422 for unmet prerequisites, got {response.status_code}: {response.text}"
        )

    async def test_unmet_prerequisites_422_uses_rfc7807_format(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks 422 response for unmet prerequisites uses RFC 7807 format."""
        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            side_effect=ValueError(
                "Dependency 'load_data' not satisfied for 'sync_transcripts'"
            ),
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "sync_transcripts"},
            )

        data = response.json()
        assert "code" in data, "RFC 7807 error must include 'code'"
        assert data["code"] == "VALIDATION_ERROR", (
            f"Expected code=VALIDATION_ERROR, got {data.get('code')}"
        )

    async def test_sync_transcripts_without_videos_returns_422(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks with sync_transcripts while no data loaded returns 422."""
        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            side_effect=ValueError(
                "Dependency 'load_data' not satisfied for 'sync_transcripts'"
            ),
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "sync_transcripts"},
            )

        assert response.status_code == 422

    async def test_normalize_tags_without_videos_returns_422(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /tasks with normalize_tags while no data loaded returns 422."""
        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            side_effect=ValueError(
                "Dependency 'load_data' not satisfied for 'normalize_tags'"
            ),
        ):
            response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "normalize_tags"},
            )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/tasks/{task_id}
# ---------------------------------------------------------------------------


class TestGetTask:
    """Tests for GET /api/v1/tasks/{task_id}."""

    async def test_get_task_returns_200_for_existing_task(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks/{task_id} returns HTTP 200 for a known task ID."""
        task_id = "get-task-001"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.SEED_REFERENCE,
            status=TaskStatus.QUEUED,
        )
        onboarding_router._task_manager._tasks[task_id] = task

        response = await async_client.get(f"/api/v1/tasks/{task_id}")

        assert response.status_code == 200, (
            f"Expected 200 for existing task, got {response.status_code}: {response.text}"
        )

    async def test_get_task_returns_matching_task_id(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks/{task_id} response id matches the requested task_id."""
        task_id = "get-task-002"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.LOAD_DATA,
            status=TaskStatus.RUNNING,
        )
        onboarding_router._task_manager._tasks[task_id] = task

        response = await async_client.get(f"/api/v1/tasks/{task_id}")

        data = response.json()
        assert data["id"] == task_id, (
            f"Response id '{data['id']}' does not match requested '{task_id}'"
        )

    async def test_get_task_returns_correct_operation_type(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks/{task_id} response operation_type matches the created task."""
        task_id = "get-task-003"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.NORMALIZE_TAGS,
            status=TaskStatus.COMPLETED,
        )
        onboarding_router._task_manager._tasks[task_id] = task

        response = await async_client.get(f"/api/v1/tasks/{task_id}")

        data = response.json()
        assert data["operation_type"] == "normalize_tags"

    async def test_get_task_response_has_required_fields(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks/{task_id} response contains all BackgroundTask fields."""
        task_id = "get-task-004"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.SEED_REFERENCE,
            status=TaskStatus.QUEUED,
        )
        onboarding_router._task_manager._tasks[task_id] = task

        response = await async_client.get(f"/api/v1/tasks/{task_id}")

        data = response.json()
        assert "id" in data, "Response must include 'id'"
        assert "operation_type" in data, "Response must include 'operation_type'"
        assert "status" in data, "Response must include 'status'"
        assert "progress" in data, "Response must include 'progress'"

    async def test_get_task_via_create_then_fetch(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Create a task via POST /tasks then retrieve it via GET /tasks/{id}.

        This exercises the create → fetch round-trip entirely through the HTTP
        layer, using mocked dispatch so no real DB or pipeline code runs.
        """
        task_id = "round-trip-001"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.SEED_REFERENCE,
            status=TaskStatus.QUEUED,
        )

        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            return_value=task_id,
        ):
            onboarding_router._task_manager._tasks[task_id] = task

            create_response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "seed_reference"},
            )

        assert create_response.status_code == 201, (
            f"POST /tasks failed: {create_response.text}"
        )
        created_data = create_response.json()
        returned_id = created_data["id"]

        # Now fetch the created task
        get_response = await async_client.get(f"/api/v1/tasks/{returned_id}")
        assert get_response.status_code == 200, (
            f"GET /tasks/{returned_id} failed: {get_response.text}"
        )
        fetched_data = get_response.json()
        assert fetched_data["id"] == returned_id
        assert fetched_data["operation_type"] == "seed_reference"


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/tasks/{task_id} — 404 Not Found
# ---------------------------------------------------------------------------


class TestGetTaskNotFound:
    """Tests for GET /tasks/{task_id} 404 behaviour."""

    async def test_missing_task_returns_404(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks/{task_id} returns HTTP 404 for an unknown task ID."""
        response = await async_client.get("/api/v1/tasks/nonexistent-task-id-xyz")
        assert response.status_code == 404, (
            f"Expected 404 for missing task, got {response.status_code}"
        )

    async def test_missing_task_404_uses_rfc7807_format(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks/{task_id} 404 response uses RFC 7807 error format with code=NOT_FOUND."""
        response = await async_client.get("/api/v1/tasks/nonexistent-task-id-xyz")
        data = response.json()
        assert "code" in data, "RFC 7807 error must include 'code'"
        assert data["code"] == "NOT_FOUND", (
            f"Expected code=NOT_FOUND, got {data.get('code')}"
        )

    async def test_missing_task_404_detail_mentions_task(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks/{task_id} 404 detail field references the Task resource type."""
        response = await async_client.get("/api/v1/tasks/no-such-task")
        data = response.json()
        # The NotFoundError is raised with resource_type="Task"
        assert "Task" in data.get("detail", ""), (
            f"detail should mention 'Task', got: {data.get('detail')}"
        )

    async def test_random_uuid_task_returns_404(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks/{task_id} with a UUID-like ID that does not exist returns 404."""
        response = await async_client.get(
            "/api/v1/tasks/00000000-0000-0000-0000-000000000099"
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/tasks
# ---------------------------------------------------------------------------


class TestListTasks:
    """Tests for GET /api/v1/tasks."""

    async def test_list_tasks_returns_200(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks returns HTTP 200."""
        response = await async_client.get("/api/v1/tasks")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

    async def test_list_tasks_response_has_tasks_key(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks response contains a 'tasks' key with a list."""
        response = await async_client.get("/api/v1/tasks")
        data = response.json()
        assert "tasks" in data, "Response must include 'tasks' key"
        assert isinstance(data["tasks"], list), "'tasks' value must be a list"

    async def test_list_tasks_includes_created_task(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks includes a task that was previously inserted into the manager."""
        task_id = "list-tasks-001"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.SEED_REFERENCE,
            status=TaskStatus.QUEUED,
        )
        onboarding_router._task_manager._tasks[task_id] = task

        response = await async_client.get("/api/v1/tasks")
        data = response.json()

        task_ids = [t["id"] for t in data["tasks"]]
        assert task_id in task_ids, (
            f"Expected task '{task_id}' in list, got {task_ids}"
        )

    async def test_list_tasks_empty_when_no_tasks_exist(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks returns empty tasks list when no tasks have been created."""
        response = await async_client.get("/api/v1/tasks")
        data = response.json()
        assert data["tasks"] == [], (
            f"Expected empty tasks list, got {data['tasks']}"
        )

    async def test_list_tasks_status_filter_returns_matching_tasks(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks?status=queued returns only queued tasks."""
        queued_id = "filter-test-001"
        completed_id = "filter-test-002"

        onboarding_router._task_manager._tasks[queued_id] = _make_background_task(
            task_id=queued_id,
            operation_type=OperationType.SEED_REFERENCE,
            status=TaskStatus.QUEUED,
        )
        onboarding_router._task_manager._tasks[completed_id] = _make_background_task(
            task_id=completed_id,
            operation_type=OperationType.NORMALIZE_TAGS,
            status=TaskStatus.COMPLETED,
        )

        response = await async_client.get("/api/v1/tasks?status=queued")
        data = response.json()

        task_ids = [t["id"] for t in data["tasks"]]
        assert queued_id in task_ids, "Queued task must appear in filtered results"
        assert completed_id not in task_ids, (
            "Completed task must not appear when filtering for queued"
        )

    async def test_list_tasks_status_filter_completed(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks?status=completed returns only completed tasks."""
        running_id = "filter-comp-001"
        completed_id = "filter-comp-002"

        onboarding_router._task_manager._tasks[running_id] = _make_background_task(
            task_id=running_id,
            operation_type=OperationType.LOAD_DATA,
            status=TaskStatus.RUNNING,
        )
        onboarding_router._task_manager._tasks[completed_id] = _make_background_task(
            task_id=completed_id,
            operation_type=OperationType.SEED_REFERENCE,
            status=TaskStatus.COMPLETED,
        )

        response = await async_client.get("/api/v1/tasks?status=completed")
        data = response.json()

        task_ids = [t["id"] for t in data["tasks"]]
        assert completed_id in task_ids, "Completed task must appear in filtered results"
        assert running_id not in task_ids, (
            "Running task must not appear when filtering for completed"
        )

    async def test_list_tasks_invalid_status_filter_returns_422(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks?status=invalid_value returns HTTP 422."""
        response = await async_client.get("/api/v1/tasks?status=not_a_real_status")
        assert response.status_code == 422, (
            f"Expected 422 for invalid status filter, got {response.status_code}"
        )

    async def test_list_tasks_multiple_tasks_returned(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /tasks returns all tasks when multiple have been inserted."""
        task_ids = ["multi-001", "multi-002", "multi-003"]
        operation_types = [
            OperationType.SEED_REFERENCE,
            OperationType.LOAD_DATA,
            OperationType.NORMALIZE_TAGS,
        ]

        for task_id, op_type in zip(task_ids, operation_types):
            onboarding_router._task_manager._tasks[task_id] = _make_background_task(
                task_id=task_id,
                operation_type=op_type,
                status=TaskStatus.COMPLETED,
            )

        response = await async_client.get("/api/v1/tasks")
        data = response.json()

        returned_ids = [t["id"] for t in data["tasks"]]
        for expected_id in task_ids:
            assert expected_id in returned_ids, (
                f"Task '{expected_id}' missing from list response"
            )

    async def test_list_tasks_after_create_via_post(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Create a task via POST /tasks then verify it appears in GET /tasks list."""
        task_id = "list-create-001"
        task = _make_background_task(
            task_id=task_id,
            operation_type=OperationType.SEED_REFERENCE,
            status=TaskStatus.QUEUED,
        )

        with patch.object(
            tasks_router._onboarding_service,
            "dispatch",
            new_callable=AsyncMock,
            return_value=task_id,
        ):
            onboarding_router._task_manager._tasks[task_id] = task
            create_response = await async_client.post(
                "/api/v1/tasks",
                json={"operation_type": "seed_reference"},
            )

        assert create_response.status_code == 201

        list_response = await async_client.get("/api/v1/tasks")
        data = list_response.json()

        returned_ids = [t["id"] for t in data["tasks"]]
        assert task_id in returned_ids, (
            f"Newly created task '{task_id}' not found in list"
        )
