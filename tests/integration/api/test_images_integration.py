"""
Integration tests for image cache proxy endpoints.

Tests end-to-end image caching behavior including cold cache, warm cache,
sharding, quality variants, and preservation guarantees.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from chronovista.api.main import app
from chronovista.services.image_cache import (
    ImageCacheConfig,
    ImageCacheService,
    _CACHE_CONTROL_HIT,
)
from tests.factories.channel_factory import ChannelTestData
from tests.factories.video_factory import VideoTestData

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


@pytest.fixture
def image_cache_config(tmp_path: Path) -> ImageCacheConfig:
    """Create test image cache configuration."""
    cache_dir = tmp_path / "cache"
    return ImageCacheConfig(
        cache_dir=cache_dir,
        channels_dir=cache_dir / "images" / "channels",
        videos_dir=cache_dir / "images" / "videos",
        on_demand_timeout=2.0,
        warm_timeout=10.0,
        max_concurrent_fetches=5,
    )


# ═══════════════════════════════════════════════════════════════════════════
# T017: Video Integration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestVideoImageIntegration:
    """End-to-end integration tests for video thumbnail caching."""

    async def test_cold_cache_fetch_warm_cache_serve(
        self, tmp_path: Path, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test cold cache → fetch → warm cache → serve from cache flow."""
        service = ImageCacheService(config=image_cache_config)
        video_id = VideoTestData.VALID_VIDEO_IDS[0]
        quality = "mqdefault"

        # Verify cache is cold (no file exists)
        prefix = video_id[:2]
        cache_path = image_cache_config.videos_dir / prefix / f"{video_id}_{quality}.jpg"
        assert not cache_path.exists()

        # Mock successful fetch
        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = valid_image

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            # First request: cold cache (MISS)
            response1 = await service.get_video_image(
                video_id=video_id,
                quality=quality,
            )

        assert response1.status_code == 200
        assert response1.headers["X-Cache"] == "MISS"
        assert cache_path.exists()
        assert cache_path.read_bytes() == valid_image

        # Second request: warm cache (HIT, no network call)
        response2 = await service.get_video_image(
            video_id=video_id,
            quality=quality,
        )

        assert response2.status_code == 200
        assert response2.headers["X-Cache"] == "HIT"
        assert response2.headers["Cache-Control"] == _CACHE_CONTROL_HIT

    async def test_prefix_sharding_creates_correct_subdirectories(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test prefix sharding creates correct subdirectories for videos."""
        service = ImageCacheService(config=image_cache_config)

        # Test with different video IDs to verify sharding
        test_cases = [
            ("dQw4w9WgXcQ", "dQ"),  # Rick Astley
            ("9bZkp7q19f0", "9b"),  # Tech video
            ("abcdefghijk", "ab"),  # Test ID
        ]

        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = valid_image

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            for video_id, expected_prefix in test_cases:
                # Fetch the image
                await service.get_video_image(
                    video_id=video_id,
                    quality="mqdefault",
                )

                # Verify the sharded directory was created
                shard_dir = image_cache_config.videos_dir / expected_prefix
                assert shard_dir.exists()
                assert shard_dir.is_dir()

                # Verify the file is in the correct location
                cache_path = shard_dir / f"{video_id}_mqdefault.jpg"
                assert cache_path.exists()

    async def test_quality_variants_cached_as_separate_files(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test different quality variants are cached as separate files."""
        service = ImageCacheService(config=image_cache_config)
        video_id = VideoTestData.VALID_VIDEO_IDS[1]
        qualities = ["default", "mqdefault", "hqdefault"]

        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = valid_image

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            # Fetch each quality variant
            for quality in qualities:
                response = await service.get_video_image(
                    video_id=video_id,
                    quality=quality,
                )
                assert response.status_code == 200

        # Verify all quality variants are cached separately
        prefix = video_id[:2]
        shard_dir = image_cache_config.videos_dir / prefix

        for quality in qualities:
            cache_path = shard_dir / f"{video_id}_{quality}.jpg"
            assert cache_path.exists()
            assert cache_path.read_bytes() == valid_image

    async def test_deterministic_url_construction_no_db_query(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test video thumbnails use deterministic URLs without DB queries."""
        service = ImageCacheService(config=image_cache_config)
        video_id = VideoTestData.VALID_VIDEO_IDS[2]
        quality = "hqdefault"

        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = valid_image

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            # Fetch the image
            response = await service.get_video_image(
                video_id=video_id,
                quality=quality,
            )

            # Verify the URL was constructed deterministically
            mock_client.get.assert_called_once()
            called_url = mock_client.get.call_args[0][0]
            expected_url = f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"
            assert called_url == expected_url

        assert response.status_code == 200
        assert response.headers["X-Cache"] == "MISS"


# ═══════════════════════════════════════════════════════════════════════════
# T023: US6 Integration Preservation Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestImagePreservationIntegration:
    """End-to-end tests for image preservation after availability changes."""

    async def test_end_to_end_cache_then_mark_unavailable_still_serves(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test end-to-end: cache image → mark entity unavailable → request image → verify still served.

        This is the complete integration test for US6: image preservation
        guarantee. Even after an entity becomes unavailable, its cached
        image continues to be served.
        """
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Step 1: Cache the image
        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(valid_image)

        # Step 2: Verify image is served (cache HIT)
        mock_db_session = AsyncMock()
        response1 = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )

        assert response1.status_code == 200
        assert response1.headers["X-Cache"] == "HIT"
        assert response1.body == valid_image

        # Step 3: Simulate availability_status change
        # (In reality this would be a DB update, but the cache service
        # doesn't query availability_status, so it has no effect on serving)

        # Step 4: Request image again - should still be served from cache
        response2 = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )

        assert response2.status_code == 200
        assert response2.headers["X-Cache"] == "HIT"
        assert response2.body == valid_image

        # Database should never be queried (cache hits)
        mock_db_session.execute.assert_not_called()

    async def test_video_preservation_after_deletion(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test video thumbnail preservation after video deletion.

        Video thumbnails are even more resilient because they don't require
        DB queries at all - they use deterministic URLs.
        """
        service = ImageCacheService(config=image_cache_config)
        video_id = VideoTestData.VALID_VIDEO_IDS[0]
        quality = "mqdefault"

        # Step 1: Cache the video thumbnail
        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        prefix = video_id[:2]
        video_dir = image_cache_config.videos_dir / prefix
        video_dir.mkdir(parents=True, exist_ok=True)
        cache_path = video_dir / f"{video_id}_{quality}.jpg"
        cache_path.write_bytes(valid_image)

        # Step 2: Verify thumbnail is served (cache HIT)
        response1 = await service.get_video_image(
            video_id=video_id,
            quality=quality,
        )

        assert response1.status_code == 200
        assert response1.headers["X-Cache"] == "HIT"
        assert response1.body == valid_image

        # Step 3: Simulate video deletion
        # (The cache service doesn't check video status, so deletion has no effect)

        # Step 4: Request thumbnail again - should still be served from cache
        response2 = await service.get_video_image(
            video_id=video_id,
            quality=quality,
        )

        assert response2.status_code == 200
        assert response2.headers["X-Cache"] == "HIT"
        assert response2.body == valid_image

    async def test_channel_preservation_across_multiple_availability_states(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test channel image remains cached through various availability states."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[1]

        # Cache the channel image
        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(valid_image)

        mock_db_session = AsyncMock()

        # Simulate various availability states (in reality these would be DB updates)
        # The cache service doesn't check these, so it continues serving the image
        availability_states = [
            "available",
            "private",
            "deleted",
            "terminated",
            "copyright",
            "tos_violation",
            "unavailable",
        ]

        for _ in availability_states:
            response = await service.get_channel_image(
                session=mock_db_session,
                channel_id=channel_id,
            )

            # Image should always be served from cache
            assert response.status_code == 200
            assert response.headers["X-Cache"] == "HIT"
            assert response.body == valid_image

        # Database should never be queried (all cache hits)
        mock_db_session.execute.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# T012: Channel Image Integration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestChannelImageIntegration:
    """End-to-end integration tests for channel avatar caching."""

    async def test_cold_cache_fetch_warm_cache_serve(
        self, tmp_path: Path, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test cold cache → fetch → warm cache → serve from cache flow."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Verify cache is cold (no file exists)
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        assert not cache_path.exists()

        # Mock database query for thumbnail_url
        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = ("https://example.com/thumbnail.jpg",)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock successful HTTP fetch
        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = valid_image

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            # First request: cold cache (MISS)
            response1 = await service.get_channel_image(
                session=mock_db_session,
                channel_id=channel_id,
            )

        assert response1.status_code == 200
        assert response1.headers["X-Cache"] == "MISS"
        assert cache_path.exists()
        assert cache_path.read_bytes() == valid_image

        # Second request: warm cache (HIT, no network call)
        response2 = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )

        assert response2.status_code == 200
        assert response2.headers["X-Cache"] == "HIT"
        assert response2.headers["Cache-Control"] == _CACHE_CONTROL_HIT

    async def test_cache_hit_response_time_under_50ms(
        self, tmp_path: Path, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test cache hit response completes in under 50ms (NFR-003 timing assertion)."""
        import time

        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[1]

        # Pre-populate cache
        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(valid_image)

        mock_db_session = AsyncMock()

        # Measure cache hit response time
        start_time = time.monotonic()
        response = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )
        elapsed_ms = (time.monotonic() - start_time) * 1000

        assert response.status_code == 200
        assert response.headers["X-Cache"] == "HIT"
        assert elapsed_ms < 50.0, f"Cache hit took {elapsed_ms:.2f}ms, expected < 50ms"

    async def test_proper_x_cache_headers(
        self, tmp_path: Path, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test proper X-Cache headers: MISS on first request, HIT on second."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[2]

        # Mock database query
        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = ("https://example.com/thumb.jpg",)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock HTTP response
        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = valid_image

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            # First request: MISS
            response1 = await service.get_channel_image(
                session=mock_db_session,
                channel_id=channel_id,
            )

        assert response1.headers["X-Cache"] == "MISS"

        # Second request: HIT
        response2 = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )

        assert response2.headers["X-Cache"] == "HIT"

    async def test_cache_control_header_for_real_images(
        self, tmp_path: Path, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test Cache-Control header: public, max-age=604800, immutable for real images."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[3]

        # Pre-populate cache
        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(valid_image)

        mock_db_session = AsyncMock()

        response = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )

        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "public, max-age=604800, immutable"
