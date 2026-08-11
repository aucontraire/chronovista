"""
Unit tests for settings and preferences API endpoints.

Tests all four settings endpoints including supported languages,
cache status and management, and application info.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app
from chronovista.api.schemas.sync import SyncOperationType
from chronovista.models.enums import LanguageCode
from chronovista.services.image_cache import CacheStats

# CRITICAL: This line ensures async tests work with coverage

# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for FastAPI testing with auth and DB overrides."""

    mock_session = AsyncMock(spec=AsyncSession)

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


@pytest.fixture
async def async_client_no_auth() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client WITHOUT auth override to test 401 responses."""

    mock_session = AsyncMock(spec=AsyncSession)

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    # Only override DB, NOT require_auth
    app.dependency_overrides[get_db] = mock_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# GET /settings/supported-languages Tests (no auth required)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetSupportedLanguages:
    """Tests for GET /api/v1/settings/supported-languages endpoint."""

    async def test_returns_200_with_api_response_envelope(
        self, async_client: AsyncClient
    ) -> None:
        """Test endpoint returns 200 with data wrapped in ApiResponse envelope."""
        response = await async_client.get("/api/v1/settings/supported-languages")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert isinstance(body["data"], list)

    async def test_returns_all_language_codes(self, async_client: AsyncClient) -> None:
        """Test returned language count matches the LanguageCode enum member count."""
        response = await async_client.get("/api/v1/settings/supported-languages")

        assert response.status_code == 200
        languages = response.json()["data"]
        expected_count = len(list(LanguageCode))
        assert len(languages) == expected_count

    async def test_each_language_has_code_and_display_name(
        self, async_client: AsyncClient
    ) -> None:
        """Test each returned language object has code and display_name fields."""
        response = await async_client.get("/api/v1/settings/supported-languages")

        assert response.status_code == 200
        languages = response.json()["data"]
        for lang in languages:
            assert "code" in lang, f"Missing 'code' key in: {lang}"
            assert "display_name" in lang, f"Missing 'display_name' key in: {lang}"
            assert isinstance(lang["code"], str)
            assert isinstance(lang["display_name"], str)
            assert len(lang["code"]) > 0
            assert len(lang["display_name"]) > 0

    async def test_languages_are_sorted_alphabetically_by_display_name(
        self, async_client: AsyncClient
    ) -> None:
        """Test returned languages are sorted alphabetically by display_name."""
        response = await async_client.get("/api/v1/settings/supported-languages")

        assert response.status_code == 200
        languages = response.json()["data"]
        display_names = [lang["display_name"] for lang in languages]
        assert display_names == sorted(display_names), (
            "Languages are not sorted alphabetically by display_name. "
            f"First few: {display_names[:5]}"
        )

    async def test_language_codes_match_enum_values(
        self, async_client: AsyncClient
    ) -> None:
        """Test all returned codes exist in the LanguageCode enum."""
        response = await async_client.get("/api/v1/settings/supported-languages")

        assert response.status_code == 200
        languages = response.json()["data"]
        enum_values = {lc.value for lc in LanguageCode}
        returned_codes = {lang["code"] for lang in languages}
        assert returned_codes == enum_values, (
            f"Returned codes do not match LanguageCode enum values. "
            f"Missing: {enum_values - returned_codes}, "
            f"Extra: {returned_codes - enum_values}"
        )

    async def test_endpoint_accessible_without_authentication(
        self, async_client_no_auth: AsyncClient
    ) -> None:
        """Test endpoint is public — accessible without authentication."""
        with patch(
            "chronovista.auth.youtube_oauth.is_authenticated",
            return_value=True,
        ):
            response = await async_client_no_auth.get(
                "/api/v1/settings/supported-languages"
            )
        # Supported languages is a public endpoint — should never require auth
        assert response.status_code == 200

    async def test_english_present_with_correct_display_name(
        self, async_client: AsyncClient
    ) -> None:
        """Test English language code is present and has expected display name."""
        response = await async_client.get("/api/v1/settings/supported-languages")

        assert response.status_code == 200
        languages = response.json()["data"]
        english = next((l for l in languages if l["code"] == "en"), None)
        assert english is not None, "English ('en') not found in supported languages"
        assert english["display_name"] == "English"

    async def test_response_does_not_contain_duplicate_codes(
        self, async_client: AsyncClient
    ) -> None:
        """Test no duplicate language codes in the response."""
        response = await async_client.get("/api/v1/settings/supported-languages")

        assert response.status_code == 200
        languages = response.json()["data"]
        codes = [lang["code"] for lang in languages]
        assert len(codes) == len(
            set(codes)
        ), "Duplicate language codes found in response"


# ═══════════════════════════════════════════════════════════════════════════
# GET /settings/cache Tests (auth required)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetCacheStatus:
    """Tests for GET /api/v1/settings/cache endpoint.

    This endpoint used to walk the cache directories itself, because
    ``ImageCacheService.get_stats()`` reached for ``pathlib``'s ``rglob``,
    which raises ``FileNotFoundError`` on Docker overlay2 when an entry
    disappears mid-scan (#101). The service now walks with ``os.walk`` and
    tolerates that, so the router delegates and the duplicate is gone.

    These tests moved with it. They previously patched ``os.scandir``,
    ``os.walk``, ``os.path.join`` and ``os.stat`` to drive the router's own
    loop; that loop no longer exists, and mocking the ``os`` module to test a
    router was never testing much anyway. What the router owes its caller now
    is the mapping from ``CacheStats`` to ``CacheStatusResponse``, which is
    what these assert. The walking itself is covered against a real directory
    tree in ``tests/unit/services/test_image_cache_walk.py``.
    """

    @staticmethod
    def _stats(**overrides: object) -> CacheStats:
        base: dict[str, object] = {
            "channel_count": 0,
            "channel_missing_count": 0,
            "video_count": 0,
            "video_missing_count": 0,
            "total_size_bytes": 0,
            "oldest_file": None,
            "newest_file": None,
        }
        base.update(overrides)
        return CacheStats(**base)  # type: ignore[arg-type]

    def _patched(self, stats: CacheStats) -> object:
        return patch(
            "chronovista.api.routers.settings._image_cache_service.get_stats",
            new=AsyncMock(return_value=stats),
        )

    async def test_returns_200_with_api_response_envelope(
        self, async_client: AsyncClient
    ) -> None:
        with self._patched(self._stats(channel_count=1, total_size_bytes=1024)):
            response = await async_client.get("/api/v1/settings/cache")

        assert response.status_code == 200
        assert "data" in response.json()

    async def test_response_contains_all_required_fields(
        self, async_client: AsyncClient
    ) -> None:
        with self._patched(self._stats()):
            response = await async_client.get("/api/v1/settings/cache")

        data = response.json()["data"]
        for field in (
            "channel_count",
            "video_count",
            "total_count",
            "total_size_bytes",
            "total_size_display",
            "oldest_file",
            "newest_file",
        ):
            assert field in data, f"missing field: {field}"

    async def test_empty_cache_returns_zero_counts(
        self, async_client: AsyncClient
    ) -> None:
        with self._patched(self._stats()):
            response = await async_client.get("/api/v1/settings/cache")

        data = response.json()["data"]
        assert data["channel_count"] == 0
        assert data["video_count"] == 0
        assert data["total_count"] == 0
        assert data["total_size_bytes"] == 0

    async def test_counts_are_passed_through_unchanged(
        self, async_client: AsyncClient
    ) -> None:
        with self._patched(
            self._stats(channel_count=2, video_count=3, total_size_bytes=4096)
        ):
            response = await async_client.get("/api/v1/settings/cache")

        data = response.json()["data"]
        assert data["channel_count"] == 2
        assert data["video_count"] == 3
        assert data["total_size_bytes"] == 4096

    async def test_total_count_is_the_sum_of_both(
        self, async_client: AsyncClient
    ) -> None:
        """The one figure the router derives rather than forwards."""
        with self._patched(self._stats(channel_count=7, video_count=11)):
            response = await async_client.get("/api/v1/settings/cache")

        data = response.json()["data"]
        assert data["total_count"] == 18

    async def test_missing_markers_are_not_counted_as_cached_images(
        self, async_client: AsyncClient
    ) -> None:
        """`.missing` markers record a failed fetch, not a cached image.

        `CacheStatusResponse` has no field for them, so the risk is that a
        future mapping quietly folds them into the counts and inflates what
        the Settings page reports as cached.
        """
        with self._patched(
            self._stats(
                channel_count=1,
                video_count=1,
                channel_missing_count=50,
                video_missing_count=60,
            )
        ):
            response = await async_client.get("/api/v1/settings/cache")

        data = response.json()["data"]
        assert data["channel_count"] == 1
        assert data["video_count"] == 1
        assert data["total_count"] == 2

    async def test_size_display_is_human_readable(
        self, async_client: AsyncClient
    ) -> None:
        with self._patched(self._stats(total_size_bytes=2 * 1024 * 1024)):
            response = await async_client.get("/api/v1/settings/cache")

        display = response.json()["data"]["total_size_display"]
        assert isinstance(display, str)
        assert "MB" in display, f"Expected MB in display string, got: {display}"

    async def test_timestamps_are_forwarded(self, async_client: AsyncClient) -> None:
        oldest = datetime(2026, 1, 2, 3, 4, 5)
        newest = datetime(2026, 6, 7, 8, 9, 10)
        with self._patched(self._stats(oldest_file=oldest, newest_file=newest)):
            response = await async_client.get("/api/v1/settings/cache")

        data = response.json()["data"]
        assert data["oldest_file"] is not None
        assert data["newest_file"] is not None
        assert data["oldest_file"].startswith("2026-01-02")
        assert data["newest_file"].startswith("2026-06-07")

    async def test_requires_authentication(
        self, async_client_no_auth: AsyncClient
    ) -> None:
        """Test cache status endpoint requires authentication."""
        with patch(
            "chronovista.auth.youtube_oauth.is_authenticated",
            return_value=False,
        ):
            response = await async_client_no_auth.get("/api/v1/settings/cache")

        assert response.status_code == 401


class TestClearCache:
    """Tests for DELETE /api/v1/settings/cache endpoint."""

    async def test_successful_purge_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        """Test successful cache purge returns 200 with purged=True."""
        with patch(
            "chronovista.api.routers.settings._image_cache_service.purge",
            new_callable=AsyncMock,
        ) as mock_purge:
            response = await async_client.delete("/api/v1/settings/cache")

        assert response.status_code == 200
        mock_purge.assert_called_once_with(type_="all")

    async def test_successful_purge_response_body(
        self, async_client: AsyncClient
    ) -> None:
        """Test successful purge response contains purged=True and message."""
        with patch(
            "chronovista.api.routers.settings._image_cache_service.purge",
            new_callable=AsyncMock,
        ):
            response = await async_client.delete("/api/v1/settings/cache")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        data = body["data"]
        assert data["purged"] is True
        assert isinstance(data["message"], str)
        assert len(data["message"]) > 0

    async def test_purge_exception_returns_500(self, async_client: AsyncClient) -> None:
        """Test that an exception during purge returns 500 ProblemJSON response."""
        with patch(
            "chronovista.api.routers.settings._image_cache_service.purge",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Disk full"),
        ):
            response = await async_client.delete("/api/v1/settings/cache")

        assert response.status_code == 500

    async def test_purge_exception_response_is_problem_json(
        self, async_client: AsyncClient
    ) -> None:
        """Test 500 response follows RFC 7807 ProblemJSON format."""
        with patch(
            "chronovista.api.routers.settings._image_cache_service.purge",
            new_callable=AsyncMock,
            side_effect=OSError("Permission denied"),
        ):
            response = await async_client.delete("/api/v1/settings/cache")

        assert response.status_code == 500
        body = response.json()
        # RFC 7807 fields
        assert "type" in body
        assert "title" in body
        assert "status" in body
        assert body["status"] == 500

    async def test_purge_error_detail_includes_exception_message(
        self, async_client: AsyncClient
    ) -> None:
        """Test 500 response detail includes the underlying exception message."""
        error_message = "No space left on device"
        with patch(
            "chronovista.api.routers.settings._image_cache_service.purge",
            new_callable=AsyncMock,
            side_effect=OSError(error_message),
        ):
            response = await async_client.delete("/api/v1/settings/cache")

        assert response.status_code == 500
        body = response.json()
        assert "detail" in body
        assert error_message in body["detail"]

    async def test_purge_called_with_type_all(self, async_client: AsyncClient) -> None:
        """Test purge is called with type_='all' to clear all cache types."""
        with patch(
            "chronovista.api.routers.settings._image_cache_service.purge",
            new_callable=AsyncMock,
        ) as mock_purge:
            await async_client.delete("/api/v1/settings/cache")

        mock_purge.assert_called_once()
        call_kwargs = mock_purge.call_args[1]
        assert call_kwargs.get("type_") == "all"

    async def test_delete_requires_authentication(
        self, async_client_no_auth: AsyncClient
    ) -> None:
        """Test DELETE cache endpoint requires authentication."""
        with patch(
            "chronovista.auth.youtube_oauth.is_authenticated",
            return_value=False,
        ):
            response = await async_client_no_auth.delete("/api/v1/settings/cache")

        assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# GET /settings/app-info Tests (auth required)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetAppInfo:
    """Tests for GET /api/v1/settings/app-info endpoint."""

    def _make_mock_session_with_counts(
        self,
        video_count: int = 100,
        channel_count: int = 20,
        playlist_count: int = 5,
        transcript_count: int = 80,
        correction_count: int = 10,
        canonical_tag_count: int = 50,
    ) -> AsyncMock:
        """Create a mock AsyncSession whose scalar() returns counts in order."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.scalar.side_effect = [
            video_count,
            channel_count,
            playlist_count,
            transcript_count,
            correction_count,
            canonical_tag_count,
        ]
        return mock_session

    async def test_returns_200_with_api_response_envelope(
        self, async_client: AsyncClient
    ) -> None:
        """Test app-info returns 200 with data wrapped in ApiResponse envelope."""
        mock_session = self._make_mock_session_with_counts()

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body

    async def test_response_contains_all_required_fields(
        self, async_client: AsyncClient
    ) -> None:
        """Test app-info response includes all required top-level fields."""
        mock_session = self._make_mock_session_with_counts()

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        data = response.json()["data"]
        assert "backend_version" in data
        assert "frontend_version" in data
        assert "database_stats" in data
        assert "sync_timestamps" in data

    async def test_database_stats_contains_all_table_counts(
        self, async_client: AsyncClient
    ) -> None:
        """Test database_stats includes counts for all tracked tables."""
        mock_session = self._make_mock_session_with_counts(
            video_count=150,
            channel_count=30,
            playlist_count=8,
            transcript_count=120,
            correction_count=25,
            canonical_tag_count=75,
        )

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        stats = response.json()["data"]["database_stats"]
        assert stats["videos"] == 150
        assert stats["channels"] == 30
        assert stats["playlists"] == 8
        assert stats["transcripts"] == 120
        assert stats["corrections"] == 25
        assert stats["canonical_tags"] == 75

    async def test_empty_tables_return_zero_counts(
        self, async_client: AsyncClient
    ) -> None:
        """Test that None scalar results (empty tables) are treated as zero."""
        mock_session = self._make_mock_session_with_counts(
            video_count=0,
            channel_count=0,
            playlist_count=0,
            transcript_count=0,
            correction_count=0,
            canonical_tag_count=0,
        )

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        stats = response.json()["data"]["database_stats"]
        assert stats["videos"] == 0
        assert stats["channels"] == 0
        assert stats["playlists"] == 0
        assert stats["transcripts"] == 0
        assert stats["corrections"] == 0
        assert stats["canonical_tags"] == 0

    async def test_null_scalar_results_coerced_to_zero(
        self, async_client: AsyncClient
    ) -> None:
        """Test that None returns from session.scalar() are coerced to 0."""
        mock_session = AsyncMock(spec=AsyncSession)
        # Return None for all 6 COUNT queries — simulates tables with no rows
        mock_session.scalar.side_effect = [None, None, None, None, None, None]

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        stats = response.json()["data"]["database_stats"]
        for field in [
            "videos",
            "channels",
            "playlists",
            "transcripts",
            "corrections",
            "canonical_tags",
        ]:
            assert stats[field] == 0, f"Expected 0 for {field}, got {stats[field]}"

    async def test_sync_timestamps_contains_all_sync_types(
        self, async_client: AsyncClient
    ) -> None:
        """Test sync_timestamps includes entries for all five sync operation types."""
        mock_session = self._make_mock_session_with_counts()

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        expected_keys = {
            SyncOperationType.SUBSCRIPTIONS.value,
            SyncOperationType.VIDEOS.value,
            SyncOperationType.TRANSCRIPTS.value,
            SyncOperationType.PLAYLISTS.value,
            SyncOperationType.TOPICS.value,
        }

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        sync_timestamps = response.json()["data"]["sync_timestamps"]
        returned_keys = set(sync_timestamps.keys())
        assert expected_keys == returned_keys, (
            f"sync_timestamps keys mismatch. "
            f"Expected: {expected_keys}, Got: {returned_keys}"
        )

    async def test_sync_timestamps_null_when_never_synced(
        self, async_client: AsyncClient
    ) -> None:
        """Test sync_timestamps values are null when sync has never run."""
        mock_session = self._make_mock_session_with_counts()

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        sync_timestamps = response.json()["data"]["sync_timestamps"]
        for key, value in sync_timestamps.items():
            assert (
                value is None
            ), f"Expected None for sync_timestamps['{key}'], got: {value}"

    async def test_sync_timestamps_include_actual_datetimes_when_synced(
        self, async_client: AsyncClient
    ) -> None:
        """Test sync_timestamps contain ISO datetime strings when sync has run."""
        mock_session = self._make_mock_session_with_counts()

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        last_sync_time = datetime(2026, 1, 15, 12, 0, 0)

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=last_sync_time,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        sync_timestamps = response.json()["data"]["sync_timestamps"]
        for key, value in sync_timestamps.items():
            assert value is not None, f"Expected a timestamp for '{key}', got None"
            # Value should be ISO format datetime string
            assert isinstance(
                value, str
            ), f"Expected str timestamp for '{key}', got {type(value)}"

    async def test_backend_version_is_non_empty_string(
        self, async_client: AsyncClient
    ) -> None:
        """Test backend_version is a non-empty string from the package version."""
        mock_session = self._make_mock_session_with_counts()

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data["backend_version"], str)
        assert len(data["backend_version"]) > 0

    async def test_frontend_version_is_set(self, async_client: AsyncClient) -> None:
        """Test frontend_version is set to the expected value."""
        mock_session = self._make_mock_session_with_counts()

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["frontend_version"] == "0.18.0"

    async def test_scalar_called_six_times_for_six_tables(
        self, async_client: AsyncClient
    ) -> None:
        """Test that session.scalar() is called exactly 6 times for COUNT queries."""
        mock_session = self._make_mock_session_with_counts()

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        assert mock_session.scalar.call_count == 6, (
            f"Expected 6 scalar() calls (one per table), "
            f"got {mock_session.scalar.call_count}"
        )

    async def test_mixed_sync_timestamps_some_null_some_present(
        self, async_client: AsyncClient
    ) -> None:
        """Test response correctly handles mixed null/non-null sync timestamps."""
        mock_session = self._make_mock_session_with_counts()

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        last_sync = datetime(2026, 3, 1, 10, 30, 0)
        # Return non-None only for SUBSCRIPTIONS, None for all others
        call_count = {"n": 0}

        def side_effect_sync(op_type: SyncOperationType) -> datetime | None:
            call_count["n"] += 1
            if op_type == SyncOperationType.SUBSCRIPTIONS:
                return last_sync
            return None

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            side_effect=side_effect_sync,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        sync_timestamps = response.json()["data"]["sync_timestamps"]
        # subscriptions should have a value
        assert sync_timestamps["subscriptions"] is not None
        # others should be null
        assert sync_timestamps["videos"] is None
        assert sync_timestamps["transcripts"] is None
        assert sync_timestamps["playlists"] is None
        assert sync_timestamps["topics"] is None

    async def test_app_info_requires_authentication(
        self, async_client_no_auth: AsyncClient
    ) -> None:
        """Test app-info endpoint requires authentication."""
        with patch(
            "chronovista.auth.youtube_oauth.is_authenticated",
            return_value=False,
        ):
            response = await async_client_no_auth.get("/api/v1/settings/app-info")

        assert response.status_code == 401

    async def test_gather_returns_correct_counts_for_each_field(
        self, async_client: AsyncClient
    ) -> None:
        """Verify asyncio.gather returns each COUNT in the correct DatabaseStats field.

        The endpoint issues 6 independent COUNT queries via asyncio.gather in
        this order: videos, channels, playlists, transcripts, corrections,
        canonical_tags.  Each field in DatabaseStats must carry the value from
        the corresponding query, not a neighbour's value.
        """
        mock_session = AsyncMock(spec=AsyncSession)
        # Distinct primes so any field-assignment swap is immediately visible.
        mock_session.scalar.side_effect = [
            101,  # videos
            202,  # channels
            303,  # playlists
            404,  # transcripts
            505,  # corrections
            606,  # canonical_tags
        ]

        async def mock_get_db_custom() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db_custom

        with patch(
            "chronovista.api.services.sync_manager.sync_manager.get_last_successful_sync",
            return_value=None,
        ):
            response = await async_client.get("/api/v1/settings/app-info")

        assert response.status_code == 200
        stats = response.json()["data"]["database_stats"]
        assert stats["videos"] == 101
        assert stats["channels"] == 202
        assert stats["playlists"] == 303
        assert stats["transcripts"] == 404
        assert stats["corrections"] == 505
        assert stats["canonical_tags"] == 606
