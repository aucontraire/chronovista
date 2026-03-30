"""Unit tests for scan endpoint ``sources`` parameter (Phase 6 — US3b)
and entity videos source filter (Phase 8 — US5).

Tests T037–T040 verify that the ``sources`` parameter on both scan
endpoints dispatches to the correct service methods and validates input.

Tests T062 verifies that ``GET /entities/{id}/videos?source=title`` returns
only title-sourced videos.

Mock strategy
-------------
- ``_get_scan_service`` is patched to return a mock scan service
- ``session.get`` is patched to simulate entity/video existence
- ``get_db`` and ``require_auth`` FastAPI dependencies are overridden
- ``EntityMentionRepository.get_entity_video_list`` is patched for T062

References
----------
- specs/054-multi-source-mentions/tasks.md — T037–T040, T062
- specs/054-multi-source-mentions/spec.md — FR-026, FR-027, FR-031, FR-036
- specs/054-multi-source-mentions/contracts/entity-videos-endpoint.md
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app
from chronovista.services.entity_mention_scan_service import ScanResult
from tests.factories import id_factory

# ---------------------------------------------------------------------------
# Module-level asyncio marker (coverage integration)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid() -> uuid.UUID:
    """Return a UUIDv7 expressed as a stdlib ``uuid.UUID`` instance."""
    return uuid.UUID(bytes=uuid7().bytes)


def _empty_scan_result(*, dry_run: bool = False) -> ScanResult:
    """Return a zeroed-out :class:`ScanResult` for mock returns."""
    return ScanResult(dry_run=dry_run)


async def _build_client(
    mock_session: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Yield an AsyncClient with ``get_db`` and ``require_auth`` overridden.

    Parameters
    ----------
    mock_session : AsyncMock
        The mock database session to inject via the ``get_db`` override.

    Yields
    ------
    AsyncClient
        A configured HTTP test client with overridden dependencies.
    """

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def mock_require_auth() -> None:
        return None

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[require_auth] = mock_require_auth

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _make_entity_session(entity_id: uuid.UUID) -> AsyncMock:
    """Build a mock session where ``session.get(NamedEntityDB, ...)`` succeeds.

    Parameters
    ----------
    entity_id : uuid.UUID
        Entity UUID that should pass the existence check.

    Returns
    -------
    AsyncMock
        Configured mock session.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    # session.get(NamedEntityDB, entity_id) returns a mock entity
    @dataclass
    class _FakeEntity:
        id: uuid.UUID
        status: str = "active"

    mock_session.get = AsyncMock(return_value=_FakeEntity(id=entity_id))
    mock_session.commit = AsyncMock()
    return mock_session


def _make_video_session(video_id: str) -> AsyncMock:
    """Build a mock session where ``session.get(VideoDB, ...)`` succeeds.

    Parameters
    ----------
    video_id : str
        Video ID that should pass the existence check.

    Returns
    -------
    AsyncMock
        Configured mock session.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    video_mock = MagicMock()
    video_mock.video_id = video_id
    mock_session.get = AsyncMock(return_value=video_mock)
    mock_session.commit = AsyncMock()
    return mock_session


# ---------------------------------------------------------------------------
# T037 — POST /entities/{id}/scan with sources=["title"] calls scan_metadata
# ---------------------------------------------------------------------------


class TestScanEntitySourcesParameter:
    """Tests for the ``sources`` parameter on POST /entities/{id}/scan."""

    async def test_sources_title_calls_scan_metadata(self) -> None:
        """T037: sources=["title"] dispatches to scan_metadata(), not scan().

        When the request body includes ``sources: ["title"]``, the endpoint
        should call ``scan_metadata(sources=["title"])`` and NOT call
        ``scan()``.
        """
        entity_id = _uuid()
        mock_session = _make_entity_session(entity_id)

        mock_service = MagicMock()
        mock_service.scan = AsyncMock(return_value=_empty_scan_result())
        mock_service.scan_metadata = AsyncMock(
            return_value=_empty_scan_result()
        )

        with patch(
            "chronovista.api.routers.entity_mentions._get_scan_service",
            return_value=mock_service,
        ):
            async for client in _build_client(mock_session):
                response = await client.post(
                    f"/api/v1/entities/{entity_id}/scan",
                    json={"sources": ["title"]},
                )

        assert response.status_code == 200
        mock_service.scan.assert_not_called()
        mock_service.scan_metadata.assert_called_once()
        call_kwargs = mock_service.scan_metadata.call_args.kwargs
        assert call_kwargs["sources"] == ["title"]

    # -------------------------------------------------------------------
    # T038 — No sources defaults to transcript-only (backward compatible)
    # -------------------------------------------------------------------

    async def test_no_sources_defaults_to_transcript_only(self) -> None:
        """T038: Omitting sources calls scan() only (backward compatible).

        When the request body does not include ``sources``, the endpoint
        should default to ``["transcript"]`` and call only ``scan()``,
        preserving existing behavior.
        """
        entity_id = _uuid()
        mock_session = _make_entity_session(entity_id)

        mock_service = MagicMock()
        mock_service.scan = AsyncMock(return_value=_empty_scan_result())
        mock_service.scan_metadata = AsyncMock(
            return_value=_empty_scan_result()
        )

        with patch(
            "chronovista.api.routers.entity_mentions._get_scan_service",
            return_value=mock_service,
        ):
            async for client in _build_client(mock_session):
                response = await client.post(
                    f"/api/v1/entities/{entity_id}/scan",
                    json={},
                )

        assert response.status_code == 200
        mock_service.scan.assert_called_once()
        mock_service.scan_metadata.assert_not_called()

    # -------------------------------------------------------------------
    # T039 — sources=["tag"] returns 422 with RFC 7807 error
    # -------------------------------------------------------------------

    async def test_sources_tag_returns_422(self) -> None:
        """T039: sources=["tag"] is rejected with HTTP 422.

        The ``tag`` value is explicitly invalid for scan sources because
        tag associations are query-time (Feature 053), not scan-persisted.
        The response body should follow RFC 7807 format.
        """
        entity_id = _uuid()
        mock_session = _make_entity_session(entity_id)

        async for client in _build_client(mock_session):
            response = await client.post(
                f"/api/v1/entities/{entity_id}/scan",
                json={"sources": ["tag"]},
            )

        assert response.status_code == 422
        body = response.json()
        # RFC 7807 requires a detail field
        assert "detail" in body


