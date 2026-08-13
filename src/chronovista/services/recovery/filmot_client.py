"""
Filmot API client for deleted-video metadata recovery.

Filmot (https://filmot.com/) indexes YouTube metadata and retains records for
videos YouTube later removed. Its ``getvideos`` endpoint is a video-ID lookup —
the inverse of the keyword search its paid product offers — and returns title,
channel, upload date and duration for ids YouTube itself no longer serves.

Sibling of :mod:`cdx_client`. Where the CDX client finds *archived pages* to
parse, this one asks a *structured index* directly, so there is no HTML to
scrape and no snapshot to choose.

**It returns metadata only.** Filmot has no per-video transcript route, in this
endpoint or its paid API. Nothing here recovers what a video said.

Historical note, because it shaped the code this replaces: an earlier manual
import script was built around the belief that this endpoint "answers
cross-origin requests only under the conditions a browser provides," and paired
a browser helper with a Python importer to work around it. That reasoning could
not have been right — CORS is enforced by browsers and has never applied to a
server-side client — and a direct request measured on 2026-08-12 returned HTTP
200 with correct JSON, no headers or cookies required.

Classes
-------
FilmotVideo
    One video's metadata as Filmot reports it.
FilmotClient
    Async, rate-limited, retrying client for the getvideos endpoint.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from chronovista import __version__
from chronovista.config.settings import settings
from chronovista.exceptions import FilmotError
from chronovista.services.recovery.cdx_client import RateLimiter

logger = logging.getLogger(__name__)

_FILMOT_URL = "https://filmot.com/api/getvideos"
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 2.0
_REQUEST_TIMEOUT_SECONDS = 30.0

# The endpoint accepts comma-separated ids. 50 matches the batch size the
# public userscript uses; there is no documented maximum, so this follows
# established practice rather than probing for a limit.
_BATCH_SIZE = 50

# Deliberately slower than the CDX client. Filmot is a single-maintainer
# archive with no published rate limits and no rate-limit headers on its
# responses — the absence of a stated limit is a reason for restraint, not
# licence. One request per second, with batches of 50, is 50 videos/second.
_REQUESTS_PER_SECOND = 1.0


class FilmotVideo(BaseModel):
    """
    One video's metadata as Filmot reports it.

    Every field except ``video_id`` is optional: Filmot's coverage is uneven,
    and a partial record is still useful for gap-filling. Validation is
    deliberately lenient about *types* (the API returns numbers as strings)
    and strict about *identity* (a record with no id is unusable).

    Attributes
    ----------
    video_id : str
        YouTube video ID, from the API's ``id`` field.
    title : str | None
        Video title.
    channel_id : str | None
        Owning channel's ID, from ``channelid``.
    channel_name : str | None
        Owning channel's display name, from ``channelname``.
    upload_date : str | None
        Upload date as reported, ``YYYY-MM-DD``. Kept as a string: it is
        used only for comparison and display, and parsing it here would
        invent a timezone the source never stated.
    duration : int | None
        Duration in seconds. Non-positive values are dropped — Filmot
        reports 0 for records where it does not know.
    """

    model_config = ConfigDict(populate_by_name=True)

    video_id: str = Field(alias="id", min_length=1)
    title: str | None = None
    channel_id: str | None = Field(default=None, alias="channelid")
    channel_name: str | None = Field(default=None, alias="channelname")
    upload_date: str | None = Field(default=None, alias="uploaddate")
    duration: int | None = None

    @field_validator("duration", mode="before")
    @classmethod
    def _coerce_duration(cls, value: Any) -> int | None:
        """Accept the API's stringly-typed numbers; drop unusable values.

        Filmot returns ``duration`` as either a number or a numeric string,
        and uses ``0`` to mean "unknown" rather than "zero seconds". Writing
        that 0 into ``videos.duration`` would replace an absent value with a
        confidently wrong one.
        """
        if value is None or value == "":
            return None
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            return None
        return seconds if seconds > 0 else None

    @field_validator("title", "channel_id", "channel_name", "upload_date")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        """An empty string is absence, not content."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class FilmotClient:
    """
    Async client for Filmot's ``getvideos`` endpoint.

    Parameters
    ----------
    api_key : str | None, optional
        Filmot API key. Defaults to ``settings.filmot_api_key``. When empty,
        :meth:`is_configured` is False and :meth:`fetch_videos` raises rather
        than issuing a request that would certainly fail.
    requests_per_second : float, optional
        Throughput ceiling (default 1.0).

    Examples
    --------
    >>> client = FilmotClient()
    >>> if client.is_configured:
    ...     found, unresolved = await client.fetch_videos(["abc", "def"])
    """

    def __init__(
        self,
        api_key: str | None = None,
        requests_per_second: float = _REQUESTS_PER_SECOND,
    ) -> None:
        """Initialize the client, defaulting the key from settings."""
        self._api_key = api_key if api_key is not None else settings.filmot_api_key
        self._limiter = RateLimiter(rate=requests_per_second)

    @property
    def is_configured(self) -> bool:
        """Whether an API key is available.

        Callers check this to skip Filmot rather than fail: an unconfigured
        optional source is a source that is simply unavailable, which is a
        normal state and not an error.
        """
        return bool(self._api_key)

    async def fetch_videos(
        self, video_ids: list[str]
    ) -> tuple[list[FilmotVideo], set[str]]:
        """
        Look up metadata for ``video_ids``, in batches.

        Parameters
        ----------
        video_ids : list[str]
            Video IDs to look up. Duplicates are collapsed. An empty list
            issues no request.

        Returns
        -------
        tuple[list[FilmotVideo], set[str]]
            ``(found, unresolved)``.

            ``unresolved`` is every id whose **batch failed to complete** —
            not ids Filmot answered about and did not have. Those are simply
            absent from ``found``, which is all a caller needs, and conflating
            the two is precisely the defect that hid 288 playlists in #149: a
            request that never completed is not evidence about its subject.

        Raises
        ------
        FilmotError
            If no API key is configured, or if the archive rejects the
            credential (401/403). Both are conditions of the run rather than of
            any batch, so they are raised rather than reported per-id.
        """
        if not self.is_configured:
            raise FilmotError(
                "No Filmot API key configured. Set FILMOT_API_KEY to enable "
                "this recovery source, or check `is_configured` first and skip it."
            )

        ordered_unique = list(dict.fromkeys(v for v in video_ids if v))
        if not ordered_unique:
            return [], set()

        found: list[FilmotVideo] = []
        unresolved: set[str] = set()

        for start in range(0, len(ordered_unique), _BATCH_SIZE):
            batch = ordered_unique[start : start + _BATCH_SIZE]
            try:
                found.extend(await self._fetch_batch(batch))
            except FilmotError as exc:
                if getattr(exc, "status_code", None) in (401, 403):
                    # A credential the archive rejects is not a fact about this
                    # batch, and the next batch will fare no better. Folding it
                    # into `unresolved` made it indistinguishable from a
                    # timeout: the caller then saw three fully-unresolved
                    # batches and told the operator "rate_limited", so a dead
                    # key read as a limit to wait out rather than a key to
                    # rotate. Callers classify this; it must reach them.
                    raise
                unresolved.update(batch)
                logger.warning(
                    "Filmot batch %d failed (%s); its %d ids are unresolved, "
                    "not missing",
                    start // _BATCH_SIZE + 1,
                    exc,
                    len(batch),
                )

        if unresolved:
            logger.warning(
                "%d of %d ids could not be looked up on Filmot. They are "
                "reported as neither found nor absent — callers must not treat "
                "them as unrecoverable.",
                len(unresolved),
                len(ordered_unique),
            )

        return found, unresolved

    async def _fetch_batch(self, batch: list[str]) -> list[FilmotVideo]:
        """Issue one request with retries, returning parsed records."""
        await self._limiter.acquire()

        params = {"key": self._api_key, "id": ",".join(batch)}
        headers = {"User-Agent": f"chronovista/{__version__}"}
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=_REQUEST_TIMEOUT_SECONDS
                ) as client:
                    response = await client.get(
                        _FILMOT_URL, params=params, headers=headers
                    )

                if response.status_code == 429:
                    if attempt >= _MAX_RETRIES:
                        raise FilmotError("Filmot rate limit exceeded", status_code=429)
                    # Retry-After is authoritative in a way a guessed backoff
                    # is not; fall back to exponential only when it is absent.
                    await asyncio.sleep(
                        _retry_after_seconds(response) or _BACKOFF_BASE_SECONDS**attempt
                    )
                    continue

                if response.status_code >= 500:
                    if attempt >= _MAX_RETRIES:
                        raise FilmotError(
                            f"Filmot server error: HTTP {response.status_code}",
                            status_code=response.status_code,
                        )
                    await asyncio.sleep(_BACKOFF_BASE_SECONDS**attempt)
                    continue

                if response.status_code != 200:
                    raise FilmotError(
                        f"Filmot returned HTTP {response.status_code}",
                        status_code=response.status_code,
                    )

                return _parse(response)

            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= _MAX_RETRIES:
                    break
                await asyncio.sleep(_BACKOFF_BASE_SECONDS**attempt)

        raise FilmotError(f"Filmot request failed after retries: {last_error}")


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse a ``Retry-After`` header expressed in seconds, if present."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse(response: httpx.Response) -> list[FilmotVideo]:
    """Turn a successful response body into records.

    A malformed *record* is skipped with a warning; a malformed *body* is an
    error. The distinction matters: one bad row in a batch of fifty should not
    discard the other forty-nine, but a response that is not a list at all
    means something changed and should be surfaced rather than read as "no
    results".
    """
    try:
        payload = response.json()
    except ValueError as exc:
        raise FilmotError(f"Filmot returned a non-JSON body: {exc}") from exc

    if not isinstance(payload, list):
        raise FilmotError(
            f"Filmot returned {type(payload).__name__}, expected a list of records"
        )

    records: list[FilmotVideo] = []
    for item in payload:
        try:
            records.append(FilmotVideo.model_validate(item))
        except Exception as exc:  # noqa: BLE001 - one bad row is not fatal
            logger.warning("Skipping unparseable Filmot record: %s", exc)
    return records
