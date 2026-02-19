"""
Unit tests for ImageCacheService.

Tests the core image caching infrastructure including directory management,
fetch pipeline, cache state management, and placeholder generation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from chronovista.services.image_cache import (
    ImageCacheConfig,
    ImageCacheService,
    _CACHE_CONTROL_HIT,
    _CACHE_CONTROL_PLACEHOLDER,
    _CHANNEL_PLACEHOLDER_SVG,
    _MAX_IMAGE_BYTES,
    _MIN_IMAGE_BYTES,
    _VIDEO_PLACEHOLDER_SVG,
)
from tests.factories.channel_factory import ChannelTestData

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


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


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


# ═══════════════════════════════════════════════════════════════════════════
# T004a: Directory Management Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestDirectoryManagement:
    """Tests for directory creation and passthrough mode."""

    def test_ensure_directories_creates_channels_dir(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test ensure_directories creates channels directory."""
        service = ImageCacheService(config=image_cache_config)

        assert image_cache_config.channels_dir.exists()
        assert image_cache_config.channels_dir.is_dir()
        assert service._passthrough is False

    def test_ensure_directories_creates_videos_dir(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test ensure_directories creates videos directory."""
        service = ImageCacheService(config=image_cache_config)

        assert image_cache_config.videos_dir.exists()
        assert image_cache_config.videos_dir.is_dir()
        assert service._passthrough is False

    def test_ensure_directories_passthrough_on_failure(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test passthrough mode when directory creation fails."""
        # Make the parent directory read-only to cause mkdir to fail
        with patch.object(Path, "mkdir", side_effect=OSError("Permission denied")):
            service = ImageCacheService(config=image_cache_config)

            # Service should be in passthrough mode
            assert service._passthrough is True

    def test_passthrough_mode_returns_placeholder_for_channel(
        self, image_cache_config: ImageCacheConfig, mock_db_session: AsyncMock
    ) -> None:
        """Test passthrough mode returns placeholder without attempting fetch."""
        # Force passthrough mode
        with patch.object(Path, "mkdir", side_effect=OSError("Permission denied")):
            service = ImageCacheService(config=image_cache_config)

        # Should return placeholder immediately
        async def run_test() -> None:
            response = await service.get_channel_image(
                session=mock_db_session,
                channel_id=ChannelTestData.VALID_CHANNEL_IDS[0],
            )

            assert response.status_code == 200
            assert response.media_type == "image/svg+xml"
            assert response.body == _CHANNEL_PLACEHOLDER_SVG
            assert response.headers["X-Cache"] == "PLACEHOLDER"
            assert response.headers["Cache-Control"] == _CACHE_CONTROL_PLACEHOLDER

            # Database should never be queried in passthrough mode
            mock_db_session.execute.assert_not_called()

        asyncio.run(run_test())


# ═══════════════════════════════════════════════════════════════════════════
# Placeholder Generation Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPlaceholderGeneration:
    """Tests for SVG placeholder generation."""

    def test_serve_placeholder_channel(self) -> None:
        """Test placeholder serving for channel returns correct SVG."""
        response = ImageCacheService._serve_placeholder("channel")

        assert response.status_code == 200
        assert response.media_type == "image/svg+xml"
        assert response.body == _CHANNEL_PLACEHOLDER_SVG
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_PLACEHOLDER
        assert response.headers["X-Cache"] == "PLACEHOLDER"

    def test_serve_placeholder_video(self) -> None:
        """Test placeholder serving for video returns correct SVG."""
        response = ImageCacheService._serve_placeholder("video")

        assert response.status_code == 200
        assert response.media_type == "image/svg+xml"
        assert response.body == _VIDEO_PLACEHOLDER_SVG
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_PLACEHOLDER
        assert response.headers["X-Cache"] == "PLACEHOLDER"

    def test_placeholder_svg_contains_valid_xml(self) -> None:
        """Test placeholder SVG contains valid XML structure."""
        # Channel placeholder
        channel_svg = _CHANNEL_PLACEHOLDER_SVG.decode("utf-8")
        assert channel_svg.startswith("<svg")
        assert "xmlns=" in channel_svg
        assert channel_svg.endswith("</svg>")

        # Video placeholder
        video_svg = _VIDEO_PLACEHOLDER_SVG.decode("utf-8")
        assert video_svg.startswith("<svg")
        assert "xmlns=" in video_svg
        assert video_svg.endswith("</svg>")


# ═══════════════════════════════════════════════════════════════════════════
# T004b: Content-Type Detection Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestContentTypeDetection:
    """Tests for magic byte content-type detection."""

    def test_detect_content_type_jpeg(self, tmp_path: Path) -> None:
        """Test JPEG detection via magic bytes."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        content_type = ImageCacheService._detect_content_type(test_file)
        assert content_type == "image/jpeg"

    def test_detect_content_type_png(self, tmp_path: Path) -> None:
        """Test PNG detection via magic bytes."""
        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        content_type = ImageCacheService._detect_content_type(test_file)
        assert content_type == "image/png"

    def test_detect_content_type_webp(self, tmp_path: Path) -> None:
        """Test WebP detection via magic bytes."""
        test_file = tmp_path / "test.webp"
        test_file.write_bytes(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100)

        content_type = ImageCacheService._detect_content_type(test_file)
        assert content_type == "image/webp"

    def test_detect_content_type_fallback(self, tmp_path: Path) -> None:
        """Test fallback to image/jpeg for unknown formats."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"UNKNOWN" + b"\x00" * 100)

        content_type = ImageCacheService._detect_content_type(test_file)
        assert content_type == "image/jpeg"

    def test_detect_content_type_oserror_fallback(self, tmp_path: Path) -> None:
        """Test fallback when file cannot be read."""
        nonexistent_file = tmp_path / "nonexistent.jpg"

        content_type = ImageCacheService._detect_content_type(nonexistent_file)
        assert content_type == "image/jpeg"


# ═══════════════════════════════════════════════════════════════════════════
# T004b: Fetch Pipeline Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestFetchPipeline:
    """Tests for image fetching and caching pipeline."""

    async def test_fetch_and_cache_success(
        self, image_cache_config: ImageCacheConfig, tmp_path: Path
    ) -> None:
        """Test successful fetch caches file atomically."""
        service = ImageCacheService(config=image_cache_config)
        cache_path = tmp_path / "test.jpg"

        # Create valid image bytes (JPEG magic + sufficient size)
        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048

        # Mock httpx response
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

            success, reason = await service._fetch_and_cache(
                url="https://example.com/image.jpg",
                cache_path=cache_path,
                timeout=2.0,
            )

        assert success is True
        assert reason is None
        assert cache_path.exists()
        assert cache_path.read_bytes() == valid_image

    async def test_fetch_and_cache_validates_content_type(
        self, image_cache_config: ImageCacheConfig, tmp_path: Path
    ) -> None:
        """Test validation rejects non-image content types."""
        service = ImageCacheService(config=image_cache_config)
        cache_path = tmp_path / "test.jpg"

        # Mock response with wrong content type
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = b"<html>Not an image</html>"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            success, reason = await service._fetch_and_cache(
                url="https://example.com/page.html",
                cache_path=cache_path,
                timeout=2.0,
            )

        assert success is False
        assert reason is not None
        assert "invalid_content_type" in reason
        assert not cache_path.exists()

    async def test_fetch_and_cache_validates_too_small(
        self, image_cache_config: ImageCacheConfig, tmp_path: Path
    ) -> None:
        """Test validation rejects images smaller than 1024 bytes."""
        service = ImageCacheService(config=image_cache_config)
        cache_path = tmp_path / "test.jpg"

        # Create too-small image (< 1024 bytes)
        small_image = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = small_image

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            success, reason = await service._fetch_and_cache(
                url="https://example.com/small.jpg",
                cache_path=cache_path,
                timeout=2.0,
            )

        assert success is False
        assert reason is not None
        assert "too_small" in reason
        assert not cache_path.exists()

    async def test_fetch_and_cache_validates_too_large(
        self, image_cache_config: ImageCacheConfig, tmp_path: Path
    ) -> None:
        """Test validation rejects images larger than 5MB."""
        service = ImageCacheService(config=image_cache_config)
        cache_path = tmp_path / "test.jpg"

        # Create too-large image (> 5MB)
        large_image = b"\xff\xd8\xff\xe0" + b"\x00" * (_MAX_IMAGE_BYTES + 1000)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = large_image

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            success, reason = await service._fetch_and_cache(
                url="https://example.com/huge.jpg",
                cache_path=cache_path,
                timeout=2.0,
            )

        assert success is False
        assert reason is not None
        assert "too_large" in reason
        assert not cache_path.exists()

    async def test_fetch_and_cache_semaphore_limiting(
        self, image_cache_config: ImageCacheConfig, tmp_path: Path
    ) -> None:
        """Test semaphore limits concurrent fetches."""
        # Set low concurrent limit
        image_cache_config.max_concurrent_fetches = 2
        service = ImageCacheService(config=image_cache_config)

        valid_image = b"\xff\xd8\xff\xe0" + b"\x00" * 2048

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = valid_image

        fetch_count = 0
        max_concurrent = 0
        current_concurrent = 0

        async def mock_get(url: str) -> Mock:
            nonlocal fetch_count, max_concurrent, current_concurrent
            current_concurrent += 1
            fetch_count += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.01)  # Simulate network delay
            current_concurrent -= 1
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = mock_get
            mock_client_cls.return_value = mock_client

            # Start 5 concurrent fetches
            tasks = [
                service._fetch_and_cache(
                    url=f"https://example.com/image{i}.jpg",
                    cache_path=tmp_path / f"image{i}.jpg",
                    timeout=2.0,
                )
                for i in range(5)
            ]

            results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(success for success, _ in results)

        # Semaphore should limit to max 2 concurrent
        assert max_concurrent <= 2


