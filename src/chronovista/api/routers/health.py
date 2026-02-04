"""Health check endpoint - no authentication required."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from chronovista import __version__
from chronovista.api.schemas.responses import ApiResponse
from chronovista.auth import youtube_oauth
from chronovista.config.database import db_manager


class HealthChecks(BaseModel):
    """Individual health check results."""

    model_config = ConfigDict(strict=True)

    database_latency_ms: Optional[int] = None
    token_expiry_hours: Optional[float] = None


class HealthStatus(BaseModel):
    """Application health status."""

    model_config = ConfigDict(strict=True)

    status: str  # "healthy", "degraded", "unhealthy"
    version: str  # chronovista version
    database: str  # "connected", "disconnected"
    authenticated: bool  # OAuth tokens valid
    timestamp: datetime
    checks: Optional[HealthChecks] = None


class HealthResponse(ApiResponse[HealthStatus]):
    """Response for health check endpoint."""

    pass


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint - no authentication required.

    Returns application health status including:
    - Database connectivity
    - OAuth authentication status
    - Application version
    """
    # Check database connectivity
    db_status = "disconnected"
    db_latency_ms: Optional[int] = None
    try:
        start = time.monotonic()
        async for session in db_manager.get_session():
            await session.execute(text("SELECT 1"))
            break
        db_latency_ms = int((time.monotonic() - start) * 1000)
        db_status = "connected"
    except Exception:
        pass

    # Check authentication
    authenticated = youtube_oauth.is_authenticated()

    # Determine overall status
    if db_status == "disconnected" or (db_latency_ms and db_latency_ms > 5000):
        status = "unhealthy"
    elif authenticated:
        # TODO: Check token expiry for degraded status
        status = "healthy"
    else:
        status = "healthy"  # Auth not required for health

    health_data = HealthStatus(
        status=status,
        version=__version__,
        database=db_status,
        authenticated=authenticated,
        timestamp=datetime.now(timezone.utc),
        checks=HealthChecks(
            database_latency_ms=db_latency_ms,
        ),
    )

    return HealthResponse(data=health_data)
