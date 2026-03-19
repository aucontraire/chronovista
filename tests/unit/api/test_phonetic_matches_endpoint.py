"""
Unit tests for GET /api/v1/entities/{entity_id}/phonetic-matches endpoint.

Tests the phonetic matches endpoint in:
  src/chronovista/api/routers/entity_mentions.py

Mounted at: /api/v1

Scenarios covered:
- 200 with phonetic matches and video title enrichment
- 200 with empty results
- 404 when entity does not exist
- 422 for invalid threshold values
- Video title enrichment with missing video entries
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
from chronovista.services.phonetic_matcher import PhoneticMatch

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_match(
    *,
    original_text: str = "shein bomb",
    proposed_correction: str = "Sheinbaum",
    confidence: float = 0.78,
    evidence_description: str = "Phonetic similarity: 0.78",
    video_id: str = "abc123",
    segment_id: int = 42,
) -> PhoneticMatch:
    """Build a PhoneticMatch with optional overrides."""
    return PhoneticMatch(
        original_text=original_text,
        proposed_correction=proposed_correction,
        confidence=confidence,
        evidence_description=evidence_description,
        video_id=video_id,
        segment_id=segment_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


_ENTITY_ID = uuid.uuid4()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide a clean AsyncSession mock for each test."""
    return AsyncMock(spec=AsyncSession)


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


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/entities/{entity_id}/phonetic-matches
# ═══════════════════════════════════════════════════════════════════════════


class TestGetPhoneticMatches:
    """Tests for GET /api/v1/entities/{entity_id}/phonetic-matches."""

    def _url(self, entity_id: uuid.UUID | None = None) -> str:
        eid = entity_id or _ENTITY_ID
        return f"/api/v1/entities/{eid}/phonetic-matches"

    @patch(
        "chronovista.api.routers.entity_mentions.PhoneticMatcher",
    )
    async def test_returns_200_with_matches(
        self,
        mock_matcher_cls: MagicMock,
        client: AsyncClient,
        mock_session: AsyncMock,
    ) -> None:
        """Endpoint returns 200 with phonetic matches and video titles."""
        # Mock entity existence
        entity_mock = MagicMock()
        entity_mock.id = _ENTITY_ID
        mock_session.get = AsyncMock(return_value=entity_mock)

        # Mock phonetic matcher
        match = _make_match(video_id="vid1")
        mock_instance = MagicMock()
        mock_instance.match_entity = AsyncMock(return_value=[match])
        mock_matcher_cls.return_value = mock_instance

        # Mock video title query
        video_row = MagicMock()
        video_row.video_id = "vid1"
        video_row.title = "Test Video Title"
        execute_result = MagicMock()
        execute_result.all.return_value = [video_row]
        mock_session.execute = AsyncMock(return_value=execute_result)

        response = await client.get(self._url())

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert len(data) == 1
        assert data[0]["original_text"] == "shein bomb"
        assert data[0]["proposed_correction"] == "Sheinbaum"
        assert data[0]["confidence"] == 0.78
        assert data[0]["evidence_description"] == "Phonetic similarity: 0.78"
        assert data[0]["video_id"] == "vid1"
        assert data[0]["segment_id"] == 42
        assert data[0]["video_title"] == "Test Video Title"

    @patch(
        "chronovista.api.routers.entity_mentions.PhoneticMatcher",
    )
    async def test_returns_200_empty_matches(
        self,
        mock_matcher_cls: MagicMock,
        client: AsyncClient,
        mock_session: AsyncMock,
    ) -> None:
        """Endpoint returns 200 with empty list when no matches found."""
        entity_mock = MagicMock()
        entity_mock.id = _ENTITY_ID
        mock_session.get = AsyncMock(return_value=entity_mock)

        mock_instance = MagicMock()
        mock_instance.match_entity = AsyncMock(return_value=[])
        mock_matcher_cls.return_value = mock_instance

        response = await client.get(self._url())

        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_returns_404_entity_not_found(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
    ) -> None:
        """Endpoint returns 404 when entity does not exist."""
        mock_session.get = AsyncMock(return_value=None)

        response = await client.get(self._url())

        assert response.status_code == 404

    async def test_threshold_below_minimum(
        self,
        client: AsyncClient,
    ) -> None:
        """threshold=-0.1 returns 422."""
        response = await client.get(
            self._url(), params={"threshold": -0.1}
        )
        assert response.status_code == 422

    async def test_threshold_above_maximum(
        self,
        client: AsyncClient,
    ) -> None:
        """threshold=1.5 returns 422."""
        response = await client.get(
            self._url(), params={"threshold": 1.5}
        )
        assert response.status_code == 422

    @patch(
        "chronovista.api.routers.entity_mentions.PhoneticMatcher",
    )
    async def test_passes_threshold_to_matcher(
        self,
        mock_matcher_cls: MagicMock,
        client: AsyncClient,
        mock_session: AsyncMock,
    ) -> None:
        """Custom threshold is forwarded to PhoneticMatcher.match_entity."""
        entity_mock = MagicMock()
        entity_mock.id = _ENTITY_ID
        mock_session.get = AsyncMock(return_value=entity_mock)

        mock_instance = MagicMock()
        mock_instance.match_entity = AsyncMock(return_value=[])
        mock_matcher_cls.return_value = mock_instance

        await client.get(self._url(), params={"threshold": 0.8})

        mock_instance.match_entity.assert_awaited_once()
        call_kwargs = mock_instance.match_entity.call_args.kwargs
        assert call_kwargs["threshold"] == 0.8

    @patch(
        "chronovista.api.routers.entity_mentions.PhoneticMatcher",
    )
    async def test_video_title_missing_for_some_videos(
        self,
        mock_matcher_cls: MagicMock,
        client: AsyncClient,
        mock_session: AsyncMock,
    ) -> None:
        """Matches with no corresponding video entry get null video_title."""
        entity_mock = MagicMock()
        entity_mock.id = _ENTITY_ID
        mock_session.get = AsyncMock(return_value=entity_mock)

        matches = [
            _make_match(video_id="vid1"),
            _make_match(video_id="vid_unknown", segment_id=99),
        ]
        mock_instance = MagicMock()
        mock_instance.match_entity = AsyncMock(return_value=matches)
        mock_matcher_cls.return_value = mock_instance

        # Only vid1 has a title
        video_row = MagicMock()
        video_row.video_id = "vid1"
        video_row.title = "Known Video"
        execute_result = MagicMock()
        execute_result.all.return_value = [video_row]
        mock_session.execute = AsyncMock(return_value=execute_result)

        response = await client.get(self._url())

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["video_title"] == "Known Video"
        assert data[1]["video_title"] is None
