"""
Page parser for extracting video metadata from archived YouTube pages.

Extracts metadata from Wayback Machine snapshots of YouTube video pages
using three strategies in priority order:

1. JSON extraction from ``ytInitialPlayerResponse`` embedded in page source
2. HTML meta tag extraction using BeautifulSoup (Open Graph + itemprop)
3. Optional Selenium fallback for pre-2017 pages requiring JS rendering

Functions
---------
is_removal_notice
    Detect whether an archived page is a removal/unavailable notice.

Classes
-------
PageParser
    Main coordinator for fetching and parsing archived YouTube pages.

Constants
---------
YOUTUBE_CATEGORY_MAP
    Mapping from YouTube category display names to numeric ID strings.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from chronovista import __version__
from chronovista.services.recovery import SELENIUM_AVAILABLE
from chronovista.services.recovery.cdx_client import RateLimiter
from chronovista.services.recovery.models import CdxSnapshot, RecoveredVideoData

logger = logging.getLogger(__name__)

YOUTUBE_CATEGORY_MAP: dict[str, str] = {
    "Film & Animation": "1",
    "Autos & Vehicles": "2",
    "Music": "10",
    "Pets & Animals": "15",
    "Sports": "17",
    "Short Movies": "18",
    "Travel & Events": "19",
    "Gaming": "20",
    "Videoblogging": "21",
    "People & Blogs": "22",
    "Comedy": "23",
    "Entertainment": "24",
    "News & Politics": "25",
    "Howto & Style": "26",
    "Education": "27",
    "Science & Technology": "28",
    "Nonprofits & Activism": "29",
}
"""Mapping from YouTube category display names to numeric category ID strings."""

# Regex to locate the START of ytInitialPlayerResponse/ytInitialData JSON.
# Only matches the variable assignment prefix; JSON body is extracted via
# brace-counting in _extract_json_object() to handle nested structures.
# Handles: var ytInitialPlayerResponse = {...};
#          ytInitialPlayerResponse = {...};
#          window["ytInitialPlayerResponse"] = {...};
_YT_INITIAL_PLAYER_RE = re.compile(
    r'(?:var\s+|window\["|)ytInitialPlayerResponse(?:"\])?\s*=\s*',
)
_YT_INITIAL_DATA_RE = re.compile(
    r'(?:var\s+|window\["|)ytInitialData(?:"\])?\s*=\s*',
)

# Regex for validating YouTube channel ID format.
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")

_REQUEST_TIMEOUT_SECONDS = 30.0
_MAX_FETCH_RETRIES = 3
_RETRY_BACKOFF_SECONDS = [2.0, 5.0, 10.0]

# Playability status values indicating removal/unavailability.
_REMOVAL_PLAYABILITY_STATUSES: dict[str, str] = {
    "ERROR": "playability_status_error",
    "UNPLAYABLE": "playability_status_unplayable",
    "LOGIN_REQUIRED": "playability_status_login_required",
}

# Text patterns (case-insensitive) indicating a removal notice.
_REMOVAL_TEXT_PATTERNS: list[tuple[str, str]] = [
    ("video unavailable", "text_video_unavailable"),
    ("removed by the uploader", "text_removed_by_uploader"),
    ("this video is private", "text_private"),
    ("copyright claim", "text_copyright"),
    ("violating youtube", "text_tos_violation"),
    ("terms of service", "text_tos_violation"),
    ("account associated with this video has been terminated", "text_account_terminated"),
]


def _extract_json_object(html: str, start: int) -> str | None:
    """
    Extract a balanced JSON object from HTML starting at the given position.

    Uses brace-counting to handle arbitrarily nested ``{...}`` structures
    that would break a simple non-greedy regex.

    Parameters
    ----------
    html : str
        Raw HTML source.
    start : int
        Position of the opening ``{`` in the HTML string.

    Returns
    -------
    str | None
        The balanced JSON string, or None if no opening brace at start
        or braces are unbalanced within the first 5MB of text.
    """
    if start >= len(html) or html[start] != "{":
        return None

    depth = 0
    in_string = False
    escape = False
    limit = min(len(html), start + 5_000_000)

    for i in range(start, limit):
        ch = html[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            if in_string:
                escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[start : i + 1]

    return None


def is_removal_notice(html: str) -> tuple[bool, str | None]:
    """
    Detect whether an archived YouTube page is a removal/unavailable notice.

    Applies several heuristics in a specific priority order to determine
    if the page represents a removed, private, or otherwise unavailable
    video rather than a page with recoverable metadata.

    Detection order:

    1. **Positive signal override**: If an ``og:video:url`` meta tag is
       present, the page is assumed to contain valid video data regardless
       of other removal signals.
    2. **Title checks**: Pages with only ``<title>YouTube</title>`` or
       ``<title> - YouTube</title>`` are generic removal stubs.
    3. **JSON playabilityStatus**: Checks the ``ytInitialPlayerResponse``
       JSON for ``playabilityStatus.status`` values indicating removal.
    4. **Body text patterns**: Case-insensitive search for known removal
       phrases in the HTML body.

    Parameters
    ----------
    html : str
        Raw HTML content of the archived YouTube page.

    Returns
    -------
    tuple[bool, str | None]
        A 2-tuple where the first element is ``True`` if the page is a
        removal notice and ``False`` otherwise. The second element is a
        reason string identifier (e.g., ``"title_only_youtube"``,
        ``"playability_status_error"``) when removed, or ``None`` when not.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # (a) Positive signal override: og:video:url meta tag present
        og_video_url = soup.find("meta", attrs={"property": "og:video:url"})
        if og_video_url is not None:
            return (False, None)

        # (b) Title checks
        title_tag = soup.find("title")
        if title_tag is not None:
            title_text = title_tag.get_text(strip=True)
            if title_text == "YouTube":
                return (True, "title_only_youtube")
            if title_text == "- YouTube":
                return (True, "title_dash_youtube")

        # (c) JSON playabilityStatus checks
        match = _YT_INITIAL_PLAYER_RE.search(html)
        if match:
            try:
                json_str = _extract_json_object(html, match.end())
                if json_str:
                    data = json.loads(json_str)
                    playability = data.get("playabilityStatus", {})
                    status = playability.get("status", "")
                    if status in _REMOVAL_PLAYABILITY_STATUSES:
                        return (True, _REMOVAL_PLAYABILITY_STATUSES[status])
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        # (d) Text pattern checks (case-insensitive)
        html_lower = html.lower()
        for pattern, reason in _REMOVAL_TEXT_PATTERNS:
            if pattern in html_lower:
                return (True, reason)

        return (False, None)

    except Exception:
        # Never raise — always return the tuple
        return (False, None)


class PageParser:
    """
    Main coordinator for fetching and parsing archived YouTube pages.

    Fetches a Wayback Machine snapshot via HTTP, checks for removal notices,
    then attempts to extract video metadata using JSON extraction first,
    falling back to HTML meta tag extraction, and optionally to Selenium
    rendering for pre-2017 pages.

    Parameters
    ----------
    rate_limiter : RateLimiter
        Rate limiter instance to throttle outgoing HTTP requests.

    Examples
    --------
    >>> from chronovista.services.recovery.cdx_client import RateLimiter
    >>> limiter = RateLimiter(rate=40.0)
    >>> parser = PageParser(rate_limiter=limiter)
    >>> result = await parser.extract_metadata(snapshot)
    """

    def __init__(self, rate_limiter: RateLimiter) -> None:
        """
        Initialize the PageParser.

        Parameters
        ----------
        rate_limiter : RateLimiter
            Rate limiter instance to throttle HTTP requests to the
            Wayback Machine.
        """
        self._rate_limiter = rate_limiter

    async def extract_metadata(
        self, snapshot: CdxSnapshot
    ) -> RecoveredVideoData | None:
        """
        Extract video metadata from a Wayback Machine snapshot.

        Fetches the snapshot URL, checks for removal notices, and attempts
        metadata extraction via JSON, meta tags, and optionally Selenium.

        Parameters
        ----------
        snapshot : CdxSnapshot
            The CDX snapshot to fetch and parse.

        Returns
        -------
        RecoveredVideoData | None
            Extracted metadata, or a minimal ``RecoveredVideoData`` with
            ``has_data=False`` if no metadata could be recovered.
        """
        # Fetch the snapshot page with retry for transient failures
        html: str | None = None
        for attempt in range(_MAX_FETCH_RETRIES):
            await self._rate_limiter.acquire()
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                ) as client:
                    response = await client.get(
                        snapshot.wayback_url,
                        timeout=_REQUEST_TIMEOUT_SECONDS,
                        headers={"User-Agent": f"chronovista/{__version__}"},
                    )
                html = response.text
                break
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as e:
                backoff = _RETRY_BACKOFF_SECONDS[attempt]
                logger.warning(
                    "Fetch attempt %d/%d for snapshot %s failed (%s), "
                    "retrying in %.0fs",
                    attempt + 1,
                    _MAX_FETCH_RETRIES,
                    snapshot.timestamp,
                    type(e).__name__,
                    backoff,
                )
                await asyncio.sleep(backoff)
            except Exception as e:
                logger.warning(
                    "Failed to fetch snapshot %s: %s: %s",
                    snapshot.timestamp,
                    type(e).__name__,
                    e,
                )
                return RecoveredVideoData(snapshot_timestamp=snapshot.timestamp)

        if html is None:
            logger.warning(
                "Failed to fetch snapshot %s after %d retries",
                snapshot.timestamp,
                _MAX_FETCH_RETRIES,
            )
            return RecoveredVideoData(snapshot_timestamp=snapshot.timestamp)

        # Check for removal notice
        is_removed, reason = is_removal_notice(html)
        if is_removed:
            logger.info(
                "Snapshot %s is a removal notice: %s",
                snapshot.timestamp,
                reason,
            )
            return RecoveredVideoData(snapshot_timestamp=snapshot.timestamp)

        # Try JSON extraction first
        result = self._extract_from_json(html, snapshot.timestamp)
        if result is not None:
            return result

        # Fall back to meta tag extraction
        result = self._extract_from_meta_tags(html, snapshot.timestamp)
        if result is not None:
            return result

        # If neither found data and Selenium is available, try Selenium
        if SELENIUM_AVAILABLE:
            try:
                selenium_result = await self._extract_with_selenium(
                    snapshot
                )
                if selenium_result is not None:
                    return selenium_result
            except asyncio.TimeoutError:
                logger.warning(
                    "Selenium timeout for snapshot %s",
                    snapshot.timestamp,
                )
                return RecoveredVideoData(
                    snapshot_timestamp=snapshot.timestamp
                )

        # No data could be recovered
        return RecoveredVideoData(snapshot_timestamp=snapshot.timestamp)

    def _extract_from_json(
        self, html: str, snapshot_timestamp: str
    ) -> RecoveredVideoData | None:
        """
        Extract metadata from ytInitialPlayerResponse JSON in page source.

        Searches the HTML for the ``ytInitialPlayerResponse`` JavaScript
        variable, parses the JSON, and extracts fields from ``videoDetails``
        and ``microformat.playerMicroformatRenderer``.

        Parameters
        ----------
        html : str
            Raw HTML content of the archived YouTube page.
        snapshot_timestamp : str
            CDX timestamp of the snapshot (14 digits).

        Returns
        -------
        RecoveredVideoData | None
            Extracted metadata if JSON was found and contained video details,
            or ``None`` if JSON was not found or was malformed.
        """
        match = _YT_INITIAL_PLAYER_RE.search(html)
        if not match:
            return None

        json_str = _extract_json_object(html, match.end())
        if not json_str:
            return None

        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Malformed ytInitialPlayerResponse JSON in snapshot %s",
                snapshot_timestamp,
            )
            return None

        video_details = data.get("videoDetails")
        if not video_details:
            return None

        # Extract fields from videoDetails
        title = video_details.get("title")
        description = video_details.get("shortDescription")
        channel_name_hint = video_details.get("author")
        channel_id = video_details.get("channelId")
        # Validate channel_id format; set to None if invalid
        if channel_id and not _CHANNEL_ID_RE.match(channel_id):
            channel_id = None
        tags = video_details.get("keywords", [])

        # Parse view count (string to int)
        view_count: int | None = None
        view_count_str = video_details.get("viewCount")
        if view_count_str is not None:
            try:
                view_count = int(view_count_str)
            except (ValueError, TypeError):
                pass

        # Extract from microformat
        upload_date: datetime | None = None
        category_id: str | None = None
        thumbnail_url: str | None = None
        microformat = data.get("microformat", {})
        renderer = microformat.get("playerMicroformatRenderer", {})

        publish_date_str = renderer.get("publishDate")
        if publish_date_str:
            try:
                upload_date = datetime.strptime(
                    publish_date_str, "%Y-%m-%d"
                ).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        category_name = renderer.get("category")
        if category_name:
            category_id = YOUTUBE_CATEGORY_MAP.get(category_name)

        # Extract thumbnail from microformat or videoDetails
        thumbnail_data = renderer.get("thumbnail", {}).get("thumbnails", [])
        if thumbnail_data:
            thumbnail_url = thumbnail_data[-1].get("url")

        # Extract like count from ytInitialData (separate JSON blob)
        like_count = self._extract_like_count(html)

        return RecoveredVideoData(
            title=title,
            description=description,
            channel_name_hint=channel_name_hint,
            channel_id=channel_id,
            view_count=view_count,
            like_count=like_count,
            upload_date=upload_date,
            tags=tags,
            category_id=category_id,
            thumbnail_url=thumbnail_url,
            snapshot_timestamp=snapshot_timestamp,
        )

    def _extract_from_meta_tags(
        self, html: str, snapshot_timestamp: str
    ) -> RecoveredVideoData | None:
        """
        Extract metadata from HTML meta tags using BeautifulSoup.

        Parses Open Graph (``og:``) meta tags and ``itemprop`` attributes
        to recover video metadata from pre-2017 archived pages that lack
        the ``ytInitialPlayerResponse`` JSON.

        Parameters
        ----------
        html : str
            Raw HTML content of the archived YouTube page.
        snapshot_timestamp : str
            CDX timestamp of the snapshot (14 digits).

        Returns
        -------
        RecoveredVideoData | None
            Extracted metadata if any usable tags were found, or ``None``
            if no meaningful metadata could be extracted.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Extract og:title
        title: str | None = None
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            title = str(og_title["content"])

        # Extract og:description
        description: str | None = None
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc and og_desc.get("content"):
            description = str(og_desc["content"])

        # Extract og:image -> thumbnail_url
        thumbnail_url: str | None = None
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            thumbnail_url = str(og_image["content"])

        # Extract all og:video:tag -> tags list
        tags: list[str] = []
        for tag_meta in soup.find_all(
            "meta", attrs={"property": "og:video:tag"}
        ):
            content = tag_meta.get("content")
            if content:
                tags.append(str(content))

        # Extract itemprop="datePublished" -> upload_date
        upload_date: datetime | None = None
        date_meta = soup.find(attrs={"itemprop": "datePublished"})
        if date_meta:
            date_str = date_meta.get("content")
            if date_str:
                try:
                    upload_date = datetime.strptime(
                        str(date_str), "%Y-%m-%d"
                    ).replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

        # Extract itemprop="interactionCount" -> view_count
        view_count: int | None = None
        interaction_meta = soup.find(attrs={"itemprop": "interactionCount"})
        if interaction_meta:
            count_str = interaction_meta.get("content")
            if count_str:
                try:
                    view_count = int(str(count_str))
                except (ValueError, TypeError):
                    pass

        # Extract itemprop="genre" -> category_id (via YOUTUBE_CATEGORY_MAP)
        category_id: str | None = None
        genre_meta = soup.find(attrs={"itemprop": "genre"})
        if genre_meta:
            genre_str = genre_meta.get("content")
            if genre_str:
                category_id = YOUTUBE_CATEGORY_MAP.get(str(genre_str))

        # Extract channel ID: try itemprop="channelId" first, then link href pattern
        channel_id: str | None = None
        channel_id_meta = soup.find(attrs={"itemprop": "channelId"})
        if channel_id_meta:
            cid = channel_id_meta.get("content", "")
            if cid and _CHANNEL_ID_RE.match(str(cid)):
                channel_id = str(cid)
        if channel_id is None:
            for link in soup.find_all("link", attrs={"itemprop": "url"}):
                href = link.get("href", "")
                if href:
                    channel_match = re.search(r"(UC[A-Za-z0-9_-]{22})", str(href))
                    if channel_match:
                        channel_id = channel_match.group(1)
                        break

        # Extract channel name from <link itemprop="url" href=".../user/Name">
        channel_name_hint: str | None = None
        for link in soup.find_all("link", attrs={"itemprop": "url"}):
            href = str(link.get("href", ""))
            user_match = re.search(r"/user/([^/?#]+)", href)
            if user_match:
                channel_name_hint = user_match.group(1)
                break
            # Also try /channel/ display name from og or other sources
            c_match = re.search(r"/c/([^/?#]+)", href)
            if c_match:
                channel_name_hint = c_match.group(1)
                break

        # Check if any usable data was found
        has_any = any([
            title,
            description,
            thumbnail_url,
            tags,
            upload_date,
            view_count is not None,
            category_id,
            channel_id,
            channel_name_hint,
        ])

        if not has_any:
            return None

        return RecoveredVideoData(
            title=title,
            description=description,
            thumbnail_url=thumbnail_url,
            tags=tags,
            upload_date=upload_date,
            view_count=view_count,
            category_id=category_id,
            channel_id=channel_id,
            channel_name_hint=channel_name_hint,
            snapshot_timestamp=snapshot_timestamp,
        )

    def _extract_like_count(self, html: str) -> int | None:
        """
        Extract like count from ytInitialData JSON blob.

        The like count is stored in the ``toggleButtonRenderer`` within
        ``videoPrimaryInfoRenderer`` in ytInitialData, with a label like
        ``"1,579 likes"``.

        Parameters
        ----------
        html : str
            Raw HTML content of the archived YouTube page.

        Returns
        -------
        int | None
            The like count as an integer, or None if not found.
        """
        match = _YT_INITIAL_DATA_RE.search(html)
        if not match:
            return None

        json_str = _extract_json_object(html, match.end())
        if not json_str:
            return None

        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            return None

        # Navigate the nested structure to find the like count label
        # Path: contents.twoColumnWatchNextResults.results.results.contents[]
        #   .videoPrimaryInfoRenderer.videoActions.menuRenderer.topLevelButtons[]
        #   .toggleButtonRenderer.defaultText.accessibility.accessibilityData.label
        try:
            text = json.dumps(data)
            # Search for the "N likes" pattern in accessibility labels
            like_match = re.search(
                r'"label"\s*:\s*"([\d,]+)\s+likes?"', text
            )
            if like_match:
                count_str = like_match.group(1).replace(",", "")
                return int(count_str)
        except (ValueError, TypeError):
            pass

        return None

    async def _extract_with_selenium(
        self, snapshot: CdxSnapshot
    ) -> RecoveredVideoData | None:
        """
        Extract metadata using Selenium WebDriver (placeholder).

        This method serves as a placeholder for optional Selenium-based
        extraction of pre-2017 archived pages that require JavaScript
        rendering. The actual Selenium implementation is deferred.

        Parameters
        ----------
        snapshot : CdxSnapshot
            The CDX snapshot to render with Selenium.

        Returns
        -------
        RecoveredVideoData | None
            Always returns ``None`` in this placeholder implementation.
        """
        return None
