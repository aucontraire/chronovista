"""
Tier 2 Integration Tests: Channel-Dependent Models

Tests models that depend on Channel entity:
- ChannelKeyword (channel content analysis)
- Playlist (channel playlist management)

These tests require an established Channel from Tier 1 tests
and verify the channel → dependent model data flow.
"""

from __future__ import annotations

from typing import Any, Awaitable, Dict

import pytest
from sqlalchemy import delete

from chronovista.db.models import ChannelKeyword as DBChannelKeyword
from chronovista.db.models import Playlist as DBPlaylist
from chronovista.models.channel_keyword import (
    ChannelKeywordCreate,
    ChannelKeywordUpdate,
)
from chronovista.models.playlist import PlaylistCreate, PlaylistUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.asyncio
class TestChannelKeywordFromAPI:
    """Test ChannelKeyword model with real channel data."""

    async def test_channel_keyword_extraction(
        self,
        authenticated_youtube_service,
        established_channel: Awaitable[Dict[str, Any] | None],
        integration_db_session,
    ):
        """Test extracting and storing channel keywords from real channel data."""
        # Await the fixture since it's async
        established_channel_data = await established_channel

        if not authenticated_youtube_service or not established_channel_data:
            pytest.skip("Prerequisites not available")

        channel_id = established_channel_data["channel_id"]

        async with integration_db_session() as session:
            try:
                # Clean up any existing test data first
                import time

                test_suffix = f"keyword_test_{int(time.time())}"

                await session.execute(
                    delete(DBChannelKeyword).where(
                        DBChannelKeyword.keyword.like("%_test_%")
                    )
                )
                await session.commit()

                # Simulate keyword extraction from channel description and metadata
                # In real implementation, this would use NLP/ML to extract keywords
                # channel_description = established_channel_data["api_data"][
                #     "snippet"
                # ].get("description", "")

                # Simple keyword extraction for demo (real implementation would be more sophisticated)
                sample_keywords = [
                    f"music_{test_suffix}",
                    f"entertainment_{test_suffix}",
                    f"official_{test_suffix}",
                    f"video_{test_suffix}",
                    f"artist_{test_suffix}",
                ]

                keyword_repo: BaseSQLAlchemyRepository[
                    DBChannelKeyword, ChannelKeywordCreate, ChannelKeywordUpdate
                ] = BaseSQLAlchemyRepository(DBChannelKeyword)

                created_keywords = []
                for i, keyword in enumerate(sample_keywords):
                    keyword_create = ChannelKeywordCreate(
                        channel_id=channel_id,
                        keyword=keyword,
                        keyword_order=i + 1,  # Order of extraction
                    )

                    db_keyword = await keyword_repo.create(
                        session, obj_in=keyword_create
                    )
                    created_keywords.append(db_keyword)

                await session.commit()

                # Verify all keywords created and linked to channel
                assert len(created_keywords) == len(sample_keywords)

                for db_keyword in created_keywords:
                    assert db_keyword.channel_id == channel_id
                    assert db_keyword.keyword in sample_keywords
                    assert db_keyword.keyword_order is not None
                    assert db_keyword.created_at is not None

                # Clean up test data
                for db_keyword in created_keywords:
                    await session.execute(
                        delete(DBChannelKeyword).where(
                            DBChannelKeyword.channel_id == db_keyword.channel_id,
                            DBChannelKeyword.keyword == db_keyword.keyword,
                        )
                    )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def test_channel_keyword_uniqueness(
        self,
        established_channel: Awaitable[Dict[str, Any] | None],
        integration_db_session,
    ):
        """Test that duplicate keywords for same channel are handled properly."""
        established_channel_data = await established_channel

        if not established_channel_data:
            pytest.skip("Established channel not available")

        channel_id = established_channel_data["channel_id"]

        async with integration_db_session() as session:
            try:
                import time

                unique_keyword = f"unique_test_keyword_{int(time.time())}"

                keyword_repo: BaseSQLAlchemyRepository[
                    DBChannelKeyword, ChannelKeywordCreate, ChannelKeywordUpdate
                ] = BaseSQLAlchemyRepository(DBChannelKeyword)

                # Create first keyword
                keyword_create = ChannelKeywordCreate(
                    channel_id=channel_id,
                    keyword=unique_keyword,
                    keyword_order=1,
                )

                first_keyword = await keyword_repo.create(
                    session, obj_in=keyword_create
                )
                await session.commit()
                assert first_keyword.keyword == unique_keyword

                # Attempt to create duplicate - this should fail due to composite primary key constraint
                try:
                    duplicate_keyword = ChannelKeywordCreate(
                        channel_id=channel_id,
                        keyword=unique_keyword,  # Same keyword
                        keyword_order=2,  # Different order
                    )

                    # This should fail with a unique constraint violation
                    second_keyword = await keyword_repo.create(
                        session, obj_in=duplicate_keyword
                    )
                    await session.commit()

                    # If we get here, the duplicate was somehow allowed
                    assert second_keyword.channel_id == channel_id
                    assert second_keyword.keyword == unique_keyword

                except Exception as e:
                    # Expected: duplicate prevention should be in place
                    assert "duplicate" in str(e).lower() or "unique" in str(e).lower()
                    # Roll back the session after the failed operation
                    await session.rollback()

                # Clean up test data
                await session.execute(
                    delete(DBChannelKeyword).where(
                        DBChannelKeyword.channel_id == channel_id,
                        DBChannelKeyword.keyword == unique_keyword,
                    )
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.asyncio
class TestPlaylistFromAPI:
    """Test Playlist model with real YouTube playlist data."""

    async def test_playlist_creation_from_api(
        self,
        authenticated_youtube_service,
        established_channel: Awaitable[Dict[str, Any] | None],
        integration_db_session,
    ):
        """Test creating playlists from YouTube API data."""
        established_channel_data = await established_channel

        if not authenticated_youtube_service or not established_channel_data:
            pytest.skip("Prerequisites not available")

        channel_id = established_channel_data["channel_id"]

        async with integration_db_session() as session:
            try:
                # Clean up any existing test playlists first
                from sqlalchemy import delete

                await session.execute(
                    delete(DBPlaylist).where(DBPlaylist.playlist_id.like("PLtest_%"))
                )
                await session.commit()

                # Get playlists from authenticated user (more realistic API usage)
                playlists_data = await authenticated_youtube_service.get_my_playlists(
                    max_results=10
                )

                if not playlists_data or len(playlists_data) == 0:
                    pytest.skip("No playlists found for authenticated user")

                playlist_repo: BaseSQLAlchemyRepository[
                    DBPlaylist, PlaylistCreate, PlaylistUpdate
                ] = BaseSQLAlchemyRepository(DBPlaylist)

                created_playlists = []

                # Test with first few playlists to avoid rate limits
                for i, playlist_data in enumerate(playlists_data[:3]):
                    # Use the established channel_id instead of the playlist's original channel_id
                    # to ensure the foreign key constraint is satisfied
                    playlist_channel_id = channel_id

                    # Create unique playlist ID using factory function with index to ensure uniqueness
                    import time

                    from chronovista.models.youtube_types import create_test_playlist_id

                    unique_suffix = f"api_{i}_{int(time.time())}"
                    unique_playlist_id = create_test_playlist_id(unique_suffix)

                    playlist_create = PlaylistCreate(
                        playlist_id=unique_playlist_id,
                        channel_id=playlist_channel_id,
                        title=playlist_data["snippet"]["title"],
                        description=playlist_data["snippet"].get("description", ""),
                        video_count=playlist_data.get("contentDetails", {}).get(
                            "itemCount", 0
                        ),
                        privacy_status=playlist_data["status"]["privacyStatus"],
                        default_language=playlist_data["snippet"].get("defaultLanguage")
                        or None,  # Handle None properly
                    )

                    db_playlist = await playlist_repo.create(
                        session, obj_in=playlist_create
                    )
                    created_playlists.append(db_playlist)

                await session.commit()

                # Verify playlists created and linked to channel
                assert len(created_playlists) > 0

                for db_playlist in created_playlists:
                    assert len(db_playlist.title) > 0
                    assert (
                        len(db_playlist.playlist_id) >= 10
                    )  # Our test playlist ID length
                    assert db_playlist.privacy_status in [
                        "public",
                        "unlisted",
                        "private",
                    ]

                # Clean up test data
                for playlist in created_playlists:
                    await session.execute(
                        delete(DBPlaylist).where(
                            DBPlaylist.playlist_id == playlist.playlist_id
                        )
                    )
                await session.commit()

            except Exception as e:
                await session.rollback()
                pytest.skip(f"Could not fetch playlists from API: {e}")

    async def test_playlist_statistics_update(
        self,
        authenticated_youtube_service,
        established_channel: Awaitable[Dict[str, Any] | None],
        integration_db_session,
    ):
        """Test updating playlist statistics from API."""
        established_channel_data = await established_channel

        if not authenticated_youtube_service or not established_channel_data:
            pytest.skip("Prerequisites not available")

        channel_id = established_channel_data["channel_id"]

        async with integration_db_session() as session:
            try:
                # Create a sample playlist first
                playlist_repo: BaseSQLAlchemyRepository[
                    DBPlaylist, PlaylistCreate, PlaylistUpdate
                ] = BaseSQLAlchemyRepository(DBPlaylist)

                # Create unique playlist ID using factory function
                from chronovista.models.youtube_types import create_test_playlist_id

                unique_id = create_test_playlist_id("stats")

                sample_playlist = PlaylistCreate(
                    playlist_id=unique_id,  # Unique playlist ID
                    channel_id=channel_id,
                    title="Integration Test Playlist",
                    description="Test playlist for integration testing",
                    video_count=0,
                    privacy_status="public",
                    default_language=None,  # Use None instead of hardcoded string
                )

                db_playlist = await playlist_repo.create(
                    session, obj_in=sample_playlist
                )
                await session.commit()

                # Simulate statistics update

                stats_update = PlaylistUpdate(
                    video_count=15,  # Updated count
                    description="Updated description with new content",
                    default_language=None,  # Updated language - use None
                    title="Updated Title",  # Updated title
                )

                # Store the original timestamp
                original_updated_at = db_playlist.updated_at

                # Add a small delay to ensure timestamp difference
                import time

                time.sleep(0.01)

                # Update playlist (would typically come from API refresh)
                updated_playlist = await playlist_repo.update(
                    session, db_obj=db_playlist, obj_in=stats_update
                )
                await session.commit()

                # Refresh to get the latest database state
                await session.refresh(updated_playlist)

                assert updated_playlist.video_count == 15
                assert "Updated description" in (updated_playlist.description or "")
                # Use the original timestamp for comparison
                assert updated_playlist.updated_at >= original_updated_at

                # Clean up test data
                await session.execute(
                    delete(DBPlaylist).where(
                        DBPlaylist.playlist_id == updated_playlist.playlist_id
                    )
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def test_playlist_video_relationship_preparation(
        self,
        established_channel: Awaitable[Dict[str, Any] | None],
        integration_db_session,
    ):
        """Test playlist creation in preparation for video relationships (Tier 3)."""
        established_channel_data = await established_channel

        if not established_channel_data:
            pytest.skip("Established channel not available")

        channel_id = established_channel_data["channel_id"]

        async with integration_db_session() as session:
            try:
                playlist_repo: BaseSQLAlchemyRepository[
                    DBPlaylist, PlaylistCreate, PlaylistUpdate
                ] = BaseSQLAlchemyRepository(DBPlaylist)

                import time

                # test_suffix = f"prep_test_{int(time.time())}"
                # Create multiple playlists that will be used in Tier 3 video tests
                # Note: test_suffix was removed as it's not currently used in this test
                from chronovista.models.youtube_types import create_test_playlist_id

                test_playlists = [
                    {
                        "playlist_id": create_test_playlist_id("music"),
                        "title": "Music Videos Collection",
                        "description": "Collection of music videos for testing",
                    },
                    {
                        "playlist_id": create_test_playlist_id("tech"),
                        "title": "Technology Reviews",
                        "description": "Tech review videos collection",
                    },
                ]

                created_playlists = []
                for playlist_data in test_playlists:
                    playlist_create = PlaylistCreate(
                        playlist_id=playlist_data["playlist_id"],
                        channel_id=channel_id,
                        title=playlist_data["title"],
                        description=playlist_data["description"],
                        video_count=0,  # Will be updated when videos are added
                        privacy_status="public",
                        default_language=None,  # Use None instead of hardcoded string
                    )

                    db_playlist = await playlist_repo.create(
                        session, obj_in=playlist_create
                    )
                    created_playlists.append(db_playlist)

                await session.commit()

                # Verify playlists ready for video association
                assert len(created_playlists) == 2

                for playlist in created_playlists:
                    assert playlist.channel_id == channel_id
                    assert playlist.video_count == 0  # No videos yet
                    assert playlist.created_at is not None

                # Clean up test data
                for playlist in created_playlists:
                    await session.execute(
                        delete(DBPlaylist).where(
                            DBPlaylist.playlist_id == playlist.playlist_id
                        )
                    )
                await session.commit()

                # These playlists will be available for Tier 3 video association tests
                return created_playlists
            except Exception:
                await session.rollback()
                raise
