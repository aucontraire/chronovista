"""
Takeout CLI Commands

Commands for exploring and analyzing Google Takeout data locally.
Enables cost-effective data discovery without API calls.

Commands:
- peek: Explore different aspects of takeout data
- analyze: Generate comprehensive analysis
- relationships: Analyze data relationships
- sync: Sync selected data to database
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from ...config.database import db_manager
from ...models.takeout.takeout_data import TakeoutData
from ...repositories.topic_category_repository import TopicCategoryRepository
from ...repositories.video_topic_repository import VideoTopicRepository
from ...services.seeding import ProgressCallback
from ...services.takeout_seeding_service import TakeoutSeedingService
from ...services.takeout_service import TakeoutParsingError, TakeoutService

# SeedingResult removed - using dict of SeedResult from modular system


# Repository imports removed - handled by TakeoutSeedingService

console = Console()
takeout_app = typer.Typer(
    name="takeout", help="📁 Explore Google Takeout data locally (no API calls)"
)

# Repository instances for topic integration
topic_category_repository = TopicCategoryRepository()
video_topic_repository = VideoTopicRepository()


async def _build_video_title_lookup(takeout_service: TakeoutService) -> dict[str, str]:
    """
    Build a lookup dictionary of video ID -> video title from watch history.

    Returns
    -------
    dict[str, str]
        Dictionary mapping video IDs to video titles
    """
    video_titles = {}
    try:
        watch_history = await takeout_service.parse_watch_history()
        video_titles = {
            entry.video_id: entry.title
            for entry in watch_history
            if entry.video_id and entry.title
        }
    except Exception:
        # If watch history unavailable, return empty dict
        pass
    return video_titles


@takeout_app.command("peek")
def peek_data(
    data_type: str = typer.Argument(
        ...,
        help="Type of data to peek at: playlists, history, channels, subscriptions, comments, chats",
    ),
    filter_name: Optional[str] = typer.Argument(
        None, help="Optional filter/name (e.g., playlist name, channel name)"
    ),
    takeout_path: Path = typer.Option(
        Path("takeout"), "--path", "-p", help="Path to Takeout directory"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of items to show"),
    recent: bool = typer.Option(
        False, "--recent", "-r", help="Show most recent items first"
    ),
    oldest: bool = typer.Option(
        False, "--oldest", "-o", help="Sort by oldest first (chronological)"
    ),
    all_items: bool = typer.Option(
        False, "--all", "-a", help="Show all items (no limit)"
    ),
    topic_filter: Optional[str] = typer.Option(
        None,
        "--topic",
        help="Filter content by topic ID (requires synced topic associations)",
    ),
) -> None:
    """
    👀 Peek at your Google Takeout data without API calls.

    Explore your local Takeout data to understand patterns and relationships
    before deciding what to sync to the database.

    Examples:
        chronovista takeout peek playlists
        chronovista takeout peek playlists "Aaron Mate" --limit=50
        chronovista takeout peek history --recent --limit=10 --topic=25
        chronovista takeout peek channels "Corey Schafer"
        chronovista takeout peek comments --recent --limit=15
    """
    import asyncio

    async def run_peek() -> None:
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"📁 Loading {data_type} from Takeout...", total=None
                )

                # Initialize TakeoutService
                takeout_service = TakeoutService(takeout_path)

                # Validate topic filter if provided
                if topic_filter:
                    progress.update(task, description="🏷️ Validating topic filter...")
                    async for session in db_manager.get_session():
                        if not await topic_category_repository.exists(
                            session, topic_filter
                        ):
                            console.print(
                                Panel(
                                    f"[red]❌ Invalid topic ID: {topic_filter}[/red]\n"
                                    "Use chronovista topics list to see available topics.",
                                    title="Topic Filter Error",
                                    border_style="red",
                                )
                            )
                            return

                        # Get topic name for display
                        topic_category = await topic_category_repository.get(
                            session, topic_filter
                        )
                        topic_name = (
                            topic_category.category_name
                            if topic_category
                            else f"Topic {topic_filter}"
                        )
                        console.print(
                            f"[blue]🔍 Filtering by topic: {topic_name}[/blue]"
                        )
                        console.print(
                            "[yellow]ℹ️ Topic filtering requires video-topic associations to be synced first[/yellow]"
                        )

                    progress.update(
                        task, description=f"📁 Loading {data_type} from Takeout..."
                    )

                # Determine effective limit
                effective_limit = None if all_items else limit

                # Determine sort order
                if recent and oldest:
                    console.print("❌ Cannot use both --recent and --oldest flags")
                    raise typer.Exit(1)
                sort_order = "recent" if recent else ("oldest" if oldest else "default")

                if data_type.lower() == "playlists":
                    await _peek_playlists(
                        takeout_service,
                        effective_limit,
                        sort_order,
                        progress,
                        task,
                        filter_name,
                    )
                elif data_type.lower() in ["history", "watch-history"]:
                    await _peek_watch_history(
                        takeout_service,
                        effective_limit,
                        sort_order,
                        progress,
                        task,
                        filter_name,
                    )
                elif data_type.lower() in ["channels", "subscriptions"]:
                    await _peek_subscriptions(
                        takeout_service, effective_limit, progress, task, filter_name
                    )
                elif data_type.lower() == "comments":
                    await _peek_comments(
                        takeout_service,
                        effective_limit,
                        sort_order,
                        progress,
                        task,
                        filter_name,
                    )
                elif data_type.lower() in ["chats", "livechats", "live-chats"]:
                    await _peek_live_chats(
                        takeout_service,
                        effective_limit,
                        sort_order,
                        progress,
                        task,
                        filter_name,
                    )
                else:
                    console.print(f"❌ Unknown data type: {data_type}")
                    console.print(
                        "Available types: playlists, history, channels, subscriptions, comments, chats"
                    )
                    raise typer.Exit(1)

        except TakeoutParsingError as e:
            console.print(f"❌ Error parsing Takeout data: {e}")
            console.print("\n💡 Make sure:")
            console.print("  • You've extracted the Takeout archive")
            console.print("  • You selected JSON format for watch history")
            console.print("  • The path points to the extracted folder")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"❌ Unexpected error: {e}")
            raise typer.Exit(1)

    asyncio.run(run_peek())


async def _peek_playlists(
    takeout_service: TakeoutService,
    limit: Optional[int],
    sort_order: str,
    progress: Progress,
    task_id: Any,
    filter_name: Optional[str] = None,
) -> None:
    """Display playlists information in a rich table."""
    try:
        # Parse playlists
        playlists = await takeout_service.parse_playlists()
        progress.update(task_id, description="📊 Analyzing playlist data...")

        if not playlists:
            console.print("📭 No playlists found in Takeout data")
            return

        # Filter by name if specified
        if filter_name:
            original_count = len(playlists)
            playlists = [p for p in playlists if filter_name.lower() in p.name.lower()]
            if not playlists:
                console.print(f"📭 No playlists found matching '{filter_name}'")
                console.print(
                    f"💡 Found {original_count} total playlists. Try a partial name match."
                )
                return
            elif len(playlists) == 1:
                # If exact match, show detailed view of that playlist
                await _show_detailed_playlist(playlists[0], limit, takeout_service)
                return

        # Sort playlists
        if sort_order == "recent":
            # Sort by most recent video added (if timestamps available)
            def get_playlist_latest_timestamp(playlist: Any) -> datetime:
                timestamps: List[datetime] = [
                    v.creation_timestamp
                    for v in playlist.videos
                    if v.creation_timestamp
                    and isinstance(v.creation_timestamp, datetime)
                ]
                if timestamps:
                    latest_timestamp: datetime = max(timestamps)
                    return latest_timestamp
                else:
                    # Return a very old timezone-aware datetime for playlists with no timestamps
                    from datetime import timezone

                    return datetime.min.replace(tzinfo=timezone.utc)

            playlists.sort(key=get_playlist_latest_timestamp, reverse=True)
        elif sort_order == "oldest":
            # Sort by oldest video added (if timestamps available)
            def get_playlist_earliest_timestamp(playlist: Any) -> datetime:
                timestamps: List[datetime] = [
                    v.creation_timestamp
                    for v in playlist.videos
                    if v.creation_timestamp
                    and isinstance(v.creation_timestamp, datetime)
                ]
                if timestamps:
                    earliest_timestamp: datetime = min(timestamps)
                    return earliest_timestamp
                else:
                    # Return a very recent timezone-aware datetime for playlists with no timestamps
                    from datetime import timezone

                    return datetime.max.replace(tzinfo=timezone.utc)

            playlists.sort(key=get_playlist_earliest_timestamp, reverse=False)
        else:
            # Sort by number of videos (largest first)
            playlists.sort(key=lambda p: len(p.videos), reverse=True)

        # Create rich table
        table = Table(
            title=f"🎵 Your Playlists ({len(playlists)} total)",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Playlist", style="cyan", width=50)
        table.add_column("Videos", style="green", justify="right")
        table.add_column("Recent Activity", style="yellow", width=20)
        table.add_column("Date Range", style="blue", width=25)

        for playlist in playlists[:limit]:
            # Calculate date range
            timestamps = [
                v.creation_timestamp for v in playlist.videos if v.creation_timestamp
            ]
            if timestamps:
                first_date = min(timestamps).strftime("%Y-%m")
                last_date = max(timestamps).strftime("%Y-%m")
                date_range = (
                    f"{first_date} → {last_date}"
                    if first_date != last_date
                    else first_date
                )
                recent_activity = max(timestamps).strftime("%Y-%m-%d")
            else:
                date_range = "Unknown"
                recent_activity = "Unknown"

            table.add_row(
                playlist.name, str(len(playlist.videos)), recent_activity, date_range
            )

        console.print(table)

        # Summary insights
        total_videos = sum(len(p.videos) for p in playlists)
        avg_size = total_videos / len(playlists) if playlists else 0
        largest_playlist = max(playlists, key=lambda p: len(p.videos))

        console.print(f"\n💡 Insights:")
        console.print(f"   • Total videos across all playlists: {total_videos:,}")
        console.print(f"   • Average playlist size: {avg_size:.1f} videos")
        console.print(
            f"   • Largest playlist: '{largest_playlist.name}' ({len(largest_playlist.videos)} videos)"
        )

        if limit is not None and len(playlists) > limit:
            console.print(
                f"   • Showing {limit} of {len(playlists)} playlists (use --limit to see more)"
            )

        if filter_name and len(playlists) > 1:
            console.print(f"\n🔍 Filter Results:")
            console.print(
                f"   • Found {len(playlists)} playlists matching '{filter_name}'"
            )
            console.print(
                f'   • Use exact name for detailed view: chronovista takeout peek playlists "{playlists[0].name}"'
            )

    except Exception as e:
        console.print(f"❌ Error analyzing playlists: {e}")


async def _show_detailed_playlist(
    playlist: Any,
    limit: Optional[int],
    takeout_service: Optional[TakeoutService] = None,
) -> None:
    """Show detailed view of a single playlist."""
    table = Table(
        title=f"🎵 Playlist: {playlist.name} ({len(playlist.videos)} videos)",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Video ID", style="cyan", width=15)
    table.add_column("Video Title", style="green", width=60)
    table.add_column("Added", style="yellow", width=20)

    # Get watch history for title lookup if available
    video_titles = {}
    total_watch_entries = 0
    matched_titles = 0

    if takeout_service:
        video_titles = await _build_video_title_lookup(takeout_service)

        if video_titles:
            # Count how many playlist videos we can match
            playlist_video_ids = {v.video_id for v in playlist.videos}
            matched_titles = len(
                playlist_video_ids.intersection(set(video_titles.keys()))
            )

            # Estimate total watch entries from video_titles size
            total_watch_entries = len(video_titles)

    # Sort videos by date added (most recent first)
    videos = sorted(
        playlist.videos,
        key=lambda v: v.creation_timestamp or datetime.min,
        reverse=True,
    )

    for video in videos[:limit]:
        timestamp_str = "Unknown"
        if video.creation_timestamp:
            timestamp_str = video.creation_timestamp.strftime("%Y-%m-%d %H:%M")

        # Get video title from watch history
        video_title = video_titles.get(video.video_id, "Title not found")
        if len(video_title) > 37:
            video_title = video_title[:37] + "..."

        table.add_row(video.video_id, video_title, timestamp_str)

    console.print(table)

    if limit is not None and len(playlist.videos) > limit:
        console.print(
            f"\n💡 Showing {limit} of {len(playlist.videos)} videos (use --limit to see more)"
        )

    # Show title matching info
    if takeout_service:
        console.print(f"\n📊 Title Lookup Results:")
        console.print(f"   • Watch history entries: {total_watch_entries:,}")
        console.print(
            f"   • Video IDs extracted from watch history: {len(video_titles)}"
        )
        console.print(
            f"   • Titles found for playlist videos: {matched_titles}/{len(playlist.videos)}"
        )

        # Debug: Show a few sample video IDs from each source
        if len(video_titles) > 0:
            sample_watch_ids = list(video_titles.keys())[:3]
            console.print(f"   • Sample watch history IDs: {sample_watch_ids}")

        playlist_sample_ids = [v.video_id for v in playlist.videos[:3]]
        console.print(f"   • Sample playlist IDs: {playlist_sample_ids}")

        if matched_titles == 0 and total_watch_entries > 0:
            console.print(
                f"   💡 No matches found - playlist videos may not be in watch history"
            )

    # Show playlist insights
    timestamps = [v.creation_timestamp for v in playlist.videos if v.creation_timestamp]
    if timestamps:
        first_date = min(timestamps).strftime("%Y-%m-%d")
        last_date = max(timestamps).strftime("%Y-%m-%d")
        console.print(f"\n📅 Date range: {first_date} to {last_date}")

        # Show activity pattern
        from collections import Counter

        months = [dt.strftime("%Y-%m") for dt in timestamps]
        month_counts = Counter(months)
        top_months = month_counts.most_common(3)

        console.print(f"📊 Most active months:")
        for month, count in top_months:
            console.print(f"   • {month}: {count} videos added")


async def _peek_watch_history(
    takeout_service: TakeoutService,
    limit: Optional[int],
    sort_order: str,
    progress: Progress,
    task_id: Any,
    filter_name: Optional[str] = None,
) -> None:
    """Display watch history information."""
    try:
        # Parse watch history
        watch_history = await takeout_service.parse_watch_history()
        progress.update(task_id, description="📊 Analyzing watch history...")

        if not watch_history:
            console.print("📭 No watch history found")
            console.print(
                "💡 Make sure you selected JSON format when downloading Takeout"
            )
            return

        # Filter by channel name if specified
        if filter_name:
            original_count = len(watch_history)
            watch_history = [
                entry
                for entry in watch_history
                if entry.channel_name
                and filter_name.lower() in entry.channel_name.lower()
            ]
            if not watch_history:
                console.print(
                    f"📭 No watch history found for channel matching '{filter_name}'"
                )
                console.print(
                    f"💡 Found {original_count} total videos. Try a partial channel name."
                )
                return

        # Sort history based on sort_order
        if sort_order == "recent":
            # Use timezone-aware datetime for proper comparison
            from datetime import timezone

            watch_history.sort(
                key=lambda x: x.watched_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
        elif sort_order == "oldest":
            from datetime import timezone

            watch_history.sort(
                key=lambda x: x.watched_at or datetime.max.replace(tzinfo=timezone.utc),
                reverse=False,
            )

        # Create rich table
        table = Table(
            title=f"📺 Watch History ({len(watch_history)} videos)",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Video", style="cyan", width=60)
        table.add_column("Channel", style="green", width=35)
        table.add_column("Watched", style="yellow", width=20)

        for entry in watch_history[:limit]:
            watched_time = (
                entry.watched_at.strftime("%Y-%m-%d %H:%M")
                if entry.watched_at
                else "Unknown"
            )

            table.add_row(
                entry.title[:40] + "..." if len(entry.title) > 40 else entry.title,
                entry.channel_name or "Unknown",
                watched_time,
            )

        console.print(table)

        # Analysis insights
        channels: Dict[str, int] = {}
        for entry in watch_history:
            if entry.channel_name:
                channels[entry.channel_name] = channels.get(entry.channel_name, 0) + 1

        top_channels = sorted(channels.items(), key=lambda x: x[1], reverse=True)[:5]

        # Date range
        dates = [e.watched_at for e in watch_history if e.watched_at]
        if dates:
            date_range = f"{min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')}"
            total_days = (max(dates) - min(dates)).days
            avg_per_day = len(watch_history) / max(total_days, 1)
        else:
            date_range = "Unknown"
            avg_per_day = 0

        console.print(f"\n💡 Insights:")
        console.print(f"   • Date range: {date_range}")
        console.print(f"   • Average videos per day: {avg_per_day:.1f}")
        console.print(f"   • Unique channels: {len(channels)}")
        console.print(f"   • Top 5 channels:")
        for channel, count in top_channels:
            console.print(f"     - {channel}: {count} videos")

        if limit is not None and len(watch_history) > limit:
            console.print(
                f"   • Showing {limit} of {len(watch_history)} videos (use --limit to see more)"
            )

        if filter_name:
            console.print(f"\n🔍 Filter Results:")
            console.print(
                f"   • Found {len(watch_history)} videos from channels matching '{filter_name}'"
            )

    except Exception as e:
        console.print(f"❌ Error analyzing watch history: {e}")


async def _peek_subscriptions(
    takeout_service: TakeoutService,
    limit: Optional[int],
    progress: Progress,
    task_id: Any,
    filter_name: Optional[str] = None,
) -> None:
    """Display subscriptions information."""
    try:
        # Parse subscriptions
        subscriptions = await takeout_service.parse_subscriptions()
        progress.update(task_id, description="📊 Analyzing subscriptions...")

        if not subscriptions:
            console.print("📭 No subscriptions found in Takeout data")
            return

        # Filter by channel name if specified
        if filter_name:
            original_count = len(subscriptions)
            subscriptions = [
                sub
                for sub in subscriptions
                if filter_name.lower() in sub.channel_title.lower()
            ]
            if not subscriptions:
                console.print(f"📭 No subscriptions found matching '{filter_name}'")
                console.print(
                    f"💡 Found {original_count} total subscriptions. Try a partial name match."
                )
                return

        # Create rich table
        table = Table(
            title=f"📺 Channel Subscriptions ({len(subscriptions)} channels)",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Channel", style="cyan", width=45)
        table.add_column("Channel ID", style="green", width=30)
        table.add_column("Type", style="yellow", width=15)

        for sub in subscriptions[:limit]:
            # Determine URL type
            if sub.channel_id and sub.channel_id.startswith("UC"):
                url_type = "Direct"
            elif "/c/" in sub.channel_url:
                url_type = "Custom"
            else:
                url_type = "Unknown"

            # Truncate channel ID for display
            display_id = sub.channel_id or "N/A"
            if len(display_id) > 24:
                display_id = display_id[:21] + "..."

            table.add_row(sub.channel_title, display_id, url_type)

        console.print(table)

        # Analysis insights
        direct_ids = sum(1 for sub in subscriptions if sub.channel_id)
        custom_urls = len(subscriptions) - direct_ids

        console.print(f"\n💡 Insights:")
        console.print(f"   • Total subscriptions: {len(subscriptions)}")
        console.print(
            f"   • Channels with direct IDs: {direct_ids} ({direct_ids/len(subscriptions)*100:.1f}%)"
        )
        console.print(
            f"   • Channels with custom URLs: {custom_urls} ({custom_urls/len(subscriptions)*100:.1f}%)"
        )
        console.print(f"   • Custom URLs need API resolution to get channel IDs")

        if limit is not None and len(subscriptions) > limit:
            console.print(
                f"   • Showing {limit} of {len(subscriptions)} subscriptions (use --limit to see more)"
            )

        if filter_name:
            console.print(f"\n🔍 Filter Results:")
            console.print(
                f"   • Found {len(subscriptions)} subscriptions matching '{filter_name}'"
            )

    except Exception as e:
        console.print(f"❌ Error analyzing subscriptions: {e}")


async def _apply_topic_filters(
    analysis: Any, topic_filter: Optional[str], by_topic: bool
) -> None:
    """Apply topic filtering and grouping to analysis results."""
    try:
        # Validate topic filter if provided
        if topic_filter:
            async for session in db_manager.get_session():
                if not await topic_category_repository.exists(session, topic_filter):
                    console.print(
                        Panel(
                            f"[red]❌ Invalid topic ID: {topic_filter}[/red]\n"
                            "Use chronovista topics list to see available topics.",
                            title="Topic Filter Error",
                            border_style="red",
                        )
                    )
                    return

                # Get topic name for display
                topic_category = await topic_category_repository.get(
                    session, topic_filter
                )
                topic_name = (
                    topic_category.category_name
                    if topic_category
                    else f"Topic {topic_filter}"
                )

                console.print(
                    f"[blue]🔍 Filtering analysis by topic: {topic_name}[/blue]"
                )

        if by_topic:
            console.print(
                "[blue]🏷️ Grouping analysis results by topic categories[/blue]"
            )
            # Note: Full topic grouping would require analyzing video content in takeout data
            # This is a placeholder for the functionality - it would need integration with
            # video categorization logic to match takeout videos with their topics
            console.print(
                "[yellow]ℹ️ Topic grouping requires video-topic associations to be synced first[/yellow]"
            )
            console.print(
                "[dim]Use 'chronovista sync all' to create topic associations before grouping[/dim]"
            )

    except Exception as e:
        console.print(f"[yellow]⚠️ Error processing topic filters: {e}[/yellow]")


@takeout_app.command("analyze")
def analyze_comprehensive(
    takeout_path: Path = typer.Option(
        Path("takeout"), "--path", "-p", help="Path to Takeout directory"
    ),
    save_report: bool = typer.Option(
        False, "--save", "-s", help="Save detailed report to file"
    ),
    by_topic: bool = typer.Option(False, "--by-topic", help="Group analysis by topics"),
    topic_filter: Optional[str] = typer.Option(
        None, "--topic", help="Filter analysis by topic ID"
    ),
) -> None:
    """
    🔬 Generate comprehensive analysis of your Takeout data.

    Analyzes patterns, relationships, and identifies opportunities for API enrichment.

    Options:
    --by-topic: Group analysis results by video topic categories
    --topic: Filter analysis to show only content from a specific topic ID
    """
    import asyncio

    async def run_analysis() -> None:
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "🔬 Generating comprehensive analysis...", total=None
                )

                # Initialize and analyze
                takeout_service = TakeoutService(takeout_path)
                analysis = await takeout_service.generate_comprehensive_analysis()

                # Handle topic filtering and grouping
                if topic_filter or by_topic:
                    progress.update(task, description="🏷️ Processing topic filters...")
                    await _apply_topic_filters(analysis, topic_filter, by_topic)

                progress.update(task, description="📊 Preparing results...")

                # Display summary
                _display_analysis_summary(analysis)

                if save_report:
                    # Save detailed report
                    report_path = Path("takeout_analysis_report.json")
                    with open(report_path, "w") as f:
                        import json

                        json.dump(analysis.model_dump(), f, indent=2, default=str)
                    console.print(f"\n💾 Detailed report saved to: {report_path}")

        except Exception as e:
            console.print(f"❌ Analysis failed: {e}")
            raise typer.Exit(1)

    asyncio.run(run_analysis())


def _display_analysis_summary(analysis: Any) -> None:
    """Display comprehensive analysis summary."""
    # Main statistics panel
    stats_text = f"""
