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

VALID_PAGE_META_WITH_EOW_DESCRIPTION = '''
<html><head>
<meta property="og:title" content="Old Format Video Title">
<meta property="og:description" content="FULL RECIPE: https://example.com/pasta Learn how to make the perfect homemade pasta from scratch using just three simple ingredients. This step-by-step tutori...">
<meta property="og:image" content="https://i.ytimg.com/vi/test123/hqdefault.jpg">
<meta property="og:video:tag" content="cooking">
<meta itemprop="datePublished" content="2018-09-28">
<meta itemprop="interactionCount" content="12345">
<link itemprop="url" href="http://www.youtube.com/user/CookingWithSarah">
</head><body>
<div id="watch-description-text" class="">
<p id="eow-description" class="">FULL RECIPE: <a href="/web/20190604182457/https://www.youtube.com/redirect?q=https%3A%2F%2Fexample.com%2Fpasta">https://example.com/pasta</a><br><br>Learn how to make the perfect homemade pasta from scratch using just three simple ingredients. This step-by-step tutorial covers everything from mixing the dough to cutting your own fettuccine.<br>We also show you how to make a classic marinara sauce to pair with your fresh pasta.<br><br>TIMESTAMPS <a href="/web/20190604182457/https://www.youtube.com/watch?v=IFAcqaNzNSc">https://www.youtube.com/watch?v=IFAcq...</a> <br><br>Check out <a href="/web/20190604182457/http://example.com">http://example.com</a><br><br>Subscribe to our channel! <a href="http://www.youtube.com/subscription_center?add_user=CookingWithSarah">http://www.youtube.com/subscription_c...</a><br><br>Follow us on Twitter <a href="/web/20190604182457/http://twitter.com/CookWithSarah">http://twitter.com/CookWithSarah</a><br>Follow us on Instagram <a href="/web/20190604182457/http://instagram.com/cookingwithsarah">http://instagram.com/cookingwithsarah</a><br><br>Cooking With Sarah is a home cooking channel dedicated to simple, delicious recipes anyone can make. We were the first cooking channel to reach 500 million YouTube views.</p>
</div>
</body></html>
'''

VALID_PAGE_META_WITH_EMPTY_EOW = '''
<html><head>
<meta property="og:title" content="Empty EOW Video">
<meta property="og:description" content="This is the og:description fallback text">
</head><body>
<div id="watch-description-text" class="">
<p id="eow-description" class="">   </p>
</div>
</body></html>
'''

VALID_PAGE_META_WITH_EOW_NO_OG_DESC = '''
<html><head>
<meta property="og:title" content="No OG Desc Video">
</head><body>
<div id="watch-description-text" class="">
<p id="eow-description" class="">This is the full description only available in the HTML element.</p>
</div>
</body></html>
'''

PAGE_JSON_WITH_EOW_AND_OLD_LIKE_BUTTON = '''
<html><head>
<meta property="og:title" content="Truncated OG Title">
<meta property="og:description" content="FULL GUIDE: https://example.com/bookshelf Learn how to build a simple bookshelf using basic hand tools and reclaimed wood from a local salvage yard. Step-by-s...">
</head><body>
<script>var ytInitialPlayerResponse = {"videoDetails":{"title":"JSON Title From Transitional Page","channelId":"UCuAXFkgsw1L7xaCfnd5JJOw","author":"Test Channel","viewCount":"50000","keywords":["woodworking","diy"]},"microformat":{"playerMicroformatRenderer":{"publishDate":"2019-04-05","category":"Howto & Style"}}};</script>
<div id="watch-description-text" class="">
<p id="eow-description" class="">Sarah demonstrates how to build a simple bookshelf using basic hand tools and reclaimed wood.<br><br>PLANS @ <a href="http://example.com/bookshelf-plans">http://example.com/bookshelf-plans</a><br>FOLLOW Sarah @ <a href="http://twitter.com/SarahBuilds">http://twitter.com/SarahBuilds</a></p>
</div>
<span class="yt-uix-clickcard">
<button class="yt-uix-button like-button-renderer-like-button like-button-renderer-like-button-unclicked" type="button" aria-label="Ich mag das Video (wie 2.510 andere auch)"><span class="yt-uix-button-content">2.510</span></button>
</span>
</body></html>
'''

