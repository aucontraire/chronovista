"""FastAPI application for chronovista API."""

import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, Response

from chronovista.api.exception_handlers import register_exception_handlers
from chronovista.api.middleware import (
    RequestIdFilter,
    RequestIdMiddleware,
    get_request_id,
)
from chronovista.api.routers import (
    batch_corrections,
    canonical_tags,
    categories,
    channels,
    entity_mentions,
    health,
    images,
    onboarding,
    playlists,
    preferences,
    search,
    settings,
    sidebar,
    sync,
    tags,
    tasks,
    topics,
    transcript_corrections,
    transcripts,
    videos,
)

# Ensure application-level logs (chronovista.*) reach stdout/stderr.
# Without this, only uvicorn's access logs appear in Docker.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

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
    # Startup — wire the tasks router with the shared TaskManager and
    # OnboardingService singletons owned by the onboarding router.
    tasks.configure(
        task_manager=onboarding._task_manager,
        onboarding_service=onboarding._get_onboarding_service(),
    )
    yield
    # Shutdown


app = FastAPI(
    title="Chronovista API",
    description="RESTful API for accessing YouTube video metadata, transcripts, and preferences",
    version="1.0.0",
    lifespan=lifespan,
)

# Determine if static files should be served (production/Docker mode)
_serve_static = os.getenv("SERVE_STATIC", "").lower() == "true"
_static_dir = Path("static")

# CORS configuration for frontend development
# Only needed when frontend runs on a separate dev server (not serving static)
if not _serve_static:
    # Get frontend port from environment variable with default
    _frontend_port = os.getenv("CHRONOVISTA_FRONTEND_PORT", "8766")

    # CORS origins for development (localhost and 127.0.0.1)
    _cors_origins = [
        f"http://localhost:{_frontend_port}",
        f"http://127.0.0.1:{_frontend_port}",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Register Request ID middleware early in the chain
# This ensures request ID is available throughout request processing
# Note: Middleware is applied in reverse order of registration,
# so this will execute first (before log_requests middleware)
app.add_middleware(RequestIdMiddleware)


@app.middleware("http")
async def add_security_headers(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    """Add security headers to every response.

    These headers instruct browsers to enforce security policies that
    mitigate clickjacking, MIME-type sniffing, and cross-site attacks.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    # CSP: allow self-origin resources; inline styles needed for Rich/Tailwind;
    # YouTube IFrame API requires script-src + frame-src for youtube.com
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://www.youtube.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' https://i.ytimg.com https://img.youtube.com https://yt3.ggpht.com https://i9.ytimg.com data:; "
        "frame-src https://www.youtube-nocookie.com https://www.youtube.com; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'"
    )
    return response

# Register centralized exception handlers for consistent error responses
register_exception_handlers(app)

# Configure logging to include request_id in all log records
# Add the filter to the root logger so all handlers inherit it
_request_id_filter = RequestIdFilter()
for handler in logging.root.handlers:
    handler.addFilter(_request_id_filter)
# Also add to the API logger specifically
logging.getLogger("chronovista.api").addFilter(_request_id_filter)


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

    Logs request method, path, client IP, and request ID at INFO level.
    Logs response status code and timing with appropriate log level:
    - INFO for 2xx/3xx responses
    - WARNING for 4xx responses
    - ERROR for 5xx responses

    Sensitive endpoints (auth, oauth, token) are logged without details.

    Note: This middleware runs after RequestIdMiddleware, so request_id
    is available via get_request_id() or request.state.request_id.
    """
    start_time = time.perf_counter()

    # Extract request info
    method = request.method
    path = request.url.path
    client_ip = _get_client_ip(request)
    request_id = get_request_id()

    # Log incoming request (skip details for sensitive paths)
    if _is_sensitive_path(path):
        logger.info(
            "Request: %s [sensitive endpoint] from %s [%s]",
            method, client_ip, request_id
        )
    else:
        logger.info(
            "Request: %s %s from %s [%s]",
            method, path, client_ip, request_id
        )

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
            "Response: %s [sensitive endpoint] - %d (%.3fs) [%s]",
            method,
            status_code,
            duration,
            request_id,
        )
    else:
        logger.log(
            log_level,
            "Response: %s %s - %d (%.3fs) [%s]",
            method,
            path,
            status_code,
            duration,
            request_id,
        )

    return response


# Mount routers under /api/v1 prefix (FR-028 versioning)
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(channels.router, prefix="/api/v1", tags=["channels"])
app.include_router(playlists.router, prefix="/api/v1", tags=["playlists"])
app.include_router(topics.router, prefix="/api/v1", tags=["topics"])
app.include_router(categories.router, prefix="/api/v1", tags=["categories"])
app.include_router(tags.router, prefix="/api/v1", tags=["tags"])
app.include_router(canonical_tags.router, prefix="/api/v1", tags=["canonical-tags"])
app.include_router(videos.router, prefix="/api/v1", tags=["videos"])
app.include_router(transcripts.router, prefix="/api/v1", tags=["transcripts"])
app.include_router(transcript_corrections.router, prefix="/api/v1", tags=["transcript-corrections"])
app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(preferences.router, prefix="/api/v1", tags=["preferences"])
app.include_router(sync.router, prefix="/api/v1", tags=["sync"])
app.include_router(sidebar.router, prefix="/api/v1", tags=["sidebar"])
app.include_router(images.router, prefix="/api/v1", tags=["images"])
app.include_router(entity_mentions.router, prefix="/api/v1", tags=["entity-mentions"])
app.include_router(batch_corrections.router, prefix="/api/v1/corrections/batch", tags=["batch-corrections"])
app.include_router(settings.router, prefix="/api/v1", tags=["settings"])
app.include_router(onboarding.router, prefix="/api/v1", tags=["onboarding"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])

# Conditionally mount static files and SPA catch-all for production/Docker mode
# This MUST be registered AFTER all API routers so API routes take priority
if _serve_static and _static_dir.exists():
    app.mount("/assets", StaticFiles(directory="static/assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        """
        Serve index.html for all non-API routes (SPA client-side routing).

        This catch-all handles React Router paths like /onboarding, /channels,
        /videos/123, etc. API routes, /docs, /redoc, and /openapi.json continue
        to work because they are registered before this catch-all.
        """
        return FileResponse("static/index.html")
