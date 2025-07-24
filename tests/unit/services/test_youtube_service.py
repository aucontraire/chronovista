"""
Comprehensive tests for YouTubeService.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chronovista.services.youtube_service import YouTubeService


class TestYouTubeService:
    """Test YouTubeService functionality."""

    @pytest.fixture
    def youtube_service(self):
        """Create YouTube service instance."""
        return YouTubeService()

    @pytest.fixture
    def mock_service_client(self):
        """Create mock YouTube API service client."""
        mock_service = MagicMock()
        return mock_service

    def test_initialization(self, youtube_service):
        """Test YouTube service initialization."""
        assert youtube_service._service is None

    @patch("chronovista.services.youtube_service.youtube_oauth")
    def test_service_property_lazy_loading(self, mock_oauth, youtube_service):
        """Test that service property lazy loads the client."""
        mock_client = MagicMock()
        mock_oauth.get_authenticated_service.return_value = mock_client

        # First access should call get_authenticated_service
        service = youtube_service.service
        assert service == mock_client
        mock_oauth.get_authenticated_service.assert_called_once()

        # Second access should use cached service
        mock_oauth.get_authenticated_service.reset_mock()
        service2 = youtube_service.service
        assert service2 == mock_client
        mock_oauth.get_authenticated_service.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_my_channel_success(self, youtube_service, mock_service_client):
        """Test successful get_my_channel."""
        youtube_service._service = mock_service_client

        # Mock API response
        mock_response = {
            "items": [
                {
                    "id": "UCtest123",
                    "snippet": {
                        "title": "Test Channel",
                        "description": "Test Description",
                    },
                    "statistics": {"subscriberCount": "1000", "videoCount": "50"},
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.channels.return_value.list.return_value = mock_request

        result = await youtube_service.get_my_channel()

        assert result["id"] == "UCtest123"
        assert result["snippet"]["title"] == "Test Channel"
        mock_service_client.channels.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_my_channel_no_items(self, youtube_service, mock_service_client):
        """Test get_my_channel when no channel found."""
        youtube_service._service = mock_service_client

        mock_response = {"items": []}
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.channels.return_value.list.return_value = mock_request

        with pytest.raises(ValueError, match="No channel found for authenticated user"):
            await youtube_service.get_my_channel()

    @pytest.mark.asyncio
    async def test_get_channel_details_success(
        self, youtube_service, mock_service_client
    ):
        """Test successful get_channel_details."""
        youtube_service._service = mock_service_client

        mock_response = {
            "items": [
                {
                    "id": "UCother123",
                    "snippet": {
                        "title": "Other Channel",
                        "description": "Other Description",
                    },
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.channels.return_value.list.return_value = mock_request

        result = await youtube_service.get_channel_details("UCother123")

        assert result["id"] == "UCother123"
        assert result["snippet"]["title"] == "Other Channel"

    @pytest.mark.asyncio
    async def test_get_channel_details_not_found(
        self, youtube_service, mock_service_client
    ):
        """Test get_channel_details when channel not found."""
        youtube_service._service = mock_service_client

        mock_response = {"items": []}
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.channels.return_value.list.return_value = mock_request

        with pytest.raises(ValueError, match="Channel UCnonexistent not found"):
            await youtube_service.get_channel_details("UCnonexistent")

    @pytest.mark.asyncio
    async def test_get_channel_videos_success(
        self, youtube_service, mock_service_client
    ):
        """Test successful get_channel_videos."""
        youtube_service._service = mock_service_client

        # Mock channel details response for uploads playlist ID
        mock_channel_response = {
            "items": [
                {"contentDetails": {"relatedPlaylists": {"uploads": "UUtest123"}}}
            ]
        }

        # Mock playlist items response
        mock_playlist_response = {
            "items": [
                {
                    "snippet": {"title": "Video 1"},
                    "contentDetails": {"videoId": "video1"},
                },
                {
                    "snippet": {"title": "Video 2"},
                    "contentDetails": {"videoId": "video2"},
                },
            ]
        }

        mock_request1 = MagicMock()
        mock_request1.execute.return_value = mock_channel_response
        mock_service_client.channels.return_value.list.return_value = mock_request1

        mock_request2 = MagicMock()
        mock_request2.execute.return_value = mock_playlist_response
        mock_service_client.playlistItems.return_value.list.return_value = mock_request2

        result = await youtube_service.get_channel_videos("UCtest123", max_results=25)

        assert len(result) == 2
        assert result[0]["snippet"]["title"] == "Video 1"
        assert result[1]["snippet"]["title"] == "Video 2"

    @pytest.mark.asyncio
    async def test_get_channel_videos_empty(self, youtube_service, mock_service_client):
        """Test get_channel_videos with no videos."""
        youtube_service._service = mock_service_client

        # Mock channel details response
        mock_channel_response = {
            "items": [
                {"contentDetails": {"relatedPlaylists": {"uploads": "UUtest123"}}}
            ]
        }

        # Mock empty playlist response
        mock_playlist_response = {"items": []}

        mock_request1 = MagicMock()
        mock_request1.execute.return_value = mock_channel_response
        mock_service_client.channels.return_value.list.return_value = mock_request1

        mock_request2 = MagicMock()
        mock_request2.execute.return_value = mock_playlist_response
        mock_service_client.playlistItems.return_value.list.return_value = mock_request2

        result = await youtube_service.get_channel_videos("UCtest123")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_video_details_success(
        self, youtube_service, mock_service_client
    ):
        """Test successful get_video_details."""
        youtube_service._service = mock_service_client

        mock_response = {
            "items": [
                {
                    "id": "video1",
                    "snippet": {"title": "Video 1"},
                    "statistics": {"viewCount": "1000"},
                },
                {
                    "id": "video2",
                    "snippet": {"title": "Video 2"},
                    "statistics": {"viewCount": "2000"},
                },
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.videos.return_value.list.return_value = mock_request

        result = await youtube_service.get_video_details(["video1", "video2"])

        assert len(result) == 2
        assert result[0]["id"] == "video1"
        assert result[1]["id"] == "video2"

    @pytest.mark.asyncio
    async def test_get_video_details_empty_list(
        self, youtube_service, mock_service_client
    ):
        """Test get_video_details with empty video list."""
        youtube_service._service = mock_service_client

        mock_response = {"items": []}
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.videos.return_value.list.return_value = mock_request

        result = await youtube_service.get_video_details(["nonexistent"])
        assert result == []

    @pytest.mark.asyncio
    async def test_get_my_playlists_success(self, youtube_service, mock_service_client):
        """Test successful get_my_playlists."""
        youtube_service._service = mock_service_client

        mock_response = {
            "items": [
                {"id": "playlist1", "snippet": {"title": "My Playlist 1"}},
                {"id": "playlist2", "snippet": {"title": "My Playlist 2"}},
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.playlists.return_value.list.return_value = mock_request

        result = await youtube_service.get_my_playlists(max_results=25)

        assert len(result) == 2
        assert result[0]["id"] == "playlist1"
        assert result[1]["id"] == "playlist2"

    @pytest.mark.asyncio
    async def test_get_playlist_videos_success(
        self, youtube_service, mock_service_client
    ):
        """Test successful get_playlist_videos."""
        youtube_service._service = mock_service_client

        mock_response = {
            "items": [
                {
                    "snippet": {
                        "resourceId": {"videoId": "video1"},
                        "title": "Playlist Video 1",
                    }
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.playlistItems.return_value.list.return_value = mock_request

        result = await youtube_service.get_playlist_videos("PLtest123")

        assert len(result) == 1
        assert result[0]["snippet"]["resourceId"]["videoId"] == "video1"

    @pytest.mark.asyncio
    async def test_search_my_videos_success(self, youtube_service, mock_service_client):
        """Test successful search_my_videos."""
        youtube_service._service = mock_service_client

        mock_response = {
            "items": [
                {"id": {"videoId": "search1"}, "snippet": {"title": "Search Result 1"}}
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.search.return_value.list.return_value = mock_request

        result = await youtube_service.search_my_videos("test query")

        assert len(result) == 1
        assert result[0]["id"]["videoId"] == "search1"

    @pytest.mark.asyncio
    async def test_get_video_captions_success(
        self, youtube_service, mock_service_client
    ):
        """Test successful get_video_captions."""
        youtube_service._service = mock_service_client

        mock_response = {
            "items": [
                {"id": "caption1", "snippet": {"language": "en", "name": "English"}}
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.captions.return_value.list.return_value = mock_request

        result = await youtube_service.get_video_captions("video123")

        assert len(result) == 1
        assert result[0]["snippet"]["language"] == "en"

    @pytest.mark.asyncio
    async def test_get_liked_videos_success(self, youtube_service, mock_service_client):
        """Test successful get_liked_videos."""
        youtube_service._service = mock_service_client

        # Mock channel response for liked playlist ID
        mock_channel_response = {
            "items": [{"contentDetails": {"relatedPlaylists": {"likes": "LLtest123"}}}]
        }

        # Mock playlist items response
        mock_playlist_response = {"items": [{"contentDetails": {"videoId": "video1"}}]}

        # Mock video details response
        mock_video_response = {
            "items": [{"id": "video1", "snippet": {"title": "Liked Video 1"}}]
        }

        # Mock the three API calls
        mock_service_client.channels.return_value.list.return_value.execute.return_value = (
            mock_channel_response
        )
        mock_service_client.playlistItems.return_value.list.return_value.execute.return_value = (
            mock_playlist_response
        )
        mock_service_client.videos.return_value.list.return_value.execute.return_value = (
            mock_video_response
        )

        result = await youtube_service.get_liked_videos(max_results=5)

        assert len(result) == 1
        assert result[0]["id"] == "video1"

    @pytest.mark.asyncio
    async def test_get_subscription_channels_success(
        self, youtube_service, mock_service_client
    ):
        """Test successful get_subscription_channels."""
        youtube_service._service = mock_service_client

        mock_response = {
            "items": [
                {
                    "snippet": {
                        "resourceId": {"channelId": "UC123"},
                        "title": "Subscribed Channel",
                    }
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.subscriptions.return_value.list.return_value = mock_request

        result = await youtube_service.get_subscription_channels()

        assert len(result) == 1
        assert result[0]["snippet"]["resourceId"]["channelId"] == "UC123"


class TestYouTubeServiceErrorHandling:
    """Test error handling in YouTube service."""

    @pytest.fixture
    def youtube_service(self):
        """Create YouTube service instance."""
        return YouTubeService()

    @pytest.fixture
    def mock_service_client(self):
        """Create mock YouTube API service client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_get_my_channel_api_error(self, youtube_service, mock_service_client):
        """Test get_my_channel with API error."""
        youtube_service._service = mock_service_client

        mock_request = MagicMock()
        mock_request.execute.side_effect = Exception("API Error")
        mock_service_client.channels.return_value.list.return_value = mock_request

        with pytest.raises(Exception, match="API Error"):
            await youtube_service.get_my_channel()

    @pytest.mark.asyncio
    async def test_get_video_details_api_error(
        self, youtube_service, mock_service_client
    ):
        """Test get_video_details with API error."""
        youtube_service._service = mock_service_client

        mock_request = MagicMock()
        mock_request.execute.side_effect = Exception("API Error")
        mock_service_client.videos.return_value.list.return_value = mock_request

        with pytest.raises(Exception, match="API Error"):
            await youtube_service.get_video_details(["video1"])

    @pytest.mark.asyncio
    async def test_get_channel_videos_api_error(
        self, youtube_service, mock_service_client
    ):
        """Test get_channel_videos with API error."""
        youtube_service._service = mock_service_client

        mock_request = MagicMock()
        mock_request.execute.side_effect = Exception("API Error")
        mock_service_client.channels.return_value.list.return_value = mock_request

        with pytest.raises(Exception, match="API Error"):
            await youtube_service.get_channel_videos("UC123")

    @pytest.mark.asyncio
    async def test_get_my_playlists_empty_response(
        self, youtube_service, mock_service_client
    ):
        """Test get_my_playlists with empty response."""
        youtube_service._service = mock_service_client

        mock_response = {"items": []}
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.playlists.return_value.list.return_value = mock_request

        result = await youtube_service.get_my_playlists()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_video_captions_empty_response(
        self, youtube_service, mock_service_client
    ):
        """Test get_video_captions with empty response."""
        youtube_service._service = mock_service_client

        mock_response = {"items": []}
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.captions.return_value.list.return_value = mock_request

        result = await youtube_service.get_video_captions("video123")

        assert result == []

    @pytest.mark.asyncio
    async def test_search_my_videos_empty_query(
        self, youtube_service, mock_service_client
    ):
        """Test search_my_videos with empty query."""
        youtube_service._service = mock_service_client

        mock_response = {"items": []}
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.search.return_value.list.return_value = mock_request

        result = await youtube_service.search_my_videos("")

        assert result == []


class TestYouTubeServiceEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def youtube_service(self):
        """Create YouTube service instance."""
        return YouTubeService()

    @pytest.fixture
    def mock_service_client(self):
        """Create mock YouTube API service client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_get_video_details_large_batch(
        self, youtube_service, mock_service_client
    ):
        """Test get_video_details with large batch of video IDs raises error."""
        youtube_service._service = mock_service_client

        # Create 100 video IDs - should raise ValueError
        video_ids = [f"video{i}" for i in range(100)]

        with pytest.raises(
            ValueError, match="Maximum 50 video IDs allowed per request"
        ):
            await youtube_service.get_video_details(video_ids)

    @pytest.mark.asyncio
    async def test_get_channel_videos_max_results_boundary(
        self, youtube_service, mock_service_client
    ):
        """Test get_channel_videos with different max_results values."""
        youtube_service._service = mock_service_client

        # Mock channel details response
        mock_channel_response = {
            "items": [
                {"contentDetails": {"relatedPlaylists": {"uploads": "UUtest123"}}}
            ]
        }

        mock_playlist_response = {"items": []}

        mock_request1 = MagicMock()
        mock_request1.execute.return_value = mock_channel_response
        mock_service_client.channels.return_value.list.return_value = mock_request1

        mock_request2 = MagicMock()
        mock_request2.execute.return_value = mock_playlist_response
        mock_service_client.playlistItems.return_value.list.return_value = mock_request2

        # Test with different max_results values
        for max_results in [1, 10, 50, 100]:
            result = await youtube_service.get_channel_videos(
                "UC123", max_results=max_results
            )
            assert result == []

    @pytest.mark.asyncio
    async def test_service_property_with_none_oauth_service(self, youtube_service):
        """Test service property when oauth service returns None."""
        with patch("chronovista.services.youtube_service.youtube_oauth") as mock_oauth:
            mock_oauth.get_authenticated_service.return_value = None

            service = youtube_service.service
            assert service is None

    @pytest.mark.asyncio
    async def test_get_my_channel_malformed_response(
        self, youtube_service, mock_service_client
    ):
        """Test get_my_channel with malformed API response."""
        youtube_service._service = mock_service_client

        # Response missing 'items' key
        mock_response = {"kind": "youtube#channelListResponse"}
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_service_client.channels.return_value.list.return_value = mock_request

        with pytest.raises(ValueError, match="No channel found for authenticated user"):
            await youtube_service.get_my_channel()

    @pytest.mark.asyncio
    async def test_multiple_service_method_calls(
        self, youtube_service, mock_service_client
    ):
        """Test multiple consecutive service method calls."""
        youtube_service._service = mock_service_client

        # Mock responses for different methods
        mock_channel_response = {
            "items": [{"id": "UC123", "snippet": {"title": "Test"}}]
        }
        mock_video_response = {
            "items": [{"id": "video1", "snippet": {"title": "Video"}}]
        }

        mock_request1 = MagicMock()
        mock_request1.execute.return_value = mock_channel_response
        mock_service_client.channels.return_value.list.return_value = mock_request1

        mock_request2 = MagicMock()
        mock_request2.execute.return_value = mock_video_response
        mock_service_client.videos.return_value.list.return_value = mock_request2

        # Call multiple methods
        channel_result = await youtube_service.get_my_channel()
        video_result = await youtube_service.get_video_details(["video1"])

        assert channel_result["id"] == "UC123"
        assert len(video_result) == 1
        assert video_result[0]["id"] == "video1"


class TestYouTubeServiceIntegration:
    """Test service integration scenarios."""

    @pytest.fixture
    def youtube_service(self):
        """Create YouTube service instance."""
        return YouTubeService()

    def test_service_initialization_integration(self, youtube_service):
        """Test service integrates properly with oauth module."""
        with patch("chronovista.services.youtube_service.youtube_oauth") as mock_oauth:
            mock_client = MagicMock()
            mock_oauth.get_authenticated_service.return_value = mock_client

            # Service should be lazily loaded
            assert youtube_service._service is None

            # First access should trigger OAuth
            service = youtube_service.service
            assert service == mock_client
            assert youtube_service._service == mock_client

            mock_oauth.get_authenticated_service.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_workflow_simulation(self, youtube_service):
        """Test a complete workflow simulation."""
        with patch("chronovista.services.youtube_service.youtube_oauth") as mock_oauth:
            mock_service_client = MagicMock()
            mock_oauth.get_authenticated_service.return_value = mock_service_client

            # Mock channel response
            mock_channel_response = {
                "items": [{"id": "UC123", "snippet": {"title": "My Channel"}}]
            }
            mock_request = MagicMock()
            mock_request.execute.return_value = mock_channel_response
            mock_service_client.channels.return_value.list.return_value = mock_request

            # Simulate workflow: get channel, then get videos
            channel = await youtube_service.get_my_channel()
            assert channel["id"] == "UC123"

            # Mock videos response for channel videos
            mock_channel_detail_response = {
                "items": [
                    {"contentDetails": {"relatedPlaylists": {"uploads": "UUtest123"}}}
                ]
            }
            mock_video_response = {"items": []}

            # Mock the two different calls for get_channel_videos
            def mock_execute_side_effect():
                # First call returns channel details, second returns playlist items
                if mock_service_client.channels.return_value.list.called:
                    return mock_channel_detail_response
                return mock_video_response

            mock_request2 = MagicMock()
            mock_request2.execute.return_value = mock_channel_detail_response
            mock_service_client.channels.return_value.list.return_value = mock_request2

            mock_request3 = MagicMock()
            mock_request3.execute.return_value = mock_video_response
            mock_service_client.playlistItems.return_value.list.return_value = (
                mock_request3
            )

            videos = await youtube_service.get_channel_videos("UC123")
            assert videos == []