📊 Data Overview:
   • Videos Watched: {analysis.total_videos_watched:,}
   • Unique Channels: {analysis.unique_channels:,}  
   • Playlists: {analysis.playlist_count:,}
   • Subscriptions: {analysis.subscription_count:,}

🎯 Content Insights:
   • Content Diversity Score: {analysis.content_diversity_score:.2f}/1.0
   • Data Completeness: {analysis.data_completeness:.1%}
   • High Priority Videos for API: {len(analysis.high_priority_videos)}
    """

    console.print(
        Panel(
            stats_text.strip(), title="📈 Takeout Analysis Summary", border_style="blue"
        )
    )

    # Top channels table
    if analysis.top_channels:
        table = Table(
            title="🌟 Top Channels", show_header=True, header_style="bold green"
        )
        table.add_column("Channel", style="cyan", width=40)
        table.add_column("Videos", style="green", justify="right", width=10)
        table.add_column("Subscribed", style="yellow", justify="center", width=12)
        table.add_column("Engagement", style="blue", justify="right", width=12)

        for channel in analysis.top_channels[:10]:
            table.add_row(
                channel.channel_name,
                str(channel.videos_watched),
                "✅" if channel.is_subscribed else "❌",
                f"{channel.engagement_score:.2f}",
            )

        console.print(table)

    # Viewing patterns insights
    patterns = analysis.viewing_patterns
    console.print(f"\n🕐 Viewing Patterns:")
    # Format peak hours with counts and readable time format
    if patterns.peak_viewing_hours:
        formatted_hours = []
        for hour in patterns.peak_viewing_hours[:3]:  # Top 3 only
            if hour == 0:
                time_str = "12 AM"
            elif hour < 12:
                time_str = f"{hour} AM"
            elif hour == 12:
                time_str = "12 PM"
            else:
                time_str = f"{hour-12} PM"
            formatted_hours.append(time_str)
        console.print(f"   • Peak hours: {', '.join(formatted_hours)}")
    else:
        console.print(f"   • Peak hours: None")
    console.print(f"   • Peak days: {', '.join(patterns.peak_viewing_days)}")
    console.print(
        f"   • Viewing frequency: {patterns.viewing_frequency:.1f} videos/day"
    )

    # Channel diversity with explanation
    diversity_pct = patterns.channel_diversity * 100
    if diversity_pct >= 80:
        diversity_desc = "Very diverse - you explore many different creators"
    elif diversity_pct >= 60:
        diversity_desc = "Moderately diverse - you watch a good variety of channels"
    elif diversity_pct >= 40:
        diversity_desc = (
            "Somewhat focused - you have preferred channels but explore others"
        )
    else:
        diversity_desc = (
            "Highly focused - you mainly watch a small set of favorite channels"
        )
    console.print(
        f"   • Channel diversity: {patterns.channel_diversity:.2f}/1.0 ({diversity_desc})"
    )

    # Playlist usage with explanation
    usage_pct = patterns.playlist_usage * 100
    if usage_pct > 100:
        playlist_desc = f"Heavy organizer - you save {usage_pct:.0f} playlist videos per 100 watched (many videos in multiple playlists)"
    elif usage_pct >= 50:
        playlist_desc = f"Active organizer - you save {usage_pct:.0f}% of watched videos to playlists"
    elif usage_pct >= 20:
        playlist_desc = f"Selective organizer - you save {usage_pct:.0f}% of watched videos to playlists"
    else:
        playlist_desc = f"Minimal organizer - you rarely save videos to playlists ({usage_pct:.0f}%)"
    console.print(
        f"   • Playlist usage: {patterns.playlist_usage:.1%} ({playlist_desc})"
    )

    # Playlist insights
    playlist_analysis = analysis.playlist_analysis
    console.print(f"\n📁 Playlist Organization:")
    console.print(
        f"   • Orphaned videos (not in playlists): {len(playlist_analysis.orphaned_videos)}"
    )
    console.print(
        f"   • Over-categorized videos (3+ playlists): {len(playlist_analysis.over_categorized_videos)}"
    )

    # Content gaps
    if analysis.content_gaps:
        console.print(f"\n🎯 API Enrichment Opportunities:")
        console.print(f"   • Videos needing metadata: {len(analysis.content_gaps)}")
        console.print(
            f"   • High priority videos: {len(analysis.high_priority_videos)}"
        )

        # Show top gaps
        top_gaps = analysis.content_gaps[:5]
        for gap in top_gaps:
            console.print(
                f"     - {gap.title[:50]}... (priority: {gap.priority_score:.2f})"
            )


@takeout_app.command("relationships")
def analyze_relationships(
    takeout_path: Path = typer.Option(
        Path("takeout"), "--path", "-p", help="Path to Takeout directory"
    ),
    relationship_type: str = typer.Argument(
        "playlist-overlap",
        help="Type: playlist-overlap, channel-clusters, temporal-patterns",
    ),
) -> None:
    """
    🔗 Analyze relationships in your Takeout data.

    Discover patterns and connections between playlists, channels, and content.
    """
    import asyncio

    async def run_analysis() -> None:
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"🔗 Analyzing {relationship_type} relationships...", total=None
                )

                # Initialize TakeoutService
                takeout_service = TakeoutService(takeout_path)

                if relationship_type == "playlist-overlap":
                    await _analyze_playlist_overlap(takeout_service, progress, task)
                elif relationship_type == "channel-clusters":
                    await _analyze_channel_clusters(takeout_service, progress, task)
                elif relationship_type == "temporal-patterns":
                    await _analyze_temporal_patterns(takeout_service, progress, task)
                else:
                    console.print(f"❌ Unknown relationship type: {relationship_type}")
                    console.print(
                        "Available types: playlist-overlap, channel-clusters, temporal-patterns"
                    )
                    raise typer.Exit(1)

        except TakeoutParsingError as e:
            console.print(f"❌ Error parsing Takeout data: {e}")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"❌ Relationship analysis failed: {e}")
            raise typer.Exit(1)

    asyncio.run(run_analysis())


@takeout_app.command("inspect")
def inspect_file(
    file_path: Path = typer.Argument(
        ..., help="Path to specific takeout file (CSV or JSON)"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of items to show"),
) -> None:
    """
    🔍 Inspect a specific takeout file (playlist CSV, subscriptions CSV, etc.).

    Directly examine individual takeout files to see their contents.

    Examples:
        chronovista takeout inspect "takeout/YouTube and YouTube Music/playlists/My Playlist.csv"
        chronovista takeout inspect "takeout/YouTube and YouTube Music/subscriptions/subscriptions.csv"
        chronovista takeout inspect "takeout/YouTube and YouTube Music/history/watch-history.json" --limit=10
    """
    import asyncio

    async def run_inspect() -> None:
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"🔍 Inspecting {file_path.name}...", total=None
                )

                if not file_path.exists():
                    console.print(f"❌ File not found: {file_path}")
                    raise typer.Exit(1)

                if file_path.suffix.lower() == ".csv":
                    await _inspect_csv_file(file_path, limit, progress, task)
                elif file_path.suffix.lower() == ".json":
                    await _inspect_json_file(file_path, limit, progress, task)
                else:
                    console.print(f"❌ Unsupported file type: {file_path.suffix}")
                    console.print("Supported types: .csv, .json")
                    raise typer.Exit(1)

        except Exception as e:
            console.print(f"❌ Error inspecting file: {e}")
            raise typer.Exit(1)

    asyncio.run(run_inspect())


async def _inspect_csv_file(
    file_path: Path, limit: int, progress: Progress, task_id: Any
) -> None:
    """Inspect a CSV file and display its contents."""
    import csv

    progress.update(task_id, description="📊 Reading CSV file...")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames) if reader.fieldnames else None
            rows = list(reader)

        if not rows:
            console.print("📭 CSV file is empty")
            return

        # Determine what type of CSV this is based on headers and filename
        file_type = _detect_csv_type(file_path, headers)

        # Create appropriate table based on file type
        if file_type == "playlist":
            await _display_playlist_csv(file_path, headers, rows, limit)
        elif file_type == "subscriptions":
            await _display_subscriptions_csv(headers, rows, limit)
        else:
            await _display_generic_csv(headers, rows, limit)

    except Exception as e:
        console.print(f"❌ Error reading CSV file: {e}")


async def _inspect_json_file(
    file_path: Path, limit: int, progress: Progress, task_id: Any
) -> None:
    """Inspect a JSON file and display its contents."""
    import json

    progress.update(task_id, description="📊 Reading JSON file...")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data:
            console.print("📭 JSON file is empty")
            return

        if file_path.name == "watch-history.json":
            await _display_watch_history_json(data, limit)
        else:
            await _display_generic_json(data, limit)

    except json.JSONDecodeError as e:
        console.print(f"❌ Invalid JSON file: {e}")
    except Exception as e:
        console.print(f"❌ Error reading JSON file: {e}")


def _detect_csv_type(file_path: Path, headers: Optional[List[str]]) -> str:
    """Detect the type of CSV file based on path and headers."""
    if "playlists" in str(file_path):
        return "playlist"
    elif "subscriptions" in str(file_path):
        return "subscriptions"
    elif headers and "Video ID" in headers:
        return "playlist"
    elif headers and "Channel Title" in headers:
        return "subscriptions"
    else:
        return "generic"


async def _display_playlist_csv(
    file_path: Path,
    headers: Optional[List[str]],
    rows: List[Dict[str, str]],
    limit: int,
) -> None:
    """Display playlist CSV contents."""
    playlist_name = file_path.stem

    table = Table(
        title=f"🎵 Playlist: {playlist_name} ({len(rows)} videos)",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Video ID", style="cyan", width=15)
    table.add_column("Added", style="yellow", width=20)

    for row in rows[:limit]:
        video_id = row.get("Video ID", "")
        timestamp = row.get("Playlist Video Creation Timestamp", "")

        # Format timestamp if available
        if timestamp:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                formatted_time = dt.strftime("%Y-%m-%d %H:%M")
            except:
                formatted_time = timestamp
        else:
            formatted_time = "Unknown"

        table.add_row(video_id, formatted_time)

    console.print(table)

    if len(rows) > limit:
        console.print(
            f"\n💡 Showing {limit} of {len(rows)} videos (use --limit to see more)"
        )

    # Show some insights
    if rows:
        timestamps = [
            row.get("Playlist Video Creation Timestamp", "")
            for row in rows
            if row.get("Playlist Video Creation Timestamp")
        ]
        if timestamps:
            try:
                from datetime import datetime

                dates = []
                for ts in timestamps:
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        dates.append(dt)
                    except:
                        continue

                if dates:
                    first_date = min(dates).strftime("%Y-%m-%d")
                    last_date = max(dates).strftime("%Y-%m-%d")
                    console.print(
                        f"\n📅 Playlist date range: {first_date} to {last_date}"
                    )
            except:
                pass


async def _display_subscriptions_csv(
    headers: Optional[List[str]], rows: List[Dict[str, str]], limit: int
) -> None:
    """Display subscriptions CSV contents."""
    table = Table(
        title=f"📺 Subscriptions ({len(rows)} channels)",
        show_header=True,
        header_style="bold green",
    )
    table.add_column("Channel", style="cyan", width=50)
    table.add_column("URL", style="blue", width=60)

    for row in rows[:limit]:
        channel_title = row.get("Channel Title", "")
        channel_url = row.get("Channel Url", "")

        table.add_row(
            channel_title,
            channel_url[:37] + "..." if len(channel_url) > 40 else channel_url,
        )

    console.print(table)

    if len(rows) > limit:
        console.print(
            f"\n💡 Showing {limit} of {len(rows)} subscriptions (use --limit to see more)"
        )


async def _display_generic_csv(
    headers: Optional[List[str]], rows: List[Dict[str, str]], limit: int
) -> None:
    """Display generic CSV contents."""
    table = Table(
        title=f"📄 CSV File ({len(rows)} rows)",
        show_header=True,
        header_style="bold blue",
    )

    # Add columns for headers
    if headers:
        for header in headers[:5]:  # Limit to first 5 columns for readability
            table.add_column(header, style="cyan", width=25)

        for row in rows[:limit]:
            row_data = [
                (
                    str(row.get(header, ""))[:30] + "..."
                    if len(str(row.get(header, ""))) > 30
                    else str(row.get(header, ""))
                )
                for header in headers[:5]
            ]
            table.add_row(*row_data)

    console.print(table)

    if len(rows) > limit:
        console.print(
            f"\n💡 Showing {limit} of {len(rows)} rows (use --limit to see more)"
        )

    console.print(f"\n📊 File info:")
    if headers:
        console.print(f"   • Headers: {', '.join(headers)}")
    else:
        console.print("   • No headers found")


async def _display_watch_history_json(data: List[Dict[str, Any]], limit: int) -> None:
    """Display watch history JSON contents."""
    youtube_entries = [entry for entry in data if entry.get("header") == "YouTube"]

    table = Table(
        title=f"📺 Watch History ({len(youtube_entries)} videos)",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Video", style="cyan", width=60)
    table.add_column("Channel", style="green", width=35)
    table.add_column("Time", style="yellow", width=20)

    for entry in youtube_entries[:limit]:
        title = entry.get("title", "")
        if title.startswith("Watched "):
            title = title[8:]  # Remove "Watched " prefix

        channel_name = ""
        if entry.get("subtitles"):
            channel_name = entry["subtitles"][0].get("name", "")

        time_str = entry.get("time", "")

        table.add_row(
            title[:37] + "..." if len(title) > 40 else title,
            channel_name[:22] + "..." if len(channel_name) > 25 else channel_name,
            time_str,
        )

    console.print(table)

    if len(youtube_entries) > limit:
        console.print(
            f"\n💡 Showing {limit} of {len(youtube_entries)} videos (use --limit to see more)"
        )


async def _display_generic_json(data: Any, limit: int) -> None:
    """Display generic JSON contents."""
    if isinstance(data, list):
        console.print(f"📄 JSON Array ({len(data)} items)")

        if data and isinstance(data[0], dict):
            # Show sample of dictionary keys
            sample_keys = list(data[0].keys())[:5]
            console.print(f"📊 Sample keys: {', '.join(sample_keys)}")

        # Show first few items
        for i, item in enumerate(data[:limit]):
            console.print(f"\n[bold]Item {i+1}:[/bold]")
            if isinstance(item, dict):
                for key, value in list(item.items())[:3]:
                    value_str = (
                        str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                    )
                    console.print(f"  {key}: {value_str}")
            else:
                console.print(f"  {str(item)[:100]}...")

    elif isinstance(data, dict):
        console.print("📄 JSON Object")
        console.print(f"📊 Keys: {', '.join(list(data.keys())[:10])}")

        for key, value in list(data.items())[:limit]:
            value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
            console.print(f"  {key}: {value_str}")

    else:
        console.print(f"📄 JSON Value: {str(data)[:200]}")


# Import required for datetime operations
from datetime import datetime


async def _analyze_playlist_overlap(
    takeout_service: TakeoutService, progress: Progress, task_id: Any
) -> None:
    """Analyze and display playlist overlap relationships."""
    progress.update(task_id, description="🔗 Calculating playlist overlaps...")

    overlap_matrix = await takeout_service.analyze_playlist_overlap()

    if not overlap_matrix:
        console.print(
            "📭 No playlist overlaps found (no playlists or all playlists are unique)"
        )
        return

    # Create overlap table
    table = Table(
        title="🔗 Playlist Overlap Analysis",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Playlist 1", style="cyan", width=40)
    table.add_column("Playlist 2", style="green", width=40)
    table.add_column("Shared Videos", style="yellow", justify="right", width=15)
    table.add_column("Relationship", style="blue", width=20)

    # Sort overlaps by count (highest first)
    all_overlaps = []
    for playlist1, overlaps in overlap_matrix.items():
        for playlist2, count in overlaps.items():
            all_overlaps.append((playlist1, playlist2, count))

    all_overlaps.sort(key=lambda x: x[2], reverse=True)

    for playlist1, playlist2, count in all_overlaps[:20]:  # Show top 20
        # Determine relationship strength
        if count >= 10:
            relationship = "Strong 💪"
        elif count >= 5:
            relationship = "Moderate 👍"
        else:
            relationship = "Weak 🤝"

        table.add_row(
            playlist1[:20] + "..." if len(playlist1) > 20 else playlist1,
            playlist2[:20] + "..." if len(playlist2) > 20 else playlist2,
            str(count),
            relationship,
        )

    console.print(table)

    # Summary insights
    total_overlaps = len(all_overlaps)
    strong_overlaps = sum(1 for _, _, count in all_overlaps if count >= 10)

    console.print(f"\n💡 Overlap Insights:")
    console.print(f"   • Total playlist pairs with overlaps: {total_overlaps}")
    console.print(f"   • Strong relationships (10+ shared videos): {strong_overlaps}")
    console.print(
        f"   • Most overlapped pair: {all_overlaps[0][0]} ↔ {all_overlaps[0][1]} ({all_overlaps[0][2]} videos)"
    )


async def _analyze_channel_clusters(
    takeout_service: TakeoutService, progress: Progress, task_id: Any
) -> None:
    """Analyze and display channel clusters."""
    progress.update(task_id, description="📊 Clustering channels by engagement...")

    clusters = await takeout_service.analyze_channel_clusters()

    # Display high engagement channels
    if clusters["high_engagement"]:
        table = Table(
            title="🌟 High Engagement Channels",
            show_header=True,
            header_style="bold green",
        )
        table.add_column("Channel", style="cyan", width=45)
        table.add_column("Videos", style="green", justify="right", width=10)
        table.add_column("Frequency", style="yellow", justify="right", width=12)
        table.add_column("Subscribed", style="blue", justify="center", width=12)

        for channel, data in sorted(
            clusters["high_engagement"].items(),
            key=lambda x: x[1]["videos_watched"],
            reverse=True,
        )[:15]:
            table.add_row(
                channel[:25] + "..." if len(channel) > 25 else channel,
                str(data["videos_watched"]),
                f"{data['avg_frequency']:.1f}/month",
                "✅" if data["is_subscribed"] else "❌",
            )

        console.print(table)

    # Display subscription recommendations
    if clusters["unsubscribed_frequent"]:
        console.print(
            f"\n🎯 Subscription Recommendations ({len(clusters['unsubscribed_frequent'])} channels):"
        )
        for channel, data in sorted(
            clusters["unsubscribed_frequent"].items(),
            key=lambda x: x[1]["videos_watched"],
            reverse=True,
        )[:10]:
            console.print(
                f"   • {channel}: {data['videos_watched']} videos watched (not subscribed)"
            )

    # Display inactive subscriptions
    if clusters["subscribed_inactive"]:
        console.print(
            f"\n🧹 Inactive Subscriptions ({len(clusters['subscribed_inactive'])} channels):"
        )
        inactive_count = 0
        for channel, data in clusters["subscribed_inactive"].items():
            if inactive_count < 10:
                console.print(f"   • {channel}: No videos watched recently")
                inactive_count += 1
        if len(clusters["subscribed_inactive"]) > 10:
            console.print(
                f"   • ... and {len(clusters['subscribed_inactive']) - 10} more"
            )

    # Summary statistics
    total_channels = (
        len(clusters["high_engagement"])
        + len(clusters["medium_engagement"])
        + len(clusters["low_engagement"])
    )

    console.print(f"\n📊 Channel Engagement Summary:")
    console.print(f"   • High engagement: {len(clusters['high_engagement'])} channels")
    console.print(
        f"   • Medium engagement: {len(clusters['medium_engagement'])} channels"
    )
    console.print(f"   • Low engagement: {len(clusters['low_engagement'])} channels")
    console.print(
        f"   • Unsubscribed frequent: {len(clusters['unsubscribed_frequent'])} channels"
    )
    console.print(
        f"   • Inactive subscriptions: {len(clusters['subscribed_inactive'])} channels"
    )


async def _analyze_temporal_patterns(
    takeout_service: TakeoutService, progress: Progress, task_id: Any
) -> None:
    """Analyze and display temporal viewing patterns."""
    progress.update(task_id, description="⏰ Analyzing viewing time patterns...")

    patterns = await takeout_service.analyze_temporal_patterns()

    if "error" in patterns:
        console.print(f"❌ {patterns['error']}")
        return

    # Display peak times
    console.print(
        Panel(
            f"""
