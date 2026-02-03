"""FastAPI application for chronovista API."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from chronovista.api.routers import health, preferences, search, sync, transcripts, videos


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="Chronovista API",
    description="RESTful API for accessing YouTube video metadata, transcripts, and preferences",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount routers under /api/v1 prefix (FR-028 versioning)
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(videos.router, prefix="/api/v1", tags=["videos"])
app.include_router(transcripts.router, prefix="/api/v1", tags=["transcripts"])
app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(preferences.router, prefix="/api/v1", tags=["preferences"])
app.include_router(sync.router, prefix="/api/v1", tags=["sync"])
