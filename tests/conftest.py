"""
Pytest configuration and fixtures for chronovista tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from chronovista.config.settings import Settings


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
