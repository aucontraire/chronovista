"""
Image cache proxy service for YouTube thumbnails.

Provides local caching of channel and video thumbnail images with
automatic fetching, content-type detection via magic bytes, atomic
writes, and placeholder SVG generation for missing images.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import Video as VideoDB

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Maximum image size: 5 MB (FR-029)
# ---------------------------------------------------------------------------
_MAX_IMAGE_BYTES = 5 * 1024 * 1024

# ---------------------------------------------------------------------------
# Minimum image size: 1024 bytes (FR-025 — corrupted file detection)
# ---------------------------------------------------------------------------
_MIN_IMAGE_BYTES = 1024

# ---------------------------------------------------------------------------
# Cache-Control headers
# ---------------------------------------------------------------------------
_CACHE_CONTROL_HIT = "public, max-age=604800, immutable"  # 7 days
_CACHE_CONTROL_PLACEHOLDER = "public, max-age=3600"  # 1 hour


# ---------------------------------------------------------------------------
# Placeholder SVGs
# ---------------------------------------------------------------------------
_CHANNEL_PLACEHOLDER_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" '
    b'viewBox="0 0 240 240">'
    b'<rect width="240" height="240" fill="#e2e8f0" rx="120"/>'
    b'<circle cx="120" cy="96" r="40" fill="#94a3b8"/>'
    b'<ellipse cx="120" cy="196" rx="64" ry="48" fill="#94a3b8"/>'
    b"</svg>"
)

_VIDEO_PLACEHOLDER_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" '
    b'viewBox="0 0 320 180">'
    b'<rect width="320" height="180" fill="#e2e8f0"/>'
    b'<polygon points="128,60 128,120 192,90" fill="#94a3b8"/>'
    b"</svg>"
)


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Pydantic V2 models                                                ║
# ╚══════════════════════════════════════════════════════════════════════╝


class ImageCacheConfig(BaseModel):
    """Configuration for the image cache proxy.

    Attributes
    ----------
    cache_dir : Path
        Root cache directory (e.g. ``./cache``).
    channels_dir : Path
        Derived directory for channel thumbnails.
    videos_dir : Path
        Derived directory for video thumbnails.
    on_demand_timeout : float
        HTTP timeout in seconds for proxy endpoint cache misses (NFR-001).
    warm_timeout : float
        HTTP timeout in seconds for CLI warming operations (NFR-001).
    max_concurrent_fetches : int
        Maximum concurrent HTTP fetches (semaphore limit).
    """

    cache_dir: Path
    channels_dir: Path
    videos_dir: Path
    on_demand_timeout: float = 2.0
    warm_timeout: float = 10.0
    max_concurrent_fetches: int = 5


class CacheStats(BaseModel):
    """Statistics about the image cache contents.

    Attributes
    ----------
    channel_count : int
        Number of cached channel images.
    channel_missing_count : int
        Number of channel .missing markers.
    video_count : int
        Number of cached video images.
    video_missing_count : int
        Number of video .missing markers.
    total_size_bytes : int
        Total disk usage for all cached images.
    oldest_file : datetime | None
        Modification time of the oldest cached file.
    newest_file : datetime | None
        Modification time of the newest cached file.
    """

    channel_count: int
    channel_missing_count: int
    video_count: int
    video_missing_count: int
    total_size_bytes: int
    oldest_file: datetime | None
    newest_file: datetime | None


class WarmResult(BaseModel):
    """Result of a cache-warming operation.

    Attributes
    ----------
    downloaded : int
        Number of images successfully downloaded.
    skipped : int
        Number of images already cached (skipped).
    failed : int
        Number of images that failed to download.
    no_url : int
        Number of entities with no thumbnail URL.
    total : int
        Total number of entities processed.
    """

    downloaded: int
    skipped: int
    failed: int
    no_url: int
    total: int


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  ImageCacheService                                                  ║
# ╚══════════════════════════════════════════════════════════════════════╝


class ImageCacheService:
    """Proxy service that caches YouTube thumbnail images locally.

    The service stores images on the local filesystem with atomic writes,
    detects content types via magic bytes, and serves SVG placeholders
    when an image is unavailable.

    Parameters
    ----------
    config : ImageCacheConfig
        Cache configuration including directory paths and timeouts.
    """

    def __init__(self, config: ImageCacheConfig) -> None:
        self._config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent_fetches)
        self._passthrough = False
        self.ensure_directories()

    # ------------------------------------------------------------------
    # Directory management (FR-030)
    # ------------------------------------------------------------------

    def ensure_directories(self) -> None:
        """Create cache directories if they do not exist.

        If directory creation fails, the service falls back to passthrough
        mode where every request returns a placeholder.
        """
        try:
            self._config.channels_dir.mkdir(parents=True, exist_ok=True)
            self._config.videos_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(
                "Image cache directories ready: channels=%s, videos=%s",
                self._config.channels_dir,
                self._config.videos_dir,
            )
        except OSError:
            logger.error(
                "Failed to create image cache directories; "
                "falling back to passthrough mode",
                exc_info=True,
            )
            self._passthrough = True

    # ------------------------------------------------------------------
    # Placeholder generation
    # ------------------------------------------------------------------

    @staticmethod
    def _serve_placeholder(entity_type: str) -> Response:
        """Return an SVG placeholder response.

        Parameters
        ----------
        entity_type : str
            Either ``"channel"`` or ``"video"``.

        Returns
        -------
        Response
            SVG placeholder with appropriate headers.
        """
        svg_bytes = (
            _CHANNEL_PLACEHOLDER_SVG
            if entity_type == "channel"
            else _VIDEO_PLACEHOLDER_SVG
        )
        return Response(
            content=svg_bytes,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": _CACHE_CONTROL_PLACEHOLDER,
                "X-Cache": "PLACEHOLDER",
            },
        )

    # ------------------------------------------------------------------
    # Content-type detection via magic bytes
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_content_type(file_path: Path) -> str:
        """Detect image content type by reading magic bytes.

        Parameters
        ----------
        file_path : Path
            Path to the image file on disk.

        Returns
        -------
        str
            MIME type string (``image/jpeg``, ``image/png``, ``image/webp``,
            or ``image/jpeg`` as fallback).
        """
        try:
            with file_path.open("rb") as f:
                header = f.read(12)
        except OSError:
            return "image/jpeg"

        if header[:2] == b"\xff\xd8":
            return "image/jpeg"
        if header[:4] == b"\x89PNG":
            return "image/png"
        if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

    # ------------------------------------------------------------------
    # Fetch pipeline
    # ------------------------------------------------------------------

    async def _fetch_and_cache(
        self,
        url: str,
        cache_path: Path,
        timeout: float,
    ) -> tuple[bool, str | None]:
        """Fetch an image from *url* and write it to *cache_path* atomically.

        Parameters
        ----------
        url : str
            Remote image URL to fetch.
        cache_path : Path
            Local path where the image should be stored.
        timeout : float
            HTTP request timeout in seconds.

        Returns
        -------
        tuple[bool, str | None]
            ``(True, None)`` on success, or ``(False, reason)`` on failure.
        """
        async with self._semaphore:
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=timeout,
                ) as client:
                    response = await client.get(url)
            except httpx.TimeoutException:
                logger.warning("Timeout fetching image: %s", url)
                return False, "timeout"
            except httpx.HTTPError as exc:
                logger.warning("HTTP error fetching image %s: %s", url, exc)
                return False, f"http_error: {exc}"

        status_code = response.status_code

        # 404 / 410 → create .missing marker (FR-006)
        if status_code in (404, 410):
            logger.info("Image not found (%d) at %s; creating .missing marker", status_code, url)
            self._create_missing_marker(cache_path)
            return False, f"not_found_{status_code}"

        # 429 / 5xx → transient failure, do NOT create .missing
        if status_code == 429 or status_code >= 500:
            logger.warning(
                "Transient error %d fetching image %s; no .missing marker",
                status_code,
                url,
            )
            return False, f"server_error_{status_code}"

        # Non-200 → generic failure
        if status_code != 200:
            logger.warning("Unexpected status %d fetching image %s", status_code, url)
            return False, f"unexpected_status_{status_code}"

        # Validate Content-Type contains "image/"
        content_type = response.headers.get("content-type", "")
        if "image/" not in content_type:
            logger.warning(
                "Non-image content-type '%s' from %s", content_type, url
            )
            return False, f"invalid_content_type: {content_type}"

        body = response.content

        # Validate body size (FR-025, FR-029)
        if len(body) < _MIN_IMAGE_BYTES:
            logger.warning(
                "Image too small (%d bytes) from %s", len(body), url
            )
            return False, f"too_small_{len(body)}"

        if len(body) > _MAX_IMAGE_BYTES:
            logger.warning(
                "Image too large (%d bytes) from %s", len(body), url
            )
            return False, f"too_large_{len(body)}"

        # Atomic write: temp file → rename (POSIX atomic rename)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_name(
                f".{cache_path.stem}.tmp.{uuid4()}"
            )
            tmp_path.write_bytes(body)
            tmp_path.rename(cache_path)
            logger.info("Cached image: %s (%d bytes)", cache_path, len(body))
            return True, None
        except OSError:
            logger.error(
                "Disk error writing cached image to %s",
                cache_path,
                exc_info=True,
            )
            return False, "disk_error"

    # ------------------------------------------------------------------
    # Cache state management
    # ------------------------------------------------------------------

    @staticmethod
    def _get_cache_path(
        entity_type: str,
        entity_id: str,
        quality: str | None = None,
        *,
        channels_dir: Path | None = None,
        videos_dir: Path | None = None,
    ) -> Path:
        """Compute the on-disk cache path for an entity image.

        Parameters
        ----------
        entity_type : str
            ``"channel"`` or ``"video"``.
        entity_id : str
            Entity identifier (channel ID or video ID).
        quality : str | None
            Quality suffix for video thumbnails (e.g. ``"hqdefault"``).
        channels_dir : Path | None
            Override channels directory (used internally).
        videos_dir : Path | None
            Override videos directory (used internally).

        Returns
        -------
        Path
            Absolute path where the image should be cached.
        """
        if entity_type == "channel":
            assert channels_dir is not None
            return channels_dir / f"{entity_id}.jpg"
        else:
            assert videos_dir is not None
            prefix = entity_id[:2] if len(entity_id) >= 2 else entity_id
            q = quality or "hqdefault"
            return videos_dir / prefix / f"{entity_id}_{q}.jpg"

    def _resolve_cache_path(
        self,
        entity_type: str,
        entity_id: str,
        quality: str | None = None,
    ) -> Path:
        """Resolve cache path using the service's configured directories.

        Parameters
        ----------
        entity_type : str
            ``"channel"`` or ``"video"``.
        entity_id : str
            Entity identifier.
        quality : str | None
            Quality suffix for video thumbnails.

        Returns
        -------
        Path
            Absolute path where the image should be cached.
        """
        return self._get_cache_path(
            entity_type,
            entity_id,
            quality,
            channels_dir=self._config.channels_dir,
            videos_dir=self._config.videos_dir,
        )

    @staticmethod
    def _get_missing_path(cache_path: Path) -> Path:
        """Get the ``.missing`` marker path for a given cache path.

        Parameters
        ----------
        cache_path : Path
            The image cache path (e.g. ``channels/UCxxx.jpg``).

        Returns
        -------
        Path
            Corresponding ``.missing`` marker path.
        """
        return cache_path.with_suffix(".missing")

    def _create_missing_marker(self, cache_path: Path) -> None:
        """Create a zero-byte ``.missing`` marker file.

        Parameters
        ----------
        cache_path : Path
            The image cache path whose marker to create.
        """
        missing_path = self._get_missing_path(cache_path)
        try:
            missing_path.parent.mkdir(parents=True, exist_ok=True)
            missing_path.touch()
        except OSError:
            logger.error(
                "Failed to create .missing marker at %s",
                missing_path,
                exc_info=True,
            )

    @staticmethod
    def _check_cache(cache_path: Path) -> str | None:
        """Check whether a cached image file exists and is valid.

        If the file exists but is smaller than the minimum size threshold,
        it is considered corrupted and is deleted.

        Parameters
        ----------
        cache_path : Path
            Path to the cached image file.

        Returns
        -------
        str | None
            ``"HIT"`` if a valid cached file exists, ``None`` otherwise.
        """
        if not cache_path.is_file():
            return None
        if cache_path.stat().st_size < _MIN_IMAGE_BYTES:
            logger.warning(
                "Corrupted cache file (too small), deleting: %s", cache_path
            )
            try:
                cache_path.unlink()
            except OSError:
                pass
            return None
        return "HIT"

    @staticmethod
    def _check_missing(cache_path: Path) -> bool:
        """Check whether a ``.missing`` marker exists for the given cache path.

        Parameters
        ----------
        cache_path : Path
            The image cache path to check.

        Returns
        -------
        bool
            ``True`` if a ``.missing`` marker is present.
        """
        return cache_path.with_suffix(".missing").is_file()

    # ------------------------------------------------------------------
    # Serve a cached file as a Response
    # ------------------------------------------------------------------

    def _serve_cached_file(self, cache_path: Path, cache_status: str) -> Response:
        """Serve a cached image file as a Starlette ``Response``.

        Parameters
        ----------
        cache_path : Path
            Path to the cached image on disk.
        cache_status : str
            Value for the ``X-Cache`` response header (e.g. ``"HIT"`` or
            ``"MISS"``).

        Returns
        -------
        Response
            Image response with correct Content-Type, Cache-Control, and
            X-Cache headers.
        """
        content_type = self._detect_content_type(cache_path)
        body = cache_path.read_bytes()
        return Response(
            content=body,
            media_type=content_type,
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": cache_status,
            },
        )

    # ------------------------------------------------------------------
    # Public API: get_channel_image (T006)
    # ------------------------------------------------------------------

    async def get_channel_image(
        self,
        session: AsyncSession,
        channel_id: str,
    ) -> Response:
        """Serve a channel thumbnail image, fetching and caching on miss.

        Flow:
        1. Check local cache (HIT -> serve with 7-day immutable).
        2. Check ``.missing`` marker -> serve placeholder.
        3. Look up ``thumbnail_url`` via DB query.
        4. If channel not found or URL is NULL -> serve placeholder.
        5. Fetch and cache.
        6. On success -> serve cached file (X-Cache: MISS).
        7. On failure -> serve placeholder (X-Cache: PLACEHOLDER).

        Parameters
        ----------
        session : AsyncSession
            Database session for looking up the channel's thumbnail URL.
        channel_id : str
            YouTube channel ID (24 characters, starts with UC).

        Returns
        -------
        Response
            Image response (JPEG/PNG/WebP) or SVG placeholder.
        """
        if self._passthrough:
            return self._serve_placeholder("channel")

        cache_path = self._resolve_cache_path("channel", channel_id)

        # 1. Cache HIT
        cache_status = self._check_cache(cache_path)
        if cache_status == "HIT":
            logger.debug("Cache HIT for channel image: %s", channel_id)
            return self._serve_cached_file(cache_path, "HIT")

        # 2. .missing marker
        if self._check_missing(cache_path):
            logger.debug(
                "Missing marker found for channel image: %s", channel_id
            )
            return self._serve_placeholder("channel")

        # 3. Look up thumbnail_url from DB
        result = await session.execute(
            select(ChannelDB.thumbnail_url).where(
                ChannelDB.channel_id == channel_id
            )
        )
        row = result.first()

        # 4. Channel not found or no thumbnail URL
        if row is None or row[0] is None:
            logger.info(
                "No thumbnail URL for channel %s; serving placeholder",
                channel_id,
            )
            return self._serve_placeholder("channel")

        thumbnail_url: str = row[0]

        # 5. Fetch and cache
        success, reason = await self._fetch_and_cache(
            url=thumbnail_url,
            cache_path=cache_path,
            timeout=self._config.on_demand_timeout,
        )

        # 6. Success → serve cached file
        if success:
            return self._serve_cached_file(cache_path, "MISS")

        # 7. Failure → placeholder
        logger.info(
            "Failed to fetch channel image for %s (%s); serving placeholder",
            channel_id,
            reason,
        )
        return self._serve_placeholder("channel")

    # ------------------------------------------------------------------
    # Public API: get_video_image (T013)
    # ------------------------------------------------------------------

    async def get_video_image(
        self,
        video_id: str,
        quality: str = "mqdefault",
    ) -> Response:
        """Serve a video thumbnail image, fetching and caching on miss.

        Video thumbnails use deterministic URLs based on the video ID and
        quality level, so no database lookup is required (FR-008).

        Cache paths use two-character prefix sharding (FR-020):
        ``{videos_dir}/{video_id[:2]}/{video_id}_{quality}.jpg``

        Flow:
        1. Check local cache (HIT -> serve with 7-day immutable).
        2. Check ``.missing`` marker -> serve placeholder.
        3. Build deterministic YouTube thumbnail URL.
        4. Fetch and cache.
        5. On success -> serve cached file (X-Cache: MISS).
        6. On failure -> serve placeholder (X-Cache: PLACEHOLDER).

        Parameters
        ----------
        video_id : str
            YouTube video ID (11 characters, alphanumeric plus ``-`` and
            ``_``).
        quality : str
            Thumbnail quality level (default ``"mqdefault"``). Must be a
            valid ``ImageQuality`` enum value.

        Returns
        -------
        Response
            Image response (JPEG/PNG/WebP) or SVG placeholder.
        """
        if self._passthrough:
            return self._serve_placeholder("video")

        cache_path = self._resolve_cache_path("video", video_id, quality)

        # 1. Cache HIT
        cache_status = self._check_cache(cache_path)
        if cache_status == "HIT":
            logger.debug("Cache HIT for video image: %s (%s)", video_id, quality)
            return self._serve_cached_file(cache_path, "HIT")

        # 2. .missing marker
        if self._check_missing(cache_path):
            logger.debug(
                "Missing marker found for video image: %s (%s)",
                video_id,
                quality,
            )
            return self._serve_placeholder("video")

        # 3. Deterministic YouTube thumbnail URL (FR-008)
        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"

        # 4. Fetch and cache
        success, reason = await self._fetch_and_cache(
            url=thumbnail_url,
            cache_path=cache_path,
            timeout=self._config.on_demand_timeout,
        )

        # 5. Success -> serve cached file
        if success:
            return self._serve_cached_file(cache_path, "MISS")

        # 6. Failure -> placeholder
        logger.info(
            "Failed to fetch video image for %s/%s (%s); serving placeholder",
            video_id,
            quality,
            reason,
        )
        return self._serve_placeholder("video")

    # ------------------------------------------------------------------
    # Exponential backoff helper for 429 responses
    # ------------------------------------------------------------------

    @staticmethod
    async def _backoff_on_429(
        attempt: int,
        *,
        initial_wait: float = 60.0,
        multiplier: float = 2.0,
        max_wait: float = 300.0,
        progress_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        """Sleep with exponential backoff after a 429 response.

        Parameters
        ----------
        attempt : int
            Zero-based retry attempt number.
        initial_wait : float
            Initial backoff duration in seconds (default 60).
        multiplier : float
            Backoff multiplier (default 2x).
        max_wait : float
            Maximum backoff duration in seconds (default 300).
        progress_callback : Callable[[str, str], None] | None
            Optional callback for reporting backoff status.
        """
        wait = min(initial_wait * (multiplier ** attempt), max_wait)
        if progress_callback is not None:
            progress_callback(
                "__backoff__",
                f"429 backoff {wait:.0f}s (attempt {attempt + 1}/3)",
            )
        logger.warning(
            "429 rate-limited — backing off %.0fs (attempt %d/3)",
            wait,
            attempt + 1,
        )
        await asyncio.sleep(wait)

    # ------------------------------------------------------------------
    # Internal: fetch with retry for warm operations
    # ------------------------------------------------------------------

    async def _fetch_with_warm_retry(
        self,
        url: str,
        cache_path: Path,
        *,
        progress_callback: Callable[[str, str], None] | None = None,
    ) -> tuple[bool, str | None]:
        """Fetch an image with warm timeout and 429 exponential backoff.

        Parameters
        ----------
        url : str
            Remote image URL.
        cache_path : Path
            Local cache path.
        progress_callback : Callable[[str, str], None] | None
            Optional progress callback.

        Returns
        -------
        tuple[bool, str | None]
            ``(True, None)`` on success, ``(False, reason)`` on failure.
        """
        max_retries = 3
        reason: str | None = None
        for attempt in range(max_retries):
            success, reason = await self._fetch_and_cache(
                url=url,
                cache_path=cache_path,
                timeout=self._config.warm_timeout,
            )
            if success:
                return True, None
            # Retry on 429 only
            if reason is not None and reason.startswith("server_error_429"):
                if attempt < max_retries - 1:
                    await self._backoff_on_429(
                        attempt,
                        progress_callback=progress_callback,
                    )
                    continue
            # Non-retryable failure
            return False, reason
        return False, reason

    # ------------------------------------------------------------------
    # Public API: warm_channels (T018)
    # ------------------------------------------------------------------

    async def warm_channels(
        self,
        session: AsyncSession,
        *,
        delay: float = 0.5,
        limit: int | None = None,
        dry_run: bool = False,
        progress_callback: Callable[[str, str], None] | None = None,
    ) -> WarmResult:
        """Pre-download channel avatar images that are not yet cached.

        Queries all channels from the database and downloads missing
        thumbnails with rate limiting and exponential backoff on 429.

        Parameters
        ----------
        session : AsyncSession
            Database session for querying channel thumbnail URLs.
        delay : float
            Seconds to sleep between successive downloads (default 0.5).
        limit : int | None
            Maximum number of images to download.  ``None`` means unlimited.
        dry_run : bool
            If ``True``, count what *would* be downloaded without fetching.
        progress_callback : Callable[[str, str], None] | None
            Optional ``(entity_id, status)`` callback for CLI progress.

        Returns
        -------
        WarmResult
            Counts of downloaded / skipped / failed / no_url / total.
        """
        downloaded = 0
        skipped = 0
        failed = 0
        no_url = 0

        # Query all channels
        result = await session.execute(
            select(ChannelDB.channel_id, ChannelDB.thumbnail_url)
        )
        rows = result.all()
        total = len(rows)

        for row in rows:
            channel_id: str = row[0]
            thumbnail_url: str | None = row[1]

            # No URL -> count and skip
            if thumbnail_url is None:
                no_url += 1
                if progress_callback is not None:
                    progress_callback(channel_id, "no_url")
                continue

            cache_path = self._resolve_cache_path("channel", channel_id)
            missing_path = self._get_missing_path(cache_path)

            # Check if already cached (valid .jpg >= 1 KB)
            cache_status = self._check_cache(cache_path)
            if cache_status == "HIT":
                skipped += 1
                if progress_callback is not None:
                    progress_callback(channel_id, "skipped")
                continue

            # In dry-run mode, count as "to download" but don't fetch
            if dry_run:
                downloaded += 1  # counts as "would download"
                if progress_callback is not None:
                    progress_callback(channel_id, "dry_run")
                continue

            # Check limit
            if limit is not None and downloaded >= limit:
                # Remaining channels count as skipped
                skipped += 1
                if progress_callback is not None:
                    progress_callback(channel_id, "limit_reached")
                continue

            # Remove .missing marker before re-attempt
            if missing_path.is_file():
                try:
                    missing_path.unlink()
                except OSError:
                    pass

            # Fetch with retry
            success, reason = await self._fetch_with_warm_retry(
                url=thumbnail_url,
                cache_path=cache_path,
                progress_callback=progress_callback,
            )

            if success:
                downloaded += 1
                if progress_callback is not None:
                    progress_callback(channel_id, "downloaded")
            else:
                failed += 1
                if progress_callback is not None:
                    progress_callback(channel_id, f"failed:{reason}")

            # Rate limiting between fetches
            if delay > 0:
                await asyncio.sleep(delay)

        return WarmResult(
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            no_url=no_url,
            total=total,
        )

    # ------------------------------------------------------------------
    # Public API: warm_videos (T018)
    # ------------------------------------------------------------------

    async def warm_videos(
        self,
        session: AsyncSession,
        *,
        quality: str = "mqdefault",
        delay: float = 0.5,
        limit: int | None = None,
        dry_run: bool = False,
        progress_callback: Callable[[str, str], None] | None = None,
    ) -> WarmResult:
        """Pre-download video thumbnail images that are not yet cached.

        Queries video IDs from the database in 1,000-row batches and
        downloads missing thumbnails using deterministic YouTube URLs.

        Parameters
        ----------
        session : AsyncSession
            Database session for querying video IDs.
        quality : str
            Thumbnail quality level (default ``"mqdefault"``).
        delay : float
            Seconds to sleep between successive downloads (default 0.5).
        limit : int | None
            Maximum number of images to download.  ``None`` means unlimited.
        dry_run : bool
            If ``True``, count what *would* be downloaded without fetching.
        progress_callback : Callable[[str, str], None] | None
            Optional ``(entity_id, status)`` callback for CLI progress.

        Returns
        -------
        WarmResult
            Counts of downloaded / skipped / failed / no_url / total.
        """
        downloaded = 0
        skipped = 0
        failed = 0
        # no_url is always 0 for videos (deterministic URLs)
        no_url = 0

        # Count total videos for reporting
        count_result = await session.execute(
            select(func.count()).select_from(VideoDB)
        )
        total = count_result.scalar_one()

        # Stream video IDs in 1,000-row batches
        batch_size = 1000
        offset = 0

        while True:
            result = await session.execute(
                select(VideoDB.video_id)
                .order_by(VideoDB.video_id)
                .offset(offset)
                .limit(batch_size)
            )
            batch = result.scalars().all()
            if not batch:
                break

            for video_id in batch:
                cache_path = self._resolve_cache_path(
                    "video", video_id, quality
                )
                missing_path = self._get_missing_path(cache_path)

                # Check if already cached
                cache_status = self._check_cache(cache_path)
                if cache_status == "HIT":
                    skipped += 1
                    if progress_callback is not None:
                        progress_callback(video_id, "skipped")
                    continue

                # Dry-run: count as "would download"
                if dry_run:
                    downloaded += 1
                    if progress_callback is not None:
                        progress_callback(video_id, "dry_run")
                    continue

                # Check download limit
                if limit is not None and downloaded >= limit:
                    skipped += 1
                    if progress_callback is not None:
                        progress_callback(video_id, "limit_reached")
                    continue

                # Remove .missing marker before re-attempt
                if missing_path.is_file():
                    try:
                        missing_path.unlink()
                    except OSError:
                        pass

                # Deterministic URL
                thumbnail_url = (
                    f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"
                )

                # Fetch with retry
                success, reason = await self._fetch_with_warm_retry(
                    url=thumbnail_url,
                    cache_path=cache_path,
                    progress_callback=progress_callback,
                )

                if success:
                    downloaded += 1
                    if progress_callback is not None:
                        progress_callback(video_id, "downloaded")
                else:
                    failed += 1
                    if progress_callback is not None:
                        progress_callback(video_id, f"failed:{reason}")

                # Rate limiting between fetches
                if delay > 0:
                    await asyncio.sleep(delay)

            offset += batch_size

        return WarmResult(
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            no_url=no_url,
            total=total,
        )

    # ------------------------------------------------------------------
    # Public API: get_stats (T024)
    # ------------------------------------------------------------------

    async def get_stats(self) -> CacheStats:
        """Compute statistics about the image cache contents.

        Scans the channels and videos cache directories for ``.jpg`` image
        files and ``.missing`` marker files, counting entries and summing
        file sizes.

        Returns
        -------
        CacheStats
            Aggregated cache statistics including counts, total size, and
            oldest/newest file modification times.
        """
        channel_count = 0
        channel_missing_count = 0
        video_count = 0
        video_missing_count = 0
        total_size_bytes = 0
        oldest_mtime: float | None = None
        newest_mtime: float | None = None

        def _update_mtime(mtime: float) -> None:
            nonlocal oldest_mtime, newest_mtime
            if oldest_mtime is None or mtime < oldest_mtime:
                oldest_mtime = mtime
            if newest_mtime is None or mtime > newest_mtime:
                newest_mtime = mtime

        # Scan channels directory
        channels_dir = self._config.channels_dir
        if channels_dir.is_dir():
            for path in channels_dir.glob("*.jpg"):
                if path.is_file():
                    channel_count += 1
                    stat = path.stat()
                    total_size_bytes += stat.st_size
                    _update_mtime(stat.st_mtime)
            for path in channels_dir.glob("*.missing"):
                if path.is_file():
                    channel_missing_count += 1

        # Scan videos directory (recursive due to sharding)
        videos_dir = self._config.videos_dir
        if videos_dir.is_dir():
            for path in videos_dir.rglob("*.jpg"):
                if path.is_file():
                    video_count += 1
                    stat = path.stat()
                    total_size_bytes += stat.st_size
                    _update_mtime(stat.st_mtime)
            for path in videos_dir.rglob("*.missing"):
                if path.is_file():
                    video_missing_count += 1

        oldest_file = (
            datetime.fromtimestamp(oldest_mtime) if oldest_mtime is not None else None
        )
        newest_file = (
            datetime.fromtimestamp(newest_mtime) if newest_mtime is not None else None
        )

        logger.info(
            "Cache stats: channels=%d (+%d missing), videos=%d (+%d missing), "
            "total_size=%d bytes",
            channel_count,
            channel_missing_count,
            video_count,
            video_missing_count,
            total_size_bytes,
        )

        return CacheStats(
            channel_count=channel_count,
            channel_missing_count=channel_missing_count,
            video_count=video_count,
            video_missing_count=video_missing_count,
            total_size_bytes=total_size_bytes,
            oldest_file=oldest_file,
            newest_file=newest_file,
        )

    # ------------------------------------------------------------------
    # Public API: purge (T025)
    # ------------------------------------------------------------------

    async def purge(self, type_: str) -> int:
        """Delete cached image files and missing markers by type.

        Removes all ``.jpg`` image files and ``.missing`` marker files from
        the specified cache directory(ies).  The directories themselves are
        preserved.

        Parameters
        ----------
        type_ : str
            Which cache to purge: ``"channels"``, ``"videos"``, or
            ``"all"``.

        Returns
        -------
        int
            Total bytes freed (sum of deleted file sizes).
        """
        bytes_freed = 0

        if type_ in ("channels", "all"):
            bytes_freed += self._purge_directory(
                self._config.channels_dir, recursive=False
            )

        if type_ in ("videos", "all"):
            bytes_freed += self._purge_directory(
                self._config.videos_dir, recursive=True
            )

        logger.info(
            "Purge complete (type=%s): freed %d bytes", type_, bytes_freed
        )
        return bytes_freed

    def _purge_directory(self, directory: Path, *, recursive: bool) -> int:
        """Delete all .jpg and .missing files in a directory.

        Parameters
        ----------
        directory : Path
            Directory to purge.
        recursive : bool
            If ``True``, use ``rglob`` to scan subdirectories.

        Returns
        -------
        int
            Total bytes freed.
        """
        bytes_freed = 0
        if not directory.is_dir():
            return bytes_freed

        glob_fn = directory.rglob if recursive else directory.glob

        for pattern in ("*.jpg", "*.missing"):
            for path in glob_fn(pattern):
                if not path.is_file():
                    continue
                try:
                    size = path.stat().st_size
                    path.unlink()
                    bytes_freed += size
                except OSError:
                    logger.warning(
                        "Failed to delete cached file: %s",
                        path,
                        exc_info=True,
                    )

        return bytes_freed

    async def count_unavailable_cached(
        self, session: AsyncSession, type_: str
    ) -> int:
        """Count cached images belonging to unavailable content.

        Queries the database for channels or videos whose
        ``availability_status`` is not ``'available'`` and checks whether
        a corresponding cached image exists on disk.

        Parameters
        ----------
        session : AsyncSession
            Database session for querying availability status.
        type_ : str
            Which cache to check: ``"channels"``, ``"videos"``, or
            ``"all"``.

        Returns
        -------
        int
            Number of cached images that belong to unavailable content.
        """
        count = 0

        if type_ in ("channels", "all"):
            result = await session.execute(
                select(ChannelDB.channel_id).where(
                    ChannelDB.availability_status != "available"
                )
            )
            for row in result.all():
                channel_id: str = row[0]
                cache_path = self._resolve_cache_path("channel", channel_id)
                if cache_path.is_file():
                    count += 1

        if type_ in ("videos", "all"):
            result = await session.execute(
                select(VideoDB.video_id).where(
                    VideoDB.availability_status != "available"
                )
            )
            for row in result.all():
                video_id: str = row[0]
                cache_path = self._resolve_cache_path("video", video_id)
                if cache_path.is_file():
                    count += 1

        return count

    # ------------------------------------------------------------------
    # Public API: invalidate_channel (T028)
    # ------------------------------------------------------------------

    async def invalidate_channel(self, channel_id: str) -> None:
        """Invalidate a channel's cached avatar image.

        Deletes the cached ``.jpg`` file and/or ``.missing`` marker for the
        given channel.  This is a no-op if neither file exists.

        Video thumbnails are never invalidated (FR-018).

        Parameters
        ----------
        channel_id : str
            YouTube channel ID whose cached avatar should be removed.
        """
        cache_path = self._resolve_cache_path("channel", channel_id)
        missing_path = self._get_missing_path(cache_path)

        deleted = False

        if cache_path.is_file():
            try:
                cache_path.unlink()
                deleted = True
                logger.info(
                    "Invalidated cached channel image: %s", channel_id
                )
            except OSError:
                logger.error(
                    "Failed to delete cached channel image for %s",
                    channel_id,
                    exc_info=True,
                )

        if missing_path.is_file():
            try:
                missing_path.unlink()
                deleted = True
                logger.info(
                    "Removed .missing marker for channel: %s", channel_id
                )
            except OSError:
                logger.error(
                    "Failed to delete .missing marker for channel %s",
                    channel_id,
                    exc_info=True,
                )

        if not deleted:
            logger.debug(
                "No cached image or .missing marker to invalidate "
                "for channel: %s",
                channel_id,
            )
