"""
Data synchronization CLI commands for chronovista.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import typer
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table

from chronovista.auth import youtube_oauth
from chronovista.config.database import db_manager
from chronovista.models.channel import ChannelCreate
from chronovista.models.channel_topic import ChannelTopicCreate
from chronovista.models.topic_category import TopicCategoryCreate
from chronovista.models.user_video import UserVideoCreate
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
                    watch_duration=None,  # Not available in Takeout
                    completion_percentage=None,  # Not available in Takeout
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
            user_id = my_channel.get("id")

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

    async def sync_topics_data() -> None:
        """Sync topic categories from YouTube API."""
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

        try:
            console.print(
                Panel(
                    f"[blue]🔄 Fetching video categories from YouTube API...[/blue]\n"
                    f"Region: {region_code.upper()}",
                    title="Sync Topics",
                    border_style="blue",
                )
            )

            # Fetch video categories from YouTube API
            categories = await youtube_service.get_video_categories(region_code)

            if not categories:
                console.print(
                    Panel(
                        f"[yellow]⚠️ No video categories found for region: {region_code}[/yellow]",
                        title="No Categories",
                        border_style="yellow",
                    )
                )
                return

            console.print(f"[green]✅ Found {len(categories)} video categories[/green]")

            # Process and save categories to database
            created_count = 0
            updated_count = 0
            error_count = 0

            async for session in db_manager.get_session(echo=False):
                for category in categories:
                    try:
                        # Extract category data
                        category_id = category["id"]
                        snippet = category["snippet"]
                        category_name = snippet["title"]

                        # Create topic category model
                        topic_data = TopicCategoryCreate(
                            topic_id=category_id,
                            category_name=category_name,
                            parent_topic_id=None,  # YouTube categories don't have hierarchy
                            topic_type="youtube",
                        )

                        # Check if category already exists and create or update
                        existing = await topic_category_repository.exists(
                            session, category_id
                        )

                        await topic_category_repository.create_or_update(
                            session, topic_data
                        )

                        if existing:
                            updated_count += 1
                        else:
                            created_count += 1

                    except Exception as e:
                        error_count += 1
                        console.print(
                            f"[red]Error processing category {category.get('id', 'unknown')}: {e}[/red]"
                        )

            # Display results summary
            results_table = Table(
                title=f"Topic Sync Results - Region: {region_code.upper()}"
            )
            results_table.add_column("Metric", style="cyan")
            results_table.add_column("Count", style="green")

            results_table.add_row("Categories Found", str(len(categories)))
            results_table.add_row("Created", str(created_count))
            results_table.add_row("Updated", str(updated_count))
            results_table.add_row("Errors", str(error_count))

            console.print(results_table)

            if error_count == 0:
                console.print(
                    Panel(
                        f"[green]✅ Topic sync completed successfully![/green]\n"
                        f"Created: {created_count} | Updated: {updated_count}\n"
                        f"Total topics available: {created_count + updated_count}\n\n"
                        f"Use [bold]chronovista topics list[/bold] to explore synced topics.",
                        title="Sync Complete",
                        border_style="green",
                    )
                )
            else:
                console.print(
                    Panel(
                        f"[yellow]⚠️ Topic sync completed with {error_count} errors[/yellow]\n"
                        f"Successfully processed: {created_count + updated_count} topics\n"
                        f"Use [bold]chronovista topics list[/bold] to explore synced topics.",
                        title="Sync Complete with Errors",
                        border_style="yellow",
                    )
                )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Failed to sync topics:[/red]\n{str(e)}",
                    title="Sync Error",
                    border_style="red",
                )
            )

    # Run the async function
    try:
        asyncio.run(sync_topics_data())
    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ Sync failed:[/red]\n{str(e)}",
                title="Sync Error",
                border_style="red",
            )
        )


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
                            category_id = category["id"]
                            snippet = category["snippet"]
                            category_name = snippet["title"]

                            topic_data = TopicCategoryCreate(
                                topic_id=category_id,
                                category_name=category_name,
                                parent_topic_id=None,
                                topic_type="youtube",
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
                                f"[red]Topic sync error for {category.get('id', 'unknown')}: {e}[/red]"
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
                console.print(
                    f"[green]✅ Channel synced: {channel_data.get('snippet', {}).get('title', 'Unknown')}[/green]"
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

            liked_videos = await youtube_service.get_liked_videos(max_results=10)

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
def channel() -> None:
    """Fetch and save your channel information to database."""

    async def sync_channel_data() -> None:
        """Sync channel data from YouTube API."""
        # Check authentication
        if not youtube_oauth.is_authenticated():
            console.print(
                Panel(
                    "[red]❌ Not authenticated[/red]\n"
                    "Use [bold]chronovista auth login[/bold] to sign in first.",
                    title="Channel Sync",
                    border_style="red",
                )
            )
            return

        try:
            console.print(
                "[blue]🔄 Fetching your YouTube channel information...[/blue]"
            )

            # Fetch channel data from YouTube API
            channel_data = await youtube_service.get_my_channel()

            console.print("[blue]💾 Saving channel data to database...[/blue]")

            # Transform YouTube API data to our Channel model
            snippet = channel_data.get("snippet", {})
            statistics = channel_data.get("statistics", {})

            # Parse dates
            from datetime import datetime

            published_at_str = snippet.get("publishedAt")
            created_at = None
            if published_at_str:
                created_at = datetime.fromisoformat(
                    published_at_str.replace("Z", "+00:00")
                )

            # Create Channel instance
            channel_create = ChannelCreate(
                channel_id=channel_data.get("id") or "",
                title=snippet.get("title", ""),
                description=snippet.get("description"),
                subscriber_count=(
                    int(statistics.get("subscriberCount", 0))
                    if statistics.get("subscriberCount")
                    else None
                ),
                video_count=(
                    int(statistics.get("videoCount", 0))
                    if statistics.get("videoCount")
                    else None
                ),
                default_language=snippet.get("defaultLanguage"),
                country=snippet.get("country"),
                thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url"),
            )

            # Save to database using repository
            async for session in db_manager.get_session():
                saved_channel = await channel_repository.create_or_update(
                    session, channel_create
                )

                # Extract and create channel-topic associations if topicDetails exists
                topic_details = channel_data.get("topicDetails", {})
                topic_ids = topic_details.get("topicIds", [])
                if topic_ids:
                    try:
                        valid_associations = 0
                        for topic_id in topic_ids:
                            # Check if topic exists in our database (only video categories are synced)
                            if await topic_category_repository.exists(session, topic_id):
                                # Create channel-topic association
                                channel_topic_create = ChannelTopicCreate(
                                    channel_id=saved_channel.channel_id, topic_id=topic_id
                                )
                                await channel_topic_repository.create_or_update(
                                    session, channel_topic_create
                                )
                                valid_associations += 1
                            else:
                                console.print(f"[dim]⚠️  Skipping unknown topic ID: {topic_id}[/dim]")

                        if valid_associations > 0:
                            console.print(
                                f"[green]✅ Created {valid_associations} channel-topic associations[/green]"
                            )
                        else:
                            console.print(
                                f"[yellow]⚠️  No valid topic associations created (all topic IDs are Freebase entities, not video categories)[/yellow]"
                            )
                    except Exception as e:
                        console.print(
                            f"[yellow]⚠️  Could not create topic associations for channel {saved_channel.channel_id}: {e}[/yellow]"
                        )

            # Create display table
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

            console.print(
                Panel(
                    "[green]✅ Channel data synced successfully![/green]\n"
                    f"Channel '{saved_channel.title}' saved to database.\n"
                    "End-to-end data flow: YouTube API → Database ✅",
                    title="Channel Sync Complete",
                    border_style="green",
                )
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Failed to sync channel data:[/red]\n{str(e)}",
                    title="Channel Sync Error",
                    border_style="red",
                )
            )

    # Run the async function
    try:
        asyncio.run(sync_channel_data())
    except Exception as e:
        console.print(
            Panel(
                f"[red]❌ Sync failed:[/red]\n{str(e)}",
                title="Sync Error",
                border_style="red",
            )
        )


# Liked videos sync implementation moved to command function


@sync_app.command()
def liked() -> None:
    """Fetch and save your liked videos to database."""

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
            user_id = my_channel.get("id")

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
                f"[blue]🔄 Fetching your liked videos (user: {user_id})...[/blue]"
            )

            # Fetch liked videos from YouTube API
            liked_videos = await youtube_service.get_liked_videos(max_results=10)

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

            console.print(
                f"[blue]💾 Saving {len(liked_videos)} liked videos to database...[/blue]"
            )

            saved_videos = []

            # Process each video
            for video_data in liked_videos:
                # Transform YouTube API data to our Video model
                snippet = video_data.get("snippet", {})
                statistics = video_data.get("statistics", {})
                content_details = video_data.get("contentDetails", {})

                # Parse upload date
                from datetime import datetime

                upload_date_str = snippet.get("publishedAt")
                upload_date = None
                if upload_date_str:
                    upload_date = datetime.fromisoformat(
                        upload_date_str.replace("Z", "+00:00")
                    )

                # Parse duration (PT4M13S format)
                duration_str = content_details.get("duration", "PT0S")
                duration_seconds = 0
                if duration_str.startswith("PT"):
                    import re

                    # Parse ISO 8601 duration format
                    pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
                    match = re.match(pattern, duration_str)
                    if match:
                        hours = int(match.group(1) or 0)
                        minutes = int(match.group(2) or 0)
                        seconds = int(match.group(3) or 0)
                        duration_seconds = hours * 3600 + minutes * 60 + seconds

                # Create Video instance
                video_create = VideoCreate(
                    video_id=video_data.get("id") or "",
                    channel_id=snippet.get("channelId") or "",
                    title=snippet.get("title", ""),
                    description=snippet.get("description"),
                    upload_date=upload_date or datetime.now(),
                    duration=duration_seconds,
                    made_for_kids=content_details.get("contentRating", {}).get(
                        "ytRating"
                    )
                    == "ytAgeRestricted",
                    self_declared_made_for_kids=False,  # Not available in API
                    default_language=snippet.get("defaultLanguage"),
                    default_audio_language=snippet.get("defaultAudioLanguage"),
                    like_count=(
                        int(statistics.get("likeCount", 0))
                        if statistics.get("likeCount")
                        else None
                    ),
                    view_count=(
                        int(statistics.get("viewCount", 0))
                        if statistics.get("viewCount")
                        else None
                    ),
                    comment_count=(
                        int(statistics.get("commentCount", 0))
                        if statistics.get("commentCount")
                        else None
                    ),
                    deleted_flag=False,
                )

                # Ensure the channel exists before creating the video
                async for session in db_manager.get_session():
                    # Check if channel exists, create if not
                    existing_channel = await channel_repository.get_by_channel_id(
                        session, video_create.channel_id
                    )
                    if not existing_channel:
                        # Fetch full channel details from YouTube API
                        try:
                            channel_data = await youtube_service.get_channel_details(
                                video_create.channel_id
                            )
                            channel_snippet = channel_data.get("snippet", {})
                            channel_statistics = channel_data.get("statistics", {})

                            # Parse channel creation date
                            published_at_str = channel_snippet.get("publishedAt")
                            created_at = None
                            if published_at_str:
                                created_at = datetime.fromisoformat(
                                    published_at_str.replace("Z", "+00:00")
                                )

                            # Create full channel record with all details
                            channel_create_obj = ChannelCreate(
                                channel_id=video_create.channel_id,
                                title=channel_snippet.get(
                                    "title",
                                    snippet.get(
                                        "channelTitle",
                                        f"Channel {video_create.channel_id}",
                                    ),
                                ),
                                description=channel_snippet.get("description", ""),
                                subscriber_count=(
                                    int(channel_statistics.get("subscriberCount", 0))
                                    if channel_statistics.get("subscriberCount")
                                    else None
                                ),
                                video_count=(
                                    int(channel_statistics.get("videoCount", 0))
                                    if channel_statistics.get("videoCount")
                                    else None
                                ),
                                default_language=channel_snippet.get("defaultLanguage"),
                                country=channel_snippet.get("country"),
                                thumbnail_url=channel_snippet.get("thumbnails", {})
                                .get("high", {})
                                .get("url"),
                            )
                        except Exception as e:
                            console.print(
                                f"[yellow]⚠️  Could not fetch full details for channel {video_create.channel_id}: {e}[/yellow]"
                            )
                            # Fallback to basic channel record
                            channel_create_obj = ChannelCreate(
                                channel_id=video_create.channel_id,
                                title=snippet.get(
                                    "channelTitle", f"Channel {video_create.channel_id}"
                                ),
                                description="",
                            )

                        saved_channel = await channel_repository.create_or_update(
                            session, channel_create_obj
                        )

                        # Extract and create channel-topic associations if we have full channel details
                        if (
                            "channel_data" in locals()
                        ):  # Only if we successfully fetched channel details
                            topic_details = channel_data.get("topicDetails", {})
                            topic_ids = topic_details.get("topicIds", [])
                            if topic_ids:
                                try:
                                    valid_associations = 0
                                    for topic_id in topic_ids:
                                        # Check if topic exists in our database (only video categories are synced)
                                        if await topic_category_repository.exists(session, topic_id):
                                            # Create channel-topic association
                                            channel_topic_create = ChannelTopicCreate(
                                                channel_id=saved_channel.channel_id,
                                                topic_id=topic_id,
                                            )
                                            await channel_topic_repository.create_or_update(
                                                session, channel_topic_create
                                            )
                                            valid_associations += 1
                                        # Silently skip unknown topics during bulk video processing
                                    
                                    if valid_associations > 0:
                                        console.print(f"[dim]✅ Created {valid_associations} channel-topic associations for {saved_channel.channel_id[:8]}...[/dim]")
                                except Exception as e:
                                    console.print(
                                        f"[yellow]⚠️  Could not create topic associations for channel {saved_channel.channel_id}: {e}[/yellow]"
                                    )

                    # Now save the video
                    saved_video = await video_repository.create_or_update(
                        session, video_create
                    )
                    saved_videos.append(saved_video)

                    # Extract and create video-topic association if categoryId exists
                    category_id = snippet.get("categoryId")
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
                        except Exception as e:
                            console.print(
                                f"[yellow]⚠️  Could not create topic association for video {saved_video.video_id}: {e}[/yellow]"
                            )

                    # Record user interaction (liked video)
                    # Note: Using record_watch as a placeholder since UserVideoRepository doesn't have create_or_update
                    # In the future, we might need a separate record_like method
                    await user_video_repository.record_watch(
                        session=session,
                        user_id=user_id,
                        video_id=saved_video.video_id,
                        watched_at=None,  # We don't have watch timestamp from liked videos API
                        watch_duration=None,
                        completion_percentage=None,
                    )

            # Create display table
            table = Table(
                title=f"Liked Videos Synced to Database ({len(saved_videos)} videos)"
            )
            table.add_column("Title", style="cyan", max_width=50)
            table.add_column("Channel", style="green", max_width=30)
            table.add_column("Duration", style="yellow")
            table.add_column("Views", style="magenta")
            table.add_column("Likes", style="red")

            for video in saved_videos[:5]:  # Show first 5
                duration_formatted = f"{video.duration // 60}:{video.duration % 60:02d}"
                table.add_row(
                    video.title[:47] + "..." if len(video.title) > 50 else video.title,
                    (
                        video.channel_id[:27] + "..."
                        if len(video.channel_id) > 30
                        else video.channel_id
                    ),
                    duration_formatted,
                    str(video.view_count) if video.view_count else "Unknown",
                    str(video.like_count) if video.like_count else "Unknown",
                )

            if len(saved_videos) > 5:
                table.add_row("...", "...", "...", "...", "...")

            console.print(table)

            console.print(
                Panel(
                    f"[green]✅ Liked videos synced successfully![/green]\n"
                    f"{len(saved_videos)} videos saved to videos table.\n"
                    f"{len(saved_videos)} user interactions saved to user_videos table.\n"
                    "Data flow: YouTube API → Videos + User Interactions → Database ✅",
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
