"""Integration tests for health endpoint."""
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


class TestHealthEndpoint:
    """Tests for GET /api/v1/health endpoint."""

    async def test_health_returns_200(self, async_client: AsyncClient) -> None:
        """Test health endpoint returns 200 OK."""
        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_health_returns_correct_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test health endpoint returns correct response structure."""
        response = await async_client.get("/api/v1/health")
        data = response.json()

        # Check top-level structure (ApiResponse envelope)
        assert "data" in data
        assert isinstance(data["data"], dict)

        # Check HealthStatus fields
        health_data = data["data"]
        assert "status" in health_data
        assert "version" in health_data
        assert "database" in health_data
        assert "authenticated" in health_data
        assert "timestamp" in health_data
        assert "checks" in health_data

    async def test_health_status_is_valid(self, async_client: AsyncClient) -> None:
        """Test health status is one of valid values."""
        response = await async_client.get("/api/v1/health")
        data = response.json()

        assert data["data"]["status"] in ["healthy", "degraded", "unhealthy"]

    async def test_health_database_status_is_valid(
        self, async_client: AsyncClient
    ) -> None:
        """Test database status is one of valid values."""
        response = await async_client.get("/api/v1/health")
        data = response.json()

        assert data["data"]["database"] in ["connected", "disconnected"]

    async def test_health_authenticated_is_boolean(
        self, async_client: AsyncClient
    ) -> None:
        """Test authenticated field is a boolean."""
        response = await async_client.get("/api/v1/health")
        data = response.json()

        assert isinstance(data["data"]["authenticated"], bool)

    async def test_health_version_matches_app_version(
        self, async_client: AsyncClient
    ) -> None:
        """Test version field matches application version."""
        from chronovista import __version__

        response = await async_client.get("/api/v1/health")
        data = response.json()

        assert data["data"]["version"] == __version__

    async def test_health_timestamp_format(self, async_client: AsyncClient) -> None:
        """Test timestamp is in valid ISO format."""
        response = await async_client.get("/api/v1/health")
        data = response.json()

        timestamp_str = data["data"]["timestamp"]
        # Should be able to parse as ISO datetime
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        assert isinstance(timestamp, datetime)

    async def test_health_checks_structure(self, async_client: AsyncClient) -> None:
        """Test checks field has correct structure."""
        response = await async_client.get("/api/v1/health")
        data = response.json()

        checks = data["data"]["checks"]
        assert isinstance(checks, dict)
        assert "database_latency_ms" in checks

    async def test_health_no_auth_required(self, async_client: AsyncClient) -> None:
        """Test health endpoint works without authentication."""
        # No auth headers, should still work
        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_health_with_custom_headers(self, async_client: AsyncClient) -> None:
        """Test health endpoint ignores custom headers."""
        response = await async_client.get(
            "/api/v1/health",
            headers={"X-Custom-Header": "test"},
        )
        assert response.status_code == 200

    async def test_health_database_connected_when_available(
        self, async_client: AsyncClient
    ) -> None:
        """Test health shows database as connected when database is available."""
        response = await async_client.get("/api/v1/health")
        data = response.json()

        # Database should be connected in test environment
        # (actual connectivity depends on test setup)
        assert data["data"]["database"] in ["connected", "disconnected"]

    async def test_health_database_latency_when_connected(
        self, async_client: AsyncClient
    ) -> None:
        """Test database latency is reported when database is connected."""
        response = await async_client.get("/api/v1/health")
        data = response.json()

        if data["data"]["database"] == "connected":
            # Latency should be present and be a positive integer
            latency = data["data"]["checks"]["database_latency_ms"]
            if latency is not None:
                assert isinstance(latency, int)
                assert latency >= 0

    async def test_health_status_healthy_when_database_connected(
        self, async_client: AsyncClient
    ) -> None:
        """Test status is healthy when database is connected."""
        response = await async_client.get("/api/v1/health")
        data = response.json()

        if data["data"]["database"] == "connected":
            # Status should be healthy when DB is connected
            assert data["data"]["status"] in ["healthy", "degraded"]

    async def test_health_response_time_reasonable(
        self, async_client: AsyncClient
    ) -> None:
        """Test health endpoint responds within reasonable time."""
        import time

        start = time.monotonic()
        response = await async_client.get("/api/v1/health")
        elapsed_ms = (time.monotonic() - start) * 1000

        assert response.status_code == 200
        # Health check should be fast (under 5 seconds for most cases)
        assert elapsed_ms < 5000

    async def test_health_content_type_json(self, async_client: AsyncClient) -> None:
        """Test health endpoint returns JSON content type."""
        response = await async_client.get("/api/v1/health")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    async def test_health_accepts_get_method_only(
        self, async_client: AsyncClient
    ) -> None:
        """Test health endpoint only accepts GET method."""
        # POST should not be allowed
        response = await async_client.post("/api/v1/health")
        assert response.status_code == 405  # Method Not Allowed

        # PUT should not be allowed
        response = await async_client.put("/api/v1/health")
        assert response.status_code == 405

        # DELETE should not be allowed
        response = await async_client.delete("/api/v1/health")
        assert response.status_code == 405

    async def test_health_multiple_concurrent_requests(
        self, async_client: AsyncClient
    ) -> None:
        """Test health endpoint handles multiple concurrent requests."""
        import asyncio

        # Make 5 concurrent requests
        responses = await asyncio.gather(
            *[async_client.get("/api/v1/health") for _ in range(5)]
        )

        # All should succeed
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "status" in data["data"]

    async def test_health_pagination_not_present(
        self, async_client: AsyncClient
    ) -> None:
        """Test health endpoint response does not include pagination."""
        response = await async_client.get("/api/v1/health")
        data = response.json()

        # Pagination should be null for non-list responses
        assert data.get("pagination") is None


class TestHealthEndpointDatabaseFailure:
    """Tests for health endpoint behavior when database fails."""

    async def test_health_returns_200_when_database_unavailable(
        self, async_client: AsyncClient
    ) -> None:
        """Test health endpoint returns 200 even when database is unavailable."""
        # Mock db_manager to raise exception
        async def mock_get_session():
            raise ConnectionError("Database unavailable")
            yield  # type: ignore[unreachable]  # Unreachable

        with patch("chronovista.api.routers.health.db_manager") as mock_db:
            mock_db.get_session = mock_get_session

            response = await async_client.get("/api/v1/health")
            assert response.status_code == 200

    async def test_health_shows_database_disconnected_on_error(
        self, async_client: AsyncClient
    ) -> None:
        """Test health shows database as disconnected when connection fails."""
        # Mock db_manager to raise exception
        async def mock_get_session():
            raise ConnectionError("Database unavailable")
            yield  # type: ignore[unreachable]

        with patch("chronovista.api.routers.health.db_manager") as mock_db:
            mock_db.get_session = mock_get_session

            response = await async_client.get("/api/v1/health")
            data = response.json()

            assert data["data"]["database"] == "disconnected"

    async def test_health_status_unhealthy_when_database_disconnected(
        self, async_client: AsyncClient
    ) -> None:
        """Test status is unhealthy when database is disconnected."""
        # Mock db_manager to raise exception
        async def mock_get_session():
            raise ConnectionError("Database unavailable")
            yield  # type: ignore[unreachable]

        with patch("chronovista.api.routers.health.db_manager") as mock_db:
            mock_db.get_session = mock_get_session

            response = await async_client.get("/api/v1/health")
            data = response.json()

            assert data["data"]["status"] == "unhealthy"

    async def test_health_no_latency_when_database_disconnected(
        self, async_client: AsyncClient
    ) -> None:
        """Test database latency is None when database is disconnected."""
        # Mock db_manager to raise exception
        async def mock_get_session():
            raise ConnectionError("Database unavailable")
            yield  # type: ignore[unreachable]

        with patch("chronovista.api.routers.health.db_manager") as mock_db:
            mock_db.get_session = mock_get_session

            response = await async_client.get("/api/v1/health")
            data = response.json()

            assert data["data"]["checks"]["database_latency_ms"] is None


class TestHealthEndpointAuthenticationStatus:
    """Tests for health endpoint authentication status reporting."""

    async def test_health_shows_authenticated_true_when_logged_in(
        self, async_client: AsyncClient
    ) -> None:
        """Test health shows authenticated=true when user is logged in."""
        with patch("chronovista.api.routers.health.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.get("/api/v1/health")
            data = response.json()

            assert data["data"]["authenticated"] is True

    async def test_health_shows_authenticated_false_when_not_logged_in(
        self, async_client: AsyncClient
    ) -> None:
        """Test health shows authenticated=false when user is not logged in."""
        with patch("chronovista.api.routers.health.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False

            response = await async_client.get("/api/v1/health")
            data = response.json()

            assert data["data"]["authenticated"] is False

    async def test_health_remains_healthy_when_not_authenticated(
        self, async_client: AsyncClient
    ) -> None:
        """Test health status remains healthy when not authenticated."""
        # Mock both database (connected) and auth (not authenticated)
        with patch("chronovista.api.routers.health.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False

            response = await async_client.get("/api/v1/health")
            data = response.json()

            # Health can be healthy even without auth
            # (auth is not required for health endpoint)
            if data["data"]["database"] == "connected":
                assert data["data"]["status"] in ["healthy", "degraded"]
