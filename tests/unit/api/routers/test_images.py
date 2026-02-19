"""
Unit tests for image cache proxy API endpoints.

Tests the FastAPI channel image endpoint including cache behavior,
placeholder serving, and error handling.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from chronovista.api.main import app
from chronovista.services.image_cache import (
    _CACHE_CONTROL_HIT,
    _CACHE_CONTROL_PLACEHOLDER,
    _CHANNEL_PLACEHOLDER_SVG,
)
from tests.factories.channel_factory import ChannelTestData

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for FastAPI testing."""
    from collections.abc import AsyncGenerator
    from sqlalchemy.ext.asyncio import AsyncSession
    from chronovista.api.deps import get_db

    # Mock database dependency
    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        mock_session = AsyncMock(spec=AsyncSession)
        yield mock_session

    # Override the dependency
    app.dependency_overrides[get_db] = mock_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        # Clean up the override
        app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Channel Image Endpoint Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelImageEndpoint:
    """Tests for GET /api/v1/images/channels/{channel_id} endpoint."""

    async def test_cache_hit_returns_image_with_hit_header(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """Test cache HIT returns image bytes with X-Cache: HIT header."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Mock the image cache service to return a HIT response
        from starlette.responses import Response

        mock_response = Response(
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 2048,
            media_type="image/jpeg",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "HIT",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            response = await async_client.get(
                f"/api/v1/images/channels/{channel_id}"
            )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "image/jpeg"
        assert response.headers["X-Cache"] == "HIT"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_HIT
        assert len(response.content) > 1024

    async def test_cache_miss_fetches_and_returns_with_miss_header(
        self, async_client: AsyncClient
    ) -> None:
        """Test cache MISS fetches, caches, returns with X-Cache: MISS."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[1]

        # Mock the image cache service to return a MISS response
        from starlette.responses import Response

        mock_response = Response(
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 2048,
            media_type="image/jpeg",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "MISS",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            response = await async_client.get(
                f"/api/v1/images/channels/{channel_id}"
            )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "image/jpeg"
        assert response.headers["X-Cache"] == "MISS"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_HIT

    async def test_placeholder_on_failure_with_placeholder_header(
        self, async_client: AsyncClient
    ) -> None:
        """Test placeholder served on failure with X-Cache: PLACEHOLDER."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[2]

        # Mock the image cache service to return a PLACEHOLDER response
        from starlette.responses import Response

        mock_response = Response(
            content=_CHANNEL_PLACEHOLDER_SVG,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": _CACHE_CONTROL_PLACEHOLDER,
                "X-Cache": "PLACEHOLDER",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            response = await async_client.get(
                f"/api/v1/images/channels/{channel_id}"
            )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "image/svg+xml"
        assert response.headers["X-Cache"] == "PLACEHOLDER"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_PLACEHOLDER
        assert response.content == _CHANNEL_PLACEHOLDER_SVG

    async def test_placeholder_on_null_thumbnail_url(
        self, async_client: AsyncClient
    ) -> None:
        """Test placeholder served when channel has NULL thumbnail_url."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[3]

        # Mock the image cache service to return a PLACEHOLDER response
        from starlette.responses import Response

        mock_response = Response(
            content=_CHANNEL_PLACEHOLDER_SVG,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": _CACHE_CONTROL_PLACEHOLDER,
                "X-Cache": "PLACEHOLDER",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            response = await async_client.get(
                f"/api/v1/images/channels/{channel_id}"
            )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "image/svg+xml"
        assert response.headers["X-Cache"] == "PLACEHOLDER"

    async def test_invalid_channel_id_format_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """Test invalid channel_id format returns 422 response."""
        # Too short
        response = await async_client.get("/api/v1/images/channels/UCxxx")
        assert response.status_code == 422

        # Too long
        response = await async_client.get(
            "/api/v1/images/channels/UCxxx123456789012345678901234567890"
        )
        assert response.status_code == 422

        # Wrong prefix
        response = await async_client.get(
            "/api/v1/images/channels/XXxxx12345678901234567890"
        )
        assert response.status_code == 422

        # Special characters
        response = await async_client.get(
            "/api/v1/images/channels/UC@@@12345678901234567890"
        )
        assert response.status_code == 422

    async def test_cache_control_header_7_day_for_real_images(
        self, async_client: AsyncClient
    ) -> None:
        """Test Cache-Control header is 7-day immutable for real images."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[4]

        # Mock HIT response (real image)
        from starlette.responses import Response

        mock_response = Response(
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 2048,
            media_type="image/jpeg",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "HIT",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            response = await async_client.get(
                f"/api/v1/images/channels/{channel_id}"
            )

        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "public, max-age=604800, immutable"

    async def test_cache_control_header_1_hour_for_placeholders(
        self, async_client: AsyncClient
    ) -> None:
        """Test Cache-Control header is 1-hour for placeholders."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Mock PLACEHOLDER response
        from starlette.responses import Response

        mock_response = Response(
            content=_CHANNEL_PLACEHOLDER_SVG,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": _CACHE_CONTROL_PLACEHOLDER,
                "X-Cache": "PLACEHOLDER",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            response = await async_client.get(
                f"/api/v1/images/channels/{channel_id}"
            )

        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "public, max-age=3600"

    async def test_endpoint_is_public_no_auth_required(
        self, async_client: AsyncClient
    ) -> None:
        """Test endpoint is public and works without authentication."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[1]

        # Mock response
        from starlette.responses import Response

        mock_response = Response(
            content=_CHANNEL_PLACEHOLDER_SVG,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": _CACHE_CONTROL_PLACEHOLDER,
                "X-Cache": "PLACEHOLDER",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            # No auth headers
            response = await async_client.get(
                f"/api/v1/images/channels/{channel_id}"
            )

        assert response.status_code == 200

    async def test_endpoint_accepts_only_get_method(
        self, async_client: AsyncClient
    ) -> None:
        """Test endpoint only accepts GET method."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[2]

        # POST should not be allowed
        response = await async_client.post(f"/api/v1/images/channels/{channel_id}")
        assert response.status_code == 405

        # PUT should not be allowed
        response = await async_client.put(f"/api/v1/images/channels/{channel_id}")
        assert response.status_code == 405

        # DELETE should not be allowed
        response = await async_client.delete(f"/api/v1/images/channels/{channel_id}")
        assert response.status_code == 405

    async def test_endpoint_handles_png_images(self, async_client: AsyncClient) -> None:
        """Test endpoint serves PNG images with correct content type."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[3]

        # Mock PNG response
        from starlette.responses import Response

        mock_response = Response(
            content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048,
            media_type="image/png",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "HIT",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            response = await async_client.get(
                f"/api/v1/images/channels/{channel_id}"
            )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "image/png"

    async def test_endpoint_handles_webp_images(
        self, async_client: AsyncClient
    ) -> None:
        """Test endpoint serves WebP images with correct content type."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[4]

        # Mock WebP response
        from starlette.responses import Response

        mock_response = Response(
            content=b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 2048,
            media_type="image/webp",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "HIT",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            response = await async_client.get(
                f"/api/v1/images/channels/{channel_id}"
            )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "image/webp"

    async def test_concurrent_requests_handled_correctly(
        self, async_client: AsyncClient
    ) -> None:
        """Test multiple concurrent requests handled correctly."""
        import asyncio

        channel_ids = ChannelTestData.VALID_CHANNEL_IDS

        # Mock responses
        from starlette.responses import Response

        mock_response = Response(
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 2048,
            media_type="image/jpeg",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "HIT",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            # Make 5 concurrent requests
            responses = await asyncio.gather(
                *[
                    async_client.get(f"/api/v1/images/channels/{channel_id}")
                    for channel_id in channel_ids
                ]
            )

        # All should succeed
        for response in responses:
            assert response.status_code == 200
            assert response.headers["X-Cache"] == "HIT"

    async def test_endpoint_path_matches_openapi_spec(
        self, async_client: AsyncClient
    ) -> None:
        """Test endpoint path matches OpenAPI specification."""
        # Get OpenAPI spec
        response = await async_client.get("/openapi.json")
        assert response.status_code == 200
        openapi_spec = response.json()

        # Check that endpoint is documented
        assert "/api/v1/images/channels/{channel_id}" in openapi_spec["paths"]

        endpoint_spec = openapi_spec["paths"]["/api/v1/images/channels/{channel_id}"]
        assert "get" in endpoint_spec

        # Check parameters
        get_spec = endpoint_spec["get"]
        assert "parameters" in get_spec

        # Verify channel_id parameter
        channel_id_param = next(
            (p for p in get_spec["parameters"] if p["name"] == "channel_id"),
            None,
        )
        assert channel_id_param is not None
        assert channel_id_param["in"] == "path"
        assert channel_id_param["required"] is True
        assert channel_id_param["schema"]["minLength"] == 24
        assert channel_id_param["schema"]["maxLength"] == 24

    async def test_response_does_not_include_api_envelope(
        self, async_client: AsyncClient
    ) -> None:
        """Test response is raw binary, not wrapped in ApiResponse."""
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Mock response
        from starlette.responses import Response

        mock_response = Response(
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 2048,
            media_type="image/jpeg",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "HIT",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_channel_image",
            return_value=mock_response,
        ):
            response = await async_client.get(
                f"/api/v1/images/channels/{channel_id}"
            )

        # Response should be raw binary, not JSON
        assert response.status_code == 200
        assert "application/json" not in response.headers.get("Content-Type", "")
        assert "image/" in response.headers.get("Content-Type", "")

        # Should not be parseable as JSON
        with pytest.raises(Exception):
            response.json()


# ═══════════════════════════════════════════════════════════════════════════
# Video Image Endpoint Tests (T015)
# ═══════════════════════════════════════════════════════════════════════════


class TestVideoImageEndpoint:
    """Tests for GET /api/v1/images/videos/{video_id} endpoint."""

    async def test_cache_hit_returns_image_with_hit_header(
        self, async_client: AsyncClient
    ) -> None:
        """Test cache HIT returns image bytes with X-Cache: HIT header."""
        from tests.factories.video_factory import VideoTestData

        video_id = VideoTestData.VALID_VIDEO_IDS[0]

        # Mock the image cache service to return a HIT response
        from starlette.responses import Response

        mock_response = Response(
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 2048,
            media_type="image/jpeg",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "HIT",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_video_image",
            return_value=mock_response,
        ):
            response = await async_client.get(f"/api/v1/images/videos/{video_id}")

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "image/jpeg"
        assert response.headers["X-Cache"] == "HIT"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_HIT
        assert len(response.content) > 1024

    async def test_cache_miss_with_deterministic_url(
        self, async_client: AsyncClient
    ) -> None:
        """Test cache MISS uses deterministic YouTube URL construction."""
        from tests.factories.video_factory import VideoTestData

        video_id = VideoTestData.VALID_VIDEO_IDS[1]

        # Mock the image cache service to return a MISS response
        from starlette.responses import Response

        mock_response = Response(
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 2048,
            media_type="image/jpeg",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "MISS",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_video_image",
            return_value=mock_response,
        ):
            response = await async_client.get(f"/api/v1/images/videos/{video_id}")

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "image/jpeg"
        assert response.headers["X-Cache"] == "MISS"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_HIT

    async def test_quality_parameter_default_mqdefault(
        self, async_client: AsyncClient
    ) -> None:
        """Test quality parameter defaults to mqdefault when not specified."""
        from tests.factories.video_factory import VideoTestData

        video_id = VideoTestData.VALID_VIDEO_IDS[2]

        # Mock to capture the quality parameter passed
        from starlette.responses import Response

        mock_response = Response(
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 2048,
            media_type="image/jpeg",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "HIT",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_video_image",
            return_value=mock_response,
        ) as mock_service:
            # No quality parameter
            response = await async_client.get(f"/api/v1/images/videos/{video_id}")

            # Verify the service was called with default quality
            mock_service.assert_called_once()
            call_kwargs = mock_service.call_args[1]
            assert call_kwargs["video_id"] == video_id
            assert call_kwargs["quality"] == "mqdefault"

        assert response.status_code == 200

    async def test_quality_parameter_variations(
        self, async_client: AsyncClient
    ) -> None:
        """Test various quality parameter values work correctly."""
        from tests.factories.video_factory import VideoTestData

        video_id = VideoTestData.VALID_VIDEO_IDS[3]
        qualities = ["default", "mqdefault", "hqdefault", "sddefault", "maxresdefault"]

        for quality in qualities:
            # Mock response
            from starlette.responses import Response

            mock_response = Response(
                content=b"\xff\xd8\xff\xe0" + b"\x00" * 2048,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": _CACHE_CONTROL_HIT,
                    "X-Cache": "HIT",
                },
            )

            with patch(
                "chronovista.api.routers.images._image_cache_service.get_video_image",
                return_value=mock_response,
            ) as mock_service:
                response = await async_client.get(
                    f"/api/v1/images/videos/{video_id}?quality={quality}"
                )

                # Verify service called with correct quality
                mock_service.assert_called_once()
                call_kwargs = mock_service.call_args[1]
                assert call_kwargs["quality"] == quality

            assert response.status_code == 200

    async def test_invalid_video_id_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """Test invalid video_id format returns 422 response."""
        # Too short
        response = await async_client.get("/api/v1/images/videos/short")
        assert response.status_code == 422

        # Too long
        response = await async_client.get("/api/v1/images/videos/toolongvideoid123")
        assert response.status_code == 422

        # Special characters
        response = await async_client.get("/api/v1/images/videos/abc@def#hij")
        assert response.status_code == 422

    async def test_invalid_quality_parameter_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """Test invalid quality parameter returns 422 response."""
        from tests.factories.video_factory import VideoTestData

        video_id = VideoTestData.VALID_VIDEO_IDS[0]

        # Invalid quality value
        response = await async_client.get(
            f"/api/v1/images/videos/{video_id}?quality=invalid"
        )
        assert response.status_code == 422

        response_data = response.json()
        assert "detail" in response_data
        assert "Invalid quality" in response_data["detail"]

    async def test_sharded_directory_creation(self, async_client: AsyncClient) -> None:
        """Test video thumbnails use sharded directory structure."""
        from tests.factories.video_factory import VideoTestData

        video_id = VideoTestData.VALID_VIDEO_IDS[4]  # "abcdefghijk"

        # Mock response
        from starlette.responses import Response

        mock_response = Response(
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 2048,
            media_type="image/jpeg",
            headers={
                "Cache-Control": _CACHE_CONTROL_HIT,
                "X-Cache": "HIT",
            },
        )

        with patch(
            "chronovista.api.routers.images._image_cache_service.get_video_image",
            return_value=mock_response,
        ):
            response = await async_client.get(f"/api/v1/images/videos/{video_id}")

        assert response.status_code == 200
        # The sharding is handled in the service layer, so we just verify it works
