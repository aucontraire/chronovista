"""Onboarding API schemas for the data onboarding pipeline.

This module defines Pydantic models for the onboarding status endpoint,
representing pipeline steps, aggregate counts, and overall onboarding state.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from chronovista.api.schemas.tasks import BackgroundTask
from chronovista.models.enums import OperationType, PipelineStepStatus


class OnboardingCounts(BaseModel):
    """Aggregate record counts for the onboarding page."""

    model_config = ConfigDict(from_attributes=True)

    channels: int = 0
    videos: int = 0
    enriched_videos: int = 0
    playlists: int = 0
    transcripts: int = 0
    categories: int = 0
    canonical_tags: int = 0


class PipelineStep(BaseModel):
    """A step in the data onboarding pipeline."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    operation_type: OperationType
    description: str
    status: PipelineStepStatus
    dependencies: list[OperationType]
    requires_auth: bool
    metrics: dict[str, int | str]
    error: str | None = None


class OnboardingStatus(BaseModel):
    """Complete onboarding pipeline state for the frontend."""

    model_config = ConfigDict(from_attributes=True)

    steps: list[PipelineStep]
    is_authenticated: bool
    data_export_path: str
    data_export_detected: bool
    new_data_available: bool = False
    active_task: BackgroundTask | None = None
    counts: OnboardingCounts