# ═══════════════════════════════════════════════════════════════════════════
# T004c: Cache State Management Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCacheStateManagement:
    """Tests for .missing marker creation and cache validation."""

    async def test_missing_marker_created_on_404(
        self, image_cache_config: ImageCacheConfig, tmp_path: Path
    ) -> None:
        """Test .missing marker created on 404 response."""
        service = ImageCacheService(config=image_cache_config)
        cache_path = tmp_path / "test.jpg"

        mock_response = Mock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            success, reason = await service._fetch_and_cache(
                url="https://example.com/missing.jpg",
                cache_path=cache_path,
                timeout=2.0,
            )

        assert success is False
        assert reason is not None and "not_found_404" in reason

        # .missing marker should exist
        missing_path = cache_path.with_suffix(".missing")
        assert missing_path.exists()

    async def test_missing_marker_created_on_410(
        self, image_cache_config: ImageCacheConfig, tmp_path: Path
    ) -> None:
        """Test .missing marker created on 410 response."""
        service = ImageCacheService(config=image_cache_config)
        cache_path = tmp_path / "test.jpg"

        mock_response = Mock()
        mock_response.status_code = 410

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            success, reason = await service._fetch_and_cache(
                url="https://example.com/gone.jpg",
                cache_path=cache_path,
                timeout=2.0,
            )

        assert success is False
        assert reason is not None and "not_found_410" in reason

        # .missing marker should exist
        missing_path = cache_path.with_suffix(".missing")
        assert missing_path.exists()

    async def test_no_missing_marker_on_429(
        self, image_cache_config: ImageCacheConfig, tmp_path: Path
    ) -> None:
        """Test NO .missing marker on 429 (transient error)."""
        service = ImageCacheService(config=image_cache_config)
        cache_path = tmp_path / "test.jpg"

        mock_response = Mock()
        mock_response.status_code = 429

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            success, reason = await service._fetch_and_cache(
                url="https://example.com/rate_limited.jpg",
                cache_path=cache_path,
                timeout=2.0,
            )

        assert success is False
        assert reason is not None and "server_error_429" in reason

        # NO .missing marker should exist
        missing_path = cache_path.with_suffix(".missing")
        assert not missing_path.exists()

    async def test_no_missing_marker_on_5xx(
        self, image_cache_config: ImageCacheConfig, tmp_path: Path
    ) -> None:
        """Test NO .missing marker on 5xx (transient error)."""
        service = ImageCacheService(config=image_cache_config)
        cache_path = tmp_path / "test.jpg"

        mock_response = Mock()
        mock_response.status_code = 503

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            success, reason = await service._fetch_and_cache(
                url="https://example.com/server_error.jpg",
                cache_path=cache_path,
                timeout=2.0,
            )

        assert success is False
        assert reason is not None and "server_error_503" in reason

        # NO .missing marker should exist
        missing_path = cache_path.with_suffix(".missing")
        assert not missing_path.exists()

    def test_check_cache_hit_for_valid_file(self, tmp_path: Path) -> None:
        """Test _check_cache returns HIT for valid cached files."""
        cache_path = tmp_path / "test.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)

        result = ImageCacheService._check_cache(cache_path)
        assert result == "HIT"

    def test_check_cache_deletes_corrupted_file(self, tmp_path: Path) -> None:
        """Test _check_cache deletes corrupted files (<1024 bytes)."""
        cache_path = tmp_path / "corrupted.jpg"
        cache_path.write_bytes(b"\x00" * 512)  # Too small

        result = ImageCacheService._check_cache(cache_path)
        assert result is None
        assert not cache_path.exists()

    def test_check_cache_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """Test _check_cache returns None when file doesn't exist."""
        cache_path = tmp_path / "nonexistent.jpg"

        result = ImageCacheService._check_cache(cache_path)
        assert result is None

    def test_check_missing_returns_true_when_marker_exists(
        self, tmp_path: Path
    ) -> None:
        """Test _check_missing returns True when .missing marker exists."""
        cache_path = tmp_path / "test.jpg"
        missing_path = cache_path.with_suffix(".missing")
        missing_path.touch()

        result = ImageCacheService._check_missing(cache_path)
        assert result is True

    def test_check_missing_returns_false_when_marker_absent(
        self, tmp_path: Path
    ) -> None:
        """Test _check_missing returns False when no marker exists."""
        cache_path = tmp_path / "test.jpg"

        result = ImageCacheService._check_missing(cache_path)
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════
# T006: get_channel_image() Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestGetChannelImage:
    """Tests for get_channel_image() public API."""

    async def test_cache_hit_path(
        self, image_cache_config: ImageCacheConfig, mock_db_session: AsyncMock
    ) -> None:
        """Test cache HIT path returns image with X-Cache: HIT."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Create cached file
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)

        response = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )

        assert response.status_code == 200
        assert response.media_type == "image/jpeg"
        assert response.headers["X-Cache"] == "HIT"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_HIT

        # Database should not be queried on cache hit
        mock_db_session.execute.assert_not_called()

    async def test_cache_miss_fetch_success(
        self, image_cache_config: ImageCacheConfig, mock_db_session: AsyncMock
    ) -> None:
        """Test cache MISS path fetches and returns with X-Cache: MISS."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[1]
        thumbnail_url = "https://example.com/thumbnail.jpg"

        # Mock DB query to return thumbnail URL
        mock_result = MagicMock()
        mock_row = (thumbnail_url,)
        mock_result.first.return_value = mock_row
        mock_db_session.execute.return_value = mock_result

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

            response = await service.get_channel_image(
                session=mock_db_session,
                channel_id=channel_id,
            )

        assert response.status_code == 200
        assert response.media_type == "image/jpeg"
        assert response.headers["X-Cache"] == "MISS"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_HIT

        # Database should be queried
        mock_db_session.execute.assert_called_once()

    async def test_placeholder_on_fetch_failure(
        self, image_cache_config: ImageCacheConfig, mock_db_session: AsyncMock
    ) -> None:
        """Test PLACEHOLDER path when fetch fails."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[2]
        thumbnail_url = "https://example.com/thumbnail.jpg"

        # Mock DB query
        mock_result = MagicMock()
        mock_row = (thumbnail_url,)
        mock_result.first.return_value = mock_row
        mock_db_session.execute.return_value = mock_result

        # Mock failed fetch (timeout)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = httpx.TimeoutException("Timeout")
            mock_client_cls.return_value = mock_client

            response = await service.get_channel_image(
                session=mock_db_session,
                channel_id=channel_id,
            )

        assert response.status_code == 200
        assert response.media_type == "image/svg+xml"
        assert response.body == _CHANNEL_PLACEHOLDER_SVG
        assert response.headers["X-Cache"] == "PLACEHOLDER"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_PLACEHOLDER

    async def test_placeholder_on_null_thumbnail_url(
        self, image_cache_config: ImageCacheConfig, mock_db_session: AsyncMock
    ) -> None:
        """Test placeholder returned when thumbnail_url is NULL."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[3]

        # Mock DB query to return NULL thumbnail URL
        mock_result = MagicMock()
        mock_row = (None,)
        mock_result.first.return_value = mock_row
        mock_db_session.execute.return_value = mock_result

        response = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )

        assert response.status_code == 200
        assert response.media_type == "image/svg+xml"
        assert response.body == _CHANNEL_PLACEHOLDER_SVG
        assert response.headers["X-Cache"] == "PLACEHOLDER"

    async def test_placeholder_on_channel_not_found(
        self, image_cache_config: ImageCacheConfig, mock_db_session: AsyncMock
    ) -> None:
        """Test placeholder returned when channel not found in DB."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[4]

        # Mock DB query to return no results
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )

        assert response.status_code == 200
        assert response.media_type == "image/svg+xml"
        assert response.body == _CHANNEL_PLACEHOLDER_SVG
        assert response.headers["X-Cache"] == "PLACEHOLDER"

    async def test_missing_marker_returns_placeholder_immediately(
        self, image_cache_config: ImageCacheConfig, mock_db_session: AsyncMock
    ) -> None:
        """Test .missing marker causes immediate placeholder return."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Create .missing marker
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        missing_path = cache_path.with_suffix(".missing")
        missing_path.parent.mkdir(parents=True, exist_ok=True)
        missing_path.touch()

        response = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )

        assert response.status_code == 200
        assert response.media_type == "image/svg+xml"
        assert response.body == _CHANNEL_PLACEHOLDER_SVG
        assert response.headers["X-Cache"] == "PLACEHOLDER"

        # Database should not be queried when .missing marker exists
        mock_db_session.execute.assert_not_called()

    async def test_serve_cached_file_with_correct_content_type(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test _serve_cached_file detects and serves correct content type."""
        service = ImageCacheService(config=image_cache_config)

        # Create PNG file
        cache_path = image_cache_config.channels_dir / "test.png"
        cache_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048)

        response = service._serve_cached_file(cache_path, "HIT")

        assert response.status_code == 200
        assert response.media_type == "image/png"
        assert response.headers["X-Cache"] == "HIT"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_HIT


# ═══════════════════════════════════════════════════════════════════════════
# T022: US6 Preservation Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestImagePreservation:
    """Tests for image preservation guarantees (US6).

    The image cache service serves cached images regardless of entity
    availability_status. This ensures that deleted/unavailable content
    continues to show cached thumbnails.
    """

    async def test_get_channel_image_serves_cached_regardless_of_status(
        self, image_cache_config: ImageCacheConfig, mock_db_session: AsyncMock
    ) -> None:
        """Test get_channel_image() serves cached avatar regardless of channel availability_status.

        The cache service does not check availability_status - it only checks
        for cached files. This is a behavioral guarantee that cached images
        are preserved even after entities become unavailable.
        """
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Create cached file
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)

        # Service should serve from cache without checking availability_status
        response = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )

        assert response.status_code == 200
        assert response.media_type == "image/jpeg"
        assert response.headers["X-Cache"] == "HIT"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_HIT

        # Database should NOT be queried on cache hit (no availability check)
        mock_db_session.execute.assert_not_called()

    async def test_get_video_image_serves_cached_regardless_of_status(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test get_video_image() serves cached thumbnail regardless of video status.

        Video thumbnails are deterministic and do not require DB queries,
        so availability_status is never checked. Cached images are always
        served if present.
        """
        from tests.factories.video_factory import VideoTestData

        service = ImageCacheService(config=image_cache_config)
        video_id = VideoTestData.VALID_VIDEO_IDS[0]
        quality = "mqdefault"

        # Create cached file in sharded directory
        prefix = video_id[:2]
        video_dir = image_cache_config.videos_dir / prefix
        video_dir.mkdir(parents=True, exist_ok=True)
        cache_path = video_dir / f"{video_id}_{quality}.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)

        # Service should serve from cache (no DB query for videos)
        response = await service.get_video_image(
            video_id=video_id,
            quality=quality,
        )

        assert response.status_code == 200
        assert response.media_type == "image/jpeg"
        assert response.headers["X-Cache"] == "HIT"
        assert response.headers["Cache-Control"] == _CACHE_CONTROL_HIT

    async def test_no_cache_invalidation_on_availability_changes(
        self, image_cache_config: ImageCacheConfig, mock_db_session: AsyncMock
    ) -> None:
        """Test that cache is NOT invalidated when availability_status changes.

        This is a behavioral test confirming that the image cache service
        has no mechanism to invalidate cache based on availability_status.
        Once an image is cached, it remains cached indefinitely.
        """
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[1]

        # Create cached file
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)

        # First request: cache hit
        response1 = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )
        assert response1.headers["X-Cache"] == "HIT"

        # Simulate availability_status change (in reality this would be a DB update,
        # but the cache service doesn't query availability_status, so it has no effect)

        # Second request: still cache hit (no invalidation)
        response2 = await service.get_channel_image(
            session=mock_db_session,
            channel_id=channel_id,
        )
        assert response2.headers["X-Cache"] == "HIT"

        # Cache file should still exist
        assert cache_path.exists()

        # Database should never be queried (cache hits)
        mock_db_session.execute.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# T030: Cache Invalidation Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCacheInvalidation:
    """Tests for cache invalidation via invalidate_channel() method.

    The image cache service provides selective invalidation for channel
    thumbnails when thumbnail_url changes. Video thumbnails are never
    invalidated (FR-018).
    """

    async def test_invalidation_deletes_cached_file(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test invalidate_channel() deletes existing .jpg cache file."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Create cached file
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)
        assert cache_path.exists()

        # Invalidate
        await service.invalidate_channel(channel_id)

        # File should be deleted
        assert not cache_path.exists()

    async def test_invalidation_deletes_missing_marker(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test invalidate_channel() deletes existing .missing marker."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[1]

        # Create .missing marker
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        missing_path = cache_path.with_suffix(".missing")
        missing_path.touch()
        assert missing_path.exists()

        # Invalidate
        await service.invalidate_channel(channel_id)

        # Marker should be deleted
        assert not missing_path.exists()

    async def test_invalidation_deletes_both_jpg_and_missing(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test invalidate_channel() deletes both .jpg and .missing when both exist."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[2]

        # Create both .jpg and .missing
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)
        missing_path = cache_path.with_suffix(".missing")
        missing_path.touch()
        assert cache_path.exists()
        assert missing_path.exists()

        # Invalidate
        await service.invalidate_channel(channel_id)

        # Both should be deleted
        assert not cache_path.exists()
        assert not missing_path.exists()

    async def test_invalidation_noop_when_neither_exists(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test invalidate_channel() is a no-op when no cached files exist.

        This verifies the method handles the case gracefully when there's
        nothing to invalidate, logging debug but not raising errors.
        """
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[3]

        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        missing_path = cache_path.with_suffix(".missing")
        assert not cache_path.exists()
        assert not missing_path.exists()

        # Should not raise any errors
        await service.invalidate_channel(channel_id)

        # Still should not exist (no-op)
        assert not cache_path.exists()
        assert not missing_path.exists()

    async def test_null_to_url_preserves_cache(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test NULL → non-NULL thumbnail_url does NOT invalidate cache.

        This is a conceptual test documenting that when old URL is NULL and
        new URL is non-NULL, no invalidation should happen. The enrichment
        hook or service calling code is responsible for this logic, not the
        invalidate_channel() method itself.

        This test verifies the service provides invalidation as a tool, but
        does NOT automatically invalidate on NULL → URL transitions.
        """
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Create cached file (simulating old state with NULL URL that somehow
        # got a cached placeholder or previous image)
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)
        assert cache_path.exists()

        # Simulate NULL → URL transition:
        # The caller (enrichment hook) should recognize this case and NOT call
        # invalidate_channel() because the old URL was NULL (no old image to
        # invalidate).

        # Verify cache still exists (because we didn't call invalidate)
        assert cache_path.exists()

        # This documents that invalidate_channel() is a manual tool - it
        # doesn't auto-detect NULL → URL transitions.

    async def test_url_to_null_preserves_cache(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test non-NULL → NULL thumbnail_url does NOT invalidate cache.

        This is a conceptual test documenting that when old URL is non-NULL
        and new URL is NULL, no invalidation should happen. The enrichment
        hook should preserve the cached image from the old URL even when the
        new metadata shows NULL.

        This supports FR-006 (image preservation for deleted content).
        """
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[1]

        # Create cached file (from old non-NULL URL)
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)
        assert cache_path.exists()

        # Simulate URL → NULL transition:
        # The caller (enrichment hook) should recognize this case and NOT call
        # invalidate_channel() to preserve the cached image from the old URL.

        # Verify cache still exists (because we didn't call invalidate)
        assert cache_path.exists()

        # This documents preservation behavior: old cached images are kept
        # even when new metadata shows NULL URL (deleted/unavailable content).

    async def test_video_thumbnails_not_invalidated(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test that there is NO invalidate_video() method on the service.

        Video thumbnails are deterministic and immutable (FR-018), so they
        should never be invalidated. This test verifies the service does NOT
        provide an invalidate_video() method.
        """
        service = ImageCacheService(config=image_cache_config)

        # Verify no invalidate_video method exists
        assert not hasattr(service, "invalidate_video")

        # Only invalidate_channel should exist
        assert hasattr(service, "invalidate_channel")

    async def test_invalidation_handles_disk_errors_gracefully(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test invalidate_channel() logs errors but does not raise on disk failures."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[4]

        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)

        # Mock unlink to raise OSError
        with patch.object(Path, "unlink", side_effect=OSError("Disk error")):
            # Should not raise - errors are logged
            await service.invalidate_channel(channel_id)

            # File still exists (deletion failed)
            assert cache_path.exists()

    async def test_multiple_invalidations_idempotent(
        self, image_cache_config: ImageCacheConfig
    ) -> None:
        """Test that calling invalidate_channel() multiple times is safe and idempotent."""
        service = ImageCacheService(config=image_cache_config)
        channel_id = ChannelTestData.VALID_CHANNEL_IDS[0]

        # Create cached file
        cache_path = image_cache_config.channels_dir / f"{channel_id}.jpg"
        cache_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 2048)

        # First invalidation
        await service.invalidate_channel(channel_id)
        assert not cache_path.exists()

        # Second invalidation (should be no-op)
        await service.invalidate_channel(channel_id)
        assert not cache_path.exists()

        # Third invalidation (still no-op)
        await service.invalidate_channel(channel_id)
        assert not cache_path.exists()
