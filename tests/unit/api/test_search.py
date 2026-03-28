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
from datetime import UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app

# CRITICAL: ensures async tests work correctly with coverage

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


# ---------------------------------------------------------------------------
# T006-D: TestSearchSegmentsBatchContextFetching
# ---------------------------------------------------------------------------


def _make_segment_mock(
    seg_id: int,
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    text: str = "Hello world",
    corrected_text: str | None = None,
    has_correction: bool = False,
    start_time: float = 0.0,
    end_time: float = 5.0,
) -> MagicMock:
    """Build a mock TranscriptSegment ORM object with the attributes the router reads."""
    seg = MagicMock()
    seg.id = seg_id
    seg.video_id = video_id
    seg.language_code = language_code
    seg.text = text
    seg.corrected_text = corrected_text
    seg.has_correction = has_correction
    seg.start_time = start_time
    seg.end_time = end_time
    return seg


def _make_video_mock(
    video_id: str = "dQw4w9WgXcQ",
    title: str = "Test Video",
    availability_status: str = "available",
    upload_date: Any = None,
) -> MagicMock:
    """Build a mock Video ORM object."""
    from datetime import datetime

    video = MagicMock()
    video.video_id = video_id
    video.title = title
    video.availability_status = availability_status
    video.channel_id = "UCtest"
    video.upload_date = upload_date or datetime(2024, 1, 1, tzinfo=UTC)
    return video


def _make_channel_mock(channel_id: str = "UCtest", title: str = "Test Channel") -> MagicMock:
    """Build a mock Channel ORM object."""
    ch = MagicMock()
    ch.channel_id = channel_id
    ch.title = title
    return ch


def _make_transcript_mock(
    video_id: str = "dQw4w9WgXcQ", language_code: str = "en"
) -> MagicMock:
    """Build a mock VideoTranscript ORM object."""
    t = MagicMock()
    t.video_id = video_id
    t.language_code = language_code
    return t


def _make_four_call_side_effect(
    *,
    lang_rows: list[Any],
    count_value: int,
    search_rows: list[Any],
    context_rows: list[Any],
) -> list[MagicMock]:
    """
    Build the list of mock execute() return values for the four sequential
    session.execute() calls made by search_segments:

      1. languages query  → result.all()  returns lang_rows (list of 1-tuples)
      2. count query      → result.scalar() returns count_value
      3. main search      → result.all()  returns search_rows (list of 4-tuples)
      4. context CTE      → result.all()  returns context_rows (list of 3-tuples)
    """
    # Call 1 — languages
    lang_result = MagicMock()
    lang_result.all.return_value = lang_rows

    # Call 2 — count
    count_result = MagicMock()
    count_result.scalar.return_value = count_value

    # Call 3 — main search rows
    search_result = MagicMock()
    search_result.all.return_value = search_rows

    # Call 4 — context CTE
    ctx_result = MagicMock()
    ctx_result.all.return_value = context_rows

    return [lang_result, count_result, search_result, ctx_result]


