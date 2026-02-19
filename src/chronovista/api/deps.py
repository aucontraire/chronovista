"""FastAPI dependencies for API endpoints."""

from collections.abc import AsyncGenerator

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.auth import youtube_oauth
from chronovista.config.database import db_manager
from chronovista.config.settings import settings
from chronovista.services.recovery.cdx_client import CDXClient, RateLimiter
from chronovista.services.recovery.page_parser import PageParser

# Module-level singleton: shared across all recovery API calls
_recovery_rate_limiter = RateLimiter(rate=40.0)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for database session.

    Yields an async SQLAlchemy session that auto-commits on success
    and rolls back on exception.

    Yields
    ------
    AsyncSession
        An async SQLAlchemy session for database operations.
    """
    async for session in db_manager.get_session():
        yield session


async def require_auth() -> None:
    """
    Dependency to require OAuth authentication.

    Raises HTTPException 401 if user is not authenticated via CLI.
    Health endpoint should NOT use this dependency.

    Raises
    ------
    HTTPException
        401 Unauthorized if user is not authenticated.
    """
    if not youtube_oauth.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "NOT_AUTHENTICATED",
                "message": "Not authenticated. Run: chronovista auth login",
            },
        )


def get_recovery_deps() -> tuple[CDXClient, PageParser, RateLimiter]:
    """
    Dependency for recovery service components.

    Creates a CDXClient and PageParser per-call (they hold no
    request-scoped state) and returns the module-level RateLimiter
    singleton so that all recovery API calls share one token bucket.

    Returns
    -------
    tuple[CDXClient, PageParser, RateLimiter]
        A 3-tuple of (cdx_client, page_parser, rate_limiter) that
        recovery endpoints can unpack for use with the orchestrator.
    """
    cache_dir = settings.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    cdx_client = CDXClient(cache_dir=cache_dir)
    page_parser = PageParser(rate_limiter=_recovery_rate_limiter)

    return cdx_client, page_parser, _recovery_rate_limiter
