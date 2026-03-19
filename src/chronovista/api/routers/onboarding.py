"""Onboarding pipeline endpoints.

This module provides the REST API endpoint for querying the data onboarding
pipeline status, including step statuses, record counts, authentication
state, and any active background task.

Endpoints
---------
- GET /onboarding/status - Get current onboarding pipeline status
"""

from __future__ import annotations

from fastapi import APIRouter

from chronovista.api.schemas.onboarding import OnboardingStatus
from chronovista.api.services.task_manager import TaskManager
from chronovista.config.database import db_manager
from chronovista.services.onboarding_service import OnboardingService

router = APIRouter()

# Module-level singletons: TaskManager is shared across all onboarding
# and task endpoints; OnboardingService wraps the task manager and a
# session factory.
_task_manager = TaskManager()
_onboarding_service: OnboardingService | None = None


def _get_onboarding_service() -> OnboardingService:
    """Return the module-level OnboardingService singleton.

    Lazily initialised so that ``db_manager`` has been configured by the
    time the first request arrives.

    Returns
    -------
    OnboardingService
        The shared onboarding service instance.
    """
    global _onboarding_service  # noqa: PLW0603
    if _onboarding_service is None:
        _onboarding_service = OnboardingService(
            task_manager=_task_manager,
            session_factory=db_manager.get_session_factory(),
        )
    return _onboarding_service


@router.get(
    "/onboarding/status",
    response_model=OnboardingStatus,
)
async def get_onboarding_status() -> OnboardingStatus:
    """Return the current onboarding pipeline status.

    Queries the database for aggregate record counts, checks filesystem
    and authentication state, computes step statuses, and reports any
    active background task.

    Returns
    -------
    OnboardingStatus
        Complete pipeline state including steps, counts, auth status,
        data export detection, and active task information.
    """
    service = _get_onboarding_service()
    return await service.get_status()
