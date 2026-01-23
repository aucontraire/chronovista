"""
Pytest configuration and fixtures for chronovista tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(
    0, str(Path(__file__).parent.parent)
)  # Add project root to path for tests imports
from chronovista.config.settings import Settings
from chronovista.container import container


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    return Settings(
        youtube_api_key="test_api_key",
        youtube_client_id="test_client_id",
        youtube_client_secret="test_client_secret",
        secret_key="test_secret_key",
        database_url="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture
def mock_youtube_client():
    """Mock YouTube API client."""
    client = MagicMock()
    client.videos().list.return_value.execute.return_value = {
        "items": [
            {
                "id": "test_video_id",
                "snippet": {
                    "title": "Test Video",
                    "channelTitle": "Test Channel",
                    "publishedAt": "2023-01-01T00:00:00Z",
                },
                "contentDetails": {"duration": "PT10M30S"},
                "statistics": {"viewCount": "1000", "likeCount": "50"},
            }
        ]
    }
    return client


# =============================================================================
# Container Testing Fixtures (US4: T047-T048)
# =============================================================================


@pytest.fixture
def mock_youtube_service():
    """
    Provide a mock YouTubeService for container testing.

    This fixture allows tests to inject a mock service without hitting
    the real YouTube API or requiring credentials.

    Examples
    --------
    >>> def test_something(mock_youtube_service):
    ...     container.__dict__['youtube_service'] = mock_youtube_service
    ...     assert container.youtube_service is mock_youtube_service
    """
    from chronovista.services import YouTubeService

    mock_service = MagicMock(spec=YouTubeService, name="MockYouTubeService")
    mock_service.check_credentials.return_value = True
    return mock_service


@pytest.fixture(autouse=True)
def container_reset():
    """
    Automatically reset the container after each test.

    This fixture ensures test isolation by clearing all cached singletons
    from the container after each test runs. It uses autouse=True so it
    applies to all tests without explicit declaration.

    This implements US4 (T048) for fixture teardown.

    Examples
    --------
    >>> def test_something():
    ...     # Container is clean at start
    ...     _ = container.youtube_service  # Cache a singleton
    ...     # After test, container_reset automatically runs
    ...     # Next test gets a fresh container
    """
    # Setup: nothing needed (container starts clean)
    yield
    # Teardown: reset container to clear all cached singletons
    container.reset()
