"""
CDX API client for the Wayback Machine video recovery service.

Provides rate-limited, cached access to the Internet Archive CDX API
for discovering archived YouTube video snapshots. Includes exponential
backoff retry logic for transient failures and file-based caching
with configurable TTL.

Classes
-------
RateLimiter
    Token-bucket rate limiter for controlling request throughput.
CDXClient
    Async client for the Wayback Machine CDX API with caching and retry.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
from pathlib import Path
from typing import cast

import httpx

from chronovista import __version__
from chronovista.exceptions import CDXError
from chronovista.services.recovery.models import CdxCacheEntry, CdxSnapshot

logger = logging.getLogger(__name__)

_CDX_BASE_URL = "https://web.archive.org/cdx/search/cdx"
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 2.0
_RATE_LIMIT_PAUSE_SECONDS = 60.0
_REQUEST_TIMEOUT_SECONDS = 30.0
_CACHE_TTL_HOURS = 24
_CDX_RESULT_LIMIT = 100
_MIN_RESPONSE_LENGTH = 5000


class RateLimiter:
    """
    Token-bucket rate limiter for controlling async request throughput.

    Starts with a full bucket of tokens equal to the configured rate,
    allowing an initial burst. Once tokens are exhausted, subsequent
    calls to ``acquire()`` will sleep to maintain the target rate.

    Parameters
    ----------
    rate : float
        Maximum requests per second (e.g., 40.0 means 40 req/s).

    Examples
    --------
    >>> limiter = RateLimiter(rate=40.0)
    >>> await limiter.acquire()  # First 40 calls proceed immediately
    """

    def __init__(self, rate: float) -> None:
        """
        Initialize the RateLimiter.

        Parameters
        ----------
        rate : float
            Maximum requests per second. The bucket starts full with
            ``rate`` tokens, allowing an initial burst up to that count.
        """
        self._rate = rate
        self._tokens = rate
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """
        Acquire a single token, sleeping if the bucket is empty.

        If tokens are available, one is consumed immediately. If the
        bucket is empty, sleeps for ``1/rate`` seconds to replenish
        one token before proceeding.

        This method is safe for concurrent async callers via an
        internal ``asyncio.Lock``.
        """
        async with self._lock:
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            # Need to wait for a token to become available
            wait_time = 1.0 / self._rate
            await asyncio.sleep(wait_time)
            # After sleeping, we have effectively earned one token
            # and immediately consume it, so tokens stays the same


class CDXClient:
    """
    Async client for the Wayback Machine CDX API.

    Fetches archived YouTube video snapshots from the CDX API with
    built-in file-based caching, rate limiting, and retry logic for
    transient HTTP errors.

    Parameters
    ----------
    cache_dir : Path
        Root directory for CDX response cache files. Cache entries
        are stored under ``{cache_dir}/cdx/{video_id}.json``.

    Attributes
    ----------
    cache_dir : Path
        The configured cache directory root.

    Examples
    --------
    >>> client = CDXClient(cache_dir=Path("/tmp/cdx_cache"))
    >>> snapshots = await client.fetch_snapshots("dQw4w9WgXcQ")
    >>> for snap in snapshots:
    ...     print(snap.timestamp, snap.wayback_url)
    """

    def __init__(self, cache_dir: Path) -> None:
        """
        Initialize the CDXClient.

        Parameters
        ----------
        cache_dir : Path
            Root directory for CDX response cache files.
        """
        self.cache_dir = cache_dir

    async def fetch_snapshots(
        self,
        video_id: str,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> list[CdxSnapshot]:
        """
        Fetch CDX snapshots for a YouTube video, using cache when available.

        Checks the file-based cache first. If a fresh cache entry exists
        (less than 24 hours old), returns the cached snapshots without
        making an HTTP request. Otherwise, queries the CDX API, filters
        and sorts the results, caches them, and returns the snapshots.

        Parameters
        ----------
        video_id : str
            YouTube video ID (e.g., "dQw4w9WgXcQ").
        from_year : int | None, optional
            Only return snapshots from this year onward (default: None).
        to_year : int | None, optional
            Only return snapshots up to this year (default: None).

        Returns
        -------
        list[CdxSnapshot]
            List of CDX snapshots. Sorted newest-first by default, or
            oldest-first when ``from_year`` is specified (so iteration
            starts near the anchor year). May be empty.

        Raises
        ------
        CDXError
            If the CDX API request fails after all retries are exhausted.
        """
        # Check cache first
        cached = self._read_cache(video_id, from_year=from_year, to_year=to_year)
        if cached is not None:
            snapshots = cached
        else:
            # Fetch from CDX API with retries
            raw_rows = await self._fetch_with_retries(
                video_id, from_year=from_year, to_year=to_year
            )

            # Parse and filter
            snapshots = self._parse_cdx_response(raw_rows)

            # Cache the results
            self._write_cache(
                video_id, snapshots, raw_count=len(raw_rows),
                from_year=from_year, to_year=to_year,
            )

        # When from_year is set, return oldest-first (ascending) so the
        # orchestrator tries snapshots closest to the anchor year first.
        if from_year is not None:
            snapshots = list(reversed(snapshots))

        return snapshots

    def _build_cdx_url(
        self,
        video_id: str,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> str:
        """
        Build the CDX API query URL for a given video ID.

        Parameters
        ----------
        video_id : str
            YouTube video ID.
        from_year : int | None, optional
            Only return snapshots from this year onward (default: None).
        to_year : int | None, optional
            Only return snapshots up to this year (default: None).

        Returns
        -------
        str
            Fully-formed CDX API URL with all required query parameters.
        """
        # When from_year is set, use positive limit (oldest first from anchor)
        # so snapshots near the anchor year are returned.
        # Without from_year, use negative limit (newest first).
        limit = _CDX_RESULT_LIMIT if from_year is not None else -_CDX_RESULT_LIMIT
        url = (
            f"{_CDX_BASE_URL}"
            f"?url=youtube.com/watch%3Fv%3D{video_id}"
            f"&output=json"
            f"&filter=statuscode:200"
            f"&filter=mimetype:text/html"
            f"&fl=timestamp,original,mimetype,statuscode,digest,length"
            f"&limit={limit}"
        )
        if from_year is not None:
            url += f"&from={from_year}0101000000"
        if to_year is not None:
            url += f"&to={to_year}1231235959"
        return url

    async def _fetch_with_retries(
        self,
        video_id: str,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> list[list[str]]:
        """
        Fetch CDX data with retry logic for transient HTTP errors.

        Implements exponential backoff for HTTP 503 (base 2s, 3 retries)
        and a fixed 60s pause for HTTP 429 (rate limit).

        Parameters
        ----------
        video_id : str
            YouTube video ID.
        from_year : int | None, optional
            Only return snapshots from this year onward (default: None).
        to_year : int | None, optional
            Only return snapshots up to this year (default: None).

        Returns
        -------
        list[list[str]]
            Raw CDX response rows (array of arrays, first row is headers).

        Raises
        ------
        CDXError
            If all retries are exhausted without a successful response.
        """
        url = self._build_cdx_url(video_id, from_year=from_year, to_year=to_year)
        headers = {"User-Agent": f"chronovista/{__version__}"}
        retries_remaining = _MAX_RETRIES

        async with httpx.AsyncClient(follow_redirects=True) as client:
            while True:
                try:
                    response = await client.get(
                        url,
                        headers=headers,
                        timeout=_REQUEST_TIMEOUT_SECONDS,
                    )
                except (
                    httpx.ConnectTimeout,
                    httpx.ReadTimeout,
                    httpx.ConnectError,
                ) as e:
                    if retries_remaining <= 0:
                        raise CDXError(
                            message=(
                                f"CDX API connection failed for video "
                                f"'{video_id}' after retries: "
                                f"{type(e).__name__}"
                            ),
                            video_id=video_id,
                            status_code=0,
                        ) from e
                    attempt = _MAX_RETRIES - retries_remaining
                    delay = _BACKOFF_BASE_SECONDS * (2 ** attempt)
                    retries_remaining -= 1
                    logger.warning(
                        "CDX fetch attempt %d/%d for video %s failed "
                        "(%s), retrying in %.0fs",
                        attempt + 1,
                        _MAX_RETRIES,
                        video_id,
                        type(e).__name__,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                if response.status_code == 200:
                    return cast(list[list[str]], response.json())

                if response.status_code == 429:
                    if retries_remaining <= 0:
                        raise CDXError(
                            message=(
                                f"CDX API rate limit exceeded for video "
                                f"'{video_id}' after retries"
                            ),
                            video_id=video_id,
                            status_code=429,
                        )
                    retries_remaining -= 1
                    await asyncio.sleep(_RATE_LIMIT_PAUSE_SECONDS)
                    continue

                if response.status_code == 503:
                    if retries_remaining <= 0:
                        raise CDXError(
                            message=(
                                f"CDX API unavailable (503) for video "
                                f"'{video_id}' after retries"
                            ),
                            video_id=video_id,
                            status_code=503,
                        )
                    attempt = _MAX_RETRIES - retries_remaining
                    delay = _BACKOFF_BASE_SECONDS * (2 ** attempt)
                    retries_remaining -= 1
                    await asyncio.sleep(delay)
                    continue

                # Unexpected status code — raise immediately
                raise CDXError(
                    message=(
                        f"CDX API returned unexpected status "
                        f"{response.status_code} for video '{video_id}'"
                    ),
                    video_id=video_id,
                    status_code=response.status_code,
                )

    def _parse_cdx_response(
        self, raw_rows: list[list[str]]
    ) -> list[CdxSnapshot]:
        """
        Parse raw CDX JSON rows into filtered, sorted CdxSnapshot objects.

        Skips the header row, filters out redirect rows (statuscode="-"),
        non-200 status codes, non-text/html mimetypes, and responses with
        length <= 5000. Results are sorted newest-first by timestamp.

        Parameters
        ----------
        raw_rows : list[list[str]]
            Raw CDX response data (array of arrays).

        Returns
        -------
        list[CdxSnapshot]
            Filtered and sorted list of CdxSnapshot objects.
        """
        if not raw_rows or len(raw_rows) <= 1:
            return []

        # First row is headers, skip it
        data_rows = raw_rows[1:]

        snapshots: list[CdxSnapshot] = []
        for row in data_rows:
            if len(row) < 6:
                continue

            timestamp, original, mimetype, statuscode_str, digest, length_str = (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
            )

            # Skip redirect rows with statuscode="-"
            if statuscode_str == "-":
                continue

            # Parse numeric fields
            try:
                statuscode = int(statuscode_str)
                length = int(length_str)
            except (ValueError, TypeError):
                continue

            # Apply filters
            if statuscode != 200:
                continue
            if mimetype != "text/html":
                continue
            if length <= _MIN_RESPONSE_LENGTH:
                continue

            snapshot = CdxSnapshot(
                timestamp=timestamp,
                original=original,
                mimetype=mimetype,
                statuscode=statuscode,
                digest=digest,
                length=length,
            )
            snapshots.append(snapshot)

        # Sort newest-first (descending by timestamp)
        snapshots.sort(key=lambda s: s.timestamp, reverse=True)

        return snapshots

    def _cache_path(
        self,
        video_id: str,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> Path:
        """
        Compute the cache file path for a given video ID and year range.

        Parameters
        ----------
        video_id : str
            YouTube video ID.
        from_year : int | None, optional
            Start year filter used in the CDX query (default: None).
        to_year : int | None, optional
            End year filter used in the CDX query (default: None).

        Returns
        -------
        Path
            Path to the cache file. When year filters are active the
            filename includes suffixes, e.g.
            ``{cache_dir}/cdx/{video_id}_from2018_to2020.json``.
        """
        suffix = ""
        if from_year is not None:
            suffix += f"_from{from_year}"
        if to_year is not None:
            suffix += f"_to{to_year}"
        return self.cache_dir / "cdx" / f"{video_id}{suffix}.json"

    def _read_cache(
        self,
        video_id: str,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> list[CdxSnapshot] | None:
        """
        Read and validate a cached CDX response for a video.

        Returns the cached snapshots if the cache file exists, contains
        valid JSON, and is still fresh (less than 24 hours old). Returns
        None on cache miss, expiration, or corruption. Corrupted cache
        files are deleted automatically.

        Parameters
        ----------
        video_id : str
            YouTube video ID.
        from_year : int | None, optional
            Start year filter used in the CDX query (default: None).
        to_year : int | None, optional
            End year filter used in the CDX query (default: None).

        Returns
        -------
        list[CdxSnapshot] | None
            Cached snapshots if valid, or None if cache miss/expired/corrupt.
        """
        cache_file = self._cache_path(video_id, from_year=from_year, to_year=to_year)
        if not cache_file.exists():
            return None

        try:
            raw_text = cache_file.read_text()
            entry = CdxCacheEntry.model_validate_json(raw_text)
        except Exception:
            # Corrupted cache — delete and re-fetch
            logger.warning(
                "Corrupted CDX cache for video '%s', deleting: %s",
                video_id,
                cache_file,
            )
            try:
                cache_file.unlink()
            except OSError:
                pass
            return None

        if not entry.is_valid(ttl_hours=_CACHE_TTL_HOURS):
            return None

        return entry.snapshots

    def _write_cache(
        self,
        video_id: str,
        snapshots: list[CdxSnapshot],
        raw_count: int,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> None:
        """
        Write a CDX response to the file cache.

        Creates the cache directory structure if it does not exist.

        Parameters
        ----------
        video_id : str
            YouTube video ID.
        snapshots : list[CdxSnapshot]
            Filtered CDX snapshots to cache.
        raw_count : int
            Total number of raw CDX rows before filtering.
        from_year : int | None, optional
            Start year filter used in the CDX query (default: None).
        to_year : int | None, optional
            End year filter used in the CDX query (default: None).
        """
        cache_file = self._cache_path(video_id, from_year=from_year, to_year=to_year)
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        entry = CdxCacheEntry(
            video_id=video_id,
            fetched_at=_dt.datetime.now(_dt.timezone.utc),
            snapshots=snapshots,
            raw_count=raw_count,
        )

        cache_file.write_text(entry.model_dump_json())
