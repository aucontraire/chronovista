"""Settings and application configuration endpoints."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista import __version__
from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.responses import (
    ApiResponse,
    ErrorCode,
    ERROR_TITLES,
    ProblemJSONResponse,
    get_error_type_uri,
)
from chronovista.api.schemas.settings import (
    AppInfoResponse,
    CachePurgeResponse,
    CacheStatusResponse,
    DatabaseStats,
    SupportedLanguage,
)
from chronovista.api.schemas.sync import SyncOperationType
from chronovista.api.services.sync_manager import sync_manager
from chronovista.cli.language_commands import LANGUAGE_NAMES
from chronovista.config.settings import settings
from chronovista.db.models import (
    CanonicalTag,
    Channel,
    Playlist,
    TranscriptCorrection,
    Video,
    VideoTranscript,
)
from chronovista.models.enums import LanguageCode
from chronovista.services.image_cache import ImageCacheConfig, ImageCacheService

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Module-level image cache service singleton
# ---------------------------------------------------------------------------
_image_cache_config = ImageCacheConfig(
    cache_dir=settings.cache_dir,
    channels_dir=settings.cache_dir / "images" / "channels",
    videos_dir=settings.cache_dir / "images" / "videos",
)

_image_cache_service = ImageCacheService(config=_image_cache_config)


def _format_size_display(size_bytes: int) -> str:
    """Format byte count as human-readable string.

    Parameters
    ----------
    size_bytes : int
        Size in bytes.

    Returns
    -------
    str
        Human-readable size string (e.g., "23.4 MB").
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


@router.get(
    "/settings/supported-languages",
    response_model=ApiResponse[list[SupportedLanguage]],
    summary="Get all supported language codes",
)
async def get_supported_languages() -> ApiResponse[list[SupportedLanguage]]:
    """Get all supported language codes with display names.

    Returns a sorted list of all supported BCP-47 language codes
    and their human-readable display names. No authentication required.

    Returns
    -------
    ApiResponse[list[SupportedLanguage]]
        Alphabetically sorted list of supported languages.
    """
    languages = [
        SupportedLanguage(
            code=lang.value,
            display_name=LANGUAGE_NAMES.get(lang.value, lang.value),
        )
        for lang in LanguageCode
    ]
    languages.sort(key=lambda lang: lang.display_name)
    return ApiResponse[list[SupportedLanguage]](data=languages)


@router.get(
    "/settings/cache",
    response_model=ApiResponse[CacheStatusResponse],
    dependencies=[Depends(require_auth)],
    summary="Get image cache status and statistics",
)
async def get_cache_status() -> ApiResponse[CacheStatusResponse]:
    """Get image cache status and statistics.

    Returns counts for cached channel and video images, total disk usage,
    and timestamps for the oldest and newest cached files.

    Returns
    -------
    ApiResponse[CacheStatusResponse]
        Cache statistics including counts, size, and file timestamps.
    """
    # ImageCacheService.get_stats() uses pathlib.rglob which fails on Docker
    # overlayfs with many prefix directories.  Use os.walk instead.
    channel_count = 0
    video_count = 0
    total_size_bytes = 0
    oldest_mtime: float | None = None
    newest_mtime: float | None = None

    def _update_mtime(mtime: float) -> None:
        nonlocal oldest_mtime, newest_mtime
        if oldest_mtime is None or mtime < oldest_mtime:
            oldest_mtime = mtime
        if newest_mtime is None or mtime > newest_mtime:
            newest_mtime = mtime

    channels_dir = _image_cache_config.channels_dir
    if channels_dir.is_dir():
        for entry in os.scandir(channels_dir):
            if entry.name.endswith(".jpg") and entry.is_file():
                channel_count += 1
                stat = entry.stat()
                total_size_bytes += stat.st_size
                _update_mtime(stat.st_mtime)

    videos_dir = _image_cache_config.videos_dir
    if videos_dir.is_dir():
        for root, _dirs, files in os.walk(videos_dir):
            for fname in files:
                if fname.endswith(".jpg"):
                    video_count += 1
                    fpath = os.path.join(root, fname)
                    try:
                        stat = os.stat(fpath)
                        total_size_bytes += stat.st_size
                        _update_mtime(stat.st_mtime)
                    except OSError:
                        pass

    oldest_file = (
        datetime.fromtimestamp(oldest_mtime) if oldest_mtime is not None else None
    )
    newest_file = (
        datetime.fromtimestamp(newest_mtime) if newest_mtime is not None else None
    )

    response = CacheStatusResponse(
        channel_count=channel_count,
        video_count=video_count,
        total_count=channel_count + video_count,
        total_size_bytes=total_size_bytes,
        total_size_display=_format_size_display(total_size_bytes),
        oldest_file=oldest_file,
        newest_file=newest_file,
    )
    return ApiResponse[CacheStatusResponse](data=response)


