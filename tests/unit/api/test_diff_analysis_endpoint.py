"""
Unit tests for GET /api/v1/corrections/batch/diff-analysis endpoint.

Tests the diff analysis endpoint in:
  src/chronovista/api/routers/batch_corrections.py

Mounted at: /api/v1/corrections/batch

Scenarios covered:
- 200 with patterns and entity enrichment
- 200 with entity_name filter applied
- 200 with empty results
- Entity enrichment via alias fallback
- Query parameter validation
- Token-level remaining_matches computation
- show_completed filtering at the token level
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app
from chronovista.api.routers.batch_corrections import (
    _PATTERN_TOKENISE_CAP,
    _REMAINING_MATCH_CAP,
)
from chronovista.models.batch_correction_models import CorrectionPattern

# CRITICAL: This line ensures async tests work with coverage

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_pattern(
    *,
    original_text: str = "jonsun",
    corrected_text: str = "Johnson",
    occurrences: int = 5,
    remaining_matches: int = 3,
) -> CorrectionPattern:
    """Build a CorrectionPattern with optional overrides."""
    return CorrectionPattern(
        original_text=original_text,
        corrected_text=corrected_text,
        occurrences=occurrences,
        remaining_matches=remaining_matches,
    )


def _mock_session_with_remaining(remaining: int = 3) -> AsyncMock:
    """Create a mock session that returns a remaining_matches scalar."""
    mock = AsyncMock(spec=AsyncSession)
    # session.execute() returns a result with scalar_one()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = remaining
    mock.execute = AsyncMock(return_value=mock_result)
    return mock


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide a clean AsyncSession mock with remaining_matches support."""
    return _mock_session_with_remaining(remaining=3)


