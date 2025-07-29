"""
Google Takeout Service

Service for parsing and analyzing Google Takeout data locally.
Handles mixed file formats:
- Watch History: JSON (user must select JSON format during Takeout download)
- Playlists: CSV (individual files per playlist)
- Subscriptions: CSV
- Other data: Various CSV formats

No API calls required - pure local analysis for cost-effective data discovery.
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import parse_qs, urlparse

from ..models.takeout import (
    ChannelSummary,
    ContentGap,
    DateRange,
    PlaylistAnalysis,
    TakeoutAnalysis,
    TakeoutData,
    TakeoutPlaylist,
    TakeoutPlaylistItem,
    TakeoutSubscription,
    TakeoutWatchEntry,
    ViewingPatterns,
)

logger = logging.getLogger(__name__)


class TakeoutParsingError(Exception):
    """Raised when there's an error parsing Takeout data."""

    pass


class TakeoutService:
    """
    Service for parsing and analyzing Google Takeout data.

    Provides local analysis capabilities without requiring API calls,
    enabling cost-effective data discovery and relationship analysis.
    """

    def __init__(self, takeout_path: Path) -> None:
        """
        Initialize TakeoutService with path to extracted Takeout data.

        Parameters
        ----------
        takeout_path : Path
            Path to the extracted "YouTube and YouTube Music" folder from Google Takeout
        """
        self.takeout_path = Path(takeout_path)
        self.youtube_path = self.takeout_path / "YouTube and YouTube Music"

        if not self.youtube_path.exists():
            raise TakeoutParsingError(
                f"YouTube data not found at {self.youtube_path}. "
                f"Please ensure you've extracted the Takeout archive correctly."
            )

    async def parse_all(self) -> TakeoutData:
        """
        Parse all available Takeout data.

        Returns
        -------
        TakeoutData
            Parsed and structured Takeout data
        """
        logger.info(f"🔍 Parsing Takeout data from {self.takeout_path}")

        # Parse each data source
        watch_history = await self.parse_watch_history()
        playlists = await self.parse_playlists()
        subscriptions = await self.parse_subscriptions()

        # Create consolidated data structure
        takeout_data = TakeoutData(  # type: ignore[call-arg]
            takeout_path=self.takeout_path,
            watch_history=watch_history,
            playlists=playlists,
            subscriptions=subscriptions,
        )

        logger.info(
            f"✅ Parsed Takeout data: {takeout_data.total_videos_watched} videos, "
            f"{takeout_data.total_playlists} playlists, {takeout_data.total_subscriptions} subscriptions"
        )

        return takeout_data

    async def parse_watch_history(self) -> List[TakeoutWatchEntry]:
        """
        Parse watch history from JSON file.

        NOTE: User must select JSON format when downloading Takeout data.

        Returns
        -------
        List[TakeoutWatchEntry]
            Parsed watch history entries
        """
        history_file = self.youtube_path / "history" / "watch-history.json"

        if not history_file.exists():
            logger.warning(f"⚠️  Watch history JSON not found at {history_file}")
            logger.warning(
                "📝 Make sure you selected JSON format for 'My Activity' when downloading Takeout"
            )
            return []

        logger.info(f"📺 Parsing watch history from {history_file}")

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history_data = json.load(f)

            watch_entries: List[TakeoutWatchEntry] = []

            for entry in history_data:
                # Skip non-YouTube entries
                if entry.get("header") != "YouTube":
                    continue

                # Skip entries without video URLs
                if "titleUrl" not in entry:
                    continue

                # Extract channel info from subtitles
                channel_name = None
                channel_url = None
                if entry.get("subtitles"):
                    subtitle = entry["subtitles"][0]
                    channel_name = subtitle.get("name")
                    channel_url = subtitle.get("url")

                # Clean title (remove "Watched " prefix)
                title = entry.get("title", "")
                if title.startswith("Watched "):
                    title = title[8:]  # Remove "Watched " prefix

                # Create watch entry
                watch_entry = TakeoutWatchEntry(  # type: ignore[call-arg]
                    title=title,
                    title_url=entry["titleUrl"],
                    channel_name=channel_name,
                    channel_url=channel_url,
                    raw_time=entry.get("time"),
                )

                watch_entries.append(watch_entry)

            logger.info(f"✅ Parsed {len(watch_entries)} watch history entries")
            return watch_entries

        except json.JSONDecodeError as e:
            raise TakeoutParsingError(f"Invalid JSON in watch history file: {e}")
        except Exception as e:
            raise TakeoutParsingError(f"Error parsing watch history: {e}")

    async def parse_playlists(self) -> List[TakeoutPlaylist]:
        """
        Parse playlists from CSV files in the playlists directory.

        Each playlist is stored as a separate CSV file.

        Returns
        -------
        List[TakeoutPlaylist]
            Parsed playlists with their videos
        """
        playlists_dir = self.youtube_path / "playlists"

        if not playlists_dir.exists():
            logger.warning(f"⚠️  Playlists directory not found at {playlists_dir}")
            return []

        logger.info(f"🎵 Parsing playlists from {playlists_dir}")

        playlists: List[TakeoutPlaylist] = []
        playlist_files = list(playlists_dir.glob("*.csv"))

        for playlist_file in playlist_files:
            try:
                # Extract playlist name from filename and remove "-videos" suffix
                playlist_name = playlist_file.stem
                if playlist_name.endswith("-videos"):
                    playlist_name = playlist_name[:-7]  # Remove "-videos" suffix

                # Parse CSV file
                videos: List[TakeoutPlaylistItem] = []
                with open(playlist_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)

                    for row in reader:
                        # Actual CSV columns: "Video ID", "Playlist Video Creation Timestamp"
                        raw_ts = row.get("Playlist Video Creation Timestamp", "")
                        video_item = TakeoutPlaylistItem(  # type: ignore[call-arg]
                            video_id=row.get("Video ID", ""),
                            raw_timestamp=raw_ts,
                        )
                        videos.append(video_item)

                playlist = TakeoutPlaylist(  # type: ignore[call-arg]
                    name=playlist_name,
                    file_path=playlist_file,
                    videos=videos,
                )

                playlists.append(playlist)
                logger.info(f"   📂 {playlist_name}: {len(videos)} videos")

            except Exception as e:
                logger.warning(f"⚠️  Error parsing playlist {playlist_file}: {e}")

        logger.info(f"✅ Parsed {len(playlists)} playlists")
        return playlists

    async def parse_subscriptions(self) -> List[TakeoutSubscription]:
        """
        Parse channel subscriptions from CSV file.

        Returns
        -------
        List[TakeoutSubscription]
            Parsed channel subscriptions
        """
        subscriptions_file = self.youtube_path / "subscriptions" / "subscriptions.csv"

        if not subscriptions_file.exists():
            logger.warning(f"⚠️  Subscriptions file not found at {subscriptions_file}")
            return []

        logger.info(f"📺 Parsing subscriptions from {subscriptions_file}")

        try:
            subscriptions: List[TakeoutSubscription] = []
            with open(subscriptions_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Actual CSV columns: "Channel Id", "Channel Url", "Channel Title"
                    subscription = TakeoutSubscription(
                        channel_id=row.get("Channel Id", ""),  # Include the Channel Id
                        channel_title=row.get("Channel Title", ""),
                        channel_url=row.get("Channel Url", ""),  # Note: "Url" not "URL"
                    )
                    subscriptions.append(subscription)

            logger.info(f"✅ Parsed {len(subscriptions)} subscriptions")
            return subscriptions

        except Exception as e:
            raise TakeoutParsingError(f"Error parsing subscriptions: {e}")

    async def analyze_viewing_patterns(
        self, takeout_data: TakeoutData
    ) -> ViewingPatterns:
        """
        Analyze viewing patterns from Takeout data.

        Parameters
        ----------
        takeout_data : TakeoutData
            Parsed Takeout data

        Returns
        -------
        ViewingPatterns
            Analysis of user viewing behavior
        """
        logger.info("📊 Analyzing viewing patterns...")

        # Analyze temporal patterns
        watched_dates = [
            entry.watched_at for entry in takeout_data.watch_history if entry.watched_at
        ]

        peak_hours = []
        peak_days = []
        viewing_frequency = 0.0

        if watched_dates:
            # Extract hours and days
            hours = [dt.hour for dt in watched_dates]
            days = [dt.strftime("%A") for dt in watched_dates]

            # Find peak hours (top 3)
            hour_counts: Dict[int, int] = {}
            for hour in hours:
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
            peak_hours = sorted(
                hour_counts.keys(), key=lambda x: hour_counts[x], reverse=True
            )[:3]

            # Find peak days (top 3)
            day_counts: Dict[str, int] = {}
            for day in days:
                day_counts[day] = day_counts.get(day, 0) + 1
            peak_days = sorted(
                day_counts.keys(), key=lambda x: day_counts[x], reverse=True
            )[:3]

            # Calculate viewing frequency
            if takeout_data.date_range:
                date_range = takeout_data.date_range
                total_days = (date_range[1] - date_range[0]).days or 1
                viewing_frequency = len(takeout_data.watch_history) / total_days

        # Analyze channel patterns
        channel_counts: Dict[str, int] = {}
        for entry in takeout_data.watch_history:
            if entry.channel_name:
                channel_counts[entry.channel_name] = (
                    channel_counts.get(entry.channel_name, 0) + 1
                )

        # Create top channels summaries
        top_channels: List[ChannelSummary] = []
        for channel_name, count in sorted(
            channel_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]:
            channel_entries = [
                e for e in takeout_data.watch_history if e.channel_name == channel_name
            ]

            # Find channel ID if available
            channel_id = None
            channel_url = None
            for entry in channel_entries:
                if entry.channel_id:
                    channel_id = entry.channel_id
                    channel_url = entry.channel_url
                    break

            # Calculate engagement metrics
            dates = [e.watched_at for e in channel_entries if e.watched_at]
            first_watched = min(dates) if dates else None
            last_watched = max(dates) if dates else None

            # Check if subscribed
            is_subscribed = any(
                sub.channel_title == channel_name or sub.channel_id == channel_id
                for sub in takeout_data.subscriptions
            )

            channel_summary = ChannelSummary(
                channel_id=channel_id,
                channel_name=channel_name,
                channel_url=channel_url,
                videos_watched=count,
                total_watch_time_minutes=None,
                first_watched=first_watched,
                last_watched=last_watched,
                videos_in_playlists=0,
                is_subscribed=is_subscribed,
                engagement_score=min(
                    count / 100, 1.0
                ),  # Simple score based on watch count
                consistency_score=0.0,
            )
            top_channels.append(channel_summary)

        # Calculate channel diversity (how spread out viewing is)
        total_videos = len(takeout_data.watch_history)
        if total_videos > 0 and channel_counts:
            # Use entropy-like measure for diversity
            channel_diversity = 1.0 - (max(channel_counts.values()) / total_videos)
        else:
            channel_diversity = 0.0

        # Analyze playlist usage
        total_playlist_videos = sum(
            len(playlist.videos) for playlist in takeout_data.playlists
        )
        playlist_usage = (
            total_playlist_videos / total_videos if total_videos > 0 else 0.0
        )

        # Calculate subscription engagement
        subscribed_channels = {sub.channel_title for sub in takeout_data.subscriptions}
        subscribed_videos = sum(
            1
            for entry in takeout_data.watch_history
            if entry.channel_name in subscribed_channels
        )
        subscription_engagement = (
            subscribed_videos / total_videos if total_videos > 0 else 0.0
        )

        return ViewingPatterns(
            peak_viewing_hours=peak_hours,
            peak_viewing_days=peak_days,
            viewing_frequency=viewing_frequency,
            top_channels=top_channels,
            channel_diversity=channel_diversity,
            playlist_usage=playlist_usage,
            subscription_engagement=subscription_engagement,
        )

    async def analyze_playlist_relationships(
        self, takeout_data: TakeoutData
    ) -> PlaylistAnalysis:
        """
        Analyze relationships and overlaps between playlists.

        Parameters
        ----------
        takeout_data : TakeoutData
            Parsed Takeout data

        Returns
        -------
        PlaylistAnalysis
            Analysis of playlist organization and relationships
        """
        logger.info("📊 Analyzing playlist relationships...")

        if not takeout_data.playlists:
            return PlaylistAnalysis()

        # Build playlist video mappings
        playlist_videos: Dict[str, Set[str]] = {}
        all_playlist_video_ids: Set[str] = set()

        for playlist in takeout_data.playlists:
            video_ids = {video.video_id for video in playlist.videos if video.video_id}
            playlist_videos[playlist.name] = video_ids
            all_playlist_video_ids.update(video_ids)

        # Calculate overlap matrix
        overlap_matrix: Dict[str, Dict[str, int]] = {}
        overlap_percentages: Dict[str, Dict[str, float]] = {}

        for playlist1_name, videos1 in playlist_videos.items():
            overlap_matrix[playlist1_name] = {}
            overlap_percentages[playlist1_name] = {}

            for playlist2_name, videos2 in playlist_videos.items():
                if playlist1_name != playlist2_name:
                    overlap_count = len(videos1.intersection(videos2))
                    overlap_matrix[playlist1_name][playlist2_name] = overlap_count

                    # Calculate percentage (based on smaller playlist)
                    smaller_size = min(len(videos1), len(videos2))
                    overlap_pct = (
                        (overlap_count / smaller_size * 100) if smaller_size > 0 else 0
                    )
                    overlap_percentages[playlist1_name][playlist2_name] = overlap_pct

        # Find orphaned videos (watched but not in any playlist)
        all_watched_video_ids = takeout_data.get_unique_video_ids()
        orphaned_videos = list(all_watched_video_ids - all_playlist_video_ids)

        # Find over-categorized videos (in many playlists)
        video_playlist_counts: Dict[str, int] = {}
        for playlist_name, video_ids in playlist_videos.items():
            for video_id in video_ids:
                video_playlist_counts[video_id] = (
                    video_playlist_counts.get(video_id, 0) + 1
                )

        over_categorized = [
            video_id
            for video_id, count in video_playlist_counts.items()
            if count >= 3  # Videos in 3+ playlists
        ]

        # Calculate playlist diversity scores (how diverse the content is)
        # Build video_id -> channel_name mapping from watch history
        video_to_channel = {
            entry.video_id: entry.channel_name
            for entry in takeout_data.watch_history
            if entry.video_id and entry.channel_name
        }

        playlist_diversity_scores: Dict[str, float] = {}
        for playlist in takeout_data.playlists:
            # Simple diversity based on channel variety using watch history lookup
            channels = {
                video_to_channel.get(video.video_id)
                for video in playlist.videos
                if video.video_id and video_to_channel.get(video.video_id)
            }
            diversity = len(channels) / len(playlist.videos) if playlist.videos else 0
            playlist_diversity_scores[playlist.name] = min(diversity, 1.0)

        # Get playlist sizes
        playlist_sizes: Dict[str, int] = {
            playlist.name: len(playlist.videos) for playlist in takeout_data.playlists
        }

        return PlaylistAnalysis(
            playlist_overlap_matrix=overlap_matrix,
            overlap_percentages=overlap_percentages,
            orphaned_videos=orphaned_videos,
            over_categorized_videos=over_categorized,
            playlist_diversity_scores=playlist_diversity_scores,
            playlist_sizes=playlist_sizes,
        )

    async def find_content_gaps(self, takeout_data: TakeoutData) -> List[ContentGap]:
        """
        Identify content that lacks metadata and would benefit from API enrichment.

        Parameters
        ----------
        takeout_data : TakeoutData
            Parsed Takeout data

        Returns
        -------
        List[ContentGap]
            Content gaps ordered by priority
        """
        logger.info("🔍 Identifying content gaps...")

        content_gaps: List[ContentGap] = []
        video_playlist_counts: Dict[str, int] = {}

        # Count playlist memberships
        for playlist in takeout_data.playlists:
            for video in playlist.videos:
                if video.video_id:
                    video_playlist_counts[video.video_id] = (
                        video_playlist_counts.get(video.video_id, 0) + 1
                    )

        # Analyze each unique video
        unique_videos: Dict[str, TakeoutWatchEntry] = {}
        for entry in takeout_data.watch_history:
            if entry.video_id and entry.video_id not in unique_videos:
                unique_videos[entry.video_id] = entry

        for video_id, entry in unique_videos.items():
            missing_fields = []

            # Always missing from Takeout (would benefit from API)
            missing_fields.extend(
                [
                    "duration",
                    "tags",
                    "transcripts",
                    "view_count",
                    "like_count",
                    "description",
                    "topic_categories",
                ]
            )

            # Calculate priority score
            priority_score = 0.0

            # Higher priority for videos in playlists
            playlist_count = video_playlist_counts.get(video_id, 0)
            priority_score += min(playlist_count * 0.2, 0.6)

            # Higher priority for recent videos
            if entry.watched_at:
                # Make datetime timezone-aware for comparison
                now_utc = datetime.utcnow().replace(tzinfo=entry.watched_at.tzinfo)
                days_since = (now_utc - entry.watched_at).days
                recency_score = max(0, 1 - (days_since / 365))  # Decay over a year
                priority_score += recency_score * 0.4

            content_gap = ContentGap(
                video_id=video_id,
                title=entry.title,
                channel_name=entry.channel_name,
                missing_fields=missing_fields,
                priority_score=min(priority_score, 1.0),
                in_playlists=playlist_count,
                watch_count=0,
                last_watched=entry.watched_at,
            )

            content_gaps.append(content_gap)

        # Sort by priority score
        content_gaps.sort(key=lambda x: x.priority_score, reverse=True)

        logger.info(f"✅ Identified {len(content_gaps)} content gaps")
        return content_gaps

    async def generate_comprehensive_analysis(
        self, takeout_data: Optional[TakeoutData] = None
    ) -> TakeoutAnalysis:
        """
        Generate comprehensive analysis of Takeout data.

        Parameters
        ----------
        takeout_data : Optional[TakeoutData]
            Parsed Takeout data. If None, will parse from scratch.

        Returns
        -------
        TakeoutAnalysis
            Comprehensive analysis results
        """
        if takeout_data is None:
            takeout_data = await self.parse_all()

        logger.info("🔬 Generating comprehensive Takeout analysis...")

        # Generate all analyses
        viewing_patterns = await self.analyze_viewing_patterns(takeout_data)
        playlist_analysis = await self.analyze_playlist_relationships(takeout_data)
        content_gaps = await self.find_content_gaps(takeout_data)

        # Create date range
        date_range = None
        if takeout_data.date_range:
            start_date, end_date = takeout_data.date_range
            total_days = (end_date - start_date).days
            date_range = DateRange(
                start_date=start_date, end_date=end_date, total_days=total_days
            )

        # Extract high priority videos (top 20% by priority score)
        high_priority_videos = [
            gap.video_id for gap in content_gaps[: max(1, len(content_gaps) // 5)]
        ]

        # Estimate data completeness (very rough heuristic)
        data_completeness = 0.8  # Assume 80% completeness for now

        # Calculate content diversity (based on channel variety)
        unique_channels = len(
            {
                entry.channel_name
                for entry in takeout_data.watch_history
                if entry.channel_name
            }
        )
        total_videos = len(takeout_data.watch_history)
        content_diversity_score = min(
            unique_channels / max(total_videos, 1) * 5, 1.0
        )  # Scale factor

        analysis = TakeoutAnalysis(
            total_videos_watched=takeout_data.total_videos_watched,
            unique_channels=unique_channels,
            playlist_count=takeout_data.total_playlists,
            subscription_count=takeout_data.total_subscriptions,
            date_range=date_range,
            data_completeness=data_completeness,
            viewing_patterns=viewing_patterns,
            playlist_analysis=playlist_analysis,
            top_channels=viewing_patterns.top_channels,
            content_gaps=content_gaps,
            high_priority_videos=high_priority_videos,
            content_diversity_score=content_diversity_score,
            analysis_version="1.0",
        )

        logger.info("✅ Comprehensive analysis complete")
        return analysis

    async def analyze_playlist_overlap(
        self, takeout_data: Optional[TakeoutData] = None
    ) -> Dict[str, Dict[str, int]]:
        """
        Analyze overlap between playlists to identify similar content groupings.

        Parameters
        ----------
        takeout_data : Optional[TakeoutData]
            Parsed Takeout data. If None, will parse from scratch.

        Returns
        -------
        Dict[str, Dict[str, int]]
            Matrix of playlist overlaps with video counts
        """
        if takeout_data is None:
            takeout_data = await self.parse_all()

        logger.info("🔗 Analyzing playlist overlaps...")

        if not takeout_data.playlists:
            return {}

        # Build video mappings for each playlist
        playlist_videos: Dict[str, Set[str]] = {}
        for playlist in takeout_data.playlists:
            video_ids = {video.video_id for video in playlist.videos if video.video_id}
            playlist_videos[playlist.name] = video_ids

        # Calculate overlap matrix
        overlap_matrix: Dict[str, Dict[str, int]] = {}
        for playlist1_name, videos1 in playlist_videos.items():
            overlap_matrix[playlist1_name] = {}

            for playlist2_name, videos2 in playlist_videos.items():
                if playlist1_name != playlist2_name:
                    overlap_count = len(videos1.intersection(videos2))
                    if overlap_count > 0:  # Only include non-zero overlaps
                        overlap_matrix[playlist1_name][playlist2_name] = overlap_count

        return overlap_matrix

    async def analyze_channel_clusters(
        self, takeout_data: Optional[TakeoutData] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Analyze channel viewing patterns to identify content clusters.

        Parameters
        ----------
        takeout_data : Optional[TakeoutData]
            Parsed Takeout data. If None, will parse from scratch.

        Returns
        -------
        Dict[str, Dict[str, any]]
            Channel clusters with viewing patterns and recommendations
        """
        if takeout_data is None:
            takeout_data = await self.parse_all()

        logger.info("📊 Analyzing channel clusters...")

        # Analyze channel viewing patterns
        channel_patterns: Dict[str, Dict[str, Any]] = {}
        for entry in takeout_data.watch_history:
            if not entry.channel_name:
                continue

            if entry.channel_name not in channel_patterns:
                channel_patterns[entry.channel_name] = {
                    "videos_watched": 0,
                    "watch_dates": [],
                    "channel_id": entry.channel_id,
                    "channel_url": entry.channel_url,
                    "is_subscribed": False,
                    "avg_frequency": 0.0,
                    "engagement_level": "low",
                }

            pattern = channel_patterns[entry.channel_name]
            pattern["videos_watched"] += 1
            if entry.watched_at:
                pattern["watch_dates"].append(entry.watched_at)

        # Check subscription status
        subscribed_channels = {sub.channel_title for sub in takeout_data.subscriptions}
        for channel_name in channel_patterns:
            channel_patterns[channel_name]["is_subscribed"] = (
                channel_name in subscribed_channels
            )

        # Calculate engagement metrics
        for channel_name, pattern in channel_patterns.items():
            # Calculate viewing frequency (videos per month)
            if pattern["watch_dates"]:
                date_range = max(pattern["watch_dates"]) - min(pattern["watch_dates"])
                months = max(date_range.days / 30, 1)
                pattern["avg_frequency"] = pattern["videos_watched"] / months

                # Determine engagement level
                if pattern["videos_watched"] >= 20 or pattern["avg_frequency"] >= 2.0:
                    pattern["engagement_level"] = "high"
                elif pattern["videos_watched"] >= 5 or pattern["avg_frequency"] >= 0.5:
                    pattern["engagement_level"] = "medium"

        # Create clusters based on engagement levels
        clusters: Dict[str, Dict[str, Dict[str, Any]]] = {
            "high_engagement": {},
            "medium_engagement": {},
            "low_engagement": {},
            "unsubscribed_frequent": {},  # Channels watched often but not subscribed
            "subscribed_inactive": {},  # Subscribed but rarely watched
        }

        for channel_name, pattern in channel_patterns.items():
            if pattern["engagement_level"] == "high":
                clusters["high_engagement"][channel_name] = pattern
            elif pattern["engagement_level"] == "medium":
                clusters["medium_engagement"][channel_name] = pattern
            else:
                clusters["low_engagement"][channel_name] = pattern

            # Special clusters for subscription patterns
            if pattern["videos_watched"] >= 5 and not pattern["is_subscribed"]:
                clusters["unsubscribed_frequent"][channel_name] = pattern

        # Find subscribed channels with low activity
        for sub in takeout_data.subscriptions:
            if sub.channel_title not in channel_patterns:
                # Never watched videos from this subscribed channel
                clusters["subscribed_inactive"][sub.channel_title] = {
                    "videos_watched": 0,
                    "channel_id": sub.channel_id,
                    "channel_url": sub.channel_url,
                    "is_subscribed": True,
                    "engagement_level": "none",
                }

        return clusters

    async def analyze_temporal_patterns(
        self, takeout_data: Optional[TakeoutData] = None
    ) -> Dict[str, Any]:
        """
        Analyze temporal patterns in viewing behavior.

        Parameters
        ----------
        takeout_data : Optional[TakeoutData]
            Parsed Takeout data. If None, will parse from scratch.

        Returns
        -------
        Dict[str, any]
            Temporal analysis including peak times, seasonal patterns, etc.
        """
        if takeout_data is None:
            takeout_data = await self.parse_all()

        logger.info("⏰ Analyzing temporal patterns...")

        # Extract dates with valid timestamps
        watch_times = [
            entry.watched_at for entry in takeout_data.watch_history if entry.watched_at
        ]

        if not watch_times:
            return {"error": "No valid timestamps found in watch history"}

        # Analyze hourly patterns
        hourly_counts: Dict[int, int] = {}
        for dt in watch_times:
            hour = dt.hour
            hourly_counts[hour] = hourly_counts.get(hour, 0) + 1

        # Analyze daily patterns (day of week)
        daily_counts: Dict[str, int] = {}
        for dt in watch_times:
            day = dt.strftime("%A")
            daily_counts[day] = daily_counts.get(day, 0) + 1

        # Analyze monthly patterns
        monthly_counts: Dict[str, int] = {}
        for dt in watch_times:
            month = dt.strftime("%Y-%m")
            monthly_counts[month] = monthly_counts.get(month, 0) + 1

        # Find peak patterns
        peak_hour = (
            max(hourly_counts.items(), key=lambda x: x[1])[0] if hourly_counts else None
        )
        peak_day = (
            max(daily_counts.items(), key=lambda x: x[1])[0] if daily_counts else None
        )
        peak_month = (
            max(monthly_counts.items(), key=lambda x: x[1])[0]
            if monthly_counts
            else None
        )

        # Calculate viewing streaks (consecutive days with activity)
        dates_only = sorted(set(dt.date() for dt in watch_times))
        current_streak = 0
        max_streak = 0

        for i, date in enumerate(dates_only):
            if i == 0:
                current_streak = 1
            else:
                prev_date = dates_only[i - 1]
                if (date - prev_date).days == 1:
                    current_streak += 1
                else:
                    max_streak = max(max_streak, current_streak)
                    current_streak = 1
        max_streak = max(max_streak, current_streak)

        # Analyze content type patterns by time
        channel_time_patterns: Dict[str, Dict[int, int]] = {}
        for entry in takeout_data.watch_history:
            if entry.channel_name and entry.watched_at:
                hour = entry.watched_at.hour
                if entry.channel_name not in channel_time_patterns:
                    channel_time_patterns[entry.channel_name] = {}
                channel_time_patterns[entry.channel_name][hour] = (
                    channel_time_patterns[entry.channel_name].get(hour, 0) + 1
                )

        return {
            "hourly_distribution": hourly_counts,
            "daily_distribution": daily_counts,
            "monthly_distribution": monthly_counts,
            "peak_viewing_hour": peak_hour,
            "peak_viewing_day": peak_day,
            "peak_viewing_month": peak_month,
            "max_consecutive_days": max_streak,
            "total_active_days": len(dates_only),
            "channel_time_preferences": channel_time_patterns,
            "date_range": {
                "start": min(watch_times).isoformat(),
                "end": max(watch_times).isoformat(),
                "duration_days": (max(watch_times) - min(watch_times)).days,
            },
        }
