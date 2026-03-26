"""Integration tests for Feature 052 targeted scan API endpoints.

Covers:
  - POST /api/v1/entities/{entity_id}/scan
  - POST /api/v1/videos/{video_id}/scan-entities

All tests use an integration database seeded with minimal rows (channel,
video, and named entity). The scan service itself is mocked via
``unittest.mock.patch`` so tests do not perform real transcript scanning —
they validate the request-routing, entity/video validation, concurrency
guard, and response structure only.

Auth: ``require_auth`` is bypassed via ``youtube_oauth`` mock following the
same pattern used in ``test_entity_mentions_api.py``.

Feature 052 — Targeted Entity & Video-Level Mention Scanning
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from chronovista.db.models import (
    Channel as ChannelDB,
    NamedEntity as NamedEntityDB,
    Video as VideoDB,
)
from chronovista.services.entity_mention_scan_service import ScanResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

# CRITICAL: Module-level asyncio marker ensures async tests run with coverage.
pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Stable IDs — must not collide with other integration test files.
# channel_id max 24 chars, video_id max 20 chars.
# ---------------------------------------------------------------------------
_CHANNEL_ID = "UCscan052_test000001"  # 20 chars
_VIDEO_ID = "scan052_vid001"  # 14 chars


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _entity_scan_url(entity_id: str | uuid.UUID) -> str:
    """Return the entity-specific scan endpoint URL."""
    return f"/api/v1/entities/{entity_id}/scan"


def _video_scan_url(video_id: str) -> str:
    """Return the video entity-scan endpoint URL."""
    return f"/api/v1/videos/{video_id}/scan-entities"


# ---------------------------------------------------------------------------
# Shared mock scan result
# ---------------------------------------------------------------------------


def _make_scan_result(
    segments_scanned: int = 10,
    mentions_found: int = 2,
    mentions_skipped: int = 0,
    unique_entities: int = 1,
    unique_videos: int = 1,
    duration_seconds: float = 0.5,
    dry_run: bool = False,
) -> ScanResult:
    """Build a ScanResult with configurable stats."""
    result = ScanResult(
        segments_scanned=segments_scanned,
        mentions_found=mentions_found,
        mentions_skipped=mentions_skipped,
        unique_entities=unique_entities,
        unique_videos=unique_videos,
        duration_seconds=duration_seconds,
        dry_run=dry_run,
    )
    return result


# ---------------------------------------------------------------------------
# Seed fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def seed_scan_data(
    integration_session_factory: "async_sessionmaker[AsyncSession]",
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed a channel, video, and named entity for scan endpoint tests.

    Yields a dict with stable IDs:
    - ``entity_id``  — UUID of the seeded active NamedEntity
    - ``entity_id_str`` — string form of entity_id
    - ``video_id``   — string video ID
    - ``inactive_entity_id`` — UUID of a merged (inactive) entity
    - ``inactive_entity_id_str`` — string form of inactive_entity_id

    Cleanup removes all seeded rows in FK-reverse order after each test.
    """
    entity_uuid = uuid.uuid4()
    inactive_entity_uuid = uuid.uuid4()

    async with integration_session_factory() as session:
        # ---- Channel -------------------------------------------------------
        existing_channel = (
            await session.execute(
                select(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
            )
        ).scalar_one_or_none()
        if not existing_channel:
            channel = ChannelDB(
                channel_id=_CHANNEL_ID,
                title="Scan 052 Test Channel",
            )
            session.add(channel)

        # ---- Video ---------------------------------------------------------
        existing_video = (
            await session.execute(
                select(VideoDB).where(VideoDB.video_id == _VIDEO_ID)
            )
        ).scalar_one_or_none()
        if not existing_video:
            video = VideoDB(
                video_id=_VIDEO_ID,
                channel_id=_CHANNEL_ID,
                title="Scan 052 Test Video",
                description="Integration test video for Feature 052",
                upload_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
                duration=300,
            )
            session.add(video)

        await session.commit()

        # ---- Active NamedEntity --------------------------------------------
        existing_entity = (
            await session.execute(
                select(NamedEntityDB).where(NamedEntityDB.id == entity_uuid)
            )
        ).scalar_one_or_none()
        if not existing_entity:
            entity = NamedEntityDB(
                id=entity_uuid,
                canonical_name="Test Person 052",
                canonical_name_normalized="test person 052",
                entity_type="person",
                status="active",
            )
            session.add(entity)

        # ---- Inactive (merged) NamedEntity ---------------------------------
        existing_inactive = (
            await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.id == inactive_entity_uuid
                )
            )
        ).scalar_one_or_none()
        if not existing_inactive:
            inactive_entity = NamedEntityDB(
                id=inactive_entity_uuid,
                canonical_name="Merged Entity 052",
                canonical_name_normalized="merged entity 052",
                entity_type="organization",
                status="merged",
            )
            session.add(inactive_entity)

        await session.commit()

    yield {
        "entity_id": entity_uuid,
        "entity_id_str": str(entity_uuid),
        "video_id": _VIDEO_ID,
        "inactive_entity_id": inactive_entity_uuid,
        "inactive_entity_id_str": str(inactive_entity_uuid),
    }

    # ---- Cleanup in FK-reverse order ---------------------------------------
    async with integration_session_factory() as session:
        await session.execute(
            delete(NamedEntityDB).where(
                NamedEntityDB.id.in_([entity_uuid, inactive_entity_uuid])
            )
        )
        await session.execute(
            delete(VideoDB).where(VideoDB.video_id == _VIDEO_ID)
        )
        await session.execute(
            delete(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# TestEntityScanEndpoint
# ---------------------------------------------------------------------------


class TestEntityScanEndpoint:
    """Tests for POST /api/v1/entities/{entity_id}/scan."""

    # ------------------------------------------------------------------
    # 200 success
    # ------------------------------------------------------------------

    async def test_entity_scan_returns_200_with_valid_active_entity(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """200 response with ScanResultResponse envelope for a valid active entity.

        The scan service is mocked so no real scanning occurs.
        """
        entity_id_str = seed_scan_data["entity_id_str"]
        mock_result = _make_scan_result(mentions_found=3, unique_entities=1)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            response = await async_client.post(_entity_scan_url(entity_id_str))

        assert response.status_code == 200, response.text
        body = response.json()

        # Verify response envelope structure
        assert "data" in body
        data = body["data"]
        assert data["segments_scanned"] == mock_result.segments_scanned
        assert data["mentions_found"] == mock_result.mentions_found
        assert data["unique_entities"] == mock_result.unique_entities
        assert data["unique_videos"] == mock_result.unique_videos
        assert data["dry_run"] is False

    async def test_entity_scan_200_with_empty_body(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """POST with empty JSON body ``{}`` must use defaults and succeed."""
        entity_id_str = seed_scan_data["entity_id_str"]
        mock_result = _make_scan_result()

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            response = await async_client.post(
                _entity_scan_url(entity_id_str), json={}
            )

        assert response.status_code == 200, response.text

    async def test_entity_scan_calls_service_with_entity_id(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """Service.scan() must be called with entity_ids=[entity_id]."""
        entity_uuid = seed_scan_data["entity_id"]
        entity_id_str = seed_scan_data["entity_id_str"]
        mock_result = _make_scan_result()

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            await async_client.post(_entity_scan_url(entity_id_str))

        call_kwargs = mock_service.scan.call_args
        assert call_kwargs is not None
        # entity_ids must include the entity UUID
        entity_ids_arg = call_kwargs.kwargs.get(
            "entity_ids", call_kwargs.args[0] if call_kwargs.args else None
        )
        assert entity_ids_arg == [entity_uuid]

    async def test_entity_scan_passes_language_code_from_body(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """language_code from the request body is forwarded to scan()."""
        entity_id_str = seed_scan_data["entity_id_str"]
        mock_result = _make_scan_result()

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            await async_client.post(
                _entity_scan_url(entity_id_str),
                json={"language_code": "en"},
            )

        call_kwargs = mock_service.scan.call_args
        assert call_kwargs is not None
        lang = call_kwargs.kwargs.get("language_code")
        assert lang == "en"

    async def test_entity_scan_passes_dry_run_from_body(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """dry_run=True from the request body is forwarded to scan()."""
        entity_id_str = seed_scan_data["entity_id_str"]
        mock_result = _make_scan_result(dry_run=True)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            await async_client.post(
                _entity_scan_url(entity_id_str),
                json={"dry_run": True},
            )

        call_kwargs = mock_service.scan.call_args
        assert call_kwargs is not None
        dry_run_arg = call_kwargs.kwargs.get("dry_run")
        assert dry_run_arg is True

    # ------------------------------------------------------------------
    # 404 entity not found
    # ------------------------------------------------------------------

    async def test_entity_scan_404_when_entity_not_found(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """404 when the entity_id UUID does not exist in the database."""
        non_existent_uuid = uuid.uuid4()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _entity_scan_url(non_existent_uuid)
            )

        assert response.status_code == 404, response.text

    # ------------------------------------------------------------------
    # 400 entity not active
    # ------------------------------------------------------------------

    async def test_entity_scan_400_when_entity_is_merged(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """400 when the entity exists but has status 'merged' (not active)."""
        inactive_id_str = seed_scan_data["inactive_entity_id_str"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _entity_scan_url(inactive_id_str)
            )

        assert response.status_code == 400, response.text
        body = response.json()
        # Error detail must mention the status
        detail = response.text.lower()
        assert "active" in detail or "status" in detail

    # ------------------------------------------------------------------
    # 409 concurrency guard
    # ------------------------------------------------------------------

    async def test_entity_scan_409_when_scan_already_in_progress(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """409 when the concurrency guard already holds the key for this entity."""
        import chronovista.api.routers.entity_mentions as em_router

        entity_uuid = seed_scan_data["entity_id"]
        entity_id_str = seed_scan_data["entity_id_str"]
        guard_key = f"scan:entity:{entity_uuid}"

        # Manually insert the guard key to simulate an in-progress scan
        em_router._scans_in_progress.add(guard_key)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.post(
                    _entity_scan_url(entity_id_str)
                )
        finally:
            em_router._scans_in_progress.discard(guard_key)

        assert response.status_code == 409, response.text

    async def test_entity_scan_guard_released_after_successful_scan(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """The concurrency guard must be removed after a successful scan."""
        import chronovista.api.routers.entity_mentions as em_router

        entity_uuid = seed_scan_data["entity_id"]
        entity_id_str = seed_scan_data["entity_id_str"]
        guard_key = f"scan:entity:{entity_uuid}"

        mock_result = _make_scan_result()

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            await async_client.post(_entity_scan_url(entity_id_str))

        # Guard must be released
        assert guard_key not in em_router._scans_in_progress, (
            f"Guard key {guard_key!r} still present after scan completion"
        )

    async def test_entity_scan_guard_released_after_service_exception(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """The concurrency guard must be released even when scan() raises.

        FastAPI's exception handler will convert the RuntimeError to a 500
        response. The important thing is that the guard key is not left in
        ``_scans_in_progress`` regardless of the response status.
        """
        import chronovista.api.routers.entity_mentions as em_router

        entity_uuid = seed_scan_data["entity_id"]
        entity_id_str = seed_scan_data["entity_id_str"]
        guard_key = f"scan:entity:{entity_uuid}"

        # Make sure the guard is not set before we start
        em_router._scans_in_progress.discard(guard_key)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(side_effect=RuntimeError("scan failed"))
            mock_get_service.return_value = mock_service

            # The 500 response is expected; we only care that the guard is cleaned up
            try:
                await async_client.post(_entity_scan_url(entity_id_str))
            except Exception:
                pass  # 500 responses may propagate in test mode

        assert guard_key not in em_router._scans_in_progress, (
            f"Guard key {guard_key!r} still present after scan failure"
        )


# ---------------------------------------------------------------------------
# TestVideoScanEndpoint
# ---------------------------------------------------------------------------


class TestVideoScanEndpoint:
    """Tests for POST /api/v1/videos/{video_id}/scan-entities."""

    # ------------------------------------------------------------------
    # 200 success
    # ------------------------------------------------------------------

    async def test_video_scan_returns_200_with_valid_video(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """200 response with ScanResultResponse envelope for a valid video."""
        video_id = seed_scan_data["video_id"]
        mock_result = _make_scan_result(
            segments_scanned=5,
            mentions_found=1,
            unique_entities=1,
            unique_videos=1,
        )

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            response = await async_client.post(_video_scan_url(video_id))

        assert response.status_code == 200, response.text
        body = response.json()

        assert "data" in body
        data = body["data"]
        assert data["segments_scanned"] == 5
        assert data["mentions_found"] == 1

    async def test_video_scan_200_with_zero_counts(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """200 response with all-zero counts when video has no matching segments."""
        video_id = seed_scan_data["video_id"]
        mock_result = _make_scan_result(
            segments_scanned=0,
            mentions_found=0,
            mentions_skipped=0,
            unique_entities=0,
            unique_videos=0,
        )

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            response = await async_client.post(_video_scan_url(video_id))

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["mentions_found"] == 0
        assert data["unique_entities"] == 0

    async def test_video_scan_calls_service_with_video_id(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """Service.scan() must be called with video_ids=[video_id]."""
        video_id = seed_scan_data["video_id"]
        mock_result = _make_scan_result()

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            await async_client.post(_video_scan_url(video_id))

        call_kwargs = mock_service.scan.call_args
        assert call_kwargs is not None
        video_ids_arg = call_kwargs.kwargs.get("video_ids")
        assert video_ids_arg == [video_id]

    async def test_video_scan_passes_entity_type_from_body(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """entity_type from the request body is forwarded to scan()."""
        video_id = seed_scan_data["video_id"]
        mock_result = _make_scan_result()

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            await async_client.post(
                _video_scan_url(video_id),
                json={"entity_type": "person"},
            )

        call_kwargs = mock_service.scan.call_args
        assert call_kwargs is not None
        entity_type_arg = call_kwargs.kwargs.get("entity_type")
        assert entity_type_arg == "person"

    async def test_video_scan_200_with_empty_body(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """POST with empty body ``{}`` must use defaults and succeed."""
        video_id = seed_scan_data["video_id"]
        mock_result = _make_scan_result()

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            response = await async_client.post(
                _video_scan_url(video_id), json={}
            )

        assert response.status_code == 200, response.text

    # ------------------------------------------------------------------
    # 404 video not found
    # ------------------------------------------------------------------

    async def test_video_scan_404_when_video_not_found(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """404 when the video_id does not exist in the database."""
        non_existent_video_id = "nosuchvideo052"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _video_scan_url(non_existent_video_id)
            )

        assert response.status_code == 404, response.text

    # ------------------------------------------------------------------
    # 409 concurrency guard
    # ------------------------------------------------------------------

    async def test_video_scan_409_when_scan_already_in_progress(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """409 when the concurrency guard already holds the key for this video."""
        import chronovista.api.routers.entity_mentions as em_router

        video_id = seed_scan_data["video_id"]
        guard_key = f"scan:video:{video_id}"

        em_router._scans_in_progress.add(guard_key)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.post(_video_scan_url(video_id))
        finally:
            em_router._scans_in_progress.discard(guard_key)

        assert response.status_code == 409, response.text

    async def test_video_scan_guard_released_after_successful_scan(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """The concurrency guard must be removed after a successful video scan."""
        import chronovista.api.routers.entity_mentions as em_router

        video_id = seed_scan_data["video_id"]
        guard_key = f"scan:video:{video_id}"
        mock_result = _make_scan_result()

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            await async_client.post(_video_scan_url(video_id))

        assert guard_key not in em_router._scans_in_progress, (
            f"Guard key {guard_key!r} still present after scan completion"
        )

    async def test_video_scan_guard_released_after_service_exception(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """The concurrency guard must be released even when scan() raises.

        FastAPI converts the RuntimeError to a 500 response.  The guard
        key must be absent from ``_scans_in_progress`` after the request
        completes, regardless of the response status code.
        """
        import chronovista.api.routers.entity_mentions as em_router

        video_id = seed_scan_data["video_id"]
        guard_key = f"scan:video:{video_id}"

        # Ensure guard is clean before test
        em_router._scans_in_progress.discard(guard_key)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(
                side_effect=RuntimeError("scan exploded")
            )
            mock_get_service.return_value = mock_service

            try:
                await async_client.post(_video_scan_url(video_id))
            except Exception:
                pass  # 500 responses may propagate in test mode

        assert guard_key not in em_router._scans_in_progress, (
            f"Guard key {guard_key!r} still present after scan failure"
        )

    # ------------------------------------------------------------------
    # Response shape validation
    # ------------------------------------------------------------------

    async def test_video_scan_response_has_all_required_fields(
        self,
        async_client: AsyncClient,
        seed_scan_data: dict[str, Any],
    ) -> None:
        """The response body must contain all ScanResultData fields."""
        video_id = seed_scan_data["video_id"]
        mock_result = _make_scan_result(
            segments_scanned=20,
            mentions_found=4,
            mentions_skipped=1,
            unique_entities=2,
            unique_videos=1,
            duration_seconds=1.5,
        )

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.entity_mentions._get_scan_service"
            ) as mock_get_service,
        ):
            mock_oauth.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_service.scan = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            response = await async_client.post(_video_scan_url(video_id))

        assert response.status_code == 200, response.text
        data = response.json()["data"]

        required_fields = {
            "segments_scanned",
            "mentions_found",
            "mentions_skipped",
            "unique_entities",
            "unique_videos",
            "duration_seconds",
            "dry_run",
        }
        for field in required_fields:
            assert field in data, f"Missing required field '{field}' in response data"