class TestSearchSegmentsBatchContextFetching:
    """
    Verify that the LAG/LEAD window-function CTE correctly populates
    context_before and context_after on search result segments.

    The refactored search_segments handler issues four sequential
    session.execute() calls:
      1. Available-languages query
      2. Total-count query
      3. Main search rows query
      4. Batch context CTE query (LAG/LEAD)

    These tests use side_effect lists so each call receives an independent
    mock result, letting us control what context the endpoint sees without
    running real SQL.
    """

    @pytest.fixture
    async def context_client(self) -> AsyncGenerator[tuple[AsyncClient, AsyncMock], None]:
        """
        Async client whose mock session exposes ``execute`` as an AsyncMock
        with a configurable ``side_effect`` list.

        Yields (client, mock_session) so individual tests can set
        ``mock_session.execute.side_effect`` before making requests.
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
                yield client, mock_session
        finally:
            app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Helper: build a single-segment scenario
    # ------------------------------------------------------------------

    def _single_segment_scenario(
        self,
        *,
        seg_id: int = 1,
        prev_text: str | None,
        next_text: str | None,
        seg_text: str = "matching segment text",
        corrected_text: str | None = None,
    ) -> list[MagicMock]:
        """
        Return the side_effect list for a search returning one segment whose
        context CTE row carries the given prev_text / next_text values.
        """
        seg = _make_segment_mock(
            seg_id=seg_id,
            text=seg_text,
            corrected_text=corrected_text,
            has_correction=corrected_text is not None,
        )
        video = _make_video_mock()
        channel = _make_channel_mock()
        transcript = _make_transcript_mock()

        return _make_four_call_side_effect(
            lang_rows=[("en",)],
            count_value=1,
            search_rows=[(seg, transcript, video, channel)],
            context_rows=[(seg_id, prev_text, next_text)],
        )

    # ------------------------------------------------------------------
    # T006-D-1: context populated from adjacent segments
    # ------------------------------------------------------------------

    async def test_context_before_and_after_populated(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        context_before and context_after are non-None when adjacent
        segments exist in the same (video_id, language_code) partition.
        """
        client, mock_session = context_client

        side_effects = self._single_segment_scenario(
            prev_text="Previous sentence text.",
            next_text="Next sentence text.",
        )
        mock_session.execute.side_effect = side_effects

        response = await client.get("/api/v1/search/segments?q=matching+segment")
        assert response.status_code == 200

        body = response.json()
        assert len(body["data"]) == 1
        item = body["data"][0]
        assert item["context_before"] == "Previous sentence text."
        assert item["context_after"] == "Next sentence text."

    # ------------------------------------------------------------------
    # T006-D-2: first segment — no previous neighbour
    # ------------------------------------------------------------------

    async def test_context_before_is_none_for_first_segment(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        context_before is None when the segment is the first in its partition
        (LAG returns NULL for the first row).
        """
        client, mock_session = context_client

        side_effects = self._single_segment_scenario(
            prev_text=None,
            next_text="The segment that comes after.",
        )
        mock_session.execute.side_effect = side_effects

        response = await client.get("/api/v1/search/segments?q=matching+segment")
        assert response.status_code == 200

        item = response.json()["data"][0]
        assert item["context_before"] is None
        assert item["context_after"] == "The segment that comes after."

    # ------------------------------------------------------------------
    # T006-D-3: last segment — no next neighbour
    # ------------------------------------------------------------------

    async def test_context_after_is_none_for_last_segment(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        context_after is None when the segment is the last in its partition
        (LEAD returns NULL for the last row).
        """
        client, mock_session = context_client

        side_effects = self._single_segment_scenario(
            prev_text="The segment that came before.",
            next_text=None,
        )
        mock_session.execute.side_effect = side_effects

        response = await client.get("/api/v1/search/segments?q=matching+segment")
        assert response.status_code == 200

        item = response.json()["data"][0]
        assert item["context_before"] == "The segment that came before."
        assert item["context_after"] is None

    # ------------------------------------------------------------------
    # T006-D-4: both neighbours absent (only segment in partition)
    # ------------------------------------------------------------------

    async def test_context_both_none_for_solo_segment(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        Both context_before and context_after are None when the matching
        segment is the only one in its (video_id, language_code) partition.
        """
        client, mock_session = context_client

        side_effects = self._single_segment_scenario(
            prev_text=None,
            next_text=None,
        )
        mock_session.execute.side_effect = side_effects

        response = await client.get("/api/v1/search/segments?q=matching+segment")
        assert response.status_code == 200

        item = response.json()["data"][0]
        assert item["context_before"] is None
        assert item["context_after"] is None

    # ------------------------------------------------------------------
    # T006-D-5: context truncated at 200 characters
    # ------------------------------------------------------------------

    async def test_context_before_truncated_to_200_chars(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        context_before is truncated to 200 characters when the adjacent
        segment text is longer (router applies [:200] slice).
        """
        client, mock_session = context_client

        long_text = "A" * 250  # 250-char string — exceeds the 200-char limit
        side_effects = self._single_segment_scenario(
            prev_text=long_text,
            next_text="Short next.",
        )
        mock_session.execute.side_effect = side_effects

        response = await client.get("/api/v1/search/segments?q=matching+segment")
        assert response.status_code == 200

        item = response.json()["data"][0]
        assert item["context_before"] == "A" * 200
        assert len(item["context_before"]) == 200

    async def test_context_after_truncated_to_200_chars(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        context_after is truncated to 200 characters when the adjacent
        segment text is longer.
        """
        client, mock_session = context_client

        long_text = "B" * 300
        side_effects = self._single_segment_scenario(
            prev_text="Short prev.",
            next_text=long_text,
        )
        mock_session.execute.side_effect = side_effects

        response = await client.get("/api/v1/search/segments?q=matching+segment")
        assert response.status_code == 200

        item = response.json()["data"][0]
        assert item["context_after"] == "B" * 200
        assert len(item["context_after"]) == 200

    async def test_context_exactly_200_chars_not_truncated(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        Context text that is exactly 200 characters is returned unchanged
        (boundary condition: truncation only applies when len > 200).
        """
        client, mock_session = context_client

        exact_text = "C" * 200
        side_effects = self._single_segment_scenario(
            prev_text=exact_text,
            next_text=exact_text,
        )
        mock_session.execute.side_effect = side_effects

        response = await client.get("/api/v1/search/segments?q=matching+segment")
        assert response.status_code == 200

        item = response.json()["data"][0]
        assert item["context_before"] == exact_text
        assert item["context_after"] == exact_text

    # ------------------------------------------------------------------
    # T006-D-6: corrected_text takes precedence in context
    # ------------------------------------------------------------------

    async def test_corrected_text_used_as_context(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        When an adjacent segment has a corrected_text, the CTE uses
        COALESCE(corrected_text, text), so the corrected version appears
        in context_before / context_after rather than the raw ASR text.

        We simulate this by having the context CTE row return the corrected
        string directly (the coalesce logic runs inside the DB, not Python),
        and assert that the response carries that corrected string.
        """
        client, mock_session = context_client

        corrected_prev = "This is the corrected previous segment."
        corrected_next = "This is the corrected next segment."

        side_effects = self._single_segment_scenario(
            prev_text=corrected_prev,   # CTE already resolved via COALESCE
            next_text=corrected_next,
        )
        mock_session.execute.side_effect = side_effects

        response = await client.get("/api/v1/search/segments?q=matching+segment")
        assert response.status_code == 200

        item = response.json()["data"][0]
        assert item["context_before"] == corrected_prev
        assert item["context_after"] == corrected_next

    async def test_main_segment_corrected_text_displayed(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        The segment's own ``text`` field in the response uses corrected_text
        when has_correction is True (via _display_text helper).
        """
        client, mock_session = context_client

        side_effects = self._single_segment_scenario(
            prev_text=None,
            next_text=None,
            seg_text="raw asr text with error",
            corrected_text="corrected segment text",
        )
        mock_session.execute.side_effect = side_effects

        response = await client.get("/api/v1/search/segments?q=corrected+segment")
        assert response.status_code == 200

        item = response.json()["data"][0]
        assert item["text"] == "corrected segment text"

    # ------------------------------------------------------------------
    # T006-D-7: no context query issued when result set is empty
    # ------------------------------------------------------------------

    async def test_no_context_query_when_no_results(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        When the main search returns zero rows the router skips the context
        CTE query entirely, so session.execute() is called only 3 times
        (languages, count, main search) rather than 4.
        """
        client, mock_session = context_client

        # Only three execute() calls when result set is empty
        lang_result = MagicMock()
        lang_result.all.return_value = []

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        search_result = MagicMock()
        search_result.all.return_value = []

        mock_session.execute.side_effect = [lang_result, count_result, search_result]

        response = await client.get("/api/v1/search/segments?q=matching+segment")
        assert response.status_code == 200

        body = response.json()
        assert body["data"] == []
        assert body["pagination"]["total"] == 0
        # Only 3 DB calls — no context CTE
        assert mock_session.execute.call_count == 3

    # ------------------------------------------------------------------
    # T006-D-8: multiple segments — context_map keyed by segment id
    # ------------------------------------------------------------------

    async def test_multiple_segments_context_mapped_correctly(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        When multiple segments are returned, context_before / context_after
        for each result map to the correct segment via the seg_id key.

        Segment 1: has prev=None, next="middle text"
        Segment 2: has prev="first text", next=None
        """
        client, mock_session = context_client

        from datetime import datetime

        upload = datetime(2024, 6, 1, tzinfo=UTC)
        seg1 = _make_segment_mock(seg_id=1, text="first segment", start_time=0.0, end_time=3.0)
        seg2 = _make_segment_mock(seg_id=2, text="second segment", start_time=3.0, end_time=6.0)
        video = _make_video_mock(upload_date=upload)
        channel = _make_channel_mock()
        transcript = _make_transcript_mock()

        lang_result = MagicMock()
        lang_result.all.return_value = [("en",)]

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        search_result = MagicMock()
        search_result.all.return_value = [
            (seg1, transcript, video, channel),
            (seg2, transcript, video, channel),
        ]

        ctx_result = MagicMock()
        ctx_result.all.return_value = [
            (1, None, "middle text"),   # seg_id=1: no prev, next="middle text"
            (2, "first segment", None), # seg_id=2: prev="first segment", no next
        ]

        mock_session.execute.side_effect = [lang_result, count_result, search_result, ctx_result]

        response = await client.get("/api/v1/search/segments?q=segment")
        assert response.status_code == 200

        data = response.json()["data"]
        assert len(data) == 2

        # Segment 1 (segment_id=1)
        s1 = next(d for d in data if d["segment_id"] == 1)
        assert s1["context_before"] is None
        assert s1["context_after"] == "middle text"

        # Segment 2 (segment_id=2)
        s2 = next(d for d in data if d["segment_id"] == 2)
        assert s2["context_before"] == "first segment"
        assert s2["context_after"] is None

    # ------------------------------------------------------------------
    # T006-D-9: context_map defaults to (None, None) for missing CTE rows
    # ------------------------------------------------------------------

    async def test_segment_missing_from_context_cte_defaults_to_none(
        self, context_client: tuple[AsyncClient, AsyncMock]
    ) -> None:
        """
        If a segment ID does not appear in the context CTE result (e.g., the
        window query returned no row for it), context_map.get() returns
        (None, None) and the response fields are null rather than raising
        a KeyError.
        """
        client, mock_session = context_client

        seg = _make_segment_mock(seg_id=99, text="orphan segment")
        video = _make_video_mock()
        channel = _make_channel_mock()
        transcript = _make_transcript_mock()

        side_effects = _make_four_call_side_effect(
            lang_rows=[("en",)],
            count_value=1,
            search_rows=[(seg, transcript, video, channel)],
            context_rows=[],  # CTE returned nothing for this segment
        )
        mock_session.execute.side_effect = side_effects

        response = await client.get("/api/v1/search/segments?q=orphan+segment")
        assert response.status_code == 200

        item = response.json()["data"][0]
        assert item["context_before"] is None
        assert item["context_after"] is None
