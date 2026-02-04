"""
Abstract Base Class for Google Takeout parsing services.

This interface defines the contract for Takeout data parsing, enabling:
- Testability via mock implementations
- Alternative Takeout format support (future)
- Clear API boundaries for type checking
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ...models.takeout import (
    ContentGap,
    PlaylistAnalysis,
    TakeoutAnalysis,
    TakeoutData,
    TakeoutPlaylist,
    TakeoutSubscription,
    TakeoutWatchEntry,
    ViewingPatterns,
)


class TakeoutServiceInterface(ABC):
    """
    Abstract interface for Google Takeout data parsing and analysis.

    Implementations of this interface provide methods for parsing and
    analyzing YouTube data exported via Google Takeout. All operations
    are local-only with no API calls required.

    Examples
    --------
    >>> class MockTakeoutService(TakeoutServiceInterface):
    ...     async def parse_all(self) -> TakeoutData:
    ...         # Mock implementation
    ...         pass
    """

    # -------------------------------------------------------------------------
    # Parsing Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def parse_all(self) -> TakeoutData:
        """
        Parse all available Takeout data.

        Parses watch history, playlists, and subscriptions from the
        Takeout export directory.

        Returns
        -------
        TakeoutData
            Parsed and structured Takeout data containing:
            - watch_history: List of watched videos
            - playlists: List of user playlists
            - subscriptions: List of channel subscriptions
            - Aggregate statistics
        """
        pass

    @abstractmethod
    async def parse_watch_history(self) -> List[TakeoutWatchEntry]:
        """
        Parse watch history from JSON file.

        NOTE: User must select JSON format when downloading Takeout data.

        Returns
        -------
        List[TakeoutWatchEntry]
            Parsed watch history entries, each containing:
            - title: Video title
            - video_id: Extracted video ID
            - channel_name: Channel name (if available)
            - channel_id: Extracted channel ID (if available)
            - watched_at: Timestamp when video was watched
        """
        pass

    @abstractmethod
    async def parse_playlists(self) -> List[TakeoutPlaylist]:
        """
        Parse playlists from CSV files in the playlists directory.

        Each playlist is stored as a separate CSV file.

        Returns
        -------
        List[TakeoutPlaylist]
            Parsed playlists with their videos, each containing:
            - name: Playlist name
            - videos: List of video items in the playlist
            - video_count: Total video count
        """
        pass

    @abstractmethod
    async def parse_subscriptions(self) -> List[TakeoutSubscription]:
        """
        Parse channel subscriptions from CSV file.

        Returns
        -------
        List[TakeoutSubscription]
            Parsed channel subscriptions, each containing:
            - channel_id: Channel ID
            - channel_title: Channel title
            - channel_url: Channel URL
        """
        pass

    # -------------------------------------------------------------------------
    # Analysis Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def analyze_viewing_patterns(
        self, takeout_data: TakeoutData
    ) -> ViewingPatterns:
        """
        Analyze viewing patterns from Takeout data.

        Parameters
        ----------
        takeout_data : TakeoutData
            Parsed Takeout data to analyze.

        Returns
        -------
        ViewingPatterns
            Analysis of user viewing behavior including:
            - peak_viewing_hours: Top viewing hours
            - peak_viewing_days: Top viewing days
            - viewing_frequency: Videos per day
            - top_channels: Most watched channels
            - channel_diversity: How spread out viewing is
            - playlist_usage: Ratio of playlist videos to total
            - subscription_engagement: Ratio of subscribed channel views
        """
        pass

    @abstractmethod
    async def analyze_playlist_relationships(
        self, takeout_data: TakeoutData
    ) -> PlaylistAnalysis:
        """
        Analyze relationships and overlaps between playlists.

        Parameters
        ----------
        takeout_data : TakeoutData
            Parsed Takeout data to analyze.

        Returns
        -------
        PlaylistAnalysis
            Analysis of playlist organization and relationships including:
            - Overlap matrix between playlists
            - Orphan videos (watched but not in any playlist)
            - Suggested playlist improvements
        """
        pass

    @abstractmethod
    async def find_content_gaps(self, takeout_data: TakeoutData) -> List[ContentGap]:
        """
        Find content gaps in Takeout data (unwatched subscribed channels, etc.).

        Parameters
        ----------
        takeout_data : TakeoutData
            Parsed Takeout data to analyze.

        Returns
        -------
        List[ContentGap]
            Content gaps ordered by priority, each containing:
            - Video/channel identifier
            - Gap type (missing metadata, etc.)
            - Priority score for enrichment
        """
        pass

    @abstractmethod
    async def generate_comprehensive_analysis(
        self, takeout_data: TakeoutData
    ) -> TakeoutAnalysis:
        """
        Generate a comprehensive analysis combining all analysis methods.

        Parameters
        ----------
        takeout_data : TakeoutData
            Parsed Takeout data to analyze.

        Returns
        -------
        TakeoutAnalysis
            Comprehensive analysis report including:
            - viewing_patterns: Temporal and channel patterns
            - playlist_analysis: Playlist relationships
            - content_gaps: Subscription/viewing gaps
            - Summary statistics and recommendations
        """
        pass