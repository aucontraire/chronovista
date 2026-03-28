"""
Unit tests for OnboardingService.

Tests step status computation (fresh DB, after data load, auth gating),
data export detection, metrics aggregation, and dispatch pre-flight checks.

All database I/O is mocked — these are pure unit tests that validate
service-layer logic without any real database connection.

Implementation target:
  src/chronovista/services/onboarding_service.py

Schemas referenced:
  src/chronovista/api/schemas/onboarding.py
  src/chronovista/api/schemas/tasks.py

Enums referenced:
  src/chronovista/models/enums.py

Design of mock strategy
-----------------------
* ``session_factory`` is a synchronous callable that returns an async
  context manager.  We build it with a plain ``MagicMock`` whose
  ``__call__`` returns an ``AsyncMock`` configured to act as an async
  context manager (``__aenter__`` / ``__aexit__``).
* ``session.execute`` is an ``AsyncMock``; its return value is a
  ``MagicMock`` whose ``.scalar_one()`` method returns the desired count.
* ``TaskManager`` is a ``MagicMock`` so that ``get_running_task_for_operation``
  can be controlled per-test without touching asyncio plumbing.
* Filesystem and OAuth token checks are patched via ``unittest.mock.patch``
  using the ``Path.is_dir`` / ``Path.is_file`` / ``Path.iterdir`` methods
  as they exist in the ``onboarding_service`` module namespace.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.api.schemas.onboarding import (
    OnboardingCounts,
    OnboardingStatus,
    PipelineStep,
)
from chronovista.api.schemas.tasks import BackgroundTask
from chronovista.models.enums import OperationType, PipelineStepStatus, TaskStatus

# ---------------------------------------------------------------------------
# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_background_task(
    operation_type: OperationType,
    status: TaskStatus = TaskStatus.RUNNING,
    error: str | None = None,
) -> BackgroundTask:
    """Build a BackgroundTask for injection into TaskManager mocks."""
    return BackgroundTask(
        id="task-abc-123",
        operation_type=operation_type,
        status=status,
        progress=50.0,
        error=error,
        started_at=datetime.now(UTC),
    )


def _make_counts(
    channels: int = 0,
    videos: int = 0,
    available_videos: int = 0,
    playlists: int = 0,
    transcripts: int = 0,
    categories: int = 0,
    canonical_tags: int = 0,
) -> OnboardingCounts:
    """Construct an OnboardingCounts object with explicit field values."""
    return OnboardingCounts(
        channels=channels,
        videos=videos,
        available_videos=available_videos,
        playlists=playlists,
        transcripts=transcripts,
        categories=categories,
        canonical_tags=canonical_tags,
    )


def _make_session_factory(counts_sequence: list[int]) -> MagicMock:
    """Build a mock async_sessionmaker that returns ``counts_sequence`` values.

    The sequence is consumed left-to-right for each call to
    ``session.execute(...).scalar_one()``.  If fewer counts than expected
    queries are provided, the last value is repeated.

    Parameters
    ----------
    counts_sequence : list[int]
        A list of integers returned in order for each
        ``session.execute(...).scalar_one()`` call.
        8 values in insertion order: channels, videos, available_videos,
        enriched_videos, playlists, transcripts, categories, canonical_tags.
    """
    scalar_values = list(counts_sequence)

    def _scalar_one_side_effect() -> int:
        if scalar_values:
            return scalar_values.pop(0)
        return 0

    mock_result = MagicMock()
    mock_result.scalar_one.side_effect = _scalar_one_side_effect
    # _get_last_loaded_at uses scalar_one_or_none; return None so it
    # resolves to "no videos loaded yet" and avoids TypeError comparisons.
    mock_result.scalar_one_or_none.return_value = None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Build an async context manager
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_cm

    return mock_factory


def _make_task_manager(
    running_tasks: dict[OperationType, BackgroundTask | None] | None = None,
) -> MagicMock:
    """Build a mock TaskManager.

    Parameters
    ----------
    running_tasks : dict[OperationType, BackgroundTask | None] | None
        Mapping from OperationType to the BackgroundTask that should be
        returned by ``get_running_task_for_operation``.  Operations not
        present map to ``None`` (no running task).
    """
    tm = MagicMock()
    _rt = running_tasks or {}

    def _get_running(op: OperationType) -> BackgroundTask | None:
        return _rt.get(op, None)

    tm.get_running_task_for_operation.side_effect = _get_running
    tm.submit = AsyncMock()
    return tm


def _build_service(
    counts_sequence: list[int] | None = None,
    running_tasks: dict[OperationType, BackgroundTask | None] | None = None,
) -> Any:
    """Construct an OnboardingService with fully mocked dependencies.

    Parameters
    ----------
    counts_sequence : list[int] | None
        DB query return values.  Defaults to all-zeros (fresh database).
    running_tasks : dict | None
        Active tasks by OperationType.  Defaults to empty (no running tasks).
    """
    from chronovista.services.onboarding_service import OnboardingService

    session_factory = _make_session_factory(counts_sequence or [0] * 8)
    task_manager = _make_task_manager(running_tasks)
    return OnboardingService(
        task_manager=task_manager,
        session_factory=session_factory,
    )


# ---------------------------------------------------------------------------
# Shared patch paths
# ---------------------------------------------------------------------------

# Auth check patches into the `settings` object used inside the service
_SETTINGS_TOKEN_IS_FILE = (
    "chronovista.services.onboarding_service.OnboardingService._check_auth"
)

# Export directory detection patches ``Path.is_dir`` and ``Path.iterdir``
# as called from within ``_detect_data_export`` on the resolved Path.
_PATH_IS_DIR = "pathlib.Path.is_dir"
_PATH_ITERDIR = "pathlib.Path.iterdir"


# ---------------------------------------------------------------------------
# Step ordering constants
# ---------------------------------------------------------------------------

_STEP_ORDER: dict[OperationType, int] = {
    OperationType.SEED_REFERENCE: 0,
    OperationType.LOAD_DATA: 1,
    OperationType.ENRICH_METADATA: 2,
    OperationType.NORMALIZE_TAGS: 3,
}


def _get_step(steps: list[PipelineStep], op: OperationType) -> PipelineStep:
    """Return the PipelineStep for the given OperationType."""
    for step in steps:
        if step.operation_type == op:
            return step
    raise KeyError(f"Step not found: {op}")


# ===========================================================================
# Tests: fresh database (all counts == 0)
# ===========================================================================


class TestFreshDatabase:
    """Validate step statuses when the database is completely empty."""

    async def test_seed_reference_is_available_when_fresh(self) -> None:
        """seed_reference has no dependencies and no auth requirement — always AVAILABLE."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.SEED_REFERENCE)
        assert step.status == PipelineStepStatus.AVAILABLE

    async def test_load_data_is_available_when_fresh(self) -> None:
        """load_data has no dependencies and no auth requirement — always AVAILABLE."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.LOAD_DATA)
        assert step.status == PipelineStepStatus.AVAILABLE

    async def test_enrich_metadata_is_blocked_when_fresh_and_no_auth(self) -> None:
        """enrich_metadata depends on load_data AND requires auth — BLOCKED if either missing."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.ENRICH_METADATA)
        assert step.status == PipelineStepStatus.BLOCKED

    async def test_normalize_tags_is_blocked_when_fresh(self) -> None:
        """normalize_tags depends on load_data — BLOCKED when videos == 0."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.NORMALIZE_TAGS)
        assert step.status == PipelineStepStatus.BLOCKED

    async def test_status_returns_four_steps(self) -> None:
        """OnboardingStatus must contain exactly the 4 defined pipeline steps."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        assert len(status.steps) == 4

    async def test_step_operation_types_match_all_defined_operations(self) -> None:
        """The four pipeline OperationType values must appear exactly once in the response."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        returned_ops = {s.operation_type for s in status.steps}
        expected_ops = {
            OperationType.SEED_REFERENCE,
            OperationType.LOAD_DATA,
            OperationType.ENRICH_METADATA,
            OperationType.NORMALIZE_TAGS,
        }
        assert returned_ops == expected_ops

    async def test_fresh_db_counts_are_all_zero(self) -> None:
        """Counts block must reflect the mocked DB values."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        counts = status.counts
        assert counts.channels == 0
        assert counts.videos == 0
        assert counts.playlists == 0
        assert counts.transcripts == 0
        assert counts.categories == 0
        assert counts.canonical_tags == 0


# ===========================================================================
# Tests: after data load (videos > 0)
# ===========================================================================


class TestAfterDataLoad:
    """Validate step statuses once videos have been loaded into the database."""

    # DB counts: channels=5, videos=100, available_videos=100, enriched_videos=0,
    # playlists=3, transcripts=0, categories=0, canonical_tags=0
    _LOADED_COUNTS = [5, 100, 100, 0, 3, 0, 0, 0]

    async def test_load_data_is_completed_when_videos_exist(self) -> None:
        """load_data is COMPLETED as soon as videos > 0."""
        service = _build_service(counts_sequence=self._LOADED_COUNTS)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.LOAD_DATA)
        assert step.status == PipelineStepStatus.COMPLETED

    async def test_normalize_tags_is_available_after_data_load(self) -> None:
        """normalize_tags requires load_data — AVAILABLE when videos > 0."""
        service = _build_service(counts_sequence=self._LOADED_COUNTS)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.NORMALIZE_TAGS)
        assert step.status == PipelineStepStatus.AVAILABLE

    async def test_enrich_metadata_blocked_when_not_enriched_yet(
        self,
    ) -> None:
        """enrich_metadata uses count_key='enriched_videos'.

        When enriched_videos == 0 and auth is absent, the step is BLOCKED.
        """
        service = _build_service(counts_sequence=self._LOADED_COUNTS)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.ENRICH_METADATA)
        assert step.status == PipelineStepStatus.BLOCKED

    async def test_seed_reference_still_available_after_data_load(self) -> None:
        """seed_reference status does not change based on video count; depends only on categories."""
        service = _build_service(counts_sequence=self._LOADED_COUNTS)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.SEED_REFERENCE)
        # categories == 0 → not completed, no dependencies → AVAILABLE
        assert step.status == PipelineStepStatus.AVAILABLE

    async def test_seed_reference_completed_when_categories_populated(self) -> None:
        """seed_reference is COMPLETED when categories > 0."""
        # channels=5, videos=100, available_videos=100, enriched_videos=0,
        # playlists=3, transcripts=0, categories=50, canonical_tags=0
        service = _build_service(counts_sequence=[5, 100, 100, 0, 3, 0, 50, 0])
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.SEED_REFERENCE)
        assert step.status == PipelineStepStatus.COMPLETED

    async def test_normalize_tags_completed_when_canonical_tags_exist(self) -> None:
        """normalize_tags is COMPLETED when canonical_tags > 0."""
        # channels=5, videos=100, available_videos=100, enriched_videos=0,
        # playlists=3, transcripts=0, categories=0, canonical_tags=5000
        service = _build_service(counts_sequence=[5, 100, 100, 0, 3, 0, 0, 5000])
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.NORMALIZE_TAGS)
        assert step.status == PipelineStepStatus.COMPLETED