@pytest.fixture
async def client(mock_session: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI test client with DB and auth overridden."""

    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _require_auth() -> None:
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[require_auth] = _require_auth

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


def _make_client_with_remaining(remaining: int) -> AsyncGenerator[AsyncClient, None]:
    """Create a client fixture with a specific remaining_matches value."""
    mock = _mock_session_with_remaining(remaining=remaining)

    async def _gen() -> AsyncGenerator[AsyncClient, None]:
        async def _get_db() -> AsyncGenerator[AsyncSession, None]:
            yield mock

        async def _require_auth() -> None:
            return None

        app.dependency_overrides[get_db] = _get_db
        app.dependency_overrides[require_auth] = _require_auth

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return _gen()


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/corrections/batch/diff-analysis
# ═══════════════════════════════════════════════════════════════════════════


class TestGetDiffAnalysis:
    """Tests for GET /api/v1/corrections/batch/diff-analysis."""

    BASE_URL = "/api/v1/corrections/batch/diff-analysis"

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_returns_200_with_patterns(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
        client: AsyncClient,
    ) -> None:
        """Endpoint returns 200 with patterns mapped to response schema."""
        pattern = _make_pattern()
        entity_id = uuid.uuid4()
        mock_service.get_patterns = AsyncMock(return_value=[pattern])
        mock_find_entity.return_value = (entity_id, "Johnson")

        response = await client.get(self.BASE_URL)

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert len(data) == 1
        assert data[0]["error_token"] == "jonsun"
        assert data[0]["canonical_form"] == "Johnson"
        assert data[0]["frequency"] == 5
        # remaining_matches is now computed at the token level (mock returns 3)
        assert data[0]["remaining_matches"] == 3
        assert data[0]["entity_id"] == str(entity_id)
        assert data[0]["entity_name"] == "Johnson"

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_limit_truncates_the_response(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
        client: AsyncClient,
    ) -> None:
        """`limit` bounds what is returned, now that it no longer bounds
        what is tokenised.

        Moving it off the pattern fetch would otherwise make it a silent
        no-op: the endpoint would accept the parameter and ignore it.
        """
        patterns = [
            _make_pattern(original_text=f"err{i}", corrected_text=f"Fix{i}")
            for i in range(5)
        ]
        mock_service.get_patterns = AsyncMock(return_value=patterns)
        mock_find_entity.return_value = (None, None)

        response = await client.get(self.BASE_URL, params={"limit": 2})

        assert response.status_code == 200
        assert len(response.json()["data"]) == 2

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_every_pattern_is_tokenised_regardless_of_limit(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
        client: AsyncClient,
    ) -> None:
        """A small limit must not stop tokens being derived.

        This is the defect the cap replaced: truncating the pattern list
        before word-level extraction removed tokens from the response that
        were never computed in the first place, so no amount of paging could
        reach them.
        """
        patterns = [
            _make_pattern(original_text=f"err{i}", corrected_text=f"Fix{i}")
            for i in range(5)
        ]
        mock_service.get_patterns = AsyncMock(return_value=patterns)
        mock_find_entity.return_value = (None, None)

        await client.get(self.BASE_URL, params={"limit": 1})

        assert (
            mock_service.get_patterns.call_args.kwargs["limit"] == _PATTERN_TOKENISE_CAP
        )

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_returns_200_empty_results(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
        client: AsyncClient,
    ) -> None:
        """Endpoint returns 200 with an empty list when no patterns found."""
        mock_service.get_patterns = AsyncMock(return_value=[])

        response = await client.get(self.BASE_URL)

        assert response.status_code == 200
        assert response.json()["data"] == []

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_entity_name_filter_includes_matching(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
        client: AsyncClient,
    ) -> None:
        """Endpoint filters results when entity_name parameter is provided."""
        entity_id = uuid.uuid4()
        pattern = _make_pattern(corrected_text="Johnson")
        mock_service.get_patterns = AsyncMock(return_value=[pattern])
        mock_find_entity.return_value = (entity_id, "Johnson")

        response = await client.get(self.BASE_URL, params={"entity_name": "Johns"})

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_entity_name_filter_excludes_non_matching(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
        client: AsyncClient,
    ) -> None:
        """Patterns not matching entity_name filter are excluded."""
        pattern = _make_pattern(corrected_text="Johnson")
        mock_service.get_patterns = AsyncMock(return_value=[pattern])
        mock_find_entity.return_value = (uuid.uuid4(), "Johnson")

        response = await client.get(self.BASE_URL, params={"entity_name": "Trump"})

        assert response.status_code == 200
        assert response.json()["data"] == []

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_entity_name_filter_excludes_no_entity(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
        client: AsyncClient,
    ) -> None:
        """Patterns with no entity match are excluded when entity_name filter is set."""
        pattern = _make_pattern(corrected_text="the")
        mock_service.get_patterns = AsyncMock(return_value=[pattern])
        mock_find_entity.return_value = (None, None)

        response = await client.get(self.BASE_URL, params={"entity_name": "Johns"})

        assert response.status_code == 200
        assert response.json()["data"] == []

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_no_entity_association(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
        client: AsyncClient,
    ) -> None:
        """Patterns without entity matches return null entity fields."""
        pattern = _make_pattern(corrected_text="the")
        mock_service.get_patterns = AsyncMock(return_value=[pattern])
        mock_find_entity.return_value = (None, None)

        response = await client.get(self.BASE_URL)

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["entity_id"] is None
        assert data[0]["entity_name"] is None

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_passes_show_completed_true_to_service(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
        client: AsyncClient,
    ) -> None:
        """Service always receives show_completed=True (filtering happens at token level)."""
        mock_service.get_patterns = AsyncMock(return_value=[])

        await client.get(
            self.BASE_URL,
            params={
                "min_occurrences": 5,
                "limit": 50,
                "show_completed": False,
            },
        )

        mock_service.get_patterns.assert_awaited_once()
        call_kwargs = mock_service.get_patterns.call_args.kwargs
        assert call_kwargs["min_occurrences"] == 5
        # NOT the caller's limit. Truncating patterns before word-level
        # extraction drops tokens that are never derived at all — measured as
        # one token missing from the response entirely, because 106 correction
        # pairs exceeded the default limit of 100. Every pair is tokenised and
        # `limit` is applied to the response instead.
        assert call_kwargs["limit"] == _PATTERN_TOKENISE_CAP
        # Always True — token-level filtering happens after word_level_diff
        assert call_kwargs["show_completed"] is True
        # Always False — this endpoint recomputes remaining matches per token
        # and never reads the segment-level figure. Asking for it cost ~3.5s
        # per request and the result was discarded, so this is pinned: the
        # saving is invisible in the response and nothing else would catch
        # its loss.
        assert call_kwargs["with_remaining"] is False

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_show_completed_false_hides_zero_remaining(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
    ) -> None:
        """When show_completed=false, patterns with 0 remaining are excluded."""
        pattern = _make_pattern()
        mock_service.get_patterns = AsyncMock(return_value=[pattern])
        mock_find_entity.return_value = (None, None)

        # Create client with remaining=0
        async for ac in _make_client_with_remaining(0):
            response = await ac.get(self.BASE_URL, params={"show_completed": "false"})

        assert response.status_code == 200
        assert response.json()["data"] == []

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_show_completed_true_includes_zero_remaining(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
    ) -> None:
        """When show_completed=true, patterns with 0 remaining are included."""
        pattern = _make_pattern()
        mock_service.get_patterns = AsyncMock(return_value=[pattern])
        mock_find_entity.return_value = (None, None)

        # Create client with remaining=0
        async for ac in _make_client_with_remaining(0):
            response = await ac.get(self.BASE_URL, params={"show_completed": "true"})

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["remaining_matches"] == 0

    async def test_min_occurrences_validation(
        self,
        client: AsyncClient,
    ) -> None:
        """min_occurrences=0 returns 422."""
        response = await client.get(self.BASE_URL, params={"min_occurrences": 0})
        assert response.status_code == 422

    async def test_limit_validation(
        self,
        client: AsyncClient,
    ) -> None:
        """limit=501 returns 422."""
        response = await client.get(self.BASE_URL, params={"limit": 501})
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Remaining-match ceiling (#212)
# ═══════════════════════════════════════════════════════════════════════════


class TestRemainingMatchCap:
    """The per-token count stops at a ceiling, and says so.

    A short error token yields few trigrams, so the pg_trgm index returns a
    large candidate set the recheck mostly discards — measured at 99,210
    candidates and 27,970 heap blocks fetched to find 3,333 rows. The block
    reads dominate, so the same query ranged from 0.47s to 3.58s depending on
    what was cached.

    The ceiling bounds that fetch. Because it changes a reported number, the
    response says when it was reached rather than presenting the ceiling as an
    exact count.
    """

    BASE_URL = "/api/v1/corrections/batch/diff-analysis"

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_count_below_the_ceiling_is_not_flagged(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
    ) -> None:
        mock_service.get_patterns = AsyncMock(return_value=[_make_pattern()])
        mock_find_entity.return_value = (None, None)

        async for ac in _make_client_with_remaining(_REMAINING_MATCH_CAP - 1):
            response = await ac.get(self.BASE_URL)

        data = response.json()["data"]
        assert data[0]["remaining_matches"] == _REMAINING_MATCH_CAP - 1
        assert data[0]["remaining_matches_capped"] is False

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_count_at_the_ceiling_is_flagged(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
    ) -> None:
        """Reaching the ceiling means "at least this many", not "exactly"."""
        mock_service.get_patterns = AsyncMock(return_value=[_make_pattern()])
        mock_find_entity.return_value = (None, None)

        async for ac in _make_client_with_remaining(_REMAINING_MATCH_CAP):
            response = await ac.get(self.BASE_URL)

        data = response.json()["data"]
        assert data[0]["remaining_matches"] == _REMAINING_MATCH_CAP
        assert data[0]["remaining_matches_capped"] is True

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_zero_remaining_is_not_flagged(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
    ) -> None:
        """Guards against a `>=` that treats 0 as having hit the ceiling."""
        mock_service.get_patterns = AsyncMock(return_value=[_make_pattern()])
        mock_find_entity.return_value = (None, None)

        async for ac in _make_client_with_remaining(0):
            response = await ac.get(self.BASE_URL, params={"show_completed": "true"})

        data = response.json()["data"]
        assert data[0]["remaining_matches"] == 0
        assert data[0]["remaining_matches_capped"] is False

    @patch(
        "chronovista.api.routers.batch_corrections._find_entity_by_name",
        new_callable=AsyncMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_the_query_carries_a_limit(
        self,
        mock_service: MagicMock,
        mock_find_entity: AsyncMock,
    ) -> None:
        """The ceiling must reach the database, not just the response.

        Counting everything and then clamping the number would report the same
        values while doing all the work the ceiling exists to avoid — and no
        assertion on the response could tell the difference.
        """
        mock_service.get_patterns = AsyncMock(return_value=[_make_pattern()])
        mock_find_entity.return_value = (None, None)

        captured: list[str] = []
        mock = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one.return_value = 5

        async def _execute(stmt: object, *a: object, **kw: object) -> object:
            captured.append(" ".join(str(stmt).split()).lower())
            return result

        mock.execute = AsyncMock(side_effect=_execute)

        async def _get_db() -> AsyncGenerator[AsyncSession, None]:
            yield mock

        async def _require_auth() -> None:
            return None

        app.dependency_overrides[get_db] = _get_db
        app.dependency_overrides[require_auth] = _require_auth
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                await ac.get(self.BASE_URL)
        finally:
            app.dependency_overrides.clear()

        count_sql = [s for s in captured if "count(" in s]
        assert count_sql, "expected a remaining-match count query"
        assert any("limit" in s for s in count_sql), (
            "the count query has no LIMIT — the heap fetch is unbounded again, "
            f"got: {count_sql[0][:200]}"
        )