⏰ Peak Viewing Patterns:
   • Peak Hour: {patterns['peak_viewing_hour']}:00
   • Peak Day: {patterns['peak_viewing_day']}
   • Peak Month: {patterns['peak_viewing_month']}
   
📅 Activity Summary:
   • Total Active Days: {patterns['total_active_days']}
   • Longest Streak: {patterns['max_consecutive_days']} consecutive days
   • Date Range: {patterns['date_range']['duration_days']} days
    """.strip(),
            title="⏰ Temporal Analysis",
            border_style="blue",
        )
    )

    # Hourly distribution table
    if patterns["hourly_distribution"]:
        table = Table(
            title="🕐 Hourly Viewing Distribution",
            show_header=True,
            header_style="bold yellow",
        )
        table.add_column("Hour", style="cyan", justify="center", width=8)
        table.add_column("Videos", style="green", justify="right", width=10)
        table.add_column("Percentage", style="yellow", justify="right", width=12)
        table.add_column("Activity Level", style="blue", width=15)

        total_videos = sum(patterns["hourly_distribution"].values())

        # Show top 12 hours
        sorted_hours = sorted(
            patterns["hourly_distribution"].items(), key=lambda x: x[1], reverse=True
        )[:12]

        for hour, count in sorted_hours:
            percentage = (count / total_videos) * 100

            if percentage >= 8:
                activity = "Very High 🔥"
            elif percentage >= 5:
                activity = "High 📈"
            elif percentage >= 3:
                activity = "Medium 📊"
            else:
                activity = "Low 📉"

            table.add_row(f"{hour:02d}:00", str(count), f"{percentage:.1f}%", activity)

        console.print(table)

    # Daily distribution
    if patterns["daily_distribution"]:
        console.print(f"\n📅 Weekly Pattern:")
        days_order = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        total_videos = sum(patterns["daily_distribution"].values())

        for day in days_order:
            count = patterns["daily_distribution"].get(day, 0)
            percentage = (count / total_videos) * 100 if total_videos > 0 else 0
            bar = "█" * int(percentage / 2)  # Visual bar
            console.print(f"   • {day:9}: {count:4} videos {bar:15} {percentage:5.1f}%")

    # Top channel time preferences
    if patterns["channel_time_preferences"]:
        console.print(f"\n🎯 Channel Time Preferences (Top 5):")

        # Find channels with clear time preferences
        channel_preferences = []
        for channel, time_dist in patterns["channel_time_preferences"].items():
            if sum(time_dist.values()) >= 5:  # At least 5 videos
                peak_hour = max(time_dist.items(), key=lambda x: x[1])
                total_channel_videos = sum(time_dist.values())
                peak_percentage = (peak_hour[1] / total_channel_videos) * 100

                if peak_percentage >= 30:  # Strong time preference
                    channel_preferences.append(
                        (channel, peak_hour[0], peak_percentage, total_channel_videos)
                    )

        # Sort by preference strength
        channel_preferences.sort(key=lambda x: x[2], reverse=True)

        for channel, hour, percentage, total in channel_preferences[:5]:
            console.print(
                f"   • {channel[:30]:30}: {hour:02d}:00 ({percentage:.0f}% of {total} videos)"
            )

    console.print(
        f"\n💡 Tip: Use this data to optimize your content discovery and subscription timing!"
    )


async def _peek_comments(
    takeout_service: TakeoutService,
    limit: Optional[int],
    sort_order: str,
    progress: Progress,
    task_id: Any,
    filter_name: Optional[str] = None,
) -> None:
    """Display comments information."""
    import csv
    import json
    from datetime import datetime

    try:
        progress.update(task_id, description="📊 Loading comments data...")

        # Find comments files
        comments_dir = takeout_service.youtube_path / "comments"
        if not comments_dir.exists():
            console.print("📭 No comments found in Takeout data")
            return

        # Parse all comment CSV files
        comments = []
        comment_files = list(comments_dir.glob("*.csv"))

        for comment_file in comment_files:
            with open(comment_file, "r", encoding="utf-8") as f:
                # Try different CSV parsing approaches
                content = f.read()
                f.seek(0)
                reader = csv.DictReader(f, quoting=csv.QUOTE_ALL)
                for row in reader:
                    # Parse comment data
                    raw_comment_text = row.get("Comment Text", "")

                    comment_data = {
                        "comment_id": row.get("Comment ID", ""),
                        "video_id": row.get("Video ID", ""),
                        "channel_id": row.get("Channel ID", ""),
                        "timestamp_str": row.get("Comment Create Timestamp", ""),
                        "comment_text": raw_comment_text,
                        "timestamp": None,
                    }

                    # Parse timestamp
                    if comment_data["timestamp_str"]:
                        try:
                            comment_data["timestamp"] = datetime.fromisoformat(
                                comment_data["timestamp_str"].replace("Z", "+00:00")
                            )
                        except:
                            pass

                    # Parse comment text (it's in JSON format)
                    if comment_data["comment_text"]:
                        clean_text = comment_data["comment_text"]

                        # Try to parse JSON - handle array format like [{"text":"..."},{"text":"..."}]
                        if clean_text.startswith("[") or clean_text.startswith("{"):
                            try:
                                # If it looks like comma-separated JSON objects without brackets, wrap it
                                if (
                                    clean_text.startswith('{"text":')
                                    and '},{"text":' in clean_text
                                ):
                                    clean_text = f"[{clean_text}]"

                                # Parse as JSON array or object
                                text_json = json.loads(clean_text)

                                if isinstance(text_json, list):
                                    # Array of text objects - concatenate all text fields
                                    text_parts = []
                                    for item in text_json:
                                        if isinstance(item, dict) and "text" in item:
                                            text_content = item["text"]
                                            # Don't strip here - preserve spacing and structure
                                            # Skip only completely empty strings
                                            if text_content is not None:
                                                text_parts.append(text_content)

                                    if text_parts:
                                        # Join directly to preserve YouTube time references like @9:20
                                        clean_text = "".join(text_parts)
                                        # Clean up only excessive whitespace, but preserve intentional spacing
                                        clean_text = " ".join(clean_text.split())
                                    else:
                                        # If no text parts, use first available text
                                        for item in text_json:
                                            if (
                                                isinstance(item, dict)
                                                and "text" in item
                                            ):
                                                clean_text = item["text"]
                                                break

                                elif (
                                    isinstance(text_json, dict) and "text" in text_json
                                ):
                                    # Single text object
                                    clean_text = text_json["text"]

                            except json.JSONDecodeError:
                                # JSON parsing failed, keep original
                                pass
                            except Exception:
                                # Any other parsing errors, keep original
                                pass

                        comment_data["clean_text"] = clean_text.strip()
                    else:
                        comment_data["clean_text"] = ""

                    comments.append(comment_data)

        if not comments:
            console.print("📭 No comments found in CSV files")
            return

        progress.update(task_id, description="📊 Analyzing comments...")

        # Filter by video ID or text content if specified
        if filter_name:
            original_count = len(comments)
            comments = [
                c
                for c in comments
                if (filter_name.lower() in (c["clean_text"] or "").lower())
                or (c["video_id"] and filter_name.lower() in c["video_id"].lower())
            ]
            if not comments:
                console.print(f"📭 No comments found matching '{filter_name}'")
                console.print(
                    f"💡 Found {original_count} total comments. Try a different search term."
                )
                return

        # Sort comments based on sort_order
        if sort_order == "recent":
            comments.sort(key=lambda x: x["timestamp"] or datetime.min, reverse=True)
        elif sort_order == "oldest":
            comments.sort(key=lambda x: x["timestamp"] or datetime.max, reverse=False)

        # Get video titles from watch history for lookup
        progress.update(task_id, description="🔍 Loading video titles...")
        video_titles = await _build_video_title_lookup(takeout_service)

        # Create rich table
        table = Table(
            title=f"💬 Your Comments ({len(comments)} total)",
            show_header=True,
            header_style="bold blue",
        )
        table.add_column("Comment", style="cyan", width=50)
        table.add_column("Video ID", style="blue", width=15)
        table.add_column("Video Title", style="green", width=40)
        table.add_column("Posted", style="yellow", width=15)

        # Apply limit for display
        display_comments = comments if limit is None else comments[:limit]

        for comment in display_comments:
            # Clean up comment text for display
            comment_text = comment["clean_text"]

            # Filter out problematic comments that are just symbols or very short
            if not comment_text or comment_text.strip() in ["\\", "@", "", "\n", '""']:
                comment_text = "[Comment text unavailable]"
            elif len(comment_text.strip()) <= 2 and comment_text.strip() in [
                "@",
                "\\",
                "&",
                "#",
            ]:
                comment_text = "[Comment text unavailable]"

            # Truncate comment text for display
            if len(comment_text) > 27:
                comment_text = comment_text[:27] + "..."

            # Get video ID and title
            video_id_display = (
                comment["video_id"][:11] + "..."
                if comment["video_id"] and len(comment["video_id"]) > 11
                else (comment["video_id"] or "N/A")
            )

            video_title_display = "Title not found"
            if comment["video_id"]:
                video_title = video_titles.get(comment["video_id"])
                if video_title:
                    video_title_display = (
                        video_title[:22] + "..."
                        if len(video_title) > 22
                        else video_title
                    )

            # Format timestamp
            if comment["timestamp"] and hasattr(comment["timestamp"], "strftime"):
                posted_time = comment["timestamp"].strftime("%Y-%m-%d %H:%M")
            else:
                posted_time = "Unknown"

            table.add_row(
                comment_text, video_id_display, video_title_display, posted_time
            )

        console.print(table)

        # Show insights
        if comments:
            # Date range
            dates = [
                c["timestamp"]
                for c in comments
                if c["timestamp"] and hasattr(c["timestamp"], "strftime")
            ]
            if dates:
                date_range = f"{min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')}"
                max_date = max(dates)
                min_date = min(dates)
                if isinstance(max_date, datetime) and isinstance(min_date, datetime):
                    total_days = (max_date - min_date).days or 1
                else:
                    total_days = 1
                avg_per_day = len(comments) / total_days
            else:
                date_range = "Unknown"
                avg_per_day = 0

            # Video distribution
            video_counts: Dict[str, int] = {}
            for comment in comments:
                if comment["video_id"]:
                    video_counts[comment["video_id"]] = (
                        video_counts.get(comment["video_id"], 0) + 1
                    )

            most_commented_video = (
                max(video_counts.items(), key=lambda x: x[1]) if video_counts else None
            )

            console.print(f"\n💡 Comments Insights:")
            console.print(f"   • Date range: {date_range}")
            console.print(f"   • Average comments per day: {avg_per_day:.1f}")
            console.print(f"   • Videos commented on: {len(video_counts)}")
            if most_commented_video:
                console.print(
                    f"   • Most commented video: {most_commented_video[0]} ({most_commented_video[1]} comments)"
                )

            # Show title lookup stats
            if video_titles:
                comment_video_ids = {c["video_id"] for c in comments if c["video_id"]}
                titles_found = len(
                    comment_video_ids.intersection(set(video_titles.keys()))
                )
                if comment_video_ids:
                    console.print(
                        f"   • Video titles found: {titles_found}/{len(comment_video_ids)} ({titles_found/len(comment_video_ids)*100:.1f}%)"
                    )

            if limit is not None and len(comments) > limit:
                console.print(
                    f"   • Showing {limit} of {len(comments)} comments (use --all to see all, or --limit N for more)"
                )
            elif limit is None:
                console.print(f"   • Showing all {len(comments)} comments")

            if filter_name:
                console.print(f"\n🔍 Filter Results:")
                console.print(
                    f"   • Found {len(comments)} comments matching '{filter_name}'"
                )

    except Exception as e:
        console.print(f"❌ Error analyzing comments: {e}")


async def _peek_live_chats(
    takeout_service: TakeoutService,
    limit: Optional[int],
    sort_order: str,
    progress: Progress,
    task_id: Any,
    filter_name: Optional[str] = None,
) -> None:
    """Display live chats information."""
    import csv
    import json
    from datetime import datetime

    try:
        progress.update(task_id, description="📊 Loading live chats data...")

        # Find live chats files
        chats_dir = takeout_service.youtube_path / "live chats"
        if not chats_dir.exists():
            console.print("📭 No live chats found in Takeout data")
            return

        # Parse all live chat CSV files
        chats = []
        chat_files = list(chats_dir.glob("*.csv"))

        for chat_file in chat_files:
            with open(chat_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, quoting=csv.QUOTE_ALL)
                for row in reader:
                    # Parse live chat data
                    raw_chat_text = row.get("Live Chat Text", "")

                    chat_data = {
                        "chat_id": row.get("Live Chat ID", ""),
                        "video_id": row.get("Video ID", ""),
                        "channel_id": row.get("Channel ID", ""),
                        "timestamp_str": row.get("Live Chat Create Timestamp", ""),
                        "chat_text": raw_chat_text,
                        "timestamp": None,
                    }

                    # Parse timestamp
                    if chat_data["timestamp_str"]:
                        try:
                            chat_data["timestamp"] = datetime.fromisoformat(
                                chat_data["timestamp_str"].replace("Z", "+00:00")
                            )
                        except:
                            pass

                    # Parse chat text (it's in JSON format like comments)
                    if chat_data["chat_text"]:
                        clean_text = chat_data["chat_text"]

                        # Try to parse JSON - handle array format like [{"text":"..."},{"text":"..."}]
                        if clean_text.startswith("[") or clean_text.startswith("{"):
                            try:
                                # If it looks like comma-separated JSON objects without brackets, wrap it
                                if (
                                    clean_text.startswith('{"text":')
                                    and '},{"text":' in clean_text
                                ):
                                    clean_text = f"[{clean_text}]"

                                # Parse as JSON array or object
                                text_json = json.loads(clean_text)

                                if isinstance(text_json, list):
                                    # Array of text objects - concatenate all text fields
                                    text_parts = []
                                    for item in text_json:
                                        if isinstance(item, dict) and "text" in item:
                                            text_content = item["text"]
                                            # Don't strip here - preserve spacing and structure
                                            # Skip only completely empty strings
                                            if text_content is not None:
                                                text_parts.append(text_content)

                                    if text_parts:
                                        # Join directly to preserve structure
                                        clean_text = "".join(text_parts)
                                        # Clean up only excessive whitespace, but preserve intentional spacing
                                        clean_text = " ".join(clean_text.split())
                                    else:
                                        # If no text parts, use first available text
                                        for item in text_json:
                                            if (
                                                isinstance(item, dict)
                                                and "text" in item
                                            ):
                                                clean_text = item["text"]
                                                break

                                elif (
                                    isinstance(text_json, dict) and "text" in text_json
                                ):
                                    # Single text object
                                    clean_text = text_json["text"]

                            except json.JSONDecodeError:
                                # JSON parsing failed, keep original
                                pass
                            except Exception:
                                # Any other parsing errors, keep original
                                pass

                        chat_data["clean_text"] = clean_text.strip()
                    else:
                        chat_data["clean_text"] = ""

                    chats.append(chat_data)

        if not chats:
            console.print("📭 No live chats found in CSV files")
            return

        progress.update(task_id, description="📊 Analyzing live chats...")

        # Filter by video ID or text content if specified
        if filter_name:
            original_count = len(chats)
            chats = [
                c
                for c in chats
                if (filter_name.lower() in (c["clean_text"] or "").lower())
                or (c["video_id"] and filter_name.lower() in c["video_id"].lower())
            ]
            if not chats:
                console.print(f"📭 No live chats found matching '{filter_name}'")
                console.print(
                    f"💡 Found {original_count} total chats. Try a different search term."
                )
                return

        # Sort chats based on sort_order
        if sort_order == "recent":
            chats.sort(key=lambda x: x["timestamp"] or datetime.min, reverse=True)
        elif sort_order == "oldest":
            chats.sort(key=lambda x: x["timestamp"] or datetime.max, reverse=False)

        # Get video titles from watch history for lookup
        progress.update(task_id, description="🔍 Loading video titles...")
        video_titles = await _build_video_title_lookup(takeout_service)

        # Create rich table
        table = Table(
            title=f"💬 Your Live Chats ({len(chats)} total)",
            show_header=True,
            header_style="bold blue",
        )
        table.add_column("Chat Message", style="cyan", width=50)
        table.add_column("Video ID", style="blue", width=15)
        table.add_column("Video Title", style="green", width=40)
        table.add_column("Posted", style="yellow", width=15)

        # Apply limit for display
        display_chats = chats if limit is None else chats[:limit]

        for chat in display_chats:
            # Clean up chat text for display
            chat_text = chat["clean_text"]

            # Filter out problematic chats that are just symbols or very short
            if not chat_text or chat_text.strip() in ["\\", "@", "", "\n", '""']:
                chat_text = "[Chat text unavailable]"
            elif len(chat_text.strip()) <= 2 and chat_text.strip() in [
                "@",
                "\\",
                "&",
                "#",
            ]:
                chat_text = "[Chat text unavailable]"

            # Truncate chat text for display
            if len(chat_text) > 27:
                chat_text = chat_text[:27] + "..."

            # Get video ID and title
            video_id_display = (
                chat["video_id"][:11] + "..."
                if chat["video_id"] and len(chat["video_id"]) > 11
                else (chat["video_id"] or "N/A")
            )

            video_title_display = "Title not found"
            if chat["video_id"]:
                video_title = video_titles.get(chat["video_id"])
                if video_title:
                    video_title_display = (
                        video_title[:22] + "..."
                        if len(video_title) > 22
                        else video_title
                    )

            # Format timestamp
            if chat["timestamp"] and hasattr(chat["timestamp"], "strftime"):
                posted_time = chat["timestamp"].strftime("%Y-%m-%d %H:%M")
            else:
                posted_time = "Unknown"

            table.add_row(chat_text, video_id_display, video_title_display, posted_time)

        console.print(table)

        # Show insights if we have timestamps
        timestamps = [
            chat["timestamp"]
            for chat in chats
            if chat["timestamp"] and hasattr(chat["timestamp"], "strftime")
        ]
        if timestamps:
            first_date = min(timestamps).strftime("%Y-%m-%d")
            last_date = max(timestamps).strftime("%Y-%m-%d")
            date_range = f"{first_date} to {last_date}"
            max_timestamp = max(timestamps)
            min_timestamp = min(timestamps)
            if isinstance(max_timestamp, datetime) and isinstance(
                min_timestamp, datetime
            ):
                total_days = (max_timestamp - min_timestamp).days or 1
            else:
                total_days = 1
            avg_per_day = len(chats) / total_days
        else:
            date_range = "Unknown"
            avg_per_day = 0

        # Count unique videos
        video_counts: Dict[str, int] = {}
        for chat in chats:
            if chat["video_id"]:
                video_counts[chat["video_id"]] = (
                    video_counts.get(chat["video_id"], 0) + 1
                )

        most_chatted_video = (
            max(video_counts.items(), key=lambda x: x[1]) if video_counts else None
        )

        console.print(f"\n💡 Live Chats Insights:")
        console.print(f"   • Date range: {date_range}")
        console.print(f"   • Average chats per day: {avg_per_day:.1f}")
        console.print(f"   • Videos with live chats: {len(video_counts)}")
        if most_chatted_video:
            console.print(
                f"   • Most active chat video: {most_chatted_video[0]} ({most_chatted_video[1]} messages)"
            )

        # Show title lookup stats
        if video_titles:
            chat_video_ids = {c["video_id"] for c in chats if c["video_id"]}
            titles_found = len(chat_video_ids.intersection(set(video_titles.keys())))
            if chat_video_ids:
                console.print(
                    f"   • Video titles found: {titles_found}/{len(chat_video_ids)} ({titles_found/len(chat_video_ids)*100:.1f}%)"
                )

        if limit is not None and len(chats) > limit:
            console.print(
                f"   • Showing {limit} of {len(chats)} chats (use --all to see all, or --limit N for more)"
            )
        elif limit is None:
            console.print(f"   • Showing all {len(chats)} chats")

        if filter_name:
            console.print(f"\n🔍 Filter Results:")
            console.print(f"   • Found {len(chats)} chats matching '{filter_name}'")

    except Exception as e:
        console.print(f"❌ Error analyzing live chats: {e}")


@takeout_app.command("seed")
def seed_database(
    takeout_path: Path = typer.Argument(
        Path("takeout"), help="Path to extracted Google Takeout directory"
    ),
    incremental: bool = typer.Option(
        False, "--incremental", "-i", help="Incremental seeding (safe to re-run)"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Show what would be seeded without making changes",
    ),
    progress: bool = typer.Option(
        True,
        "--progress/--no-progress",
        help="Show progress tracking (default: enabled)",
    ),
    only: Optional[str] = typer.Option(
        None,
        "--only",
        help="Seed only specific data types (comma-separated): channels,videos,playlists,user_videos,playlist_memberships",
    ),
    skip: Optional[str] = typer.Option(
        None,
        "--skip",
        help="Skip specific data types (comma-separated): channels,videos,playlists,user_videos,playlist_memberships",
    ),
    user_id: str = typer.Option(
        "takeout_user", "--user-id", "-u", help="User ID for seeding user-specific data"
    ),
    batch_size: int = typer.Option(
        100, "--batch-size", "-b", help="Batch size for processing (default: 100)"
    ),
) -> None:
    """
    🌱 Seed database with Google Takeout data.

    Transform and load your Takeout data into the chronovista database.
    Handles foreign key dependencies and provides safe incremental updates.

    Examples:
        chronovista takeout seed                                    # uses ./takeout
        chronovista takeout seed ~/Downloads/takeout-20240101       # specific path
        chronovista takeout seed ./my-google-takeout --incremental  # incremental mode
        chronovista takeout seed --dry-run                          # preview only
        chronovista takeout seed --only channels,videos             # selective seeding
        chronovista takeout seed --skip playlists                   # exclude playlists
    """
    import asyncio

    async def run_seeding() -> None:
        try:
            # Validate takeout path
            if not takeout_path.exists():
                console.print(f"❌ Takeout path not found: {takeout_path}")
                console.print("💡 Make sure you've extracted the Takeout archive")
                raise typer.Exit(1)

            # Parse data type filters
            only_types = set()
            skip_types = set()

            # Get valid types dynamically from the seeding service
            temp_seeding_service = TakeoutSeedingService(user_id=user_id)
            valid_types = temp_seeding_service.get_available_types()

            if only:
                only_types = set(t.strip() for t in only.split(","))
                invalid = only_types - valid_types
                if invalid:
                    console.print(f"❌ Invalid data types in --only: {invalid}")
                    console.print(f"Valid types: {', '.join(sorted(valid_types))}")
                    raise typer.Exit(1)

            if skip:
                skip_types = set(t.strip() for t in skip.split(","))
                invalid = skip_types - valid_types
                if invalid:
                    console.print(f"❌ Invalid data types in --skip: {invalid}")
                    console.print(f"Valid types: {', '.join(sorted(valid_types))}")
                    raise typer.Exit(1)

            # Check for conflicting filters
            if only_types and skip_types:
                conflicts = only_types & skip_types
                if conflicts:
                    console.print(f"❌ Cannot both include and skip: {conflicts}")
                    raise typer.Exit(1)

            # Initialize services first to get progress totals
            takeout_service = TakeoutService(takeout_path)
            console.print("📊 Loading Takeout data...")
            takeout_data = await takeout_service.parse_all()

            if dry_run:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress_tracker:
                    task = progress_tracker.add_task(
                        "📋 Preparing preview...", total=None
                    )
                    await _show_seeding_preview(
                        takeout_data, only_types, skip_types, progress_tracker, task
                    )
                return

            # Initialize modular seeding service
            seeding_service = TakeoutSeedingService(user_id=user_id)

            # Determine which data types to process
            available_types = seeding_service.get_available_types()
            if only_types:
                types_to_process = only_types & available_types
            else:
                types_to_process = available_types
            if skip_types:
                types_to_process = types_to_process - skip_types

            # Calculate totals for proper progress bars
            progress_totals = {}
            if "channels" in types_to_process:
                # Total unique channels from subscriptions + watch history
                subscription_channels = len(takeout_data.subscriptions)
                watch_channels = len(
                    set(
                        entry.channel_id or entry.channel_name or "unknown"
                        for entry in takeout_data.watch_history
                    )
                )
                progress_totals["channels"] = subscription_channels + watch_channels

            if "videos" in types_to_process:
                # Unique videos from watch history
                unique_videos = set()
                for entry in takeout_data.watch_history:
                    video_id = entry.video_id or entry.title_url or "unknown"
                    unique_videos.add(video_id)
                progress_totals["videos"] = len(unique_videos)

            if "user_videos" in types_to_process:
                # All watch entries with timestamps
                progress_totals["user_videos"] = len(
                    [e for e in takeout_data.watch_history if e.watched_at]
                )

            if "playlists" in types_to_process:
                progress_totals["playlists"] = len(takeout_data.playlists)

            if "playlist_memberships" in types_to_process:
                # Total playlist membership entries across all playlists
                total_memberships = sum(
                    len(playlist.videos) for playlist in takeout_data.playlists
                )
                progress_totals["playlist_memberships"] = total_memberships

            # Create visual-only progress bars with proper totals
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console,
            ) as progress_tracker:
                # Add tasks with proper totals
                task_mapping = {}
                task_counters = {}
                for data_type in types_to_process:
                    total = progress_totals.get(
                        data_type, 1
                    )  # Fallback to 1 if unknown
                    if data_type == "channels":
                        task_mapping[data_type] = progress_tracker.add_task(
                            "📺 Channels", total=total
                        )
                    elif data_type == "videos":
                        task_mapping[data_type] = progress_tracker.add_task(
                            "🎥 Videos", total=total
                        )
                    elif data_type == "user_videos":
                        task_mapping[data_type] = progress_tracker.add_task(
                            "👤 User Videos", total=total
                        )
                    elif data_type == "playlists":
                        task_mapping[data_type] = progress_tracker.add_task(
                            "📁 Playlists", total=total
                        )
                    elif data_type == "playlist_memberships":
                        task_mapping[data_type] = progress_tracker.add_task(
                            "🔗 Playlist Memberships", total=total
                        )
                    task_counters[data_type] = 0

                # Progress callback to update Rich progress bars smoothly
                def update_progress(data_type: str) -> None:
                    if data_type in task_mapping:
                        task_counters[data_type] += 1
                        # Update every item for smooth progress
                        progress_tracker.update(
                            task_mapping[data_type], completed=task_counters[data_type]
                        )

                # Perform seeding with database session (disable SQL logging for clean progress)
                async for session in db_manager.get_session(echo=False):
                    if incremental:
                        result = await seeding_service.seed_incrementally(
                            session,
                            takeout_data,
                            data_types=types_to_process,
                            skip_types=skip_types,
                            progress_callback=ProgressCallback(update_progress),
                        )
                    else:
                        result = await seeding_service.seed_database(
                            session,
                            takeout_data,
                            data_types=types_to_process,
                            skip_types=skip_types,
                            progress_callback=ProgressCallback(update_progress),
                        )

            # Display results outside the progress tracker
            _display_seeding_results(result)

            # Show filtering info if applied
            if only_types or skip_types:
                console.print(f"\n🔍 Filtering Applied:")
                if only_types:
                    console.print(f"   • Only processed: {', '.join(only_types)}")
                if skip_types:
                    console.print(f"   • Skipped: {', '.join(skip_types)}")

            console.print(f"\n✅ Database seeding completed successfully!")

        except TakeoutParsingError as e:
            console.print(f"❌ Error parsing Takeout data: {e}")
            console.print("\n💡 Make sure:")
            console.print("  • You've extracted the Takeout archive")
            console.print("  • You selected JSON format for watch history")
            console.print("  • The path points to the extracted folder")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"❌ Seeding failed: {e}")
            raise typer.Exit(1)

    asyncio.run(run_seeding())


async def _show_seeding_preview(
    takeout_data: TakeoutData,
    only_types: set[str],
    skip_types: set[str],
    progress_tracker: Progress,
    task_id: Any,
) -> None:
    """Show what would be seeded in dry-run mode."""
    progress_tracker.update(task_id, description="📋 Preparing seeding preview...")

    # Calculate what would be processed
    unique_channels = set()

    # From subscriptions
    for sub in takeout_data.subscriptions:
        if sub.channel_id:
            unique_channels.add(sub.channel_id)

    # From watch history
    for entry in takeout_data.watch_history:
        if entry.channel_id:
            unique_channels.add(entry.channel_id)

    unique_videos = len(takeout_data.get_unique_video_ids())
    user_videos = len(
        [entry for entry in takeout_data.watch_history if entry.watched_at]
    )
    playlists = len(takeout_data.playlists)

    # Apply filters
    process_channels = ("channels" not in skip_types) and (
        not only_types or "channels" in only_types
    )
    process_videos = ("videos" not in skip_types) and (
        not only_types or "videos" in only_types
    )
    process_user_videos = ("user_videos" not in skip_types) and (
        not only_types or "user_videos" in only_types
    )
    process_playlists = ("playlists" not in skip_types) and (
        not only_types or "playlists" in only_types
    )

    # Create preview table
    table = Table(
        title="🌱 Seeding Preview (Dry Run)",
        show_header=True,
        header_style="bold green",
    )
    table.add_column("Data Type", style="cyan", width=20)
    table.add_column("Count", style="green", justify="right", width=10)
    table.add_column("Status", style="yellow", width=15)
    table.add_column("Dependencies", style="blue", width=30)

    # Add rows based on processing order
    table.add_row(
        "Channels",
        str(len(unique_channels)),
        "✅ Process" if process_channels else "⏭️ Skip",
        "None (foundation data)",
    )

    table.add_row(
        "Videos",
        str(unique_videos),
        "✅ Process" if process_videos else "⏭️ Skip",
        "Requires: Channels",
    )

    table.add_row(
        "User Videos",
        str(user_videos),
        "✅ Process" if process_user_videos else "⏭️ Skip",
        "Requires: Videos",
    )

    table.add_row(
        "Playlists",
        str(playlists),
        "✅ Process" if process_playlists else "⏭️ Skip",
        "Requires: Channels",
    )

    console.print(table)

    # Show filtering info
    if only_types or skip_types:
        console.print(f"\n🔍 Filtering Applied:")
        if only_types:
            console.print(f"   • Only processing: {', '.join(only_types)}")
        if skip_types:
            console.print(f"   • Skipping: {', '.join(skip_types)}")

    console.print(f"\n💡 This is a dry run - no data will be written to the database")
    console.print(f"💡 Remove --dry-run to perform actual seeding")


def _display_seeding_results(results: Dict[str, Any]) -> None:
    """Display seeding results in a formatted table."""
    # Calculate totals across all data types
    total_created = sum(r.created for r in results.values())
    total_updated = sum(r.updated for r in results.values())
    total_failed = sum(r.failed for r in results.values())
    total_duration = sum(r.duration_seconds for r in results.values())

    # Calculate overall success rate
    total_operations = total_created + total_updated + total_failed
    success_rate = (
        ((total_created + total_updated) / total_operations * 100)
        if total_operations > 0
        else 0.0
    )

    # Build summary text
    summary_lines = ["📊 Results Summary:"]
    for data_type, result in sorted(results.items()):
        if data_type == "channels":
            emoji = "📺"
        elif data_type == "videos":
            emoji = "🎥"
        elif data_type == "user_videos":
            emoji = "👤"
        elif data_type == "playlists":
            emoji = "📁"
        else:
            emoji = "📄"

        summary_lines.append(
            f"   {emoji} {data_type.title()}: {result.created} created, {result.updated} updated, {result.failed} failed ({result.success_rate:.1f}%)"
        )

    console.print(
        Panel(
            f"""