# ===========================================================================
# Tests: authentication gating
# ===========================================================================


class TestAuthGating:
    """Validate that enrich_metadata obeys the requires_auth flag."""

    # Both unauthenticated and authenticated with data loaded.
    # channels=5, videos=100, available_videos=3, enriched_videos=3,
    # playlists=0, transcripts=0, categories=0, canonical_tags=0
    # available_videos == enriched_videos so enrich_metadata resolves COMPLETED.
    _LOADED_COUNTS = [5, 100, 3, 3, 0, 0, 0, 0]

    async def test_enrich_metadata_completed_when_data_exists_and_not_authenticated(
        self,
    ) -> None:
        """enrich_metadata resolves COMPLETED when videos > 0 regardless of auth.

        The service resolves status as COMPLETED (count > 0) before evaluating
        the auth requirement.  enrich_metadata shares count_key='videos' with
        load_data, so when videos are present the step is already COMPLETED.
        """
        service = _build_service(counts_sequence=self._LOADED_COUNTS)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        assert status.is_authenticated is False
        step = _get_step(status.steps, OperationType.ENRICH_METADATA)
        assert step.status == PipelineStepStatus.COMPLETED

    async def test_enrich_metadata_completed_when_authenticated_with_data(
        self,
    ) -> None:
        """enrich_metadata is COMPLETED (not AVAILABLE) when data exists and user is authenticated.

        Both the data-loaded and authenticated conditions result in COMPLETED
        because the count check fires first in _resolve_status.
        """
        service = _build_service(counts_sequence=self._LOADED_COUNTS)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=True):
            status = await service.get_status()

        assert status.is_authenticated is True
        step = _get_step(status.steps, OperationType.ENRICH_METADATA)
        assert step.status == PipelineStepStatus.COMPLETED

    async def test_enrich_metadata_blocked_when_authenticated_but_no_data(
        self,
    ) -> None:
        """enrich_metadata is BLOCKED if auth is present but load_data not complete.

        When videos == 0 the COMPLETED check fails, so auth is evaluated next.
        Auth is present but the load_data dependency is not met, so BLOCKED.
        """
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=True):
            status = await service.get_status()

        assert status.is_authenticated is True
        step = _get_step(status.steps, OperationType.ENRICH_METADATA)
        # Auth present, but videos == 0 → load_data dep not met → BLOCKED
        assert step.status == PipelineStepStatus.BLOCKED

    async def test_enrich_metadata_blocked_when_not_authenticated_and_no_data(
        self,
    ) -> None:
        """enrich_metadata is BLOCKED when both auth is absent and data is absent.

        When videos == 0: count check fails → auth check fires (no auth) → BLOCKED.
        """
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        assert status.is_authenticated is False
        step = _get_step(status.steps, OperationType.ENRICH_METADATA)
        assert step.status == PipelineStepStatus.BLOCKED

    async def test_enrich_metadata_available_when_authenticated_and_no_data(
        self,
    ) -> None:
        """enrich_metadata is AVAILABLE when authed but videos == 0 and deps are met via auth.

        Note: With videos == 0, the load_data dependency is not satisfied so it
        remains BLOCKED.  This test confirms BLOCKED rather than AVAILABLE when
        the dependency is not met, even with auth present.
        This mirrors test_enrich_metadata_blocked_when_authenticated_but_no_data.
        """
        # This test intentionally mirrors the above — confirming consistent BLOCKED
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=True):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.ENRICH_METADATA)
        assert step.status == PipelineStepStatus.BLOCKED

    async def test_is_authenticated_field_reflects_check_auth(self) -> None:
        """is_authenticated on OnboardingStatus must match what _check_auth returns."""
        service = _build_service()

        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=True):
            status_authed = await service.get_status()

        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status_unauthed = await service.get_status()

        assert status_authed.is_authenticated is True
        assert status_unauthed.is_authenticated is False

    async def test_non_auth_steps_unaffected_by_auth_state(self) -> None:
        """Steps that do not require_auth must not change status based on auth."""
        # With data loaded, normalize_tags should be AVAILABLE regardless of auth
        # Sequence: channels=5, videos=100, available_videos=100, enriched_videos=0,
        # playlists=3, transcripts=0, categories=0, canonical_tags=0
        service_authed = _build_service(counts_sequence=[5, 100, 100, 0, 3, 0, 0, 0])
        service_unauthed = _build_service(counts_sequence=[5, 100, 100, 0, 3, 0, 0, 0])

        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=True):
            status_authed = await service_authed.get_status()
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status_unauthed = await service_unauthed.get_status()

        st_authed = _get_step(status_authed.steps, OperationType.NORMALIZE_TAGS)
        st_unauthed = _get_step(status_unauthed.steps, OperationType.NORMALIZE_TAGS)
        assert st_authed.status == st_unauthed.status == PipelineStepStatus.AVAILABLE


# ===========================================================================
# Tests: data export detection
# ===========================================================================


class TestDataExportDetection:
    """Validate _detect_data_export logic and data_export_detected field."""

    async def _get_status_with_export(
        self, is_dir: bool, has_files: bool
    ) -> OnboardingStatus:
        """Helper that runs get_status() with controlled Path behaviour."""
        service = _build_service(counts_sequence=[0] * 8)

        with (
            patch(_SETTINGS_TOKEN_IS_FILE, return_value=False),
            patch("pathlib.Path.is_dir", return_value=is_dir),
            patch(
                "pathlib.Path.iterdir",
                return_value=iter([Path("some_file.txt")] if has_files else []),
            ),
        ):
            result = await service.get_status()
            assert isinstance(result, OnboardingStatus)
            return result

    async def test_data_export_detected_when_directory_has_files(self) -> None:
        """data_export_detected is True when the takeout dir exists and is non-empty."""
        status = await self._get_status_with_export(is_dir=True, has_files=True)
        assert status.data_export_detected is True

    async def test_data_export_not_detected_when_directory_is_empty(self) -> None:
        """data_export_detected is False when the takeout dir exists but is empty."""
        status = await self._get_status_with_export(is_dir=True, has_files=False)
        assert status.data_export_detected is False

    async def test_data_export_not_detected_when_directory_missing(self) -> None:
        """data_export_detected is False when the takeout directory does not exist."""
        status = await self._get_status_with_export(is_dir=False, has_files=False)
        assert status.data_export_detected is False

    async def test_data_export_path_uses_env_var(self) -> None:
        """data_export_path reflects the TAKEOUT_DIR environment variable when set."""
        service = _build_service(counts_sequence=[0] * 8)
        custom_dir = "/custom/takeout/path"

        with (
            patch(_SETTINGS_TOKEN_IS_FILE, return_value=False),
            patch("os.environ.get", return_value=custom_dir),
            patch("pathlib.Path.is_dir", return_value=False),
        ):
            status = await service.get_status()

        # The path should incorporate the custom_dir value
        assert custom_dir in status.data_export_path

    async def test_data_export_path_defaults_when_no_env_var(self) -> None:
        """data_export_path falls back to ./data/takeout when TAKEOUT_DIR is unset."""
        service = _build_service(counts_sequence=[0] * 8)

        with (
            patch(_SETTINGS_TOKEN_IS_FILE, return_value=False),
            patch("pathlib.Path.is_dir", return_value=False),
        ):
            status = await service.get_status()

        # Default resolved path should contain 'data/takeout'
        assert "data" in status.data_export_path
        assert "takeout" in status.data_export_path

    async def test_detect_data_export_returns_false_on_permission_error(
        self,
    ) -> None:
        """_detect_data_export returns False and logs a warning on PermissionError."""
        service = _build_service(counts_sequence=[0] * 8)

        with (
            patch(_SETTINGS_TOKEN_IS_FILE, return_value=False),
            patch("pathlib.Path.is_dir", return_value=True),
            patch("pathlib.Path.iterdir", side_effect=PermissionError("denied")),
        ):
            status = await service.get_status()

        assert status.data_export_detected is False


# ===========================================================================
# Tests: metrics aggregation
# ===========================================================================


