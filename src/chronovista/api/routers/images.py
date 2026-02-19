"""Image cache proxy endpoints.

This module provides REST API endpoints for serving cached YouTube
thumbnail images:

- GET /images/channels/{channel_id} — Serve channel thumbnail (public)
- GET /images/videos/{video_id} — Serve video thumbnail (public)

All image endpoints are public (no authentication required) and return
binary image responses or SVG placeholders.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from chronovista.api.deps import get_db
from chronovista.config.settings import settings
from chronovista.models.enums import ImageQuality
from chronovista.services.image_cache import ImageCacheConfig, ImageCacheService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router — no auth dependency (images are public)
# ---------------------------------------------------------------------------
router = APIRouter(tags=["images"])

# ---------------------------------------------------------------------------
# Module-level service singleton
# ---------------------------------------------------------------------------
_image_cache_config = ImageCacheConfig(
    cache_dir=settings.cache_dir,
    channels_dir=settings.cache_dir / "images" / "channels",
    videos_dir=settings.cache_dir / "images" / "videos",
)

_image_cache_service = ImageCacheService(config=_image_cache_config)


@router.get(
    "/images/channels/{channel_id}",
    responses={
        200: {
            "content": {
                "image/jpeg": {},
                "image/png": {},
                "image/webp": {},
                "image/svg+xml": {},
            },
            "description": "Channel thumbnail image or SVG placeholder",
        },
        422: {"description": "Invalid channel ID format"},
    },
    response_class=Response,
)
async def get_channel_image(
    channel_id: str = Path(
        ...,
        min_length=24,
        max_length=24,
        pattern=r"^UC[A-Za-z0-9_-]+$",
        description="YouTube channel ID (24 characters, starts with UC)",
    ),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Serve a channel thumbnail image from local cache.

    Returns the cached image if available, fetches and caches on first
    request, or returns an SVG placeholder if the image cannot be
    obtained.

    Parameters
    ----------
    channel_id : str
        YouTube channel ID (exactly 24 characters, starts with ``UC``).
    db : AsyncSession
        Database session for thumbnail URL lookup.

    Returns
    -------
    Response
        Image bytes with appropriate Content-Type, Cache-Control, and
        X-Cache headers.
    """
    return await _image_cache_service.get_channel_image(
        session=db,
        channel_id=channel_id,
    )


# ---------------------------------------------------------------------------
# Valid quality values (derived from ImageQuality enum)
# ---------------------------------------------------------------------------
_VALID_QUALITIES = {q.value for q in ImageQuality}


@router.get(
    "/images/videos/{video_id}",
    responses={
        200: {
            "content": {
                "image/jpeg": {},
                "image/png": {},
                "image/webp": {},
                "image/svg+xml": {},
            },
            "description": "Video thumbnail image or SVG placeholder",
        },
        422: {"description": "Invalid video ID format or quality value"},
    },
    response_class=Response,
)
async def get_video_image(
    video_id: str = Path(
        ...,
        min_length=11,
        max_length=11,
        pattern=r"^[A-Za-z0-9_-]{11}$",
        description="YouTube video ID (exactly 11 characters)",
    ),
    quality: str = Query(
        default="mqdefault",
        description=(
            "Thumbnail quality level. Valid values: "
            + ", ".join(sorted(q.value for q in ImageQuality))
        ),
    ),
) -> Response:
    """Serve a video thumbnail image from local cache.

    Returns the cached image if available, fetches and caches on first
    request, or returns an SVG placeholder if the image cannot be
    obtained. Video thumbnails use deterministic YouTube URLs (no DB
    lookup required).

    Parameters
    ----------
    video_id : str
        YouTube video ID (exactly 11 characters).
    quality : str
        Thumbnail quality level (default ``"mqdefault"``). Must be one
        of: ``default``, ``mqdefault``, ``hqdefault``, ``sddefault``,
        ``maxresdefault``.

    Returns
    -------
    Response
        Image bytes with appropriate Content-Type, Cache-Control, and
        X-Cache headers.
    """
    if quality not in _VALID_QUALITIES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid quality '{quality}'. "
                f"Valid values: {', '.join(sorted(_VALID_QUALITIES))}"
            ),
        )

    return await _image_cache_service.get_video_image(
        video_id=video_id,
        quality=quality,
    )
