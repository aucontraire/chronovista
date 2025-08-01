"""
Topic CLI commands for chronovista.

Commands for exploring topics, finding content by topics, and topic analytics.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chronovista.config.database import db_manager
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.channel_topic_repository import ChannelTopicRepository
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_topic_repository import VideoTopicRepository

console = Console()

topic_app = typer.Typer(
    name="topics",
    help="🏷️ Topic exploration and analytics",
    no_args_is_help=True,
)


@topic_app.command("list")
def list_topics(
    limit: int = typer.Option(
        50, "--limit", "-l", help="Maximum number of topics to show"
    )
) -> None:
    """List all topic categories with content counts."""

    async def run_list() -> None:
        try:
            topic_repo = TopicCategoryRepository()
            async for session in db_manager.get_session(echo=False):
                # Get topics with pagination
                topics = await topic_repo.get_multi(session, skip=0, limit=limit)

                if not topics:
                    console.print(
                        Panel(
                            "[yellow]No topics found in database[/yellow]\n"
                            "Use 'chronovista sync' to populate topic data from YouTube API",
                            title="No Topics",
                            border_style="yellow",
                        )
                    )
                    return

                # Create table for topics
                topic_table = Table(
                    title=f"Topic Categories (showing {len(topics)} of {limit} max)",
                    show_header=True,
                    header_style="bold blue",
                )
                topic_table.add_column("Topic ID", style="cyan", width=20)
                topic_table.add_column("Category Name", style="white", width=30)
                topic_table.add_column("Type", style="green", width=10)
                topic_table.add_column("Parent", style="yellow", width=15)

                for topic in topics:
                    parent_id = topic.parent_topic_id or "-"
                    topic_table.add_row(
                        topic.topic_id, topic.category_name, topic.topic_type, parent_id
                    )

                console.print(topic_table)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error listing topics: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_list())


@topic_app.command("show")
def show_topic(
    topic_id: str = typer.Argument(..., help="Topic ID to show details for")
) -> None:
    """Show detailed information about a specific topic."""

    async def run_show() -> None:
        try:
            topic_repo = TopicCategoryRepository()
            async for session in db_manager.get_session(echo=False):
                topic = await topic_repo.get(session, topic_id)

                if not topic:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic_id}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                # Show topic details
                details = f"""[bold]Topic ID:[/bold] {topic.topic_id}
[bold]Category Name:[/bold] {topic.category_name}
[bold]Type:[/bold] {topic.topic_type}
[bold]Parent Topic:[/bold] {topic.parent_topic_id or 'None'}
[bold]Created:[/bold] {topic.created_at.strftime('%Y-%m-%d %H:%M:%S')}"""

                console.print(
                    Panel(
                        details,
                        title=f"Topic: {topic.category_name}",
                        border_style="blue",
                    )
                )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error showing topic: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_show())


@topic_app.command("channels")
def channels_by_topic(
    topic_id: str = typer.Argument(..., help="Topic ID to find channels for"),
    limit: int = typer.Option(
        20, "--limit", "-l", help="Maximum number of channels to show"
    ),
) -> None:
    """Show channels associated with a specific topic."""

    async def run_channels() -> None:
        try:
            topic_repo = TopicCategoryRepository()
            channel_topic_repo = ChannelTopicRepository()
            channel_repo = ChannelRepository()

            async for session in db_manager.get_session(echo=False):
                # Verify topic exists
                topic = await topic_repo.get(session, topic_id)
                if not topic:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic_id}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                # Find channels with this topic
                # Method signature: find_channels_by_topics(session: AsyncSession, topic_ids: List[str], match_all: bool = False) -> List[str]
                channel_ids = await channel_topic_repo.find_channels_by_topics(
                    session, [topic_id], match_all=False
                )

                if not channel_ids:
                    console.print(
                        Panel(
                            f"[yellow]No channels found for topic '{topic.category_name}'[/yellow]",
                            title="No Channels",
                            border_style="yellow",
                        )
                    )
                    return

                # Limit results
                limited_channel_ids = channel_ids[:limit]

                # Get channel details
                channels_table = Table(
                    title=f"Channels for Topic: {topic.category_name} (showing {len(limited_channel_ids)} of {len(channel_ids)})",
                    show_header=True,
                    header_style="bold blue",
                )
                channels_table.add_column("Channel ID", style="cyan", width=25)
                channels_table.add_column("Title", style="white", width=40)
                channels_table.add_column("Subscribers", style="green", width=15)

                for channel_id in limited_channel_ids:
                    channel = await channel_repo.get_by_channel_id(session, channel_id)
                    if channel:
                        subscriber_count = (
                            f"{channel.subscriber_count:,}"
                            if channel.subscriber_count
                            else "N/A"
                        )
                        channels_table.add_row(
                            channel.channel_id, channel.title, subscriber_count
                        )

                console.print(channels_table)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error finding channels: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_channels())


@topic_app.command("videos")
def videos_by_topic(
    topic_id: str = typer.Argument(..., help="Topic ID to find videos for"),
    limit: int = typer.Option(
        20, "--limit", "-l", help="Maximum number of videos to show"
    ),
) -> None:
    """Show videos associated with a specific topic."""

    async def run_videos() -> None:
        try:
            topic_repo = TopicCategoryRepository()
            video_topic_repo = VideoTopicRepository()
            video_repo = VideoRepository()

            async for session in db_manager.get_session(echo=False):
                # Verify topic exists
                topic = await topic_repo.get(session, topic_id)
                if not topic:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic_id}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                # Find videos with this topic
                # Method signature: find_videos_by_topics(session: AsyncSession, topic_ids: List[str], match_all: bool = False) -> List[str]
                video_ids = await video_topic_repo.find_videos_by_topics(
                    session, [topic_id], match_all=False
                )

                if not video_ids:
                    console.print(
                        Panel(
                            f"[yellow]No videos found for topic '{topic.category_name}'[/yellow]",
                            title="No Videos",
                            border_style="yellow",
                        )
                    )
                    return

                # Limit results
                limited_video_ids = video_ids[:limit]

                # Get video details
                videos_table = Table(
                    title=f"Videos for Topic: {topic.category_name} (showing {len(limited_video_ids)} of {len(video_ids)})",
                    show_header=True,
                    header_style="bold blue",
                )
                videos_table.add_column("Video ID", style="cyan", width=15)
                videos_table.add_column("Title", style="white", width=50)
                videos_table.add_column("Views", style="green", width=15)
                videos_table.add_column("Duration", style="yellow", width=10)

                for video_id in limited_video_ids:
                    video = await video_repo.get_by_video_id(session, video_id)
                    if video:
                        view_count = (
                            f"{video.view_count:,}" if video.view_count else "N/A"
                        )
                        duration = f"{video.duration}s" if video.duration else "N/A"
                        videos_table.add_row(
                            video.video_id,
                            (
                                video.title[:47] + "..."
                                if len(video.title) > 50
                                else video.title
                            ),
                            view_count,
                            duration,
                        )

                console.print(videos_table)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error finding videos: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_videos())
