"""
Shared fixtures and configuration for YouTube API integration tests.

Provides authenticated YouTube service, database sessions, and test data
fixtures for systematic integration testing across model tiers.
"""

from __future__ import annotations

import os
from typing import Any, Awaitable, Dict

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from chronovista.auth.oauth_service import YouTubeOAuthService
from chronovista.config.settings import get_settings
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.user_language_preference_repository import (
    UserLanguagePreferenceRepository,
)
from chronovista.repositories.user_video_repository import UserVideoRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)
from chronovista.services.youtube_service import YouTubeService


@pytest.fixture(scope="session")
def settings():
    """Get application settings for integration tests."""
    return get_settings()


@pytest.fixture(scope="function")
def integration_db_engine(settings):
    """Create database engine for integration tests."""
    # Use a separate test database for integration tests
    # First try the environment variable, then fall back to dev database with different db name
    test_db_url = os.getenv(
        "DATABASE_INTEGRATION_URL",
        os.getenv(
            "CHRONOVISTA_INTEGRATION_DB_URL",
            "postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test",
        ),
    )

    engine = create_async_engine(
        test_db_url,
        echo=False,  # Set to True for SQL debugging
        pool_pre_ping=True,
    )

    return engine


@pytest.fixture(scope="function")
def integration_session_factory(integration_db_engine):
    """Create session factory for integration tests."""
    return async_sessionmaker(
        integration_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
def integration_db_session(integration_session_factory):
    """Provide database session factory for integration tests."""
    return integration_session_factory


@pytest.fixture
def oauth_service(settings) -> YouTubeOAuthService:
    """Provide OAuth service for YouTube API authentication."""
    return YouTubeOAuthService()


@pytest.fixture
def authenticated_youtube_service(oauth_service) -> YouTubeService | None:
    """
    Provide authenticated YouTube service for API calls.

    Skips tests if authentication is not available or configured.
    Set CHRONOVISTA_SKIP_API_TESTS=true to skip all API tests.
    """
    if os.getenv("CHRONOVISTA_SKIP_API_TESTS", "false").lower() == "true":
        pytest.skip("API tests disabled by CHRONOVISTA_SKIP_API_TESTS")

    try:
        # Check if user is authenticated
        if not oauth_service.is_authenticated():
            pytest.skip("No valid YouTube API credentials available")

        return YouTubeService()
    except Exception as e:
        pytest.skip(f"Failed to authenticate YouTube service: {e}")


@pytest.fixture
def channel_repository() -> ChannelRepository:
    """Provide channel repository for integration tests."""
    return ChannelRepository()


@pytest.fixture
def video_repository() -> VideoRepository:
    """Provide video repository for integration tests."""
    return VideoRepository()


@pytest.fixture
def video_transcript_repository() -> VideoTranscriptRepository:
    """Provide video transcript repository for integration tests."""
    return VideoTranscriptRepository()


@pytest.fixture
def user_language_preference_repository() -> UserLanguagePreferenceRepository:
    """Provide user language preference repository for integration tests."""
    return UserLanguagePreferenceRepository()


@pytest.fixture
def user_video_repository() -> UserVideoRepository:
    """Provide user video repository for integration tests."""
    return UserVideoRepository()


@pytest.fixture
def test_user_id() -> str:
    """Provide consistent test user ID for integration tests."""
    return "integration_test_user"


@pytest.fixture
def sample_youtube_channel_ids() -> list[str]:
    """
    Provide sample YouTube channel IDs for testing.

    These are well-known, stable channels for consistent testing.
    """
    return [
        "UCuAXFkgsw1L7xaCfnd5JJOw",  # Rick Astley (stable, english content)
        "UC_x5XG1OV2P6uZZ5FSM9Ttw",  # Google Developers (stable, tech content)
        "UCMtFAi84ehTSYSE9XoHefig",  # The Late Show with Stephen Colbert (stable, many videos)
    ]


@pytest.fixture
def sample_youtube_video_ids() -> list[str]:
    """
    Provide sample YouTube video IDs for testing.

    These are well-known, stable videos for consistent testing.
    """
    return [
        "dQw4w9WgXcQ",  # Rick Astley - Never Gonna Give You Up (has captions)
        "9bZkp7q19f0",  # Google I/O (tech content, good for transcripts)
        "jNQXAC9IVRw",  # Popular tech review (multilingual potential)
    ]


@pytest.fixture(scope="function")
async def established_channel(
    authenticated_youtube_service,
    integration_db_session,
    sample_youtube_channel_ids,
) -> Dict[str, Any] | None:
    """
    Provide an established channel in the database for dependent model testing.

    Creates a channel from YouTube API data and persists it to the database.
    Returns the channel data for use in dependent tests.
    """
    if not authenticated_youtube_service:
        pytest.skip("YouTube service not available")

    try:
        # Use the first sample channel ID
        channel_id = sample_youtube_channel_ids[0]

        async with integration_db_session() as session:
            # Get channel data from YouTube API
            api_channel_data = await authenticated_youtube_service.get_channel_details(
                channel_id
            )

            # Create channel in database using repository
            from chronovista.db.models import Channel as DBChannel
            from chronovista.models.channel import ChannelCreate, ChannelUpdate
            from chronovista.repositories.base import BaseSQLAlchemyRepository

            channel_repo: BaseSQLAlchemyRepository[
                DBChannel, ChannelCreate, ChannelUpdate
            ] = BaseSQLAlchemyRepository(DBChannel)

            # First check if channel already exists
            from sqlalchemy import select

            result = await session.execute(
                select(DBChannel).where(DBChannel.channel_id == api_channel_data["id"])
            )
            existing_channel = result.scalar_one_or_none()

            if existing_channel:
                # Channel already exists, use it
                db_channel = existing_channel
                # Using existing channel
            else:
                # Create new channel
                # Creating new channel

                # Handle default language properly with enum
                default_lang = api_channel_data["snippet"].get("defaultLanguage")
                if default_lang:
                    try:
                        from chronovista.models.enums import LanguageCode

                        # Try to convert string to enum, fallback to None if not found
                        default_language = LanguageCode(default_lang)
                    except ValueError:
                        default_language = None
                else:
                    default_language = None

                channel_create = ChannelCreate(
                    channel_id=api_channel_data["id"],
                    title=api_channel_data["snippet"]["title"],
                    description=api_channel_data["snippet"].get("description", ""),
                    default_language=default_language,
                    country=api_channel_data["snippet"].get("country", None),
                    subscriber_count=int(
                        api_channel_data.get("statistics", {}).get("subscriberCount", 0)
                    ),
                    video_count=int(
                        api_channel_data.get("statistics", {}).get("videoCount", 0)
                    ),
                    thumbnail_url=api_channel_data["snippet"]["thumbnails"]["default"][
                        "url"
                    ],
                )

                db_channel = await channel_repo.create(session, obj_in=channel_create)
                await session.commit()

            return {
                "channel_id": db_channel.channel_id,
                "api_data": api_channel_data,
                "db_model": db_channel,
            }
    except Exception as e:
        pytest.skip(f"Could not establish test channel: {e}")


@pytest.fixture(scope="function")
async def established_videos(
    authenticated_youtube_service,
    integration_db_session,
    established_channel: Awaitable[Dict[str, Any] | None],
    sample_youtube_video_ids,
) -> list[Dict[str, Any]] | None:
    """
    Provide established videos in the database for dependent model testing.

    Creates videos from YouTube API data and persists them to the database.
    Returns list of video data for use in dependent tests.
    """
    # Await the established_channel fixture since it's async
    established_channel_data = await established_channel

    if not authenticated_youtube_service or not established_channel_data:
        pytest.skip("Prerequisites not available")

    videos = []
    try:
        async with integration_db_session() as session:
            for video_id in sample_youtube_video_ids[
                :2
            ]:  # Limit to 2 videos for testing
                # Get video data from YouTube API
                video_details_list = (
                    await authenticated_youtube_service.get_video_details([video_id])
                )
                api_video_data = video_details_list[0] if video_details_list else None

                if not api_video_data:
                    continue  # Skip this video if not accessible

                # Create video in database using repository
                from datetime import datetime

                from chronovista.db.models import Video as DBVideo
                from chronovista.models.video import VideoCreate, VideoUpdate
                from chronovista.repositories.base import BaseSQLAlchemyRepository

                video_repo: BaseSQLAlchemyRepository[
                    DBVideo, VideoCreate, VideoUpdate
                ] = BaseSQLAlchemyRepository(DBVideo)

                # First check if video already exists
                from sqlalchemy import select

                result = await session.execute(
                    select(DBVideo).where(DBVideo.video_id == api_video_data["id"])
                )
                existing_video = result.scalar_one_or_none()

                if existing_video:
                    # Video already exists, use it
                    db_video = existing_video
                else:
                    # Create new video
                    # Handle default language properly with enum
                    default_lang = api_video_data["snippet"].get("defaultLanguage")
                    if default_lang:
                        try:
                            from chronovista.models.enums import LanguageCode

                            # Try to convert string to enum, fallback to None if not found
                            default_language = LanguageCode(default_lang)
                        except ValueError:
                            default_language = None
                    else:
                        default_language = None

                    video_create = VideoCreate(
                        video_id=api_video_data["id"],
                        channel_id=established_channel_data[
                            "channel_id"
                        ],  # Use established channel instead of API channel
                        title=api_video_data["snippet"]["title"],
                        description=api_video_data["snippet"].get("description", ""),
                        upload_date=datetime.fromisoformat(
                            api_video_data["snippet"]["publishedAt"].replace(
                                "Z", "+00:00"
                            )
                        ),
                        duration=300,  # Simplified for fixture
                        made_for_kids=api_video_data.get("status", {}).get(
                            "madeForKids", False
                        ),
                        default_language=default_language,
                        view_count=int(
                            api_video_data.get("statistics", {}).get("viewCount", 0)
                        ),
                        like_count=int(
                            api_video_data.get("statistics", {}).get("likeCount", 0)
                        ),
                        comment_count=int(
                            api_video_data.get("statistics", {}).get("commentCount", 0)
                        ),
                    )

                    db_video = await video_repo.create(session, obj_in=video_create)

                videos.append(
                    {
                        "video_id": db_video.video_id,
                        "api_data": api_video_data,
                        "db_model": db_video,
                    }
                )

            await session.commit()
            print(
                f"DEBUG: Returning {len(videos)} videos from established_videos fixture"
            )
            return videos
    except Exception as e:
        pytest.skip(f"Could not establish test videos: {e}")


# Pytest markers for integration tests
pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
]


def pytest_configure(config):
    """Configure pytest markers for integration tests."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring database"
    )
    config.addinivalue_line("markers", "api: mark test as requiring YouTube API access")
    config.addinivalue_line("markers", "e2e: mark test as end-to-end integration test")
    config.addinivalue_line(
        "markers", "resilience: mark test as API resilience/error handling test"
    )
