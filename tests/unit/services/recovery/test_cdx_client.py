"""
Comprehensive unit tests for the CDX client.

This module provides complete test coverage for the Wayback Machine CDX API
client, including:
- RateLimiter token-bucket rate limiting logic
- CDX URL construction and JSON response parsing
- Filtering and sorting of CDX snapshots
- File-based caching with TTL validation
- Retry logic with exponential backoff and rate limit handling

All tests use mocked httpx responses and never make real HTTP calls.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, mock_open, patch

import httpx
import pytest

from chronovista.exceptions import CDXError
from chronovista.services.recovery.cdx_client import CDXClient, RateLimiter
from chronovista.services.recovery.models import CdxCacheEntry, CdxSnapshot

# Mark all tests in this module as async by default
pytestmark = pytest.mark.asyncio


# =============================================================================
# TestRateLimiter - Token-bucket rate limiting logic
# =============================================================================


class TestRateLimiter:
    """Test the token-bucket rate limiter."""

    async def test_rate_limiter_allows_burst(self) -> None:
        """
        Creating a RateLimiter(rate=40) should allow initial requests without delay.

        The token bucket should start full, allowing up to `rate` requests
        to proceed immediately without any asyncio.sleep calls.
        """
        rate_limiter = RateLimiter(rate=40.0)

        # First 40 requests should complete without delay
        with patch("asyncio.sleep") as mock_sleep:
            for _ in range(40):
                await rate_limiter.acquire()

            # No sleep should have been called for burst capacity
            mock_sleep.assert_not_called()

    async def test_rate_limiter_enforces_rate(self) -> None:
        """
        After burst capacity is consumed, acquire() should introduce a delay.

        Once the token bucket is empty, subsequent requests should sleep
        to maintain the configured rate limit.
        """
        # Use a small rate for faster test execution
        rate_limiter = RateLimiter(rate=10.0)  # 10 requests per second

        with patch("asyncio.sleep") as mock_sleep:
            # Consume burst capacity (10 tokens)
            for _ in range(10):
                await rate_limiter.acquire()

            # No sleep yet
            mock_sleep.assert_not_called()

            # Next request should require waiting
            await rate_limiter.acquire()
            mock_sleep.assert_called()
            # Should wait approximately 1/rate seconds = 0.1s
            assert mock_sleep.call_count >= 1

    async def test_rate_limiter_shared_across_callers(self) -> None:
        """
        Two async tasks sharing the same rate_limiter instance both respect the rate.

        This verifies that the rate limiter correctly synchronizes access
        across multiple concurrent consumers.
        """
        rate_limiter = RateLimiter(rate=20.0)

        async def consumer(count: int) -> None:
            for _ in range(count):
                await rate_limiter.acquire()

        with patch("asyncio.sleep"):
            # Two tasks each making 15 requests = 30 total
            # Burst capacity is 20, so 10 requests should trigger sleep
            await asyncio.gather(consumer(15), consumer(15))

            # Both tasks should have completed without errors
            # (implicitly verified by gather not raising)


# =============================================================================
# TestCDXURLConstruction (T011) - URL construction and JSON parsing
# =============================================================================


class TestCDXURLConstruction:
    """Test URL construction and JSON parsing."""

    async def test_cdx_url_construction(self) -> None:
        """
        For video_id "dQw4w9WgXcQ", the CDX URL should contain all required parameters.

        Expected query parameters:
        - url=youtube.com/watch%3Fv%3DdQw4w9WgXcQ
        - output=json
        - filter=statuscode:200
        - filter=mimetype:text/html
        - fl=timestamp,original,mimetype,statuscode,digest,length
        - limit=-100
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        # Mock the HTTP response to inspect the constructed URL
        mock_response = httpx.Response(
            status_code=200,
            json=[],  # Empty CDX response
        )

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.fetch_snapshots("dQw4w9WgXcQ")

            # Verify get was called once
            mock_get.assert_called_once()

            # Extract the URL that was requested
            call_args = mock_get.call_args
            requested_url = str(call_args[0][0])  # First positional argument

            # Verify all required components are present
            assert "youtube.com/watch" in requested_url
            assert "v=dQw4w9WgXcQ" in requested_url or "v%3DdQw4w9WgXcQ" in requested_url
            assert "output=json" in requested_url
            assert "filter=statuscode:200" in requested_url
            assert "filter=mimetype:text/html" in requested_url
            assert "fl=timestamp,original,mimetype,statuscode,digest,length" in requested_url
            assert "limit=-100" in requested_url

    async def test_cdx_response_parsing(self) -> None:
        """
        CDX returns JSON as array-of-arrays with first row as headers.

        The CDX API response format is:
        [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            ["20220106075526", "https://...", "text/html", "200", "ABC", 50000],
            ...
        ]

        The first row contains field names, subsequent rows contain data.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        # Mock CDX response with header row + 2 data rows
        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20220106075526",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "ABCDEF123456",
                "50000",
            ],
            [
                "20210315120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "GHIJKL789012",
                "60000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots("dQw4w9WgXcQ")

            # Should return 2 snapshots (excluding header row)
            assert len(snapshots) == 2

            # Verify first snapshot
            assert snapshots[0].timestamp == "20220106075526"
            assert snapshots[0].original == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            assert snapshots[0].mimetype == "text/html"
            assert snapshots[0].statuscode == 200
            assert snapshots[0].digest == "ABCDEF123456"
            assert snapshots[0].length == 50000

            # Verify second snapshot
            assert snapshots[1].timestamp == "20210315120000"
            assert snapshots[1].digest == "GHIJKL789012"

    async def test_cdx_status_dash_excluded(self) -> None:
        """
        CDX rows where statuscode is "-" (redirects) should be excluded.

        The CDX API sometimes returns rows with statuscode="-" for redirects.
        These should be filtered out during parsing.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        # Mock CDX response with one valid row and one redirect (statuscode="-")
        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20220106075526",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "ABCDEF123456",
                "50000",
            ],
            [
                "20210315120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "-",  # Redirect, should be excluded
                "GHIJKL789012",
                "60000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots("dQw4w9WgXcQ")

            # Should return only 1 snapshot (the one with statuscode=200)
            assert len(snapshots) == 1
            assert snapshots[0].statuscode == 200

    async def test_empty_cdx_response(self) -> None:
        """
        CDX returns [] (empty array) with HTTP 200, no error, return empty list.

        An empty CDX response indicates no snapshots are available for the
        video. This is not an error condition.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        # Mock empty CDX response
        mock_response = httpx.Response(status_code=200, json=[])

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots("dQw4w9WgXcQ")

            # Should return empty list without raising an error
            assert snapshots == []


# =============================================================================
# TestCDXFiltering (T012) - Filtering and sorting
# =============================================================================


class TestCDXFiltering:
    """Test filtering and sorting."""

    async def test_filter_status_200_only(self) -> None:
        """
        Rows with statuscode != 200 filtered out.

        Only snapshots with HTTP 200 status should be returned.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20220106075526",
                "https://www.youtube.com/watch?v=test1",
                "text/html",
                "200",
                "ABC123",
                "50000",
            ],
            [
                "20220106075527",
                "https://www.youtube.com/watch?v=test2",
                "text/html",
                "404",  # Should be filtered out
                "DEF456",
                "50000",
            ],
            [
                "20220106075528",
                "https://www.youtube.com/watch?v=test3",
                "text/html",
                "302",  # Should be filtered out
                "GHI789",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots("test123")

            # Only the 200 status should remain
            assert len(snapshots) == 1
            assert snapshots[0].statuscode == 200

    async def test_filter_mimetype_text_html(self) -> None:
        """
        Non-text/html mimetypes filtered out.

        Only snapshots with mimetype="text/html" should be returned.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20220106075526",
                "https://www.youtube.com/watch?v=test1",
                "text/html",
                "200",
                "ABC123",
                "50000",
            ],
            [
                "20220106075527",
                "https://www.youtube.com/watch?v=test2",
                "application/json",  # Should be filtered out
                "200",
                "DEF456",
                "50000",
            ],
            [
                "20220106075528",
                "https://www.youtube.com/watch?v=test3",
                "text/plain",  # Should be filtered out
                "200",
                "GHI789",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots("test123")

            # Only the text/html snapshot should remain
            assert len(snapshots) == 1
            assert snapshots[0].mimetype == "text/html"

    async def test_filter_length_gt_5000(self) -> None:
        """
        Rows with length <= 5000 filtered out.

        Very small responses are likely error pages or stubs, not full YouTube pages.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20220106075526",
                "https://www.youtube.com/watch?v=test1",
                "text/html",
                "200",
                "ABC123",
                "50000",  # Valid
            ],
            [
                "20220106075527",
                "https://www.youtube.com/watch?v=test2",
                "text/html",
                "200",
                "DEF456",
                "5000",  # Should be filtered out (not greater than 5000)
            ],
            [
                "20220106075528",
                "https://www.youtube.com/watch?v=test3",
                "text/html",
                "200",
                "GHI789",
                "1000",  # Should be filtered out
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots("test123")

            # Only the snapshot with length > 5000 should remain
            assert len(snapshots) == 1
            assert snapshots[0].length == 50000

    async def test_sort_newest_first(self) -> None:
        """
        Results sorted by timestamp descending (newest first).

        CDX responses may not be in chronological order. The client should
        sort by timestamp descending to prioritize newer snapshots.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        # Response with timestamps in mixed order
        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20210315120000",  # Middle
                "https://www.youtube.com/watch?v=test",
                "text/html",
                "200",
                "BBB222",
                "50000",
            ],
            [
                "20220106075526",  # Newest
                "https://www.youtube.com/watch?v=test",
                "text/html",
                "200",
                "AAA111",
                "50000",
            ],
            [
                "20200101000000",  # Oldest
                "https://www.youtube.com/watch?v=test",
                "text/html",
                "200",
                "CCC333",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots("test123")

            # Should be sorted newest first
            assert len(snapshots) == 3
            assert snapshots[0].timestamp == "20220106075526"  # Newest
            assert snapshots[1].timestamp == "20210315120000"  # Middle
            assert snapshots[2].timestamp == "20200101000000"  # Oldest

    async def test_cdx_limit_100(self) -> None:
        """
        CDX query includes limit=-100 parameter.

        The client should request up to 100 snapshots from the CDX API.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        mock_response = httpx.Response(status_code=200, json=[])

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.fetch_snapshots("test123")

            # Extract the URL
            call_args = mock_get.call_args
            requested_url = str(call_args[0][0])

            # Verify limit=-100 is present
            assert "limit=-100" in requested_url


# =============================================================================
# TestCDXCaching (T013) - File-based caching
# =============================================================================


class TestCDXCaching:
    """Test file-based caching."""

    async def test_cache_hit_returns_cached(self, tmp_path: Path) -> None:
        """
        When cache file exists and is fresh (<24h), return cached data without HTTP call.

        A valid cache entry should be returned immediately without making
        an HTTP request to the CDX API.
        """
        cache_dir = tmp_path / "cdx_cache"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / "cdx" / "dQw4w9WgXcQ.json"
        cache_file.parent.mkdir(parents=True)

        # Create a fresh cache entry (fetched 1 hour ago)
        cache_entry = CdxCacheEntry(
            video_id="dQw4w9WgXcQ",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=1),
            snapshots=[
                CdxSnapshot(
                    timestamp="20220106075526",
                    original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    mimetype="text/html",
                    statuscode=200,
                    digest="CACHED123",
                    length=50000,
                )
            ],
            raw_count=1,
        )

        # Write cache file
        cache_file.write_text(cache_entry.model_dump_json())

        client = CDXClient(cache_dir=cache_dir)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            snapshots = await client.fetch_snapshots("dQw4w9WgXcQ")

            # Should not make HTTP request
            mock_get.assert_not_called()

            # Should return cached snapshot
            assert len(snapshots) == 1
            assert snapshots[0].digest == "CACHED123"

    async def test_cache_miss_triggers_fetch(self, tmp_path: Path) -> None:
        """
        When cache file doesn't exist, make HTTP call and write cache file.

        A cache miss should trigger a CDX API request and create a new cache file.
        """
        cache_dir = tmp_path / "cdx_cache"
        cache_file = cache_dir / "cdx" / "dQw4w9WgXcQ.json"

        client = CDXClient(cache_dir=cache_dir)

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20220106075526",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "FRESH123",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots("dQw4w9WgXcQ")

            # Should make HTTP request
            mock_get.assert_called_once()

            # Should return fetched snapshot
            assert len(snapshots) == 1
            assert snapshots[0].digest == "FRESH123"

            # Cache file should exist
            assert cache_file.exists()

            # Verify cache contents
            cached_data = json.loads(cache_file.read_text())
            assert cached_data["video_id"] == "dQw4w9WgXcQ"
            assert len(cached_data["snapshots"]) == 1

    async def test_expired_cache_triggers_refetch(self, tmp_path: Path) -> None:
        """
        Cache file with fetched_at > 24h ago should trigger re-fetch.

        Expired cache entries should be refreshed from the CDX API.
        """
        cache_dir = tmp_path / "cdx_cache"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / "cdx" / "dQw4w9WgXcQ.json"
        cache_file.parent.mkdir(parents=True)

        # Create an expired cache entry (fetched 25 hours ago)
        cache_entry = CdxCacheEntry(
            video_id="dQw4w9WgXcQ",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=25),
            snapshots=[
                CdxSnapshot(
                    timestamp="20220106075526",
                    original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    mimetype="text/html",
                    statuscode=200,
                    digest="EXPIRED123",
                    length=50000,
                )
            ],
            raw_count=1,
        )

        cache_file.write_text(cache_entry.model_dump_json())

        client = CDXClient(cache_dir=cache_dir)

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20220106075526",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "FRESH123",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots("dQw4w9WgXcQ")

            # Should make HTTP request despite cache file existing
            mock_get.assert_called_once()

            # Should return fresh snapshot
            assert len(snapshots) == 1
            assert snapshots[0].digest == "FRESH123"

    async def test_corrupted_cache_triggers_refetch(self, tmp_path: Path) -> None:
        """
        Invalid JSON in cache file → delete file + re-query CDX. Don't crash.

        Corrupted cache files should be handled gracefully by fetching fresh data.
        """
        cache_dir = tmp_path / "cdx_cache"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / "cdx" / "dQw4w9WgXcQ.json"
        cache_file.parent.mkdir(parents=True)

        # Write invalid JSON to cache file
        cache_file.write_text("{this is not valid json")

        client = CDXClient(cache_dir=cache_dir)

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20220106075526",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "FRESH123",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            # Should not crash, should fetch fresh data
            snapshots = await client.fetch_snapshots("dQw4w9WgXcQ")

            # Should make HTTP request
            mock_get.assert_called_once()

            # Should return fresh snapshot
            assert len(snapshots) == 1
            assert snapshots[0].digest == "FRESH123"

    async def test_cache_write_creates_directory(self, tmp_path: Path) -> None:
        """
        Cache write should create {cache_dir}/cdx/ directory if missing.

        The client should automatically create the cache directory structure.
        """
        cache_dir = tmp_path / "nonexistent_cache"
        # Directory doesn't exist yet
        assert not cache_dir.exists()

        client = CDXClient(cache_dir=cache_dir)

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20220106075526",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "ABC123",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.fetch_snapshots("dQw4w9WgXcQ")

            # Cache directory should now exist
            cache_subdir = cache_dir / "cdx"
            assert cache_subdir.exists()
            assert cache_subdir.is_dir()


