"""
Data synchronization CLI commands for chronovista.
"""

from __future__ import annotations

from typing import Any, Dict, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chronovista.cli.sync.base import (
    SyncResult,
    check_authenticated,
    display_auth_error,
    display_error,
    display_progress_start,
    display_success,
    display_sync_results,
    display_warning,
    run_sync_operation,
)
from chronovista.cli.sync.transformers import DataTransformers
from chronovista.config.database import db_manager
from chronovista.db.models import Video as VideoDB
from chronovista.models.api_responses import (
    YouTubePlaylistResponse,
    YouTubeVideoResponse,
)
from chronovista.models.channel import ChannelCreate
from chronovista.models.channel_topic import ChannelTopicCreate
from chronovista.models.video import VideoCreate
from chronovista.models.video_topic import VideoTopicCreate
from chronovista.models.youtube_types import UserId
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.channel_topic_repository import ChannelTopicRepository
from chronovista.repositories.playlist_membership_repository import (
    PlaylistMembershipRepository,
)
from chronovista.repositories.playlist_repository import PlaylistRepository
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.repositories.user_video_repository import UserVideoRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_topic_repository import VideoTopicRepository
from chronovista.services import youtube_service

console = Console()

# Repository instances
channel_repository = ChannelRepository()
playlist_repository = PlaylistRepository()
playlist_membership_repository = PlaylistMembershipRepository()
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
                    # T050: Create minimal video record with nullable channel_id
                    # If no valid channel_id, set channel_name_hint for future resolution
                    video_data = VideoCreate(
                        video_id=entry.video_id,
                        channel_id=entry.channel_id if entry.channel_id else None,
                        channel_name_hint=entry.channel_name if not entry.channel_id else None,
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

    async def import_watch_history() -> SyncResult:
        """Import watch history data from takeout file."""
        from pathlib import Path

        from chronovista.parsers.takeout_parser import TakeoutParser

        result = SyncResult()

        # Validate file path
        takeout_file = Path(file_path)
        if not takeout_file.exists():
            display_error(
                f"File not found\nCould not find file: {file_path}",
                title="Watch History Import",
            )
            return result

        # Check authentication using shared utility
        if not check_authenticated():
            display_auth_error("Watch History Import")
            return result

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
                display_error(
                    "Could not identify user\n"
                    "Unable to get your channel ID for user tracking.",
                    title="Watch History Import",
                )
                return result

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
                    display_success(
                        f"Processed {processed:,} / {total_to_process:,} entries"
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

            # Update result counts
            result.created = videos_created + channels_created + user_videos_created
            result.failed = errors

            # Display final results
            if errors == 0:
                display_success(
                    f"Watch history import complete!\n"
                    f"Processed: {processed:,} entries\n"
                    f"Videos: {videos_created:,} created/updated\n"
                    f"Channels: {channels_created:,} created/updated\n"
                    f"User interactions: {user_videos_created:,} created/updated\n"
                    f"Data flow: Google Takeout -> Videos + Channels + UserVideos -> Database"
                )
            else:
                display_warning(
                    f"Watch history import completed with {errors} errors\n"
                    f"Processed: {processed:,} entries\n"
                    f"Videos: {videos_created:,} created/updated\n"
                    f"Channels: {channels_created:,} created/updated\n"
                    f"User interactions: {user_videos_created:,} created/updated\n"
                    f"Errors: {errors:,}",
                    title="Watch History Import Complete",
                )

            return result

        except Exception as e:
            display_error(
                f"Failed to import watch history:\n{str(e)}",
                title="Watch History Import Error",
            )
            return result

    # Run the async function using shared wrapper
    run_sync_operation(import_watch_history, "Watch History Import")


async def _show_playlists_dry_run(
    playlists: list[YouTubePlaylistResponse],
    include_items: bool,
) -> None:
    """
    Display preview of playlists that would be synced without making database changes.

    Parameters
    ----------
    playlists : list[YouTubePlaylistResponse]
        List of playlists from YouTube API
    include_items : bool
        Whether --include-items flag is set
    """
    # Display panel header
    console.print()
    console.print(
        Panel(
            f"[blue]Sync Preview (Dry Run)[/blue]\n"
            f"Total playlists: {len(playlists)}\n"
            f"Include items: {'Yes' if include_items else 'No'}",
            title="Playlist Sync Preview",
            border_style="blue",
        )
    )

    # Create preview table
    table = Table(title=f"Preview: {len(playlists)} Playlists")
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Videos", style="yellow", justify="right")
    table.add_column("Privacy", style="green")
    table.add_column("Language", style="magenta")
    table.add_column("Playlist ID", style="dim", max_width=20)

    for playlist in playlists:
        snippet = playlist.snippet
        content_details = playlist.content_details
        status = playlist.status

        title = snippet.title if snippet else "Unknown"
        video_count = content_details.item_count if content_details else 0
        privacy = status.privacy_status if status else "unknown"
        language = snippet.default_language if snippet else None

        table.add_row(
            title[:37] + "..." if len(title) > 40 else title,
            str(video_count),
            privacy,
            language or "N/A",
            playlist.id[:17] + "..." if len(playlist.id) > 20 else playlist.id,
        )

    console.print(table)

    # Footer message showing what would happen
    console.print()
    console.print(
        "[yellow]This is a dry run - no data will be written to the database[/yellow]"
    )
    console.print()
    console.print("[blue]What would happen:[/blue]")
    console.print(f"   [green]Create or update {len(playlists)} playlists[/green]")

    if include_items:
        total_videos = sum(
            p.content_details.item_count if p.content_details else 0 for p in playlists
        )
        console.print(
            f"   [yellow]Sync up to {total_videos} playlist memberships "
            f"(requires additional API calls)[/yellow]"
        )
    else:
        console.print(
            "   [dim]Skipping playlist items (use --include-items to sync videos)[/dim]"
        )

    console.print()
    console.print("[yellow]Remove --dry-run to perform actual sync[/yellow]")


async def _sync_playlist_items(
    playlists: list[YouTubePlaylistResponse],
    create_missing_channels: bool,
) -> SyncResult:
    """
    Sync videos for each playlist (playlist memberships).

    Parameters
    ----------
    playlists : list[YouTubePlaylistResponse]
        List of playlists to sync items for
    create_missing_channels : bool
        Whether to create channel records if they don't exist

    Returns
    -------
    SyncResult
        Result tracking created/updated/failed memberships
    """
    result = SyncResult()

    for playlist in playlists:
        playlist_id = playlist.id
        snippet = playlist.snippet
        playlist_title = snippet.title if snippet else playlist_id

        console.print(f"[blue]Syncing items for playlist: {playlist_title}[/blue]")

        try:
            # Fetch playlist items from YouTube API
            items = await youtube_service.get_playlist_videos(playlist_id)

            if not items:
                console.print(f"   [dim]No items found in playlist[/dim]")
                continue

            console.print(f"   [dim]Found {len(items)} items[/dim]")

            async for session in db_manager.get_session():
                for item in items:
                    try:
                        # Transform to PlaylistMembershipCreate
                        membership_create = (
                            DataTransformers.extract_playlist_membership_create(item)
                        )

                        if membership_create is None:
                            # Missing required data
                            continue

                        # Check if video exists, create if necessary
                        video_id = membership_create.video_id
                        video_exists = await video_repository.exists(session, video_id)

                        if not video_exists:
                            # Skip videos not in database - video creation
                            # would require additional API calls
                            result.skipped += 1
                            continue

                        # Check if this is an update or create
                        existing = await playlist_membership_repository.get_membership(
                            session, membership_create.playlist_id, video_id
                        )

                        # Save membership
                        await playlist_membership_repository.create_or_update(
                            session, membership_create
                        )

                        if existing:
                            result.updated += 1
                        else:
                            result.created += 1

                    except Exception as e:
                        result.add_error(f"Item in {playlist_title}: {e}")

                await session.commit()

        except Exception as e:
            result.add_error(f"Playlist {playlist_title}: {e}")
            console.print(f"   [red]Error syncing items: {e}[/red]")

    return result


@sync_app.command()
def playlists(
    include_items: bool = typer.Option(
        False,
        "--include-items",
        "-i",
        help="Also sync videos within each playlist (requires additional API calls)",
    ),
    create_missing_channels: bool = typer.Option(
        False,
        "--create-missing-channels",
        help="Create channel records if they don't exist",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be synced without making database changes",
    ),
) -> None:
    """
    Sync playlists from YouTube.

    By default, syncs only playlist metadata. Use --include-items to also
    sync the videos within each playlist (requires additional API calls).

    Examples:
        chronovista sync playlists                    # Sync playlist metadata only
        chronovista sync playlists --include-items    # Include playlist videos
        chronovista sync playlists --dry-run          # Preview without changes
    """
    # Check authentication using framework utility
    if not check_authenticated():
        display_auth_error("Playlist Sync")
        return

    async def sync_playlists_data() -> SyncResult:
        """Sync playlists from YouTube API."""
        result = SyncResult()

        display_progress_start(
            "Fetching your YouTube playlists...",
            title="Playlist Sync",
        )

        # Fetch playlists from YouTube API
        youtube_playlists = await youtube_service.get_my_playlists()

        if not youtube_playlists:
            display_warning(
                "No playlists found\n"
                "Either you haven't created any playlists or they are not accessible.",
                title="No Playlists",
            )
            return result

        display_success(f"Found {len(youtube_playlists)} playlists from YouTube")

        # Handle dry-run mode
        if dry_run:
            await _show_playlists_dry_run(youtube_playlists, include_items)
            return result

        # Process playlists
        console.print("[blue]Saving playlists to database...[/blue]")

        async for session in db_manager.get_session():
            for playlist_data in youtube_playlists:
                try:
                    # Transform YouTube API data using DataTransformers
                    playlist_create = DataTransformers.extract_playlist_create(
                        playlist_data
                    )

                    # Check if playlist already exists
                    existing = await playlist_repository.exists(
                        session, playlist_data.id
                    )

                    # Save to database
                    await playlist_repository.create_or_update(session, playlist_create)

                    if existing:
                        result.updated += 1
                    else:
                        result.created += 1

                except Exception as e:
                    snippet = playlist_data.snippet
                    title = snippet.title if snippet else playlist_data.id
                    result.add_error(f"Playlist '{title}': {e}")
                    console.print(f"[red]Error processing playlist: {e}[/red]")

            await session.commit()

        # Sync playlist items if requested
        items_result = SyncResult()
        if include_items:
            console.print()
            console.print("[blue]Syncing playlist items...[/blue]")
            items_result = await _sync_playlist_items(
                youtube_playlists, create_missing_channels
            )

        # Merge results
        final_result = result.merge(items_result)

        # Create display table for playlists
        table = Table(title="Playlists Synced to Database")
        table.add_column("Title", style="cyan", max_width=40)
        table.add_column("Videos", style="yellow", justify="right")
        table.add_column("Privacy", style="green")
        table.add_column("Status", style="magenta")

        for playlist_data in youtube_playlists[:10]:  # Show first 10
            snippet = playlist_data.snippet
            content_details = playlist_data.content_details
            status = playlist_data.status

            title = snippet.title if snippet else "Unknown"
            video_count = content_details.item_count if content_details else 0
            privacy = status.privacy_status if status else "unknown"

            table.add_row(
                title[:37] + "..." if len(title) > 40 else title,
                str(video_count),
                privacy,
                "Synced",
            )

        if len(youtube_playlists) > 10:
            table.add_row("...", "...", "...", f"+{len(youtube_playlists) - 10} more")

        console.print(table)

        # Display final results
        extra_info = f"Synced {len(youtube_playlists)} playlists to database."
        if include_items:
            extra_info += (
                f"\nPlaylist items: {items_result.created} created, "
                f"{items_result.updated} updated"
            )
            if items_result.skipped > 0:
                extra_info += (
                    f", {items_result.skipped} skipped (videos not in database)"
                )
        extra_info += "\nData flow: YouTube API -> Playlists -> Database"

        display_sync_results(
            final_result,
            title="Playlist Sync Complete",
            extra_info=extra_info,
        )

        return final_result

    # Run the async function using shared wrapper
    run_sync_operation(sync_playlists_data, "Playlist Sync")


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
        # Check authentication using framework utility
        if not check_authenticated():
            display_auth_error("Full Sync")
            return

        display_progress_start(
            "Starting complete data synchronization...\n"
            "This will sync: Topics -> Channel -> Liked Videos",
            title="Full Sync",
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
                            # Use transformer to create the model
                            topic_data = DataTransformers.extract_topic_category_create(
                                category
                            )

                            existing = await topic_category_repository.exists(
                                session, category.id
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
                display_success(
                    f"Topics: {sync_results['topics']['created']} created, "
                    f"{sync_results['topics']['updated']} updated"
                )
            else:
                display_warning("No topic categories found", title="Topics")
                sync_results["topics"]["status"] = "no_data"

        except Exception as e:
            sync_results["topics"]["status"] = "failed"
            display_error(f"Topic sync failed: {e}", title="Topics")

        # Step 2: Sync Channel Data
        try:
            console.print("[cyan]Step 2/3: Syncing your channel information[/cyan]")
            sync_results["channel"]["status"] = "running"

            channel_data = await youtube_service.get_my_channel()

            if channel_data:
                # Process channel data (simplified version)
                title = channel_data.snippet.title if channel_data.snippet else "Unknown"
                display_success(f"Channel synced: {title}")
                sync_results["channel"]["success"] = True
                sync_results["channel"]["status"] = "completed"
            else:
                display_warning("No channel data found", title="Channel")
                sync_results["channel"]["status"] = "no_data"

        except Exception as e:
            sync_results["channel"]["status"] = "failed"
            display_error(f"Channel sync failed: {e}", title="Channel")

        # Step 3: Sync Liked Videos
        try:
            console.print("[cyan]Step 3/3: Syncing liked videos[/cyan]")
            sync_results["liked"]["status"] = "running"

            # Fetch all liked videos (no artificial limit - paginated by API)
            liked_videos = await youtube_service.get_liked_videos()

            if liked_videos:
                sync_results["liked"]["count"] = len(liked_videos)
                display_success(f"Found {len(liked_videos)} liked videos")
                sync_results["liked"]["status"] = "completed"
            else:
                display_warning("No liked videos found", title="Liked Videos")
                sync_results["liked"]["status"] = "no_data"

        except Exception as e:
            sync_results["liked"]["status"] = "failed"
            sync_results["liked"]["errors"] = 1
            display_error(f"Liked videos sync failed: {e}", title="Liked Videos")

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

    # Run the async function using shared wrapper
    run_sync_operation(sync_all_data, "Full Sync")


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

    Uses DataTransformers for consistent data conversion from YouTube API responses.

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

            # Create all channels using DataTransformers
            async for session in db_manager.get_session():
                for channel_data in channel_details:
                    # Use DataTransformers for channel creation
                    channel_create_obj = DataTransformers.extract_channel_create(
                        channel_data
                    )

                    saved_channel = await channel_repository.create_or_update(
                        session, channel_create_obj
                    )
                    new_channels_count += 1

                    # Extract and create channel-topic associations using DataTransformers
                    topic_ids = DataTransformers.extract_topic_ids(channel_data)
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
            display_warning(f"Could not batch fetch channel details: {e}")

    # Now create all videos using DataTransformers
    async for session in db_manager.get_session():
        for video_data in videos_to_create:
            snippet = video_data.snippet
            statistics = video_data.statistics

            # Use DataTransformers for video creation
            video_create = DataTransformers.extract_video_create(video_data)

            # Add statistics that aren't in the base transformer
            # (transformer handles core fields, we add engagement metrics here)
            video_create_with_stats = VideoCreate(
                video_id=video_create.video_id,
                channel_id=video_create.channel_id,
                title=video_create.title,
                description=video_create.description,
                upload_date=video_create.upload_date,
                duration=video_create.duration,
                made_for_kids=video_create.made_for_kids,
                self_declared_made_for_kids=video_create.self_declared_made_for_kids,
                default_language=video_create.default_language,
                default_audio_language=DataTransformers.cast_language_code(
                    snippet.default_audio_language if snippet else None
                ),
                category_id=video_create.category_id,
                like_count=statistics.like_count if statistics else None,
                view_count=statistics.view_count if statistics else None,
                comment_count=statistics.comment_count if statistics else None,
                deleted_flag=False,
            )

            # Now save the video
            saved_video = await video_repository.create_or_update(
                session, video_create_with_stats
            )
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

    Uses DataTransformers for duration parsing.

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

        # Parse duration using DataTransformers
        duration_str = content_details.duration if content_details else None
        duration_seconds = DataTransformers.parse_duration(duration_str)
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
    # Check authentication using framework utility
    if not check_authenticated():
        display_auth_error("Liked Videos Sync")
        return

    async def sync_liked_videos() -> None:
        """Sync liked videos from YouTube API."""
        console.print(
            "[blue]🔄 Fetching your channel info for user identification...[/blue]"
        )

        # Get user's channel ID to use as user_id
        my_channel = await youtube_service.get_my_channel()
        user_id = my_channel.id if my_channel else None

        if not user_id:
            display_error(
                "Could not identify user\n"
                "Unable to get your channel ID for user tracking.",
                title="Liked Videos Sync",
            )
            return

        console.print(
            "[blue]🔄 Fetching your liked videos...[/blue]"
        )

        # Fetch all liked videos from YouTube API (no artificial limit)
        liked_videos = await youtube_service.get_liked_videos()

        if not liked_videos:
            display_warning(
                "No liked videos found\n"
                "Either you haven't liked any videos or the liked videos playlist is private.",
            )
            return

        display_success(f"Found {len(liked_videos)} liked videos from YouTube")

        # Apply topic filtering if requested
        if topic:
            console.print(f"[blue]🔍 Filtering videos by topic ID: {topic}[/blue]")

            # Validate topic exists
            async for session in db_manager.get_session():
                if not await topic_category_repository.exists(session, topic):
                    display_error(
                        f"Invalid topic ID: {topic}\n"
                        "Use [bold]chronovista topics list[/bold] to see available topics.",
                        title="Topic Filter Error",
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
                display_warning(
                    f"No videos found with topic ID: {topic}\n"
                    "Try a different topic or remove the --topic filter.",
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
                await user_video_repository.update_like_status_batch(
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

            display_success(f"Updated liked status for {len(existing_video_ids)} videos")

        # Process missing videos only if --create-missing flag is set
        if missing_video_ids and create_missing:
            console.print()
            console.print(f"[blue]💾 Creating {len(missing_video_ids)} new videos and channels...[/blue]")

            videos_to_create = [v for v in liked_videos if v.id in missing_video_ids]
            created_videos, created_channels = await _create_videos_with_channels(
                videos_to_create, user_id
            )

            display_success(f"Created {len(created_videos)} new videos, {created_channels} new channels")
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

            display_success(f"Updated liked status for {len(created_videos)} videos")

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

    # Run the async function using framework wrapper
    run_sync_operation(sync_liked_videos, "Liked Videos Sync")
