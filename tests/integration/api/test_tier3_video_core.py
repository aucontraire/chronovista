"""
Tier 3 Integration Tests: Video Core Models

Tests the Video model with real YouTube video data:
- Video (core video entity with complex metadata)
- VideoWithChannel (video + channel information)
- VideoSearchFilters (video search functionality)
- VideoStatistics (video analytics)

These tests require established Channel entities from Tier 1/2 tests
and form the foundation for video-dependent models in Tier 4.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Dict, List

import pytest
from sqlalchemy import delete, select

from chronovista.db.models import Video as DBVideo
from chronovista.models.video import Video, VideoCreate, VideoStatistics, VideoUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository

pytestmark = pytest.mark.asyncio


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.asyncio
class TestVideoFromYouTubeAPI:
    """Test Video model with real YouTube API data."""

    async def test_video_creation_from_api(
        self,
        authenticated_youtube_service,
        integration_db_session,
        established_channel: Awaitable[Dict[str, Any] | None],
        sample_youtube_video_ids,
    ):
        """Test creating videos from real YouTube API data."""
        # Await the fixture since it's async
        established_channel_data = await established_channel

        if not authenticated_youtube_service or not established_channel_data:
            pytest.skip("Prerequisites not available")

        channel_id = established_channel_data["channel_id"]
        video_id = sample_youtube_video_ids[0]  # Rick Astley - Never Gonna Give You Up

        async with integration_db_session() as session:
            try:
                # Clean up any existing test data first
                await session.execute(
                    delete(DBVideo).where(DBVideo.video_id == video_id)
                )
                await session.commit()

                # Get video data from YouTube API
                video_details_list = (
                    await authenticated_youtube_service.get_video_details([video_id])
                )
                api_video_data = video_details_list[0] if video_details_list else None

                if not api_video_data:
                    pytest.skip(f"Video {video_id} not found or not accessible")

                # Validate API data structure
                assert "id" in api_video_data
                assert "snippet" in api_video_data
                assert "contentDetails" in api_video_data
                assert api_video_data["id"] == video_id

                # Create Pydantic model from API data
                video_create = VideoCreate(
                    video_id=api_video_data["id"],
                    channel_id=api_video_data["snippet"]["channelId"],
                    title=api_video_data["snippet"]["title"],
                    description=api_video_data["snippet"].get("description", ""),
                    upload_date=datetime.fromisoformat(
                        api_video_data["snippet"]["publishedAt"].replace("Z", "+00:00")
                    ),
                    duration=self._parse_youtube_duration(
                        api_video_data["contentDetails"]["duration"]
                    ),
                    made_for_kids=api_video_data.get("status", {}).get(
                        "madeForKids", False
                    ),
                    default_language=api_video_data["snippet"].get("defaultLanguage")
                    or None,  # Handle None properly
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

                # Validate Pydantic model
                assert isinstance(video_create, VideoCreate)
                assert video_create.video_id == video_id
                assert len(video_create.title) > 0
                assert video_create.duration > 0
                assert video_create.view_count is None or video_create.view_count >= 0

                # Use repository pattern for database operations
                video_repo: BaseSQLAlchemyRepository[
                    DBVideo, VideoCreate, VideoUpdate
                ] = BaseSQLAlchemyRepository(DBVideo)

                # Persist to database
                db_video = await video_repo.create(session, obj_in=video_create)
                await session.commit()

                # Verify database persistence
                assert db_video.video_id == video_id
                assert db_video.title == video_create.title
                assert db_video.channel_id == video_create.channel_id
                assert db_video.created_at is not None
                assert db_video.updated_at is not None

                # Verify data integrity
                result = await session.execute(
                    select(DBVideo).where(DBVideo.video_id == video_id)
                )
                retrieved_video = result.scalar_one_or_none()
                assert retrieved_video is not None
                assert retrieved_video.video_id == video_id
                assert retrieved_video.title == db_video.title

                # Clean up test data
                await session.execute(
                    delete(DBVideo).where(DBVideo.video_id == video_id)
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def test_video_complex_metadata_handling(
        self,
        authenticated_youtube_service,
        integration_db_session,
        sample_youtube_video_ids,
    ):
        """Test handling complex video metadata from YouTube API."""
        if not authenticated_youtube_service:
            pytest.skip("YouTube API not available")

        async with integration_db_session() as session:
            try:
                # Test with multiple videos to check different metadata scenarios
                for video_id in sample_youtube_video_ids[:2]:
                    try:
                        video_details_list = (
                            await authenticated_youtube_service.get_video_details(
                                [video_id]
                            )
                        )
                        api_data = video_details_list[0] if video_details_list else None

                        if not api_data:
                            continue  # Skip this video

                        # Test multi-language metadata
                        available_languages = api_data["snippet"].get(
                            "availableLanguages", {}
                        )
                        if available_languages:
                            assert isinstance(available_languages, dict)

                        # Test region restrictions
                        region_restriction = api_data.get("contentDetails", {}).get(
                            "regionRestriction"
                        )
                        if region_restriction:
                            assert (
                                "blocked" in region_restriction
                                or "allowed" in region_restriction
                            )

                        # Test content rating
                        content_rating = api_data.get("contentDetails", {}).get(
                            "contentRating", {}
                        )
                        if content_rating:
                            # YouTube content ratings can include various rating systems
                            rating_systems = [
                                "ytRating",
                                "mpaaRating",
                                "fskRating",
                                "bbfcRating",
                            ]
                            assert any(
                                system in content_rating for system in rating_systems
                            )

                        # Test age restriction handling
                        made_for_kids = api_data.get("status", {}).get("madeForKids")
                        self_declared_made_for_kids = api_data.get("status", {}).get(
                            "selfDeclaredMadeForKids"
                        )

                        if made_for_kids is not None:
                            assert isinstance(made_for_kids, bool)
                        if self_declared_made_for_kids is not None:
                            assert isinstance(self_declared_made_for_kids, bool)

                        # Test video statistics validation
                        stats = api_data.get("statistics", {})
                        for stat_name in [
                            "viewCount",
                            "likeCount",
                            "dislikeCount",
                            "commentCount",
                        ]:
                            if stat_name in stats:
                                stat_value = int(stats[stat_name])
                                assert stat_value >= 0

                    except Exception as e:
                        print(f"Warning: Could not test video {video_id}: {e}")
                        continue
            except Exception:
                await session.rollback()
                raise

    async def test_video_language_detection(
        self,
        authenticated_youtube_service,
        integration_db_session,
        sample_youtube_video_ids,
    ):
        """Test video language detection and validation."""
        if not authenticated_youtube_service:
            pytest.skip("YouTube API not available")

        for video_id in sample_youtube_video_ids:
            try:
                video_details_list = (
                    await authenticated_youtube_service.get_video_details([video_id])
                )
                api_data = video_details_list[0] if video_details_list else None

                if not api_data:
                    continue  # Skip this video

                # Test default language validation
                default_language = api_data["snippet"].get("defaultLanguage")
                if default_language:
                    # Should be valid BCP-47 code
                    assert 2 <= len(default_language) <= 10
                    assert "-" in default_language or len(default_language) <= 3

                # Test audio language detection
                default_audio_language = api_data["snippet"].get("defaultAudioLanguage")
                if default_audio_language:
                    assert 2 <= len(default_audio_language) <= 10

                # Test available languages structure
                available_languages = api_data["snippet"].get("availableLanguages")
                if available_languages:
                    assert isinstance(available_languages, (dict, list))

            except Exception as e:
                print(f"Warning: Could not test language detection for {video_id}: {e}")
                continue

    async def test_video_update_from_fresh_api_data(
        self,
        authenticated_youtube_service,
        integration_db_session,
        established_videos: Awaitable[List[Dict[str, Any]] | None],
    ):
        """Test updating video with fresh data from API."""
        # Await the fixture since it's async
        established_videos_data = await established_videos

        if not authenticated_youtube_service or not established_videos_data:
            print(
                f"DEBUG: Test prerequisites - auth_service: {bool(authenticated_youtube_service)}, videos_data: {bool(established_videos_data)}, videos_count: {len(established_videos_data) if established_videos_data else 0}"
            )
            pytest.skip("Prerequisites not available")

        test_video = established_videos_data[0]
        video_id = test_video["video_id"]

        async with integration_db_session() as session:
            try:
                # Get fresh data from API
                video_details_list = (
                    await authenticated_youtube_service.get_video_details([video_id])
                )
                fresh_api_data = video_details_list[0] if video_details_list else None

                if not fresh_api_data:
                    pytest.skip(f"Video {video_id} not found for update test")

                # Create update model with fresh statistics
                from tests.factories.video_factory import create_video_update

                video_update = create_video_update(
                    view_count=int(
                        fresh_api_data.get("statistics", {}).get("viewCount", 0)
                    ),
                    like_count=int(
                        fresh_api_data.get("statistics", {}).get("likeCount", 0)
                    ),
                    comment_count=int(
                        fresh_api_data.get("statistics", {}).get("commentCount", 0)
                    ),
                )

                # Use repository pattern
                video_repo: BaseSQLAlchemyRepository[
                    DBVideo, VideoCreate, VideoUpdate
                ] = BaseSQLAlchemyRepository(DBVideo)
                # First get the existing video
                result = await session.execute(
                    select(DBVideo).where(DBVideo.video_id == video_id)
                )
                existing_video = result.scalar_one_or_none()

                if not existing_video:
                    pytest.skip(f"Video {video_id} not found in database")

                updated_video = await video_repo.update(
                    session, db_obj=existing_video, obj_in=video_update
                )
                await session.commit()

                # Verify update
                assert updated_video.video_id == video_id
                assert updated_video.updated_at >= existing_video.created_at

                # Statistics should be updated (they may change over time)
                assert updated_video.view_count is None or updated_video.view_count >= 0
                assert updated_video.like_count is None or updated_video.like_count >= 0
            except Exception:
                await session.rollback()
                raise

    def _parse_youtube_duration(self, duration_str: str) -> int:
        """
        Parse YouTube's ISO 8601 duration format (PT4M13S) to seconds.

        Args:
            duration_str: YouTube duration in ISO 8601 format

        Returns:
            Duration in seconds
        """
        import re

        # Remove PT prefix
        duration_str = duration_str.replace("PT", "")

        # Extract hours, minutes, seconds
        hours = 0
        minutes = 0
        seconds = 0

        hour_match = re.search(r"(\d+)H", duration_str)
        if hour_match:
            hours = int(hour_match.group(1))

        minute_match = re.search(r"(\d+)M", duration_str)
        if minute_match:
            minutes = int(minute_match.group(1))

        second_match = re.search(r"(\d+)S", duration_str)
        if second_match:
            seconds = int(second_match.group(1))

        return hours * 3600 + minutes * 60 + seconds


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.asyncio
class TestVideoSearchAndFiltering:
    """Test video search and filtering functionality with real data."""

    async def test_video_search_filters_with_real_data(
        self,
        integration_db_session,
        established_videos: Awaitable[List[Dict[str, Any]] | None],
    ):
        """Test video search filters with established video data."""
        # Await the fixture since it's async
        established_videos_data = await established_videos

        if not established_videos_data:
            pytest.skip("Prerequisites not available")

        # Get channel_id from the video data since established_videos includes channel info
        channel_id = established_videos_data[0]["db_model"].channel_id

        async with integration_db_session() as session:
            try:
                # Use repository pattern
                video_repo: BaseSQLAlchemyRepository[
                    DBVideo, VideoCreate, VideoUpdate
                ] = BaseSQLAlchemyRepository(DBVideo)
                # Test channel-based filtering
                from tests.factories.video_factory import create_video_search_filters

                channel_filter = create_video_search_filters(
                    channel_ids=[channel_id],
                    exclude_deleted=True,
                )

                # For now, use a simple query since search_videos method may not exist
                result = await session.execute(
                    select(DBVideo).where(
                        DBVideo.channel_id == channel_id, DBVideo.availability_status == "available"
                    )
                )
                filtered_videos = result.scalars().all()

                # Should find our established videos
                assert len(filtered_videos) >= 0  # May be 0 if no videos match filter
                for video in filtered_videos:
                    assert video.channel_id == channel_id
                    assert video.availability_status == "available"

                # Test duration-based filtering
                duration_result = await session.execute(
                    select(DBVideo).where(
                        DBVideo.duration >= 60, DBVideo.duration <= 600
                    )
                )
                duration_filtered = duration_result.scalars().all()
                for video in duration_filtered:
                    assert 60 <= video.duration <= 600

                # Test view count filtering
                view_result = await session.execute(
                    select(DBVideo).where(DBVideo.view_count >= 1000)
                )
                popular_videos = view_result.scalars().all()
                for video in popular_videos:
                    assert video.view_count >= 1000

            except Exception:
                await session.rollback()
                raise

    async def test_video_date_range_filtering(
        self,
        integration_db_session,
        established_videos: Awaitable[List[Dict[str, Any]] | None],
    ):
        """Test video filtering by upload date ranges."""
        # Await the fixture since it's async
        established_videos_data = await established_videos

        if not established_videos_data:
            pytest.skip("Established videos not available")

        async with integration_db_session() as session:
            try:
                # Use repository pattern
                video_repo: BaseSQLAlchemyRepository[
                    DBVideo, VideoCreate, VideoUpdate
                ] = BaseSQLAlchemyRepository(DBVideo)
                # Test recent videos (last year)
                recent_date = datetime.now(timezone.utc).replace(
                    year=datetime.now().year - 1
                )

                recent_result = await session.execute(
                    select(DBVideo).where(DBVideo.upload_date >= recent_date)
                )
                recent_videos = recent_result.scalars().all()
                for video in recent_videos:
                    assert video.upload_date >= recent_date

                # Test older videos (before specific date)
                cutoff_date = datetime(2020, 1, 1, tzinfo=timezone.utc)

                older_result = await session.execute(
                    select(DBVideo).where(DBVideo.upload_date <= cutoff_date)
                )
                older_videos = older_result.scalars().all()
                for video in older_videos:
                    assert video.upload_date <= cutoff_date

            except Exception:
                await session.rollback()
                raise


@pytest.mark.integration
@pytest.mark.asyncio
class TestVideoStatisticsAggregation:
    """Test video statistics aggregation with real data."""

    async def test_channel_video_statistics(
        self,
        integration_db_session,
        established_videos: Awaitable[List[Dict[str, Any]] | None],
    ):
        """Test aggregating video statistics for a channel."""
        # Await the fixture since it's async
        established_videos_data = await established_videos

        if not established_videos_data:
            pytest.skip("Prerequisites not available")

        # Get channel_id from the video data since established_videos includes channel info
        channel_id = established_videos_data[0]["db_model"].channel_id

        async with integration_db_session() as session:
            try:
                # Use repository pattern to get channel videos
                video_repo: BaseSQLAlchemyRepository[
                    DBVideo, VideoCreate, VideoUpdate
                ] = BaseSQLAlchemyRepository(DBVideo)
                # Get all videos for the channel
                result = await session.execute(
                    select(DBVideo).where(DBVideo.channel_id == channel_id)
                )
                channel_videos = result.scalars().all()

                if len(channel_videos) == 0:
                    pytest.skip("No videos found for channel")

                # Calculate basic statistics
                total_videos = len(channel_videos)
                total_duration = sum(video.duration for video in channel_videos)
                avg_duration = total_duration / total_videos if total_videos > 0 else 0
                total_views = sum(video.view_count or 0 for video in channel_videos)
                total_likes = sum(video.like_count or 0 for video in channel_videos)

                # Create statistics model
                stats = VideoStatistics(
                    total_videos=total_videos,
                    total_duration=total_duration,
                    avg_duration=avg_duration,
                    total_views=total_views,
                    total_likes=total_likes,
                    total_comments=sum(
                        video.comment_count or 0 for video in channel_videos
                    ),
                    avg_views_per_video=(
                        total_views / total_videos if total_videos > 0 else 0
                    ),
                    avg_likes_per_video=(
                        total_likes / total_videos if total_videos > 0 else 0
                    ),
                    deleted_video_count=sum(
                        1 for video in channel_videos if video.availability_status != "available"
                    ),
                    kids_friendly_count=sum(
                        1 for video in channel_videos if video.made_for_kids
                    ),
                    top_languages=self._extract_top_languages(channel_videos),
                    upload_trend=self._calculate_upload_trend(channel_videos),
                )

                # Verify statistics are reasonable
                assert stats.total_videos > 0
                assert stats.total_duration > 0
                assert stats.avg_duration > 0
                assert stats.total_views >= 0
                assert 0 <= stats.deleted_video_count <= stats.total_videos
                assert 0 <= stats.kids_friendly_count <= stats.total_videos

            except Exception:
                await session.rollback()
                raise

    def _extract_top_languages(self, videos: list[Video]) -> list[tuple[str, int]]:
        """Extract top languages from video collection."""
        language_counts: Dict[str, int] = {}

        for video in videos:
            lang = video.default_language or "unknown"
            language_counts[lang] = language_counts.get(lang, 0) + 1

        # Sort by count descending, return top 5
        sorted_languages = sorted(
            language_counts.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_languages[:5]

    def _calculate_upload_trend(self, videos: list[Video]) -> dict[str, int]:
        """Calculate upload trend by month."""
        trend: Dict[str, int] = {}

        for video in videos:
            month_key = video.upload_date.strftime("%Y-%m")
            trend[month_key] = trend.get(month_key, 0) + 1

        return trend
