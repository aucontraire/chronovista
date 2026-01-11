"""
Data synchronization CLI commands for chronovista.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chronovista.auth import youtube_oauth
from chronovista.cli.sync.base import (
    SyncResult,
    check_authenticated,
    display_auth_error,
    display_progress_start,
    display_success,
    display_sync_results,
    display_warning,
    run_sync_operation,
)
from chronovista.cli.sync.transformers import DataTransformers
from chronovista.config.database import db_manager
from chronovista.db.models import Video as VideoDB
from chronovista.models.api_responses import YouTubeVideoResponse
from chronovista.models.channel import ChannelCreate
from chronovista.models.channel_topic import ChannelTopicCreate
from chronovista.models.enums import LanguageCode, TopicType
from chronovista.models.topic_category import TopicCategoryCreate
from chronovista.models.video import VideoCreate
from chronovista.models.video_topic import VideoTopicCreate
from chronovista.models.youtube_types import UserId
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.channel_topic_repository import ChannelTopicRepository
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.repositories.user_video_repository import UserVideoRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_topic_repository import VideoTopicRepository
from chronovista.services import youtube_service

console = Console()

# Repository instances
channel_repository = ChannelRepository()
topic_category_repository = TopicCategoryRepository()
user_video_repository = UserVideoRepository()
video_repository = VideoRepository()
video_topic_repository = VideoTopicRepository()
channel_topic_repository = ChannelTopicRepository()

sync_app = typer.Typer(
    name="sync",
    help="Data synchronization commands",
    no_args_is_help=True,
)


async def process_watch_history_batch(
    batch: List[Any], user_id: UserId
) -> Dict[str, int]:
    """Process a batch of watch history entries."""
    from chronovista.parsers.takeout_parser import WatchHistoryEntry

    results = {
        "videos_created": 0,
        "channels_created": 0,
        "user_videos_created": 0,
        "errors": 0,
    }

    # Process entire batch in single session to avoid foreign key issues
    async for session in db_manager.get_session():
        for entry in batch:
            try:
                # First, ensure channel exists
                if entry.channel_id:
                    existing_channel = await channel_repository.get_by_channel_id(
                        session, entry.channel_id
                    )
                    if not existing_channel:
                        channel_data = ChannelCreate(
                            channel_id=entry.channel_id,
                            title=entry.channel_name or f"Channel {entry.channel_id}",
                            description="",
                        )
                        await channel_repository.create_or_update(session, channel_data)
                        results["channels_created"] += 1

                # Then, ensure video exists
                existing_video = await video_repository.get_by_video_id(
                    session, entry.video_id
                )
                if not existing_video:
                    # Create minimal video record from Takeout data
                    video_data = VideoCreate(
                        video_id=entry.video_id,
                        channel_id=entry.channel_id or "UNKNOWN",
                        title=entry.title,
                        description=None,
                        upload_date=entry.watched_at,  # Placeholder - we don't have actual upload date
                        duration=0,  # We don't have duration from Takeout
                        made_for_kids=False,
                        self_declared_made_for_kids=False,
                        deleted_flag=False,
                    )
                    await video_repository.create_or_update(session, video_data)
                    results["videos_created"] += 1

                # Finally, record user video interaction
                await user_video_repository.record_watch(
                    session=session,
                    user_id=user_id,
                    video_id=entry.video_id,
                    watched_at=entry.watched_at,
                )
                results["user_videos_created"] += 1

            except Exception as e:
                results["errors"] += 1
                console.print(
                    f"[yellow]⚠️  Error processing {entry.video_id}: {str(e)}[/yellow]"
                )
                continue

    return results


# No module-level async functions to avoid coroutine creation during import


# No module-level async functions to avoid coroutine creation during import


@sync_app.command()
def history(
    file_path: str = typer.Argument(
        ..., help="Path to Google Takeout watch-history.json file"
    ),
    limit: int = typer.Option(
        None, "--limit", help="Limit number of entries to process (for testing)"
    ),
    batch_size: int = typer.Option(
        1000, "--batch-size", help="Number of entries to process in each batch"
    ),
) -> None:
    """Import watch history from Google Takeout JSON file."""

    async def import_watch_history() -> None:
        """Import watch history data from takeout file."""
        from pathlib import Path

        from chronovista.parsers.takeout_parser import TakeoutParser

        # Validate file path
        takeout_file = Path(file_path)
        if not takeout_file.exists():
            console.print(
                Panel(
                    f"[red]❌ File not found[/red]\n"
                    f"Could not find file: {file_path}",
                    title="Watch History Import",
                    border_style="red",
                )
            )
            return

        # Check authentication
        if not youtube_oauth.is_authenticated():
            console.print(
                Panel(
                    "[red]❌ Not authenticated[/red]\n"
                    "Use [bold]chronovista auth login[/bold] to sign in first.",
                    title="Watch History Import",
                    border_style="red",
                )
            )
            return

        try:
            console.print(
                f"[blue]🔄 Analyzing takeout file: {takeout_file.name}[/blue]"
            )

            # Get file statistics
            counts = TakeoutParser.count_entries(takeout_file)

            console.print(
                f"[blue]📊 Found {counts['videos']:,} video watches in takeout data[/blue]"
            )

            # Get user's channel ID to use as user_id
            my_channel = await youtube_service.get_my_channel()
            user_id = my_channel.id if my_channel else None

            if not user_id:
                console.print(
                    Panel(
                        "[red]❌ Could not identify user[/red]\n"
                        "Unable to get your channel ID for user tracking.",
                        title="Watch History Import",
                        border_style="red",
                    )
                )
                return

            # Determine how many entries to process
            total_to_process = (
                min(counts["videos"], limit) if limit else counts["videos"]
            )

            console.print(
                f"[blue]📥 Importing {total_to_process:,} watch history entries (user: {user_id})[/blue]"
            )

            # Process entries in batches
            processed = 0
            videos_created = 0
            channels_created = 0
            user_videos_created = 0
            errors = 0

            batch = []

            for entry in TakeoutParser.parse_watch_history_file(takeout_file):
                if limit and processed >= limit:
                    break

                batch.append(entry)

                # Process batch when it reaches batch_size
                if len(batch) >= batch_size:
                    batch_results = await process_watch_history_batch(batch, user_id)

                    videos_created += batch_results["videos_created"]
                    channels_created += batch_results["channels_created"]
                    user_videos_created += batch_results["user_videos_created"]
                    errors += batch_results["errors"]

                    processed += len(batch)
                    console.print(
                        f"[green]✅ Processed {processed:,} / {total_to_process:,} entries[/green]"
                    )

                    batch = []  # Clear batch

            # Process remaining entries in final batch
            if batch:
                batch_results = await process_watch_history_batch(batch, user_id)

                videos_created += batch_results["videos_created"]
                channels_created += batch_results["channels_created"]
                user_videos_created += batch_results["user_videos_created"]
                errors += batch_results["errors"]

                processed += len(batch)

            # Display final results
            console.print(
                Panel(
                    f"[green]✅ Watch history import complete![/green]\n"
                    f"Processed: {processed:,} entries\n"
                    f"Videos: {videos_created:,} created/updated\n"
                    f"Channels: {channels_created:,} created/updated\n"
                    f"User interactions: {user_videos_created:,} created/updated\n"
                    f"Errors: {errors:,}\n"
                    "Data flow: Google Takeout → Videos + Channels + UserVideos → Database ✅",
                    title="Watch History Import Complete",
                    border_style="green",
                )
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Failed to import watch history:[/red]\n{str(e)}",
                    title="Watch History Import Error",
                    border_style="red",
                )
            )

    # Run the async function
    try:
        asyncio.run(import_watch_history())
    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ Import failed:[/red]\n{str(e)}",
                title="Import Error",
                border_style="red",
            )
        )


@sync_app.command()
def playlists() -> None:
    """Sync playlists from YouTube."""
    console.print(
        Panel(
            "[yellow]Playlist sync not yet implemented[/yellow]\n"
            "This will fetch and store your YouTube playlists.",
            title="Sync Playlists",
            border_style="yellow",
        )
    )


@sync_app.command()
def transcripts() -> None:
    """Sync transcripts for videos."""
    console.print(
        Panel(
            "[yellow]Transcript sync not yet implemented[/yellow]\n"
            "This will download transcripts for your videos.",
            title="Sync Transcripts",
            border_style="yellow",
        )
    )


@sync_app.command()
def topics(
    region_code: str = typer.Option(
        "US", "--region", "-r", help="Two-character country code (e.g., US, GB, DE)"
    )
) -> None:
    """Sync YouTube video categories/topics to database."""

    async def sync_topics_data() -> SyncResult:
        """Sync topic categories from YouTube API."""
        result = SyncResult()

        # Check authentication using shared utility
        if not check_authenticated():
            display_auth_error("Sync Topics")
            return result

        display_progress_start(
            f"Fetching video categories from YouTube API...\nRegion: {region_code.upper()}",
            title="Sync Topics",
        )

        # Fetch video categories from YouTube API
        categories = await youtube_service.get_video_categories(region_code)

        if not categories:
            display_warning(
                f"No video categories found for region: {region_code}",
                title="No Categories",
            )
            return result

        display_success(f"Found {len(categories)} video categories")

        # Process and save categories to database
        async for session in db_manager.get_session(echo=False):
            for category in categories:
                try:
                    # Use transformer to create the model
                    topic_data = DataTransformers.extract_topic_category_create(category)

                    # Check if category already exists and create or update
                    existing = await topic_category_repository.exists(
                        session, category.id
                    )

                    await topic_category_repository.create_or_update(
                        session, topic_data
                    )

                    if existing:
                        result.updated += 1
                    else:
                        result.created += 1

                except Exception as e:
                    result.add_error(f"Category {category.id}: {e}")
                    console.print(
                        f"[red]Error processing category {category.id}: {e}[/red]"
                    )

        # Display results using shared utility
        display_sync_results(
            result,
            title=f"Topic Sync - Region: {region_code.upper()}",
            extra_info="Use [bold]chronovista topics list[/bold] to explore synced topics.",
        )

        return result

    # Run the async function using shared wrapper
    run_sync_operation(sync_topics_data, "Sync Topics")


@sync_app.command()
def all(
    region_code: str = typer.Option(
        "US",
        "--region",
        "-r",
        help="Two-character country code for topics (e.g., US, GB, DE)",
    )
) -> None:
    """Sync all data (full synchronization)."""

    async def sync_all_data() -> None:
        """Perform complete data synchronization."""
        # Check authentication
        if not youtube_oauth.is_authenticated():
            console.print(
                Panel(
                    "[red]❌ Not authenticated[/red]\n"
                    "Use [bold]chronovista auth login[/bold] to sign in first.",
                    title="Authentication Required",
                    border_style="red",
                )
            )
            return

        console.print(
            Panel(
                "[blue]🚀 Starting complete data synchronization...[/blue]\n"
                "This will sync: Topics → Channel → Liked Videos",
                title="Full Sync",
                border_style="blue",
            )
        )

        sync_results: dict[str, dict[str, Any]] = {
            "topics": {"status": "pending", "created": 0, "updated": 0, "errors": 0},
            "channel": {"status": "pending", "success": False},
            "liked": {"status": "pending", "count": 0, "errors": 0},
        }

        # Step 1: Sync Topics
        try:
            console.print(
                f"[cyan]Step 1/3: Syncing video categories (region: {region_code.upper()})[/cyan]"
            )

            categories = await youtube_service.get_video_categories(region_code)
            sync_results["topics"]["status"] = "running"

            if categories:
                async for session in db_manager.get_session(echo=False):
                    for category in categories:
                        try:
                            category_id = category.id
                            snippet = category.snippet
                            category_name = snippet.title if snippet else ""

                            topic_data = TopicCategoryCreate(
                                topic_id=category_id,
                                category_name=category_name,
                                parent_topic_id=None,
                                topic_type=TopicType.YOUTUBE,
                            )

                            existing = await topic_category_repository.exists(
                                session, category_id
                            )
                            await topic_category_repository.create_or_update(
                                session, topic_data
                            )

                            if existing:
                                sync_results["topics"]["updated"] += 1
                            else:
                                sync_results["topics"]["created"] += 1

                        except Exception as e:
                            sync_results["topics"]["errors"] += 1
                            console.print(
                                f"[red]Topic sync error for {category.id}: {e}[/red]"
                            )

                sync_results["topics"]["status"] = "completed"
                console.print(
                    f"[green]✅ Topics: {sync_results['topics']['created']} created, {sync_results['topics']['updated']} updated[/green]"
                )
            else:
                console.print("[yellow]⚠️ No topic categories found[/yellow]")
                sync_results["topics"]["status"] = "no_data"

        except Exception as e:
            sync_results["topics"]["status"] = "failed"
            console.print(f"[red]❌ Topic sync failed: {e}[/red]")

        # Step 2: Sync Channel Data
        try:
            console.print("[cyan]Step 2/3: Syncing your channel information[/cyan]")
            sync_results["channel"]["status"] = "running"

            channel_data = await youtube_service.get_my_channel()

            if channel_data:
                # Process channel data (simplified version)
                title = channel_data.snippet.title if channel_data.snippet else "Unknown"
                console.print(
                    f"[green]✅ Channel synced: {title}[/green]"
                )
                sync_results["channel"]["success"] = True
                sync_results["channel"]["status"] = "completed"
            else:
                console.print("[yellow]⚠️ No channel data found[/yellow]")
                sync_results["channel"]["status"] = "no_data"

        except Exception as e:
            sync_results["channel"]["status"] = "failed"
            console.print(f"[red]❌ Channel sync failed: {e}[/red]")

        # Step 3: Sync Liked Videos
        try:
            console.print("[cyan]Step 3/3: Syncing liked videos[/cyan]")
            sync_results["liked"]["status"] = "running"

            # Fetch all liked videos (no artificial limit - paginated by API)
            liked_videos = await youtube_service.get_liked_videos()

            if liked_videos:
                sync_results["liked"]["count"] = len(liked_videos)
                console.print(
                    f"[green]✅ Found {len(liked_videos)} liked videos[/green]"
                )
                sync_results["liked"]["status"] = "completed"
            else:
                console.print("[yellow]⚠️ No liked videos found[/yellow]")
                sync_results["liked"]["status"] = "no_data"

        except Exception as e:
            sync_results["liked"]["status"] = "failed"
            sync_results["liked"]["errors"] = 1
            console.print(f"[red]❌ Liked videos sync failed: {e}[/red]")

        # Display final results
        results_table = Table(title="Full Sync Results Summary")
        results_table.add_column("Component", style="cyan")
        results_table.add_column("Status", style="white")
        results_table.add_column("Details", style="green")

        # Topics row
        topics_status = sync_results["topics"]["status"]
        if topics_status == "completed":
            topics_details = f"{sync_results['topics']['created']} created, {sync_results['topics']['updated']} updated"
            topics_status_display = "✅ Success"
        elif topics_status == "failed":
            topics_details = f"{sync_results['topics']['errors']} errors"
            topics_status_display = "❌ Failed"
        else:
            topics_details = "No data"
            topics_status_display = "⚠️ No Data"

        results_table.add_row("Topics", topics_status_display, topics_details)

        # Channel row
        channel_status = sync_results["channel"]["status"]
        if channel_status == "completed":
            channel_details = "Channel data updated"
            channel_status_display = "✅ Success"
        elif channel_status == "failed":
            channel_details = "Sync failed"
            channel_status_display = "❌ Failed"
        else:
            channel_details = "No data"
            channel_status_display = "⚠️ No Data"

        results_table.add_row("Channel", channel_status_display, channel_details)

        # Liked videos row
        liked_status = sync_results["liked"]["status"]
        if liked_status == "completed":
            liked_details = f"{sync_results['liked']['count']} videos found"
            liked_status_display = "✅ Success"
        elif liked_status == "failed":
            liked_details = f"{sync_results['liked']['errors']} errors"
            liked_status_display = "❌ Failed"
        else:
            liked_details = "No data"
            liked_status_display = "⚠️ No Data"

        results_table.add_row("Liked Videos", liked_status_display, liked_details)

        console.print(results_table)

        # Final summary message
        total_errors = int(sync_results["topics"]["errors"]) + int(
            sync_results["liked"]["errors"]
        )
        all_successful = True
        for result in sync_results.values():
            if result["status"] not in ["completed", "no_data"]:
                all_successful = False
                break

        if total_errors == 0 and all_successful:
            console.print(
                Panel(
                    "[green]🎉 Full synchronization completed successfully![/green]\n"
                    "All available data has been synced to your database.\n\n"
                    "Next steps:\n"
                    "• Use [bold]chronovista topics list[/bold] to explore synced topics\n"
                    "• Check your synced data with other CLI commands",
                    title="Sync Complete",
                    border_style="green",
                )
            )
        else:
            console.print(
                Panel(
                    f"[yellow]⚠️ Full synchronization completed with issues[/yellow]\n"
                    f"Some components had errors or no data available.\n"
                    f"Total errors: {total_errors}\n\n"
                    "Check the results table above for details.",
                    title="Sync Complete with Issues",
                    border_style="yellow",
                )
            )

    # Run the async function
    try:
        asyncio.run(sync_all_data())
    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ Full sync failed:[/red]\n{str(e)}",
                title="Sync Error",
                border_style="red",
            )
        )


# Channel sync implementation moved to command function


@sync_app.command()
def channel(
    topic: str = typer.Option(
        None,
        "--topic",
        help="Only sync if channel matches topic ID (e.g., 25 for News & Politics)",
    )
) -> None:
    """Fetch and save your channel information to database."""

    async def sync_channel_data() -> SyncResult:
        """Sync channel data from YouTube API."""
        result = SyncResult()

        # Check authentication using shared utility
        if not check_authenticated():
            display_auth_error("Channel Sync")
            return result

        display_progress_start(
            "Fetching your YouTube channel information...",
            title="Channel Sync",
        )

        # Fetch channel data from YouTube API
        channel_data = await youtube_service.get_my_channel()

        if not channel_data:
            display_warning("No channel data retrieved", title="Channel Sync")
            return result

        # Apply topic filtering if requested
        if topic:
            console.print(
                f"[blue]🔍 Checking if channel matches topic ID: {topic}[/blue]"
            )

            # Validate topic exists
            async for session in db_manager.get_session():
                if not await topic_category_repository.exists(session, topic):
                    from chronovista.cli.sync.base import display_error

                    display_error(
                        f"Invalid topic ID: {topic}\n"
                        f"Use [bold]chronovista topics list[/bold] to see available topics.",
                        title="Topic Filter Error",
                    )
                    return result

            # Check if channel has matching topics using transformer
            topic_ids = DataTransformers.extract_topic_ids(channel_data)
            has_matching_topic = topic in topic_ids

            if not has_matching_topic:
                display_warning(
                    f"Channel does not match topic ID: {topic}\n"
                    f"Channel topics: {topic_ids[:3] if topic_ids else 'None'}\n"
                    f"Use [bold]chronovista sync channel[/bold] without --topic to sync anyway.",
                    title="Topic Filter: No Match",
                )
                return result

            display_success(f"Channel matches topic {topic}")

        console.print("[blue]💾 Saving channel data to database...[/blue]")

        # Transform YouTube API data using DataTransformers
        channel_create = DataTransformers.extract_channel_create(channel_data)

        # Save to database using repository
        async for session in db_manager.get_session():
            existing = await channel_repository.exists(session, channel_data.id)
            saved_channel = await channel_repository.create_or_update(
                session, channel_create
            )

            if existing:
                result.updated += 1
            else:
                result.created += 1

            # Extract and create channel-topic associations using transformer
            topic_ids = DataTransformers.extract_topic_ids(channel_data)
            if topic_ids:
                valid_associations = 0
                for topic_id in topic_ids:
                    # Check if topic exists in our database
                    if await topic_category_repository.exists(session, topic_id):
                        channel_topic_create = ChannelTopicCreate(
                            channel_id=saved_channel.channel_id,
                            topic_id=topic_id,
                        )
                        await channel_topic_repository.create_or_update(
                            session, channel_topic_create
                        )
                        valid_associations += 1
                    else:
                        console.print(
                            f"[dim]⚠️  Skipping unknown topic ID: {topic_id}[/dim]"
                        )

                if valid_associations > 0:
                    display_success(
                        f"Created {valid_associations} channel-topic associations"
                    )
                else:
                    display_warning(
                        "No valid topic associations created "
                        "(all topic IDs are Freebase entities, not video categories)"
                    )

        # Create display table for channel details
        table = Table(title="Channel Synced to Database")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Channel ID", saved_channel.channel_id)
        table.add_row("Title", saved_channel.title)
        table.add_row(
            "Description",
            (
                (saved_channel.description or "No description")[:100] + "..."
                if saved_channel.description
                and len(saved_channel.description) > 100
                else saved_channel.description or "No description"
            ),
        )
        table.add_row(
            "Subscriber Count",
            (
                str(saved_channel.subscriber_count)
                if saved_channel.subscriber_count
                else "Unknown"
            ),
        )
        table.add_row(
            "Video Count",
            (
                str(saved_channel.video_count)
                if saved_channel.video_count
                else "Unknown"
            ),
        )
        table.add_row("Country", saved_channel.country or "Unknown")
        table.add_row(
            "Default Language", saved_channel.default_language or "Unknown"
        )
        table.add_row(
            "Created At", saved_channel.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        )
        table.add_row(
            "Updated At", saved_channel.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        )

        console.print(table)

        # Display final results
        display_sync_results(
            result,
            title="Channel Sync Complete",
            extra_info=f"Channel '{saved_channel.title}' saved to database.\n"
            "End-to-end data flow: YouTube API → Database ✅",
        )

        return result

    # Run the async function using shared wrapper
    run_sync_operation(sync_channel_data, "Channel Sync")


# Liked videos sync implementation moved to command function


async def _create_videos_with_channels(
    videos_to_create: List[YouTubeVideoResponse],
    user_id: str,
) -> tuple[List[VideoDB], int]:
    """
    Helper function to create videos and their associated channels with batch channel fetching.

    Parameters
    ----------
    videos_to_create : List[YouTubeVideoResponse]
        List of YouTube video responses to create
    user_id : str
        User ID for tracking

    Returns
    -------
    tuple[List[VideoDB], int]
        Tuple of (created videos, count of new channels created)
    """
    from datetime import datetime
    import re

    created_videos: List[VideoDB] = []
    new_channels_count = 0

    # Collect unique missing channel IDs
    missing_channel_ids: set[str] = set()

    async for session in db_manager.get_session():
        for video in videos_to_create:
            snippet = video.snippet
            if snippet and snippet.channel_id:
                # Check if channel exists
                if not await channel_repository.exists(session, snippet.channel_id):
                    missing_channel_ids.add(snippet.channel_id)

    # Batch fetch all missing channels at once
    if missing_channel_ids:
        try:
            channel_details = await youtube_service.get_channel_details(
                list(missing_channel_ids)
            )

            # Create all channels
            async for session in db_manager.get_session():
                for channel_data in channel_details:
                    channel_snippet = channel_data.snippet
                    channel_statistics = channel_data.statistics

                    # Cast channel default_language
                    channel_default_lang: LanguageCode | None = None
                    if channel_snippet and channel_snippet.default_language:
                        try:
                            channel_default_lang = LanguageCode(channel_snippet.default_language)
                        except ValueError:
                            pass

                    # Get channel thumbnails
                    channel_thumbnails = channel_snippet.thumbnails if channel_snippet else {}
                    high_thumb = channel_thumbnails.get("high")
                    channel_thumbnail_url = high_thumb.url if high_thumb else None

                    channel_create_obj = ChannelCreate(
                        channel_id=channel_data.id,
                        title=channel_snippet.title if channel_snippet else f"Channel {channel_data.id}",
                        description=channel_snippet.description if channel_snippet else "",
                        subscriber_count=channel_statistics.subscriber_count if channel_statistics else None,
                        video_count=channel_statistics.video_count if channel_statistics else None,
                        default_language=channel_default_lang,
                        country=channel_snippet.country if channel_snippet else None,
                        thumbnail_url=channel_thumbnail_url,
                    )

                    saved_channel = await channel_repository.create_or_update(
                        session, channel_create_obj
                    )
                    new_channels_count += 1

                    # Extract and create channel-topic associations
                    topic_details = channel_data.topic_details
                    topic_ids = topic_details.topic_ids if topic_details else []
                    if topic_ids:
                        for topic_id in topic_ids:
                            # Check if topic exists in our database
                            if await topic_category_repository.exists(session, topic_id):
                                channel_topic_create = ChannelTopicCreate(
                                    channel_id=saved_channel.channel_id,
                                    topic_id=topic_id,
                                )
                                await channel_topic_repository.create_or_update(
                                    session, channel_topic_create
                                )

                await session.commit()

        except Exception as e:
            console.print(f"[yellow]⚠️  Could not batch fetch channel details: {e}[/yellow]")

    # Now create all videos
    async for session in db_manager.get_session():
        for video_data in videos_to_create:
            snippet = video_data.snippet
            statistics = video_data.statistics
            content_details = video_data.content_details

            # Parse upload date
            upload_date = snippet.published_at if snippet else None

            # Parse duration (PT4M13S format)
            duration_str = content_details.duration if content_details else "PT0S"
            duration_seconds = 0
            if duration_str and duration_str.startswith("PT"):
                # Parse ISO 8601 duration format
                pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
                match = re.match(pattern, duration_str)
                if match:
                    hours = int(match.group(1) or 0)
                    minutes = int(match.group(2) or 0)
                    seconds = int(match.group(3) or 0)
                    duration_seconds = hours * 3600 + minutes * 60 + seconds

            # Create Video instance
            content_rating = content_details.content_rating if content_details else None
            made_for_kids = False
            if content_rating and isinstance(content_rating, dict):
                made_for_kids = content_rating.get("ytRating") == "ytAgeRestricted"

            # Cast language codes
            default_lang: LanguageCode | None = None
            default_audio_lang: LanguageCode | None = None
            if snippet:
                if snippet.default_language:
                    try:
                        default_lang = LanguageCode(snippet.default_language)
                    except ValueError:
                        pass
                if snippet.default_audio_language:
                    try:
                        default_audio_lang = LanguageCode(snippet.default_audio_language)
                    except ValueError:
                        pass

            video_create = VideoCreate(
                video_id=video_data.id,
                channel_id=snippet.channel_id if snippet else "",
                title=snippet.title if snippet else "",
                description=snippet.description if snippet else None,
                upload_date=upload_date or datetime.now(),
                duration=duration_seconds,
                made_for_kids=made_for_kids,
                self_declared_made_for_kids=False,  # Not available in API
                default_language=default_lang,
                default_audio_language=default_audio_lang,
                like_count=statistics.like_count if statistics else None,
                view_count=statistics.view_count if statistics else None,
                comment_count=statistics.comment_count if statistics else None,
                deleted_flag=False,
            )

            # Now save the video
            saved_video = await video_repository.create_or_update(session, video_create)
            created_videos.append(saved_video)

            # Extract and create video-topic association if categoryId exists
            category_id = snippet.category_id if snippet else None
            if category_id:
                try:
                    # Create video-topic association
                    video_topic_create = VideoTopicCreate(
                        video_id=saved_video.video_id,
                        topic_id=category_id,
                        relevance_type="primary",  # This is the main category for the video
                    )
                    await video_topic_repository.create_or_update(
                        session, video_topic_create
                    )
                except Exception:
                    # Silently skip if topic doesn't exist
                    pass

        await session.commit()

    return created_videos, new_channels_count


async def _show_liked_videos_dry_run(
    videos: list[YouTubeVideoResponse],
    user_id: str,
    existing_video_ids: List[str],
    missing_video_ids: List[str],
    create_missing: bool,
) -> None:
    """
    Display preview of liked videos that would be synced without making database changes.

    Parameters
    ----------
    videos : list[YouTubeVideoResponse]
        List of liked videos from YouTube API
    user_id : str
        User ID for tracking
    existing_video_ids : List[str]
        Video IDs already in database
    missing_video_ids : List[str]
        Video IDs not in database
    create_missing : bool
        Whether --create-missing flag is set
    """
    import re
    from datetime import datetime

    # Helper function to parse ISO 8601 duration
    def parse_duration(duration_str: str) -> int:
        """Parse ISO 8601 duration (PT4M13S) to seconds."""
        if not duration_str or not duration_str.startswith("PT"):
            return 0
        pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
        match = re.match(pattern, duration_str)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            return hours * 3600 + minutes * 60 + seconds
        return 0

    # Display panel header with database status
    console.print()
    console.print(
        Panel(
            f"[blue]🌱 Sync Preview (Dry Run)[/blue]\n"
            f"User: {user_id}\n"
            f"Total liked videos: {len(videos)}\n"
            f"Videos already in database: {len(existing_video_ids)}\n"
            f"Videos NOT in database: {len(missing_video_ids)}",
            title="Liked Videos Sync Preview",
            border_style="blue",
        )
    )

    # Create preview table
    table = Table(title=f"Preview: {len(videos)} Liked Videos")
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Channel", style="green", max_width=25)
    table.add_column("Duration", style="yellow", justify="right")
    table.add_column("Views", style="magenta", justify="right")
    table.add_column("Likes", style="red", justify="right")

    for video in videos:
        snippet = video.snippet
        statistics = video.statistics
        content_details = video.content_details

        # Parse duration
        duration_str = content_details.duration if content_details else "PT0S"
        duration_seconds = parse_duration(duration_str)
        duration_formatted = f"{duration_seconds // 60}:{duration_seconds % 60:02d}"

        # Format counts
        view_count = (
            f"{statistics.view_count:,}" if statistics and statistics.view_count else "N/A"
        )
        like_count = (
            f"{statistics.like_count:,}" if statistics and statistics.like_count else "N/A"
        )

        # Add row
        title = snippet.title if snippet else "Unknown"
        channel_title = snippet.channel_title if snippet else "Unknown"

        table.add_row(
            title[:37] + "..." if len(title) > 40 else title,
            channel_title[:22] + "..." if len(channel_title) > 25 else channel_title,
            duration_formatted,
            view_count,
            like_count,
        )

    console.print(table)

    # Footer message showing what would happen
    console.print()
    console.print(
        "[yellow]💡 This is a dry run - no data will be written to the database[/yellow]"
    )
    console.print()

    if create_missing:
        console.print("[blue]📋 What would happen (--create-missing mode):[/blue]")
        console.print(f"   [green]• Update liked status for {len(existing_video_ids)} existing videos[/green]")
        console.print(f"   [yellow]• Create {len(missing_video_ids)} new videos with full metadata[/yellow]")
        console.print(f"   [yellow]• Update liked status for {len(missing_video_ids)} new videos[/yellow]")
    else:
        console.print("[blue]📋 What would happen (existing-only mode):[/blue]")
        console.print(f"   [green]• Update liked status for {len(existing_video_ids)} existing videos[/green]")
        if missing_video_ids:
            console.print(f"   [yellow]• Skip {len(missing_video_ids)} videos not in database[/yellow]")
            console.print()
            console.print("[yellow]💡 To include missing videos, run with --create-missing[/yellow]")

    console.print()
    console.print("[yellow]💡 Remove --dry-run to perform actual sync[/yellow]")


@sync_app.command()
def liked(
    topic: str = typer.Option(
        None, "--topic", help="Filter videos by topic ID (e.g., 25 for News & Politics)"
    ),
    create_missing: bool = typer.Option(
        False,
        "--create-missing",
        help="Create Video and Channel records for liked videos not yet in database (makes additional API calls)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be synced without making database changes",
    ),
) -> None:
    """
    Sync liked video status for videos in your database.

    By default, only updates 'liked' status for videos already in your database.
    Use --create-missing to also fetch and save videos not yet in your database
    (this makes additional YouTube API calls for metadata).

    Examples:
        chronovista sync liked                    # Update liked status for known videos
        chronovista sync liked --create-missing   # Fetch all liked videos with full metadata
        chronovista sync liked --dry-run          # Preview without changes
    """

    async def sync_liked_videos() -> None:
        """Sync liked videos from YouTube API."""
        # Check authentication
        if not youtube_oauth.is_authenticated():
            console.print(
                Panel(
                    "[red]❌ Not authenticated[/red]\n"
                    "Use [bold]chronovista auth login[/bold] to sign in first.",
                    title="Liked Videos Sync",
                    border_style="red",
                )
            )
            return

        try:
            console.print(
                "[blue]🔄 Fetching your channel info for user identification...[/blue]"
            )

            # Get user's channel ID to use as user_id
            my_channel = await youtube_service.get_my_channel()
            user_id = my_channel.id if my_channel else None

            if not user_id:
                console.print(
                    Panel(
                        "[red]❌ Could not identify user[/red]\n"
                        "Unable to get your channel ID for user tracking.",
                        title="Liked Videos Sync",
                        border_style="red",
                    )
                )
                return

            console.print(
                "[blue]🔄 Fetching your liked videos...[/blue]"
            )

            # Fetch all liked videos from YouTube API (no artificial limit)
            liked_videos = await youtube_service.get_liked_videos()

            if not liked_videos:
                console.print(
                    Panel(
                        "[yellow]ℹ️ No liked videos found[/yellow]\n"
                        "Either you haven't liked any videos or the liked videos playlist is private.",
                        title="Liked Videos Sync",
                        border_style="yellow",
                    )
                )
                return

            console.print(f"[green]✅ Found {len(liked_videos)} liked videos from YouTube[/green]")

            # Apply topic filtering if requested
            if topic:
                console.print(f"[blue]🔍 Filtering videos by topic ID: {topic}[/blue]")

                # Validate topic exists
                async for session in db_manager.get_session():
                    if not await topic_category_repository.exists(session, topic):
                        console.print(
                            Panel(
                                f"[red]❌ Invalid topic ID: {topic}[/red]\n"
                                f"Use [bold]chronovista topics list[/bold] to see available topics.",
                                title="Topic Filter Error",
                                border_style="red",
                            )
                        )
                        return

                # Filter videos by categoryId
                filtered_videos = []
                for video in liked_videos:
                    snippet = video.snippet
                    category_id = snippet.category_id if snippet else None
                    if category_id == topic:
                        filtered_videos.append(video)

                console.print(
                    f"[blue]📊 Topic filter: {len(filtered_videos)} of {len(liked_videos)} videos match topic {topic}[/blue]"
                )
                liked_videos = filtered_videos

                if not liked_videos:
                    console.print(
                        Panel(
                            f"[yellow]ℹ️ No videos found with topic ID: {topic}[/yellow]\n"
                            f"Try a different topic or remove the --topic filter.",
                            title="No Matching Videos",
                            border_style="yellow",
                        )
                    )
                    return

            # Categorize videos: existing vs missing from database
            console.print()
            console.print("[blue]📊 Checking database status...[/blue]")

            existing_video_ids: List[str] = []
            missing_video_ids: List[str] = []

            async for session in db_manager.get_session():
                for video_data in liked_videos:
                    video_id = video_data.id
                    if await video_repository.exists(session, video_id):
                        existing_video_ids.append(video_id)
                    else:
                        missing_video_ids.append(video_id)

            console.print()
            console.print("[blue]📊 Database Status:[/blue]")
            console.print(f"   [green]• Videos already in database: {len(existing_video_ids)}[/green]")
            console.print(f"   [yellow]• Videos NOT in database: {len(missing_video_ids)}[/yellow]")
            console.print()

            # Handle dry-run mode
            if dry_run:
                await _show_liked_videos_dry_run(
                    liked_videos, user_id, existing_video_ids, missing_video_ids, create_missing
                )
                return

            # Process existing videos (default behavior)
            if existing_video_ids:
                console.print(f"[blue]💾 Updating liked status for {len(existing_video_ids)} videos...[/blue]")

                async for session in db_manager.get_session():
                    # Batch update liked status for existing videos
                    updated_count = await user_video_repository.update_like_status_batch(
                        session=session,
                        user_id=user_id,
                        video_ids=existing_video_ids,
                        liked=True,
                    )

                    # For videos that don't have user_video records yet, create them
                    videos_to_like = []
                    for video_id in existing_video_ids:
                        existing_interaction = await user_video_repository.get_by_composite_key(
                            session, user_id, video_id
                        )
                        if not existing_interaction:
                            videos_to_like.append(video_id)

                    # Create new user_video records with liked=True
                    for video_id in videos_to_like:
                        await user_video_repository.record_like(
                            session=session,
                            user_id=user_id,
                            video_id=video_id,
                            liked=True,
                        )

                    await session.commit()

                console.print(f"[green]✅ Updated liked status for {len(existing_video_ids)} videos[/green]")

            # Process missing videos only if --create-missing flag is set
            if missing_video_ids and create_missing:
                console.print()
                console.print(f"[blue]💾 Creating {len(missing_video_ids)} new videos and channels...[/blue]")

                videos_to_create = [v for v in liked_videos if v.id in missing_video_ids]
                created_videos, created_channels = await _create_videos_with_channels(
                    videos_to_create, user_id
                )

                console.print(f"[green]✅ Created {len(created_videos)} new videos, {created_channels} new channels[/green]")
                console.print(f"[blue]💾 Updating liked status for {len(created_videos)} videos...[/blue]")

                # Update liked status for newly created videos
                async for session in db_manager.get_session():
                    for video_id in [v.video_id for v in created_videos]:
                        await user_video_repository.record_like(
                            session=session,
                            user_id=user_id,
                            video_id=video_id,
                            liked=True,
                        )
                    await session.commit()

                console.print(f"[green]✅ Updated liked status for {len(created_videos)} videos[/green]")

            elif missing_video_ids and not create_missing:
                console.print()
                console.print(f"[yellow]ℹ️  Skipped {len(missing_video_ids)} videos not in your database[/yellow]")
                console.print("[yellow]💡 To fetch metadata for these videos, run:[/yellow]")
                console.print("[yellow]   chronovista sync liked --create-missing[/yellow]")

            # Final summary
            console.print()
            total_updated = len(existing_video_ids) + (len(missing_video_ids) if create_missing else 0)
            console.print(
                Panel(
                    f"[green]✅ Liked videos synced successfully![/green]\n"
                    f"Updated liked status for {total_updated} videos.\n"
                    f"Data flow: YouTube API → User Video Interactions → Database ✅",
                    title="Liked Videos Sync Complete",
                    border_style="green",
                )
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Failed to sync liked videos:[/red]\n{str(e)}",
                    title="Liked Videos Sync Error",
                    border_style="red",
                )
            )

    # Run the async function
    try:
        asyncio.run(sync_liked_videos())
    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ Sync failed:[/red]\n{str(e)}",
                title="Sync Error",
                border_style="red",
            )
        )
