"""FastAPI application for chronovista API."""

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from chronovista.api.routers import health, preferences, search, sync, transcripts, videos

logger = logging.getLogger(__name__)

# Paths that should not have their details logged (sensitive endpoints)
SENSITIVE_PATHS: frozenset[str] = frozenset({
    "/api/v1/auth",
    "/api/v1/oauth",
    "/api/v1/token",
})


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


def _is_sensitive_path(path: str) -> bool:
    """Check if the path is a sensitive endpoint that should not be logged in detail."""
    return any(path.startswith(sensitive) for sensitive in SENSITIVE_PATHS)


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxied requests."""
    # Check for forwarded headers (common with reverse proxies)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()

    # Fall back to direct client host
    if request.client:
        return request.client.host
    return "unknown"


@app.middleware("http")
async def log_requests(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    """
    Middleware to log incoming requests and outgoing responses.

    Logs request method, path, and client IP at INFO level.
    Logs response status code and timing with appropriate log level:
    - INFO for 2xx/3xx responses
    - WARNING for 4xx responses
    - ERROR for 5xx responses

    Sensitive endpoints (auth, oauth, token) are logged without details.
    """
    start_time = time.perf_counter()

    # Extract request info
    method = request.method
    path = request.url.path
    client_ip = _get_client_ip(request)

    # Log incoming request (skip details for sensitive paths)
    if _is_sensitive_path(path):
        logger.info("Request: %s [sensitive endpoint] from %s", method, client_ip)
    else:
        logger.info("Request: %s %s from %s", method, path, client_ip)

    # Process the request
    response = await call_next(request)

    # Calculate duration
    duration = time.perf_counter() - start_time
    status_code = response.status_code

    # Determine log level based on status code
    if status_code >= 500:
        log_level = logging.ERROR
    elif status_code >= 400:
        log_level = logging.WARNING
    else:
        log_level = logging.INFO

    # Log response (skip path details for sensitive endpoints)
    if _is_sensitive_path(path):
        logger.log(
            log_level,
            "Response: %s [sensitive endpoint] - %d (%.3fs)",
            method,
            status_code,
            duration,
        )
    else:
        logger.log(
            log_level,
            "Response: %s %s - %d (%.3fs)",
            method,
            path,
            status_code,
            duration,
        )

    return response


# Mount routers under /api/v1 prefix (FR-028 versioning)
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(videos.router, prefix="/api/v1", tags=["videos"])
app.include_router(transcripts.router, prefix="/api/v1", tags=["transcripts"])
app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(preferences.router, prefix="/api/v1", tags=["preferences"])
app.include_router(sync.router, prefix="/api/v1", tags=["sync"])