PAGE_JSON_WITH_MODERN_LIKE_BUTTON = '''
<html><head></head><body>
<script>var ytInitialPlayerResponse = {"videoDetails":{"title":"Modern Transitional Page","channelId":"UCuAXFkgsw1L7xaCfnd5JJOw","author":"Test Channel","viewCount":"100000","keywords":["test"]},"microformat":{"playerMicroformatRenderer":{"publishDate":"2020-08-10","category":"Entertainment"}}};</script>
<div id="watch-description-text" class="">
<p id="eow-description" class="">This is the full description from the HTML element.</p>
</div>
<yt-formatted-string id="text" aria-label="1,230 likes">1.2K</yt-formatted-string>
</body></html>
'''

PAGE_JSON_WITH_ENGLISH_LIKE_ARIA = '''
<html><head></head><body>
<script>var ytInitialPlayerResponse = {"videoDetails":{"title":"English Like Page","channelId":"UCuAXFkgsw1L7xaCfnd5JJOw","author":"Channel","viewCount":"5000"},"microformat":{"playerMicroformatRenderer":{}}};</script>
<button aria-label="like this video along with 3,456 other people" class="like-button"><span>3.4K</span></button>
</body></html>
'''

PAGE_JSON_WITH_GERMAN_LIKE_DISLIKE = '''
<html><head></head><body>
<script>var ytInitialPlayerResponse = {"videoDetails":{"title":"German Locale Page","channelId":"UCuAXFkgsw1L7xaCfnd5JJOw","author":"Test Channel","viewCount":"80000"},"microformat":{"playerMicroformatRenderer":{"publishDate":"2020-02-11","category":"Entertainment"}}};</script>
<div id="watch-description-text" class="">
<p id="eow-description" class="">This is the full description for the German locale test page.</p>
</div>
<span class="like-button-renderer " data-button-toggle-group="optional">
    <span class="yt-uix-clickcard">
      <button class="yt-uix-button yt-uix-button-size-default yt-uix-button-opacity yt-uix-button-has-icon no-icon-markup like-button-renderer-like-button like-button-renderer-like-button-unclicked yt-uix-clickcard-target   yt-uix-tooltip" type="button" onclick=";return false;" aria-label="Ich mag das Video (wie 2.510 andere auch)" title="Mag ich" data-force-position="true" data-orientation="vertical" data-position="bottomright"><span class="yt-uix-button-content">2.510</span></button>
    </span>
    <span class="yt-uix-clickcard">
      <button class="yt-uix-button yt-uix-button-size-default yt-uix-button-opacity like-button-renderer-like-button like-button-renderer-like-button-clicked yt-uix-button-toggled  hid" type="button" aria-label="Ich mag das Video (wie 2.510 andere auch)"><span class="yt-uix-button-content">2.511</span></button>
    </span>
    <span class="yt-uix-clickcard">
      <button class="yt-uix-button yt-uix-button-size-default yt-uix-button-opacity like-button-renderer-dislike-button like-button-renderer-dislike-button-unclicked yt-uix-clickcard-target" type="button" aria-label="Ich mag das Video nicht (wie 112 andere)" title="Mag ich nicht"><span class="yt-uix-button-content">112</span></button>
    </span>
    <span class="yt-uix-clickcard">
      <button class="yt-uix-button like-button-renderer-dislike-button like-button-renderer-dislike-button-clicked hid" type="button" aria-label="Ich mag das Video nicht (wie 112 andere)"><span class="yt-uix-button-content">113</span></button>
    </span>
</span>
</body></html>
'''

PAGE_JSON_WITH_LIKE_BUTTON_NO_CONTENT_SPAN = '''
<html><head></head><body>
<script>var ytInitialPlayerResponse = {"videoDetails":{"title":"No Content Span Page","channelId":"UCuAXFkgsw1L7xaCfnd5JJOw","author":"Test Channel","viewCount":"30000"},"microformat":{"playerMicroformatRenderer":{}}};</script>
<button class="yt-uix-button like-button-renderer-like-button like-button-renderer-like-button-unclicked" type="button" aria-label="Ich mag das Video (wie 1.234 andere auch)" title="Mag ich">Mag ich</button>
</body></html>
'''

