"""Task API schemas for background task tracking.

This module defines Pydantic models for the task management endpoints,
supporting the onboarding pipeline's background task execution.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from chronovista.models.enums import OperationType, TaskStatus


class TaskCreate(BaseModel):
    """Request to start a pipeline operation."""

    operation_type: OperationType


class BackgroundTask(BaseModel):
    """A background task tracked by the in-memory TaskManager."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    operation_type: OperationType
    status: TaskStatus
    progress: float = 0.0
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
