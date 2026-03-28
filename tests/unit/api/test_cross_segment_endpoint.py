"""
Unit tests for GET /api/v1/corrections/batch/cross-segment/candidates endpoint.

Tests the cross-segment candidates endpoint in:
  src/chronovista/api/routers/batch_corrections.py

Mounted at: /api/v1/corrections/batch

Scenarios covered:
- 200 with candidates mapped to response schema
- 200 with empty results
- Query parameter forwarding (min_corrections, entity_name)
- Query parameter validation (min_corrections bounds)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app
from chronovista.services.cross_segment_discovery import CrossSegmentCandidate

# CRITICAL: This line ensures async tests work with coverage

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_candidate(
    *,
    segment_n_id: int = 100,
    segment_n_text: str = "end of seg",
    segment_n1_id: int = 101,
    segment_n1_text: str = "ment text",
    proposed_correction: str = "segment",
    source_pattern: str = "seg ment",
    confidence: float = 0.85,
    is_partially_corrected: bool = False,
    video_id: str = "abc123",
) -> CrossSegmentCandidate:
    """Build a CrossSegmentCandidate with optional overrides."""
    return CrossSegmentCandidate(
        segment_n_id=segment_n_id,
        segment_n_text=segment_n_text,
        segment_n1_id=segment_n1_id,
        segment_n1_text=segment_n1_text,
        proposed_correction=proposed_correction,
        source_pattern=source_pattern,
        confidence=confidence,
        is_partially_corrected=is_partially_corrected,
        video_id=video_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


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
# GET /api/v1/corrections/batch/cross-segment/candidates
# ═══════════════════════════════════════════════════════════════════════════


class TestGetCrossSegmentCandidates:
    """Tests for GET /api/v1/corrections/batch/cross-segment/candidates."""

    BASE_URL = "/api/v1/corrections/batch/cross-segment/candidates"

    @patch(
        "chronovista.api.routers.batch_corrections.CrossSegmentDiscovery",
    )
    async def test_returns_200_with_candidates(
        self,
        mock_discovery_cls: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Endpoint returns 200 with candidates mapped to response schema."""
        candidate = _make_candidate()
        mock_instance = MagicMock()
        mock_instance.discover = AsyncMock(return_value=[candidate])
        mock_discovery_cls.return_value = mock_instance

        response = await client.get(self.BASE_URL)

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert len(data) == 1
        assert data[0]["segment_n_id"] == 100
        assert data[0]["segment_n_text"] == "end of seg"
        assert data[0]["segment_n1_id"] == 101
        assert data[0]["segment_n1_text"] == "ment text"
        assert data[0]["proposed_correction"] == "segment"
        assert data[0]["source_pattern"] == "seg ment"
        assert data[0]["confidence"] == 0.85
        assert data[0]["is_partially_corrected"] is False
        assert data[0]["video_id"] == "abc123"

    @patch(
        "chronovista.api.routers.batch_corrections.CrossSegmentDiscovery",
    )
    async def test_returns_200_empty_results(
        self,
        mock_discovery_cls: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Endpoint returns 200 with empty list when no candidates found."""
        mock_instance = MagicMock()
        mock_instance.discover = AsyncMock(return_value=[])
        mock_discovery_cls.return_value = mock_instance

        response = await client.get(self.BASE_URL)

        assert response.status_code == 200
        assert response.json()["data"] == []

    @patch(
        "chronovista.api.routers.batch_corrections.CrossSegmentDiscovery",
    )
    async def test_passes_query_params(
        self,
        mock_discovery_cls: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Query params are forwarded to CrossSegmentDiscovery.discover."""
        mock_instance = MagicMock()
        mock_instance.discover = AsyncMock(return_value=[])
        mock_discovery_cls.return_value = mock_instance

        await client.get(
            self.BASE_URL,
            params={"min_corrections": 5, "entity_name": "Sheinbaum"},
        )

        mock_instance.discover.assert_awaited_once()
        call_kwargs = mock_instance.discover.call_args.kwargs
        assert call_kwargs["min_corrections"] == 5
        assert call_kwargs["entity_name"] == "Sheinbaum"

    async def test_min_corrections_below_minimum(
        self,
        client: AsyncClient,
    ) -> None:
        """min_corrections=0 returns 422."""
        response = await client.get(
            self.BASE_URL, params={"min_corrections": 0}
        )
        assert response.status_code == 422

    async def test_min_corrections_above_maximum(
        self,
        client: AsyncClient,
    ) -> None:
        """min_corrections=21 returns 422."""
        response = await client.get(
            self.BASE_URL, params={"min_corrections": 21}
        )
        assert response.status_code == 422

    @patch(
        "chronovista.api.routers.batch_corrections.CrossSegmentDiscovery",
    )
    async def test_multiple_candidates(
        self,
        mock_discovery_cls: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Endpoint correctly maps multiple candidates."""
        candidates = [
            _make_candidate(segment_n_id=1, video_id="vid1"),
            _make_candidate(segment_n_id=2, video_id="vid2"),
        ]
        mock_instance = MagicMock()
        mock_instance.discover = AsyncMock(return_value=candidates)
        mock_discovery_cls.return_value = mock_instance

        response = await client.get(self.BASE_URL)

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["video_id"] == "vid1"
        assert data[1]["video_id"] == "vid2"