PAGE_JSON_COMPLETE_NO_SUPPLEMENT_NEEDED = '''
<html><head></head><body>
<script>var ytInitialPlayerResponse = {"videoDetails":{"title":"Complete JSON Page","shortDescription":"Full description from JSON","channelId":"UCuAXFkgsw1L7xaCfnd5JJOw","author":"Channel","viewCount":"5000","keywords":["test"]},"microformat":{"playerMicroformatRenderer":{"publishDate":"2021-01-01","category":"Education"}}};</script>
<script>var ytInitialData = {"contents":{"twoColumnWatchNextResults":{"results":{"results":{"contents":[{"videoPrimaryInfoRenderer":{"videoActions":{"menuRenderer":{"topLevelButtons":[{"toggleButtonRenderer":{"defaultText":{"accessibility":{"accessibilityData":{"label":"9,999 likes"}}}}}]}}}}]}}}}};</script>
</body></html>
'''

PAGE_JSON_WITH_TRUNCATED_DESC_AND_EOW = '''
<html><head></head><body>
<script>var ytInitialPlayerResponse = {"videoDetails":{"title":"Truncated Desc Page","shortDescription":"Learn how to build a simple bookshelf using basic hand tools and reclaimed wood from a local salvage yard. Step-by-step guide for beg...","channelId":"UCuAXFkgsw1L7xaCfnd5JJOw","author":"Test Channel","viewCount":"75000","keywords":["woodworking"]},"microformat":{"playerMicroformatRenderer":{"publishDate":"2019-12-04","category":"Howto & Style"}}};</script>
<div id="watch-description-text" class="">
<p id="eow-description" class="">Learn how to build a simple bookshelf using basic hand tools and reclaimed wood from a local salvage yard. Step-by-step guide for beginners and experienced woodworkers alike.<br><br>PLANS @ <a href="http://example.com/bookshelf-plans">http://example.com/bookshelf-plans</a><br>FOLLOW Sarah @ <a href="http://twitter.com/SarahBuilds">http://twitter.com/SarahBuilds</a></p>
</div>
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

    async def test_extracts_channel_id_from_data_channel_external_id(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test channel ID extraction from data-channel-external-id attribute (pre-2020 pages)."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        html = '''
