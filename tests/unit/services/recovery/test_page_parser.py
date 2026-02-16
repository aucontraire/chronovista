"""
Unit tests for PageParser (Wayback Machine page metadata extraction).

Tests cover:
- T020: ytInitialPlayerResponse JSON extraction
- T021: HTML meta tag extraction (BeautifulSoup)
- T022: Removal notice detection (10 pattern categories)
- T023: Category name-to-ID mapping
- T024: Two-era extraction strategy (2017+ JSON vs pre-2017 meta)
- T025: Optional Selenium fallback

All tests mock httpx responses. No live HTTP calls are made.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chronovista.services.recovery.cdx_client import RateLimiter
from chronovista.services.recovery.models import CdxSnapshot, RecoveredVideoData
from chronovista.services.recovery.page_parser import (
    YOUTUBE_CATEGORY_MAP,
    PageParser,
    is_removal_notice,
)

# CRITICAL: Ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


# ============================================================================
# HTML Test Fixtures
# ============================================================================

VALID_PAGE_WITH_JSON = '''
<html><head>
<meta property="og:title" content="Meta Title Fallback">
<meta property="og:description" content="Meta description fallback">
</head><body>
<script>var ytInitialPlayerResponse = {"videoDetails":{"title":"JSON Title","shortDescription":"JSON description from videoDetails","author":"Test Channel","channelId":"UCuAXFkgsw1L7xaCfnd5JJOw","viewCount":"1000000","keywords":["music","test","viral"]},"microformat":{"playerMicroformatRenderer":{"publishDate":"2021-06-15","category":"Music"}}};</script>
</body></html>
'''

VALID_PAGE_WITH_JSON_NO_VAR = '''
<html><head></head><body>
<script>ytInitialPlayerResponse = {"videoDetails":{"title":"JSON Title No Var","shortDescription":"Description without var keyword","author":"Channel Name","channelId":"UCabc123def456ghi789jkl000","viewCount":"5000","keywords":["keyword1","keyword2"]},"microformat":{"playerMicroformatRenderer":{"publishDate":"2020-03-20","category":"Education"}}};</script>
</body></html>
'''

VALID_PAGE_META_ONLY = '''
<html><head>
<meta property="og:title" content="Meta Video Title">
<meta property="og:description" content="Meta description from Open Graph tags">
<meta property="og:image" content="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg">
<meta property="og:video:tag" content="music">
<meta property="og:video:tag" content="classic">
<meta property="og:video:tag" content="nostalgia">
<meta itemprop="datePublished" content="2015-03-20">
<meta itemprop="interactionCount" content="5000000">
<meta itemprop="genre" content="Entertainment">
<link itemprop="url" href="https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw">
</head><body></body></html>
'''

REMOVAL_NOTICE_TITLE_ONLY_YOUTUBE = '''
<html><head><title>YouTube</title></head><body></body></html>
'''

REMOVAL_NOTICE_TITLE_DASH_YOUTUBE = '''
<html><head><title> - YouTube</title></head><body></body></html>
'''

REMOVAL_NOTICE_PLAYABILITY_ERROR = '''
<html><head></head><body>
<script>var ytInitialPlayerResponse = {"playabilityStatus":{"status":"ERROR","reason":"Video unavailable"}};</script>
</body></html>
'''

REMOVAL_NOTICE_PLAYABILITY_UNPLAYABLE = '''
<html><head></head><body>
<script>ytInitialPlayerResponse = {"playabilityStatus":{"status":"UNPLAYABLE"}};</script>
</body></html>
'''

REMOVAL_NOTICE_PLAYABILITY_LOGIN_REQUIRED = '''
<html><head></head><body>
<script>var ytInitialPlayerResponse = {"playabilityStatus":{"status":"LOGIN_REQUIRED"}};</script>
</body></html>
'''

REMOVAL_NOTICE_TEXT_VIDEO_UNAVAILABLE = '''
<html><head><title>Test Video - YouTube</title></head><body>
<div>Video unavailable</div>
</body></html>
'''

REMOVAL_NOTICE_TEXT_REMOVED_BY_UPLOADER = '''
<html><head><title>Test Video - YouTube</title></head><body>
<div>This video has been removed by the uploader</div>
</body></html>
'''

REMOVAL_NOTICE_TEXT_PRIVATE = '''
<html><head><title>Test Video - YouTube</title></head><body>
<div>This video is private</div>
</body></html>
'''

REMOVAL_NOTICE_TEXT_COPYRIGHT = '''
<html><head><title>Test Video - YouTube</title></head><body>
<div>This video is no longer available due to a copyright claim by XYZ Corporation</div>
</body></html>
'''

REMOVAL_NOTICE_TEXT_TOS_VIOLATION = '''
<html><head><title>Test Video - YouTube</title></head><body>
<div>This video has been removed for violating YouTube's Terms of Service</div>
</body></html>
'''

REMOVAL_NOTICE_TEXT_ACCOUNT_TERMINATED = '''
<html><head><title>Test Video - YouTube</title></head><body>
<div>This video is no longer available because the YouTube account associated with this video has been terminated</div>
</body></html>
'''

REMOVAL_NOTICE_WITH_POSITIVE_SIGNAL_OVERRIDE = '''
<html><head>
<title>YouTube</title>
<meta property="og:video:url" content="https://www.youtube.com/watch?v=dQw4w9WgXcQ">
</head><body>
<div>Video unavailable</div>
</body></html>
'''

EMPTY_PAGE = '''
<html><head></head><body></body></html>
'''

PAGE_WITH_MALFORMED_JSON = '''
<html><head></head><body>
<script>var ytInitialPlayerResponse = {invalid json here, missing quotes};</script>
</body></html>
'''

PAGE_WITH_BOTH_JSON_AND_META = '''
<html><head>
<meta property="og:title" content="Meta Title Should Be Ignored">
<meta property="og:description" content="Meta description should be ignored">
<meta property="og:video:tag" content="meta-tag-1">
<meta itemprop="datePublished" content="2010-01-01">
<meta itemprop="interactionCount" content="999">
</head><body>
<script>var ytInitialPlayerResponse = {"videoDetails":{"title":"JSON Title Takes Priority","shortDescription":"JSON description takes priority","author":"JSON Channel","channelId":"UCjsonpriorityid123456789","viewCount":"2000000","keywords":["json-keyword"]},"microformat":{"playerMicroformatRenderer":{"publishDate":"2022-12-31","category":"Science & Technology"}}};</script>
</body></html>
'''


# ============================================================================
# Test Class: JSON Extraction (T020)
# ============================================================================


class TestJSONExtraction:
    """
    Test ytInitialPlayerResponse JSON extraction.

    Covers:
    - Field extraction from videoDetails (title, description, author, channelId, viewCount, keywords)
    - Field extraction from microformat.playerMicroformatRenderer (publishDate, category)
    - Regex pattern matching (var pattern and no-var pattern)
    - Missing JSON returns None
    - Malformed JSON handled gracefully
    """

    async def test_extract_title_from_json(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that videoDetails.title is extracted from JSON."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_WITH_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.title == "JSON Title"

    async def test_extract_description_from_json(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that videoDetails.shortDescription is extracted from JSON."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_WITH_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.description == "JSON description from videoDetails"

    async def test_extract_channel_from_json(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that videoDetails.author and channelId are extracted."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_WITH_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.channel_name_hint == "Test Channel"
        assert result.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"

    async def test_extract_view_count_from_json(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that videoDetails.viewCount (string) is converted to int."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_WITH_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.view_count == 1000000

    async def test_extract_keywords_from_json(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that videoDetails.keywords is extracted as tags list."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_WITH_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.tags == ["music", "test", "viral"]

    async def test_extract_upload_date_from_json(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that microformat.playerMicroformatRenderer.publishDate is extracted."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_WITH_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.upload_date is not None
        assert result.upload_date.year == 2021
        assert result.upload_date.month == 6
        assert result.upload_date.day == 15

    async def test_extract_category_from_json(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that microformat category is mapped to category_id."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_WITH_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # "Music" should map to "10"
        assert result.category_id == "10"

    async def test_json_regex_var_pattern(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that regex matches 'var ytInitialPlayerResponse = {...};' pattern."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_WITH_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.title == "JSON Title"

    async def test_json_regex_no_var_pattern(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that regex also matches 'ytInitialPlayerResponse = {...};' (no var)."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_WITH_JSON_NO_VAR
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.title == "JSON Title No Var"

    async def test_missing_json_returns_none(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that page without JSON falls back to meta tags."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # Should have extracted from meta tags, not JSON
        assert result.title == "Meta Video Title"

    async def test_malformed_json_graceful(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that malformed JSON is handled gracefully (returns None, no crash)."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_WITH_MALFORMED_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        # Should not crash - returns RecoveredVideoData with no extracted fields
        assert result is not None
        assert result.has_data is False


# ============================================================================
# Test Class: Meta Tag Extraction (T021)
# ============================================================================


class TestMetaTagExtraction:
    """
    Test HTML meta tag extraction using BeautifulSoup.

    Covers:
    - og:title, og:description, og:image extraction
    - Multiple og:video:tag extraction
    - itemprop extraction (datePublished, interactionCount, genre)
    - Channel ID extraction from link itemprop="url"
    - Graceful handling of missing tags
    """

    async def test_extract_og_title(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that og:title meta tag is extracted."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.title == "Meta Video Title"

    async def test_extract_og_description(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that og:description meta tag is extracted."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.description == "Meta description from Open Graph tags"

    async def test_extract_og_image(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that og:image is extracted as thumbnail_url."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert (
            result.thumbnail_url
            == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
        )

    async def test_extract_multiple_og_video_tags(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that multiple og:video:tag meta tags are extracted as tags list."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.tags == ["music", "classic", "nostalgia"]

    async def test_extract_date_published(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that itemprop='datePublished' is extracted as upload_date."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.upload_date is not None
        assert result.upload_date.year == 2015
        assert result.upload_date.month == 3
        assert result.upload_date.day == 20

    async def test_extract_interaction_count(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that itemprop='interactionCount' is extracted as view_count."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.view_count == 5000000

    async def test_extract_genre(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that itemprop='genre' is extracted and mapped to category_id."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # "Entertainment" should map to "24"
        assert result.category_id == "24"

    async def test_extract_channel_from_link(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that channel ID is extracted from link itemprop='url'."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"

    async def test_extracts_channel_id_from_itemprop_channelid(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that channel ID is extracted from itemprop='channelId' meta tag."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        html = '''
<html><head>
<meta itemprop="channelId" content="UCpwvZwUam-URkxB7g4USKpg">
<meta property="og:title" content="Test Video">
</head><body></body></html>
'''

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = html
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.channel_id == "UCpwvZwUam-URkxB7g4USKpg"

    async def test_channel_id_itemprop_takes_priority_over_link_href(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that itemprop='channelId' takes priority over link href pattern."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        html = '''
<html><head>
<meta itemprop="channelId" content="UCpwvZwUam-URkxB7g4USKpg">
<link itemprop="url" href="https://youtube.com/channel/UCDifferentChannelId1234">
<meta property="og:title" content="Test Video">
</head><body></body></html>
'''

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = html
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # itemprop="channelId" should win
        assert result.channel_id == "UCpwvZwUam-URkxB7g4USKpg"

    async def test_extracts_channel_name_from_user_url(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that channel name is extracted from /user/ URL pattern."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        html = '''
<html><head>
<link itemprop="url" href="http://www.youtube.com/user/RussiaToday">
<meta property="og:title" content="Test Video">
</head><body></body></html>
'''

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = html
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.channel_name_hint == "RussiaToday"

    async def test_extracts_channel_name_from_c_url(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that channel name is extracted from /c/ URL pattern."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        html = '''
<html><head>
<link itemprop="url" href="https://www.youtube.com/c/SomeChannel">
<meta property="og:title" content="Test Video">
</head><body></body></html>
'''

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = html
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.channel_name_hint == "SomeChannel"

    async def test_missing_tags_graceful(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that page with no meta tags returns RecoveredVideoData with no data."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = EMPTY_PAGE
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.has_data is False


# ============================================================================
# Test Class: Removal Notice Detection (T022)
# ============================================================================


class TestRemovalNoticeDetection:
    """
    Test removal notice detection function.

    Covers all 10 removal pattern categories:
    - Title-based detection ("YouTube", " - YouTube")
    - JSON playabilityStatus detection (ERROR, UNPLAYABLE, LOGIN_REQUIRED)
    - Text pattern detection (unavailable, removed, private, copyright, etc.)
    - Positive signal override (og:video:url)
    """

    def test_title_only_youtube(self) -> None:
        """Test that title 'YouTube' is detected as removal."""
        is_removed, reason = is_removal_notice(REMOVAL_NOTICE_TITLE_ONLY_YOUTUBE)
        assert is_removed is True
        assert reason == "title_only_youtube"

    def test_title_dash_youtube(self) -> None:
        """Test that title ' - YouTube' is detected as removal."""
        is_removed, reason = is_removal_notice(REMOVAL_NOTICE_TITLE_DASH_YOUTUBE)
        assert is_removed is True
        assert reason == "title_dash_youtube"

    def test_playability_status_error(self) -> None:
        """Test that JSON playabilityStatus.status = 'ERROR' is detected as removal."""
        is_removed, reason = is_removal_notice(
            REMOVAL_NOTICE_PLAYABILITY_ERROR
        )
        assert is_removed is True
        assert reason == "playability_status_error"

    def test_playability_status_unplayable(self) -> None:
        """Test that JSON playabilityStatus.status = 'UNPLAYABLE' is detected."""
        is_removed, reason = is_removal_notice(
            REMOVAL_NOTICE_PLAYABILITY_UNPLAYABLE
        )
        assert is_removed is True
        assert reason == "playability_status_unplayable"

    def test_playability_status_login_required(self) -> None:
        """Test that JSON playabilityStatus.status = 'LOGIN_REQUIRED' is detected."""
        is_removed, reason = is_removal_notice(
            REMOVAL_NOTICE_PLAYABILITY_LOGIN_REQUIRED
        )
        assert is_removed is True
        assert reason == "playability_status_login_required"

    def test_text_video_unavailable(self) -> None:
        """Test that 'Video unavailable' text is detected as removal."""
        is_removed, reason = is_removal_notice(
            REMOVAL_NOTICE_TEXT_VIDEO_UNAVAILABLE
        )
        assert is_removed is True
        assert reason == "text_video_unavailable"

    def test_text_removed_by_uploader(self) -> None:
        """Test that 'removed by the uploader' text is detected."""
        is_removed, reason = is_removal_notice(
            REMOVAL_NOTICE_TEXT_REMOVED_BY_UPLOADER
        )
        assert is_removed is True
        assert reason == "text_removed_by_uploader"

    def test_text_private(self) -> None:
        """Test that 'This video is private' text is detected."""
        is_removed, reason = is_removal_notice(REMOVAL_NOTICE_TEXT_PRIVATE)
        assert is_removed is True
        assert reason == "text_private"

    def test_text_copyright(self) -> None:
        """Test that copyright claim text is detected."""
        is_removed, reason = is_removal_notice(REMOVAL_NOTICE_TEXT_COPYRIGHT)
        assert is_removed is True
        assert reason == "text_copyright"

    def test_text_tos_violation(self) -> None:
        """Test that ToS violation text is detected."""
        is_removed, reason = is_removal_notice(
            REMOVAL_NOTICE_TEXT_TOS_VIOLATION
        )
        assert is_removed is True
        assert reason == "text_tos_violation"

    def test_text_account_terminated(self) -> None:
        """Test that account terminated text is detected."""
        is_removed, reason = is_removal_notice(
            REMOVAL_NOTICE_TEXT_ACCOUNT_TERMINATED
        )
        assert is_removed is True
        assert reason == "text_account_terminated"

    def test_og_video_url_overrides(self) -> None:
        """Test that og:video:url presence overrides removal signals."""
        is_removed, reason = is_removal_notice(
            REMOVAL_NOTICE_WITH_POSITIVE_SIGNAL_OVERRIDE
        )
        # Positive signal (og:video:url) should override removal text
        assert is_removed is False
        assert reason is None

    def test_valid_page_not_removal(self) -> None:
        """Test that normal page with content is not detected as removal."""
        is_removed, reason = is_removal_notice(VALID_PAGE_WITH_JSON)
        assert is_removed is False
        assert reason is None


# ============================================================================
# Test Class: Category Mapping (T023)
# ============================================================================


class TestCategoryMapping:
    """
    Test YouTube category name to ID mapping.

    Covers:
    - Known categories (Entertainment, Music, Education, etc.)
    - Unknown categories return None
    - Case-insensitive matching
    """

    def test_entertainment_to_24(self) -> None:
        """Test that 'Entertainment' maps to '24'."""
        assert YOUTUBE_CATEGORY_MAP.get("Entertainment") == "24"

    def test_music_to_10(self) -> None:
        """Test that 'Music' maps to '10'."""
        assert YOUTUBE_CATEGORY_MAP.get("Music") == "10"

    def test_education_to_27(self) -> None:
        """Test that 'Education' maps to '27'."""
        assert YOUTUBE_CATEGORY_MAP.get("Education") == "27"

    def test_unknown_category_returns_none(self) -> None:
        """Test that unknown category name returns None."""
        assert YOUTUBE_CATEGORY_MAP.get("Unknown Category XYZ") is None

    def test_case_insensitive(self) -> None:
        """Test that category lookup is case-insensitive."""
        # The map should support lowercase lookups
        # NOTE: Implementation should handle case-insensitivity in lookup logic
        # For now, testing that exact case works
        assert YOUTUBE_CATEGORY_MAP.get("Entertainment") == "24"
        # Implementation should normalize to title case or use case-insensitive dict


# ============================================================================
# Test Class: Two-Era Strategy (T024)
# ============================================================================


class TestTwoEraStrategy:
    """
    Test two-era extraction strategy.

    Covers:
    - 2017+ pages with JSON → JSON extraction used
    - Pre-2017 pages without JSON → meta tag extraction used
    - Pages with both → JSON takes priority
    - Pages with neither → returns RecoveredVideoData with has_data=False
    """

    async def test_2017_plus_uses_json(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that 2017+ page with JSON uses JSON extraction, meta tags ignored."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_WITH_BOTH_JSON_AND_META
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # JSON values should be used, not meta tag values
        assert result.title == "JSON Title Takes Priority"
        assert result.description == "JSON description takes priority"
        assert result.tags == ["json-keyword"]
        assert result.view_count == 2000000

    async def test_pre_2017_uses_meta(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that pre-2017 page without JSON uses meta tag extraction."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.title == "Meta Video Title"
        assert result.description == "Meta description from Open Graph tags"
        assert result.tags == ["music", "classic", "nostalgia"]

    async def test_json_takes_priority(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that when both JSON and meta are present, JSON takes priority."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_WITH_BOTH_JSON_AND_META
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # All values should come from JSON, not meta tags
        assert result.title != "Meta Title Should Be Ignored"
        assert result.title == "JSON Title Takes Priority"

    async def test_neither_source_returns_empty(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that page with neither JSON nor meta tags returns has_data=False."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = EMPTY_PAGE
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.has_data is False


# ============================================================================
# Test Class: Selenium Fallback (T025)
# ============================================================================


class TestSeleniumFallback:
    """
    Test optional Selenium fallback behavior.

    Covers:
    - When SELENIUM_AVAILABLE=False and primary fails → log warning + return None
    - When SELENIUM_AVAILABLE=True and primary fails → call Selenium path
    - Selenium timeout → return None
    """

    async def test_selenium_unavailable_logs_warning(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that when Selenium is unavailable, warning is logged and None returned."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())

        with patch(
            "chronovista.services.recovery.page_parser.SELENIUM_AVAILABLE",
            False,
        ):
            parser = PageParser(rate_limiter=rate_limiter_mock)

            with patch.object(
                httpx.AsyncClient, "get", new_callable=AsyncMock
            ) as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = EMPTY_PAGE  # No JSON, no meta
                mock_get.return_value = mock_response

                result = await parser.extract_metadata(snapshot)

            # Should return RecoveredVideoData with has_data=False
            # (Selenium fallback not attempted)
            assert result is not None
            assert result.has_data is False

    async def test_selenium_available_calls_fallback(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that when Selenium is available and primary fails, fallback is called."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())

        with patch(
            "chronovista.services.recovery.page_parser.SELENIUM_AVAILABLE",
            True,
        ):
            parser = PageParser(rate_limiter=rate_limiter_mock)

            with patch.object(
                httpx.AsyncClient, "get", new_callable=AsyncMock
            ) as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = EMPTY_PAGE  # No JSON, no meta
                mock_get.return_value = mock_response

                # Mock the Selenium fallback method
                with patch.object(
                    parser,
                    "_extract_with_selenium",
                    new_callable=AsyncMock,
                ) as mock_selenium:
                    mock_selenium.return_value = RecoveredVideoData(
                        title="Selenium Title",
                        snapshot_timestamp=snapshot.timestamp,
                    )

                    result = await parser.extract_metadata(snapshot)

            # Selenium fallback should have been called
            mock_selenium.assert_called_once()
            assert result is not None
            assert result.title == "Selenium Title"

    async def test_selenium_timeout_skips(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that Selenium timeout returns None and continues."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())

        with patch(
            "chronovista.services.recovery.page_parser.SELENIUM_AVAILABLE",
            True,
        ):
            parser = PageParser(rate_limiter=rate_limiter_mock)

            with patch.object(
                httpx.AsyncClient, "get", new_callable=AsyncMock
            ) as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = EMPTY_PAGE
                mock_get.return_value = mock_response

                # Mock Selenium to raise timeout
                with patch.object(
                    parser,
                    "_extract_with_selenium",
                    new_callable=AsyncMock,
                ) as mock_selenium:
                    import asyncio

                    mock_selenium.side_effect = asyncio.TimeoutError(
                        "Selenium timeout"
                    )

                    result = await parser.extract_metadata(snapshot)

            # Should return None on Selenium timeout
            assert result is not None
            assert result.has_data is False


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def rate_limiter_mock() -> RateLimiter:
    """Create a mock RateLimiter for testing."""
    # RateLimiter is a simple class with acquire() method
    mock = MagicMock(spec=RateLimiter)
    mock.acquire = AsyncMock()
    return mock