@router.delete(
    "/settings/cache",
    response_model=ApiResponse[CachePurgeResponse],
    dependencies=[Depends(require_auth)],
    summary="Clear the local image cache",
)
async def clear_cache() -> ApiResponse[CachePurgeResponse] | ProblemJSONResponse:
    """Clear the local image cache.

    Purges all cached channel and video thumbnail images from disk.
    The cache directories themselves are preserved.

    Returns
    -------
    ApiResponse[CachePurgeResponse]
        Confirmation that the cache was purged.
    """
    try:
        await _image_cache_service.purge(type_="all")
        response = CachePurgeResponse(
            purged=True,
            message="Image cache cleared successfully",
        )
        return ApiResponse[CachePurgeResponse](data=response)
    except Exception as exc:
        logger.exception("Failed to clear image cache: %s", exc)
        return ProblemJSONResponse(
            status_code=500,
            content={
                "type": get_error_type_uri(ErrorCode.INTERNAL_ERROR),
                "title": ERROR_TITLES[ErrorCode.INTERNAL_ERROR],
                "status": 500,
                "detail": f"Failed to clear image cache: {exc}",
                "instance": "/api/v1/settings/cache",
                "code": ErrorCode.INTERNAL_ERROR.value,
                "request_id": str(uuid.uuid4()),
            },
        )


@router.get(
    "/settings/app-info",
    response_model=ApiResponse[AppInfoResponse],
    summary="Get application version, database stats, and sync timestamps",
    dependencies=[Depends(require_auth)],
)
async def get_app_info(
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[AppInfoResponse]:
    """Get application version and system information.

    Returns backend/frontend versions, aggregate database record counts,
    and the last successful sync timestamp for each sync operation type.

    Parameters
    ----------
    session : AsyncSession
        Database session injected via FastAPI dependency.

    Returns
    -------
    ApiResponse[AppInfoResponse]
        Application info including versions, database stats, and sync timestamps.
    """
    # Query counts for each table
    video_count = await session.scalar(
        select(func.count()).select_from(Video)
    )
    channel_count = await session.scalar(
        select(func.count()).select_from(Channel)
    )
    playlist_count = await session.scalar(
        select(func.count()).select_from(Playlist)
    )
    transcript_count = await session.scalar(
        select(func.count()).select_from(VideoTranscript)
    )
    correction_count = await session.scalar(
        select(func.count()).select_from(TranscriptCorrection)
    )
    canonical_tag_count = await session.scalar(
        select(func.count()).select_from(CanonicalTag)
    )

    database_stats = DatabaseStats(
        videos=video_count or 0,
        channels=channel_count or 0,
        playlists=playlist_count or 0,
        transcripts=transcript_count or 0,
        corrections=correction_count or 0,
        canonical_tags=canonical_tag_count or 0,
    )

    # Gather last successful sync timestamps
    sync_types = [
        SyncOperationType.SUBSCRIPTIONS,
        SyncOperationType.VIDEOS,
        SyncOperationType.TRANSCRIPTS,
        SyncOperationType.PLAYLISTS,
        SyncOperationType.TOPICS,
    ]
    sync_timestamps: dict[str, Optional[datetime]] = {
        op_type.value: sync_manager.get_last_successful_sync(op_type)
        for op_type in sync_types
    }

    app_info = AppInfoResponse(
        backend_version=__version__,
        frontend_version="0.18.0",
        database_stats=database_stats,
        sync_timestamps=sync_timestamps,
    )

    return ApiResponse[AppInfoResponse](data=app_info)