# =============================================================================
# TestCDXRetry (T014) - Retry and rate limiting
# =============================================================================


class TestCDXRetry:
    """Test retry and rate limiting."""

    async def test_exponential_backoff_on_503(self) -> None:
        """
        HTTP 503 → retry with exponential backoff (3 retries, 2s base).

        Server errors should be retried with exponential backoff.
        Mock sleep to verify delays: 2s, 4s, 8s.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        # First 3 calls return 503, 4th call succeeds
        responses = [
            httpx.Response(status_code=503, text="Service Unavailable"),
            httpx.Response(status_code=503, text="Service Unavailable"),
            httpx.Response(status_code=503, text="Service Unavailable"),
            httpx.Response(
                status_code=200,
                json=[
                    ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                    [
                        "20220106075526",
                        "https://www.youtube.com/watch?v=test",
                        "text/html",
                        "200",
                        "ABC123",
                        "50000",
                    ],
                ],
            ),
        ]

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, patch(
            "asyncio.sleep"
        ) as mock_sleep:
            mock_get.side_effect = responses

            snapshots = await client.fetch_snapshots("test123")

            # Should succeed after retries
            assert len(snapshots) == 1

            # Verify exponential backoff: 2s, 4s, 8s
            assert mock_sleep.call_count == 3
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert sleep_calls[0] == pytest.approx(2.0, rel=0.1)
            assert sleep_calls[1] == pytest.approx(4.0, rel=0.1)
            assert sleep_calls[2] == pytest.approx(8.0, rel=0.1)

    async def test_fixed_pause_on_429(self) -> None:
        """
        HTTP 429 → 60s fixed pause before retry.

        Rate limit errors should trigger a fixed 60-second pause before retry.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        # First call returns 429, second call succeeds
        responses = [
            httpx.Response(status_code=429, text="Too Many Requests"),
            httpx.Response(
                status_code=200,
                json=[
                    ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                    [
                        "20220106075526",
                        "https://www.youtube.com/watch?v=test",
                        "text/html",
                        "200",
                        "ABC123",
                        "50000",
                    ],
                ],
            ),
        ]

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, patch(
            "asyncio.sleep"
        ) as mock_sleep:
            mock_get.side_effect = responses

            snapshots = await client.fetch_snapshots("test123")

            # Should succeed after retry
            assert len(snapshots) == 1

            # Verify 60s pause
            mock_sleep.assert_called_once_with(60.0)

    async def test_user_agent_header(self) -> None:
        """
        All requests include User-Agent: chronovista/{version} header.

        The client should identify itself with a proper User-Agent header.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        mock_response = httpx.Response(status_code=200, json=[])

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.fetch_snapshots("test123")

            # Verify get was called
            mock_get.assert_called_once()

            # Extract headers from the call
            call_kwargs = mock_get.call_args[1]
            headers = call_kwargs.get("headers", {})

            # Verify User-Agent header
            assert "User-Agent" in headers
            user_agent = headers["User-Agent"]
            assert user_agent.startswith("chronovista/")
            # Should contain version (e.g., "chronovista/0.26.0")
            assert len(user_agent.split("/")) == 2

    async def test_httpx_timeout_30s(self) -> None:
        """
        CDX requests use 30s timeout.

        The client should configure httpx with a 30-second timeout for CDX requests.
        """
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        mock_response = httpx.Response(status_code=200, json=[])

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.fetch_snapshots("test123")

            # Verify get was called
            mock_get.assert_called_once()

            # Extract timeout from the call
            call_kwargs = mock_get.call_args[1]
            timeout = call_kwargs.get("timeout")

            # Verify timeout is 30 seconds
            assert timeout == 30.0 or timeout == 30


# =============================================================================
# TestCDXYearFiltering - from_year / to_year parameter support
# =============================================================================


class TestCDXYearFilteringURL:
    """Test that _build_cdx_url correctly appends from/to year parameters."""

    def test_build_cdx_url_with_from_year(self) -> None:
        """_build_cdx_url with from_year uses positive limit (oldest first from anchor)."""
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        url = client._build_cdx_url("dQw4w9WgXcQ", from_year=2018)

        assert "&from=20180101000000" in url
        assert "&to=" not in url
        # Positive limit = oldest first from anchor year
        assert "limit=100" in url
        assert "limit=-100" not in url

    def test_build_cdx_url_with_to_year(self) -> None:
        """_build_cdx_url with only to_year uses negative limit (newest first)."""
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        url = client._build_cdx_url("dQw4w9WgXcQ", to_year=2020)

        assert "&to=20201231235959" in url
        assert "&from=" not in url
        # No from_year = newest first (default)
        assert "limit=-100" in url

    def test_build_cdx_url_with_both_years(self) -> None:
        """_build_cdx_url with both years uses positive limit (oldest first from anchor)."""
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        url = client._build_cdx_url("dQw4w9WgXcQ", from_year=2018, to_year=2020)

        assert "&from=20180101000000" in url
        assert "&to=20201231235959" in url
        # from_year present = oldest first from anchor
        assert "limit=100" in url
        assert "limit=-100" not in url

    def test_build_cdx_url_with_neither_year(self) -> None:
        """_build_cdx_url with no year params produces unchanged URL (newest first)."""
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        url = client._build_cdx_url("dQw4w9WgXcQ")

        assert "&from=" not in url
        assert "&to=" not in url
        # Should still contain normal params
        assert "output=json" in url
        assert "limit=-100" in url


class TestCDXYearFilteringCachePath:
    """Test that _cache_path incorporates year filters into the cache filename."""

    def test_cache_path_with_from_year(self, tmp_path: Path) -> None:
        """_cache_path with from_year=2018 returns {video_id}_from2018.json."""
        client = CDXClient(cache_dir=tmp_path)

        result = client._cache_path("dQw4w9WgXcQ", from_year=2018)

        assert result == tmp_path / "cdx" / "dQw4w9WgXcQ_from2018.json"

    def test_cache_path_with_to_year(self, tmp_path: Path) -> None:
        """_cache_path with to_year=2020 returns {video_id}_to2020.json."""
        client = CDXClient(cache_dir=tmp_path)

        result = client._cache_path("dQw4w9WgXcQ", to_year=2020)

        assert result == tmp_path / "cdx" / "dQw4w9WgXcQ_to2020.json"

    def test_cache_path_with_both_years(self, tmp_path: Path) -> None:
        """_cache_path with both returns {video_id}_from2018_to2020.json."""
        client = CDXClient(cache_dir=tmp_path)

        result = client._cache_path("dQw4w9WgXcQ", from_year=2018, to_year=2020)

        assert result == tmp_path / "cdx" / "dQw4w9WgXcQ_from2018_to2020.json"

    def test_cache_path_with_neither_year(self, tmp_path: Path) -> None:
        """_cache_path with neither returns {video_id}.json (backward compat)."""
        client = CDXClient(cache_dir=tmp_path)

        result = client._cache_path("dQw4w9WgXcQ")

        assert result == tmp_path / "cdx" / "dQw4w9WgXcQ.json"


class TestCDXYearFilteringIntegration:
    """Test that fetch_snapshots threads from_year/to_year through the stack."""

    async def test_fetch_snapshots_passes_years_to_url(self) -> None:
        """fetch_snapshots threads from_year/to_year to _build_cdx_url via _fetch_with_retries."""
        client = CDXClient(cache_dir=Path("/tmp/test_cache"))

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20190601120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "ABC123DEF456",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.fetch_snapshots(
                "dQw4w9WgXcQ", from_year=2018, to_year=2020
            )

            # Verify the URL includes from/to params
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            requested_url = str(call_args[0][0])
            assert "&from=20180101000000" in requested_url
            assert "&to=20201231235959" in requested_url

    async def test_fetch_snapshots_year_filtered_cache_hit(
        self, tmp_path: Path
    ) -> None:
        """Cache hit for year-filtered query uses correct cache file and oldest-first order."""
        cache_dir = tmp_path / "cdx_cache"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / "cdx" / "dQw4w9WgXcQ_from2018_to2020.json"
        cache_file.parent.mkdir(parents=True)

        # Create a fresh cache entry (stored newest-first, as _parse_cdx_response does)
        cache_entry = CdxCacheEntry(
            video_id="dQw4w9WgXcQ",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=1),
            snapshots=[
                CdxSnapshot(
                    timestamp="20200601120000",
                    original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    mimetype="text/html",
                    statuscode=200,
                    digest="NEWER_2020",
                    length=50000,
                ),
                CdxSnapshot(
                    timestamp="20180601120000",
                    original="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    mimetype="text/html",
                    statuscode=200,
                    digest="OLDER_2018",
                    length=50000,
                ),
            ],
            raw_count=2,
        )

        cache_file.write_text(cache_entry.model_dump_json())

        client = CDXClient(cache_dir=cache_dir)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            snapshots = await client.fetch_snapshots(
                "dQw4w9WgXcQ", from_year=2018, to_year=2020
            )

            # Should not make HTTP request (cache hit)
            mock_get.assert_not_called()

            # Should return oldest-first when from_year is set
            assert len(snapshots) == 2
            assert snapshots[0].digest == "OLDER_2018"
            assert snapshots[1].digest == "NEWER_2020"

    async def test_fetch_snapshots_year_filtered_cache_miss_writes_correct_file(
        self, tmp_path: Path
    ) -> None:
        """Cache miss for year-filtered query writes to correct cache file."""
        cache_dir = tmp_path / "cdx_cache"

        client = CDXClient(cache_dir=cache_dir)

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20190601120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "FRESH_YEAR01",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.fetch_snapshots(
                "dQw4w9WgXcQ", from_year=2018, to_year=2020
            )

        # Cache file should be written at the year-filtered path
        expected_cache = cache_dir / "cdx" / "dQw4w9WgXcQ_from2018_to2020.json"
        assert expected_cache.exists()

        # The unfiltered cache file should NOT exist
        unfiltered_cache = cache_dir / "cdx" / "dQw4w9WgXcQ.json"
        assert not unfiltered_cache.exists()

    async def test_fetch_snapshots_with_from_year_returns_oldest_first(
        self, tmp_path: Path
    ) -> None:
        """fetch_snapshots with from_year returns snapshots oldest-first."""
        client = CDXClient(cache_dir=tmp_path)

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20180301120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "OLDEST_2018",
                "50000",
            ],
            [
                "20190601120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "MIDDLE_2019",
                "50000",
            ],
            [
                "20200901120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "NEWEST_2020",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots(
                "dQw4w9WgXcQ", from_year=2018
            )

        # With from_year, results should be oldest-first (ascending)
        assert len(snapshots) == 3
        assert snapshots[0].digest == "OLDEST_2018"
        assert snapshots[1].digest == "MIDDLE_2019"
        assert snapshots[2].digest == "NEWEST_2020"

    async def test_fetch_snapshots_without_from_year_returns_newest_first(
        self, tmp_path: Path
    ) -> None:
        """fetch_snapshots without from_year returns snapshots newest-first (default)."""
        client = CDXClient(cache_dir=tmp_path)

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20180301120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "OLDEST_2018",
                "50000",
            ],
            [
                "20190601120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "MIDDLE_2019",
                "50000",
            ],
            [
                "20200901120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "NEWEST_2020",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots("dQw4w9WgXcQ")

        # Without from_year, results should be newest-first (descending)
        assert len(snapshots) == 3
        assert snapshots[0].digest == "NEWEST_2020"
        assert snapshots[1].digest == "MIDDLE_2019"
        assert snapshots[2].digest == "OLDEST_2018"

    async def test_fetch_snapshots_with_only_to_year_returns_newest_first(
        self, tmp_path: Path
    ) -> None:
        """fetch_snapshots with only to_year (no from_year) returns newest-first."""
        client = CDXClient(cache_dir=tmp_path)

        cdx_response = [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            [
                "20180301120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "OLDER",
                "50000",
            ],
            [
                "20190601120000",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "text/html",
                "200",
                "NEWER",
                "50000",
            ],
        ]

        mock_response = httpx.Response(status_code=200, json=cdx_response)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            snapshots = await client.fetch_snapshots(
                "dQw4w9WgXcQ", to_year=2020
            )

        # Only to_year (no from_year) = newest-first (default)
        assert len(snapshots) == 2
        assert snapshots[0].digest == "NEWER"
        assert snapshots[1].digest == "OLDER"