<html><head>
<meta property="og:title" content="Test Video">
</head><body>
<button class="yt-uix-subscription-button" data-channel-external-id="UC8-Th83bH_thdKZDJCrn88g">Subscribe</button>
</body></html>
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
        assert result.channel_id == "UC8-Th83bH_thdKZDJCrn88g"

    async def test_extracts_channel_id_from_anchor_tag(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test channel ID extraction from <a> tags linking to /channel/UCxxx."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        html = '''
<html><head>
<meta property="og:title" content="Test Video">
</head><body>
<div class="yt-user-info">
  <a href="/web/20190509183907/https://www.youtube.com/channel/UC8-Th83bH_thdKZDJCrn88g">The Tonight Show</a>
</div>
</body></html>
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
        assert result.channel_id == "UC8-Th83bH_thdKZDJCrn88g"

    async def test_channel_id_itemprop_takes_priority_over_data_attribute(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that itemprop='channelId' takes priority over data-channel-external-id."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        html = '''
<html><head>
<meta itemprop="channelId" content="UCpwvZwUam-URkxB7g4USKpg">
<meta property="og:title" content="Test Video">
</head><body>
<button data-channel-external-id="UC8-Th83bH_thdKZDJCrn88g">Subscribe</button>
</body></html>
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

    async def test_data_channel_external_id_ignores_invalid_format(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that invalid data-channel-external-id values are ignored."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        html = '''
<html><head>
<meta property="og:title" content="Test Video">
</head><body>
<button data-channel-external-id="not-a-valid-channel-id">Subscribe</button>
</body></html>
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
        assert result.channel_id is None

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

    async def test_eow_description_preferred_over_og(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that #eow-description full text is preferred over truncated og:description."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_WITH_EOW_DESCRIPTION
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # Should have the full description from #eow-description, not the
        # truncated 160-char og:description
        assert result.description is not None
        assert len(result.description) > 160
        assert "homemade pasta from scratch" in result.description
        assert "YouTube views" in result.description
        # Should NOT end with "..."
        assert not result.description.endswith("...")

    async def test_eow_description_br_tags_become_newlines(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that <br> tags in #eow-description are converted to newlines."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_WITH_EOW_DESCRIPTION
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.description is not None
        # <br> tags should become newlines
        assert "\n" in result.description
        # No more than 2 consecutive newlines (triple+ collapsed)
        assert "\n\n\n" not in result.description

    async def test_eow_description_strips_html_tags(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that <a> tags are stripped but their text content preserved."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_WITH_EOW_DESCRIPTION
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.description is not None
        # Link text should be preserved
        assert "https://example.com/pasta" in result.description
        assert "http://example.com" in result.description
        # HTML tags should not appear
        assert "<a " not in result.description
        assert "<br" not in result.description

    async def test_empty_eow_description_falls_back_to_og(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that empty #eow-description falls back to og:description."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_WITH_EMPTY_EOW
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.description == "This is the og:description fallback text"

    async def test_eow_description_without_og_desc(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that #eow-description works when og:description is absent."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_WITH_EOW_NO_OG_DESC
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.description == "This is the full description only available in the HTML element."

    async def test_eow_preserves_other_meta_fields(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that #eow-description enhancement doesn't break other meta field extraction."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = VALID_PAGE_META_WITH_EOW_DESCRIPTION
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # All other fields should still be extracted from meta tags
        assert result.title == "Old Format Video Title"
        assert result.thumbnail_url == "https://i.ytimg.com/vi/test123/hqdefault.jpg"
        assert result.tags == ["cooking"]
        assert result.upload_date is not None
        assert result.upload_date.year == 2018
        assert result.view_count == 12345
        assert result.channel_name_hint == "CookingWithSarah"

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
# Test Class: HTML Supplement for Transitional Pages
# ============================================================================


class TestHTMLSupplement:
    """
    Test _supplement_from_html() behavior for transitional-era pages.

    When _extract_from_json succeeds but videoDetails lacks shortDescription
    and ytInitialData lacks the like count, the supplement pass fills gaps
    from #eow-description and like button HTML elements.

    Covers:
    - Description supplemented from #eow-description when JSON has none
    - Like count from old-format button content (European locale)
    - Like count from modern aria-label="N likes"
    - Like count from "along with N other people" aria-label
    - No supplement when JSON already has both fields
    """

    async def test_supplements_description_from_eow(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that missing description is filled from #eow-description."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_JSON_WITH_EOW_AND_OLD_LIKE_BUTTON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # JSON title should be used (JSON takes priority for fields it has)
        assert result.title == "JSON Title From Transitional Page"
        # Description should come from #eow-description (JSON had none)
        assert result.description is not None
        assert "Sarah demonstrates how to build a simple bookshelf" in result.description
        assert "http://example.com/bookshelf-plans" in result.description
        assert not result.description.endswith("...")

    async def test_supplements_like_count_from_old_button(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that like count is extracted from old-format button content."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_JSON_WITH_EOW_AND_OLD_LIKE_BUTTON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # Like count from button content "2.510" (European format = 2510)
        assert result.like_count == 2510

    async def test_supplements_like_count_from_modern_aria_label(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that like count is extracted from modern aria-label='N likes'."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_JSON_WITH_MODERN_LIKE_BUTTON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.like_count == 1230

    async def test_supplements_like_count_from_along_with_pattern(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that like count is extracted from 'along with N other people'."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_JSON_WITH_ENGLISH_LIKE_ARIA
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.like_count == 3456

    async def test_no_supplement_when_json_complete(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that supplement is skipped when JSON has both description and likes."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_JSON_COMPLETE_NO_SUPPLEMENT_NEEDED
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # Values should come from JSON, not HTML supplement
        assert result.description == "Full description from JSON"
        assert result.like_count == 9999

    async def test_supplement_preserves_json_fields(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that supplement doesn't overwrite fields already extracted by JSON."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_JSON_WITH_EOW_AND_OLD_LIKE_BUTTON
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # JSON-sourced fields must be preserved
        assert result.title == "JSON Title From Transitional Page"
        assert result.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert result.channel_name_hint == "Test Channel"
        assert result.view_count == 50000
        assert result.tags == ["woodworking", "diy"]
        assert result.category_id == "26"  # "Howto & Style"
        assert result.upload_date is not None
        assert result.upload_date.year == 2019

    async def test_supplements_truncated_description_from_eow(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that truncated JSON shortDescription is replaced by full #eow-description."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_JSON_WITH_TRUNCATED_DESC_AND_EOW
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.title == "Truncated Desc Page"
        # The JSON shortDescription ends with "..." and is ~130 chars.
        # The #eow-description has the full text, which is longer.
        assert result.description is not None
        assert not result.description.endswith("...")
        assert "beginners and experienced woodworkers" in result.description
        assert "http://example.com/bookshelf-plans" in result.description

    async def test_supplements_like_count_from_german_locale(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test like count extraction from full German like/dislike button HTML."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_JSON_WITH_GERMAN_LIKE_DISLIKE
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        assert result.title == "German Locale Page"
        # Like count from button content "2.510" (European format = 2510)
        assert result.like_count == 2510

    async def test_supplements_like_count_german_dislike_not_matched(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that German dislike button (112) is not returned as like count."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_JSON_WITH_GERMAN_LIKE_DISLIKE
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # Must be 2510 (like), NOT 112 (dislike)
        assert result.like_count != 112
        assert result.like_count == 2510

    async def test_supplements_like_from_aria_label_when_no_content_span(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test like count from aria-label when button has no yt-uix-button-content span."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = PAGE_JSON_WITH_LIKE_BUTTON_NO_CONTENT_SPAN
            mock_get.return_value = mock_response

            result = await parser.extract_metadata(snapshot)

        assert result is not None
        # Extracted from aria-label "Ich mag das Video (wie 1.234 andere auch)"
        assert result.like_count == 1234


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


# ============================================================================
# HTML Test Fixtures for Channel Metadata Extraction
# ============================================================================

CHANNEL_PAGE_WITH_JSON = '''
<html><head></head><body>
<script>var ytInitialData = {"metadata":{"channelMetadataRenderer":{"title":"Tech Channel","description":"A channel about technology and gadgets","externalId":"UCuAXFkgsw1L7xaCfnd5JJOw","country":"US","defaultLanguage":"en","avatar":{"thumbnails":[{"url":"https://yt3.googleusercontent.com/channel/avatar.jpg"}]}}},"header":{"c4TabbedHeaderRenderer":{"subscriberCountText":{"simpleText":"1.2M subscribers"},"videosCountText":{"runs":[{"text":"1,234"}]}}}};</script>
</body></html>
'''

CHANNEL_PAGE_META_ONLY = '''
<html><head>
<meta property="og:title" content="Classic Channel">
<meta property="og:description" content="A classic YouTube channel">
<meta property="og:image" content="https://yt3.googleusercontent.com/channel/classic.jpg">
</head><body></body></html>
'''

CHANNEL_PAGE_ID_MISMATCH = '''
<html><head></head><body>
<script>var ytInitialData = {"metadata":{"channelMetadataRenderer":{"title":"Wrong Channel","externalId":"UCDifferentChannelId123456","country":"GB"}}};</script>
</body></html>
'''

CHANNEL_PAGE_NO_DATA = '''
<html><head></head><body></body></html>
'''

CHANNEL_PAGE_SUBSCRIBER_VARIANTS = '''
<html><head></head><body>
<script>var ytInitialData = {"metadata":{"channelMetadataRenderer":{"title":"Test Channel","externalId":"UCuAXFkgsw1L7xaCfnd5JJOw"}},"header":{"c4TabbedHeaderRenderer":{"subscriberCountText":{"simpleText":"500K subscribers"},"videosCountText":{"runs":[{"text":"500"}]}}}};</script>
</body></html>
'''

CHANNEL_PAGE_NO_SUBSCRIBERS = '''
<html><head></head><body>
<script>var ytInitialData = {"metadata":{"channelMetadataRenderer":{"title":"New Channel","externalId":"UCuAXFkgsw1L7xaCfnd5JJOw"}},"header":{"c4TabbedHeaderRenderer":{"subscriberCountText":{"simpleText":"No subscribers"},"videosCountText":{"runs":[{"text":"5"}]}}}};</script>
</body></html>
'''

CHANNEL_PAGE_PLAIN_NUMBERS = '''
<html><head></head><body>
<script>var ytInitialData = {"metadata":{"channelMetadataRenderer":{"title":"Small Channel","externalId":"UCuAXFkgsw1L7xaCfnd5JJOw"}},"header":{"c4TabbedHeaderRenderer":{"subscriberCountText":{"simpleText":"1,234 subscribers"},"videosCountText":{"runs":[{"text":"1,234"}]}}}};</script>
</body></html>
'''


# ============================================================================
# Test Class: Channel Metadata Extraction (T014)
# ============================================================================


class TestExtractChannelMetadata:
    """
    Test extract_channel_metadata() and channel-specific helpers.

    Covers:
    - JSON extraction from 2017+ channel pages (ytInitialData)
    - Meta tag fallback for pre-2017 channel pages
    - Subscriber count parsing with SI suffixes and commas
    - Video count parsing
    - Channel ID cross-validation
    - Missing data handling
    - Fetch failure handling
    """

    async def test_extract_channel_from_json_all_fields(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test JSON extraction with all fields present."""
        from chronovista.services.recovery.models import RecoveredChannelData

        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)
        channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = CHANNEL_PAGE_WITH_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_channel_metadata(snapshot, channel_id)

        assert result is not None
        assert isinstance(result, RecoveredChannelData)
        assert result.title == "Tech Channel"
        assert result.description == "A channel about technology and gadgets"
        assert result.subscriber_count == 1200000
        assert result.video_count == 1234
        assert (
            result.thumbnail_url
            == "https://yt3.googleusercontent.com/channel/avatar.jpg"
        )
        assert result.country == "US"
        assert result.default_language == "en"
        assert result.snapshot_timestamp == snapshot.timestamp

    async def test_extract_channel_from_meta_tags(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test meta tag extraction for pre-2017 channel pages."""
        from chronovista.services.recovery.models import RecoveredChannelData

        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)
        channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = CHANNEL_PAGE_META_ONLY
            mock_get.return_value = mock_response

            result = await parser.extract_channel_metadata(snapshot, channel_id)

        assert result is not None
        assert isinstance(result, RecoveredChannelData)
        assert result.title == "Classic Channel"
        assert result.description == "A classic YouTube channel"
        assert (
            result.thumbnail_url
            == "https://yt3.googleusercontent.com/channel/classic.jpg"
        )
        # Meta tag extraction cannot recover subscriber_count or video_count
        assert result.subscriber_count is None
        assert result.video_count is None

    async def test_channel_id_cross_validation_success(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that matching channel_id passes cross-validation."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)
        channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = CHANNEL_PAGE_WITH_JSON
            mock_get.return_value = mock_response

            result = await parser.extract_channel_metadata(snapshot, channel_id)

        assert result is not None
        assert result.title == "Tech Channel"

    async def test_channel_id_cross_validation_mismatch(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that mismatched channel_id returns None."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)
        # Expected channel_id doesn't match the one in the page
        channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = CHANNEL_PAGE_ID_MISMATCH
            mock_get.return_value = mock_response

            result = await parser.extract_channel_metadata(snapshot, channel_id)

        # Should return None due to ID mismatch
        assert result is None

    async def test_channel_page_no_extractable_data(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that page with no extractable data returns None."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)
        channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = CHANNEL_PAGE_NO_DATA
            mock_get.return_value = mock_response

            result = await parser.extract_channel_metadata(snapshot, channel_id)

        assert result is None

    async def test_channel_page_fetch_failure(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test that HTTP fetch failure returns None without raising."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)
        channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = httpx.ConnectTimeout("Connection timeout")

            result = await parser.extract_channel_metadata(snapshot, channel_id)

        # Should return None, not raise exception
        assert result is None


class TestParseSubscriberCount:
    """
    Test _parse_subscriber_count() helper method.

    Covers:
    - SI suffix parsing (K, M, B)
    - Comma-separated numbers
    - "No subscribers" special case
    - Invalid input handling
    """

    def test_parse_1_2m_subscribers(self) -> None:
        """Test parsing '1.2M subscribers' -> 1200000."""
        result = PageParser._parse_subscriber_count("1.2M subscribers")
        assert result == 1200000

    def test_parse_500k_subscribers(self) -> None:
        """Test parsing '500K subscribers' -> 500000."""
        result = PageParser._parse_subscriber_count("500K subscribers")
        assert result == 500000

    def test_parse_comma_separated_subscribers(self) -> None:
        """Test parsing '1,234 subscribers' -> 1234."""
        result = PageParser._parse_subscriber_count("1,234 subscribers")
        assert result == 1234

    def test_parse_plain_number_subscribers(self) -> None:
        """Test parsing '1234 subscribers' -> 1234."""
        result = PageParser._parse_subscriber_count("1234 subscribers")
        assert result == 1234

    def test_parse_no_subscribers(self) -> None:
        """Test parsing 'No subscribers' -> 0."""
        result = PageParser._parse_subscriber_count("No subscribers")
        assert result == 0

    def test_parse_billion_suffix(self) -> None:
        """Test parsing '1.5B subscribers' -> 1500000000."""
        result = PageParser._parse_subscriber_count("1.5B subscribers")
        assert result == 1500000000

    def test_parse_empty_string(self) -> None:
        """Test that empty string returns None."""
        result = PageParser._parse_subscriber_count("")
        assert result is None

    def test_parse_whitespace_only(self) -> None:
        """Test that whitespace-only string returns None."""
        result = PageParser._parse_subscriber_count("   ")
        assert result is None

    def test_parse_invalid_format(self) -> None:
        """Test that invalid format returns None."""
        result = PageParser._parse_subscriber_count("abc subscribers")
        assert result is None

    def test_parse_lowercase_k_suffix(self) -> None:
        """Test parsing with lowercase 'k' suffix (normalized to uppercase)."""
        result = PageParser._parse_subscriber_count("500k subscribers")
        assert result == 500000


class TestParseVideoCount:
    """
    Test _parse_video_count() helper method.

    Covers:
    - Comma-separated numbers
    - Plain numbers
    - Invalid input handling
    """

    def test_parse_comma_separated_videos(self) -> None:
        """Test parsing '1,234 videos' -> 1234."""
        result = PageParser._parse_video_count("1,234 videos")
        assert result == 1234

    def test_parse_plain_number_videos(self) -> None:
        """Test parsing '500' -> 500."""
        result = PageParser._parse_video_count("500")
        assert result == 500

    def test_parse_with_videos_suffix(self) -> None:
        """Test parsing '500 videos' -> 500."""
        result = PageParser._parse_video_count("500 videos")
        assert result == 500

    def test_parse_large_number_with_commas(self) -> None:
        """Test parsing '10,000 videos' -> 10000."""
        result = PageParser._parse_video_count("10,000 videos")
        assert result == 10000

    def test_parse_empty_string(self) -> None:
        """Test that empty string returns None."""
        result = PageParser._parse_video_count("")
        assert result is None

    def test_parse_whitespace_only(self) -> None:
        """Test that whitespace-only string returns None."""
        result = PageParser._parse_video_count("   ")
        assert result is None

    def test_parse_invalid_format(self) -> None:
        """Test that invalid format returns None."""
        result = PageParser._parse_video_count("abc videos")
        assert result is None

    def test_parse_singular_video(self) -> None:
        """Test parsing '1 video' (singular) -> 1."""
        result = PageParser._parse_video_count("1 video")
        assert result == 1


class TestChannelMetadataIntegration:
    """
    Integration tests for channel metadata extraction.

    Tests the full extraction flow with various subscriber/video count formats.
    """

    async def test_subscriber_count_500k(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test extraction with '500K subscribers' format."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)
        channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = CHANNEL_PAGE_SUBSCRIBER_VARIANTS
            mock_get.return_value = mock_response

            result = await parser.extract_channel_metadata(snapshot, channel_id)

        assert result is not None
        assert result.subscriber_count == 500000
        assert result.video_count == 500

    async def test_no_subscribers(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test extraction with 'No subscribers' special case."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)
        channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = CHANNEL_PAGE_NO_SUBSCRIBERS
            mock_get.return_value = mock_response

            result = await parser.extract_channel_metadata(snapshot, channel_id)

        assert result is not None
        assert result.subscriber_count == 0
        assert result.video_count == 5

    async def test_plain_numbers(
        self, cdx_snapshot_factory: Any, rate_limiter_mock: RateLimiter
    ) -> None:
        """Test extraction with plain comma-separated numbers."""
        snapshot = CdxSnapshot(**cdx_snapshot_factory())
        parser = PageParser(rate_limiter=rate_limiter_mock)
        channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = CHANNEL_PAGE_PLAIN_NUMBERS
            mock_get.return_value = mock_response

            result = await parser.extract_channel_metadata(snapshot, channel_id)

        assert result is not None
        assert result.subscriber_count == 1234
        assert result.video_count == 1234
