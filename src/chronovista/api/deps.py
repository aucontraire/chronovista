"""FastAPI dependencies for API endpoints."""

from collections.abc import AsyncGenerator

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.auth import youtube_oauth
from chronovista.config.database import db_manager


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