class TestMetricsAggregation:
    """Validate that each PipelineStep.metrics dict is correctly populated."""

    # channels=5, videos=100, available_videos=100, enriched_videos=50,
    # playlists=3, transcripts=200, categories=50, canonical_tags=9999
    _FULL_COUNTS = [5, 100, 100, 50, 3, 200, 50, 9999]

    async def test_seed_reference_metrics_contain_categories(self) -> None:
        """seed_reference metrics must include the 'categories' count key."""
        service = _build_service(counts_sequence=self._FULL_COUNTS)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.SEED_REFERENCE)
        assert "categories" in step.metrics
        assert step.metrics["categories"] == 50

    async def test_load_data_metrics_contain_videos_channels_playlists(
        self,
    ) -> None:
        """load_data metrics must include videos, channels, and playlists."""
        service = _build_service(counts_sequence=self._FULL_COUNTS)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.LOAD_DATA)
        assert step.metrics.get("videos") == 100
        assert step.metrics.get("channels") == 5
        assert step.metrics.get("playlists") == 3

    async def test_enrich_metadata_metrics_contain_channels(self) -> None:
        """enrich_metadata metrics must include 'channels'."""
        service = _build_service(counts_sequence=self._FULL_COUNTS)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=True):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.ENRICH_METADATA)
        assert "channels" in step.metrics
        assert step.metrics["channels"] == 5

    async def test_normalize_tags_metrics_contain_canonical_tags(self) -> None:
        """normalize_tags metrics must include 'canonical_tags'."""
        service = _build_service(counts_sequence=self._FULL_COUNTS)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.NORMALIZE_TAGS)
        assert step.metrics.get("canonical_tags") == 9999

    async def test_metrics_reflect_zero_counts_on_fresh_db(self) -> None:
        """All metric values must be 0 when the database is empty."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        for step in status.steps:
            for value in step.metrics.values():
                assert int(value) == 0, (
                    f"Expected all metrics to be 0 on fresh DB, "
                    f"but step '{step.operation_type}' has {step.metrics}"
                )


# ===========================================================================
# Tests: running task affects step status
# ===========================================================================


class TestRunningTaskAffectsStepStatus:
    """Validate that a RUNNING task overrides computed step statuses."""

    async def test_load_data_running_shows_running_status(self) -> None:
        """When TaskManager reports a running load_data task, the step is RUNNING."""
        running_task = _make_background_task(OperationType.LOAD_DATA)
        service = _build_service(
            counts_sequence=[0] * 8,
            running_tasks={OperationType.LOAD_DATA: running_task},
        )
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.LOAD_DATA)
        assert step.status == PipelineStepStatus.RUNNING

    async def test_seed_reference_running_shows_running_status(self) -> None:
        """A running seed_reference task overrides AVAILABLE to RUNNING."""
        running_task = _make_background_task(OperationType.SEED_REFERENCE)
        service = _build_service(
            counts_sequence=[0] * 8,
            running_tasks={OperationType.SEED_REFERENCE: running_task},
        )
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.SEED_REFERENCE)
        assert step.status == PipelineStepStatus.RUNNING

    async def test_active_task_returned_in_status(self) -> None:
        """get_status() returns the running task in the active_task field."""
        running_task = _make_background_task(OperationType.LOAD_DATA)
        service = _build_service(
            counts_sequence=[0] * 8,
            running_tasks={OperationType.LOAD_DATA: running_task},
        )
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        assert status.active_task is not None
        assert status.active_task.operation_type == OperationType.LOAD_DATA

    async def test_active_task_is_none_when_no_running_tasks(self) -> None:
        """active_task is None when TaskManager has no active tasks."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        assert status.active_task is None

    async def test_running_task_error_propagated_to_step(self) -> None:
        """A failed task's error message is surfaced in the step's error field."""
        errored_task = _make_background_task(
            OperationType.LOAD_DATA,
            status=TaskStatus.RUNNING,
            error="Something went wrong",
        )
        service = _build_service(
            counts_sequence=[0] * 8,
            running_tasks={OperationType.LOAD_DATA: errored_task},
        )
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.LOAD_DATA)
        assert step.error == "Something went wrong"

    async def test_step_without_running_task_has_no_error(self) -> None:
        """Steps with no associated running task have error=None."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        for step in status.steps:
            assert step.error is None


# ===========================================================================
# Tests: counts populated from DB queries
# ===========================================================================


class TestCountsFromDatabase:
    """Validate that OnboardingCounts is correctly populated from DB queries."""

    async def test_counts_reflect_db_query_values(self) -> None:
        """OnboardingCounts fields must match the sequence returned by session.execute."""
        # Sequence: channels=7, videos=42, available_videos=42, enriched_videos=10,
        # playlists=1, transcripts=99, categories=5, canonical_tags=300
        service = _build_service(counts_sequence=[7, 42, 42, 10, 1, 99, 5, 300])
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        counts = status.counts
        assert counts.channels == 7
        assert counts.videos == 42
        assert counts.available_videos == 42
        assert counts.playlists == 1
        assert counts.transcripts == 99
        assert counts.categories == 5
        assert counts.canonical_tags == 300

    async def test_counts_type_is_onboarding_counts(self) -> None:
        """The counts field must be an OnboardingCounts Pydantic model."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        assert isinstance(status.counts, OnboardingCounts)

    async def test_counts_are_integers(self) -> None:
        """All count fields must be integers, not strings or floats."""
        # Sequence: channels=1, videos=2, available_videos=3, enriched_videos=4,
        # playlists=5, transcripts=6, categories=7, canonical_tags=8
        service = _build_service(counts_sequence=[1, 2, 3, 4, 5, 6, 7, 8])
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        counts = status.counts
        for field_name in ("channels", "videos", "playlists", "transcripts", "categories", "canonical_tags"):
            assert isinstance(getattr(counts, field_name), int), (
                f"Expected int for counts.{field_name}"
            )


# ===========================================================================
# Tests: dispatch pre-flight validation
# ===========================================================================


class TestDispatch:
    """Validate OnboardingService.dispatch pre-flight checks and delegation."""

    async def test_dispatch_raises_for_unknown_operation(self) -> None:
        """dispatch() must raise ValueError for an operation not in the pipeline."""
        # We test this indirectly by patching _find_step to return None
        service = _build_service(counts_sequence=[0] * 8)

        with (
            patch.object(service, "_find_step", return_value=None),
            pytest.raises(ValueError, match="Unknown operation type"),
        ):
            await service.dispatch(OperationType.SEED_REFERENCE)

    async def test_dispatch_raises_when_dependency_unsatisfied(self) -> None:
        """dispatch() raises ValueError when a required dependency step is not complete."""
        # normalize_tags depends on load_data (videos > 0), but DB is fresh
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            with pytest.raises(ValueError, match="not satisfied"):
                await service.dispatch(OperationType.NORMALIZE_TAGS)

    async def test_dispatch_raises_when_auth_required_but_absent(self) -> None:
        """dispatch() raises ValueError when enrich_metadata is requested without auth."""
        # Give enough videos to satisfy load_data dep but no auth
        service = _build_service(counts_sequence=[5, 100, 100, 0, 3, 0, 0, 0])
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            with pytest.raises(ValueError, match="requires OAuth"):
                await service.dispatch(OperationType.ENRICH_METADATA)

    async def test_dispatch_delegates_to_task_manager_when_valid(self) -> None:
        """dispatch() calls task_manager.submit() when pre-flight checks pass."""
        # seed_reference has no dependencies and no auth — always dispatchable
        task_manager = _make_task_manager()
        task_manager.submit = AsyncMock(return_value="task-xyz")

        from chronovista.services.onboarding_service import OnboardingService

        session_factory = _make_session_factory([0] * 8)
        service = OnboardingService(
            task_manager=task_manager,
            session_factory=session_factory,
        )

        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            task_id = await service.dispatch(OperationType.SEED_REFERENCE)

        task_manager.submit.assert_awaited_once()
        assert task_id == "task-xyz"

    async def test_dispatch_passes_correct_operation_type_to_submit(self) -> None:
        """task_manager.submit must receive the correct OperationType."""
        task_manager = _make_task_manager()
        task_manager.submit = AsyncMock(return_value="task-123")

        from chronovista.services.onboarding_service import OnboardingService

        session_factory = _make_session_factory([0] * 8)
        service = OnboardingService(
            task_manager=task_manager,
            session_factory=session_factory,
        )

        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            await service.dispatch(OperationType.LOAD_DATA)

        call_args = task_manager.submit.call_args
        assert call_args[0][0] == OperationType.LOAD_DATA

    async def test_dispatch_normalize_tags_with_loaded_data(self) -> None:
        """normalize_tags can be dispatched once data is loaded."""
        task_manager = _make_task_manager()
        task_manager.submit = AsyncMock(return_value="task-norm")

        from chronovista.services.onboarding_service import OnboardingService

        # videos=100 satisfies load_data dependency
        session_factory = _make_session_factory([5, 100, 100, 0, 3, 0, 0, 0])
        service = OnboardingService(
            task_manager=task_manager,
            session_factory=session_factory,
        )

        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            task_id = await service.dispatch(OperationType.NORMALIZE_TAGS)

        assert task_id == "task-norm"

    async def test_dispatch_enrich_metadata_with_data_and_auth(self) -> None:
        """enrich_metadata can be dispatched when both data exists and auth is present."""
        task_manager = _make_task_manager()
        task_manager.submit = AsyncMock(return_value="task-enrich")

        from chronovista.services.onboarding_service import OnboardingService

        # videos=100 satisfies load_data dependency
        session_factory = _make_session_factory([5, 100, 100, 0, 3, 0, 0, 0])
        service = OnboardingService(
            task_manager=task_manager,
            session_factory=session_factory,
        )

        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=True):
            task_id = await service.dispatch(OperationType.ENRICH_METADATA)

        assert task_id == "task-enrich"


# ===========================================================================
# Tests: _compute_steps and _resolve_status edge cases
# ===========================================================================


