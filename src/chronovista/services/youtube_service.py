"""
YouTube Data API service for fetching user data.

Provides high-level methods for interacting with YouTube Data API v3,
including channel info, videos, playlists, and watch history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from chronovista.auth import youtube_oauth
from chronovista.models.youtube_types import ChannelId, PlaylistId, VideoId


class YouTubeService:
    """
    YouTube Data API service.

    Provides methods for fetching YouTube data using authenticated API client.
    """

    def __init__(self) -> None:
        """Initialize YouTube service."""
        self._service = None

    @property
    def service(self) -> Any:
        """Get authenticated YouTube API service client."""
        if self._service is None:
            self._service = youtube_oauth.get_authenticated_service()
        return self._service

    async def get_my_channel(self) -> Dict[str, Any]:
        """
        Get information about the authenticated user's channel.

        Returns
        -------
        Dict[str, Any]
            Channel information including id, title, description, statistics
        """
        request = self.service.channels().list(
            part="id,snippet,statistics,contentDetails,status,brandingSettings,topicDetails",
            mine=True,
        )
        response = request.execute()

        if not response.get("items"):
            raise ValueError("No channel found for authenticated user")

        return dict(response["items"][0])

    async def get_channel_details(self, channel_id: ChannelId) -> Dict[str, Any]:
        """
        Get detailed information about a specific channel.

        Parameters
        ----------
        channel_id : ChannelId
            The channel ID to fetch details for (validated)

        Returns
        -------
        Dict[str, Any]
            Channel information including id, title, description, statistics
        """
        request = self.service.channels().list(
            part="id,snippet,statistics,contentDetails,status,brandingSettings,topicDetails",
            id=channel_id,
        )
        response = request.execute()

        if not response.get("items"):
            raise ValueError(f"Channel {channel_id} not found")

        return dict(response["items"][0])

    async def get_channel_videos(
        self, channel_id: ChannelId, max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get videos from a specific channel.

        Parameters
        ----------
        channel_id : ChannelId
            The channel ID to fetch videos from (validated)
        max_results : int
            Maximum number of videos to return (default 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of video information
        """
        # First get the uploads playlist ID
        request = self.service.channels().list(part="contentDetails", id=channel_id)
        response = request.execute()

        if not response.get("items"):
            raise ValueError(f"Channel {channel_id} not found")

        uploads_playlist_id = response["items"][0]["contentDetails"][
            "relatedPlaylists"
        ]["uploads"]

        # Get videos from uploads playlist
        request = self.service.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=max_results,
        )
        response = request.execute()

        return list(response.get("items", []))

    async def get_video_details(self, video_ids: list[VideoId]) -> list[Dict[str, Any]]:
        """
        Get detailed information about specific videos.

        Parameters
        ----------
        video_ids : List[VideoId]
            List of video IDs to fetch details for (max 50, validated)

        Returns
        -------
        List[Dict[str, Any]]
            List of detailed video information
        """
        # YouTube API allows max 50 video IDs per request
        if len(video_ids) > 50:
            raise ValueError("Maximum 50 video IDs allowed per request")

        request = self.service.videos().list(
            part="id,snippet,statistics,contentDetails,status,localizations,topicDetails",
            id=",".join(video_ids),
        )
        response = request.execute()

        return list(response.get("items", []))

    async def get_my_playlists(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Get playlists owned by the authenticated user.

        Parameters
        ----------
        max_results : int
            Maximum number of playlists to return (default 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of playlist information
        """
        request = self.service.playlists().list(
            part="id,snippet,status,contentDetails", mine=True, maxResults=max_results
        )
        response = request.execute()

        return list(response.get("items", []))

    async def get_playlist_videos(
        self, playlist_id: PlaylistId, max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get videos from a specific playlist.

        Parameters
        ----------
        playlist_id : PlaylistId
            The playlist ID to fetch videos from (validated)
        max_results : int
            Maximum number of videos to return (default 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of video information from the playlist
        """
        request = self.service.playlistItems().list(
            part="snippet,contentDetails,status",
            playlistId=playlist_id,
            maxResults=max_results,
        )
        response = request.execute()

        return list(response.get("items", []))

    async def search_my_videos(
        self, query: str, max_results: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Search through the authenticated user's videos.

        Parameters
        ----------
        query : str
            Search query string
        max_results : int
            Maximum number of results to return (default 25)

        Returns
        -------
        List[Dict[str, Any]]
            List of matching video information
        """
        request = self.service.search().list(
            part="id,snippet",
            forMine=True,
            q=query,
            type="video",
            maxResults=max_results,
        )
        response = request.execute()

        return list(response.get("items", []))

    async def get_video_captions(self, video_id: VideoId) -> List[Dict[str, Any]]:
        """
        Get available captions/transcripts for a video.

        Parameters
        ----------
        video_id : VideoId
            The video ID to get captions for (validated)

        Returns
        -------
        List[Dict[str, Any]]
            List of available caption tracks
        """
        try:
            request = self.service.captions().list(part="id,snippet", videoId=video_id)
            response = request.execute()
            return list(response.get("items", []))
        except Exception as e:
            # Captions API may not be accessible for all videos
            print(f"Could not fetch captions for video {video_id}: {e}")
            return []


    async def get_my_watch_later_videos(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Get videos in the authenticated user's Watch Later playlist.

        Parameters
        ----------
        max_results : int
            Maximum number of videos to return (default 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of Watch Later video information
        """
        try:
            # First get user's channel to find watch later playlist
            my_channel = await self.get_my_channel()
            
            # Get the watch later playlist ID
            watch_later_playlist_id = my_channel["contentDetails"]["relatedPlaylists"]["watchLater"]
            
            # Get videos from watch later playlist
            request = self.service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=watch_later_playlist_id,
                maxResults=max_results,
            )
            response = request.execute()
            
            return list(response.get("items", []))
        except Exception as e:
            print(f"Could not fetch Watch Later videos: {e}")
            return []

    async def check_video_in_playlist(self, video_id: VideoId, playlist_id: PlaylistId) -> bool:
        """
        Check if a specific video exists in a playlist.

        Parameters
        ----------
        video_id : VideoId
            The video ID to check for (validated)
        playlist_id : PlaylistId
            The playlist ID to check in (validated)

        Returns
        -------
        bool
            True if video is in playlist, False otherwise
        """
        try:
            request = self.service.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                videoId=video_id,
                maxResults=1
            )
            response = request.execute()
            
            return len(response.get("items", [])) > 0
        except Exception as e:
            print(f"Could not check video {video_id} in playlist {playlist_id}: {e}")
            return False

    async def get_user_playlists_for_video(self, video_id: VideoId) -> List[str]:
        """
        Get all user playlists that contain a specific video.

        Parameters
        ----------
        video_id : VideoId
            The video ID to search for (validated)

        Returns
        -------
        List[str]
            List of playlist IDs that contain the video
        """
        try:
            # Get all user playlists
            all_playlists = await self.get_my_playlists(max_results=50)
            
            video_playlists = []
            
            # Check each playlist for the video
            for playlist in all_playlists:
                playlist_id = playlist["id"]
                if await self.check_video_in_playlist(video_id, playlist_id):
                    video_playlists.append(playlist_id)
            
            return video_playlists
        except Exception as e:
            print(f"Could not get playlists for video {video_id}: {e}")
            return []

    async def get_liked_videos(self, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Get videos that the authenticated user has liked.

        Parameters
        ----------
        max_results : int
            Maximum number of liked videos to return (default 10, max 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of liked videos with details
        """
        try:
            # First get the liked videos playlist ID
            request = self.service.channels().list(part="contentDetails", mine=True)
            response = request.execute()

            if not response.get("items"):
                raise ValueError("No channel found for authenticated user")

            # Get the liked videos playlist ID
            content_details = response["items"][0].get("contentDetails", {})
            related_playlists = content_details.get("relatedPlaylists", {})
            liked_playlist_id = related_playlists.get("likes")

            if not liked_playlist_id:
                return []  # No liked videos playlist available

            # Get videos from liked playlist
            request = self.service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=liked_playlist_id,
                maxResults=min(max_results, 50),  # API max is 50
            )
            response = request.execute()

            playlist_items = response.get("items", [])

            if not playlist_items:
                return []

            # Extract video IDs to get detailed video information
            video_ids = [
                item["contentDetails"]["videoId"]
                for item in playlist_items
                if item.get("contentDetails", {}).get("videoId")
            ]

            if not video_ids:
                return []

            # Get detailed video information
            detailed_videos = await self.get_video_details(video_ids)

            return detailed_videos

        except Exception as e:
            print(f"Could not fetch liked videos: {e}")
            return []

    async def get_subscription_channels(
        self, max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get channels that the authenticated user is subscribed to.

        Parameters
        ----------
        max_results : int
            Maximum number of subscriptions to return (default 50)

        Returns
        -------
        List[Dict[str, Any]]
            List of subscribed channels
        """
        request = self.service.subscriptions().list(
            part="id,snippet,subscriberSnippet", mine=True, maxResults=max_results
        )
        response = request.execute()

        return list(response.get("items", []))

    def close(self) -> None:
        """Clean up resources."""
        self._service = None


# Global YouTube service instance
youtube_service = YouTubeService()