✅ Seeding Completed Successfully

{chr(10).join(summary_lines)}

⏱️  Total Duration: {total_duration:.1f} seconds
📈 Overall Success Rate: {success_rate:.1f}%
🎯 Operations: {total_created:,} created, {total_updated:,} updated, {total_failed:,} failed
            """.strip(),
            title="🌱 Database Seeding Results",
            border_style="green",
        )
    )

    # Show detailed errors if any failed
    total_errors = sum(len(r.errors) for r in results.values() if r.errors)
    if total_errors > 0:
        console.print(f"\n⚠️  Found {total_errors} errors across all data types")
        for data_type, result in results.items():
            if result.errors:
                console.print(
                    f"   • {data_type}: {len(result.errors)} errors (showing first 3):"
                )
                for error in result.errors[:3]:
                    console.print(f"     - {error}")


# ============================================================================
# Historical Takeout Recovery Command
# ============================================================================


@takeout_app.command("recover")
def recover_metadata(
    takeout_dir: Path = typer.Option(
        Path("takeout"),
        "--takeout-dir",
        "-t",
        help="Base directory containing historical takeout subdirectories",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Show what would be recovered without making changes",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed progress for each video",
    ),
) -> None:
    """
    Recover metadata from historical Google Takeout exports.

    Scans for historical takeout directories and recovers video/channel
    metadata for placeholder entries in the database.

    Historical takeouts are identified by directory naming pattern:
    'YouTube and YouTube Music YYYY-MM-DD' or directories containing a date.

    The recovery process:
    1. Discovers all historical takeout directories
    2. Parses watch-history.json from each to build a metadata map
    3. Identifies placeholder videos in the database (title: '[Placeholder] Video {id}')
    4. Updates placeholders with real metadata from historical takeouts
    5. Creates missing channels found in historical data

    When multiple takeouts have different metadata for the same video,
    the most recent metadata is used.

    Examples:
        chronovista takeout recover --takeout-dir ~/takeouts
        chronovista takeout recover --dry-run
        chronovista takeout recover --verbose
    """
    import asyncio

    from ...models.takeout import RecoveryOptions
    from ...services.takeout_recovery_service import TakeoutRecoveryService
    from ...services.takeout_service import TakeoutService

    async def run_recovery() -> None:
        try:
            # Validate takeout directory exists
            if not takeout_dir.exists():
                console.print(f"[red]Error: Takeout directory not found: {takeout_dir}[/red]")
                raise typer.Exit(2)

            if not takeout_dir.is_dir():
                console.print(f"[red]Error: Path is not a directory: {takeout_dir}[/red]")
                raise typer.Exit(2)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Discovering historical takeouts...", total=None
                )

                # Discover historical takeouts
                historical_takeouts = TakeoutService.discover_historical_takeouts(
                    takeout_dir, sort_oldest_first=True
                )

                if not historical_takeouts:
                    console.print(
                        Panel(
                            f"[yellow]No historical takeouts found in {takeout_dir}[/yellow]\n\n"
                            "Expected directory structure:\n"
                            "  takeout/\n"
                            "    YouTube and YouTube Music 2023-01-15/\n"
                            "    YouTube and YouTube Music 2023-06-20/\n"
                            "    ...\n\n"
                            "Each subdirectory should contain:\n"
                            "  history/watch-history.json",
                            title="No Historical Takeouts Found",
                            border_style="yellow",
                        )
                    )
                    raise typer.Exit(0)

                # Display discovered takeouts
                progress.update(task, description="Preparing recovery...")

                dates = [t.export_date for t in historical_takeouts]
                console.print(
                    Panel(
                        f"Found {len(historical_takeouts)} historical takeout(s)\n"
                        f"Date range: {min(dates).date()} to {max(dates).date()}\n"
                        f"With watch history: {sum(1 for t in historical_takeouts if t.has_watch_history)}",
                        title="Historical Takeouts Discovered",
                        border_style="blue",
                    )
                )

                if verbose:
                    table = Table(
                        title="Discovered Takeouts",
                        show_header=True,
                        header_style="bold cyan",
                    )
                    table.add_column("Date", style="cyan")
                    table.add_column("Watch History", justify="center")
                    table.add_column("Playlists", justify="center")
                    table.add_column("Subscriptions", justify="center")

                    for takeout in historical_takeouts:
                        table.add_row(
                            str(takeout.export_date.date()),
                            "[green]Yes[/green]" if takeout.has_watch_history else "[red]No[/red]",
                            "[green]Yes[/green]" if takeout.has_playlists else "[red]No[/red]",
                            "[green]Yes[/green]" if takeout.has_subscriptions else "[red]No[/red]",
                        )

                    console.print(table)

                # Configure recovery options
                options = RecoveryOptions(
                    dry_run=dry_run,
                    verbose=verbose,
                    process_oldest_first=True,  # Process oldest first so newer overwrites
                    update_channels=True,
                    batch_size=100,
                )

                if dry_run:
                    console.print("\n[yellow]DRY RUN MODE - No changes will be made[/yellow]\n")

                # Run recovery
                progress.update(task, description="Running recovery...")

                recovery_service = TakeoutRecoveryService()

                async for session in db_manager.get_session(echo=False):
                    result = await recovery_service.recover_from_historical_takeouts(
                        session, takeout_dir, options
                    )

                # Display results
                _display_recovery_results(result, verbose)

        except TakeoutParsingError as e:
            console.print(f"[red]Error parsing Takeout data: {e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Recovery failed: {e}[/red]")
            import traceback
            if verbose:
                traceback.print_exc()
            raise typer.Exit(1)

    asyncio.run(run_recovery())


def _display_recovery_results(result: Any, verbose: bool) -> None:
    """Display recovery operation results."""
    from ...models.takeout import RecoveryResult

    if not isinstance(result, RecoveryResult):
        console.print("[red]Invalid result type[/red]")
        return

    # Calculate duration
    duration_seconds = 0.0
    if result.completed_at and result.started_at:
        duration_seconds = (result.completed_at - result.started_at).total_seconds()

    # Build summary
    mode_str = "[yellow]DRY RUN[/yellow]" if result.dry_run else "[green]APPLIED[/green]"

    summary_text = f"""