# ---------------------------------------------------------------------------
# T040 — POST /videos/{id}/scan-entities with sources=title+description
# ---------------------------------------------------------------------------


class TestScanVideoEntitiesSourcesParameter:
    """Tests for the ``sources`` parameter on POST /videos/{id}/scan-entities."""

    async def test_sources_title_description_calls_scan_metadata(
        self,
    ) -> None:
        """T040: sources=["title","description"] dispatches to scan_metadata().

        When the request body includes both ``title`` and ``description``
        sources (but not ``transcript``), the endpoint should call
        ``scan_metadata()`` and NOT call ``scan()``.
        """
        video_id = id_factory.video_id(seed="scan_sources_test")
        mock_session = _make_video_session(video_id)

        mock_service = MagicMock()
        mock_service.scan = AsyncMock(return_value=_empty_scan_result())
        mock_service.scan_metadata = AsyncMock(
            return_value=_empty_scan_result()
        )

        with patch(
            "chronovista.api.routers.entity_mentions._get_scan_service",
            return_value=mock_service,
        ):
            async for client in _build_client(mock_session):
                response = await client.post(
                    f"/api/v1/videos/{video_id}/scan-entities",
                    json={"sources": ["title", "description"]},
                )

        assert response.status_code == 200
        mock_service.scan.assert_not_called()
        mock_service.scan_metadata.assert_called_once()
        call_kwargs = mock_service.scan_metadata.call_args.kwargs
        assert sorted(call_kwargs["sources"]) == ["description", "title"]

    async def test_all_sources_calls_both_scan_and_scan_metadata(
        self,
    ) -> None:
        """All three sources dispatches to both scan() and scan_metadata().

        When ``sources: ["transcript", "title", "description"]``, both
        ``scan()`` and ``scan_metadata()`` should be called, and the
        results merged.
        """
        video_id = id_factory.video_id(seed="scan_all_sources")
        mock_session = _make_video_session(video_id)

        transcript_result = ScanResult(
            segments_scanned=100,
            mentions_found=5,
            mentions_skipped=2,
            unique_entities=3,
            unique_videos=1,
            duration_seconds=1.5,
        )
        metadata_result = ScanResult(
            segments_scanned=50,
            mentions_found=3,
            mentions_skipped=1,
            unique_entities=2,
            unique_videos=1,
            duration_seconds=0.5,
        )

        mock_service = MagicMock()
        mock_service.scan = AsyncMock(return_value=transcript_result)
        mock_service.scan_metadata = AsyncMock(return_value=metadata_result)

        with patch(
            "chronovista.api.routers.entity_mentions._get_scan_service",
            return_value=mock_service,
        ):
            async for client in _build_client(mock_session):
                response = await client.post(
                    f"/api/v1/videos/{video_id}/scan-entities",
                    json={
                        "sources": ["transcript", "title", "description"],
                    },
                )

        assert response.status_code == 200
        mock_service.scan.assert_called_once()
        mock_service.scan_metadata.assert_called_once()

        body = response.json()
        data = body["data"]
        # Merged numeric fields
        assert data["segments_scanned"] == 150
        assert data["mentions_found"] == 8
        assert data["mentions_skipped"] == 3
        assert data["unique_entities"] == 5
        assert data["unique_videos"] == 2
        assert data["duration_seconds"] == pytest.approx(2.0)

    async def test_sources_tag_on_video_endpoint_returns_422(self) -> None:
        """Invalid source 'tag' on video scan endpoint returns 422."""
        video_id = id_factory.video_id(seed="scan_tag_invalid")
        mock_session = _make_video_session(video_id)

        async for client in _build_client(mock_session):
            response = await client.post(
                f"/api/v1/videos/{video_id}/scan-entities",
                json={"sources": ["tag"]},
            )

        assert response.status_code == 422

    async def test_sources_unknown_value_returns_422(self) -> None:
        """Unknown source value returns 422."""
        video_id = id_factory.video_id(seed="scan_unknown_source")
        mock_session = _make_video_session(video_id)

        async for client in _build_client(mock_session):
            response = await client.post(
                f"/api/v1/videos/{video_id}/scan-entities",
                json={"sources": ["foobar"]},
            )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# T062 — GET /entities/{id}/videos?source=title returns filtered results
