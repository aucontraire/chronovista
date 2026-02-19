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
from bs4 import BeautifulSoup, Tag

from chronovista import __version__
from chronovista.services.recovery import SELENIUM_AVAILABLE
from chronovista.services.recovery.cdx_client import RateLimiter
from chronovista.services.recovery.models import (
    CdxSnapshot,
    RecoveredChannelData,
    RecoveredVideoData,
)

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
            # Supplement missing fields from HTML DOM.  Transitional pages
            # (pre-mid-2020) may have ytInitialPlayerResponse but with an
            # incomplete videoDetails (no shortDescription) and no like
            # count in ytInitialData.  The full data is often present in
            # dedicated HTML elements (#eow-description, like button).
            desc_needs_supplement = (
                result.description is None
                or (result.description.endswith("...") and len(result.description) < 200)
            )
            if desc_needs_supplement or result.like_count is None:
                self._supplement_from_html(result, html, supplement_desc=desc_needs_supplement)
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

        # Try full description from #eow-description HTML element.
        # Old-format YouTube pages (pre-mid-2020) have the complete
        # description in this element, while og:description is always
        # truncated to 160 characters by YouTube.
        eow_desc = soup.find(id="eow-description")
        if eow_desc:
            for br in eow_desc.find_all("br"):
                br.replace_with("\n")
            full_desc = eow_desc.get_text().strip()
            # Clean up excessive consecutive newlines
            full_desc = re.sub(r"\n{3,}", "\n\n", full_desc)
            if full_desc and (
                description is None or len(full_desc) > len(description)
            ):
                description = full_desc

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

        # Extract channel ID using multiple strategies in priority order:
        # 1. itemprop="channelId" meta tag (modern structured data)
        # 2. <link itemprop="url"> with channel URL (modern structured data)
        # 3. data-channel-external-id attribute (pre-2020 subscribe buttons)
        # 4. <a> tags linking to /channel/UCxxx (pre-2020 page layouts)
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
        if channel_id is None:
            ext_id_el = soup.find(attrs={"data-channel-external-id": True})
            if ext_id_el:
                ext_id = str(ext_id_el["data-channel-external-id"])
                if _CHANNEL_ID_RE.match(ext_id):
                    channel_id = ext_id
        if channel_id is None:
            for anchor in soup.find_all("a", href=True):
                href = str(anchor["href"])
                anchor_match = re.search(r"/channel/(UC[A-Za-z0-9_-]{22})", href)
                if anchor_match:
                    channel_id = anchor_match.group(1)
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

    def _supplement_from_html(
        self,
        result: RecoveredVideoData,
        html: str,
        *,
        supplement_desc: bool = True,
    ) -> None:
        """
        Supplement missing or truncated fields from HTML DOM elements.

        When ``_extract_from_json`` succeeds but leaves gaps (no
        ``shortDescription`` in ``videoDetails``, or a truncated
        ``shortDescription`` ending in ``...``), the full data is often
        present in dedicated HTML elements that predate the JSON era.

        Mutates *result* in place — sets ``description`` and/or
        ``like_count`` when a richer value is found in the HTML.

        Parameters
        ----------
        result : RecoveredVideoData
            Mutable result from JSON extraction with potential gaps.
        html : str
            Raw HTML content of the archived YouTube page.
        supplement_desc : bool
            Whether to attempt description supplementation (default True).
        """
        soup = BeautifulSoup(html, "html.parser")

        # Supplement description from #eow-description when missing or truncated
        if supplement_desc:
            eow_desc = soup.find(id="eow-description")
            if eow_desc:
                for br in eow_desc.find_all("br"):
                    br.replace_with("\n")
                full_desc = eow_desc.get_text().strip()
                full_desc = re.sub(r"\n{3,}", "\n\n", full_desc)
                if full_desc and (
                    result.description is None
                    or len(full_desc) > len(result.description)
                ):
                    result.description = full_desc

        # Supplement like_count from HTML elements
        if result.like_count is None:
            result.like_count = self._extract_like_count_from_html(soup)

    def _extract_like_count_from_html(
        self, soup: BeautifulSoup
    ) -> int | None:
        """
        Extract like count from HTML elements as a fallback.

        Checks five patterns in priority order, starting with the most
        targeted (class-scoped) before falling back to broad scans:

        1. **Old-format button content**: The number inside
           ``<span class="yt-uix-button-content">`` within the like
           button (class ``like-button-renderer-like-button``).
           Handles European thousand separators (``2.510`` → 2510).
        2. **Old-format aria-label (locale-agnostic)**: Extract the
           first multi-digit number from the like button's
           ``aria-label``, regardless of language.  Covers German
           ``"Ich mag das Video (wie 2.510 andere auch)"``, Spanish,
           French, etc.
        3. **Modern format**: ``aria-label="N likes"`` on
           ``yt-formatted-string`` elements (scoped to avoid stray
           matches on unrelated page elements).
        4. **Older English format**: ``aria-label="like this video along
           with N other people"`` on the like button.
        5. **ytInitialData accessibility label**: ``"N likes"`` in
           a ``yt-formatted-string`` or button ``aria-label`` (broad
           scan as last resort).

        Parameters
        ----------
        soup : BeautifulSoup
            Parsed HTML of the archived YouTube page.

        Returns
        -------
        int | None
            The like count as an integer, or None if not found.
        """
        # Collect like buttons (exclude dislike) once for patterns 1-2
        like_buttons: list[Tag] = []
        for btn in soup.find_all(
            "button", class_="like-button-renderer-like-button"
        ):
            classes = btn.get("class")
            if classes is not None and any(
                "dislike" in str(c) for c in classes
            ):
                continue
            like_buttons.append(btn)

        # Pattern 1: Old-format button content <span class="yt-uix-button-content">
        for btn in like_buttons:
            content_span = btn.find(class_="yt-uix-button-content")
            if content_span:
                text = content_span.get_text(strip=True)
                # Remove thousand separators (both . and , conventions)
                cleaned = re.sub(r"[.,]", "", text)
                try:
                    return int(cleaned)
                except (ValueError, TypeError):
                    pass

        # Pattern 2: Locale-agnostic number from like button aria-label.
        # Works for any language: DE "wie 2.510 andere", EN "2,510 likes",
        # ES "2.510 personas", FR "2 510 autres", etc.
        for btn in like_buttons:
            label = btn.get("aria-label")
            if not label:
                continue
            # Extract first multi-digit number (may contain . or , separators)
            match = re.search(r"(\d[\d.,]*\d)", str(label))
            if match:
                cleaned = re.sub(r"[.,]", "", match.group(1))
                try:
                    return int(cleaned)
                except (ValueError, TypeError):
                    pass

        # Pattern 3: Modern yt-formatted-string with aria-label="N likes"
        for elem in soup.find_all("yt-formatted-string", attrs={"aria-label": True}):
            label = str(elem.get("aria-label", ""))
            match = re.search(r"([\d,]+)\s+likes?", label)
            if match:
                try:
                    return int(match.group(1).replace(",", ""))
                except (ValueError, TypeError):
                    pass

        # Pattern 4: "like this video along with N other people"
        for elem in soup.find_all(attrs={"aria-label": True}):
            label = str(elem.get("aria-label", ""))
            match = re.search(r"along with ([\d,]+) other", label)
            if match:
                try:
                    return int(match.group(1).replace(",", ""))
                except (ValueError, TypeError):
                    pass

        # Pattern 5: Broad scan — aria-label="N likes" on any element
        for elem in soup.find_all(attrs={"aria-label": True}):
            label = str(elem.get("aria-label", ""))
            match = re.search(r"([\d,]+)\s+likes?", label)
            if match:
                try:
                    return int(match.group(1).replace(",", ""))
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

    # ------------------------------------------------------------------
    # Channel metadata extraction
    # ------------------------------------------------------------------

    async def extract_channel_metadata(
        self, snapshot: CdxSnapshot, channel_id: str
    ) -> RecoveredChannelData | None:
        """
        Extract channel metadata from a Wayback Machine snapshot.

        Fetches the archived channel page, checks for embedded
        ``ytInitialData`` JSON first, then falls back to HTML meta tag
        extraction for pre-2017 pages.

        Parameters
        ----------
        snapshot : CdxSnapshot
            The CDX snapshot of the channel page to fetch and parse.
        channel_id : str
            Expected YouTube channel ID for cross-validation. If the
            ``externalId`` found in the page JSON does not match this
            value, the snapshot is discarded and ``None`` is returned.

        Returns
        -------
        RecoveredChannelData | None
            Extracted channel metadata, or ``None`` if no useful data
            could be extracted or the channel ID did not match.
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
            except (
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.ConnectError,
            ) as e:
                backoff = _RETRY_BACKOFF_SECONDS[attempt]
                logger.warning(
                    "Channel fetch attempt %d/%d for snapshot %s failed "
                    "(%s), retrying in %.0fs",
                    attempt + 1,
                    _MAX_FETCH_RETRIES,
                    snapshot.timestamp,
                    type(e).__name__,
                    backoff,
                )
                await asyncio.sleep(backoff)
            except Exception as e:
                logger.warning(
                    "Failed to fetch channel snapshot %s: %s: %s",
                    snapshot.timestamp,
                    type(e).__name__,
                    e,
                )
                return None

        if html is None:
            logger.warning(
                "Failed to fetch channel snapshot %s after %d retries",
                snapshot.timestamp,
                _MAX_FETCH_RETRIES,
            )
            return None

        # Try JSON extraction first
        result = self._extract_channel_from_json(
            html, snapshot.timestamp, channel_id
        )
        if result is not None:
            return result

        # Fall back to meta tag extraction (no cross-validation possible)
        return self._extract_channel_from_meta_tags(html, snapshot.timestamp)

    def _extract_channel_from_json(
        self,
        html: str,
        snapshot_timestamp: str,
        expected_channel_id: str,
    ) -> RecoveredChannelData | None:
        """
        Extract channel metadata from ``ytInitialData`` JSON in page source.

        Navigates into ``metadata.channelMetadataRenderer`` for core fields
        (title, description, avatar, externalId, country, defaultLanguage)
        and ``header.c4TabbedHeaderRenderer`` for subscriber/video counts.

        Parameters
        ----------
        html : str
            Raw HTML content of the archived YouTube channel page.
        snapshot_timestamp : str
            CDX timestamp of the snapshot (14 digits).
        expected_channel_id : str
            Channel ID that the page is expected to belong to. Used for
            cross-validation against ``externalId``.

        Returns
        -------
        RecoveredChannelData | None
            Extracted channel metadata, or ``None`` if JSON was not found,
            was malformed, or the channel ID did not match.
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
            logger.warning(
                "Malformed ytInitialData JSON in channel snapshot %s",
                snapshot_timestamp,
            )
            return None

        # --- channelMetadataRenderer ---
        metadata_renderer = (
            data.get("metadata", {}).get("channelMetadataRenderer", {})
        )
        if not metadata_renderer:
            return None

        # Cross-validate channel ID (FR-023)
        external_id = metadata_renderer.get("externalId")
        if external_id and external_id != expected_channel_id:
            logger.warning(
                "Channel ID mismatch in snapshot %s: expected %s, "
                "found %s — discarding snapshot",
                snapshot_timestamp,
                expected_channel_id,
                external_id,
            )
            return None

        title = metadata_renderer.get("title")
        description = metadata_renderer.get("description")
        country = metadata_renderer.get("country")
        default_language = metadata_renderer.get("defaultLanguage")

        # Avatar / thumbnail
        thumbnail_url: str | None = None
        avatar = metadata_renderer.get("avatar", {})
        thumbnails = avatar.get("thumbnails", [])
        if thumbnails:
            thumbnail_url = thumbnails[0].get("url")

        # Normalise country to uppercase 2-letter ISO code or None
        if country:
            country = country.strip().upper()
            if not re.match(r"^[A-Z]{2}$", country):
                country = None

        # --- c4TabbedHeaderRenderer (subscriber + video counts) ---
        header_renderer = (
            data.get("header", {}).get("c4TabbedHeaderRenderer", {})
        )
        subscriber_count: int | None = None
        video_count: int | None = None

        sub_text = (
            header_renderer.get("subscriberCountText", {})
            .get("simpleText", "")
        )
        if sub_text:
            subscriber_count = self._parse_subscriber_count(sub_text)

        video_text_runs = (
            header_renderer.get("videosCountText", {}).get("runs", [])
        )
        if video_text_runs:
            video_count = self._parse_video_count(
                video_text_runs[0].get("text", "")
            )

        # Check if any usable data was found
        has_any = any([
            title,
            description,
            thumbnail_url,
            subscriber_count is not None,
            video_count is not None,
            country,
            default_language,
        ])
        if not has_any:
            return None

        return RecoveredChannelData(
            title=title,
            description=description,
            subscriber_count=subscriber_count,
            video_count=video_count,
            thumbnail_url=thumbnail_url,
            country=country,
            default_language=default_language,
            snapshot_timestamp=snapshot_timestamp,
        )

    def _extract_channel_from_meta_tags(
        self, html: str, snapshot_timestamp: str
    ) -> RecoveredChannelData | None:
        """
        Extract channel metadata from HTML meta tags using BeautifulSoup.

        Parses Open Graph meta tags (``og:title``, ``og:description``,
        ``og:image``) as a fallback for pre-2017 channel pages that lack
        the ``ytInitialData`` JSON.

        Parameters
        ----------
        html : str
            Raw HTML content of the archived YouTube channel page.
        snapshot_timestamp : str
            CDX timestamp of the snapshot (14 digits).

        Returns
        -------
        RecoveredChannelData | None
            Extracted channel metadata if any usable tags were found, or
            ``None`` if no meaningful metadata could be extracted.
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

        # Check if any usable data was found
        has_any = any([title, description, thumbnail_url])
        if not has_any:
            return None

        return RecoveredChannelData(
            title=title,
            description=description,
            thumbnail_url=thumbnail_url,
            snapshot_timestamp=snapshot_timestamp,
        )

    @staticmethod
    def _parse_subscriber_count(text: str) -> int | None:
        """
        Parse a human-readable subscriber count string into an integer.

        Handles YouTube's various formatting conventions including SI
        suffixes (K, M, B), comma-separated numbers, and the special
        "No subscribers" case.

        Parameters
        ----------
        text : str
            Subscriber count text, e.g. ``"1.2M subscribers"``,
            ``"500K subscribers"``, ``"1,234 subscribers"``,
            ``"No subscribers"``.

        Returns
        -------
        int | None
            Parsed integer count, or ``None`` if the text could not be
            parsed.

        Examples
        --------
        >>> PageParser._parse_subscriber_count("1.2M subscribers")
        1200000
        >>> PageParser._parse_subscriber_count("500K subscribers")
        500000
        >>> PageParser._parse_subscriber_count("1,234 subscribers")
        1234
        >>> PageParser._parse_subscriber_count("No subscribers")
        0
        """
        if not text or not text.strip():
            return None

        cleaned = text.strip()

        # "No subscribers" special case
        if cleaned.lower().startswith("no "):
            return 0

        # Remove "subscribers" suffix (case-insensitive)
        cleaned = re.sub(r"\s*subscribers?\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        if not cleaned:
            return None

        # SI suffix multipliers
        suffix_map: dict[str, int] = {
            "K": 1_000,
            "M": 1_000_000,
            "B": 1_000_000_000,
        }

        last_char = cleaned[-1].upper()
        if last_char in suffix_map:
            numeric_part = cleaned[:-1].strip().replace(",", "")
            try:
                value = float(numeric_part) * suffix_map[last_char]
                return int(value)
            except (ValueError, TypeError):
                return None

        # Plain number (possibly comma-separated)
        numeric_str = cleaned.replace(",", "")
        try:
            return int(numeric_str)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_video_count(text: str) -> int | None:
        """
        Parse a human-readable video count string into an integer.

        Handles YouTube's formatting with optional comma separators and
        the ``"videos"`` suffix.

        Parameters
        ----------
        text : str
            Video count text, e.g. ``"1,234 videos"``, ``"500"``.

        Returns
        -------
        int | None
            Parsed integer count, or ``None`` if the text could not be
            parsed.

        Examples
        --------
        >>> PageParser._parse_video_count("1,234 videos")
        1234
        >>> PageParser._parse_video_count("500")
        500
        """
        if not text or not text.strip():
            return None

        cleaned = text.strip()

        # Remove "videos" suffix (case-insensitive)
        cleaned = re.sub(r"\s*videos?\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        if not cleaned:
            return None

        # Plain number (possibly comma-separated)
        numeric_str = cleaned.replace(",", "")
        try:
            return int(numeric_str)
        except (ValueError, TypeError):
            return None