Mode: {mode_str}

Takeouts Scanned: {result.takeouts_scanned}
Date Range: {result.oldest_takeout_date.date() if result.oldest_takeout_date else 'N/A'} to {result.newest_takeout_date.date() if result.newest_takeout_date else 'N/A'}

Video Recovery:
   Recovered: {result.videos_recovered}
   Still Missing: {result.videos_still_missing}

Channel Recovery:
   Created: {result.channels_created}
   Updated: {result.channels_updated}

Duration: {duration_seconds:.1f} seconds
    """.strip()

    border_style = "yellow" if result.dry_run else "green"
    title = "Recovery Preview" if result.dry_run else "Recovery Complete"

    console.print(Panel(summary_text, title=title, border_style=border_style))

    # Show detailed actions in verbose mode or dry-run
    if verbose or result.dry_run:
        if result.video_actions:
            console.print("\n[bold]Video Recovery Actions:[/bold]")
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Video ID", style="cyan", width=15)
            table.add_column("Old Title", style="red", width=35)
            table.add_column("New Title", style="green", width=35)
            table.add_column("Source Date", style="yellow", width=12)

            for action in result.video_actions[:20]:  # Limit to first 20
                old_title = action.old_title[:32] + "..." if len(action.old_title) > 35 else action.old_title
                new_title = action.new_title[:32] + "..." if len(action.new_title) > 35 else action.new_title
                table.add_row(
                    action.video_id,
                    old_title,
                    new_title,
                    str(action.source_date.date()),
                )

            console.print(table)

            if len(result.video_actions) > 20:
                console.print(f"   ... and {len(result.video_actions) - 20} more")

        if result.channel_actions:
            console.print("\n[bold]Channel Recovery Actions:[/bold]")
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Channel ID", style="cyan", width=26)
            table.add_column("Channel Name", style="green", width=35)
            table.add_column("Action", style="yellow", width=12)
            table.add_column("Source Date", style="blue", width=12)

            for action in result.channel_actions[:20]:  # Limit to first 20
                name = action.channel_name[:32] + "..." if len(action.channel_name) > 35 else action.channel_name
                table.add_row(
                    action.channel_id,
                    name,
                    action.action_type,
                    str(action.source_date.date()),
                )

            console.print(table)

            if len(result.channel_actions) > 20:
                console.print(f"   ... and {len(result.channel_actions) - 20} more")

    # Show videos that couldn't be recovered
    if result.videos_not_recovered and verbose:
        console.print(f"\n[yellow]Videos still missing metadata ({len(result.videos_not_recovered)}):[/yellow]")
        for video_id in result.videos_not_recovered[:10]:
            console.print(f"   - {video_id}")
        if len(result.videos_not_recovered) > 10:
            console.print(f"   ... and {len(result.videos_not_recovered) - 10} more")

    # Show errors if any
    if result.errors:
        console.print(f"\n[red]Errors ({len(result.errors)}):[/red]")
        for error in result.errors[:5]:
            console.print(f"   - {error}")
        if len(result.errors) > 5:
            console.print(f"   ... and {len(result.errors) - 5} more")

    # Provide next steps
    if result.dry_run:
        console.print("\n[bold]To apply these changes, run without --dry-run:[/bold]")
        console.print("   chronovista takeout recover --takeout-dir <path>")
    elif result.videos_still_missing > 0:
        console.print(f"\n[yellow]Note: {result.videos_still_missing} videos could not be recovered.[/yellow]")
        console.print("These videos may not be present in your historical takeouts.")
        console.print("Consider using the YouTube API to fetch their metadata.")
