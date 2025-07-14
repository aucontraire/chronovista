"""
YouTube Data API service for fetching user data.

Provides high-level methods for interacting with YouTube Data API v3,
including channel info, videos, playlists, and watch history.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from chronovista.auth import youtube_oauth


class YouTubeService:
    """
    YouTube Data API service.
    
    Provides methods for fetching YouTube data using authenticated API client.
    """

    def __init__(self) -> None:
        """Initialize YouTube service."""
        self._service = None

    @property
    def service(self):
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
            part="id,snippet,statistics,contentDetails,status,brandingSettings",
            mine=True
        )
        response = request.execute()
        
        if not response.get("items"):
            raise ValueError("No channel found for authenticated user")
        
        return response["items"][0]

    async def get_channel_videos(self, channel_id: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Get videos from a specific channel.
        
        Parameters
        ----------
        channel_id : str
            The channel ID to fetch videos from
        max_results : int
            Maximum number of videos to return (default 50)
            
        Returns
        -------
        List[Dict[str, Any]]
            List of video information
        """
        # First get the uploads playlist ID
        request = self.service.channels().list(
            part="contentDetails",
            id=channel_id
        )
        response = request.execute()
        
        if not response.get("items"):
            raise ValueError(f"Channel {channel_id} not found")
        
        uploads_playlist_id = response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        # Get videos from uploads playlist
        request = self.service.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=max_results
        )
        response = request.execute()
        
        return response.get("items", [])

    async def get_video_details(self, video_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get detailed information about specific videos.
        
        Parameters
        ----------
        video_ids : List[str]
            List of video IDs to fetch details for (max 50)
            
        Returns
        -------
        List[Dict[str, Any]]
            List of detailed video information
        """
        # YouTube API allows max 50 video IDs per request
        if len(video_ids) > 50:
            raise ValueError("Maximum 50 video IDs allowed per request")
        
        request = self.service.videos().list(
            part="id,snippet,statistics,contentDetails,status,localizations",
            id=",".join(video_ids)
        )
        response = request.execute()
        
        return response.get("items", [])

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
            part="id,snippet,status,contentDetails",
            mine=True,
            maxResults=max_results
        )
        response = request.execute()
        
        return response.get("items", [])

    async def get_playlist_videos(self, playlist_id: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Get videos from a specific playlist.
        
        Parameters
        ----------
        playlist_id : str
            The playlist ID to fetch videos from
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
            maxResults=max_results
        )
        response = request.execute()
        
        return response.get("items", [])

    async def search_my_videos(self, query: str, max_results: int = 25) -> List[Dict[str, Any]]:
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
            maxResults=max_results
        )
        response = request.execute()
        
        return response.get("items", [])

    async def get_video_captions(self, video_id: str) -> List[Dict[str, Any]]:
        """
        Get available captions/transcripts for a video.
        
        Parameters
        ----------
        video_id : str
            The video ID to get captions for
            
        Returns
        -------
        List[Dict[str, Any]]
            List of available caption tracks
        """
        try:
            request = self.service.captions().list(
                part="id,snippet",
                videoId=video_id
            )
            response = request.execute()
            return response.get("items", [])
        except Exception as e:
            # Captions API may not be accessible for all videos
            print(f"Could not fetch captions for video {video_id}: {e}")
            return []

    async def get_subscription_channels(self, max_results: int = 50) -> List[Dict[str, Any]]:
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
            part="id,snippet,subscriberSnippet",
            mine=True,
            maxResults=max_results
        )
        response = request.execute()
        
        return response.get("items", [])

    def close(self) -> None:
        """Clean up resources."""
        self._service = None


# Global YouTube service instance
youtube_service = YouTubeService()