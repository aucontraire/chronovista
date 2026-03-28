"""Tests for HTTP security headers middleware."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from chronovista.api.main import app

EXPECTED_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


class TestSecurityHeaders:
    """Verify security headers are present on all responses."""

    @pytest.fixture
    async def client(self) -> AsyncGenerator[AsyncClient, None]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    async def test_health_endpoint_has_security_headers(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/health")
        for header, value in EXPECTED_HEADERS.items():
            assert response.headers.get(header) == value, (
                f"Missing or wrong header: {header}"
            )

    async def test_csp_header_present(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        csp = response.headers.get("content-security-policy")
        assert csp is not None
        assert "default-src 'self'" in csp
        assert "script-src 'self' https://www.youtube.com" in csp
        assert "object-src 'none'" in csp
        assert "frame-src https://www.youtube-nocookie.com" in csp

    async def test_headers_on_404_response(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/nonexistent")
        for header in EXPECTED_HEADERS:
            assert header in response.headers, (
                f"Security header missing on 404: {header}"
            )
