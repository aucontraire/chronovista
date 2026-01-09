"""
Pytest fixtures for enrichment service tests.

Provides helper functions to create YouTubeVideoResponse Pydantic models
for mocking YouTube API responses in tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pytest

from chronovista.models.api_responses import (
    TopicDetails,
    VideoContentDetails,
    VideoSnippet,
    VideoStatisticsResponse,
    VideoStatus,
    YouTubeVideoResponse,
)


def make_video_response(
    video_id: str,
    title: str = "Test Video",
    description: str = "",
    channel_id: str = "UCuAXFkgsw1L7xaCfnd5JJOw",
    channel_title: str = "Test Channel",
    published_at: Optional[datetime] = None,
    duration: str = "PT10M30S",
    view_count: int = 1000,
    like_count: Optional[int] = 50,
    comment_count: Optional[int] = 10,
    category_id: str = "10",
    tags: Optional[list[str]] = None,
    topic_categories: Optional[list[str]] = None,
    made_for_kids: bool = False,
    self_declared_made_for_kids: Optional[bool] = None,
    default_language: Optional[str] = None,
    default_audio_language: Optional[str] = None,
) -> YouTubeVideoResponse:
    """
    Create a valid YouTubeVideoResponse instance for testing.

    Parameters
    ----------
    video_id : str
        YouTube video ID (11 characters).
    title : str
        Video title.
    description : str
        Video description.
    channel_id : str
        Channel ID.
    channel_title : str
        Channel title/name.
    published_at : Optional[datetime]
        Publication timestamp. Defaults to current time.
    duration : str
        ISO 8601 duration string.
    view_count : int
        View count.
    like_count : Optional[int]
        Like count.
    comment_count : Optional[int]
        Comment count.
    category_id : str
        YouTube category ID.
    tags : Optional[list[str]]
        List of video tags.
    topic_categories : Optional[list[str]]
        List of Wikipedia topic URLs.
    made_for_kids : bool
        Whether video is made for kids.
    self_declared_made_for_kids : Optional[bool]
        Creator's made for kids declaration.
    default_language : Optional[str]
        Default language code.
    default_audio_language : Optional[str]
        Default audio language code.

    Returns
    -------
    YouTubeVideoResponse
        A valid Pydantic model instance.
    """
    if published_at is None:
        published_at = datetime.now(timezone.utc)

    snippet = VideoSnippet(
        publishedAt=published_at,
        channelId=channel_id,
        title=title,
        description=description,
        channelTitle=channel_title,
        categoryId=category_id,
        tags=tags or [],
        thumbnails={},
        defaultLanguage=default_language,
        defaultAudioLanguage=default_audio_language,
    )

    content_details = VideoContentDetails(
        duration=duration,
    )

    statistics = VideoStatisticsResponse(
        viewCount=view_count,
        likeCount=like_count,
        commentCount=comment_count,
    )

    status = VideoStatus(
        madeForKids=made_for_kids,
        selfDeclaredMadeForKids=self_declared_made_for_kids,
    )

    topic_details = None
    if topic_categories:
        topic_details = TopicDetails(
            topicCategories=topic_categories,
        )

    return YouTubeVideoResponse(
        kind="youtube#video",
        etag="test_etag",
        id=video_id,
        snippet=snippet,
        contentDetails=content_details,
        statistics=statistics,
        status=status,
        topicDetails=topic_details,
    )


def make_minimal_video_response(video_id: str) -> YouTubeVideoResponse:
    """
    Create a minimal YouTubeVideoResponse with just the ID.

    Useful for tests that only care about the video being returned,
    not the full metadata.

    Parameters
    ----------
    video_id : str
        YouTube video ID.

    Returns
    -------
    YouTubeVideoResponse
        A minimal valid Pydantic model instance.
    """
    return YouTubeVideoResponse(
        kind="youtube#video",
        etag="test_etag",
        id=video_id,
    )


@pytest.fixture
def video_response_factory():
    """Fixture that returns the make_video_response helper function."""
    return make_video_response


@pytest.fixture
def minimal_video_response_factory():
    """Fixture that returns the make_minimal_video_response helper function."""
    return make_minimal_video_response