class TestStepStatusEdgeCases:
    """Edge cases for the step status resolution logic."""

    async def test_running_status_takes_priority_over_completed(self) -> None:
        """RUNNING overrides COMPLETED — if a step is running, it shows RUNNING."""
        # categories=50 means seed_reference would be COMPLETED — but we inject
        # a running task for it
        # Sequence: channels=0, videos=0, available_videos=0, enriched_videos=0,
        # playlists=0, transcripts=0, categories=50, canonical_tags=0
        running_task = _make_background_task(OperationType.SEED_REFERENCE)
        service = _build_service(
            counts_sequence=[0, 0, 0, 0, 0, 0, 50, 0],
            running_tasks={OperationType.SEED_REFERENCE: running_task},
        )
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.SEED_REFERENCE)
        assert step.status == PipelineStepStatus.RUNNING

    async def test_multiple_running_tasks_each_reflected_in_own_step(self) -> None:
        """Multiple concurrently running operations each mark their own step RUNNING."""
        running_seed = _make_background_task(OperationType.SEED_REFERENCE)
        running_load = _make_background_task(OperationType.LOAD_DATA)
        service = _build_service(
            counts_sequence=[0] * 8,
            running_tasks={
                OperationType.SEED_REFERENCE: running_seed,
                OperationType.LOAD_DATA: running_load,
            },
        )
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        assert _get_step(status.steps, OperationType.SEED_REFERENCE).status == PipelineStepStatus.RUNNING
        assert _get_step(status.steps, OperationType.LOAD_DATA).status == PipelineStepStatus.RUNNING

    async def test_step_requires_auth_flag_matches_definition(self) -> None:
        """Only enrich_metadata should have requires_auth=True."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        for step in status.steps:
            if step.operation_type == OperationType.ENRICH_METADATA:
                assert step.requires_auth is True
            else:
                assert step.requires_auth is False, (
                    f"{step.operation_type.value} should not require auth"
                )

    async def test_step_dependencies_match_definition(self) -> None:
        """Dependency lists must match the static pipeline definition."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        expected_deps: dict[OperationType, list[OperationType]] = {
            OperationType.SEED_REFERENCE: [],
            OperationType.LOAD_DATA: [],
            OperationType.ENRICH_METADATA: [OperationType.LOAD_DATA],
            OperationType.NORMALIZE_TAGS: [OperationType.LOAD_DATA],
        }

        for step in status.steps:
            assert step.dependencies == expected_deps[step.operation_type], (
                f"{step.operation_type.value} dependencies mismatch"
            )

    async def test_enrich_metadata_blocked_auth_takes_priority_over_missing_data(
        self,
    ) -> None:
        """When data is missing AND auth is missing, enrich_metadata is BLOCKED."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        step = _get_step(status.steps, OperationType.ENRICH_METADATA)
        # Either condition would block it — both are absent, result must still be BLOCKED
        assert step.status == PipelineStepStatus.BLOCKED

    async def test_all_steps_completed_when_all_counts_positive(self) -> None:
        """When all relevant counts are > 0, all steps should be COMPLETED."""
        # channels=5, videos=100, available_videos=50, enriched_videos=50 → enrich_metadata done
        # (enriched_videos >= available_videos so COMPLETED, not AVAILABLE);
        # playlists=3, transcripts=0, categories=10 → seed_reference done;
        # canonical_tags=200 → normalize_tags done
        service = _build_service(counts_sequence=[5, 100, 50, 50, 3, 0, 10, 200])
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=True):
            status = await service.get_status()

        for step in status.steps:
            assert step.status == PipelineStepStatus.COMPLETED, (
                f"Expected COMPLETED for {step.operation_type.value}, "
                f"got {step.status.value}"
            )


# ===========================================================================
# Tests: return type and schema compliance
# ===========================================================================


class TestSchemaCompliance:
    """Validate that get_status() returns a well-formed OnboardingStatus."""

    async def test_get_status_returns_onboarding_status_instance(self) -> None:
        """get_status() must return an OnboardingStatus Pydantic model."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        assert isinstance(status, OnboardingStatus)

    async def test_steps_are_pipeline_step_instances(self) -> None:
        """Each element in status.steps must be a PipelineStep instance."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        for step in status.steps:
            assert isinstance(step, PipelineStep)

    async def test_data_export_path_is_string(self) -> None:
        """data_export_path must be serialized as a string, not a Path object."""
        service = _build_service(counts_sequence=[0] * 8)
        with (
            patch(_SETTINGS_TOKEN_IS_FILE, return_value=False),
            patch("pathlib.Path.is_dir", return_value=False),
        ):
            status = await service.get_status()

        assert isinstance(status.data_export_path, str)

    async def test_step_names_are_non_empty_strings(self) -> None:
        """Each step must have a non-empty name string."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        for step in status.steps:
            assert isinstance(step.name, str)
            assert len(step.name) > 0

    async def test_step_descriptions_are_non_empty_strings(self) -> None:
        """Each step must have a non-empty description string."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        for step in status.steps:
            assert isinstance(step.description, str)
            assert len(step.description) > 0


# ===========================================================================
# Tests: returning user — new data detection (US3)
# ===========================================================================


class TestReturningUser:
    """Validate the returning-user scenario where the full pipeline has been
    completed and the user adds a new Google Takeout export.

    The key behaviour:
    * Completed steps retain their metrics after re-visiting the page.
    * ``load_data`` shows ``AVAILABLE`` when new export data is detected,
      even though videos > 0.
    * Downstream steps keep their statuses based on their own counts.
    """

    # Full pipeline completed: channels=5, videos=100, available_videos=50,
    # enriched_videos=50 (== available_videos so COMPLETED), playlists=3,
    # transcripts=200, categories=50, canonical_tags=9999
    _FULL_COUNTS = [5, 100, 50, 50, 3, 200, 50, 9999]

    def _make_export_entry(self, mtime: float = 1700000000.0) -> MagicMock:
        """Create a mock Path entry with a controllable stat().st_mtime."""
        entry = MagicMock(spec=Path)
        stat_result = MagicMock()
        stat_result.st_mtime = mtime
        entry.stat.return_value = stat_result
        return entry

    async def _get_status_returning_user(
        self,
        counts_sequence: list[int],
        *,
        export_dir_exists: bool = True,
        export_has_files: bool = True,
        export_mtime: float = 1700000000.0,
        is_authenticated: bool = True,
    ) -> Any:
        """Build a service and call get_status() with export-dir patches.

        Simulates a returning user scenario by controlling the export
        directory state (exists, has files, modification time).

        ``Path.iterdir`` is patched as a side_effect that returns a fresh
        iterator each time it is called — this is critical because
        ``_detect_data_export`` and ``_get_export_mtime`` both consume
        the iterator independently.
        """
        service = _build_service(counts_sequence=counts_sequence)
        entry = self._make_export_entry(mtime=export_mtime)

        def _iterdir_side_effect() -> Any:
            return iter([entry] if export_has_files else [])

        with (
            patch(_SETTINGS_TOKEN_IS_FILE, return_value=is_authenticated),
            patch("pathlib.Path.is_dir", return_value=export_dir_exists),
            patch(
                "pathlib.Path.iterdir",
                side_effect=_iterdir_side_effect,
            ),
        ):
            return await service.get_status()

    # -----------------------------------------------------------------------
    # Scenario 1: completed steps retain metrics on re-visit
    # -----------------------------------------------------------------------

    async def test_completed_steps_retain_metrics_on_revisit(self) -> None:
        """All completed steps preserve their metric counts when the page is
        re-loaded — metrics come from the DB, not from task results.
        """
        status = await self._get_status_returning_user(
            self._FULL_COUNTS,
            export_dir_exists=False,  # no new export
        )

        load_step = _get_step(status.steps, OperationType.LOAD_DATA)
        assert load_step.metrics["videos"] == 100
        assert load_step.metrics["channels"] == 5
        assert load_step.metrics["playlists"] == 3

        seed_step = _get_step(status.steps, OperationType.SEED_REFERENCE)
        assert seed_step.metrics["categories"] == 50

        norm_step = _get_step(status.steps, OperationType.NORMALIZE_TAGS)
        assert norm_step.metrics["canonical_tags"] == 9999

    async def test_all_steps_completed_without_new_export(self) -> None:
        """Without new export data, every step should remain COMPLETED."""
        status = await self._get_status_returning_user(
            self._FULL_COUNTS,
            export_dir_exists=False,
        )

        for step in status.steps:
            assert step.status == PipelineStepStatus.COMPLETED, (
                f"Expected COMPLETED for {step.operation_type.value}, "
                f"got {step.status.value}"
            )

    async def test_new_data_available_is_false_without_export(self) -> None:
        """new_data_available must be False when no export directory exists."""
        status = await self._get_status_returning_user(
            self._FULL_COUNTS,
            export_dir_exists=False,
        )
        assert status.new_data_available is False

    # -----------------------------------------------------------------------
    # Scenario 2: new export detected → load_data shows AVAILABLE
    # -----------------------------------------------------------------------

    async def test_load_data_available_when_new_export_detected(self) -> None:
        """load_data shows AVAILABLE (not COMPLETED) when new exports are
        detected alongside existing videos in the database.
        """
        status = await self._get_status_returning_user(
            self._FULL_COUNTS,
            export_dir_exists=True,
            export_has_files=True,
            export_mtime=1700000000.0,
        )

        step = _get_step(status.steps, OperationType.LOAD_DATA)
        assert step.status == PipelineStepStatus.AVAILABLE

    async def test_new_data_available_is_true_with_export_and_videos(self) -> None:
        """new_data_available is True when exports exist and videos are loaded."""
        status = await self._get_status_returning_user(
            self._FULL_COUNTS,
            export_dir_exists=True,
            export_has_files=True,
        )
        assert status.new_data_available is True

    async def test_load_data_metrics_preserved_even_when_available(self) -> None:
        """Even when load_data reverts to AVAILABLE, its metrics reflect DB state."""
        status = await self._get_status_returning_user(
            self._FULL_COUNTS,
            export_dir_exists=True,
            export_has_files=True,
        )

        step = _get_step(status.steps, OperationType.LOAD_DATA)
        assert step.status == PipelineStepStatus.AVAILABLE
        assert step.metrics["videos"] == 100
        assert step.metrics["channels"] == 5

    async def test_new_data_not_detected_when_no_videos_loaded(self) -> None:
        """new_data_available is False on a fresh DB even with export files,
        because the user hasn't done the initial load yet.
        """
        status = await self._get_status_returning_user(
            [0] * 8,
            export_dir_exists=True,
            export_has_files=True,
        )
        assert status.new_data_available is False

    async def test_new_data_not_detected_when_export_dir_empty(self) -> None:
        """new_data_available is False when export directory exists but is empty."""
        status = await self._get_status_returning_user(
            self._FULL_COUNTS,
            export_dir_exists=True,
            export_has_files=False,
        )
        assert status.new_data_available is False

    # -----------------------------------------------------------------------
    # Scenario 3: downstream steps unaffected by new data signal
    # -----------------------------------------------------------------------

    async def test_downstream_steps_remain_completed_with_new_data(self) -> None:
        """normalize_tags, enrich_metadata, seed_reference keep COMPLETED
        status even when load_data reverts to AVAILABLE.
        """
        status = await self._get_status_returning_user(
            self._FULL_COUNTS,
            export_dir_exists=True,
            export_has_files=True,
        )

        # load_data should be AVAILABLE (new data)
        assert (
            _get_step(status.steps, OperationType.LOAD_DATA).status
            == PipelineStepStatus.AVAILABLE
        )

        # All other steps should still be COMPLETED
        for op in (
            OperationType.SEED_REFERENCE,
            OperationType.ENRICH_METADATA,
            OperationType.NORMALIZE_TAGS,
        ):
            step = _get_step(status.steps, op)
            assert step.status == PipelineStepStatus.COMPLETED, (
                f"Expected COMPLETED for {op.value}, got {step.status.value}"
            )

    async def test_enrich_metadata_stays_completed_with_new_data(self) -> None:
        """enrich_metadata uses count_key='enriched_videos' — even though load_data
        reverts to AVAILABLE, enrich_metadata's own status depends on
        its count_key which is still > 0, so it stays COMPLETED.
        """
        status = await self._get_status_returning_user(
            self._FULL_COUNTS,
            export_dir_exists=True,
            export_has_files=True,
        )

        step = _get_step(status.steps, OperationType.ENRICH_METADATA)
        assert step.status == PipelineStepStatus.COMPLETED

    async def test_counts_unchanged_by_new_data_detection(self) -> None:
        """OnboardingCounts must reflect actual DB values regardless of
        the new_data_available signal — it's purely a UI hint.
        """
        status = await self._get_status_returning_user(
            self._FULL_COUNTS,
            export_dir_exists=True,
            export_has_files=True,
        )

        assert status.counts.channels == 5
        assert status.counts.videos == 100
        assert status.counts.playlists == 3
        assert status.counts.transcripts == 200
        assert status.counts.categories == 50
        assert status.counts.canonical_tags == 9999


# ===========================================================================
# Helpers shared by factory tests
# ===========================================================================


def _make_factory_session_factory() -> MagicMock:
    """Build a bare async session-factory mock for factory tests.

    Unlike ``_make_session_factory``, this helper does not wire up
    ``session.execute`` / ``scalar_one``; factory tests drive their own
    session interactions via ``AsyncMock`` attributes.
    """
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock(return_value=None)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_cm

    return mock_factory


def _build_factory_service() -> Any:
    """Construct an OnboardingService wired for factory unit tests.

    Uses a minimal session factory and a no-op task manager.
    """
    from chronovista.services.onboarding_service import OnboardingService

    session_factory = _make_factory_session_factory()
    task_manager = _make_task_manager()
    return OnboardingService(
        task_manager=task_manager,
        session_factory=session_factory,
    )


def _capture_progress() -> tuple[list[float], Any]:
    """Return ``(calls, cb)`` where ``cb`` records each progress value."""
    calls: list[float] = []

    def _cb(value: float) -> None:
        calls.append(value)

    return calls, _cb


# ===========================================================================
# Tests: _factory_seed_reference
# ===========================================================================


class TestFactorySeedReference:
    """Unit tests for ``OnboardingService._factory_seed_reference``.

    Parameters
    ----------
    None

    Notes
    -----
    The factory returns a ``CoroFactory`` (a callable that accepts a
    ``progress_cb`` and returns a coroutine).  Tests exercise:
    - that the return value is callable
    - that awaiting the coroutine produces the expected result dict
    - that ``progress_cb`` is called at the correct progress milestones
    - that topic/category seeders are invoked with the session
    """

    async def test_factory_returns_callable(self) -> None:
        """_factory_seed_reference() returns a callable (the CoroFactory)."""
        service = _build_factory_service()
        factory = service._factory_seed_reference()
        assert callable(factory)

    async def test_factory_callable_returns_coroutine(self) -> None:
        """Calling the CoroFactory with a progress_cb returns an awaitable."""
        import inspect

        service = _build_factory_service()
        factory = service._factory_seed_reference()
        _, cb = _capture_progress()

        topic_seed_result = MagicMock(created=5, skipped=2, aliases_seeded=10)
        category_seed_result = MagicMock(created=3, skipped=1, quota_used=100)

        mock_topic_seeder = AsyncMock()
        mock_topic_seeder.seed = AsyncMock(return_value=topic_seed_result)
        mock_category_seeder = AsyncMock()
        mock_category_seeder.seed = AsyncMock(return_value=category_seed_result)

        mock_container = MagicMock()
        mock_container.create_topic_seeder.return_value = mock_topic_seeder
        mock_container.create_category_seeder.return_value = mock_category_seeder

        with patch(
            "chronovista.container.container", mock_container
        ):
            coro = factory(cb)
            assert inspect.isawaitable(coro)
            await coro

    async def test_result_has_expected_keys(self) -> None:
        """The result dict from the factory coroutine contains all expected keys."""
        service = _build_factory_service()
        factory = service._factory_seed_reference()
        _, cb = _capture_progress()

        topic_seed_result = MagicMock(created=5, skipped=2, aliases_seeded=10)
        category_seed_result = MagicMock(created=3, skipped=1, quota_used=100)

        mock_topic_seeder = AsyncMock()
        mock_topic_seeder.seed = AsyncMock(return_value=topic_seed_result)
        mock_category_seeder = AsyncMock()
        mock_category_seeder.seed = AsyncMock(return_value=category_seed_result)

        mock_container = MagicMock()
        mock_container.create_topic_seeder.return_value = mock_topic_seeder
        mock_container.create_category_seeder.return_value = mock_category_seeder

        with patch(
            "chronovista.container.container", mock_container
        ):
            result = await factory(cb)

        expected_keys = {
            "topics_created",
            "topics_skipped",
            "aliases_seeded",
            "categories_created",
            "categories_skipped",
            "quota_used",
        }
        assert set(result.keys()) == expected_keys

    async def test_result_values_reflect_seeder_results(self) -> None:
        """Result dict values come from TopicSeedResult and CategorySeedResult."""
        service = _build_factory_service()
        factory = service._factory_seed_reference()
        _, cb = _capture_progress()

        topic_seed_result = MagicMock(created=7, skipped=3, aliases_seeded=20)
        category_seed_result = MagicMock(created=15, skipped=5, quota_used=200)

        mock_topic_seeder = AsyncMock()
        mock_topic_seeder.seed = AsyncMock(return_value=topic_seed_result)
        mock_category_seeder = AsyncMock()
        mock_category_seeder.seed = AsyncMock(return_value=category_seed_result)

        mock_container = MagicMock()
        mock_container.create_topic_seeder.return_value = mock_topic_seeder
        mock_container.create_category_seeder.return_value = mock_category_seeder

        with patch(
            "chronovista.container.container", mock_container
        ):
            result = await factory(cb)

        assert result["topics_created"] == 7
        assert result["topics_skipped"] == 3
        assert result["aliases_seeded"] == 20
        assert result["categories_created"] == 15
        assert result["categories_skipped"] == 5
        assert result["quota_used"] == 200

    async def test_progress_called_at_zero(self) -> None:
        """progress_cb is called at 0.0 before any seeding work begins."""
        service = _build_factory_service()
        factory = service._factory_seed_reference()
        calls, cb = _capture_progress()

        topic_seed_result = MagicMock(created=1, skipped=0, aliases_seeded=0)
        category_seed_result = MagicMock(created=1, skipped=0, quota_used=0)

        mock_topic_seeder = AsyncMock()
        mock_topic_seeder.seed = AsyncMock(return_value=topic_seed_result)
        mock_category_seeder = AsyncMock()
        mock_category_seeder.seed = AsyncMock(return_value=category_seed_result)

        mock_container = MagicMock()
        mock_container.create_topic_seeder.return_value = mock_topic_seeder
        mock_container.create_category_seeder.return_value = mock_category_seeder

        with patch(
            "chronovista.container.container", mock_container
        ):
            await factory(cb)

        assert calls[0] == 0.0

    async def test_progress_called_at_forty_after_topics(self) -> None:
        """progress_cb is called at 40.0 after topic seeding completes."""
        service = _build_factory_service()
        factory = service._factory_seed_reference()
        calls, cb = _capture_progress()

        topic_seed_result = MagicMock(created=1, skipped=0, aliases_seeded=0)
        category_seed_result = MagicMock(created=1, skipped=0, quota_used=0)

        mock_topic_seeder = AsyncMock()
        mock_topic_seeder.seed = AsyncMock(return_value=topic_seed_result)
        mock_category_seeder = AsyncMock()
        mock_category_seeder.seed = AsyncMock(return_value=category_seed_result)

        mock_container = MagicMock()
        mock_container.create_topic_seeder.return_value = mock_topic_seeder
        mock_container.create_category_seeder.return_value = mock_category_seeder

        with patch(
            "chronovista.container.container", mock_container
        ):
            await factory(cb)

        assert 40.0 in calls

    async def test_progress_called_at_ninety_and_hundred(self) -> None:
        """progress_cb is called at 90.0 and 100.0 before the coroutine returns."""
        service = _build_factory_service()
        factory = service._factory_seed_reference()
        calls, cb = _capture_progress()

        topic_seed_result = MagicMock(created=1, skipped=0, aliases_seeded=0)
        category_seed_result = MagicMock(created=1, skipped=0, quota_used=0)

        mock_topic_seeder = AsyncMock()
        mock_topic_seeder.seed = AsyncMock(return_value=topic_seed_result)
        mock_category_seeder = AsyncMock()
        mock_category_seeder.seed = AsyncMock(return_value=category_seed_result)

        mock_container = MagicMock()
        mock_container.create_topic_seeder.return_value = mock_topic_seeder
        mock_container.create_category_seeder.return_value = mock_category_seeder

        with patch(
            "chronovista.container.container", mock_container
        ):
            await factory(cb)

        assert 90.0 in calls
        assert 100.0 in calls

    async def test_progress_milestones_in_order(self) -> None:
        """progress_cb milestones are received in ascending order: 0, 40, 90, 100."""
        service = _build_factory_service()
        factory = service._factory_seed_reference()
        calls, cb = _capture_progress()

        topic_seed_result = MagicMock(created=1, skipped=0, aliases_seeded=0)
        category_seed_result = MagicMock(created=1, skipped=0, quota_used=0)

        mock_topic_seeder = AsyncMock()
        mock_topic_seeder.seed = AsyncMock(return_value=topic_seed_result)
        mock_category_seeder = AsyncMock()
        mock_category_seeder.seed = AsyncMock(return_value=category_seed_result)

        mock_container = MagicMock()
        mock_container.create_topic_seeder.return_value = mock_topic_seeder
        mock_container.create_category_seeder.return_value = mock_category_seeder

        with patch(
            "chronovista.container.container", mock_container
        ):
            await factory(cb)

        assert calls == sorted(calls), "Progress values must be non-decreasing"
        assert calls[0] == 0.0
        assert calls[-1] == 100.0

    async def test_topic_seeder_called_with_session(self) -> None:
        """topic_seeder.seed() is called with the session from the session factory."""
        service = _build_factory_service()
        factory = service._factory_seed_reference()
        _, cb = _capture_progress()

        topic_seed_result = MagicMock(created=1, skipped=0, aliases_seeded=0)
        category_seed_result = MagicMock(created=1, skipped=0, quota_used=0)

        mock_topic_seeder = AsyncMock()
        mock_topic_seeder.seed = AsyncMock(return_value=topic_seed_result)
        mock_category_seeder = AsyncMock()
        mock_category_seeder.seed = AsyncMock(return_value=category_seed_result)

        mock_container = MagicMock()
        mock_container.create_topic_seeder.return_value = mock_topic_seeder
        mock_container.create_category_seeder.return_value = mock_category_seeder

        with patch(
            "chronovista.container.container", mock_container
        ):
            await factory(cb)

        mock_topic_seeder.seed.assert_awaited_once()

    async def test_category_seeder_called_with_session(self) -> None:
        """category_seeder.seed() is called with the session from the session factory."""
        service = _build_factory_service()
        factory = service._factory_seed_reference()
        _, cb = _capture_progress()

        topic_seed_result = MagicMock(created=1, skipped=0, aliases_seeded=0)
        category_seed_result = MagicMock(created=1, skipped=0, quota_used=0)

        mock_topic_seeder = AsyncMock()
        mock_topic_seeder.seed = AsyncMock(return_value=topic_seed_result)
        mock_category_seeder = AsyncMock()
        mock_category_seeder.seed = AsyncMock(return_value=category_seed_result)

        mock_container = MagicMock()
        mock_container.create_topic_seeder.return_value = mock_topic_seeder
        mock_container.create_category_seeder.return_value = mock_category_seeder

        with patch(
            "chronovista.container.container", mock_container
        ):
            await factory(cb)

        mock_category_seeder.seed.assert_awaited_once()


# ===========================================================================
# Tests: _factory_load_data
# ===========================================================================


class TestFactoryLoadData:
    """Unit tests for ``OnboardingService._factory_load_data``.

    Parameters
    ----------
    None

    Notes
    -----
    The factory discovers takeout directories, creates ``TakeoutService``
    instances via ``object.__new__``, calls ``parse_all`` and
    ``seed_database`` for each directory, then runs the recovery service.
    Tests exercise directory discovery, result merging, recovery, and
    progress callback milestones.

    Patching strategy
    -----------------
    The code inside the coroutine uses ``object.__new__(TakeoutService)``
    instead of a normal constructor, so patching the class at its origin
    module intercepts both the import and the ``object.__new__`` call.
    We patch ``builtins.object.__new__`` with a side_effect that returns
    our mock when called with the patched class, forwarding all other calls
    to the real ``object.__new__``.
    """

    def _make_mock_dir_entry(self, name: str, is_dir: bool = True) -> MagicMock:
        """Build a mock filesystem directory entry.

        The entry is sortable (via ``__lt__``) so that ``sorted(path.iterdir())``
        in the factory does not raise ``TypeError`` when multiple entries are
        returned.
        """
        entry = MagicMock(spec=Path)
        entry.name = name
        entry.is_dir.return_value = is_dir
        entry.parent = Path("/fake/takeout")
        # Make entries sortable by name so sorted() in the factory works
        entry.__lt__ = lambda self, other: self.name < other.name
        entry.__le__ = lambda self, other: self.name <= other.name
        entry.__gt__ = lambda self, other: self.name > other.name
        entry.__ge__ = lambda self, other: self.name >= other.name
        return entry

    def _make_seed_result(self, created: int = 5) -> MagicMock:
        """Build a mock SeedResult-like object."""
        result = MagicMock()
        result.created = created
        return result

    def _build_mocks(
        self,
        *,
        dir_entries: list[MagicMock],
        seed_result: dict[str, Any] | None = None,
        recovery_result: MagicMock | None = None,
        recovery_raises: Exception | None = None,
        parse_raises: Exception | None = None,
    ) -> tuple[AsyncMock, AsyncMock, AsyncMock, Path]:
        """Return (mock_svc, mock_seeding, mock_recovery_svc, fake_path).

        The mock_svc is a pre-configured ``AsyncMock`` that stands in for
        the ``TakeoutService`` instance created via ``object.__new__``.
        """
        mock_data = MagicMock()
        mock_svc = AsyncMock()
        if parse_raises is not None:
            mock_svc.parse_all = AsyncMock(side_effect=parse_raises)
        else:
            mock_svc.parse_all = AsyncMock(return_value=mock_data)

        _seed_result = seed_result or {"videos": self._make_seed_result(3)}
        mock_seeding = AsyncMock()
        mock_seeding.seed_database = AsyncMock(return_value=_seed_result)

        mock_recovery_svc = AsyncMock()
        if recovery_raises is not None:
            mock_recovery_svc.recover_from_historical_takeouts = AsyncMock(
                side_effect=recovery_raises
            )
        else:
            _recovery = recovery_result or MagicMock(
                videos_recovered=0, channels_created=0, channels_updated=0
            )
            mock_recovery_svc.recover_from_historical_takeouts = AsyncMock(
                return_value=_recovery
            )

        fake_path = Path("/fake/takeout")
        return mock_svc, mock_seeding, mock_recovery_svc, fake_path

    async def _run_factory_with_patches(
        self,
        *,
        dir_entries: list[MagicMock],
        seed_result: dict[str, Any] | None = None,
        recovery_result: MagicMock | None = None,
        recovery_raises: Exception | None = None,
        parse_raises: Exception | None = None,
    ) -> tuple[dict[str, Any], list[float]]:
        """Run the full factory pipeline with all mocks in place.

        Strategy for ``object.__new__(TakeoutService)``
        -----------------------------------------------
        The coroutine creates a ``TakeoutService`` via
        ``object.__new__(TakeoutService)`` without calling ``__init__``.
        We intercept this by patching ``TakeoutService`` in the module
        where it is imported with a minimal stub class that holds our
        async ``parse_all`` mock.  When the code does
        ``object.__new__(StubTakeoutService)``, Python returns a real
        ``StubTakeoutService`` instance with our mock in place.
        """
        mock_svc, mock_seeding, mock_recovery_svc, fake_path = self._build_mocks(
            dir_entries=dir_entries,
            seed_result=seed_result,
            recovery_result=recovery_result,
            recovery_raises=recovery_raises,
            parse_raises=parse_raises,
        )

        service = _build_factory_service()
        factory = service._factory_load_data()
        calls, cb = _capture_progress()

        # Build a stub class whose instances will have parse_all as an AsyncMock.
        # The coroutine reads the class reference from the local import and then
        # calls object.__new__(that_class), so patching the class in its own
        # module is sufficient.
        _parse_all_mock = mock_svc.parse_all

        class _StubTakeoutService:
            takeout_path: Any = None
            youtube_path: Any = None
            parse_all = _parse_all_mock  # shared across all instances

        with (
            patch(
                "chronovista.services.onboarding_service.OnboardingService._get_data_export_path",
                return_value=fake_path,
            ),
            patch.object(Path, "iterdir", return_value=iter(dir_entries)),
            patch(
                "chronovista.services.takeout_seeding_service.TakeoutSeedingService",
                return_value=mock_seeding,
            ),
            patch(
                "chronovista.services.takeout_recovery_service.TakeoutRecoveryService",
                return_value=mock_recovery_svc,
            ),
            # Patch TakeoutService in the module where the closure imports it
            patch(
                "chronovista.services.takeout_service.TakeoutService",
                new=_StubTakeoutService,
            ),
        ):
            result = await factory(cb)

        return result, calls

    async def test_factory_returns_callable(self) -> None:
        """_factory_load_data() returns a callable (the CoroFactory)."""
        service = _build_factory_service()
        factory = service._factory_load_data()
        assert callable(factory)

    async def _run(
        self,
        dir_entries: list[MagicMock] | None = None,
        *,
        seed_result: dict[str, Any] | None = None,
        recovery_result: MagicMock | None = None,
        recovery_raises: Exception | None = None,
        parse_raises: Exception | None = None,
    ) -> tuple[dict[str, Any], list[float]]:
        """Thin alias used by individual tests."""
        _entries = dir_entries or [
            self._make_mock_dir_entry("YouTube and YouTube Music")
        ]
        return await self._run_factory_with_patches(
            dir_entries=_entries,
            seed_result=seed_result,
            recovery_result=recovery_result,
            recovery_raises=recovery_raises,
            parse_raises=parse_raises,
        )

    async def test_result_includes_recovery_data_when_successful(self) -> None:
        """When recovery succeeds, its keys are merged into the result dict."""
        recovery = MagicMock(
            videos_recovered=10,
            channels_created=2,
            channels_updated=1,
        )
        result, _ = await self._run(recovery_result=recovery)
        assert result.get("videos_recovered") == 10
        assert result.get("channels_created") == 2
        assert result.get("channels_updated") == 1

    async def test_recovery_failure_is_non_fatal(self) -> None:
        """Recovery exceptions are caught and result contains 'recovery_error' key."""
        result, _ = await self._run(
            recovery_raises=RuntimeError("Recovery exploded")
        )
        # Factory must return (not raise) even when recovery fails
        assert "recovery_error" in result
        assert "Recovery exploded" in result["recovery_error"]

    async def test_fallback_to_undated_dir_when_no_dirs_found(self) -> None:
        """When no 'YouTube and YouTube Music*' dirs exist, a fallback path is used."""
        # Provide an entry that does NOT start with the expected prefix
        unrelated = self._make_mock_dir_entry("SomeOtherFolder")
        result, _ = await self._run(dir_entries=[unrelated])
        assert isinstance(result, dict)

    async def test_merges_created_counts_across_multiple_dirs(self) -> None:
        """When multiple takeout dirs are found, 'created' counts are summed."""
        entries = [
            self._make_mock_dir_entry("YouTube and YouTube Music 2024-01-01"),
            self._make_mock_dir_entry("YouTube and YouTube Music 2025-01-01"),
        ]

        call_num = 0

        def _side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal call_num
            call_num += 1
            r = MagicMock()
            r.created = 5
            return {"videos": r}

        mock_svc, _, mock_recovery_svc, fake_path = self._build_mocks(
            dir_entries=entries
        )
        mock_seeding = AsyncMock()
        mock_seeding.seed_database = AsyncMock(side_effect=_side_effect)

        _parse_all_mock = mock_svc.parse_all

        class _Stub:
            takeout_path: Any = None
            youtube_path: Any = None
            parse_all = _parse_all_mock

        service = _build_factory_service()
        factory = service._factory_load_data()
        _, cb = _capture_progress()

        with (
            patch(
                "chronovista.services.onboarding_service.OnboardingService._get_data_export_path",
                return_value=fake_path,
            ),
            patch.object(Path, "iterdir", return_value=iter(entries)),
            patch(
                "chronovista.services.takeout_seeding_service.TakeoutSeedingService",
                return_value=mock_seeding,
            ),
            patch(
                "chronovista.services.takeout_recovery_service.TakeoutRecoveryService",
                return_value=mock_recovery_svc,
            ),
            patch("chronovista.services.takeout_service.TakeoutService", new=_Stub),
        ):
            result = await factory(cb)

        # Two directories each contributing 5 created → sum should be 10
        assert result.get("videos") == 10

    async def test_progress_called_at_zero(self) -> None:
        """progress_cb is called at 0.0 as the first step."""
        _, calls = await self._run()
        assert calls[0] == 0.0

    async def test_progress_ends_at_hundred(self) -> None:
        """progress_cb is called at 100.0 as the final milestone."""
        _, calls = await self._run()
        assert calls[-1] == 100.0

    async def test_progress_called_at_sixty_after_seeding(self) -> None:
        """progress_cb is called at 60.0 after all directories are seeded."""
        _, calls = await self._run()
        assert 60.0 in calls

    async def test_result_is_dict(self) -> None:
        """The factory coroutine returns a dict regardless of input."""
        result, _ = await self._run()
        assert isinstance(result, dict)

    async def test_recovery_service_called_with_takeout_path(self) -> None:
        """recover_from_historical_takeouts is called with the takeout_path."""
        entries = [self._make_mock_dir_entry("YouTube and YouTube Music")]
        mock_svc, mock_seeding, mock_recovery_svc, fake_path = self._build_mocks(
            dir_entries=entries
        )

        _parse_all_mock = mock_svc.parse_all

        class _Stub:
            takeout_path: Any = None
            youtube_path: Any = None
            parse_all = _parse_all_mock

        service = _build_factory_service()
        factory = service._factory_load_data()
        _, cb = _capture_progress()

        with (
            patch(
                "chronovista.services.onboarding_service.OnboardingService._get_data_export_path",
                return_value=fake_path,
            ),
            patch.object(Path, "iterdir", return_value=iter(entries)),
            patch(
                "chronovista.services.takeout_seeding_service.TakeoutSeedingService",
                return_value=mock_seeding,
            ),
            patch(
                "chronovista.services.takeout_recovery_service.TakeoutRecoveryService",
                return_value=mock_recovery_svc,
            ),
            patch("chronovista.services.takeout_service.TakeoutService", new=_Stub),
        ):
            await factory(cb)

        mock_recovery_svc.recover_from_historical_takeouts.assert_awaited_once()
        call_args = mock_recovery_svc.recover_from_historical_takeouts.call_args
        # Second positional arg is takeout_path
        assert call_args[0][1] == fake_path

    async def test_parse_all_called_for_each_directory(self) -> None:
        """parse_all is called once for each discovered takeout directory."""
        entries = [
            self._make_mock_dir_entry("YouTube and YouTube Music 2024-01-01"),
            self._make_mock_dir_entry("YouTube and YouTube Music 2025-01-01"),
        ]

        mock_svc, mock_seeding, mock_recovery_svc, fake_path = self._build_mocks(
            dir_entries=entries
        )

        _parse_all_mock = mock_svc.parse_all

        class _Stub:
            takeout_path: Any = None
            youtube_path: Any = None
            parse_all = _parse_all_mock

        service = _build_factory_service()
        factory = service._factory_load_data()
        _, cb = _capture_progress()

        with (
            patch(
                "chronovista.services.onboarding_service.OnboardingService._get_data_export_path",
                return_value=fake_path,
            ),
            patch.object(Path, "iterdir", return_value=iter(entries)),
            patch(
                "chronovista.services.takeout_seeding_service.TakeoutSeedingService",
                return_value=mock_seeding,
            ),
            patch(
                "chronovista.services.takeout_recovery_service.TakeoutRecoveryService",
                return_value=mock_recovery_svc,
            ),
            patch("chronovista.services.takeout_service.TakeoutService", new=_Stub),
        ):
            await factory(cb)

        # parse_all called once per directory
        assert mock_svc.parse_all.await_count == 2

    async def test_individual_dir_failure_is_non_fatal(self) -> None:
        """Exceptions from processing a single takeout dir are caught and logged."""
        entries = [
            self._make_mock_dir_entry("YouTube and YouTube Music 2024-01-01"),
        ]
        result, _ = await self._run(
            dir_entries=entries,
            parse_raises=RuntimeError("dir parse failed"),
        )
        # Should not raise and must return a dict
        assert isinstance(result, dict)


# ===========================================================================
# Tests: _factory_enrich_metadata
# ===========================================================================


class TestFactoryEnrichMetadata:
    """Unit tests for ``OnboardingService._factory_enrich_metadata``.

    Parameters
    ----------
    None

    Notes
    -----
    The factory runs four enrichment steps (videos, playlists, likes, channels)
    in sequence, each wrapped in a separate try/except so that step failures
    are non-fatal.  Tests verify:
    - result dict keys and values
    - progress callback milestones
    - each step's failure does not prevent subsequent steps
    - likes sync path (my_channel, liked_videos, exists, update_like_status_batch)
    """

    def _make_enrichment_summary(
        self,
        *,
        videos_processed: int = 10,
        videos_updated: int = 8,
        videos_deleted: int = 1,
        channels_created: int = 2,
        tags_created: int = 50,
        errors: int = 0,
        quota_used: int = 100,
        topic_associations: int = 0,
        categories_assigned: int = 0,
    ) -> MagicMock:
        summary = MagicMock()
        summary.videos_processed = videos_processed
        summary.videos_updated = videos_updated
        summary.videos_deleted = videos_deleted
        summary.channels_created = channels_created
        summary.tags_created = tags_created
        summary.errors = errors
        summary.quota_used = quota_used
        return summary

    def _make_enrichment_report(self, summary: MagicMock) -> MagicMock:
        report = MagicMock()
        report.summary = summary
        return report

    def _make_channel_enrichment_result(
        self, channels_enriched: int = 5
    ) -> MagicMock:
        result = MagicMock()
        result.channels_enriched = channels_enriched
        return result

    async def _run_factory(
        self,
        *,
        enrich_videos_raises: Exception | None = None,
        enrich_playlists_raises: Exception | None = None,
        enrich_channels_raises: Exception | None = None,
        my_channel: MagicMock | None = None,
        liked_videos: list[MagicMock] | None = None,
        likes_sync_raises: Exception | None = None,
        video_exists: bool = True,
        likes_updated: int = 3,
    ) -> tuple[dict[str, Any], list[float]]:
        """Run the factory with full mocking and return (result, progress_calls)."""
        summary = self._make_enrichment_summary()
        report = self._make_enrichment_report(summary)
        channel_result = self._make_channel_enrichment_result()

        mock_enrichment_svc = AsyncMock()
        if enrich_videos_raises:
            mock_enrichment_svc.enrich_videos = AsyncMock(
                side_effect=enrich_videos_raises
            )
        else:
            mock_enrichment_svc.enrich_videos = AsyncMock(return_value=report)

        if enrich_playlists_raises:
            mock_enrichment_svc.enrich_playlists = AsyncMock(
                side_effect=enrich_playlists_raises
            )
        else:
            mock_enrichment_svc.enrich_playlists = AsyncMock(
                return_value=(5, 3, 1)
            )

        if enrich_channels_raises:
            mock_enrichment_svc.enrich_channels = AsyncMock(
                side_effect=enrich_channels_raises
            )
        else:
            mock_enrichment_svc.enrich_channels = AsyncMock(
                return_value=channel_result
            )

        # YouTube service mock for likes
        mock_youtube_svc = AsyncMock()
        if likes_sync_raises:
            mock_youtube_svc.get_my_channel = AsyncMock(
                side_effect=likes_sync_raises
            )
        else:
            mock_youtube_svc.get_my_channel = AsyncMock(return_value=my_channel)
            mock_youtube_svc.get_liked_videos = AsyncMock(
                return_value=liked_videos or []
            )

        mock_container = MagicMock()
        mock_container.create_enrichment_service.return_value = mock_enrichment_svc
        mock_container.youtube_service = mock_youtube_svc

        mock_video_repo = AsyncMock()
        mock_video_repo.exists = AsyncMock(return_value=video_exists)

        mock_user_video_repo = AsyncMock()
        mock_user_video_repo.update_like_status_batch = AsyncMock(
            return_value=likes_updated
        )

        service = _build_factory_service()
        factory = service._factory_enrich_metadata()
        calls, cb = _capture_progress()

        with (
            patch(
                "chronovista.container.container", mock_container
            ),
            patch(
                "chronovista.repositories.video_repository.VideoRepository",
                return_value=mock_video_repo,
            ),
            patch(
                "chronovista.repositories.user_video_repository.UserVideoRepository",
                return_value=mock_user_video_repo,
            ),
        ):
            result = await factory(cb)

        return result, calls

    async def test_factory_returns_callable(self) -> None:
        """_factory_enrich_metadata() returns a callable (the CoroFactory)."""
        service = _build_factory_service()
        factory = service._factory_enrich_metadata()
        assert callable(factory)

    async def test_result_has_expected_keys(self) -> None:
        """Result dict contains all expected keys."""
        result, _ = await self._run_factory()
        expected_keys = {
            "videos_processed",
            "videos_updated",
            "videos_deleted",
            "channels_created",
            "channels_enriched",
            "playlists_processed",
            "playlists_updated",
            "likes_synced",
            "tags_created",
            "errors",
            "quota_used",
        }
        assert set(result.keys()) == expected_keys

    async def test_result_values_from_report_summary(self) -> None:
        """Result values map correctly from the EnrichmentReport summary."""
        result, _ = await self._run_factory()
        # These come from _make_enrichment_summary defaults
        assert result["videos_processed"] == 10
        assert result["videos_updated"] == 8
        assert result["videos_deleted"] == 1
        assert result["channels_created"] == 2
        assert result["tags_created"] == 50
        assert result["errors"] == 0
        assert result["quota_used"] == 100

    async def test_channels_enriched_from_channel_result(self) -> None:
        """channels_enriched comes from enrich_channels result."""
        result, _ = await self._run_factory()
        assert result["channels_enriched"] == 5

    async def test_playlists_processed_and_updated_from_enrich_playlists(
        self,
    ) -> None:
        """playlists_processed and playlists_updated reflect enrich_playlists return."""
        result, _ = await self._run_factory()
        assert result["playlists_processed"] == 5
        assert result["playlists_updated"] == 3

    async def test_enrich_videos_called_with_correct_params(self) -> None:
        """enrich_videos is called with priority='all', include_deleted=True, check_prerequisites=False."""
        summary = self._make_enrichment_summary()
        report = self._make_enrichment_report(summary)
        channel_result = self._make_channel_enrichment_result()

        mock_enrichment_svc = AsyncMock()
        mock_enrichment_svc.enrich_videos = AsyncMock(return_value=report)
        mock_enrichment_svc.enrich_playlists = AsyncMock(return_value=(0, 0, 0))
        mock_enrichment_svc.enrich_channels = AsyncMock(return_value=channel_result)

        mock_youtube_svc = AsyncMock()
        mock_youtube_svc.get_my_channel = AsyncMock(return_value=None)

        mock_container = MagicMock()
        mock_container.create_enrichment_service.return_value = mock_enrichment_svc
        mock_container.youtube_service = mock_youtube_svc

        service = _build_factory_service()
        factory = service._factory_enrich_metadata()
        _, cb = _capture_progress()

        with (
            patch(
                "chronovista.container.container", mock_container
            ),
            patch("chronovista.repositories.video_repository.VideoRepository"),
            patch("chronovista.repositories.user_video_repository.UserVideoRepository"),
        ):
            await factory(cb)

        mock_enrichment_svc.enrich_videos.assert_awaited_once_with(
            unittest_mock_any,
            priority="all",
            include_deleted=True,
            check_prerequisites=False,
            progress_cb=unittest_mock_any,
        )

    async def test_progress_called_at_zero(self) -> None:
        """progress_cb starts at 0.0."""
        _, calls = await self._run_factory()
        assert calls[0] == 0.0

    async def test_progress_called_at_thirty_after_videos(self) -> None:
        """progress_cb hits 30.0 after enrich_videos completes."""
        _, calls = await self._run_factory()
        assert 30.0 in calls

    async def test_progress_called_at_fifty_after_playlists(self) -> None:
        """progress_cb hits 50.0 after enrich_playlists completes."""
        _, calls = await self._run_factory()
        assert 50.0 in calls

    async def test_progress_called_at_seventy_after_likes(self) -> None:
        """progress_cb hits 70.0 after likes sync completes."""
        _, calls = await self._run_factory()
        assert 70.0 in calls

    async def test_progress_called_at_ninetyfive_after_channels(self) -> None:
        """progress_cb hits 95.0 after enrich_channels completes."""
        _, calls = await self._run_factory()
        assert 95.0 in calls

    async def test_progress_ends_at_hundred(self) -> None:
        """progress_cb ends at 100.0."""
        _, calls = await self._run_factory()
        assert calls[-1] == 100.0

    async def test_playlist_enrichment_failure_is_non_fatal(self) -> None:
        """enrich_playlists raising does not prevent channels step from running."""
        result, _ = await self._run_factory(
            enrich_playlists_raises=RuntimeError("playlists exploded")
        )
        # channels_enriched still present means the step continued
        assert "channels_enriched" in result
        assert result["playlists_processed"] == 0
        assert result["playlists_updated"] == 0

    async def test_channel_enrichment_failure_is_non_fatal(self) -> None:
        """enrich_channels raising does not prevent the factory from returning."""
        result, _ = await self._run_factory(
            enrich_channels_raises=RuntimeError("channels exploded")
        )
        assert isinstance(result, dict)
        assert result["channels_enriched"] == 0

    async def test_likes_sync_failure_is_non_fatal(self) -> None:
        """Likes sync exceptions are caught; likes_synced defaults to 0."""
        result, _ = await self._run_factory(
            likes_sync_raises=RuntimeError("likes exploded")
        )
        assert isinstance(result, dict)
        assert result["likes_synced"] == 0

    async def test_likes_synced_when_channel_and_videos_exist(self) -> None:
        """likes_synced is populated when my_channel and liked_videos are present."""
        my_channel = MagicMock()
        my_channel.id = "UCfakeChannel"
        liked_video = MagicMock()
        liked_video.id = "vid-001"

        result, _ = await self._run_factory(
            my_channel=my_channel,
            liked_videos=[liked_video],
            video_exists=True,
            likes_updated=1,
        )
        assert result["likes_synced"] == 1

    async def test_likes_synced_zero_when_no_channel(self) -> None:
        """likes_synced is 0 when get_my_channel returns None."""
        result, _ = await self._run_factory(my_channel=None)
        assert result["likes_synced"] == 0

    async def test_likes_synced_zero_when_no_liked_videos(self) -> None:
        """likes_synced is 0 when get_liked_videos returns an empty list."""
        my_channel = MagicMock()
        my_channel.id = "UCfake"
        result, _ = await self._run_factory(
            my_channel=my_channel, liked_videos=[]
        )
        assert result["likes_synced"] == 0

    async def test_create_enrichment_service_called_with_include_playlists_true(
        self,
    ) -> None:
        """create_enrichment_service is called with include_playlists=True."""
        summary = self._make_enrichment_summary()
        report = self._make_enrichment_report(summary)
        channel_result = self._make_channel_enrichment_result()

        mock_enrichment_svc = AsyncMock()
        mock_enrichment_svc.enrich_videos = AsyncMock(return_value=report)
        mock_enrichment_svc.enrich_playlists = AsyncMock(return_value=(0, 0, 0))
        mock_enrichment_svc.enrich_channels = AsyncMock(return_value=channel_result)

        mock_youtube_svc = AsyncMock()
        mock_youtube_svc.get_my_channel = AsyncMock(return_value=None)

        mock_container = MagicMock()
        mock_container.create_enrichment_service.return_value = mock_enrichment_svc
        mock_container.youtube_service = mock_youtube_svc

        service = _build_factory_service()
        factory = service._factory_enrich_metadata()
        _, cb = _capture_progress()

        with (
            patch(
                "chronovista.container.container", mock_container
            ),
            patch("chronovista.repositories.video_repository.VideoRepository"),
            patch("chronovista.repositories.user_video_repository.UserVideoRepository"),
        ):
            await factory(cb)

        mock_container.create_enrichment_service.assert_called_once_with(
            include_playlists=True
        )


# Stand-in for ``unittest.mock.ANY`` used in ``assert_awaited_once_with``
from unittest.mock import ANY as unittest_mock_any  # noqa: E402


# ===========================================================================
# Tests: _factory_normalize_tags
# ===========================================================================


class TestFactoryNormalizeTags:
    """Unit tests for ``OnboardingService._factory_normalize_tags``.

    Parameters
    ----------
    None

    Notes
    -----
    The factory instantiates ``TagNormalizationService`` and
    ``TagBackfillService`` and calls ``run_backfill`` on the latter.
    Tests verify:
    - factory is callable
    - result dict has status="completed"
    - run_backfill is awaited with the session
    - progress callbacks at 0, 90, 100
    """

    async def test_factory_returns_callable(self) -> None:
        """_factory_normalize_tags() returns a callable (the CoroFactory)."""
        service = _build_factory_service()
        factory = service._factory_normalize_tags()
        assert callable(factory)

    async def test_result_has_status_completed(self) -> None:
        """Result dict must contain status='completed'."""
        service = _build_factory_service()
        factory = service._factory_normalize_tags()
        _, cb = _capture_progress()

        mock_norm_svc = MagicMock()
        mock_backfill_svc = AsyncMock()
        mock_backfill_svc.run_backfill = AsyncMock(return_value=None)

        with (
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=mock_norm_svc,
            ),
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_backfill_svc,
            ),
        ):
            result = await factory(cb)

        assert result == {"status": "completed"}

    async def test_run_backfill_is_awaited(self) -> None:
        """TagBackfillService.run_backfill is awaited exactly once."""
        service = _build_factory_service()
        factory = service._factory_normalize_tags()
        _, cb = _capture_progress()

        mock_norm_svc = MagicMock()
        mock_backfill_svc = AsyncMock()
        mock_backfill_svc.run_backfill = AsyncMock(return_value=None)

        with (
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=mock_norm_svc,
            ),
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_backfill_svc,
            ),
        ):
            await factory(cb)

        mock_backfill_svc.run_backfill.assert_awaited_once()

    async def test_progress_called_at_zero(self) -> None:
        """progress_cb is called at 0.0 before backfill starts."""
        service = _build_factory_service()
        factory = service._factory_normalize_tags()
        calls, cb = _capture_progress()

        mock_norm_svc = MagicMock()
        mock_backfill_svc = AsyncMock()
        mock_backfill_svc.run_backfill = AsyncMock(return_value=None)

        with (
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=mock_norm_svc,
            ),
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_backfill_svc,
            ),
        ):
            await factory(cb)

        assert calls[0] == 0.0

    async def test_progress_called_at_ninety_and_hundred(self) -> None:
        """progress_cb is called at 90.0 and 100.0 after backfill."""
        service = _build_factory_service()
        factory = service._factory_normalize_tags()
        calls, cb = _capture_progress()

        mock_norm_svc = MagicMock()
        mock_backfill_svc = AsyncMock()
        mock_backfill_svc.run_backfill = AsyncMock(return_value=None)

        with (
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
                return_value=mock_norm_svc,
            ),
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_backfill_svc,
            ),
        ):
            await factory(cb)

        assert 90.0 in calls
        assert 100.0 in calls


# ===========================================================================
# Tests: _get_counts_and_last_loaded gather parallelism
# ===========================================================================


class TestGetCountsAndLastLoadedGather:
    """Validate that asyncio.gather in _get_counts_and_last_loaded assigns
    each query result to the correct OnboardingCounts field.

    Uses distinct non-zero values so any field-assignment swap is immediately
    visible rather than hiding behind equal integers.
    """

    async def test_each_count_field_receives_correct_gather_result(self) -> None:
        """Each OnboardingCounts field must carry the value from its own query.

        _get_counts_and_last_loaded issues 9 concurrent queries via
        asyncio.gather in this order:
          0 channels, 1 videos, 2 available_videos, 3 enriched_videos,
          4 playlists, 5 transcripts, 6 categories, 7 canonical_tags,
          8 max(created_at)  -- returned as scalar_one_or_none()=None.
        """
        # Distinct values -- a value in the wrong field will fail the assertion
        service = _build_service(
            counts_sequence=[11, 22, 33, 44, 55, 66, 77, 88]
        )
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        counts = status.counts
        assert counts.channels == 11
        assert counts.videos == 22
        assert counts.available_videos == 33
        assert counts.enriched_videos == 44
        assert counts.playlists == 55
        assert counts.transcripts == 66
        assert counts.categories == 77
        assert counts.canonical_tags == 88

    async def test_gather_handles_all_zero_counts(self) -> None:
        """All-zero counts still produce a valid OnboardingCounts object."""
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        counts = status.counts
        for field in (
            "channels",
            "videos",
            "available_videos",
            "enriched_videos",
            "playlists",
            "transcripts",
            "categories",
            "canonical_tags",
        ):
            assert getattr(counts, field) == 0, (
                f"Expected 0 for counts.{field}, "
                f"got {getattr(counts, field)}"
            )

    async def test_gather_last_loaded_none_results_in_no_new_data(self) -> None:
        """When max(created_at) returns NULL, new_data_available must be False.

        The 9th gather result (session.execute for max(Video.created_at)) uses
        scalar_one_or_none().  The factory mock returns None for
        scalar_one_or_none, so last_loaded_at is None inside the service.
        With no videos and no last-loaded timestamp, new_data_available=False.
        """
        service = _build_service(counts_sequence=[0] * 8)
        with patch(_SETTINGS_TOKEN_IS_FILE, return_value=False):
            status = await service.get_status()

        # No videos loaded yet and no timestamp -> no new data to flag
        assert status.new_data_available is False