# ---------------------------------------------------------------------------


class TestGetEntityVideosSourceFilter:
    """Tests for the ``source`` query parameter on GET /entities/{id}/videos.

    T062: ``GET /entities/{id}/videos?source=title`` returns only
    title-sourced videos (the repository filter is applied).
    """

    async def test_source_title_returns_only_title_sourced_videos(
        self,
    ) -> None:
        """T062: GET /entities/{id}/videos?source=title returns title-only results.

        When ``source=title`` is supplied, the endpoint must pass
        ``source_filter="title"`` to the repository and only return videos
        whose ``sources`` list contains ``"title"``.
        """
        entity_id = _uuid()
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock existence check
        @dataclass
        class _FakeEntity:
            id: uuid.UUID
            status: str = "active"

        mock_session.execute = AsyncMock()
        # First execute call → entity existence check (returns scalar)
        entity_scalar = MagicMock()
        entity_scalar.scalar_one_or_none = MagicMock(return_value=entity_id)
        mock_session.execute.return_value = entity_scalar

        # Repository returns a title-sourced video result
        title_video = {
            "video_id": "vid-001",
            "video_title": "David Sheen Documentary",
            "channel_name": "Test Channel",
            "mention_count": 0,
            "mentions": [],
            "sources": ["title"],
            "has_manual": False,
            "first_mention_time": None,
            "upload_date": None,
            "description_context": None,
        }

        with patch(
            "chronovista.repositories.entity_mention_repository"
            ".EntityMentionRepository.get_entity_video_list",
            new_callable=AsyncMock,
            return_value=([title_video], 1),
        ) as mock_repo:
            async for client in _build_client(mock_session):
                response = await client.get(
                    f"/api/v1/entities/{entity_id}/videos?source=title"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["pagination"]["total"] == 1
        assert len(body["data"]) == 1
        assert body["data"][0]["sources"] == ["title"]

        # Verify the repository was called with source_filter="title"
        mock_repo.assert_called_once()
        call_kwargs = mock_repo.call_args.kwargs
        assert call_kwargs.get("source_filter") == "title"

    async def test_no_source_returns_all_videos(self) -> None:
        """GET /entities/{id}/videos without source returns all videos.

        When no ``source`` parameter is supplied, ``source_filter=None``
        is passed to the repository and all videos are returned.
        """
        entity_id = _uuid()
        mock_session = AsyncMock(spec=AsyncSession)

        entity_scalar = MagicMock()
        entity_scalar.scalar_one_or_none = MagicMock(return_value=entity_id)
        mock_session.execute = AsyncMock(return_value=entity_scalar)

        all_videos = [
            {
                "video_id": f"vid-{i:03d}",
                "video_title": f"Video {i}",
                "channel_name": "Channel",
                "mention_count": 1,
                "mentions": [],
                "sources": ["transcript"],
                "has_manual": False,
                "first_mention_time": None,
                "upload_date": None,
                "description_context": None,
            }
            for i in range(3)
        ]

        with patch(
            "chronovista.repositories.entity_mention_repository"
            ".EntityMentionRepository.get_entity_video_list",
            new_callable=AsyncMock,
            return_value=(all_videos, 3),
        ) as mock_repo:
            async for client in _build_client(mock_session):
                response = await client.get(
                    f"/api/v1/entities/{entity_id}/videos"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["pagination"]["total"] == 3

        # Verify source_filter is None when not supplied
        call_kwargs = mock_repo.call_args.kwargs
        assert call_kwargs.get("source_filter") is None

    async def test_invalid_source_value_returns_422(self) -> None:
        """GET /entities/{id}/videos?source=foobar returns 422.

        Invalid source values should be rejected by the endpoint before
        reaching the repository.
        """
        entity_id = _uuid()
        mock_session = AsyncMock(spec=AsyncSession)

        entity_scalar = MagicMock()
        entity_scalar.scalar_one_or_none = MagicMock(return_value=entity_id)
        mock_session.execute = AsyncMock(return_value=entity_scalar)

        async for client in _build_client(mock_session):
            response = await client.get(
                f"/api/v1/entities/{entity_id}/videos?source=foobar"
            )

        assert response.status_code == 422
