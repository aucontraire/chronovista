"""
Unit tests for search router — phrase matching and NULL byte rejection (T006).

Tests focus on request/response behavior of the three search endpoints:
  - GET /api/v1/search/segments
  - GET /api/v1/search/titles
  - GET /api/v1/search/descriptions

All database I/O is mocked via dependency override so these tests run
without a real database connection.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app

# CRITICAL: ensures async tests work correctly with coverage
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared fixture: mocked async client
# ---------------------------------------------------------------------------


def _make_empty_execute_result() -> MagicMock:
    """Return a mock session.execute() result that yields no rows."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar.return_value = 0
    mock_result.all.return_value = []
    return mock_result


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Create async test client with fully mocked database and auth.

    Overrides ``get_db`` and ``require_auth`` FastAPI dependencies so that
    no real database or OAuth credentials are required.
    """
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(return_value=_make_empty_execute_result())

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def mock_require_auth() -> None:
        return None

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[require_auth] = mock_require_auth

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# T006-A: TestSearchSegmentsNullByteRejection
# ---------------------------------------------------------------------------


class TestSearchSegmentsNullByteRejection:
    """
    Verify that all three search endpoints reject NULL bytes with HTTP 400.

    NULL bytes (``\\x00``) are invalid in SQL and PostgreSQL raises an error
    when they appear in ILIKE patterns.  The routers must reject them before
    any SQL is executed.

    Note: NULL bytes must be percent-encoded as ``%00`` in the URL because
    httpx (and the HTTP spec) prohibit raw ``\\x00`` in URL strings.  The
    ASGI layer decodes ``%00`` back to the NUL character before the router
    receives the query parameter value.
    """

    async def test_segments_null_byte_returns_400(
        self, async_client: AsyncClient
    ) -> None:
        """GET /search/segments with NULL byte (percent-encoded) returns 400."""
        # %00 → decoded as \x00 by the query-string parser
        response = await async_client.get("/api/v1/search/segments?q=hello%00world")
        assert response.status_code == 400

    async def test_segments_null_byte_rfc7807_code(
        self, async_client: AsyncClient
    ) -> None:
        """400 response for NULL byte has RFC 7807 ``code=BAD_REQUEST``."""
        response = await async_client.get("/api/v1/search/segments?q=hello%00world")
        assert response.status_code == 400
        body = response.json()
        assert body.get("code") == "BAD_REQUEST"

    async def test_segments_null_byte_only_returns_400(
        self, async_client: AsyncClient
    ) -> None:
        """A query with a NULL byte also returns 400 (two chars, one is NUL)."""
        response = await async_client.get("/api/v1/search/segments?q=a%00")
        assert response.status_code == 400

    async def test_titles_null_byte_returns_400(
        self, async_client: AsyncClient
    ) -> None:
        """GET /search/titles with NULL byte (percent-encoded) returns 400."""
        response = await async_client.get("/api/v1/search/titles?q=he%00llo")
        assert response.status_code == 400
        body = response.json()
        assert body.get("code") == "BAD_REQUEST"

    async def test_descriptions_null_byte_returns_400(
        self, async_client: AsyncClient
    ) -> None:
        """GET /search/descriptions with NULL byte (percent-encoded) returns 400."""
        response = await async_client.get("/api/v1/search/descriptions?q=he%00llo")
        assert response.status_code == 400
        body = response.json()
        assert body.get("code") == "BAD_REQUEST"

    async def test_null_byte_mid_string_segments(
        self, async_client: AsyncClient
    ) -> None:
        """NULL byte embedded in a longer query (segments) is rejected."""
        response = await async_client.get(
            "/api/v1/search/segments?q=some%00query"
        )
        assert response.status_code == 400

    async def test_null_byte_mid_string_titles(
        self, async_client: AsyncClient
    ) -> None:
        """NULL byte embedded in a title search query is rejected."""
        response = await async_client.get(
            "/api/v1/search/titles?q=some%00query"
        )
        assert response.status_code == 400

    async def test_null_byte_mid_string_descriptions(
        self, async_client: AsyncClient
    ) -> None:
        """NULL byte embedded in a description search query is rejected."""
        response = await async_client.get(
            "/api/v1/search/descriptions?q=some%00query"
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# T006-B: TestSearchSegmentsPhraseMatching
# ---------------------------------------------------------------------------


class TestSearchSegmentsPhraseMatching:
    """
    Verify that multi-word queries are treated as a contiguous phrase.

    The old implementation split on whitespace and produced per-word ILIKE
    conditions.  The new implementation passes the entire query — including
    spaces — as a single ILIKE argument.  We cannot inspect internal SQL
    without a real DB, but we can verify that the endpoint accepts
    multi-word and special-character queries without error, and that those
    queries produce a valid 200 response (not a 400/422/500).
    """

    async def test_multi_word_query_accepted_segments(
        self, async_client: AsyncClient
    ) -> None:
        """Multi-word query with space returns 200 (not 422 or 500)."""
        response = await async_client.get(
            "/api/v1/search/segments?q=hello+world"
        )
        assert response.status_code == 200

    async def test_multi_word_with_percent_accepted_segments(
        self, async_client: AsyncClient
    ) -> None:
        """Query containing ``%`` is accepted and returns 200."""
        response = await async_client.get(
            "/api/v1/search/segments?q=100%25+complete"
        )
        assert response.status_code == 200

    async def test_multi_word_with_underscore_accepted_segments(
        self, async_client: AsyncClient
    ) -> None:
        """Query containing ``_`` is accepted and returns 200."""
        response = await async_client.get(
            "/api/v1/search/segments?q=__init__+method"
        )
        assert response.status_code == 200

    async def test_multi_word_with_backslash_accepted_segments(
        self, async_client: AsyncClient
    ) -> None:
        """Query containing backslash is accepted and returns 200."""
        response = await async_client.get(
            "/api/v1/search/segments?q=C%3A%5Cpath+file"
        )
        assert response.status_code == 200

    async def test_multi_word_query_response_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Multi-word query returns the standard paginated response structure."""
        response = await async_client.get(
            "/api/v1/search/segments?q=hello+world"
        )
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "pagination" in body
        assert "available_languages" in body
        assert isinstance(body["data"], list)

    async def test_multi_word_query_accepted_titles(
        self, async_client: AsyncClient
    ) -> None:
        """Title search: multi-word query is accepted without error."""
        response = await async_client.get(
            "/api/v1/search/titles?q=python+tutorial"
        )
        assert response.status_code == 200

    async def test_multi_word_with_percent_accepted_titles(
        self, async_client: AsyncClient
    ) -> None:
        """Title search: query with ``%`` is accepted and returns 200."""
        response = await async_client.get(
            "/api/v1/search/titles?q=100%25+tutorial"
        )
        assert response.status_code == 200

    async def test_multi_word_query_accepted_descriptions(
        self, async_client: AsyncClient
    ) -> None:
        """Description search: multi-word query is accepted without error."""
        response = await async_client.get(
            "/api/v1/search/descriptions?q=python+tutorial"
        )
        assert response.status_code == 200

    async def test_multi_word_with_percent_accepted_descriptions(
        self, async_client: AsyncClient
    ) -> None:
        """Description search: query with ``%`` is accepted and returns 200."""
        response = await async_client.get(
            "/api/v1/search/descriptions?q=100%25+tutorial"
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# T006-C: TestSearchSegmentsSpecialCharWithVideoFilter
# ---------------------------------------------------------------------------


class TestSearchSegmentsSpecialCharWithVideoFilter:
    """
    Verify that special character queries work correctly with video_id filters.

    FR-004 requires that special-character queries scoped to a specific video
    ID return the correct (possibly empty) result set rather than crashing or
    ignoring the video_id filter.
    """

    async def test_percent_query_with_video_id_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        """Percent sign in query combined with video_id filter returns 200."""
        response = await async_client.get(
            "/api/v1/search/segments?q=100%25&video_id=dQw4w9WgXcQ"
        )
        assert response.status_code == 200

    async def test_underscore_query_with_video_id_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        """Underscore in query combined with video_id filter returns 200."""
        response = await async_client.get(
            "/api/v1/search/segments?q=__init__&video_id=dQw4w9WgXcQ"
        )
        assert response.status_code == 200

    async def test_backslash_query_with_video_id_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        """Backslash in query combined with video_id filter returns 200."""
        response = await async_client.get(
            "/api/v1/search/segments?q=C%3A%5Cpath&video_id=dQw4w9WgXcQ"
        )
        assert response.status_code == 200

    async def test_multi_word_special_query_with_video_id_response_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Combined filter returns valid paginated response shape."""
        response = await async_client.get(
            "/api/v1/search/segments?q=100%25+_done&video_id=dQw4w9WgXcQ"
        )
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "pagination" in body
        # With a mocked empty DB, data should be an empty list
        assert isinstance(body["data"], list)

    async def test_video_id_filter_validation_still_applies_with_special_chars(
        self, async_client: AsyncClient
    ) -> None:
        """video_id validation (must be 11 chars) still applies alongside special chars."""
        response = await async_client.get(
            "/api/v1/search/segments?q=100%25&video_id=short"
        )
        assert response.status_code == 422

    async def test_null_byte_with_video_id_returns_400_not_500(
        self, async_client: AsyncClient
    ) -> None:
        """NULL byte (percent-encoded) is rejected even when video_id filter is present."""
        response = await async_client.get(
            "/api/v1/search/segments?q=hel%00lo&video_id=dQw4w9WgXcQ"
        )
        assert response.status_code == 400
        body = response.json()
        assert body.get("code") == "BAD_REQUEST"

    async def test_language_filter_with_special_char_query(
        self, async_client: AsyncClient
    ) -> None:
        """Language filter combined with special character query returns 200."""
        response = await async_client.get(
            "/api/v1/search/segments?q=100%25+done&language=en"
        )
        assert response.status_code == 200

    async def test_all_filters_combined_with_special_chars(
        self, async_client: AsyncClient
    ) -> None:
        """All filters (video_id + language) combined with special char query returns 200."""
        response = await async_client.get(
            "/api/v1/search/segments?q=__init__&video_id=dQw4w9WgXcQ&language=en"
        )
        assert response.status_code == 200
